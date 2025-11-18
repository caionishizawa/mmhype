"""
Risk management and circuit breaker logic.
"""
from decimal import Decimal
from typing import Optional
from datetime import datetime, timedelta
import structlog

from ..utils.config import RiskConfig
from ..utils.models import Order, Fill, OrderSide
from ..managers.position_manager import PositionManager

logger = structlog.get_logger(__name__)


class RiskController:
    """
    Manages risk limits and circuit breakers.
    """

    def __init__(self, config: RiskConfig, position_manager: PositionManager):
        """
        Initialize risk controller.

        Args:
            config: Risk configuration
            position_manager: Position manager instance
        """
        self.config = config
        self.position_manager = position_manager

        # Circuit breaker state
        self.circuit_breaker_active = False
        self.circuit_breaker_activated_at: Optional[datetime] = None
        self.circuit_breaker_reason: Optional[str] = None

        # Risk tracking
        self.consecutive_failures = 0
        self.daily_loss_usd = Decimal("0")
        self.daily_start = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )

        # Latency tracking
        self.recent_latencies_ms = []
        self.max_latency_samples = 100

        # Unhedged position tracking
        self.unhedged_positions: dict = {}  # {fill_id: timestamp}

        logger.info("risk_controller_initialized", config=config.model_dump())

    def validate_order(self, order: Order) -> tuple[bool, Optional[str]]:
        """
        Validate if an order can be placed based on risk limits.

        Args:
            order: Order to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check circuit breaker
        if self.circuit_breaker_active:
            return False, f"Circuit breaker active: {self.circuit_breaker_reason}"

        # Check inventory limits
        inventory = self.position_manager.get_inventory_usd()
        order_notional = order.price * order.quantity

        if order.side == OrderSide.BUY:
            new_inventory = inventory + order_notional
        else:
            new_inventory = inventory - order_notional

        if abs(new_inventory) > self.config.max_inventory_usd:
            return False, f"Inventory limit exceeded: {float(new_inventory)} > {float(self.config.max_inventory_usd)}"

        # Check position limits
        position = self.position_manager.get_position(order.symbol)
        if position:
            position_notional = position.quantity * position.current_price
            if position_notional > self.config.max_position_notional_usd:
                return False, f"Position notional limit exceeded: {float(position_notional)} > {float(self.config.max_position_notional_usd)}"

        # Check daily loss limit
        if self.daily_loss_usd > self.config.max_daily_loss_usd:
            self.activate_circuit_breaker("Daily loss limit exceeded")
            return False, "Daily loss limit exceeded"

        # All checks passed
        return True, None

    def record_fill(self, fill: Fill):
        """
        Record a fill and track unhedged exposure.

        Args:
            fill: Fill event
        """
        # Add to unhedged positions
        self.unhedged_positions[fill.fill_id] = datetime.utcnow()

        logger.info(
            "fill_recorded",
            fill_id=fill.fill_id,
            symbol=fill.symbol,
            side=fill.side.value,
            unhedged_count=len(self.unhedged_positions),
        )

    def record_hedge(self, entry_fill_id: str):
        """
        Record that a fill has been hedged.

        Args:
            entry_fill_id: Fill ID that was hedged
        """
        if entry_fill_id in self.unhedged_positions:
            del self.unhedged_positions[entry_fill_id]

            logger.info(
                "hedge_recorded",
                fill_id=entry_fill_id,
                unhedged_count=len(self.unhedged_positions),
            )

    def check_unhedged_duration(self) -> bool:
        """
        Check if any unhedged positions exceed max duration.

        Returns:
            True if all positions within limit, False otherwise
        """
        now = datetime.utcnow()
        max_duration = timedelta(seconds=self.config.max_unhedged_duration_seconds)

        for fill_id, timestamp in list(self.unhedged_positions.items()):
            duration = now - timestamp

            if duration > max_duration:
                logger.error(
                    "unhedged_duration_exceeded",
                    fill_id=fill_id,
                    duration_seconds=duration.total_seconds(),
                    max_duration_seconds=self.config.max_unhedged_duration_seconds,
                )
                self.activate_circuit_breaker(
                    f"Unhedged position duration exceeded: {fill_id}"
                )
                return False

        return True

    def record_latency(self, latency_ms: float):
        """
        Record API latency for monitoring.

        Args:
            latency_ms: Latency in milliseconds
        """
        self.recent_latencies_ms.append(latency_ms)

        # Keep only recent samples
        if len(self.recent_latencies_ms) > self.max_latency_samples:
            self.recent_latencies_ms.pop(0)

        # Check latency threshold
        if latency_ms > self.config.latency_threshold_ms:
            logger.warning(
                "high_latency_detected",
                latency_ms=latency_ms,
                threshold_ms=self.config.latency_threshold_ms,
            )

            # Check if sustained high latency
            recent_high_latency = [
                l for l in self.recent_latencies_ms[-10:]
                if l > self.config.latency_threshold_ms
            ]

            if len(recent_high_latency) >= 5:
                self.activate_circuit_breaker("Sustained high latency")

    def get_average_latency_ms(self) -> float:
        """
        Get average latency from recent samples.

        Returns:
            Average latency in milliseconds
        """
        if not self.recent_latencies_ms:
            return 0.0

        return sum(self.recent_latencies_ms) / len(self.recent_latencies_ms)

    def record_failure(self):
        """Record a failed operation (order placement, etc.)."""
        self.consecutive_failures += 1

        logger.warning(
            "failure_recorded",
            consecutive_failures=self.consecutive_failures,
        )

        if self.consecutive_failures >= self.config.max_consecutive_failures:
            self.activate_circuit_breaker(
                f"Too many consecutive failures: {self.consecutive_failures}"
            )

    def record_success(self):
        """Record a successful operation."""
        self.consecutive_failures = 0

    def update_daily_pnl(self, pnl: Decimal):
        """
        Update daily PnL tracking.

        Args:
            pnl: PnL from completed trade
        """
        # Check if new day
        now = datetime.utcnow()
        current_day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if current_day_start > self.daily_start:
            # New day - reset
            self.daily_loss_usd = Decimal("0")
            self.daily_start = current_day_start

        # Update daily loss (only track losses)
        if pnl < Decimal("0"):
            self.daily_loss_usd += abs(pnl)

        logger.info(
            "daily_pnl_updated",
            pnl=float(pnl),
            daily_loss=float(self.daily_loss_usd),
            max_daily_loss=float(self.config.max_daily_loss_usd),
        )

    def check_position_imbalance(self) -> bool:
        """
        Check if position imbalance exceeds threshold.

        Returns:
            True if imbalance is acceptable, False otherwise
        """
        positions = self.position_manager.get_position_summary()["positions"]

        if not positions:
            return True

        # Calculate long and short exposure
        long_exposure = Decimal("0")
        short_exposure = Decimal("0")

        for pos_data in positions.values():
            notional = Decimal(str(pos_data["quantity"])) * Decimal(
                str(pos_data["current_price"])
            )

            if pos_data["side"] == "buy":
                long_exposure += notional
            else:
                short_exposure += notional

        # Calculate imbalance ratio
        total_exposure = long_exposure + short_exposure

        if total_exposure == Decimal("0"):
            return True

        imbalance_ratio = abs(long_exposure - short_exposure) / total_exposure

        if imbalance_ratio > self.config.max_position_imbalance_ratio:
            logger.error(
                "position_imbalance_exceeded",
                imbalance_ratio=float(imbalance_ratio),
                max_ratio=float(self.config.max_position_imbalance_ratio),
                long_exposure=float(long_exposure),
                short_exposure=float(short_exposure),
            )
            self.activate_circuit_breaker("Position imbalance exceeded")
            return False

        return True

    def activate_circuit_breaker(self, reason: str):
        """
        Activate circuit breaker.

        Args:
            reason: Reason for activation
        """
        if self.circuit_breaker_active:
            return  # Already active

        self.circuit_breaker_active = True
        self.circuit_breaker_activated_at = datetime.utcnow()
        self.circuit_breaker_reason = reason

        # Update metrics
        metrics = self.position_manager.get_metrics()
        metrics.circuit_breaker_activations += 1

        logger.error(
            "circuit_breaker_activated",
            reason=reason,
            timestamp=self.circuit_breaker_activated_at.isoformat(),
        )

    def check_circuit_breaker_cooldown(self) -> bool:
        """
        Check if circuit breaker cooldown period has elapsed.

        Returns:
            True if cooldown elapsed and circuit breaker can be reset
        """
        if not self.circuit_breaker_active:
            return False

        now = datetime.utcnow()
        cooldown = timedelta(seconds=self.config.circuit_breaker_cooldown_seconds)

        if now - self.circuit_breaker_activated_at >= cooldown:
            return True

        return False

    def reset_circuit_breaker(self, force: bool = False):
        """
        Reset circuit breaker after cooldown or manual intervention.

        Args:
            force: Force reset without checking cooldown
        """
        if not force and not self.check_circuit_breaker_cooldown():
            logger.warning("circuit_breaker_reset_attempted_during_cooldown")
            return

        self.circuit_breaker_active = False
        self.circuit_breaker_activated_at = None
        self.circuit_breaker_reason = None
        self.consecutive_failures = 0

        logger.info("circuit_breaker_reset")

    def is_circuit_breaker_active(self) -> bool:
        """
        Check if circuit breaker is active.

        Returns:
            True if active
        """
        return self.circuit_breaker_active

    def get_risk_summary(self) -> dict:
        """
        Get summary of current risk status.

        Returns:
            Dictionary with risk information
        """
        return {
            "circuit_breaker_active": self.circuit_breaker_active,
            "circuit_breaker_reason": self.circuit_breaker_reason,
            "consecutive_failures": self.consecutive_failures,
            "daily_loss_usd": float(self.daily_loss_usd),
            "max_daily_loss_usd": float(self.config.max_daily_loss_usd),
            "unhedged_positions_count": len(self.unhedged_positions),
            "average_latency_ms": self.get_average_latency_ms(),
            "inventory_usd": float(self.position_manager.get_inventory_usd()),
            "max_inventory_usd": float(self.config.max_inventory_usd),
        }
