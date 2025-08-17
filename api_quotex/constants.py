"""Constants and configuration for the Quotex API."""
import time
import random
from loguru import logger
from typing import List, Dict, Any, Optional

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

ASSETS: Dict[str, int] = {
    "ADAUSD_otc": 376,
    "APTUSD_otc": 377,
    "ARBUSD_otc": 378,
    "ATOUSD_otc": 368,
    "AUDCAD": 36,
    "AUDCAD_otc": 67,
    "AUDCHF": 37,
    "AUDCHF_otc": 68,
    "AUDJPY": 38,
    "AUDJPY_otc": 69,
    "AUDNZD": 39,
    "AUDNZD_otc": 70,
    "AUDUSD": 40,
    "AUDUSD_otc": 71,
    "AXJAUD": 315,
    "AXP_otc": 291,
    "BA_otc": 292,
    "BCHUSD_otc": 363,
    "BNBUSD_otc": 362,
    "BONUSD_otc": 358,
    "BRLUSD_otc": 332,
    "BTCUSD_otc": 352,
    "CADCHF": 41,
    "CADCHF_otc": 72,
    "CADJPY": 42,
    "CADJPY_otc": 73,
    "CHFJPY": 43,
    "CHFJPY_otc": 74,
    "CHIA50": 328,
    "DJIUSD": 317,
    "DOGUSD_otc": 353,
    "ETHUSD_otc": 360,
    "EURAUD": 44,
    "EURAUD_otc": 75,
    "EURCAD": 45,
    "EURCAD_otc": 76,
    "EURCHF": 46,
    "EURCHF_otc": 77,
    "EURGBP": 47,
    "EURGBP_otc": 78,
    "EURJPY": 48,
    "EURJPY_otc": 79,
    "EURNZD": 49,
    "EURNZD_otc": 80,
    "EURSGD": 123,
    "EURSGD_otc": 303,
    "EURUSD": 1,
    "EURUSD_otc": 66,
    "F40EUR": 318,
    "FB_otc": 187,
    "FLOUSD_otc": 356,
    "FTSGBP": 319,
    "GBPAUD": 51,
    "GBPAUD_otc": 81,
    "GBPCAD": 52,
    "GBPCAD_otc": 82,
    "GBPCHF": 53,
    "GBPCHF_otc": 83,
    "GBPJPY": 54,
    "GBPJPY_otc": 84,
    "GBPUSD": 56,
    "GBPUSD_otc": 86,
    "GEREUR": 316,
    "HSIHKD": 320,
    "IBXEUR": 321,
    "INTC_otc": 190,
    "IT4EUR": 326,
    "JNJ_otc": 296,
    "JPXJPY": 327,
    "MCD_otc": 175,
    "MSFT_otc": 176,
    "NDXUSD": 322,
    "NZDJPY": 58,
    "NZDJPY_otc": 89,
    "NZDUSD": 60,
    "NZDUSD_otc": 90,
    "PFE_otc": 297,
    "SPXUSD": 323,
    "STXEUR": 325,
    "UKBrent_otc": 164,
    "USCrude_otc": 165,
    "USDCAD": 61,
    "USDCAD_otc": 91,
    "USDCHF": 62,
    "USDCHF_otc": 92,
    "USDJPY": 63,
    "USDJPY_otc": 93,
    "XAGUSD": 65,
    "XAGUSD_otc": 167,
    "XAUUSD": 2,
    "XAUUSD_otc": 169,
    "XRPUSD_otc": 364,
    "AVAUSD_otc": 379,
    "AXSUSD_otc": 380,
}

def update_assets_from_api(api_assets: List[Dict[str, Any]]) -> None:
    global ASSETS
    new_assets: Dict[str, int] = {}
    for asset_data in api_assets:
        symbol = str(asset_data.get("symbol"))
        asset_id = int(asset_data.get("id", 0))
        if symbol and asset_id:
            new_assets[symbol] = asset_id
    ASSETS.update(new_assets)
    logger.info(f"Updated ASSETS dictionary with {len(new_assets)} assets")

class Regions:
    _REGIONS: Dict[str, str] = {
        "DEMO": "wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket",
        "LIVE": "wss://ws2.qxbroker.com/socket.io/?EIO=3&transport=websocket",
    }

    @classmethod
    def get_all(cls, randomize: bool = True) -> List[str]:
        urls = list(cls._REGIONS.values())
        if randomize:
            random.shuffle(urls)
        return urls

    @classmethod
    def get_all_regions(cls) -> Dict[str, str]:
        return cls._REGIONS.copy()

    @classmethod
    def get_region(cls, region_name: str) -> Optional[str]:
        return cls._REGIONS.get(region_name.upper())

    @classmethod
    def get_demo_regions(cls) -> List[str]:
        return [url for name, url in cls._REGIONS.items() if "DEMO" in name]

REGIONS = Regions()

TIMEFRAMES: Dict[str, int] = {
    "30s": 30,
    "1m": 60,
    "2m": 120,
    "3m": 180,
    "5m": 300,
    "10m": 600,
    "15m": 900,
    "30m": 1800,
    "45m": 2700,
    "1h": 3600,
    "2h": 7200,
    "3h": 10800,
    "4h": 14400,
}

CONNECTION_SETTINGS: Dict[str, float] = {
    "ping_interval": 25.0,
    "ping_timeout": 5.0,
    "close_timeout": 10.0,
    "max_reconnect_attempts": 5,
    "reconnect_initial_delay": 1.0,
    "reconnect_max_delay": 15.0,
    "reconnect_factor": 1.8,
    "handshake_timeout": 10.0,
    "receive_timeout": 30.0,
    "tick_interval": 15.0,
    "message_timeout": 60.0,
}

API_LIMITS: Dict[str, float] = {
    "min_order_amount": 1.0,
    "max_order_amount": 50000.0,
    "min_duration": 30,
    "max_duration": 14400,
    "max_concurrent_orders": 10,
    "rate_limit": 100,
}

DEFAULT_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Origin": "https://qxbroker.com",
    "Referer": "https://qxbroker.com/",
    "Accept-Language": "en-US,en;q=0.9",
}
