# ✨ API-Quotex – Setup & Installation (Playwright Login Ready)

> **Purpose:** A polished, one-stop setup guide for installing **API-Quotex**, enabling **Playwright**-based login (SSID extraction), and running your first test.

<p align="center">
  <a href="https://github.com/A11ksa/API-Quotex"><img alt="AsyncIO" src="https://img.shields.io/badge/Framework-AsyncIO-informational" /></a>
  <a href="https://github.com/A11ksa/API-Quotex"><img alt="Playwright" src="https://img.shields.io/badge/Login-Playwright-blue" /></a>
  <a href="https://github.com/A11ksa/API-Quotex"><img alt="Status" src="https://img.shields.io/badge/Status-Stable-success" /></a>
  <a href="https://github.com/A11ksa/API-Quotex/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/github/license/A11ksa/API-Quotex" /></a>
</p>

---

## 🔗 Quick Links
- **Repo:** https://github.com/A11ksa/API-Quotex
- **README:** See top-level `README.md` for API overview and examples
- **Issues:** https://github.com/A11ksa/API-Quotex/issues

---

## ✅ Prerequisites
- **Python 3.8+** (3.9+ recommended)
- `pip` and optionally `venv`
- Playwright browsers (we’ll install Chromium)
- Network access to `quotex.com`

---

## ⚡ Install (recommended flow)
```bash
# 1) Clone
git clone https://github.com/A11ksa/API-Quotex.git
cd API-Quotex

# 2) Virtualenv
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scripts\activate

# 3) Install package
pip install -U pip
pip install .

# 4) Install Playwright browser(s)
python -m playwright install chromium
```

## Using uv
```bash
uv sync
uv run python -m playwright install chromium
uv run python examples/trading_methods.py
```

The trading example is read-only by default. To explicitly submit its single demo order:
```bash
uv run python examples/trading_methods.py --place-demo-order
```

---

## 🔐 Configure Sessions (Playwright)
Run the standalone helper and sign in manually in the opened browser:
```bash
python login.py --mode demo
```

Choose `--mode live` to open the live account instead. Demo is the default. After sign-in, the helper navigates to `/en/demo-trade` or `/en/trade` for the selected mode and only saves a session when its route and authorization frame agree. The SSID and its mode are saved to `sessions/session.json`; the SSID is also written to `QUOTEX_SSID` in `.env` for reuse. The `.env` file is ignored by Git and restricted to owner-only permissions when the SSID is saved.

---

## 🧪 Smoke Test
```bash
python demo_smoke.py
```
This confirms the demo connection, prints the account balance, and submits one `$1` CALL order with a 60-second duration before checking its result. The order can lose up to `$1`. The script refuses to run unless the saved session explicitly confirms demo mode. `test1.py` is a separate network script that submits multiple demo orders.

---

## 🧰 Troubleshooting
- **Playwright browser missing:** `python -m playwright install chromium`
- **Login fails / SSID expired:** remove `QUOTEX_SSID` from `.env` and `sessions/session.json`, then sign in again
- **WebSocket region issues:** adjust region settings in your config
- **SSL / cert warnings:** re-check your Python and OpenSSL runtime

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

## 🏁 You’re Done
You now have a fully async Quotex client with **Playwright**-assisted login. Build strategies freely.
