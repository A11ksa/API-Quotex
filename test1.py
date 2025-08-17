#################################################################
# Example TEST CMD
#################################################################
# ======================
# python test1.py --demo --once --amount 1.5 --interval 120 --top 30
# python test1.py --live --loop --amount 1.0
# ======================
import os
import time
import logging
import asyncio
import argparse
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

# Third-party
from loguru import logger as loguru_logger
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.align import Align
from rich.text import Text
from rich import print as rprint

# Project
from api_quotex.client import AsyncQuotexClient, OrderDirection
from api_quotex.utils import format_timeframe
from api_quotex.login import get_ssid, load_config

# ==========================
# Color & Icon Definitions
# ==========================
ENDC = "[white]"
PURPLE = "[purple]"
DARK_GRAY = "[bright_black]"
OKCYAN = "[steel_blue1]"
lg = "[green3]"
r = "[red]"
dr = "[dark_red]"
dg = "[spring_green4]"
dg2 = "[dark_green]"
bl = "[blue]"
g = "[green]"
w = "[white]"
cy = "[cyan]"
ye = "[yellow]"
yl = "[#FFD700]"
orange = "[dark_orange3]"

# UI icons
info = f"{OKCYAN}ℹ{ENDC}"
warning = f"{yl}⚠{ENDC}"
error = f"{r}⛔{ENDC}"
win = f"{g}✔{ENDC}"
loss = f"{r}✘{ENDC}"
draw = f"{ye}＝{ENDC}"
wait = f"{OKCYAN}…{ENDC}"

# Global console
console = Console()

# ==========================
# Logging config
# ==========================
LOG_FILE = f"log-{time.strftime('%Y-%m-%d')}.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE, encoding="utf-8")]
)
logger = logging.getLogger(__name__)
loguru_logger.remove()
loguru_logger.add(LOG_FILE, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

# ==========================
# CLI Args / UI Preferences
# ==========================
def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Elegant smoke test for API-Quotex (Playwright SSID + Async WS)"
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="Use demo account (default)")
    mode.add_argument("--live", action="store_true", help="Use live account")

    loopgrp = parser.add_mutually_exclusive_group()
    loopgrp.add_argument("--once", action="store_true", help="Run a single iteration then exit")
    loopgrp.add_argument("--loop", action="store_true", help="Run continuous loop")

    parser.add_argument("--amount", type=float, default=1.0, help="Test trade amount (default: 1.0)")
    parser.add_argument("--interval", type=int, default=300, help="Refresh interval for assets table (sec)")
    parser.add_argument("--top", type=int, default=30, help="Top N assets to display in table")
    parser.add_argument("--required-tf", type=str, default="1m", help="Timeframe key (e.g., 1m, 5m, 60)")
    parser.add_argument("--quiet", action="store_true", help="Reduce console output; keep detailed logs to file")
    return parser.parse_args()

ARGS = _parse_args()
QUIET_MODE = ARGS.quiet
REFRESH_INTERVAL = max(30, ARGS.interval)
TRADE_AMOUNT = max(0.5, ARGS.amount)
REQUIRED_TF = ARGS.required_tf
TOP_ASSETS = max(0, ARGS.top)
USE_DEMO = (not ARGS.live) or ARGS.demo
RUN_LOOP = ARGS.loop and not ARGS.once

# ==========================
# Beautiful Banner
# ==========================
def _banner() -> None:
    title = Text("API‑Quotex • Smoke Test", justify="center")
    title.stylize("bold cyan")
    subtitle = Text("Playwright SSID  •  Async WebSocket  •  Rich UI", justify="center")
    subtitle.stylize("bright_black")
    console.print(Rule(style="cyan"))
    console.print(Align.center(title))
    console.print(Align.center(subtitle))
    console.print(Rule(style="cyan"))

#========================
# SSID resolver (supports async/sync get_ssid)
#========================
async def resolve_ssid(is_demo: bool = True) -> Optional[dict]:
    """
    Try to reuse existing session via get_ssid(). If get_ssid is sync in your build,
    we adapt automatically. Returns a dict like {"ssid": "...", "is_demo": True} or None.
    """
    try:
        maybe = get_ssid  # function ref
        result = maybe(is_demo=is_demo)  # attempt reuse
        if asyncio.iscoroutine(result):
            result = await result
    except RuntimeError:
        creds = load_config()
        email = creds.get("email") or input("Enter your email: ")
        password = creds.get("password") or input("Enter your password: ")
        result = maybe(email=email, password=password, is_demo=is_demo)
        if asyncio.iscoroutine(result):
            result = await result
    except Exception as e:
        logger.error(f"resolve_ssid initial attempt failed: {e}", exc_info=True)
        return None

    if isinstance(result, tuple) and len(result) == 2:
        success, data = result
        if not success:
            return None
        return data
    elif isinstance(result, dict):
        return result
    else:
        logger.error("get_ssid() returned an unexpected structure.")
        return None

