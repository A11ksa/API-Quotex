<div align="center">
  <h1>API-Quotex – Python Async WebSocket Client</h1>
  <p><b>⚡ Professional, fully asynchronous trading API for the Quotex broker ⚡</b></p>
  <p>
    <img src="https://img.shields.io/pypi/pyversions/pandas?label=python&logo=python" />
    <img src="https://img.shields.io/github/license/A11ksa/API-Quotex?style=flat-square" />
    <img src="https://img.shields.io/badge/async-supported-brightgreen?logo=python" />
    <img src="https://img.shields.io/badge/login-Playwright-blue" />
    <img src="https://img.shields.io/badge/status-stable-success?logo=github"/>
  </p>
</div>

---

## Overview
**API-Quotex** is a production-grade, fully asynchronous WebSocket client for the **Quotex** broker. It powers high-frequency trading bots, research tools, and automation.

**Highlights**
- Live & Demo trading
- Real-time candles, quotes, and assets/payouts
- Full trade lifecycle (place, track, result)
- **Automated login and SSID management via Playwright**
- Comprehensive logging & health monitoring

---

## Installation

```bash
git clone https://github.com/A11ksa/API-Quotex
cd API-Quotex
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scriptsctivate
pip install -U pip
pip install .
python -m playwright install chromium
```

---

## Quick Start

```python
import asyncio
from api_quotex import AsyncQuotexClient, OrderDirection, get_ssid

async def main():
    # Extract (or reuse) SSID via Playwright-based login
    # If a valid sessions/session.json exists, it will be reused by your login helper.
    ssid_info = get_ssid(email="you@example.com", password="YourPassword")
    demo_ssid = ssid_info.get("demo")  # or "live" for real account

    client = AsyncQuotexClient(ssid=demo_ssid, is_demo=True)
    connected = await client.connect()
    if not connected:
        print("Failed to connect")
        return

    balance = await client.get_balance()
    print(f"Balance: {balance.balance} {balance.currency}")

    # Place a 60s CALL order (example)
    order = await client.place_order(
        asset="AUDCAD_otc",
        amount=5.0,
        direction=OrderDirection.CALL,
        duration=60
    )
    profit, status = await client.check_win(order.order_id)
    print("Result:", status, "Profit:", profit)

    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Sessions & SSID
- First run performs login (Playwright) and saves `sessions/session.json`.
- Subsequent runs reuse `session.json` until it expires; then login is refreshed.

---

## Logging & Monitoring
- Daily logs: `log-YYYY-MM-DD.txt`
- Advanced error categorization and health checks are available in `api_quotex/monitoring.py`.

---

## Troubleshooting
- **Browser missing:** `python -m playwright install chromium`
- **Auth error:** delete `sessions/session.json` and re-login
- **Order not placed:** ensure asset is open & balance sufficient
- **WebSocket issues:** verify region/connection in your configuration

---

## Contributing
PRs welcome. Please open issues first for large changes and keep style consistent (PEP 8).

## License
MIT — see `LICENSE`.

## Contact
Author: Ahmed — ar123ksa@gmail.com • Telegram: @A11ksa

## Disclaimer
This library is for educational/research purposes only. Trading involves risk. Use at your own discretion.
