"""Utility functions for the Quotex API"""
import asyncio
import time
import base64
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import pandas as pd
from .models import Candle, OrderResult
from loguru import logger

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

def format_session_id(session_id: str, is_demo: bool = True, is_fast_history: bool = True) -> str:
    import json
    auth_data = {
        "session": session_id,
        "isDemo": 1 if is_demo else 0,
        "tournamentId": 0,
    }
    if is_fast_history:
        auth_data["isFastHistory"] = True
    return f'42["authorization",{json.dumps(auth_data)}]'

def sanitize_symbol(symbol: str) -> str:
    if not isinstance(symbol, str):
        logger.warning(f"Invalid symbol type: {type(symbol)}, converting to string")
        symbol = str(symbol)
    parts = symbol.strip().split('_')
    base_symbol = parts[0].upper()
    if len(parts) > 1 and parts[1].lower() == 'otc':
        return f"{base_symbol}_otc"
    return base_symbol

def decode_base64_message(message: str) -> Optional[str]:
    try:
        if message.startswith("BFtb"):
            return base64.b64decode(message[4:]).decode("utf-8")
        return message
    except Exception as e:
        logger.error(f"Failed to decode base64 message: {str(e)}")
        return None

def calculate_payout_percentage(entry_price: float, exit_price: float, direction: str, payout_rate: float = 0.8) -> float:
    if direction.lower() == "call":
        win = exit_price > entry_price
    else:
        win = exit_price < entry_price
    return payout_rate if win else -1.0

def analyze_candles(candles: List[Candle]) -> Dict[str, Any]:
    if not candles:
        return {}
    prices = [candle.close for candle in candles]
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    return {
        "count": len(candles),
        "first_price": prices[0],
        "last_price": prices[-1],
        "price_change": prices[-1] - prices[0],
        "price_change_percent": ((prices[-1] - prices[0]) / prices[0]) * 100,
        "highest": max(highs),
        "lowest": min(lows),
        "average_close": sum(prices) / len(prices),
        "volatility": calculate_volatility(prices),
        "trend": determine_trend(prices),
    }

def calculate_volatility(prices: List[float], periods: int = 14) -> float:
    if len(prices) < periods:
        periods = len(prices)
    recent_prices = prices[-periods:]
    mean = sum(recent_prices) / len(recent_prices)
    variance = sum((price - mean) ** 2 for price in recent_prices) / len(recent_prices)
    return variance**0.5

def determine_trend(prices: List[float], periods: int = 10) -> str:
    if len(prices) < periods:
        periods = len(prices)
    if periods < 2:
        return "sideways"
    recent_prices = prices[-periods:]
    first_half = recent_prices[: periods // 2]
    second_half = recent_prices[periods // 2 :]
    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)
    change_percent = ((second_avg - first_avg) / first_avg) * 100
    if change_percent > 0.1:
        return "bullish"
    elif change_percent < -0.1:
        return "bearish"
    else:
        return "sideways"

def calculate_support_resistance(candles: List[Candle], periods: int = 20) -> Dict[str, float]:
    if len(candles) < periods:
        periods = len(candles)
    recent_candles = candles[-periods:]
    highs = [candle.high for candle in recent_candles]
    lows = [candle.low for candle in recent_candles]
    resistance = max(highs)
    support = min(lows)
    return {"support": support, "resistance": resistance, "range": resistance - support}

def format_timeframe(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        return f"{seconds // 3600}h"
    else:
        return f"{seconds // 86400}d"

def validate_asset_symbol(symbol: str, available_assets: Dict[str, int]) -> bool:
    return symbol in available_assets

def calculate_order_expiration(duration_seconds: int, current_time: Optional[datetime] = None) -> datetime:
    if current_time is None:
        current_time = datetime.now()
    return current_time + timedelta(seconds=duration_seconds)

def retry_async(max_attempts: int = 3, delay: float = 1.0, backoff_factor: float = 2.0):
    def decorator(func):
        async def wrapper(*args, **kwargs):
            current_delay = delay
            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_attempts - 1:
                        logger.error(
                            f"Function {func.__name__} failed after {max_attempts} attempts: {e}"
                        )
                        raise
                    logger.warning(
                        f"Attempt {attempt + 1} failed for {func.__name__}: {e}"
                    )
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff_factor
        return wrapper
    return decorator

def performance_monitor(func):
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = await func(*args, **kwargs)
            execution_time = time.time() - start_time
            logger.debug(f"{func.__name__} executed in {execution_time:.3f}s")
            return result
        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"{func.__name__} failed after {execution_time:.3f}s: {e}")
            raise
    return wrapper

class RateLimiter:
    def __init__(self, max_calls: int = 100, time_window: int = 60):
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []

    async def acquire(self) -> bool:
        now = time.time()
        self.calls = [
            call_time for call_time in self.calls if now - call_time < self.time_window
        ]
        if len(self.calls) < self.max_calls:
            self.calls.append(now)
            return True
        wait_time = self.time_window - (now - self.calls[0])
        if wait_time > 0:
            logger.warning(f"Rate limit exceeded, waiting {wait_time:.1f}s")
            await asyncio.sleep(wait_time)
            return await self.acquire()
        return True

class OrderManager:
    def __init__(self):
        self.active_orders: Dict[str, OrderResult] = {}
        self.completed_orders: Dict[str, OrderResult] = {}
        self.order_callbacks: Dict[str, List] = {}

    def add_order(self, order: OrderResult) -> None:
        self.active_orders[order.order_id] = order

    def complete_order(self, order_id: str, result: OrderResult) -> None:
        if order_id in self.active_orders:
            del self.active_orders[order_id]
        self.completed_orders[order_id] = result
        if order_id in self.order_callbacks:
            for callback in self.order_callbacks[order_id]:
                try:
                    callback(result)
                except Exception as e:
                    logger.error(f"Error in order callback: {e}")
            del self.order_callbacks[order_id]

    def add_order_callback(self, order_id: str, callback) -> None:
        if order_id not in self.order_callbacks:
            self.order_callbacks[order_id] = []
        self.order_callbacks[order_id].append(callback)

    def get_order_status(self, order_id: str) -> Optional[OrderResult]:
        if order_id in self.active_orders:
            return self.active_orders[order_id]
        elif order_id in self.completed_orders:
            return self.completed_orders[order_id]
        return None

    def get_active_count(self) -> int:
        return len(self.active_orders)

    def get_completed_count(self) -> int:
        return len(self.completed_orders)

def candles_to_dataframe(candles: List[Candle]) -> pd.DataFrame:
    data = []
    for candle in candles:
        data.append(
            {
                "timestamp": candle.timestamp,
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "asset": candle.asset,
            }
        )
    df = pd.DataFrame(data)
    if not df.empty:
        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
    return df
