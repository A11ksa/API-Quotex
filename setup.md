# ✨ API-Quotex – Setup & Installation (Playwright Login Ready)

> **Purpose:** A polished, one-stop setup guide for installing **API-Quotex**, enabling **Playwright**-based login (SSID extraction), and running your first test.

<p align="center">
  <img alt="AsyncIO" src="https://img.shields.io/badge/Framework-AsyncIO-informational" />
  <img alt="Playwright" src="https://img.shields.io/badge/Login-Playwright-blue" />
  <img alt="Status" src="https://img.shields.io/badge/Status-Stable-success" />
  <img alt="License" src="https://img.shields.io/github/license/A11ksa/API-Quotex" />
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
- Network access to `qxbroker.com`

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

---

## 🔐 Configure Sessions (Playwright)
- On first use, the library can open a **Playwright** Chromium window to log in at `https://qxbroker.com/en/sign-in`, then extract and save your **SSID** to `sessions/session.json`.
- Optional **credentials** location: `sessions/config.json`

**Manual SSID (if you already have it):**
```json
{
  "live": "YOUR_LIVE_SSID",
  "demo": "YOUR_DEMO_SSID"
}
```

**Folder structure (suggested):**
```
API-Quotex/
  sessions/
    config.json       # {"email":"...", "password":"..."}
    session.json      # {"live":"...", "demo":"..."}
```

---

## 🧪 Smoke Test
```bash
python test4.py
```
What you should see: **connect → account → assets → (optional) order → result**.

---

## 🧰 Troubleshooting
- **Playwright browser missing:** `python -m playwright install chromium`
- **Login fails / SSID expired:** delete `sessions/session.json` and sign in again
- **WebSocket region issues:** adjust region settings in your config
- **SSL / cert warnings:** re-check your Python and OpenSSL runtime

---

## 🏁 You’re Done
You now have a fully async Quotex client with **Playwright**-assisted login. Build strategies freely.
