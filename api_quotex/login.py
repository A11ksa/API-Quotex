"""Login utilities for Quotex API using Playwright + Cloudscraper, with region
validation driven by constants and session-cookie–first SSID building."""
import os
import json
import time
import re
import requests
import cloudscraper
from loguru import logger
from pathlib import Path
from typing import Dict, Tuple, Any, Optional
from bs4 import BeautifulSoup

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

from .config import Config
from .monitoring import error_monitor, ErrorSeverity, ErrorCategory
from .constants import REGIONS

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

SESSION_DIR = Path("sessions")
SESSION_FILE = SESSION_DIR / "session.json"
CREDENTIALS_FILE = SESSION_DIR / "config.json"
QX_BASE = "https://qxbroker.com"

# Persistence helpers (via Config singleton)
def load_config() -> Dict[str, Any]:
    cfg = Config()
    return cfg.load_config()

def save_config(config_data: Dict[str, Any]) -> None:
    cfg = Config()
    cfg.save_config(config_data)

def load_session() -> Dict[str, Any]:
    cfg = Config()
    return cfg.session_data.copy()

def save_session(session_data: Dict[str, Any]) -> None:
    cfg = Config()
    cfg.save_session(session_data)

# URL helpers
def _login_urls(lang: str, is_demo: bool) -> Tuple[str, str]:
    login_url = f"{QX_BASE}/{lang}/sign-in/"
    target_url = f"{QX_BASE}/{lang}/demo-trade" if is_demo else f"{QX_BASE}/{lang}/trade"
    return login_url, target_url

# SSID utils
def _cookies_string_to_dict(cookie_header: Optional[str]) -> Dict[str, str]:
    if not cookie_header:
        return {}
    parts = [p.strip() for p in cookie_header.split(";") if p.strip()]
    out: Dict[str, str] = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            out[k.strip()] = v.strip()
    return out

def _extract_session_cookie_value(cookies: Dict[str, str]) -> Optional[str]:
    for name in ("session", "ssid", "qx_session"):
        v = cookies.get(name) or cookies.get(name.upper()) or cookies.get(name.lower())
        if v:
            return v
    return None

def _infer_is_demo_from_ssid(complete_ssid: str, default_demo: bool = True) -> bool:
    try:
        if complete_ssid.startswith('42["authorization",'):
            js_start = complete_ssid.find("{")
            js_end = complete_ssid.rfind("}") + 1
            if js_start != -1 and js_end > js_start:
                data = json.loads(complete_ssid[js_start:js_end])
                val = data.get("isDemo", None)
                if val is None:
                    return default_demo
                try:
                    return bool(int(val))
                except Exception:
                    return bool(val)
    except Exception:
        pass
    return default_demo

async def validate_ssid(ssid: str) -> bool:
    """
    Validate an SSID frame by attempting a lightweight WebSocket connect.
    Uses multiple regions to ensure reliability.
    """
    from .websocket_client import AsyncWebSocketClient
    is_demo = _infer_is_demo_from_ssid(ssid, default_demo=True)
    all_regions = REGIONS.get_all_regions()
    urls = []
    try:
        if is_demo:
            demo_urls = REGIONS.get_demo_regions()
            urls = demo_urls if demo_urls else list(all_regions.values())
        else:
            urls = [url for name, url in all_regions.items() if "DEMO" not in name.upper()] or list(all_regions.values())
    except Exception:
        urls = ["wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket"]
    client = AsyncWebSocketClient()
    for url in urls:
        try:
            import socket
            host = url.split("//")[1].split("/")[0]
            socket.getaddrinfo(host, 443)
            success = await client.connect([url], ssid)
            if success:
                await client.disconnect()
                logger.info(f"SSID validated successfully using {url}")
                return True
        except socket.gaierror as e:
            logger.warning(f"DNS resolution failed for {url}: {str(e)}")
            await error_monitor.record_error(
                error_type="dns_resolution_failed",
                severity=ErrorSeverity.HIGH,
                category=ErrorCategory.CONNECTION,
                message=f"DNS resolution failed for {url}: {str(e)}",
                context={"url": url}
            )
        except Exception as e:
            logger.warning(f"SSID validation failed for {url}: {str(e)}")
            await error_monitor.record_error(
                error_type="ssid_validation_failed",
                severity=ErrorSeverity.MEDIUM,
                category=ErrorCategory.AUTHENTICATION,
                message=f"SSID validation failed for {url}: {str(e)}",
                context={"url": url}
            )
    logger.error("SSID validation failed for all regions")
    return False

