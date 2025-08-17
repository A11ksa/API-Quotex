"""Async WebSocket client for Quotex API."""
import asyncio
import json
import ssl
import time
import base64
from datetime import datetime
import pkg_resources
from collections import deque
from typing import Any, Callable, Dict, List, Optional, Union

import websockets
from websockets.exceptions import ConnectionClosed, ConnectionClosedOK, ConnectionClosedError
from loguru import logger

from .models import ConnectionInfo, ConnectionStatus, ServerTime
from .constants import CONNECTION_SETTINGS, DEFAULT_HEADERS
from .exceptions import WebSocketError, ConnectionError, Base64DecodeError
from .monitoring import error_monitor, ErrorSeverity, ErrorCategory
from .config import Config

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

def _now_ms() -> int:
    """Return current time in milliseconds."""
    return int(time.time() * 1000)

class MessageBatcher:
    """Batch outgoing messages to reduce WebSocket send calls under high load."""
    def __init__(self, batch_size: int = 10, batch_timeout: float = 0.1):
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout
        self.pending_messages: deque = deque()
        self._last_batch_time = time.time()
        self._batch_lock = asyncio.Lock()

    async def add_message(self, message: str) -> List[str]:
        async with self._batch_lock:
            self.pending_messages.append(message)
            current_time = time.time()
            if len(self.pending_messages) >= self.batch_size or (current_time - self._last_batch_time) >= self.batch_timeout:
                batch = list(self.pending_messages)
                self.pending_messages.clear()
                self._last_batch_time = current_time
                return batch
            return []

    async def flush_batch(self) -> List[str]:
        async with self._batch_lock:
            if not self.pending_messages:
                return []
            batch = list(self.pending_messages)
            self.pending_messages.clear()
            self._last_batch_time = time.time()
            return batch

class ConnectionPool:
    """Manages multiple WebSocket connections and tracks their performance statistics."""
    def __init__(self, max_connections: int = 3):
        self.max_connections = max_connections
        self.active_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.connection_stats: Dict[str, Dict[str, Any]] = {}
        self._pool_lock = asyncio.Lock()

    async def get_best_connection(self) -> Optional[str]:
        async with self._pool_lock:
            if not self.connection_stats:
                return None
            best_url = min(
                self.connection_stats.keys(),
                key=lambda url: (
                    self.connection_stats[url].get("avg_response_time", float("inf")),
                    -self.connection_stats[url].get("success_rate", 0.0),
                )
            )
            return best_url

    async def update_stats(self, url: str, response_time: float, success: bool) -> None:
        async with self._pool_lock:
            if url not in self.connection_stats:
                self.connection_stats[url] = {
                    "response_times": deque(maxlen=100),
                    "successes": 0,
                    "failures": 0,
                    "avg_response_time": 0.0,
                    "success_rate": 0.0,
                }
            stats = self.connection_stats[url]
            stats["response_times"].append(response_time)
            if success:
                stats["successes"] += 1
            else:
                stats["failures"] += 1
            if stats["response_times"]:
                stats["avg_response_time"] = sum(stats["response_times"]) / len(stats["response_times"])
            total_attempts = stats["successes"] + stats["failures"]
            if total_attempts > 0:
                stats["success_rate"] = stats["successes"] / total_attempts

