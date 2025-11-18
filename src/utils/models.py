"""
Data models for the market making system.
"""
from decimal import Decimal
from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class OrderSide(str, Enum):
    """Order side enum."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type enum."""
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(str, Enum):
    """Order status enum."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class Order(BaseModel):
    """Order model."""
    order_id: Optional[str] = None
    client_order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    price: Decimal
    quantity: Decimal
    filled_quantity: Decimal = Decimal("0")
    status: OrderStatus = OrderStatus.PENDING
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator('price', 'quantity', 'filled_quantity', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert string/float to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class Fill(BaseModel):
    """Fill event model."""
    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    price: Decimal
    quantity: Decimal
    fee: Decimal
    timestamp: datetime
    is_maker: bool = True

    @field_validator('price', 'quantity', 'fee', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert string/float to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class Position(BaseModel):
    """Position model."""
    symbol: str
    side: OrderSide
    quantity: Decimal
    entry_price: Decimal
    current_price: Decimal
    unrealized_pnl: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")

    @field_validator('quantity', 'entry_price', 'current_price', 'unrealized_pnl', 'realized_pnl', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert string/float to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class TradeExecution(BaseModel):
    """Complete trade cycle (entry + hedge)."""
    trade_id: str
    symbol: str
    entry_fill: Fill
    hedge_order: Optional[Order] = None
    hedge_fill: Optional[Fill] = None
    target_spread_bps: Decimal
    actual_spread_bps: Optional[Decimal] = None
    gross_profit: Optional[Decimal] = None
    total_fees: Decimal
    net_profit: Optional[Decimal] = None
    entry_timestamp: datetime
    hedge_timestamp: Optional[datetime] = None
    completion_timestamp: Optional[datetime] = None
    status: str = "pending_hedge"

    @field_validator('target_spread_bps', 'actual_spread_bps', 'gross_profit', 'total_fees', 'net_profit', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert string/float to Decimal."""
        if v is None:
            return v
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class MarketData(BaseModel):
    """Market data snapshot."""
    symbol: str
    bid: Decimal
    ask: Decimal
    mid: Decimal
    spread_bps: Decimal
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator('bid', 'ask', 'mid', 'spread_bps', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert string/float to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class Balance(BaseModel):
    """Account balance."""
    account: str
    currency: str = "USD"
    total: Decimal
    available: Decimal
    locked: Decimal = Decimal("0")
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @field_validator('total', 'available', 'locked', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert string/float to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v


class PerformanceMetrics(BaseModel):
    """Performance tracking metrics."""
    total_trades: int = 0
    successful_trades: int = 0
    failed_trades: int = 0
    total_volume_usd: Decimal = Decimal("0")
    total_fees_paid: Decimal = Decimal("0")
    gross_profit: Decimal = Decimal("0")
    net_profit: Decimal = Decimal("0")
    average_spread_captured_bps: Decimal = Decimal("0")
    average_hedge_latency_ms: Decimal = Decimal("0")
    fill_rate: Decimal = Decimal("0")
    uptime_seconds: int = 0
    circuit_breaker_activations: int = 0

    @field_validator('total_volume_usd', 'total_fees_paid', 'gross_profit', 'net_profit',
                     'average_spread_captured_bps', 'average_hedge_latency_ms', 'fill_rate', mode='before')
    @classmethod
    def convert_to_decimal(cls, v):
        """Convert string/float to Decimal."""
        if isinstance(v, (str, float, int)):
            return Decimal(str(v))
        return v
