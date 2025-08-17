"""Configuration file for the async Quotex API"""
import os
import json
import time
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, Optional
from loguru import logger
from threading import Lock
logger.remove()
log_filename = f"log-{time.strftime('%Y-%m-%d')}.txt"
logger.add(log_filename, level="INFO", encoding="utf-8", backtrace=True, diagnose=True)

@dataclass
class ConnectionConfig:
    ping_interval: int = 25
    ping_timeout: int = 5
    close_timeout: int = 10
    max_reconnect_attempts: int = 5
    reconnect_delay: int = 5
    message_timeout: int = 30

@dataclass
class TradingConfig:
    min_order_amount: float = 1.0
    max_order_amount: float = 50000.0
    min_duration: int = 30
    max_duration: int = 14400
    max_concurrent_orders: int = 10
    default_timeout: float = 30.0

@dataclass
class LoggingConfig:
    level: str = "INFO"
    format: str = ("{time:YYYY-MM-DD HH:mm:ss} | {level} | {name}:{function}:{line} | {message}")
    rotation: str = "1 day"
    retention: str = "7 days"
    log_file: str = f"log-{time.strftime('%Y-%m-%d')}.txt"

class Config:
    _instance = None
    _lock = Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
            return cls._instance

    def __init__(self, resource_path: str = "sessions"):
        if hasattr(self, '_initialized') and self._initialized:
            logger.debug("Config instance already initialized, skipping redundant initialization")
            return
        self.resource_path = Path(resource_path)
        self.config_file = self.resource_path / "config.json"
        self.session_file = self.resource_path / "session.json"
        self.connection = ConnectionConfig()
        self.trading = TradingConfig()
        self.logging = LoggingConfig()
        self.session_data: Dict[str, Any] = {
            "user_agent": None,
            "cookies": None,
            "token": None
        }
        self._config_data: Dict[str, Any] = {
            "email": None,
            "password": None,
            "lang": "en",
            "user_data_dir": "."
        }
        self._session_loaded = False
        self._config_loaded = False
        self.resource_path.mkdir(parents=True, exist_ok=True)
        self._load_from_env()
        self._load_config()
        self._load_session()
        self._initialized = True
        logger.info("Config instance initialized successfully")

    def _load_from_env(self):
        try:
            self.connection.ping_interval = int(os.getenv("PING_INTERVAL", self.connection.ping_interval))
            self.connection.ping_timeout = int(os.getenv("PING_TIMEOUT", self.connection.ping_timeout))
            self.connection.max_reconnect_attempts = int(os.getenv("MAX_RECONNECT_ATTEMPTS", self.connection.max_reconnect_attempts))
            self.trading.min_order_amount = float(os.getenv("MIN_ORDER_AMOUNT", self.trading.min_order_amount))
            self.trading.max_order_amount = float(os.getenv("MAX_ORDER_AMOUNT", self.trading.max_order_amount))
            self.trading.default_timeout = float(os.getenv("DEFAULT_TIMEOUT", self.trading.default_timeout))
            self.logging.level = os.getenv("LOG_LEVEL", self.logging.level)
            self.logging.log_file = os.getenv("LOG_FILE", self.logging.log_file)
            logger.debug("Environment variables loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load environment variables: {str(e)}")

    def _load_config(self) -> None:
        with self._lock:
            try:
                if self._config_loaded:
                    logger.debug("Configuration already loaded, skipping")
                    return
                if self.config_file.exists():
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        self._config_data.update(json.load(f))
                    logger.info("Configuration loaded from config.json")
                else:
                    logger.warning("config.json not found, using default configuration")
                self._config_loaded = True
            except Exception as e:
                logger.error(f"Failed to load config.json: {str(e)}")
                self._config_data = {
                    "email": None,
                    "password": None,
                    "lang": "en",
                    "user_data_dir": "."
                }
                self._config_loaded = True

    def _load_session(self) -> None:
        with self._lock:
            if self._session_loaded:
                logger.debug("Session already loaded, skipping")
                return
            try:
                if self.session_file.exists():
                    # Check file age (14 days)
                    file_mtime = os.path.getmtime(self.session_file)
                    current_time = time.time()
                    fourteen_days = 14 * 24 * 60 * 60  # 14 days in seconds
                    if (current_time - file_mtime) > fourteen_days:
                        logger.warning("Session file is older than 14 days, removing")
                        os.remove(self.session_file)
                        self.session_data = {
                            "user_agent": None,
                            "cookies": None,
                            "token": None
                        }
                    else:
                        with open(self.session_file, "r", encoding="utf-8") as f:
                            self.session_data.update(json.load(f))
                        logger.info("Session data loaded from session.json")
                else:
                    logger.warning("session.json not found, using default session data")
                    self.session_data = {
                        "user_agent": None,
                        "cookies": None,
                        "token": None
                    }
                self._session_loaded = True
            except Exception as e:
                logger.error(f"Failed to load session.json: {str(e)}")
                self.session_data = {
                    "user_agent": None,
                    "cookies": None,
                    "token": None
                }
                self._session_loaded = True

    def load_config(self) -> Dict[str, Any]:
        self._load_config()
        return self._config_data.copy()

    def save_config(self, config: Dict[str, Any]) -> None:
        with self._lock:
            try:
                if self._config_data != config:
                    self._config_data.update(config)
                    with open(self.config_file, "w", encoding="utf-8") as f:
                        json.dump(self._config_data, f, indent=4)
                    logger.info("Configuration saved to config.json")
                else:
                    logger.debug("No changes in config data, skipping save")
            except Exception as e:
                logger.error(f"Failed to save config.json: {str(e)}")

    def save_session(self, session_data: Dict[str, Any]) -> None:
        with self._lock:
            try:
                if self.session_data != session_data:
                    self.session_data.update(session_data)
                    with open(self.session_file, "w", encoding="utf-8") as f:
                        json.dump(self.session_data, f, indent=4)
                    logger.info("Session data saved to session.json")
                    self._session_loaded = True
                else:
                    logger.debug("No changes in session data, skipping save")
            except Exception as e:
                logger.error(f"Failed to save session.json: {str(e)}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "connection": {
                "ping_interval": self.connection.ping_interval,
                "ping_timeout": self.connection.ping_timeout,
                "close_timeout": self.connection.close_timeout,
                "max_reconnect_attempts": self.connection.max_reconnect_attempts,
                "reconnect_delay": self.connection.reconnect_delay,
                "message_timeout": self.connection.message_timeout,
            },
            "trading": {
                "min_order_amount": self.trading.min_order_amount,
                "max_order_amount": self.trading.max_order_amount,
                "min_duration": self.trading.min_duration,
                "max_duration": self.trading.max_duration,
                "max_concurrent_orders": self.trading.max_concurrent_orders,
                "default_timeout": self.trading.default_timeout,
            },
            "logging": {
                "level": self.logging.level,
                "format": self.logging.format,
                "rotation": self.logging.rotation,
                "retention": self.logging.retention,
                "log_file": self.logging.log_file,
            },
            "user": self._config_data,
            "session": self.session_data
        }

    @property
    def lang(self) -> str:
        return self._config_data.get("lang", "en")

    @property
    def user_data_dir(self) -> str:
        return self._config_data.get("user_data_dir", ".")

# Global configuration instance
config = Config()