#========================
# Helpers
#========================
def _has_tf(info: Dict[str, Any], tf_key: str) -> bool:
    tfs = info.get("available_timeframes") or []
    formatted = {format_timeframe(t) for t in tfs}
    return tf_key in formatted or (tf_key.isdigit() and int(tf_key) in set(tfs))

def _score_asset(sym: str, info: Dict[str, Any], required_tf: str) -> float:
    """
    Smart scoring: prioritize payout, de-prioritize closed assets and OTC slightly,
    ensure timeframe availability.
    """
    if not info.get("is_open"):
        return -1.0
    if (info.get("payout") or 0) <= 0:
        return -1.0
    if not _has_tf(info, required_tf):
        return -1.0
    payout = float(info.get("payout", 0.0))
    otc_penalty = 3.0 if info.get("is_otc") else 0.0
    name_bonus = 0.5 if any(x in sym for x in ("EURUSD", "GBPUSD", "AUDUSD", "USDJPY", "USDCAD", "EURJPY", "GBPJPY")) else 0.0
    return payout - otc_penalty + name_bonus

def choose_best_asset(assets: Dict[str, Dict[str, Any]], required_tf: str = "1m") -> Optional[Tuple[str, str, float]]:
    """Return (symbol, timeframe_key, payout) for the best open asset with payout>0."""
    ranked = sorted(
        assets.items(),
        key=lambda kv: _score_asset(kv[0], kv[1], required_tf),
        reverse=True
    )
    for sym, info in ranked:
        score = _score_asset(sym, info, required_tf)
        if score <= 0:
            break
        return sym, required_tf, float(info.get("payout", 0.0))
    return None

#========================
# Assets Table Display
#========================
def print_assets_table(
    assets: Dict[str, Dict[str, Any]],
    *,
    only_open: bool = False,
    sort_by_payout: bool = True,
    top: int = 0
) -> None:
    table = Table(title=f"{PURPLE}Available Assets and Payouts{ENDC}", show_lines=True)
    table.add_column(f"{cy}Symbol{ENDC}", justify="left", no_wrap=True)
    table.add_column(f"{g}Name{ENDC}")
    table.add_column(f"{PURPLE}Type{ENDC}")
    table.add_column(f"{ye}Payout %{ENDC}", justify="right")
    table.add_column(f"{r}OTC{ENDC}")
    table.add_column(f"{ENDC}Open{ENDC}")
    table.add_column(f"{ENDC}Timeframes{ENDC}")

    filtered = {
        sym: info for sym, info in assets.items()
        if not only_open or (info.get('is_open') and (info.get('payout') or 0) > 0)
    }
    if not filtered:
        logger.info("No assets match filter")
        return

    items = sorted(filtered.items(), key=lambda x: x[1].get('payout', 0), reverse=sort_by_payout)
    if top > 0:
        items = items[:top]

    for sym, info in items:
        tfs = info.get('available_timeframes', []) or []
        tfs_str = ", ".join(format_timeframe(t) for t in tfs) if tfs else "N/A"
        table.add_row(
            f"{cy}{sym}{ENDC}",
            f"{g}{info.get('name','--')}{ENDC}",
            f"{PURPLE}{info.get('type','--')}{ENDC}",
            f"{ye}{info.get('payout','--')}{ENDC}",
            f"{r}Yes{ENDC}" if info.get('is_otc') else f"{ENDC}No{ENDC}",
            f"{g}Yes{ENDC}" if info.get('is_open') else f"{ENDC}No{ENDC}",
            f"{ENDC}{tfs_str}{ENDC}"
        )
    if not QUIET_MODE:
        console.print(table)

#========================
# Candles Table Display
#========================
def print_candles_table(candles_df, asset: str, timeframe: str) -> None:
    table = Table(title=f"{PURPLE}Candles for {asset} ({timeframe}){ENDC}", show_lines=True)
    table.add_column(f"{cy}Timestamp{ENDC}", justify="left")
    table.add_column(f"{g}Open{ENDC}", justify="right")
    table.add_column(f"{ye}High{ENDC}", justify="right")
    table.add_column(f"{r}Low{ENDC}", justify="right")
    table.add_column(f"{ENDC}Close{ENDC}", justify="right")
    table.add_column(f"{PURPLE}Volume{ENDC}", justify="right")

    # Expecting index to be datetime-like; fallback to string if needed
    for idx, row in candles_df.iterrows():
        try:
            ts = idx.strftime('%Y-%m-%d %H:%M:%S')
        except Exception:
            ts = str(idx)
        o = row.get('open', None)
        h = row.get('high', None)
        l = row.get('low', None)
        c = row.get('close', None)
        v = row.get('volume', 0)
        table.add_row(
            f"{cy}{ts}{ENDC}",
            f"{g}{(o if o is not None else 0):.5f}{ENDC}",
            f"{ye}{(h if h is not None else 0):.5f}{ENDC}",
            f"{r}{(l if l is not None else 0):.5f}{ENDC}",
            f"{ENDC}{(c if c is not None else 0):.5f}{ENDC}",
            f"{PURPLE}{(v if v is not None else 0):.2f}{ENDC}"
        )
    if not QUIET_MODE:
        console.print(table)