# Playwright login
async def _playwright_login_and_capture(email: str, password: str, lang: str, is_demo: bool, keep_browser_on_error: bool = False) -> Tuple[bool, Dict]:
    login_url, target_url = _login_urls(lang, is_demo)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-default-browser-check",
                "--no-first-run",
                "--start-maximized",
            ],
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 768})
        page = await context.new_page()
        try:
            logger.info("Playwright: opening login page...")
            await page.goto(login_url, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_selector('#tab-1 form[action$="/sign-in/"]', state="visible", timeout=30_000)
            email_input = page.locator('#tab-1 input[name="email"]:visible').first
            pwd_input = page.locator('#tab-1 input[name="password"]:visible').first
            submit_btn = page.locator('#tab-1 form[action$="/sign-in/"] button[type="submit"]:visible').first
            await email_input.fill(email)
            await pwd_input.fill(password)
            if "/trade" not in (page.url or "") and "/cabinet" not in (page.url or ""):
                try:
                    nav_task = page.wait_for_url("**/(trade|demo-trade|cabinet)**", timeout=60_000)
                    await submit_btn.click()
                    try:
                        await nav_task
                    except PlaywrightTimeoutError:
                        await page.wait_for_load_state("networkidle", timeout=20_000)
                except PlaywrightTimeoutError:
                    pass
            await page.goto(target_url, wait_until="domcontentloaded", timeout=45_000)
            await page.wait_for_load_state("networkidle", timeout=20_000)
            try:
                token = await page.evaluate("() => window?.settings?.token ?? null")
            except Exception:
                token = None
            try:
                cookies = await context.cookies()
                for c in cookies:
                    name = (c.get("name") or "").lower()
                    if name in ("session", "ssid", "qx_session"):
                        qx_session_val = c.get("value")
                        break
                else:
                    qx_session_val = None
            except Exception:
                cookies = []
                qx_session_val = None
            cookies_string = "; ".join(
                f"{c.get('name')}={c.get('value')}"
                for c in (cookies or [])
                if c.get("name") and c.get("value")
            )
            try:
                user_agent = await page.evaluate("() => navigator.userAgent")
            except Exception:
                user_agent = None
            session_data: Dict[str, Any] = {
                "token": token,
                "cookies": cookies_string,
                "user_agent": user_agent,
                "is_demo": is_demo,
            }
            ssid_source = qx_session_val or token
            if ssid_source:
                session_data["ssid"] = (
                    f'42["authorization",{{"session":"{ssid_source}","isDemo":{1 if is_demo else 0},"tournamentId":0}}]'
                )
                logger.info(f"{'Demo' if is_demo else 'Live'} SSID captured via Playwright ({'cookie' if qx_session_val else 'token'})")
            else:
                logger.warning("Playwright: logged in but no session cookie or token found.")
            save_session(session_data)
            logger.info("Playwright: session data saved successfully")
            return True, session_data
        except Exception as e:
            logger.error(f"Playwright login failed: {e}")
            await error_monitor.record_error(
                error_type="playwright_login_failed",
                severity=ErrorSeverity.CRITICAL,
                category=ErrorCategory.AUTHENTICATION,
                message=f"Playwright login failed: {e}",
                context={"email": email},
            )
            if keep_browser_on_error:
                logger.warning("Keeping browser open for inspection (keep_browser_on_error=True).")
                try:
                    while True:
                        await page.wait_for_timeout(1_000)
                except KeyboardInterrupt:
                    pass
            return False, {}
        finally:
            try:
                await context.close()
                await browser.close()
            except Exception:
                pass

# Cloudscraper helpers
def _extract_csrf_from_signin(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    login_form = soup.select_one('#tab-1 form[action$="/sign-in/"]')
    if login_form:
        hidden = login_form.select_one('input[name="_token"]')
        if hidden and hidden.get("value"):
            return hidden["value"]
    m = re.search(r"window\.settings\s*=\s*(\{.*?\})", html, re.S)
    if m:
        try:
            w = json.loads(m.group(1))
            return w.get("csrf")
        except Exception:
            return None
    return None

def _extract_token_from_trade(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script")
    for s in scripts:
        txt = (s.get_text() or "").strip()
        if "window.settings" in txt:
            try:
                j = re.sub(r"^window\.settings\s*=\s*", "", txt.replace(";", ""))
                token = json.loads(j).get("token")
                if token:
                    return token
            except Exception:
                continue
    return None

# Main entry
async def get_ssid(email: str = None, password: str = None, email_pass: str = None, lang: str = "en", is_demo: bool = True, keep_browser_on_error: bool = False) -> Tuple[bool, Dict]:
    """
    Strategy:
      1) Check if session.json exists and is valid (SSID works).
      2) If session.json is missing or SSID is invalid, delete it and perform login.
      3) Use Cloudscraper first, fall back to Playwright if it fails.
      4) Save new session.json after successful login.
    """
    # Step 1: Check existing session
    session_data = load_session()
    if session_data and SESSION_FILE.exists():
        logger.info("Checking existing saved session...")
        cookie_map = _cookies_string_to_dict(session_data.get("cookies"))
        cookie_session = _extract_session_cookie_value(cookie_map)
        ssid_candidate = session_data.get("ssid")
        if not ssid_candidate:
            source = cookie_session or session_data.get("token")
            if source:
                ssid_candidate = f'42["authorization",{{"session":"{source}","isDemo":{1 if is_demo else 0},"tournamentId":0}}]'
                session_data["ssid"] = ssid_candidate
        if ssid_candidate and await validate_ssid(ssid_candidate):
            logger.info("Existing session is valid.")
            return True, session_data
        else:
            logger.warning("Existing session is invalid or expired; removing session.json")
            try:
                if SESSION_FILE.exists():
                    os.remove(SESSION_FILE)
            except Exception as e:
                logger.error(f"Failed to remove session.json: {str(e)}")
            session_data = {}

    # Step 2: Load credentials
    creds = load_config()
    if not email and creds.get("email"):
        email = creds["email"]
    if not password and creds.get("password"):
        password = creds["password"]
    if not email or not password:
        raise RuntimeError("Email/password not found in config.json. Please set them before running.")
    creds.update({"email": email, "password": password, "email_pass": email_pass})
    save_config(creds)

    # Step 3: Cloudscraper fast path
    try:
        scraper = cloudscraper.create_scraper()
        login_url, target_url = _login_urls(lang, is_demo)
        resp = scraper.get(login_url, timeout=30, headers={"Referer": login_url})
        if resp.status_code == 200:
            csrf = _extract_csrf_from_signin(resp.text)
            if csrf:
                logger.info("Submitting login form via Cloudscraper with CSRF")
                post_url = f"{QX_BASE}/{lang}/sign-in/"
                payload = {"_token": csrf, "email": email, "password": password, "remember": "1"}
                resp2 = scraper.post(
                    post_url,
                    data=payload,
                    headers={"Referer": login_url, "Content-Type": "application/x-www-form-urlencoded"},
                    timeout=30,
                    allow_redirects=False,
                )
                if resp2.status_code in (301, 302, 303, 307, 308):
                    loc = resp2.headers.get("Location")
                    if loc:
                        next_url = loc if loc.startswith("http") else (QX_BASE + loc)
                        try:
                            scraper.get(next_url, timeout=30)
                        except Exception:
                            pass
                if resp2.status_code in (200, 301, 302, 303, 307, 308):
                    resp3 = scraper.get(target_url, timeout=30, headers={"Referer": login_url})
                    if resp3.status_code == 200:
                        token = _extract_token_from_trade(resp3.text)
                        cookies_dict = scraper.cookies.get_dict()
                        session_cookie_val = None
                        for k, v in cookies_dict.items():
                            if k.lower() in ("session", "ssid", "qx_session") and v:
                                session_cookie_val = v
                                break
                        ssid_source = session_cookie_val or token
                        if ssid_source:
                            cookies_string = "; ".join(f"{k}={v}" for k, v in cookies_dict.items())
                            user_agent = scraper.headers.get("User-Agent", None)
                            session_data = {
                                "token": token,
                                "cookies": cookies_string,
                                "user_agent": user_agent,
                                "is_demo": is_demo,
                                "ssid": f'42["authorization",{{"session":"{ssid_source}","isDemo":{1 if is_demo else 0},"tournamentId":0}}]',
                            }
                            logger.info(
                                f"{'Demo' if is_demo else 'Live'} SSID captured via Cloudscraper "
                                f"({'cookie' if session_cookie_val else 'token'})"
                            )
                            save_session(session_data)
                            logger.info("Session data saved successfully")
                            return True, session_data
                        else:
                            logger.warning("Cloudscraper: neither session cookie nor token found; switching to Playwright")
                    else:
                        logger.warning(f"Cloudscraper: GET target page failed ({resp3.status_code}); switching to Playwright")
                else:
                    logger.warning(f"Cloudscraper login failed with status {resp2.status_code}; switching to Playwright")
            else:
                logger.warning("CSRF token not found on /sign-in; switching to Playwright")
        else:
            logger.warning(f"Cloudscraper GET /sign-in failed with status {resp.status_code}; switching to Playwright")
    except Exception as e:
        logger.warning(f"Cloudscraper path failed: {e}")

    # Step 4: Playwright fallback
    ok, session_data = await _playwright_login_and_capture(
        email, password, lang, is_demo, keep_browser_on_error=keep_browser_on_error
    )
    if ok and session_data.get("ssid"):
        try:
            if await validate_ssid(session_data["ssid"]):
                logger.info("New SSID validated successfully")
                return True, session_data
        except Exception as e:
            logger.error(f"Failed to validate new SSID: {str(e)}")
        return True, session_data
    await error_monitor.record_error(
        error_type="ssid_retrieval_failed_all",
        severity=ErrorSeverity.CRITICAL,
        category=ErrorCategory.AUTHENTICATION,
        message="Unable to retrieve a valid SSID via Cloudscraper or Playwright.",
        context={"email": email},
    )
    return False, {}
