<div align="center">

<h1>🚀 API-Quotex – Async WebSocket Client for Quotex</h1>

<p><b>High-performance, production-ready Python client with <u>Playwright</u> login (SSID) & full trade lifecycle.</b></p>

<p>
  <a href="https://www.python.org/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/pandas?label=python&logo=python" /></a>
  <a href="https://docs.python.org/3/library/asyncio.html"><img alt="AsyncIO" src="https://img.shields.io/badge/Framework-AsyncIO-informational" /></a>
  <a href="https://playwright.dev/"><img alt="Playwright" src="https://img.shields.io/badge/Login-Playwright-blue" /></a>
  <a href="https://github.com/A11ksa/API-Quotex/actions"><img alt="Status" src="https://img.shields.io/badge/Status-Stable-success" /></a>
  <a href="https://github.com/A11ksa/API-Quotex/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/A11ksa/API-Quotex?style=flat-square" /></a>
</p>

</div>

---

## ✨ Features
- ⚡ **Async**: non-blocking WebSocket client optimized for realtime data
- 🔐 **Playwright Login**: automated SSID extraction & reuse (demo/live)
- 📈 **Market Data**: assets, payouts, quotes, and real-time candles
- 🧾 **Orders**: open, track, and resolve full trade lifecycle (WIN/LOSS/DRAW)
- 🩺 **Monitoring**: structured logging & health checks
- 🧪 **Examples**: quick-start scripts for connection, candles, and orders

---

## 🧭 Table of Contents
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Why Playwright?](#why-playwright)
- [Architecture](#architecture)
- [Examples](#examples)
- [Sessions & SSID](#sessions--ssid)
- [Troubleshooting](#troubleshooting)
- [Contact](#-contact)
- [Contributing](#contributing)
- [License](#license)

---

## Installation
```bash
git clone https://github.com/A11ksa/API-Quotex
cd API-Quotex
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate
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
    # 1) Get / refresh SSID via Playwright helper (opens browser on first run)
    ssid_info = get_ssid(email="you@example.com", password="YourPassword")
    demo_ssid = ssid_info.get("demo")  # or "live"

    # 2) Connect
    client = AsyncQuotexClient(ssid=demo_ssid, is_demo=True)
    if not await client.connect():
        print("Failed to connect")
        return

    # 3) Balance
    bal = await client.get_balance()
    print(f"Balance: {bal.balance} {bal.currency}")

    # 4) Place order (60s CALL example)
    order = await client.place_order(
        asset="AUDCAD_otc",
        amount=5.0,
        direction=OrderDirection.CALL,
        duration=60
    )

    # 5) Await result
    profit, status = await client.check_win(order.order_id)
    print("Result:", status, "Profit:", profit)

    # 6) Disconnect
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Why Playwright?
- ✅ Maintains parity with browser behavior (anti-bot friendly)
- ✅ Simplifies cookie/session extraction (SSID)
- ✅ Robust to UX changes vs brittle HTTP scraping
- ✅ Easy to refresh sessions and switch demo/live

---

## Architecture
```
+---------------------+
|  Playwright Helper  |  (Login UI)
|  - opens browser    |--> SSID saved to sessions/session.json
+----------+----------+
           |
           v
+---------------------+      WebSocket (AsyncIO)
|  AsyncQuotexClient  |<-------------------------------> Quotex WS
|  - connect          |       - quotes, candles, orders
|  - assets/payouts   |
|  - place/check      |
+---------------------+
```

---

## Examples

### Stream latest candles for an asset
```python
# Pseudocode outline; see your client for exact APIs
await client.subscribe_candles(asset="EURUSD_otc", timeframe=60)
async for candle in client.iter_candles("EURUSD_otc", 60):
    print(candle.time, candle.open, candle.close)
```

### Place PUT order and check result
```python
order = await client.place_order(
    asset="EURUSD_otc",
    amount=10.0,
    direction=OrderDirection.PUT,
    duration=60
)
profit, status = await client.check_win(order.order_id)
print(status, profit)
```

---

## Sessions & SSID
- First run opens Chromium and stores **SSID** in `sessions/session.json`
- Subsequent runs reuse it until expiry (then it auto-refreshes via login)

**Manual override**

```json
{
  "live": "A8i6rBIfrfrfUYD9BkfGKv00000akJkSeouX73q",
  "demo": "A8i6rBIfrfrfUYD9BkfGKv00000akJkSeouX73q"
}
```

---

## Troubleshooting
- **No browser installed?** `python -m playwright install chromium`
- **Auth error?** Delete `sessions/session.json` and retry login
- **No data / timeouts?** Check region, network, and broker status
- **SSL errors?** Ensure your Python/OpenSSL environment is clean

> Tip: Logs are written as `log-YYYY-MM-DD.txt`. Attach them when opening GitHub issues.

---

## 📬 Contact
<p align="left">
  <a href="mailto:ar123ksa@gmail.com">
    <img alt="Email" src="https://img.shields.io/badge/Email-ar123ksa%40gmail.com-EA4335?logo=gmail" />
  </a>
  <a href="https://t.me/A11ksa">
    <img alt="Telegram" src="https://img.shields.io/badge/Telegram-@A11ksa-26A5E4?logo=telegram" />
  </a>
</p>

* **Author:** Ahmed (<a href="mailto:ar123ksa@gmail.com">ar123ksa@gmail.com</a>)
* **Telegram:** <a href="https://t.me/A11ksa">@A11ksa</a>

---

## Contributing
PRs are welcome. Please:
1. Open an issue describing the change
2. Keep style consistent (PEP 8 + type hints)
3. Add tests where meaningful

---

## License
MIT — see `LICENSE`.

---

## Acknowledgments
Thanks to the community for continued feedback and to the maintainers for the Playwright + AsyncIO integration.