#========================
# Trade Card Display
#========================
def print_trade_card(order_id: str, status: str, profit: float) -> None:
    """
    Render a unified, minimal card with [ Trade {id} ] as the header line (user preference),
    and a small key/values table below.
    """
    header = Text(f"[ Trade {order_id} ]", justify="left")
    header.stylize("bold yellow")
    if not QUIET_MODE:
        console.print(header)

    profit_color = g if profit > 0 else r if profit < 0 else OKCYAN
    status_color = {
        "WIN": lg, "LOSS": r, "DRAW": ye,
    }.get(status.upper(), w)

    table = Table(show_lines=True, show_header=False, padding=(0,1))
    table.add_column("Label", style="bright_black", width=16, no_wrap=True)
    table.add_column("Value", style="white", no_wrap=False)
    table.add_row("Result", f"{status_color}{status}{ENDC}")
    table.add_row("Profit", f"{profit_color}${profit:.2f}{ENDC}")
    table.add_row("When", f"{ye}{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{ENDC}")
    if not QUIET_MODE:
        console.print(table)

#========================
# Trade Result Panel Display (verbose)
#========================
async def check_win_task(client: AsyncQuotexClient, order_id: str) -> None:
    try:
        profit, status = await client.check_win(order_id)
        if profit is None or status is None:
            if not QUIET_MODE:
                rprint(Panel(
                    f"{error} {r}No result received for order {order_id}{ENDC}",
                    title=f"{r}Trade Result{ENDC}",
                    border_style="red"
                ))
            return

        print_trade_card(order_id, (status or 'UNKNOWN').upper(), float(profit or 0.0))

    except Exception as e:
        logger.error(f"Failed to check win result for order {order_id}: {e}", exc_info=True)
        if not QUIET_MODE:
            rprint(Panel(
                f"{error} Exception occurred: {r}{str(e)}{ENDC}",
                title=f"{r}Trade Result Error{ENDC}", border_style="red"
            ))

