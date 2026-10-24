import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock

from datetime import datetime, timedelta

from api_quotex.client import AsyncQuotexClient
from api_quotex.exceptions import InvalidParameterError, OrderError
from api_quotex.models import Order, OrderDirection, OrderResult, OrderStatus


class OrderProtocolTests(unittest.IsolatedAsyncioTestCase):
    def test_rejects_30_second_expiration_before_sending(self):
        client = AsyncQuotexClient(ssid="synthetic", is_demo=True, enable_logging=False)

        with self.assertRaisesRegex(InvalidParameterError, "between 60 and"):
            client._validate_order_parameters("AUDCAD", 1.0, OrderDirection.CALL, 30)

    def test_check_win_timeout_uses_order_duration_plus_grace(self):
        client = AsyncQuotexClient(ssid="synthetic", is_demo=True, enable_logging=False)
        client._active_orders["1792762365"] = OrderResult(
            order_id="1792762365",
            broker_order_id="a56a1fbb-0331-4060-aaa7-16dc3ac84619",
            asset="AUDCAD",
            amount=1,
            direction=OrderDirection.CALL,
            duration=300,
            status=OrderStatus.OPEN,
            placed_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=300),
        )

        self.assertGreaterEqual(client._get_order_wait_timeout("1792762365"), 330.0)
        self.assertGreaterEqual(client._get_order_wait_timeout("missing-order"), 180.0)

    async def test_immediate_order_frame_matches_demo_protocol(self):
        for asset in ("AUDCAD", "AUDCAD_otc"):
            with self.subTest(asset=asset):
                client = AsyncQuotexClient(ssid="synthetic", is_demo=True, enable_logging=False)
                client.send_message = AsyncMock()
                client.send_message_immediate = AsyncMock()
                order = Order(
                    asset=asset,
                    amount=1,
                    direction=OrderDirection.CALL,
                    duration=60,
                    request_id="1792672089",
                )

                client._prepare_asset_for_order = AsyncMock()
                await client._send_order(order)

                client._prepare_asset_for_order.assert_awaited_once_with(asset)
                frame = client.send_message_immediate.await_args.args[0]
                event, payload = json.loads(frame[2:])
                self.assertEqual(event, "orders/open")
                self.assertEqual(
                    payload,
                    {
                        "asset": asset,
                        "amount": 1.0,
                        "time": 60,
                        "action": "call",
                        "isDemo": 1,
                        "tournamentId": 0,
                        "requestId": 1792672089,
                        "optionType": 100,
                    },
                )

    async def test_immediate_send_flushes_queued_frames_before_order(self):
        client = AsyncQuotexClient(ssid="synthetic", is_demo=True, enable_logging=False)
        websocket = SimpleNamespace(closed=False, send=AsyncMock())
        client._websocket.websocket = websocket
        client._websocket._message_batcher.pending_messages.extend(
            ['42["tick"]', '42["instruments/follow","AUDCAD"]']
        )
        order_frame = '42["orders/open",{"asset":"AUDCAD"}]'

        await client._websocket.send_message_immediate(order_frame)

        self.assertEqual(
            [call.args[0] for call in websocket.send.await_args_list],
            [
                '42["tick"]',
                '42["instruments/follow","AUDCAD"]',
                order_frame,
            ],
        )
        self.assertFalse(client._websocket._message_batcher.pending_messages)

    async def test_prepare_asset_sends_browser_observed_subscriptions_and_waits_for_quote(self):
        client = AsyncQuotexClient(ssid="synthetic", is_demo=True, enable_logging=False)
        sent_frames = []

        async def record_send(frame):
            sent_frames.append(frame)
            if frame.startswith('42["depth/follow"'):
                await client._on_quote_stream([["AUDCAD", 1_792_760_528, 0.9823]])
            return True

        client.send_message = AsyncMock(side_effect=record_send)

        await client._prepare_asset_for_order("AUDCAD")

        self.assertEqual(
            sent_frames,
            [
                '42["instruments/update",{"asset":"AUDCAD","period":60}]',
                '42["chart_notification/get",{"asset":"AUDCAD","version":"1.0.0"}]',
                '42["depth/follow","AUDCAD"]',
                '42["tick"]',
            ],
        )
        self.assertGreater(client._payout_data["AUDCAD"], 0)
        self.assertNotIn("AUDCAD", client._quote_update_events)

    async def test_server_order_rejection_fails_wait_immediately(self):
        request_id = "1792760630"
        order = Order(
            asset="AUDCAD",
            amount=1,
            direction=OrderDirection.CALL,
            duration=30,
            request_id=request_id,
        )
        client = AsyncQuotexClient(ssid="synthetic", is_demo=True, enable_logging=False)
        client._pending_order_requests[request_id] = order

        await client._on_json_data(
            ["f_orders/open", {"error": "expiration", "amount": 1, "requestId": int(request_id)}]
        )

        with self.assertRaisesRegex(OrderError, "rejected by Quotex: expiration"):
            await client._wait_for_order_result(request_id, order, timeout=1)
        self.assertNotIn(request_id, client._pending_order_requests)

    async def test_binary_open_and_close_frames_correlate_to_request(self):
        request_id = "1792672089"
        client = AsyncQuotexClient(ssid="synthetic", is_demo=True, enable_logging=False)
        client._pending_order_requests[request_id] = Order(
            asset="AUDCAD",
            amount=1,
            direction=OrderDirection.CALL,
            duration=60,
            request_id=request_id,
        )

        opened = {
            "id": "ffa14f24-e981-462b-b5e1-560d78001f90",
            "openTime": "2026-10-22 12:27:26",
            "closeTime": "2026-10-22 12:28:26",
            "openTimestamp": 1792672046,
            "closeTimestamp": 1792672106,
            "uid": 94510941,
            "isDemo": 1,
            "tournamentId": 0,
            "amount": 1,
            "profit": 0.77,
            "percentProfit": 77,
            "openPrice": 0.98388,
            "closePrice": 0,
            "command": 0,
            "asset": "AUDCAD",
            "requestId": int(request_id),
        }
        client._websocket._pending_binary_event = "s_orders/open"
        await client._websocket._handle_candle_message("\x04" + json.dumps(opened))

        self.assertIn(request_id, client._active_orders)
        self.assertEqual(
            client._active_orders[request_id].broker_order_id,
            "ffa14f24-e981-462b-b5e1-560d78001f90",
        )

        closed = {
            "profit": 1.77,
            "deals": [
                {
                    "id": "ffa14f24-e981-462b-b5e1-560d78001f90",
                    "openTime": "2026-10-22 12:27:26",
                    "closeTime": "2026-10-22 12:28:26",
                    "openTimestamp": 1792672046,
                    "closeTimestamp": 1792672106,
                    "uid": 94510941,
                    "amount": 1,
                    "profit": 0.77,
                    "percentProfit": 77,
                    "openPrice": 0.98388,
                    "closePrice": 0.98394,
                    "command": 0,
                    "asset": "AUDCAD",
                    "isDemo": 1,
                    "tournamentId": 0,
                    "currency": "USD",
                }
            ],
        }
        client._websocket._pending_binary_event = "s_orders/close"
        await client._websocket._handle_candle_message("\x04" + json.dumps(closed))

        result = client._order_results[request_id]
        self.assertEqual(result.status, OrderStatus.WIN)
        self.assertEqual(result.profit, 0.77)
        self.assertEqual(result.close_price, 0.98394)
        self.assertNotIn(request_id, client._active_orders)

    async def test_successopen_and_successclose_binary_frames_are_accepted(self):
        request_id = "987654321"
        client = AsyncQuotexClient(ssid="synthetic", is_demo=True, enable_logging=False)
        client._pending_order_requests[request_id] = Order(
            asset="AUDCAD",
            amount=1,
            direction=OrderDirection.CALL,
            duration=60,
            request_id=request_id,
        )

        opened = {
            "id": "success-open-id",
            "asset": "AUDCAD",
            "amount": 1,
            "openPrice": 0.98415,
            "requestId": int(request_id),
            "command": 0,
            "openTime": "2026-10-22 12:00:00",
        }
        client._websocket._pending_binary_event = "successopenOrder"
        await client._websocket._handle_candle_message("\x04" + json.dumps(opened))
        self.assertIn(request_id, client._active_orders)

        client._websocket._pending_binary_event = "successcloseOrder"
        await client._websocket._handle_candle_message(
            "\x04" + json.dumps({
                "deals": [{
                    "id": "success-open-id",
                    "asset": "AUDCAD",
                    "amount": 1,
                    "profit": 1.0,
                    "openPrice": 0.98415,
                    "closePrice": 0.98422,
                    "command": 0,
                    "openTime": "2026-10-22 12:00:00",
                    "closeTime": "2026-10-22 12:01:00",
                    "requestId": int(request_id),
                }]
            })
        )

        self.assertEqual(client._order_results[request_id].status, OrderStatus.WIN)
        self.assertEqual(client._order_results[request_id].profit, 1.0)


if __name__ == "__main__":
    unittest.main()