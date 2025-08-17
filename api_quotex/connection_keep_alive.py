"""Connection Keep-Alive Manager for Quotex API"""
import asyncio
import time
import json
import base64
from collections import defaultdict
from typing import Dict, List, Any, Callable, Optional, Union
from websockets.exceptions import ConnectionClosed
from datetime import datetime, timedelta
from loguru import logger
from .monitoring import error_monitor, ErrorSeverity, ErrorCategory
from .constants import REGIONS, CONNECTION_SETTINGS

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

class ConnectionKeepAlive:
    def __init__(self, ssid: str, is_demo: bool = True):
        self.ssid = ssid
        self.is_demo = is_demo
        self.is_connected = False
        self._websocket = None
        self._event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._ping_task = None
        self._reconnect_task = None
        self._health_task = None
        self._assets_request_task = None
        self._last_assets_request = None
        self._connection_stats = {
            "last_ping_time": None,
            "last_pong_time": None,
            "total_reconnections": 0,
            "messages_sent": 0,
            "messages_received": 0,
        }
        try:
            from .websocket_client import AsyncWebSocketClient
            self._websocket_client_class = AsyncWebSocketClient
        except ImportError:
            logger.error("Failed to import AsyncWebSocketClient")
            raise ImportError("AsyncWebSocketClient module not available")

    def add_event_handler(self, event: str, handler: Callable):
        self._event_handlers[event].append(handler)

    async def _trigger_event_async(self, event: str, data: Dict[str, Any]) -> None:
        try:
            for handler in self._event_handlers.get(event, []):
                if asyncio.iscoroutinefunction(handler):
                    await handler(data)
                else:
                    handler(data)
        except Exception as e:
            logger.error(f"Error in {event} handler: {e}")
            await error_monitor.record_error(
                error_type=f"{event}_handler_error",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.SYSTEM,
                message=f"Error in {event} handler: {str(e)}",
                context={"event": event}
            )

    async def _trigger_event(self, event: str, *args, **kwargs):
        if not self._websocket or not getattr(self._websocket, "is_connected", False):
            logger.warning(f"Skipping {event} handler: WebSocket is not connected")
            return
        for handler in self._event_handlers.get(event, []):
            try:
                data = kwargs.get("data", {})
                if asyncio.iscoroutinefunction(handler):
                    await self._handle_async_callback(handler, (data,), {})
                else:
                    handler(data)
            except Exception as e:
                logger.error(f"Error in {event} handler: {e}")
                await error_monitor.record_error(
                    error_type=f"{event}_handler_error",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.SYSTEM,
                    message=f"Error in {event} handler: {str(e)}",
                    context={"event": event}
                )

    async def _handle_async_callback(self, callback, args, kwargs):
        try:
            await callback(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in async callback: {e}")
            await error_monitor.record_error(
                error_type="async_callback_error",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.SYSTEM,
                message=f"Error in async callback: {str(e)}",
                context={}
            )

    async def _forward_balance_data(self, data):
        await self._trigger_event_async("balance_data", data=data)

    async def _forward_balance_updated(self, data):
        await self._trigger_event_async("balance_updated", data=data)

    async def _forward_authenticated(self, data):
        await self._trigger_event_async("authenticated", data=data)

    async def _forward_order_opened(self, data):
        await self._trigger_event_async("order_opened", data=data)

    async def _forward_order_closed(self, data):
        await self._trigger_event_async("order_closed", data=data)

    async def _forward_candles_received(self, data):
        await self._trigger_event_async("candles_received", data=data)

    async def _forward_assets_updated(self, data):
        await self._trigger_event_async("assets_list", data=data)

    async def _forward_stream_update(self, data):
        await self._trigger_event_async("stream_update", data=data)

    async def _forward_quote_stream(self, data):
        await self._trigger_event_async("quote_stream", data=data)

    async def _forward_error(self, data):
        await self._trigger_event_async("error", data=data)

    async def _forward_json_data(self, data):
        await self._trigger_event_async("json_data", data=data)

    async def connect_with_keep_alive(self, regions: Optional[List[str]] = None) -> bool:
        if not self._websocket:
            self._websocket = self._websocket_client_class()
            # wire forwarders ...
            self._websocket.add_event_handler("balance_data", self._forward_balance_data)
            self._websocket.add_event_handler("balance_updated", self._forward_balance_updated)
            self._websocket.add_event_handler("authenticated", self._forward_authenticated)
            self._websocket.add_event_handler("order_opened", self._forward_order_opened)
            self._websocket.add_event_handler("order_closed", self._forward_order_closed)
            self._websocket.add_event_handler("candles_received", self._forward_candles_received)
            self._websocket.add_event_handler("assets_list", self._forward_assets_updated)
            self._websocket.add_event_handler("stream_update", self._forward_stream_update)
            self._websocket.add_event_handler("quote_stream", self._forward_quote_stream)
            self._websocket.add_event_handler("error", self._forward_error)
            self._websocket.add_event_handler("json_data", self._forward_json_data)

        # Use given frame if already complete, else wrap session only
        if self.ssid.startswith('42["authorization",'):
            ssid_message = self.ssid
        else:
            ssid_message = (
                f'42["authorization", {{"session":"{self.ssid}","isDemo":{1 if self.is_demo else 0},"tournamentId":0}}]'
            )

        if not regions:
            all_regions = REGIONS.get_all_regions()
            if self.is_demo:
                demo_urls = REGIONS.get_demo_regions()
                regions = [name for name, url in all_regions.items() if url in demo_urls]
            else:
                regions = [name for name, url in all_regions.items() if "DEMO" not in name.upper()]

        for region_name in regions:
            region_url = REGIONS.get_region(region_name)
            if not region_url:
                continue
            try:
                logger.info(f"Trying to connect to {region_name} ({region_url})")
                ok = await asyncio.wait_for(
                    self._websocket.connect([region_url], ssid_message),
                    timeout=CONNECTION_SETTINGS["handshake_timeout"]
                )
                if ok:
                    logger.info(f"Connected to {region_name}")
                    self.is_connected = True
                    self._start_keep_alive_tasks()
                    await self._trigger_event_async("connected", data={"region": region_name, "url": region_url})
                    await self._websocket.send_message('451-["instruments/list",{"_placeholder":true,"num":0}]')
                    return True
            except asyncio.TimeoutError:
                logger.warning(f"Connection timeout to {region_name}")
                await error_monitor.record_error(
                    error_type="connection_timeout",
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.CONNECTION,
                    message=f"Connection timeout to {region_name}",
                    context={"region": region_name}
                )
            except Exception as e:
                logger.warning(f"Failed to connect to {region_name}: {e}")
                await error_monitor.record_error(
                    error_type="connection_failed",
                    severity=ErrorSeverity.HIGH,
                    category=ErrorCategory.CONNECTION,
                    message=f"Failed to connect to {region_name}: {str(e)}",
                    context={"region": region_name, "exception": str(e)}
                )
        return False

    def _start_keep_alive_tasks(self):
        logger.info("Starting keep-alive tasks")
        if self._ping_task:
            self._ping_task.cancel()
        self._ping_task = asyncio.create_task(self._ping_loop())
        if self._reconnect_task:
            self._reconnect_task.cancel()
        self._reconnect_task = asyncio.create_task(self._reconnection_monitor())
        if self._health_task:
            self._health_task.cancel()
        self._health_task = asyncio.create_task(self._health_monitor_loop())
        if self._assets_request_task:
            self._assets_request_task.cancel()
        self._assets_request_task = asyncio.create_task(self._assets_request_loop())

    async def _ping_loop(self):
        """Engine.IO heartbeat: send '2' periodically; upstream will reply '3' (PONG)."""
        while self.is_connected and self._websocket:
            try:
                await self._websocket.send_message('2')
                self._connection_stats["last_ping_time"] = time.time()
                self._connection_stats["messages_sent"] += 1
                logger.debug("Ping sent")
                await asyncio.sleep(25)
            except Exception as e:
                logger.warning(f"Ping failed: {e}")
                self.is_connected = False
                await error_monitor.record_error(
                    error_type="ping_failed",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.CONNECTION,
                    message=f"Ping failed: {str(e)}",
                    context={}
                )

    async def _health_monitor_loop(self):
        logger.info("Starting health monitor...")
        while True:
            try:
                await asyncio.sleep(30)
                if not self.is_connected or not self._websocket:
                    continue
                if self._connection_stats["last_ping_time"]:
                    time_since_ping = (
                        datetime.now() - datetime.fromtimestamp(self._connection_stats["last_ping_time"])
                    ).total_seconds()
                    if time_since_ping > 60:
                        logger.warning("No ping response, connection may be dead")
                        self.is_connected = False
                        await error_monitor.record_error(
                            error_type="no_ping_response",
                            severity=ErrorSeverity.HIGH,
                            category=ErrorCategory.CONNECTION,
                            message="No ping response, connection may be dead",
                            context={"time_since_ping": time_since_ping}
                        )
                if not self._websocket.is_connected:
                    logger.warning("WebSocket is closed")
                    self.is_connected = False
                    await error_monitor.record_error(
                        error_type="websocket_closed",
                        severity=ErrorSeverity.HIGH,
                        category=ErrorCategory.CONNECTION,
                        message="WebSocket is closed",
                        context={}
                    )
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
                self.is_connected = False
                await error_monitor.record_error(
                    error_type="health_monitor_error",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.SYSTEM,
                    message=f"Health monitor error: {str(e)}",
                    context={}
                )

    async def _assets_request_loop(self):
        """
        Periodically request instruments list to keep local cache fresh.
        Uses a conservative cadence and guards against spamming the server.
        """
        logger.info("Starting assets request loop...")
        while self.is_connected and self._websocket:
            try:
                now = datetime.now()
                if self._last_assets_request:
                    if (now - self._last_assets_request).total_seconds() < 60:
                        await asyncio.sleep(30)
                        continue
                await self._websocket.send_message('451-["instruments/list",{"_placeholder":true,"num":0}]')
                self._last_assets_request = now
                self._connection_stats["messages_sent"] += 1
                logger.debug("Assets data request sent")
                await asyncio.sleep(60)
            except Exception as e:
                logger.warning(f"Assets request failed: {e}")
                self.is_connected = False
                await error_monitor.record_error(
                    error_type="assets_request_failed",
                    severity=ErrorSeverity.MEDIUM,
                    category=ErrorCategory.DATA,
                    message=f"Assets request failed: {str(e)}",
                    context={}
                )

    async def _reconnection_monitor(self):
        """
        Watchdog: if connection drops, attempt a clean reconnect and resubscribe to instruments.
        """
        logger.info("Starting reconnection monitor...")
        while True:
            await asyncio.sleep(30)
            if not self.is_connected or not self._websocket or not self._websocket.is_connected:
                logger.info("Connection lost, reconnecting...")
                self.is_connected = False
                self._connection_stats["total_reconnections"] += 1
                try:
                    success = await self.connect_with_keep_alive()
                    if success:
                        logger.info("Reconnection successful")
                        await self._trigger_event_async("reconnected", data={})
                        await self._websocket.send_message('451-["instruments/list",{"_placeholder":true,"num":0}]')
                    else:
                        logger.error("Reconnection failed")
                        await error_monitor.record_error(
                            error_type="reconnection_failed",
                            severity=ErrorSeverity.HIGH,
                            category=ErrorCategory.CONNECTION,
                            message="Reconnection failed",
                            context={"attempt": self._connection_stats["total_reconnections"]}
                        )
                except Exception as e:
                    logger.error(f"Reconnection error: {e}")
                    await error_monitor.record_error(
                        error_type="reconnection_error",
                        severity=ErrorSeverity.HIGH,
                        category=ErrorCategory.CONNECTION,
                        message=f"Reconnection error: {str(e)}",
                        context={"attempt": self._connection_stats["total_reconnections"]}
                    )

    async def disconnect(self):
        logger.info("Disconnecting...")
        try:
            if self._ping_task:
                self._ping_task.cancel()
                try:
                    await self._ping_task
                except asyncio.CancelledError:
                    pass
            if self._reconnect_task:
                self._reconnect_task.cancel()
                try:
                    await self._reconnect_task
                except asyncio.CancelledError:
                    pass
            if self._health_task:
                self._health_task.cancel()
                try:
                    await self._health_task
                except asyncio.CancelledError:
                    pass
            if self._assets_request_task:
                self._assets_request_task.cancel()
                try:
                    await self._assets_request_task
                except asyncio.CancelledError:
                    pass
            if self._websocket:
                await self._websocket.disconnect()
            self.is_connected = False
            logger.info("Disconnected")
            await self._trigger_event_async("disconnected", data={})
        except Exception as e:
            logger.error(f"Error during disconnection: {e}")
            await error_monitor.record_error(
                error_type="disconnect_error",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.CONNECTION,
                message=f"Error during disconnection: {str(e)}",
                context={}
            )

    async def send_message(self, message):
        if not self.is_connected or not self._websocket:
            raise ConnectionError("Not connected")
        try:
            await self._websocket.send_message(message)
            self._connection_stats["messages_sent"] += 1
            logger.debug(f"Sent message: {message[:100]}...")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self.is_connected = False
            await error_monitor.record_error(
                error_type="send_message_failed",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.CONNECTION,
                message=f"Failed to send message: {str(e)}",
                context={"message": message[:100]}
            )
            raise ConnectionError(f"Failed to send message: {e}")

    async def on_message(self, message: Union[str, bytes]):
        """
        Old-compat + New-compat Engine.IO / Socket.IO message handler.

        Old library behaviour preserved:
          - Send 'tick' at second==0 and after processing frames (best-effort).
          - Detect 'authorization/reject' and 's_authorization'.
          - Handle two-part headers '451-'/'51-' followed by a binary JSON frame starting with '\\x04'.
          - Interpret payloads by keys (liveBalance/demoBalance, index, id, ticket, deals ...).

        New library behaviour added:
          - Reply '3' to server PING '2'; just record server PONG '3'.
          - Decode 'BFtb' base64-wrapped frames when present.
          - Route topics to unified forwarders via _trigger_event_async(...).
        """
        # Old-style periodic tick: send when time.second == 0 (best-effort)
        try:
            if self._websocket and getattr(self._websocket, "is_connected", False):
                if int(time.time()) % 60 == 0:
                    try:
                        await self._websocket.send_message('42["tick"]')
                    except Exception:
                        pass
        except Exception:
            pass

        # Lazy init for old-style header bookkeeping
        if not hasattr(self, "_pending_binary_event"):
            self._pending_binary_event = None
        if not hasattr(self, "_temp_status"):
            self._temp_status = ""

        try:
            self._connection_stats["messages_received"] += 1

            # Bytes → UTF-8
            if isinstance(message, (bytes, bytearray)):
                try:
                    message = message.decode("utf-8")
                except UnicodeDecodeError:
                    logger.error("on_message: failed to decode bytes message")
                    await error_monitor.record_error(
                        error_type="message_decode_error",
                        severity=ErrorSeverity.MEDIUM,
                        category=ErrorCategory.DATA,
                        message="Failed to decode bytes message",
                        context={}
                    )
                    return

            # Optional base64 wrapper: 'BFtb' + b64
            if isinstance(message, str) and message.startswith("BFtb"):
                try:
                    message = base64.b64decode(message[4:]).decode("utf-8")
                except Exception as e:
                    logger.error(f"on_message: base64 decode error: {e}")
                    await error_monitor.record_error(
                        error_type="base64_decode_error",
                        severity=ErrorSeverity.MEDIUM,
                        category=ErrorCategory.DATA,
                        message=f"Base64 decode error: {str(e)}",
                        context={}
                    )
                    return

            # Engine.IO heartbeat (new)
            if message == "2":  # PING
                try:
                    await self._websocket.send_message("3")  # PONG
                    self._connection_stats["last_pong_time"] = time.time()
                except Exception as e:
                    logger.error(f"on_message: failed to send PONG: {e}")
                return
            if message == "3":  # server PONG
                self._connection_stats["last_pong_time"] = time.time()
                return

            # Engine.IO handshake assist: send '40' after initial '0...sid...'
            if isinstance(message, str) and message.startswith("0") and "sid" in message:
                try:
                    await self._websocket.send_message("40")
                except Exception:
                    pass
                return

            text_view = str(message)

            # Old auth signals
            if "authorization/reject" in text_view:
                await self._trigger_event_async("error", data={"type": "authorization_reject", "raw": text_view})
            elif "s_authorization" in text_view:
                await self._trigger_event_async("authenticated", data={})

            # Two-part header: 451- / 51-
            if isinstance(message, str) and (message.startswith("451-") or message.startswith("51-")):
                try:
                    header_json = message.split("-", 1)[1]
                    header = json.loads(header_json)  # ["topic", {"_placeholder":true,"num":0}]
                    self._pending_binary_event = header[0] if isinstance(header, list) and header else None
                    self._temp_status = message  # mirror old behaviour (store last header)
                except Exception:
                    self._pending_binary_event = None
                return

            # Inline Socket.IO event: 42["topic", {...}]
            if isinstance(message, str) and message.startswith('42['):
                try:
                    event = json.loads(message[2:])
                    topic = event[0]
                    payload = event[1] if len(event) > 1 else {}
                except Exception as e:
                    logger.error(f"on_message: malformed 42 JSON: {e}")
                    return

                # Route by topic (mix of old/new names)
                if topic in ("instruments/list",):
                    await self._trigger_event_async("assets_list", data=payload)
                    self._last_assets_request = None
                elif topic in ("s_authorization",):
                    await self._trigger_event_async("authenticated", data=payload)
                    if self.is_connected and self._websocket and self._websocket.is_connected:
                        try:
                            await self._websocket.send_message('451-["instruments/list",{"_placeholder":true,"num":0}]')
                        except Exception:
                            pass
                elif topic in ("successupdateBalance",):
                    await self._trigger_event_async("balance_updated", data=payload)
                elif topic in ("s_orders/open", "successopenOrder"):
                    await self._trigger_event_async("order_opened", data=payload)
                elif topic in ("s_orders/close", "successcloseOrder"):
                    await self._trigger_event_async("order_closed", data=payload)
                elif topic in ("quotes/stream",):
                    await self._trigger_event_async("quote_stream", data=payload)
                elif topic in ("loadHistoryPeriod", "history/load/line", "chart/candles"):
                    await self._trigger_event_async("candles_received", data=payload)
                elif topic in ("updateHistoryNew",):
                    await self._trigger_event_async("history_update", data=payload)
                elif topic in ("error",):
                    await self._trigger_event_async("error", data=payload)
                else:
                    await self._trigger_event_async("message_received", data=message)

                # Old-style: send tick after processing
                try:
                    if self._websocket and self._websocket.is_connected:
                        await self._websocket.send_message('42["tick"]')
                except Exception:
                    pass
                return

            # Binary JSON payload (starts with \x04), usually follows a 451-/51- header
            if isinstance(message, str) and message.startswith("\x04"):
                try:
                    payload = json.loads(message[1:])
                except Exception as e:
                    logger.error(f"on_message: binary JSON decode error: {e}")
                    await error_monitor.record_error(
                        error_type="binary_json_decode_error",
                        severity=ErrorSeverity.MEDIUM,
                        category=ErrorCategory.DATA,
                        message=f"Binary JSON decode error: {str(e)}",
                        context={}
                    )
                    return

                topic = self._pending_binary_event
                self._pending_binary_event = None

                # Old-style interpretation by keys/shapes
                if isinstance(payload, dict) and (payload.get("liveBalance") or payload.get("demoBalance")):
                    await self._trigger_event_async("balance_data", data=payload)
                elif isinstance(payload, dict) and ("index" in payload):
                    await self._trigger_event_async("candles_received", data=payload)
                elif isinstance(payload, dict) and payload.get("id"):
                    await self._trigger_event_async("order_opened", data=payload)
                elif isinstance(payload, dict) and payload.get("ticket"):
                    await self._trigger_event_async("order_closed", data=payload)

                if isinstance(payload, dict) and payload.get("deals"):
                    await self._trigger_event_async("order_closed", data=payload)

                if isinstance(payload, dict) and (payload.get("isDemo") is not None) and ("balance" in payload):
                    await self._trigger_event_async("balance_updated", data=payload)

                if self._temp_status == '51-["settings/list",{"_placeholder":true,"num":0}]':
                    await self._trigger_event_async("json_data", data={"settings_list": payload})
                    self._temp_status = ""
                elif self._temp_status == '51-["history/list/v2",{"_placeholder":true,"num":0}]':
                    await self._trigger_event_async("candles_received", data=payload)
                    self._temp_status = ""

                if isinstance(payload, list) and payload and isinstance(payload[0], list) and len(payload[0]) >= 3:
                    first = payload[0]
                    if isinstance(first[0], str):
                        await self._trigger_event_async("quote_stream", data=payload)
                    else:
                        await self._trigger_event_async("json_data", data=payload)

                # Old-style: send tick after processing
                try:
                    if self._websocket and self._websocket.is_connected:
                        await self._websocket.send_message('42["tick"]')
                except Exception:
                    pass
                return

            # Fallback: pass as generic message
            await self._trigger_event_async("message_received", data=message)

        except Exception as e:
            logger.error(f"on_message: unexpected error: {e}")
            await error_monitor.record_error(
                error_type="message_processing_error",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.DATA,
                message=f"Unexpected error in on_message: {str(e)}",
                context={}
            )
        finally:
            # Old-style: best-effort tick after any frame
            try:
                if self._websocket and self._websocket.is_connected:
                    await self._websocket.send_message('42["tick"]')
            except Exception:
                pass

    def get_stats(self) -> Dict[str, Any]:
        """Expose basic connection stats to the outer client."""
        stats = dict(self._connection_stats)
        stats.update({
            "connected": self.is_connected,
            "has_websocket": bool(self._websocket),
        })
        return stats