#========================
# Main Execution Loop
#========================
async def main() -> None:
    """
    1) Resolve SSID (Playwright flow if needed)
    2) Connect & show account
    3) List assets periodically; pick best 1m asset
    4) Place CALL then PUT test orders; show results as cards
    5) Loop or exit based on flags
    """
    if not QUIET_MODE:
        _banner()

    client: Optional[AsyncQuotexClient] = None
    try:
        # Resolve session/SSID
        session_data = await resolve_ssid(is_demo=USE_DEMO)
        if not session_data:
            if not QUIET_MODE:
                rprint(Panel(f"{error} {r}Failed to obtain SSID.{ENDC}",
                             title=f"{info} {PURPLE}Login{ENDC}", border_style="red"))
            return

        ssid_or_token = session_data.get("ssid") or session_data.get("token")
        if not ssid_or_token:
            if not QUIET_MODE:
                rprint(Panel(f"{error} {r}No SSID or token returned by get_ssid().{ENDC}",
                             title=f"{info} {PURPLE}Login{ENDC}", border_style="red"))
            return

        client = AsyncQuotexClient(
            ssid=ssid_or_token,
            is_demo=session_data.get("is_demo", USE_DEMO),
            persistent_connection=False
        )

        # Connect with a status spinner
        with console.status(f"{wait} Connecting to server...", spinner="dots"):
            connected = await client.connect()
        if not connected:
            if not QUIET_MODE:
                rprint(Panel(f"{error} {r}Failed to connect to server.{ENDC}",
                             title=f"{info} {PURPLE}Connection{ENDC}", border_style="red"))
            return

        last_fetch = 0.0
        assets_cache: Dict[str, Dict[str, Any]] = {}

        # Prepare one iteration function so we can loop or run once easily
        async def iteration() -> None:
            nonlocal last_fetch, assets_cache

            # Account info
            balance = await client.get_balance()
            bal_value = getattr(balance, "amount", None)
            if bal_value is None:
                bal_value = getattr(balance, "balance", 0.0)

            if not QUIET_MODE:
                rprint(Panel(
                    f"{info} {DARK_GRAY}Balance: {g}{bal_value:.2f} USD{ENDC}\n"
                    f"{info} {DARK_GRAY}Demo: {ye}{getattr(balance, 'is_demo', USE_DEMO)}{ENDC}\n"
                    f"{info} {DARK_GRAY}Uid: {g}{getattr(client, 'uid', '--')}{ENDC}",
                    title=f"{info} {PURPLE}Account Info{ENDC}"
                ))

            now = time.time()
            # Always fetch assets for decision making; print the table only every refresh interval
            assets = await client.get_available_assets()
            if assets:
                assets_cache = assets

            if (now - last_fetch) >= REFRESH_INTERVAL and not QUIET_MODE:
                rprint(Panel(f"{info} {ye}Open assets{ENDC}", title=f"{info} {PURPLE}Assets{ENDC}"))
                print_assets_table(assets_cache, only_open=True, sort_by_payout=True, top=TOP_ASSETS)
                last_fetch = now

            # Pick a tradable asset
            choice = choose_best_asset(assets_cache, required_tf=REQUIRED_TF)
            if not choice:
                if not QUIET_MODE:
                    rprint(Panel(
                        f"{warning} {yl}No open assets with positive payout at {REQUIRED_TF}.{ENDC}",
                        title=f"{info} {PURPLE}Assets{ENDC}", border_style="yellow"
                    ))
                await asyncio.sleep(30)
                return

            asset_sym, tf_key, live_payout = choice

            # Confirm payout via API; tolerant to int/string tf
            try:
                payout = await client.get_payout(asset_sym, tf_key)
            except Exception:
                try:
                    tf_int = int(tf_key) if tf_key.isdigit() else 60 if tf_key.lower().endswith("m") else 60
                    payout = await client.get_payout(asset_sym, tf_int)
                except Exception:
                    payout = live_payout

            if not QUIET_MODE:
                rprint(f"{info} {g}Payout on {cy}{asset_sym}{ENDC} ({tf_key}): {ye}{payout}%{ENDC}")

            # Quick candles preview (if available)
            try:
                if hasattr(client, "get_candles_dataframe"):
                    candles_df = await client.get_candles_dataframe(asset_sym, tf_key, count=10)  # type: ignore
                    if candles_df is not None and not QUIET_MODE:
                        print_candles_table(candles_df, asset_sym, tf_key)
            except Exception:
                pass

            # --- Test CALL order ---
            order_id = None
            try:
                order = await client.place_order(asset_sym, amount=TRADE_AMOUNT, direction=OrderDirection.CALL, duration=60)
                order_id = getattr(order, "order_id", None) or getattr(order, "id", None)
                if not QUIET_MODE:
                    rprint(f"{info} {cy}Order Placed: {ye}{order_id} {w}- {g}{getattr(order, 'status', 'OPEN')}{ENDC}")
            except Exception as e:
                logger.error(f"Failed to place CALL order: {e}", exc_info=True)
                if not QUIET_MODE:
                    rprint(Panel(
                        f"{error} CALL order failed: {r}{str(e)}{ENDC}",
                        title=f"{info} {r}Order Error{ENDC}", border_style="red"
                    ))
                await asyncio.sleep(5)
                return

            if order_id:
                await check_win_task(client, order_id)

            # --- Test PUT order ---
            try:
                order = await client.place_order(asset=asset_sym, amount=TRADE_AMOUNT, direction=OrderDirection.PUT, duration=60)
                order_id = getattr(order, "order_id", None) or getattr(order, "id", None)
                if not QUIET_MODE:
                    rprint(f"{info} {DARK_GRAY}Order placed with ID: {ye}{order_id}{ENDC}")
                profit, status = await client.check_win(order_id)
                print_trade_card(order_id, (status or "UNKNOWN").upper(), float(profit or 0.0))
            except Exception as e:
                logger.error(f"Failed to place/check PUT order: {e}", exc_info=True)

        # Run once or loop
        if RUN_LOOP:
            while True:
                try:
                    await iteration()
                    logger.info("Sleeping 60 seconds before next iteration...")
                    await asyncio.sleep(60)
                except KeyboardInterrupt:
                    break
        else:
            await iteration()

    except KeyboardInterrupt:
        logger.info("Stopping due to user interrupt...")
    finally:
        try:
            if client:
                await client.disconnect()
        except Exception:
            pass

#========================
# Entrypoint
#========================
if __name__ == "__main__":
    # Windows loop policy safety
    if os.name == "nt":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())  # type: ignore[attr-defined]
        except Exception:
            pass
    asyncio.run(main())
