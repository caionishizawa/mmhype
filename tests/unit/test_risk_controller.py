"""
Unit tests for risk controller.
"""
import pytest
from decimal import Decimal
from datetime import datetime
from src.risk.risk_controller import RiskController
from src.utils.config import RiskConfig
from src.utils.fee_calculator import FeeCalculator
from src.managers.position_manager import PositionManager
from src.utils.models import Order, Fill, OrderSide


class TestRiskController:
    """Test risk controller functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.config = RiskConfig()
        self.fee_calculator = FeeCalculator()
        self.position_manager = PositionManager(fee_calculator=self.fee_calculator)
        self.controller = RiskController(
            config=self.config,
            position_manager=self.position_manager,
        )

    def test_initial_state(self):
        """Test initial risk controller state."""
        assert not self.controller.is_circuit_breaker_active()
        assert self.controller.consecutive_failures == 0

    def test_validate_order_within_limits(self):
        """Test order validation within risk limits."""
        order = Order(
            client_order_id="test_1",
            symbol="BTC",
            side=OrderSide.BUY,
            order_type="limit",
            price=Decimal("40000"),
            quantity=Decimal("0.0001"),  # Very small, within limits
        )

        is_valid, error = self.controller.validate_order(order)
        assert is_valid
        assert error is None

    def test_validate_order_exceeds_inventory(self):
        """Test order validation exceeding inventory limit."""
        # Large order that exceeds max_inventory_usd (5.0)
        order = Order(
            client_order_id="test_1",
            symbol="BTC",
            side=OrderSide.BUY,
            order_type="limit",
            price=Decimal("40000"),
            quantity=Decimal("1.0"),  # 40,000 USD notional
        )

        is_valid, error = self.controller.validate_order(order)
        assert not is_valid
        assert "Inventory limit exceeded" in error

    def test_record_failure(self):
        """Test failure recording."""
        initial = self.controller.consecutive_failures

        self.controller.record_failure()

        assert self.controller.consecutive_failures == initial + 1

    def test_record_success(self):
        """Test success recording resets failures."""
        self.controller.consecutive_failures = 5

        self.controller.record_success()

        assert self.controller.consecutive_failures == 0

    def test_circuit_breaker_on_max_failures(self):
        """Test circuit breaker activates on max failures."""
        # Record failures up to limit
        for _ in range(self.config.max_consecutive_failures):
            self.controller.record_failure()

        assert self.controller.is_circuit_breaker_active()

    def test_record_fill_and_hedge(self):
        """Test recording fills and hedges."""
        fill = Fill(
            fill_id="fill_1",
            order_id="order_1",
            symbol="BTC",
            side=OrderSide.BUY,
            price=Decimal("40000"),
            quantity=Decimal("0.001"),
            fee=Decimal("0.01"),
            timestamp=datetime.utcnow(),
            is_maker=True,
        )

        self.controller.record_fill(fill)

        # Should have unhedged position
        assert len(self.controller.unhedged_positions) == 1

        # Record hedge
        self.controller.record_hedge("fill_1")

        # Should clear unhedged position
        assert len(self.controller.unhedged_positions) == 0

    def test_latency_recording(self):
        """Test latency recording."""
        self.controller.record_latency(100.0)
        self.controller.record_latency(150.0)
        self.controller.record_latency(120.0)

        avg = self.controller.get_average_latency_ms()
        assert avg > 0
        assert avg == pytest.approx(123.33, rel=0.1)

    def test_high_latency_circuit_breaker(self):
        """Test circuit breaker on sustained high latency."""
        # Record many high latency samples
        for _ in range(10):
            self.controller.record_latency(1000.0)  # Very high

        # Should activate circuit breaker
        assert self.controller.is_circuit_breaker_active()

    def test_activate_circuit_breaker(self):
        """Test manual circuit breaker activation."""
        self.controller.activate_circuit_breaker("Test reason")

        assert self.controller.is_circuit_breaker_active()
        assert self.controller.circuit_breaker_reason == "Test reason"

    def test_circuit_breaker_prevents_orders(self):
        """Test circuit breaker prevents order validation."""
        self.controller.activate_circuit_breaker("Test")

        order = Order(
            client_order_id="test_1",
            symbol="BTC",
            side=OrderSide.BUY,
            order_type="limit",
            price=Decimal("40000"),
            quantity=Decimal("0.0001"),
        )

        is_valid, error = self.controller.validate_order(order)
        assert not is_valid
        assert "Circuit breaker active" in error

    def test_risk_summary(self):
        """Test risk summary generation."""
        summary = self.controller.get_risk_summary()

        assert "circuit_breaker_active" in summary
        assert "consecutive_failures" in summary
        assert "daily_loss_usd" in summary
        assert "inventory_usd" in summary

    def test_update_daily_pnl(self):
        """Test daily PnL tracking."""
        # Record a loss
        self.controller.update_daily_pnl(Decimal("-2.0"))

        assert self.controller.daily_loss_usd == Decimal("2.0")

        # Record a profit (should not affect loss tracking)
        self.controller.update_daily_pnl(Decimal("1.0"))

        assert self.controller.daily_loss_usd == Decimal("2.0")