class AsyncWebSocketClient:
    """Asynchronous WebSocket client for Quotex API (Engine.IO/Socket.IO v3)."""

    def __init__(self) -> None:
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self.connection_info: Optional[ConnectionInfo] = None
        self.server_time: Optional[ServerTime] = None
        self._status: ConnectionStatus = ConnectionStatus.DISCONNECTED
        self._receiver_task: Optional[asyncio.Task] = None
        self._ping_task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._reconnect_attempts: int = 0
        self._max_reconnect_attempts: int = CONNECTION_SETTINGS["max_reconnect_attempts"]
        self._message_batcher = MessageBatcher()
        self._flush_task: Optional[asyncio.Task] = None  # delayed flush for small bursts
        self._connection_pool = ConnectionPool()
        self._rate_limiter = asyncio.Semaphore(10)
        self._message_cache: Dict[int, Any] = {}
        self._cache_ttl: float = 5.0
        self._event_handlers: Dict[str, List[Callable]] = {}
        # Handlers by prefix (Engine.IO/Socket.IO text frames)
        self._message_handlers: Dict[str, Callable[[str], None]] = {
            "0": self._handle_initial_message,
            "2": self._handle_ping_message,
            "3": self._handle_pong_message,
            "40": self._handle_connection_message,
            "41": self._handle_disconnect_message,
            "451-[": self._handle_json_message_wrapper,   # binary placeholder preface
            "42": self._handle_auth_message,
            "[": self._handle_candle_message,            # Engine.IO binary frame decoded to string (\x04JSON)
        }

        self.websocket_is_connected: bool = False
        self.ssl_mutual_exclusion: bool = False
        self.ssl_mutual_exclusion_write: bool = False
        self._last_auth_error: Optional[Dict] = None
        # Pending event from '451-["event",{"_placeholder":true}]'
        self._pending_binary_event: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return (
            self.websocket is not None
            and not self.websocket.closed
            and self.connection_info is not None
            and self.connection_info.status == ConnectionStatus.CONNECTED
            and self.websocket_is_connected
        )

    async def connect(self, urls: List[str], ssid: str) -> bool:
        for url in urls:
            try:
                logger.info(f"Attempting to connect to {url}")
                ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
                ssl_context.options = (ssl.OP_NO_TLSv1 | ssl.OP_NO_TLSv1_1) | ssl.OP_NO_TLSv1_2
                ws_version = pkg_resources.get_distribution("websockets").version
                connect_kwargs = {
                    "uri": url,
                    "ssl": ssl_context,
                    "ping_interval": 25,
                    "ping_timeout": 5,
                    "close_timeout": CONNECTION_SETTINGS["close_timeout"],
                }
                if float(ws_version.split('.')[0]) >= 8:
                    connect_kwargs["extra_headers"] = DEFAULT_HEADERS
                else:
                    connect_kwargs["headers"] = DEFAULT_HEADERS
                    logger.warning("Using older websockets version; headers parameter may not work as expected")

                self.websocket = await asyncio.wait_for(
                    websockets.connect(**connect_kwargs),
                    timeout=CONNECTION_SETTINGS.get("handshake_timeout", 10.0)
                )
                region = self._extract_region_from_url(url)
                self.connection_info = ConnectionInfo(
                    url=url,
                    region=region,
                    status=ConnectionStatus.CONNECTED,
                    connected_at=datetime.now(),
                    reconnect_attempts=self._reconnect_attempts,
                )
                logger.info(f"Connected to {region} region successfully")
                self._running = True
                self.websocket_is_connected = True
                await self._send_handshake(ssid)
                await self._start_background_tasks()
                self._reconnect_attempts = 0
                self._last_auth_error = None
                return True

            except Exception as e:
                logger.warning(f"Failed to connect to {url}: {str(e)}")
                await error_monitor.record_error(
                    error_type="websocket_connect_failed",
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.CONNECTION,
                    message=f"Failed to connect to {url}: {str(e)}",
                    context={"url": url, "exception": str(e)}
                )
                if self.websocket:
                    try:
                        await self.websocket.close()
                    except Exception:
                        pass
                    self.websocket = None
                self.websocket_is_connected = False
                continue

        raise ConnectionError("Failed to connect to any WebSocket endpoint")

    async def disconnect(self) -> None:
        logger.info("Disconnecting from WebSocket")

        self._running = False

        if self._ping_task and not self._ping_task.done():
            self._ping_task.cancel()
            try:
                await self._ping_task
            except asyncio.CancelledError:
                pass

        if self._receiver_task:
            self._receiver_task.cancel()
            self._receiver_task = None

        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None

        if self.connection_info:
            self.connection_info = ConnectionInfo(
                url=self.connection_info.url,
                region=self.connection_info.region,
                status=ConnectionStatus.DISCONNECTED,
                connected_at=self.connection_info.connected_at,
                last_ping=self.connection_info.last_ping,
                reconnect_attempts=self.connection_info.reconnect_attempts,
            )

        self.websocket_is_connected = False
        self.ssl_mutual_exclusion = False
        self.ssl_mutual_exclusion_write = False

    async def send_message(self, message: str) -> None:
        """
        Queue outgoing Socket.IO frame and send in small batches to reduce syscalls.
        Uses a short delayed flush to coalesce bursts; messages are sent as separate frames
        to preserve Socket.IO framing (no concatenation).
        """
        if not self.websocket or self.websocket.closed:
            self.websocket_is_connected = False
            raise WebSocketError("WebSocket is not connected")

        try:
            while self.ssl_mutual_exclusion or self.ssl_mutual_exclusion_write:
                await asyncio.sleep(0.1)

            self.ssl_mutual_exclusion_write = True

            # Add to batch; if threshold reached, send immediately (each as its own frame)
            batch = await self._message_batcher.add_message(message)
            if batch:
                for msg in batch:
                    await self.websocket.send(msg)
                    logger.debug(f"Sent batched message: {msg}")

            # Ensure a short delayed flush for small bursts
            if not self._flush_task or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._delayed_flush())

            self.ssl_mutual_exclusion_write = False

        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            self.ssl_mutual_exclusion_write = False
            self.websocket_is_connected = False
            await error_monitor.record_error(
                error_type="websocket_send_failed",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.CONNECTION,
                message=f"Failed to send message: {str(e)}",
                context={"message": message[:100]}
            )
            raise WebSocketError(f"Failed to send message: {str(e)}")

    async def _delayed_flush(self) -> None:
        """Flush pending messages after a short delay to coalesce bursts."""
        await asyncio.sleep(0.04)
        leftover = await self._message_batcher.flush_batch()
        if not leftover:
            return
        try:
            for msg in leftover:
                await self.websocket.send(msg)
                logger.debug(f"Sent delayed-flush message: {msg}")
        except Exception as e:
            logger.error(f"Failed to flush batched messages: {str(e)}")
            await error_monitor.record_error(
                error_type="websocket_flush_failed",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.CONNECTION,
                message=f"Failed to flush batched messages: {str(e)}",
                context={}
            )

    async def send_event(self, event: str, data: Any) -> None:
        payload = json.dumps([event, data], separators=(",", ":"))
        await self.send_message("42" + payload)

    async def send_message_optimized(self, message: str) -> None:
        """Compatibility: rate-limited wrapper that delegates to the batched send_message."""
        async with self._rate_limiter:
            await self.send_message(message)

    async def receive_messages(self) -> None:
        try:
            while self._running and self.websocket:
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), timeout=CONNECTION_SETTINGS["receive_timeout"])
                    await self._process_message(message)

                except asyncio.TimeoutError:
                    logger.warning("Message receive timeout")
                    await error_monitor.record_error(
                        error_type="websocket_receive_timeout",
                        severity=ErrorSeverity.MEDIUM,
                        category=ErrorCategory.CONNECTION,
                        message="Timeout waiting for WebSocket message",
                        context={}
                    )
                    continue

                except (ConnectionClosedOK, ConnectionClosed):
                    logger.info("WebSocket connection closed normally (code 1005 or OK)")
                    await self._handle_disconnect()
                    break

                except ConnectionClosedError as e:
                    logger.warning(f"WebSocket connection closed with error: {str(e)}")
                    await self._handle_disconnect()
                    break

        except Exception as e:
            logger.error(f"Error in message receiving: {str(e)}")
            await self._handle_disconnect()
            await error_monitor.record_error(
                error_type="websocket_receive_error",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.CONNECTION,
                message=f"Error in message receiving: {str(e)}",
                context={}
            )

    def on(self, event: str, callback: Callable) -> None:
        self._event_handlers.setdefault(event, []).append(callback)

    def add_event_handler(self, event: str, handler: Callable) -> None:
        self.on(event, handler)

    def remove_event_handler(self, event: str, handler: Callable) -> None:
        if event in self._event_handlers:
            try:
                self._event_handlers[event].remove(handler)
            except ValueError:
                pass

    async def _on_unknown_event(self, event_data: Dict[str, Any]) -> None:
        logger.debug(f"Ignoring unknown event: {event_data}")
        await error_monitor.record_error(
            error_type="unknown_event",
            severity=ErrorSeverity.LOW,
            category=ErrorCategory.DATA,
            message=f"Ignoring unknown event: {event_data}",
            context={"event_data": str(event_data)[:100]}
        )

    async def _recv_until_sioconnect(self, timeout: float = 7.0) -> bool:
        """
        Wait until we see the Socket.IO '40' connect frame.
        Parse Engine.IO open packet '0{...}' safely (strip the leading '0').
        Reply to Engine.IO ping '2' with pong '3' while waiting.
        ALSO: proactively send '40' after receiving the Engine.IO open frame.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            msg = await asyncio.wait_for(self.websocket.recv(), timeout=timeout)
            if not isinstance(msg, str):
                continue

            if msg.startswith("0"):
                try:
                    data = json.loads(msg[1:])
                    self.server_time = ServerTime(
                        server_timestamp=data.get("sid_timestamp", time.time()),
                        local_timestamp=time.time(),
                        offset=0.0
                    )
                    await self._emit_event("connected", {"sid": data.get("sid")})
                    self.websocket_is_connected = True
                    # Important: open default namespace
                    await self.send_message("40")
                except json.JSONDecodeError:
                    logger.error("Failed to parse initial message (Engine.IO open)")
                    await error_monitor.record_error(
                        error_type="websocket_initial_message_parse_error",
                        severity=ErrorSeverity.MEDIUM,
                        category=ErrorCategory.DATA,
                        message="Failed to parse initial Engine.IO open",
                        context={}
                    )
                    continue

            elif msg == "40":
                return True

            elif msg == "2":
                await self.send_message("3")

            else:
                continue

    async def _process_message(self, message: Union[str, bytes]) -> None:
        """Process incoming WebSocket messages with enhanced event handling (handles PONG '3')."""
        try:
            # Binary frames
            if isinstance(message, bytes):
                try:
                    decoded_message = message.decode("utf-8")
                    logger.debug(f"Received binary message: {decoded_message[:100]}...")
                    if decoded_message.startswith('\x04'):
                        # Delegate to binary handler that understands pending 451- header
                        await self._handle_candle_message(decoded_message)
                    else:
                        logger.debug(f"Non-JSON binary message: {decoded_message[:100]}...")
                except UnicodeDecodeError:
                    logger.error("Failed to decode binary message")
                    await error_monitor.record_error(
                        error_type="binary_decode_error",
                        severity=ErrorSeverity.MEDIUM,
                        category=ErrorCategory.DATA,
                        message="Failed to decode binary WebSocket message",
                        context={}
                    )
                return

            # Text frames
            logger.debug(f"Received message: {message[:100]}...")

            # Engine.IO heartbeat
            if message == "2":                     # ping → reply with pong
                await self.send_message("3")
                return

            if message == "3":                     # explicit pong handling
                await self._handle_pong_message(message)
                return

            # Engine.IO open → send Socket.IO connect (if this comes through here)
            if message.startswith("0") and "sid" in message:
                await self.send_message("40")
                return

            # Socket.IO connected ack (some servers echo '40' with sid in same line)
            if message.startswith("40") and "sid" in message:
                await self._emit_event("connected", {})
                self.websocket_is_connected = True
                return

            # Handle Socket.IO disconnect '41'
            if message == "41" or message.startswith("41"):
                await self._handle_disconnect_message(message)
                return

            # Socket.IO array events
            if message.startswith("42"):
                await self._handle_auth_message(message)
                return

            # JSON header announcing a following binary payload
            if message.startswith("451-["):
                await self._handle_json_message_wrapper(message)
                return

            # Unknown text frames → low severity
            logger.warning(f"Unknown message format: {message[:100]}...")
            await self._emit_event("unknown_event", {"type": "unknown", "data": message})

        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            self.websocket_is_connected = False
            self.ssl_mutual_exclusion = False
            await error_monitor.record_error(
                error_type="message_processing_error",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.DATA,
                message=f"Error processing WebSocket message: {str(e)}",
                context={"message": str(message)[:100]}
            )

    async def _handle_initial_message(self, message: str) -> None:
        if message.startswith("0") and "sid" in message:
            try:
                data = json.loads(message[1:])
                self.server_time = ServerTime(
                    server_timestamp=data.get("sid_timestamp", time.time()),
                    local_timestamp=time.time(),
                    offset=0.0
                )
                await self._emit_event("connected", {"sid": data.get("sid")})
                self.websocket_is_connected = True
            except json.JSONDecodeError:
                logger.error("Failed to parse initial message")
                await error_monitor.record_error(
                    error_type="websocket_initial_message_parse_error",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.DATA,
                    message="Failed to parse initial message",
                    context={"message": message[:100]}
                )

    async def _handle_ping_message(self, message: str) -> None:
        await self.send_message("3")
        logger.debug("Received ping, sent pong")
        if self.connection_info:
            self.connection_info = ConnectionInfo(
                url=self.connection_info.url,
                region=self.connection_info.region,
                status=self.connection_info.status,
                connected_at=self.connection_info.connected_at,
                last_ping=datetime.now(),
                reconnect_attempts=self.connection_info.reconnect_attempts,
            )

    async def _handle_pong_message(self, message: str) -> None:
        logger.debug("Received pong message")

    async def _handle_connection_message(self, message: str) -> None:
        logger.debug("Received connection message")

    async def _handle_disconnect_message(self, message: str) -> None:
        logger.info("Received Socket.IO disconnect message ('41')")
        await self._handle_disconnect()

    async def _handle_json_message_wrapper(self, message: str) -> None:
        """
        Example header lines:
          451-["s_balance",{"_placeholder":true,"num":0}]
          451-["s_orders/open",{"_placeholder":true,"num":0}]
          451-["s_orders/close",{"_placeholder":true,"num":0}]
          451-["instruments/list",{"_placeholder":true,"num":0}]
          451-["quotes/stream",{"_placeholder":true,"num":0}]
          451-["history/list/v2",{"_placeholder":true,"num":0}]
        Next line (payload) arrives as a separate Engine.IO binary frame that starts with \x04 then raw JSON.
        """
        try:
            head = message.split('451-[')[1]
            event_name = head.split('"')[1]  # e.g. s_orders/open
            self._pending_binary_event = event_name
            logger.debug(f"Pending binary event set to: {self._pending_binary_event}")
        except Exception as e:
            logger.error(f"Failed to parse 451- header: {e}")
            await error_monitor.record_error(
                error_type="json_wrapper_parse_error",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.DATA,
                message=f"Failed to parse 451- header: {str(e)}",
                context={"message": message[:120]}
            )

    async def _handle_auth_message(self, message: str) -> None:
        """
        Handle Socket.IO '42' packets with unified routing:
          - Authentication
          - Assets / Quotes / History
          - Orders open/close (single and list)
          - Balance updates
          - Errors
        """
        try:
            if not message.startswith("42"):
                return

            data = json.loads(message[2:])
            if not (isinstance(data, list) and len(data) >= 1):
                return

            event = data[0]
            body = data[1] if len(data) > 1 else {}

            # ---- Routing (unified) ----
            if event == "s_authorization":
                await self._emit_event("authenticated", body)
                self.websocket_is_connected = True
                self.ssl_mutual_exclusion = False
                return

            if event in ("instruments/list",):
                await self._emit_event("assets_list", body)
                return

            if event in ("quotes/stream",):
                await self._emit_event("quote_stream", body)
                return

            if event in ("history/list/v2", "chart_notification/get", "loadHistoryPeriod"):
                await self._emit_event("candles_received", body)
                return

            if event in ("successupdateBalance",):
                await self._emit_event("balance_updated", body)
                return

            if event in ("s_orders/open", "successopenOrder"):
                # Some servers send string "OPEN", ignore that and pass dicts only
                if isinstance(body, dict):
                    await self._emit_event("order_opened", body)
                return

            if event in ("s_orders/close", "successcloseOrder"):
                # payload may be {"deals":[{...}, ...]} or {"ticket":{...}} or a single dict
                deals: List[Dict[str, Any]] = []
                if isinstance(body, dict):
                    if isinstance(body.get("deals"), list):
                        deals = [d for d in body["deals"] if isinstance(d, dict)]
                    elif isinstance(body.get("ticket"), dict):
                        deals = [body["ticket"]]
                    else:
                        deals = [body]
                elif isinstance(body, list):
                    deals = [d for d in body if isinstance(d, dict)]

                for d in deals:
                    await self._emit_event("order_closed", d)
                return

            if event in ("orders/closed/list",):
                bulk = body if isinstance(body, list) else []
                await self._emit_event("orders_closed_list", bulk)
                return

            if event in ("error",):
                await self._emit_event("error", body)
                return

            # Fallback: forward raw
            await self._emit_event("json_data", {"event": event, "data": body})

        except Exception as e:
            logger.error(f"Error in _handle_auth_message: {e}")
            await error_monitor.record_error(
                error_type="auth_frame_error",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.DATA,
                message=f"Error in _handle_auth_message: {str(e)}",
                context={}
            )

    def _event_headerless_payload(self, payload: Any) -> str:
        """
        Infer event type when a binary Engine.IO frame (\x04JSON) arrives WITHOUT a preceding 451 header.
        Shapes:
          - instruments/list: payload is a LIST of LISTs, where inner[0] is int (id), inner[1] is str (symbol), inner[2] is str (name)
          - quotes/stream: payload is a LIST of LISTs where inner[0] is str (symbol), inner[1] is timestamp, inner[2] is price
          - candles/history: payload is a DICT with {"asset","period","history"}
          - balance blob: payload is a DICT with {"uid","balance"}
          - default → "json_data"
        """
        try:
            if isinstance(payload, list) and payload:
                first = payload[0]
                if isinstance(first, list) and len(first) >= 3 and isinstance(first[0], int) and isinstance(first[1], str) and isinstance(first[2], str):
                    return "assets_list"
                if isinstance(first, list) and len(first) >= 3 and isinstance(first[0], str) and isinstance(first[1], (int, float)):
                    return "quote_stream"
            if isinstance(payload, dict):
                if all(k in payload for k in ("asset", "period", "history")):
                    return "candles_received"
                if "uid" in payload and "balance" in payload:
                    return "balance_data"
        except Exception:
            pass
        return "json_data"

    async def _handle_candle_message(self, message: str) -> None:
        """
        Handles Engine.IO binary frame decoded as str that starts with '\x04'.
        After '\x04' is pure JSON (object or array).
        Supports:
          - headered flow: 451-["<event>",...]  then \x04{...}
          - headerless flow: directly \x04[...] or \x04{...}
        """
        try:
            if not message.startswith("\x04"):
                return

            payload = json.loads(message[1:])  # strip \x04

            # No pending header (headerless push)
            if not self._pending_binary_event:
                inferred = self._event_headerless_payload(payload)
                logger.debug(f"Headerless \\x04 payload inferred as: {inferred}")
                await self._emit_event(inferred, payload)
                return

            # We have a header stored from 451-[...]
            event_name = self._pending_binary_event
            self._pending_binary_event = None  # reset

            logger.debug(f"Dispatching payload for {event_name}")

            if event_name == "s_balance":
                await self._emit_event("balance_data", payload)

            elif event_name == "s_orders/open":
                await self._emit_event("order_opened", payload)

            elif event_name == "s_orders/close":
                deals = (payload or {}).get("deals") or []
                if isinstance(deals, list):
                    for d in deals:
                        await self._emit_event("order_closed", d)
                else:
                    ticket = (payload or {}).get("ticket")
                    if isinstance(ticket, dict):
                        await self._emit_event("order_closed", ticket)

            elif event_name == "orders/closed/list":
                # Emit as a dedicated event (not json_data) to match client handler
                await self._emit_event("orders_closed_list", payload if isinstance(payload, list) else [])

            elif event_name == "instruments/list":
                await self._emit_event("assets_list", payload)

            elif event_name == "quotes/stream":
                await self._emit_event("quote_stream", payload)

            elif event_name == "history/list/v2":
                await self._emit_event("candles_received", payload)

            else:
                await self._emit_event("json_data", {"event": event_name, "data": payload})

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error for binary payload: {e}")
            await error_monitor.record_error(
                error_type="binary_json_decode_error",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.DATA,
                message=f"JSON decode error for binary payload: {str(e)}",
                context={}
            )

        except Exception as e:
            logger.error(f"Error handling binary payload: {e}")
            await error_monitor.record_error(
                error_type="binary_payload_error",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.DATA,
                message=f"Error handling binary payload: {str(e)}",
                context={}
            )

    async def _handle_json_message(self, data: List[Any]) -> None:
        """Handle JSON messages with comprehensive event detection."""
        if not data or len(data) < 1:
            logger.debug("Empty JSON message received")
            return

        event_type = data[0]
        event_data = data[1] if len(data) > 1 else {}

        logger.debug(f"Processing JSON event: {event_type}")

        if event_type == "s_authorization":
            await self._emit_event("authenticated", event_data)
            self.websocket_is_connected = True
            self.ssl_mutual_exclusion = False
            await self.send_message('451-["instruments/list",{"_placeholder":true,"num":0}]')
            logger.debug("Sent instruments/list request after s_authorization")

        elif event_type == "successauth":
            await self._emit_event("authenticated", event_data)
            self.websocket_is_connected = True
            self.ssl_mutual_exclusion = False
            await self.send_message('451-["instruments/list",{"_placeholder":true,"num":0}]')
            logger.debug("Sent instruments/list request after authentication")

        elif event_type == "successupdateBalance":
            await self._emit_event("balance_updated", event_data)

        elif event_type == "s_balance":
            await self._emit_event("balance_data", event_data)

        elif event_type == "s_balance/list":
            await self._emit_event("balance_list", event_data)
            logger.info("Received balance list data")

        elif event_type == "settings/list":
            await self._emit_event("settings_list", event_data)
            logger.info("Received settings list data")

        elif event_type == "orders/opened/list":
            await self._emit_event("orders_opened_list", event_data)
            logger.info("Received opened orders list")

        elif event_type == "s_drawing/load":
            await self._emit_event("drawing_load", event_data)
            logger.info("Received drawing load data")

        elif event_type == "orders/closed/list":
            await self._emit_event("orders_closed_list", event_data)
            logger.info("Received closed orders list")

        elif event_type == "successopenOrder":
            await self._emit_event("order_opened", event_data)

        elif event_type == "successcloseOrder":
            await self._emit_event("order_closed", event_data)

        elif event_type == "updateStream":
            await self._emit_event("stream_update", event_data)

        elif event_type == "loadHistoryPeriod":
            await self._emit_event("candles_received", event_data)

        elif event_type == "updateHistoryNew":
            await self._emit_event("history_update", event_data)

        elif event_type == "instruments/list":
            await self._emit_event("assets_list", event_data)

        elif event_type == "quotes/stream":
            await self._emit_event("quote_stream", event_data)

        elif event_type == "depth/change":
            await self._emit_event("depth_change", event_data)

        elif event_type == "error":
            if "authorization/reject" in str(event_data):
                self._last_auth_error = {"message": "Authorization rejected by server"}
                await self._emit_event("auth_error", self._last_auth_error)
                await error_monitor.record_error(
                    error_type="websocket_auth_failed",
                    severity=ErrorSeverity.CRITICAL,
                    category=ErrorCategory.AUTHENTICATION,
                    message="Authentication failed: Authorization rejected",
                    context={"event_data": str(event_data)[:100]}
                )
            else:
                await self._emit_event("error", event_data)
                await error_monitor.record_error(
                    error_type=f"websocket_server_error_{event_data.get('error', 'unknown')}",
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.DATA,
                    message=f"Server error: {event_data}",
                    context={"event_data": str(event_data)[:100]}
                )
        else:
            logger.warning(f"Unknown JSON event type: {event_type}")
            await self._emit_event("unknown_event", {"type": event_type, "data": event_data})

    async def _emit_event(self, event: str, data: Any) -> None:
        logger.info(f"Dispatching event: {event}, data={str(data)[:200]}")
        handlers = self._event_handlers.get(event, [])
        for cb in handlers:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(data)
                else:
                    cb(data)
            except Exception as e:
                logger.error(f"Error in handler for {event}: {e}")
                await error_monitor.record_error(
                    error_type=f"handler_error_{event}",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.SYSTEM,
                    message=f"Error in handler for {event}: {str(e)}",
                    context={"event": event}
                )

    async def _handle_disconnect(self) -> None:
        logger.info("Handling WebSocket disconnection")

        if self.connection_info:
            self.connection_info = ConnectionInfo(
                url=self.connection_info.url,
                region=self.connection_info.region,
                status=ConnectionStatus.DISCONNECTED,
                connected_at=self.connection_info.connected_at,
                last_ping=self.connection_info.last_ping,
                reconnect_attempts=self.connection_info.reconnect_attempts + 1,
            )

        self.websocket_is_connected = False
        self.ssl_mutual_exclusion = False
        await self._emit_event("disconnected", {})

        if self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            logger.info(f"Attempting reconnection {self._reconnect_attempts}/{self._max_reconnect_attempts}")
            delay = min(
                CONNECTION_SETTINGS["reconnect_initial_delay"] * (CONNECTION_SETTINGS["reconnect_factor"] ** self._reconnect_attempts),
                CONNECTION_SETTINGS["reconnect_max_delay"]
            )
            await asyncio.sleep(delay)
            await error_monitor.record_error(
                error_type="websocket_reconnect_attempt",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.CONNECTION,
                message=f"Attempting reconnection {self._reconnect_attempts}/{self._max_reconnect_attempts}",
                context={"attempt": self._reconnect_attempts}
            )
        else:
            logger.error("Max reconnect attempts reached. Connection terminated.")

    def _extract_region_from_url(self, url: str) -> str:
        try:
            parts = url.split("//")[1].split(".")[0]
            if "ws-" in parts:
                return parts.replace("ws-", "").upper()
            elif "demo" in parts:
                return "DEMO"
            else:
                return "LIVE"
        except Exception:
            return "UNKNOWN"

        return False
