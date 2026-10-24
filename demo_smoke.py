import asyncio
import json
from pathlib import Path

from api_quotex import AsyncQuotexClient, OrderDirection


SESSION_PATH = Path("sessions/session.json")


def load_demo_session() -> str:
    session_data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
    ssid = session_data.get("ssid")
    if not isinstance(ssid, str) or not ssid.startswith('42["authorization",'):
        raise RuntimeError("No complete authorization frame found in sessions/session.json")

    auth_data = json.loads(ssid[len('42["authorization",') : -1])
    if auth_data.get("isDemo") != 1 or session_data.get("is_demo") is not True:
        raise RuntimeError("Refusing to run: saved session is not confirmed as demo")
    return ssid


async def main() -> None:
    ssid = load_demo_session()
    client = AsyncQuotexClient(ssid=ssid, is_demo=True)
    connected = False

    try:
        connected = await asyncio.wait_for(client.connect(), timeout=60)
        if not connected:
            raise RuntimeError("Could not connect to the demo account")

        balance = await asyncio.wait_for(client.get_balance(), timeout=20)
        print("Account: DEMO")
        print("Account UID: {}".format(client.uid))
        print("Balance: {:.2f} {}".format(balance.balance, balance.currency))
        print("Connection alive: {}".format(client.is_connected))

        assets = await asyncio.wait_for(client.get_available_assets(), timeout=30)
        candidates = [
            (symbol, details)
            for symbol, details in assets.items()
            if details.get("is_open")
            and not details.get("is_otc")
            and (details.get("payout") or 0) > 0
        ]
        if not candidates:
            raise RuntimeError("No open regular demo assets with a positive payout were returned")

        asset, details = sorted(
            candidates,
            key=lambda item: (-(item[1].get("payout") or 0), item[0]),
        )[0]

        await client.disconnect()
        connected = False
        connected = await asyncio.wait_for(client.connect(), timeout=60)
        if not connected or not client.is_connected:
            raise RuntimeError("Could not reconnect to the demo account")
        print("Reconnect: successful")

        duration = 60
        print("Submitting one DEMO order: $1 CALL, {} seconds, {} (payout {}%).".format(duration, asset, details["payout"]))
        order = await client.place_order(
            asset=asset,
            amount=1.0,
            direction=OrderDirection.CALL,
            duration=duration,
        )
        print("Order confirmation: status={}, request_id={}, broker_id={}, asset={}, amount={:.2f}, duration={}s, open_price={:.5f}, expires_at={}".format(
            order.status.value if order.status else "unknown",
            order.order_id,
            order.broker_order_id or "missing",
            order.asset,
            order.amount,
            order.duration,
            order.open_price or 0.0,
            order.expires_at.isoformat() if order.expires_at else "unknown",
        ))

        profit, status = await client.check_win(order.order_id)
        if status is None:
            raise RuntimeError("Order was accepted, but no final result arrived before the timeout")

        result = await client.check_order_result(order.order_id)
        if result is None:
            raise RuntimeError("Order result was reported, but the final order details were not retained")
        print("Order closed: status={}, profit={:.2f} {}, open_price={:.5f}, close_price={:.5f}, closed_at={}".format(
            status,
            profit or 0.0,
            balance.currency,
            result.open_price or 0.0,
            result.close_price or 0.0,
            result.expires_at.isoformat() if result.expires_at else "unknown",
        ))

        final_balance = await asyncio.wait_for(client.get_balance(), timeout=20)
        print("Final balance: {:.2f} {}".format(final_balance.balance, final_balance.currency))
    finally:
        if connected:
            await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())