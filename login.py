import asyncio
import argparse
import json
import os
import re
import time
import base64
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from urllib.parse import urlsplit

from dotenv import load_dotenv, set_key
from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError, Frame

ENV_PATH = Path(".env")
load_dotenv(ENV_PATH)
SESSION_PATH = Path("sessions/session.json")

def _print(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")

def _safe_json_dump(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False), encoding="utf-8")
    path.chmod(0o600)

def _payload_text(payload: Union[str, bytes]) -> str:
    if isinstance(payload, bytes):
        return payload.decode("utf-8", errors="replace")
    return payload

def _extract_ssid_from_socketio(payload: str) -> Optional[str]:
    """Extract SSID from Socket.IO frames like:
       42["authorization",{"session":"<SSID>","isDemo":0,"tournamentId":0}]
    """
    try:
        idx = payload.find("[")
        if idx == -1:
            return None
        arr_text = payload[idx:]
        arr = json.loads(arr_text)
        if isinstance(arr, list) and len(arr) >= 2:
            event = arr[0]
            data = arr[1]
            if isinstance(event, str) and isinstance(data, dict):
                if event.lower() in ("authorization", "authorize", "auth", "authenticated"):
                    ssid = data.get("session")
                    if isinstance(ssid, str) and len(ssid) >= 8:
                        return ssid
                # fallback: any field containing "session"
                for k, v in data.items():
                    if isinstance(k, str) and "session" in k.lower() and isinstance(v, str) and len(v) >= 8:
                        return v
    except Exception:
        pass
    return None

def _extract_ssid_from_payload(payload: Union[str, bytes]) -> Optional[str]:
    payload = _payload_text(payload)

    # 0) Socket.IO
    ssid = _extract_ssid_from_socketio(payload)
    if ssid:
        return ssid

    # 1) Direct JSON
    try:
        obj = json.loads(payload)
        if isinstance(obj, dict):
            for key in ("session", "ssid", "sessionId", "session_id"):
                val = obj.get(key)
                if isinstance(val, str) and len(val) >= 8:
                    return val
            for key in ("message", "data", "payload"):
                sub = obj.get(key)
                if isinstance(sub, dict):
                    for k2 in ("session", "ssid", "sessionId", "session_id"):
                        val = sub.get(k2)
                        if isinstance(val, str) and len(val) >= 8:
                            return val
    except Exception:
        pass

    # 2) base64 JSON
    try:
        s = payload.strip()
        if re.fullmatch(r"[A-Za-z0-9_\-+/=]+", s) and len(s) >= 16:
            missing = (-len(s)) % 4
            if missing:
                s += "=" * missing
            decoded = base64.b64decode(s)
            as_text = decoded.decode("utf-8", errors="ignore")
            m = re.search(r'"session"\s*:\s*"([^"]{8,})"', as_text)
            if m:
                return m.group(1)
            try:
                obj2 = json.loads(as_text)
                if isinstance(obj2, dict):
                    for key in ("session", "ssid", "sessionId", "session_id"):
                        val = obj2.get(key)
                        if isinstance(val, str) and len(val) >= 8:
                            return val
            except Exception:
                pass
    except Exception:
        pass

    # 3) fallback regex
    m = re.search(r'"session"\s*:\s*"([^"]{8,})"', payload)
    if m:
        return m.group(1)
    return None

def _extract_is_demo_from_payload(payload: Union[str, bytes]) -> Optional[bool]:
    payload = _payload_text(payload)

    try:
        start = payload.find("[")
        message = json.loads(payload[start:]) if start >= 0 else json.loads(payload)
        if isinstance(message, list) and len(message) >= 2 and isinstance(message[1], dict):
            value = message[1].get("isDemo")
        elif isinstance(message, dict):
            value = message.get("isDemo", message.get("is_demo"))
        else:
            return None
        return bool(int(value)) if value is not None else None
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

