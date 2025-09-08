#################################################################
# Example TEST CMD
#################################################################
# ======================
# python test1.py
# ======================
import time
import logging
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from loguru import logger as loguru_logger
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich import print as rprint
from api_quotex.client import AsyncQuotexClient, OrderDirection
from api_quotex.utils import format_timeframe
from api_quotex.login import get_ssid, load_config

# Color definitions
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
Bold_orange = "[bold orange1]"
Bold_green = "[bold green]"
info = g + "[" + w + "i" + g + "]" + ENDC
attempt = g + "[" + w + "+" + g + "]" + ENDC
INPUT = lg + "(" + cy + "~" + lg + ")" + ENDC
sleep = bl + "[" + w + "*" + bl + "]" + ENDC
error = g + "[" + r + "!" + g + "]" + ENDC
success = w + "(" + lg + "*" + w + ")" + ENDC
warning = yl + "(" + w + "!" + yl + ")" + ENDC
wait = yl + "(" + w + "●" + yl + ")" + ENDC
win = w + "[" + lg + "✓" + w + "]" + ENDC
loss = w + "[" + r + "x" + w + "]" + ENDC
draw = w + "[" + OKCYAN + "≈" + w + "]" + ENDC

# Logging config
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(f"log-{time.strftime('%Y-%m-%d')}.txt", encoding="utf-8")]
)
logger = logging.getLogger(__name__)
loguru_logger.remove()
loguru_logger.add(f"log-{time.strftime('%Y-%m-%d')}.txt", level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

#==========================
# Assets Table Display
#==========================
def print_assets_table(assets: Dict[str, Dict[str, Any]], *, only_open: bool = False, sort_by_payout: bool = True, top: int = 0):
    console = Console()
    table = Table(title=f"{PURPLE}Available Assets and Payouts{ENDC}", show_lines=True)
    table.add_column(f"{cy}Symbol{ENDC}", justify="left", no_wrap=True)
    table.add_column(f"{g}Name{ENDC}")
    table.add_column(f"{PURPLE}Type{ENDC}")
    table.add_column(f"{ye}Payout %{ENDC}", justify="right")
    table.add_column(f"{r}OTC{ENDC}")
    table.add_column(f"{ENDC}Open{ENDC}")
    table.add_column(f"{ENDC}Timeframes{ENDC}")
    filtered = {sym: info for sym, info in assets.items() if not only_open or (info.get('is_open') and (info.get('payout') or 0) > 0)}
    if not filtered:
        logger.warning("No assets match filter")
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
    console.print(table)

#==========================
# Candles Table Display
#==========================
def print_candles_table(candles_df, asset: str, timeframe: str):
    console = Console()
    table = Table(title=f"{PURPLE}Candles for {asset} ({timeframe}){ENDC}", show_lines=True)
    table.add_column(f"{cy}Timestamp{ENDC}", justify="left")
    table.add_column(f"{g}Open{ENDC}", justify="right")
    table.add_column(f"{ye}High{ENDC}", justify="right")
    table.add_column(f"{r}Low{ENDC}", justify="right")
    table.add_column(f"{ENDC}Close{ENDC}", justify="right")
    table.add_column(f"{PURPLE}Volume{ENDC}", justify="right")
    for idx, row in candles_df.iterrows():
        table.add_row(
            f"{cy}{idx.strftime('%Y-%m-%d %H:%M:%S')}{ENDC}",
            f"{g}{row['open']:.5f}{ENDC}",
            f"{ye}{row['high']:.5f}{ENDC}",
            f"{r}{row['low']:.5f}{ENDC}",
            f"{ENDC}{row['close']:.5f}{ENDC}",
            f"{PURPLE}{row.get('volume', 0):.2f}{ENDC}"
        )
    console.print(table)

#==========================
# Helpers: choose a tradable asset/timeframe
#==========================
def _has_tf(info: Dict[str, Any], tf_key: str) -> bool:
    tfs = info.get("available_timeframes") or []
    formatted = {format_timeframe(t) for t in tfs}
    return tf_key in formatted or (tf_key.isdigit() and int(tf_key) in set(tfs))

def choose_best_asset(assets: Dict[str, Dict[str, Any]], required_tf: str = "1m") -> Optional[Tuple[str, str, float]]:
    """Return (symbol, timeframe_key, payout) for the best open asset with payout>0, preferring some majors."""
    preferred = ["AUDCAD", "EURUSD", "GBPUSD", "USDJPY", "USDCAD", "EURGBP", "EURJPY", "AUDUSD", "GBPJPY"]
    # filter for open + payout>0 + has required timeframe
    candidates = []
    for sym, info in assets.items():
        if info.get("is_open") and (info.get("payout") or 0) > 0 and _has_tf(info, required_tf):
            candidates.append((sym, info.get("payout", 0.0)))
    if not candidates:
        return None
    # sort by (preferred first, then high payout)
    def rank(item):
        sym, payout = item
        pref_rank = preferred.index(sym) if sym in preferred else len(preferred) + 1
        return (pref_rank, -payout)
    sym, _ = sorted(candidates, key=rank)[0]
    payout = assets[sym].get("payout", 0.0)
    return sym, required_tf, payout

#==========================
# Trade Result Panel Display
#==========================
async def check_win_task(client: AsyncQuotexClient, order_id: str):
    try:
        profit, status = await client.check_win(order_id)
        if profit is None or status is None:
            rprint(Panel(
                f"{error}{r}No result received for order {order_id}{ENDC}",
                title=f"{r}Trade Result{ENDC}",
                border_style="red"
            ))
            return
        color_code = {
            'win': f"{lg}WIN{ENDC}",
            'loss': f"{r}LOSS{ENDC}",
            'draw': f"{OKCYAN}DRAW{ENDC}"
        }.get(status.lower(), f"{w}{status.upper()}{ENDC}")
        icon = {
            'win': win,
            'loss': loss,
            'draw': draw
        }.get(status.lower(), wait)
        profit_color = g if profit > 0 else r if profit < 0 else OKCYAN
        profit_val = f"{profit_color}${profit:.2f}{ENDC}"
        try:
            order_result = await client.check_order_result(order_id)
            completion_time = order_result.expires_at.strftime('%Y-%m-%d %H:%M:%S') if order_result else "N/A"
        except Exception:
            completion_time = "N/A"
        panel_content = (
            f"{DARK_GRAY}Order ID: {ye}{order_id}{ENDC}\n"
            f"{DARK_GRAY}Result: {icon} {color_code}\n"
            f"{DARK_GRAY}Profit/Loss: {profit_val}\n"
            f"{DARK_GRAY}Completion Time: {ye}{completion_time}{ENDC}"
        )
        rprint(Panel(
            panel_content,
            title=f"{g}Trade Result{ENDC}",
            border_style="bright_green" if status.lower() == "win" else "red" if status.lower() == "loss" else "yellow"
        ))
    except Exception as e:
        logger.error(f"Failed to check win result for order {order_id}: {e}", exc_info=True)
        rprint(Panel(
            f"{error}Exception occurred: {r}{str(e)}{ENDC}",
            title=f"{r}Trade Result Error{ENDC}",
            border_style="red"
        ))

#==========================
# Main Execution Loop
#==========================
async def main():
    """
    1) Try to reuse an existing session (sessions/session.json or config.json) without prompting.
    2) If credentials are missing, prompt once for email/password and attempt login.
    3) Accept either an SSID frame or a bare token to initialize the client.
    4) Connect, show account info, list open assets periodically, preview candles,
       and place two small test orders (CALL then PUT) while reporting results.
    5) Clean up the connection on exit.
    """
    client = None
    try:
        # Attempt session reuse without asking the user first.
        try:
            success, session_data = await get_ssid(is_demo=True)
        except RuntimeError:
            # No saved credentials in config.json → prompt once, then try again.
            creds = load_config()
            email = creds.get("email") or input("Enter your email: ")
            password = creds.get("password") or input("Enter your password: ")
            success, session_data = await get_ssid(email=email, password=password, is_demo=True)

        if not success:
            rprint(Panel(f"{error} {r}Failed to obtain SSID.{ENDC}",
                         title=f"{info} {PURPLE}Login{ENDC}", border_style="red"))
            return

        # Use SSID if present; otherwise fall back to token.
        ssid_or_token = session_data.get("ssid") or session_data.get("token")
        if not ssid_or_token:
            rprint(Panel(f"{error} {r}No SSID or token returned by get_ssid().{ENDC}",
                         title=f"{info} {PURPLE}Login{ENDC}", border_style="red"))
            return

        # Initialize the async client.
        client = AsyncQuotexClient(
            ssid=ssid_or_token,
            is_demo=session_data.get("is_demo", True),
            persistent_connection=False
        )

        # Establish WebSocket connection.
        connected = await client.connect()
        if not connected:
            rprint(Panel(f"{error} {r}Failed to connect to server.{ENDC}",
                         title=f"{info} {PURPLE}Connection{ENDC}", border_style="red"))
            return

        # Main loop: refresh assets table every 5 minutes, place two tiny test trades.
        last_fetch = 0
        interval = 300  # seconds
        assets_cache: Dict[str, Dict[str, Any]] = {}

        while True:
            try:
                if not client.is_connected:
                    logger.info(f"{bl}Reconnecting...{ENDC}")
                    if not await client.connect():
                        logger.error(f"{error}Connection failed, retrying...{ENDC}")
                        await asyncio.sleep(10)
                        continue
                    rprint(Panel(f"{OKCYAN}Connected!{ENDC}", title=f"{g}Status{ENDC}"))

                # Account info
                balance = await client.get_balance()
                bal_value = getattr(balance, "amount", None)
                if bal_value is None:
                    bal_value = getattr(balance, "balance", 0.0)
                rprint(Panel(
                    f"{info} {DARK_GRAY}Balance: {g}{bal_value:.2f} USD{ENDC}\n"
                    f"{info} {DARK_GRAY}Demo: {ye}{balance.is_demo}{ENDC}\n"
                    f"{info} {DARK_GRAY}Uid: {g}{getattr(client, 'uid', '--')}{ENDC}",
                    title=f"{info} {PURPLE}Account Info{ENDC}"
                ))

                now = time.time()

                # Always fetch assets for decision making; print the table only every 'interval'.
                assets = await client.get_available_assets()
                assets_cache = assets or assets_cache

                if now - last_fetch >= interval:
                    rprint(Panel(f"{info} {ye}Open assets{ENDC}",
                                 title=f"{info} {PURPLE}Assets{ENDC}"))
                    print_assets_table(assets_cache, only_open=True, sort_by_payout=True, top=50)
                    last_fetch = now

                # Pick a tradable asset with a 1m timeframe.
                choice = choose_best_asset(assets_cache, required_tf="1m")
                if not choice:
                    rprint(Panel(
                        f"{warning} {yl}No open assets with a positive return at 1m right now.{ENDC}",
                        title=f"{info} {PURPLE}Assets{ENDC}", border_style="yellow"
                    ))
                    await asyncio.sleep(30)
                    continue

                asset_sym, tf_key, live_payout = choice

                # Confirm payout via API (source of truth).
                payout = await client.get_payout(asset_sym, tf_key)
                rprint(f"{info} {g}Payout on {cy}{asset_sym}{ENDC} ({tf_key}): {ye}{payout}%{ENDC}")

                # Quick candles preview.
                candles_df = await client.get_candles_dataframe(asset_sym, tf_key, count=10)
                print_candles_table(candles_df, asset_sym, tf_key)

                # --- Test CALL order ---
                logger.info(f"Placing test order ({asset_sym} CALL $1 / 1m)...")
                order_id = None
                try:
                    order = await client.place_order(asset_sym, amount=1.0, direction=OrderDirection.CALL, duration=60)
                    order_id = order.order_id
                    rprint(f"{info} {cy}Order Placed: {ye}{order.order_id} {w}- {g}{order.status.value}{ENDC}")
                except Exception as e:
                    logger.error(f"Failed to place order: {e}", exc_info=True)
                    msg = str(e).lower()
                    if "not_money" in msg or "insufficient" in msg:
                        rprint(Panel(
                            f"{error} Insufficient funds: {r}{str(e)}{ENDC}",
                            title=f"{info} {r}Order Error{ENDC}", border_style="red"
                        ))
                    else:
                        rprint(Panel(
                            f"{error}Order placement failed: {r}{str(e)}{ENDC}",
                            title=f"{info} {r}Order Error{ENDC}", border_style="red"
                        ))
                    await asyncio.sleep(10)
                    continue

                # Show the result (also display a background panel task) Either wait and print safely:
                if order_id:
                    profit, status = await client.check_win(order_id)
                    if status is None:
                        rprint(Panel(
                            f"{error}{r}No result received for order {order_id}{ENDC}",
                            title=f"{r}Trade Result{ENDC}",
                            border_style="red"
                        ))
                    else:
                        safe_status = (status or "unknown").upper()
                        profit_val = profit if profit is not None else 0.0
                        rprint(f"{info} {ye}[ Trade {order_id} ] ↔ Status: {safe_status} | Profit: ${profit_val:.2f}{ENDC}")

                # --- Test PUT order ---
                order = await client.place_order(asset=asset_sym, amount=1.0, direction=OrderDirection.PUT, duration=60)
                order_id = order.order_id
                rprint(f"{info} {DARK_GRAY}Order placed with ID: {ye}{order_id}{ENDC}")
                profit, status = await client.check_win(order_id)
                rprint(f"{info} {DARK_GRAY}Order result: {ye}{status.upper()}, {DARK_GRAY}Profit: {g}${profit:.2f}{ENDC}")

                # Wait before the next iteration.
                logger.info("Sleeping 60 seconds before next iteration...")
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in main loop: {e}", exc_info=True)
                if "decode" in str(e).lower():
                    rprint(Panel(
                        f"{error} {DARK_GRAY}Message decoding error: {r}{str(e)}{ENDC}",
                        title=f"{info} {r}Main Loop Error{ENDC}", border_style="red"
                    ))
                logger.info("Retrying in 10 seconds...")
                await asyncio.sleep(10)
                continue

    except KeyboardInterrupt:
        logger.info("Stopping due to user interrupt...")
    finally:
        try:
            if client:
                await client.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
