"""Demonstrate Quotex account, asset, payout, and order methods.

Read-only by default:
    uv run python examples/trading_methods.py

Place one demo order explicitly:
    uv run python examples/trading_methods.py --place-demo-order
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from api_quotex import AsyncQuotexClient, OrderDirection


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SESSION_PATH = PROJECT_ROOT / "sessions" / "session.json"


def load_demo_session() -> str:
    session_data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    ssid = session_data.get("ssid")
    prefix = '42["authorization",'
    if not isinstance(ssid, str) or not ssid.startswith(prefix):
        raise RuntimeError("No complete authorization frame found in sessions/session.json")

    auth_data = json.loads(ssid[len(prefix) : -1])
    if auth_data.get("isDemo") != 1 or session_data.get("is_demo") is not True:
        raise RuntimeError("Refusing to run: saved session is not confirmed as demo")
    return ssid


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--place-demo-order",
        action="store_true",
        help="place one demo order after showing the account and asset data",
    )
    parser.add_argument("--asset", default="AUDCAD", help="open asset symbol (default: AUDCAD)")
    parser.add_argument("--amount", type=float, default=1.0, help="demo investment amount (default: 1.0)")
    parser.add_argument(
        "--direction",
        choices=("call", "put"),
        default="call",
        help="order direction when --place-demo-order is set",
    )
    parser.add_argument("--duration", type=int, default=60, help="order duration in seconds (default: 60)")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    os.chdir(PROJECT_ROOT)

    ssid = load_demo_session()
    client = AsyncQuotexClient(ssid=ssid, is_demo=True)
    connected = False

    try:
        connected = await asyncio.wait_for(client.connect(), timeout=60)
        if not connected:
            raise RuntimeError("Could not connect to the demo account")

        balance = await asyncio.wait_for(client.get_balance(), timeout=20)
        print("Account: DEMO")
        print("Balance: {:.2f} {}".format(balance.balance, balance.currency))

        assets = await asyncio.wait_for(client.get_available_assets(), timeout=30)
        open_assets = {
            symbol: details
            for symbol, details in assets.items()
            if details.get("is_open") and (details.get("payout") or 0) > 0
        }
        if not open_assets:
            raise RuntimeError("No open demo assets with a positive payout were returned")

        print("Open assets with positive payout: {}".format(len(open_assets)))
        for symbol, details in sorted(open_assets.items())[:10]:
            print("  {}: {}%".format(symbol, details["payout"]))

        if not args.place_demo_order:
            print("Read-only run. Add --place-demo-order to submit one demo order.")
            return

        asset_info = open_assets.get(args.asset)
        if not asset_info:
            raise RuntimeError("{} is not currently open with a positive payout".format(args.asset))

        payout = await client.get_payout(args.asset, "1m")
        if payout <= 0:
            raise RuntimeError("No positive 1-minute payout for {}".format(args.asset))

        direction = OrderDirection.CALL if args.direction == "call" else OrderDirection.PUT
        print(
            "Submitting one DEMO order: {} {} {} seconds, payout {}%.".format(
                args.amount, args.asset, args.duration, payout
            )
        )
        order = await client.place_order(
            asset=args.asset,
            amount=args.amount,
            direction=direction,
            duration=args.duration,
        )
        print("Order accepted: {} ({})".format(order.order_id, order.status))

        current = await client.check_order_result(order.order_id)
        if current:
            print("Current order status: {}".format(current.status))

        active_orders = await client.get_active_orders()
        print("Active orders: {}".format(len(active_orders)))

        profit, status = await client.check_win(order.order_id)
        if status is None:
            print("No final result received before the result timeout.")
        else:
            print("Final result: {} (net profit {:.2f} {})".format(status, profit or 0.0, balance.currency))
    finally:
        if connected:
            await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())