# 🛠️ Setup & Installation Guide (API-Quotex)

This guide walks you through installing **API-Quotex** and enabling **Playwright-based** auto-login (SSID extraction) for Quotex.

---

## 📋 Prerequisites
- **Python 3.8+** (3.9+ recommended)
- `pip` / `venv`
- **Google Chrome or Chromium** (Playwright will install its own Chromium build)
- Network access to `qxbroker.com`

---

## 🚀 Installation

```bash
# 1) Clone the repository
git clone https://github.com/A11ksa/API-Quotex.git
cd API-Quotex

# 2) Create & activate a virtual environment
python -m venv venv
# Linux/macOS:
source venv/bin/activate
# Windows:
venv\Scriptsctivate

# 3) Install the package
pip install -U pip
pip install .

# 4) Install Playwright browser(s)
python -m playwright install chromium
```

---

## ⚙️ Configuration

### Sessions & Credentials
- On first use, the library can **open a Playwright browser** and perform a login to `https://qxbroker.com/en/sign-in`, then extract and save your **SSID**.
- Credentials can be stored in `sessions/config.json` (email/password) and the extracted **SSID** is saved to `sessions/session.json`.

**Manual SSID (optional):**  
If you already have an SSID, place it in `sessions/session.json`:
```json
{
  "live": "YOUR_LIVE_SSID",
  "demo": "YOUR_DEMO_SSID"
}
```

---

## 🔧 Environment Variables (Optional)

| Variable            | Description                          | Default |
|---------------------|--------------------------------------|---------|
| `PING_INTERVAL`     | WebSocket ping interval (seconds)    | `20`    |
| `DEFAULT_TIMEOUT`   | Default API timeout (seconds)        | `30.0`  |
| `LOG_LEVEL`         | Logging level                        | `INFO`  |

> Notes: Amount limits and other trading parameters are controlled from code/config.

---

## 🧪 Quick Test

```bash
python test4.py
```

You should see: connection → balance → assets → (optional) place order → wait for result.

---

## ❓ Troubleshooting

- **Playwright not found / browsers missing:** run `python -m playwright install chromium`.
- **Login flow fails:** verify email/password and re-run; if SSID expired, delete `sessions/session.json` and try again.
- **WebSocket issues:** check network/region in your config and retry.

---

## ✅ That’s it
You’re ready to build strategies and bots over the async Quotex WebSocket client with **Playwright** login support.