def _infer_is_demo_from_url(url: str) -> Optional[bool]:
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").lower()
    if not (
        hostname == "quotex.com"
        or hostname.endswith(".quotex.com")
        or hostname == "qxbroker.com"
        or hostname.endswith(".qxbroker.com")
    ):
        return None
    path_parts = {part.lower() for part in parsed.path.split("/") if part}
    if "demo-trade" in path_parts:
        return True
    if "trade" in path_parts:
        return False
    return None

def _trade_url(is_demo: bool, lang: str = "en") -> str:
    route = "demo-trade" if is_demo else "trade"
    return f"https://quotex.com/{lang}/{route}"

class QuotexBot:
    def __init__(self, headless: bool = False, is_demo: bool = True):
        self.email = os.getenv("QUOTEX_EMAIL", "")
        self.password = os.getenv("QUOTEX_PASSWORD", "")
        self.headless = headless
        self.is_demo = is_demo
        self.ws_urls: List[str] = []
        self.ssid: Optional[str] = None
        self.captured_is_demo: Optional[bool] = None

    # persistence
    def save_session(self) -> None:
        if self.captured_is_demo is None:
            raise RuntimeError("Refusing to save a session without a confirmed account mode")
        if self.ssid and not self.ssid.startswith('42["authorization",'):
            auth_data = {"session": self.ssid, "isDemo": int(self.captured_is_demo), "tournamentId": 0}
            self.ssid = '42["authorization",' + json.dumps(auth_data, separators=(",", ":")) + "]"
        _safe_json_dump(SESSION_PATH, {"ssid": self.ssid, "is_demo": self.captured_is_demo})
        set_key(str(ENV_PATH), "QUOTEX_SSID", self.ssid, quote_mode="always")
        ENV_PATH.chmod(0o600)
        os.environ["QUOTEX_SSID"] = self.ssid
        _print(f"{'Demo' if self.captured_is_demo else 'Live'} session saved to sessions/session.json")
        _print("SSID saved to .env")

    # helpers
    async def _dismiss_banners(self, page) -> None:
        """Try to dismiss cookie banners / overlays that may block clicks."""
        selectors = [
            'button:has-text("Accept all")',
            'button:has-text("Allow all")',
            'button:has-text("I Agree")',
            'button:has-text("I agree")',
            'button:has-text("OK")',
            'button:has-text("Got it")',
            '[data-testid="cookie-accept-all"]',
            '#onetrust-accept-btn-handler',
        ]
        for sel in selectors:
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.click(timeout=800)
                    _print(f"Dismissed banner via {sel}")
                    await page.wait_for_timeout(200)
            except Exception:
                continue
        # Escape overlay
        try:
            await page.keyboard.press("Escape")
        except Exception:
            pass
        # Remove full-screen portals if any
        try:
            await page.evaluate("""() => {
                const portals = document.querySelectorAll('#portal, .modal, .overlay');
                portals.forEach(p => { try { p.remove(); } catch(e){} });
            }""")
        except Exception:
            pass

    async def _grant_notifications(self, context, origin: str) -> None:
        try:
            await context.grant_permissions(["notifications"], origin=origin)
        except Exception:
            pass

    async def _try_click_allow_ui(self, page) -> None:
        candidates = [
            'button:has-text("Allow")',
            'text=/^Allow Notifications?$/i',
            'button:has-text("السماح")',
            'text=/السماح/',
        ]
        for sel in candidates:
            try:
                loc = page.locator(sel)
                if await loc.count():
                    await loc.first.click(timeout=800)
                    _print('Clicked site "Allow" button.')
                    return
            except Exception:
                continue

    # login flow
    async def _fill_login_in_frame(self, frame: Frame) -> bool:
        """Try to fill login inside the provided frame. Returns True if success."""
        email_selectors = [
            'input[name="email"]',
            'input[type="email"]',
            '#emailInput',
            'input[autocomplete="username"]',
            'input[placeholder*="mail" i]',
            'input[placeholder*="email" i]',
            'input[name="login"]',
            '#login',
        ]
        pass_selectors = [
            'input[name="password"]',
            'input[type="password"]',
            'input[autocomplete="current-password"]',
            '#password',
        ]
        submit_selectors = [
            'button[type="submit"]',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            'text=/^Sign in$/i',
            'button:has-text("Continue")',
        ]

        # Email
        for sel in email_selectors:
            try:
                el = frame.locator(sel).first
                await el.wait_for(state="visible", timeout=2500)
                await el.fill(self.email, timeout=2500)
                email_ok = True
                break
            except Exception:
                continue
        else:
            return False

        # Password (may be same step or appear after clicking Continue)
        pwd_ok = False
        for sel in pass_selectors:
            try:
                el = frame.locator(sel).first
                await el.wait_for(state="visible", timeout=2000)
                await el.fill(self.password, timeout=2000)
                pwd_ok = True
                break
            except Exception:
                continue

        # If password not visible yet, try to proceed one step
        if not pwd_ok:
            for sel in submit_selectors:
                try:
                    btn = frame.locator(sel).first
                    if await btn.count():
                        await btn.click(timeout=1500)
                        await frame.wait_for_timeout(800)
                        # try password again
                        for sel2 in pass_selectors:
                            try:
                                el2 = frame.locator(sel2).first
                                await el2.wait_for(state="visible", timeout=2500)
                                await el2.fill(self.password, timeout=2500)
                                pwd_ok = True
                                break
                            except Exception:
                                continue
                except Exception:
                    continue

        if not pwd_ok:
            return False

        # Submit
        for sel in submit_selectors:
            try:
                btn = frame.locator(sel).first
                if await btn.count():
                    await btn.click(timeout=2000)
                    _print("Submitted login form.")
                    return True
            except Exception:
                continue
        # Or press Enter
        try:
            await frame.keyboard.press("Enter")
            _print("Submitted login form (Enter).")
            return True
        except Exception:
            return False

    async def _force_login_tab(self, page) -> None:
        """Ensure the 'Login' tab (#tab-1) is active/visible."""
        try:
            login_tab = page.locator('#tab-1')
            if not await login_tab.is_visible():
                tab_btn = page.locator('.modal-sign__tabs-block a.modal-sign__tab', has_text='Login').first
                await tab_btn.click(timeout=3000)
                await page.wait_for_timeout(300)
            # Sometimes both tabs are in DOM; make sure #tab-1 has 'active' or is displayed
            await login_tab.wait_for(state='visible', timeout=8000)
            _print("Login tab is active.")
        except Exception:
            # fallback: click header "Log in" button to reload sign-in page
            try:
                await page.locator('a.header__button-log-in, a[href$="/en/sign-in/"]').first.click(timeout=2000)
                await page.wait_for_load_state('domcontentloaded', timeout=10000)
                await page.wait_for_selector('#tab-1', timeout=10000)
                _print("Navigated via header 'Log in' link.")
            except Exception:
                pass

    async def _fill_login_in_tab(self, page) -> bool:
        """Fill the form strictly within #tab-1 (Login)."""
        try:
            await page.wait_for_selector('#tab-1 form[action*="/sign-in"]', timeout=15000)
        except Exception:
            return False

        form_scope = page.locator('#tab-1')

        # Email
        email_selectors = [
            '#tab-1 input[name="email"]',
            '#tab-1 input[type="email"]',
            '#tab-1 .modal-sign__input-value[type="email"]',
            'form[action*="/sign-in"] input[name="email"]',
        ]
        filled_email = False
        for sel in email_selectors:
            try:
                el = page.locator(sel).first
                await el.wait_for(state='visible', timeout=4000)
                await el.scroll_into_view_if_needed()
                await el.click(timeout=1000)
                await el.fill(self.email, timeout=2500)
                filled_email = True
                _print(f"Filled email via: {sel}")
                break
            except Exception:
                continue
        if not filled_email:
            return False

        # Password
        pass_selectors = [
            '#tab-1 input[name="password"]',
            '#tab-1 input[type="password"]',
            '#tab-1 .modal-sign__input-value[type="password"]',
            'form[action*="/sign-in"] input[type="password"]',
        ]
        filled_pwd = False
        for sel in pass_selectors:
            try:
                el = page.locator(sel).first
                await el.wait_for(state='visible', timeout=4000)
                await el.scroll_into_view_if_needed()
                await el.click(timeout=1000)
                await el.fill(self.password, timeout=2500)
                filled_pwd = True
                _print(f"Filled password via: {sel}")
                break
            except Exception:
                continue
        if not filled_pwd:
            return False

        # Submit (button without type=submit; text "Sign in")
        submit_selectors = [
            '#tab-1 button.modal-sign__block-button:has-text("Sign in")',
            '#tab-1 button:has-text("Sign in")',
            'form[action*="/sign-in"] button:has-text("Sign in")',
        ]
        clicked_submit = False
        for sel in submit_selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count():
                    await btn.scroll_into_view_if_needed()
                    await btn.click(timeout=2500)
                    clicked_submit = True
                    _print(f"Clicked submit via: {sel}")
                    break
            except Exception:
                continue

        if not clicked_submit:
            try:
                await page.locator('#tab-1 input[name="password"]').press('Enter')
                _print("Submitted login form via Enter key.")
                clicked_submit = True
            except Exception:
                pass

        if clicked_submit:
            try:
                await page.wait_for_load_state('networkidle', timeout=15000)
            except Exception:
                pass
            return True
        return False

    async def _fill_login(self, page) -> None:
        await page.wait_for_load_state('domcontentloaded')
        await self._dismiss_banners(page)
        await self._force_login_tab(page)
        # Try strict tab fill first
        if await self._fill_login_in_tab(page):
            return
        # Fallback: original generic strategy (page + iframes)
        if await self._fill_login_in_frame(page):
            return
        for fr in page.frames:
            if fr == page.main_frame:
                continue
            try:
                if await self._fill_login_in_frame(fr):
                    return
            except Exception:
                continue
        raise RuntimeError('Could not find email/password fields in any frame or tab')

    async def _scan_client_storage_for_ssid(self, page) -> Optional[str]:
        try:
            ssid = await page.evaluate("""() => {
                try {
                    for (let i = 0; i < localStorage.length; i++) {
                        const k = localStorage.key(i);
                        const v = localStorage.getItem(k) || "";
                        if (/session|ssid/i.test(k) && typeof v === 'string' && v.length >= 8) return v;
                        const m = /"session"\\s*:\\s*"([^"]{8,})"/.exec(v);
                        if (m) return m[1];
                    }
                    for (const k of Object.keys(window)) {
                        if (/session|ssid/i.test(k)) {
                            const v = String(window[k] ?? '');
                            if (v && v.length >= 8) return v;
                        }
                    }
                    const parts = (document.cookie || '').split(';');
                    for (const p of parts) {
                        const [ck, cv] = p.split('=');
                        if (/session|ssid/i.test(ck || '') && (cv || '').length >= 8) return cv;
                    }
                } catch (e) {}
                return null;
            }""")
            if ssid and isinstance(ssid, str):
                return ssid
        except Exception:
            pass
        return None

    # main
    async def run(self) -> None:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=self.headless,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--ignore-certificate-errors",
                    "--disable-features=IsolateOrigins,site-per-process",
                ],
            )

            context = await browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                permissions=["notifications"],
                viewport={"width": 1366, "height": 768},
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
            )
            await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")

            await self._grant_notifications(context, "https://quotex.com")

            page = await context.new_page()

            # SSID event
            ssid_event = asyncio.Event()

            # HTTP JSON watcher (fallback)
            async def on_response(response):
                try:
                    ct = response.headers.get("content-type", "")
                    if "application/json" in ct:
                        text = await response.text()
                        m = re.search(r'"session"\\s*:\\s*"([^"]{8,})"', text)
                        payload_mode = _extract_is_demo_from_payload(text)
                        url_mode = _infer_is_demo_from_url(page.url)
                        if payload_mode is not None and url_mode is not None and payload_mode != url_mode:
                            _print("Session response mode conflicts with the current trade URL; ignoring it.")
                            return
                        is_demo = payload_mode if payload_mode is not None else url_mode
                        if m and not self.ssid and is_demo is not None:
                            if is_demo != self.is_demo:
                                _print("Session response does not match the selected account mode; ignoring it.")
                                return
                            self.ssid = m.group(1)
                            self.captured_is_demo = is_demo
                            _print("Session captured from HTTP response.")
                            self.save_session()
                            ssid_event.set()
                except Exception:
                    pass

            page.on("response", on_response)

            # WebSocket watcher
            def on_websocket(ws):
                self.ws_urls.append(ws.url)
                _print(f"WebSocket created: {ws.url}")

                async def _handle_payload(payload: str):
                    if self.ssid:
                        return
                    ssid = _extract_ssid_from_payload(payload)
                    if ssid:
                        payload_mode = _extract_is_demo_from_payload(payload)
                        url_mode = _infer_is_demo_from_url(page.url)
                        if payload_mode is not None and url_mode is not None and payload_mode != url_mode:
                            _print("Session frame mode conflicts with the current trade URL; ignoring it.")
                            return
                        is_demo = payload_mode if payload_mode is not None else url_mode
                        if is_demo is None:
                            _print("Session frame has no mode and the current URL is not a demo/live trade URL; ignoring it.")
                            return
                        if is_demo != self.is_demo:
                            _print("Session frame does not match the selected account mode; ignoring it.")
                            return
                        self.ssid = ssid
                        self.captured_is_demo = is_demo
                        _print(f"{'Demo' if is_demo else 'Live'} session captured from WebSocket.")
                        self.save_session()
                        ssid_event.set()

                def _frame_received(payload: str):
                    asyncio.create_task(_handle_payload(payload))

                ws.on("framereceived", _frame_received)
                ws.on("framesent", _frame_received)

            page.on("websocket", on_websocket)

            url = "https://quotex.com/en/sign-in/"
            _print(f"Navigating to {url} ...")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            await self._dismiss_banners(page)
            await self._try_click_allow_ui(page)
            if self.email and self.password:
                await self._fill_login(page)
                target_url = _trade_url(self.is_demo)
                _print(f"Opening selected {'demo' if self.is_demo else 'live'} account: {target_url}")
                await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                actual_mode = _infer_is_demo_from_url(page.url)
                if actual_mode != self.is_demo:
                    raise RuntimeError(
                        f"Quotex did not open the selected {'demo' if self.is_demo else 'live'} route; "
                        f"current URL is {page.url}"
                    )
            else:
                _print(
                    "Complete sign-in manually in the browser; credentials will not be saved. "
                    f"After sign-in, the helper will open {_trade_url(self.is_demo)}."
                )
                await page.wait_for_url(re.compile(r"/(?:demo-)?trade(?:/|$)"), timeout=300000)
                await page.goto(_trade_url(self.is_demo), wait_until="domcontentloaded", timeout=60000)
                actual_mode = _infer_is_demo_from_url(page.url)
                if actual_mode != self.is_demo:
                    raise RuntimeError(
                        f"Quotex did not open the selected {'demo' if self.is_demo else 'live'} route; "
                        f"current URL is {page.url}"
                    )

            timeout = 30 if self.email and self.password else 300
            try:
                await asyncio.wait_for(ssid_event.wait(), timeout=timeout)
                _print("SSID saved. Closing browser now...")
            except asyncio.TimeoutError:
                _print("SSID was not captured from network; scanning client storage...")
                ssid = await self._scan_client_storage_for_ssid(page)
                if ssid:
                    is_demo = _infer_is_demo_from_url(page.url)
                    if is_demo is None or is_demo != self.is_demo:
                        _print(f"Could not determine account mode from URL {page.url}; refusing to save the SSID.")
                    else:
                        self.ssid = ssid
                        self.captured_is_demo = is_demo
                        self.save_session()
                        _print("SSID saved from client storage. Closing browser now...")
                else:
                    _print("SSID not found. Closing browser.")

            await browser.close()

async def main():
    parser = argparse.ArgumentParser(description="Sign in to Quotex and save a reusable session.")
    parser.add_argument(
        "--mode",
        choices=("demo", "live"),
        default="demo",
        help="Account to open and capture (default: demo).",
    )
    args = parser.parse_args()
    bot = QuotexBot(headless=False, is_demo=args.mode == "demo")
    await bot.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
