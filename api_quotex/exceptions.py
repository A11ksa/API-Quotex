"""Custom exceptions for the Quotex API"""
import time
from loguru import logger

logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

class QuotexError(Exception):
    def __init__(self, message: str, error_code: str = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        logger.error(f"QuotexError: {message} (Code: {error_code})")

class ConnectionError(QuotexError):
    pass

class AuthenticationError(QuotexError):
    pass

class OrderError(QuotexError):
    pass

class TimeoutError(QuotexError):
    pass

class InvalidParameterError(QuotexError):
    pass

class WebSocketError(QuotexError):
    pass

class AssetError(QuotexError):
    pass

class InsufficientFundsError(QuotexError):
    def __init__(self, message: str = "Insufficient funds for order", error_code: str = "not_money"):
        super().__init__(message, error_code)

class Base64DecodeError(QuotexError):
    def __init__(self, message: str = "Failed to decode base64 message", error_code: str = "base64_decode"):
        super().__init__(message, error_code)
