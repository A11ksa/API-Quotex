"""Pydantic models for type safety and validation in Quotex API"""
import time
import uuid
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum

class OrderDirection(str, Enum):
    CALL = "call"
    PUT = "put"

class OrderStatus(Enum):
    PENDING = "pending"
    ACTIVE  = "active"
    OPEN    = "open"
    CLOSED  = "closed"
    CANCELLED = "cancelled"
    WIN     = "win"
    LOSS    = "loss"
    DRAW    = "draw"

class ConnectionStatus(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    RECONNECTING = "reconnecting"

class TimeFrame(int, Enum):
    S1 = 1
    S5 = 5
    S10 = 10
    S15 = 15
    S30 = 30
    M1 = 60
    M2 = 120
    M3 = 180
    M5 = 300
    M10 = 600
    M15 = 900
    M30 = 1800
    M45 = 2700
    H1 = 3600
    H2 = 7200
    H3 = 10800
    H4 = 14400

class Asset(BaseModel):
    id: int
    symbol: str
    name: str
    type: str
    payout: int
    is_otc: bool
    is_open: bool
    available_timeframes: List[int] = Field(default=[30, 60, 120, 180, 300, 600, 900, 1800, 2700, 3600, 7200, 10800, 14400])
    is_active: bool = True
    class Config:
        frozen = True

class Balance(BaseModel):
    balance: float
    currency: str = "USD"
    is_demo: bool = True
    last_updated: datetime = Field(default_factory=datetime.now)
    class Config:
        frozen = True

class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None
    asset: str
    timeframe: int
    class Config:
        frozen = True

class Order(BaseModel):
    asset: str
    amount: float
    direction: OrderDirection
    duration: int
    request_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    option_type: int = 100
    class Config:
        frozen = True

class OrderResult(BaseModel):
    order_id: str
    broker_order_id: Optional[str] = None
    asset: Optional[str] = None
    amount: Optional[float] = None
    direction: Optional[OrderDirection] = None
    duration: Optional[int] = None
    status: Optional[OrderStatus] = None
    placed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    open_price: Optional[float] = None
    close_price: Optional[float] = None
    profit: Optional[float] = None
    payout: Optional[float] = None
    error_message: Optional[str] = None
    latest_price: Optional[float] = None
    uid: Optional[int] = None
    class Config:
        frozen = True

class ServerTime(BaseModel):
    server_timestamp: float
    local_timestamp: float
    offset: float
    last_sync: datetime = Field(default_factory=datetime.now)
    class Config:
        frozen = True

class ConnectionInfo(BaseModel):
    url: str
    region: str
    status: ConnectionStatus
    connected_at: Optional[datetime] = None
    last_ping: Optional[datetime] = None
    reconnect_attempts: int = 0
    class Config:
        frozen = True
