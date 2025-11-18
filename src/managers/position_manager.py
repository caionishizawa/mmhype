"""
Position and PnL management.
"""
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime
import structlog

from ..utils.models import (
    Fill,
    Position,
    TradeExecution,
    OrderSide,
    PerformanceMetrics,
)
from ..utils.fee_calculator import FeeCalculator

logger = structlog.get_logger(__name__)


class PositionManager:
    """
    Manages positions, tracks PnL, and maintains trade history.
    """

    def __init__(self, fee_calculator: FeeCalculator):
        """
        Initialize position manager.

        Args:
            fee_calculator: Fee calculator instance
        """
        self.fee_calculator = fee_calculator

        # Current positions by symbol
        self.positions: Dict[str, Position] = {}

        # Trade execution tracking
        self.active_trades: Dict[str, TradeExecution] = {}
        self.completed_trades: List[TradeExecution] = []

        # Performance metrics
        self.metrics = PerformanceMetrics()

        # Inventory tracking
        self.inventory_usd: Decimal = Decimal("0")  # Net inventory in USD

        logger.info("position_manager_initialized")

    def get_position(self, symbol: str) -> Optional[Position]:
        """
        Get current position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position or None if no position
        """
        return self.positions.get(symbol)

    def update_position_from_fill(self, fill: Fill):
        """
        Update position based on a fill.

        Args:
            fill: Fill event
        """
        symbol = fill.symbol

        if symbol not in self.positions:
            # New position
            self.positions[symbol] = Position(
                symbol=symbol,
                side=fill.side,
                quantity=fill.quantity,
                entry_price=fill.price,
                current_price=fill.price,
            )
        else:
            # Existing position - update
            pos = self.positions[symbol]

            if fill.side == pos.side:
                # Adding to position
                total_quantity = pos.quantity + fill.quantity
                weighted_price = (
                    (pos.entry_price * pos.quantity) + (fill.price * fill.quantity)
                ) / total_quantity

                pos.quantity = total_quantity
                pos.entry_price = weighted_price
            else:
                # Reducing or reversing position
                pos.quantity -= fill.quantity

                if pos.quantity < Decimal("0"):
                    # Position reversed
                    pos.quantity = abs(pos.quantity)
                    pos.side = fill.side
                    pos.entry_price = fill.price
                elif pos.quantity == Decimal("0"):
                    # Position closed
                    del self.positions[symbol]
                    return

            pos.current_price = fill.price

        # Update inventory
        self._update_inventory()

        logger.info(
            "position_updated",
            symbol=symbol,
            side=self.positions[symbol].side.value if symbol in self.positions else None,
            quantity=float(self.positions[symbol].quantity) if symbol in self.positions else 0,
        )

    def _update_inventory(self):
        """Calculate total inventory in USD."""
        total = Decimal("0")

        for pos in self.positions.values():
            notional = pos.quantity * pos.current_price
            if pos.side == OrderSide.BUY:
                total += notional
            else:
                total -= notional

        self.inventory_usd = total

    def get_inventory_usd(self) -> Decimal:
        """Get current inventory in USD."""
        return self.inventory_usd

    def calculate_unrealized_pnl(self, symbol: str, current_price: Decimal) -> Decimal:
        """
        Calculate unrealized PnL for a position.

        Args:
            symbol: Trading symbol
            current_price: Current market price

        Returns:
            Unrealized PnL
        """
        if symbol not in self.positions:
            return Decimal("0")

        pos = self.positions[symbol]
        pos.current_price = current_price

        if pos.side == OrderSide.BUY:
            pnl = (current_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - current_price) * pos.quantity

        pos.unrealized_pnl = pnl

        return pnl

    def start_trade_execution(
        self,
        symbol: str,
        entry_fill: Fill,
        target_spread_bps: Decimal,
    ) -> TradeExecution:
        """
        Start tracking a new trade execution cycle.

        Args:
            symbol: Trading symbol
            entry_fill: Entry fill event
            target_spread_bps: Target spread in basis points

        Returns:
            TradeExecution object
        """
        trade_id = f"{symbol}_{entry_fill.fill_id}"

        # Calculate entry fee
        entry_notional = entry_fill.price * entry_fill.quantity
        entry_fee = self.fee_calculator.calculate_maker_fee(entry_notional)

        trade = TradeExecution(
            trade_id=trade_id,
            symbol=symbol,
            entry_fill=entry_fill,
            target_spread_bps=target_spread_bps,
            total_fees=entry_fee,
            entry_timestamp=entry_fill.timestamp,
            status="pending_hedge",
        )

        self.active_trades[trade_id] = trade

        logger.info(
            "trade_execution_started",
            trade_id=trade_id,
            symbol=symbol,
            entry_side=entry_fill.side.value,
            entry_price=float(entry_fill.price),
            entry_quantity=float(entry_fill.quantity),
        )

        return trade

    def complete_trade_execution(
        self,
        trade_id: str,
        hedge_fill: Fill,
    ):
        """
        Complete a trade execution with hedge fill.

        Args:
            trade_id: Trade ID
            hedge_fill: Hedge fill event
        """
        if trade_id not in self.active_trades:
            logger.error("trade_not_found", trade_id=trade_id)
            return

        trade = self.active_trades[trade_id]

        # Update trade with hedge information
        trade.hedge_fill = hedge_fill
        trade.hedge_timestamp = hedge_fill.timestamp
        trade.completion_timestamp = datetime.utcnow()
        trade.status = "completed"

        # Calculate hedge fee
        hedge_notional = hedge_fill.price * hedge_fill.quantity
        hedge_fee = self.fee_calculator.calculate_maker_fee(hedge_notional)
        trade.total_fees += hedge_fee

        # Calculate actual spread
        entry_price = trade.entry_fill.price
        hedge_price = hedge_fill.price
        actual_spread_bps = self.fee_calculator.calculate_spread_bps(
            entry_price, hedge_price
        )
        trade.actual_spread_bps = actual_spread_bps

        # Calculate profit
        is_profitable, net_profit = self.fee_calculator.validate_trade_profitability(
            entry_price=entry_price,
            exit_price=hedge_price,
            quantity=trade.entry_fill.quantity,
            entry_side=trade.entry_fill.side.value,
        )

        entry_notional = entry_price * trade.entry_fill.quantity
        hedge_notional = hedge_price * hedge_fill.quantity

        if trade.entry_fill.side == OrderSide.BUY:
            gross_profit = hedge_notional - entry_notional
        else:
            gross_profit = entry_notional - hedge_notional

        trade.gross_profit = gross_profit
        trade.net_profit = net_profit

        # Move to completed trades
        self.completed_trades.append(trade)
        del self.active_trades[trade_id]

        # Update metrics
        self._update_metrics(trade)

        logger.info(
            "trade_execution_completed",
            trade_id=trade_id,
            actual_spread_bps=float(actual_spread_bps),
            gross_profit=float(gross_profit),
            net_profit=float(net_profit),
            total_fees=float(trade.total_fees),
            is_profitable=is_profitable,
        )

    def _update_metrics(self, trade: TradeExecution):
        """
        Update performance metrics with completed trade.

        Args:
            trade: Completed trade execution
        """
        self.metrics.total_trades += 1

        if trade.net_profit > Decimal("0"):
            self.metrics.successful_trades += 1
        else:
            self.metrics.failed_trades += 1

        # Update volume and fees
        entry_notional = trade.entry_fill.price * trade.entry_fill.quantity
        self.metrics.total_volume_usd += entry_notional
        self.metrics.total_fees_paid += trade.total_fees

        # Update profit
        self.metrics.gross_profit += trade.gross_profit or Decimal("0")
        self.metrics.net_profit += trade.net_profit or Decimal("0")

        # Update average spread
        if trade.actual_spread_bps:
            current_avg = self.metrics.average_spread_captured_bps
            n = Decimal(str(self.metrics.total_trades))
            new_avg = (current_avg * (n - Decimal("1")) + trade.actual_spread_bps) / n
            self.metrics.average_spread_captured_bps = new_avg

        # Update hedge latency
        if trade.hedge_timestamp and trade.entry_timestamp:
            latency_ms = (
                trade.hedge_timestamp - trade.entry_timestamp
            ).total_seconds() * 1000
            current_avg = self.metrics.average_hedge_latency_ms
            n = Decimal(str(self.metrics.total_trades))
            new_avg = (current_avg * (n - Decimal("1")) + Decimal(str(latency_ms))) / n
            self.metrics.average_hedge_latency_ms = new_avg

    def get_metrics(self) -> PerformanceMetrics:
        """
        Get current performance metrics.

        Returns:
            PerformanceMetrics object
        """
        # Calculate fill rate
        if self.metrics.total_trades > 0:
            self.metrics.fill_rate = Decimal(
                str(self.metrics.successful_trades)
            ) / Decimal(str(self.metrics.total_trades))

        return self.metrics

    def get_active_trades(self) -> List[TradeExecution]:
        """
        Get list of active trade executions.

        Returns:
            List of active trades
        """
        return list(self.active_trades.values())

    def get_completed_trades(
        self, limit: Optional[int] = None
    ) -> List[TradeExecution]:
        """
        Get list of completed trades.

        Args:
            limit: Maximum number of trades to return (most recent)

        Returns:
            List of completed trades
        """
        trades = sorted(
            self.completed_trades,
            key=lambda t: t.completion_timestamp,
            reverse=True,
        )

        if limit:
            return trades[:limit]

        return trades

    def get_position_summary(self) -> Dict:
        """
        Get summary of all positions.

        Returns:
            Dictionary with position summary
        """
        return {
            "positions": {
                symbol: {
                    "side": pos.side.value,
                    "quantity": float(pos.quantity),
                    "entry_price": float(pos.entry_price),
                    "current_price": float(pos.current_price),
                    "unrealized_pnl": float(pos.unrealized_pnl),
                }
                for symbol, pos in self.positions.items()
            },
            "inventory_usd": float(self.inventory_usd),
            "active_trades": len(self.active_trades),
            "completed_trades": len(self.completed_trades),
        }

    def reset_daily_metrics(self):
        """Reset daily metrics (call at start of each day)."""
        # Keep cumulative metrics, reset daily ones
        # For now, we don't have specific daily metrics
        # This can be extended if needed
        logger.info("daily_metrics_reset")
