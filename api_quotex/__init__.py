"""
Professional Async API Quotex - Core module
Fully async implementation with modern Python practices
"""
from .client import AsyncQuotexClient
from .exceptions import (
    QuotexError,
    ConnectionError,
    AuthenticationError,
    OrderError,
    TimeoutError,
    InvalidParameterError,
    WebSocketError,
    InsufficientFundsError,
)
from .models import (
    Balance,
    Candle,
    Order,
    OrderResult,
    OrderStatus,
    OrderDirection,
    Asset,
    ConnectionStatus,
)
from .constants import ASSETS, REGIONS, TIMEFRAMES
from .login import get_ssid, load_config, save_config
# Import monitoring components
from .monitoring import (
    ErrorMonitor,
    HealthChecker,
    ErrorSeverity,
    ErrorCategory,
    CircuitBreaker,
    RetryPolicy,
    error_monitor,
    health_checker,
)
# Use the REGIONS instance directly
__version__ = "2.0.0"
__author__ = "APIQuotex"
__all__ = [
    "AsyncQuotexClient",
    "QuotexError",
    "ConnectionError",
    "AuthenticationError",
    "OrderError",
    "TimeoutError",
    "InvalidParameterError",
    "WebSocketError",
    "InsufficientFundsError",
    "Balance",
    "Candle",
    "Order",
    "OrderResult",
    "OrderStatus",
    "OrderDirection",
    "Asset",
    "ConnectionStatus",
    "ASSETS",
    "REGIONS",
    "TIMEFRAMES",
    "get_ssid",
    "load_config",
    "save_config",
    # Monitoring and error handling
    "ErrorMonitor",
    "HealthChecker",
    "ErrorSeverity",
    "ErrorCategory",
    "CircuitBreaker",
    "RetryPolicy",
    "error_monitor",
    "health_checker",
]
