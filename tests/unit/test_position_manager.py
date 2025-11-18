"""
Unit tests for position manager.
"""
import pytest
from decimal import Decimal
from datetime import datetime
from src.managers.position_manager import PositionManager
from src.utils.fee_calculator import FeeCalculator
from src.utils.models import Fill, OrderSide


class TestPositionManager:
    """Test position manager functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.fee_calculator = FeeCalculator()
        self.manager = PositionManager(fee_calculator=self.fee_calculator)

    def test_initial_state(self):
        """Test initial position manager state."""
        assert self.manager.get_inventory_usd() == Decimal("0")
        assert self.manager.get_position("BTC") is None
        assert len(self.manager.get_active_trades()) == 0

    def test_update_position_from_buy_fill(self):
        """Test updating position from buy fill."""
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

        self.manager.update_position_from_fill(fill)

        position = self.manager.get_position("BTC")
        assert position is not None
        assert position.side == OrderSide.BUY
        assert position.quantity == Decimal("0.001")
        assert position.entry_price == Decimal("40000")

    def test_update_position_from_sell_fill(self):
        """Test updating position from sell fill."""
        fill = Fill(
            fill_id="fill_1",
            order_id="order_1",
            symbol="BTC",
            side=OrderSide.SELL,
            price=Decimal("40000"),
            quantity=Decimal("0.001"),
            fee=Decimal("0.01"),
            timestamp=datetime.utcnow(),
            is_maker=True,
        )

        self.manager.update_position_from_fill(fill)

        position = self.manager.get_position("BTC")
        assert position is not None
        assert position.side == OrderSide.SELL
        assert position.quantity == Decimal("0.001")

    def test_position_flattening(self):
        """Test position flattening when buying and selling."""
        # Buy
        buy_fill = Fill(
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
        self.manager.update_position_from_fill(buy_fill)

        # Sell same quantity
        sell_fill = Fill(
            fill_id="fill_2",
            order_id="order_2",
            symbol="BTC",
            side=OrderSide.SELL,
            price=Decimal("40100"),
            quantity=Decimal("0.001"),
            fee=Decimal("0.01"),
            timestamp=datetime.utcnow(),
            is_maker=True,
        )
        self.manager.update_position_from_fill(sell_fill)

        # Position should be flat
        position = self.manager.get_position("BTC")
        assert position is None

    def test_start_trade_execution(self):
        """Test starting a trade execution."""
        entry_fill = Fill(
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

        trade = self.manager.start_trade_execution(
            symbol="BTC",
            entry_fill=entry_fill,
            target_spread_bps=Decimal("6.0"),
        )

        assert trade is not None
        assert trade.symbol == "BTC"
        assert trade.status == "pending_hedge"
        assert len(self.manager.get_active_trades()) == 1

    def test_complete_trade_execution(self):
        """Test completing a trade execution."""
        # Start trade
        entry_fill = Fill(
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

        trade = self.manager.start_trade_execution(
            symbol="BTC",
            entry_fill=entry_fill,
            target_spread_bps=Decimal("6.0"),
        )

        # Complete with hedge
        hedge_fill = Fill(
            fill_id="fill_2",
            order_id="order_2",
            symbol="BTC",
            side=OrderSide.SELL,
            price=Decimal("40030"),  # Profitable
            quantity=Decimal("0.001"),
            fee=Decimal("0.01"),
            timestamp=datetime.utcnow(),
            is_maker=True,
        )

        self.manager.complete_trade_execution(
            trade_id=trade.trade_id,
            hedge_fill=hedge_fill,
        )

        # Should move to completed
        assert len(self.manager.get_active_trades()) == 0
        assert len(self.manager.get_completed_trades()) == 1

        # Check metrics updated
        metrics = self.manager.get_metrics()
        assert metrics.total_trades == 1

    def test_calculate_unrealized_pnl(self):
        """Test unrealized PnL calculation."""
        # Open position
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
        self.manager.update_position_from_fill(fill)

        # Calculate PnL at higher price
        current_price = Decimal("40100")
        pnl = self.manager.calculate_unrealized_pnl("BTC", current_price)

        # (40100 - 40000) * 0.001 = 0.1
        expected = Decimal("0.1")
        assert pnl == expected

    def test_inventory_tracking(self):
        """Test inventory tracking."""
        # Buy fill
        buy_fill = Fill(
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
        self.manager.update_position_from_fill(buy_fill)

        # Inventory should be positive (long)
        inventory = self.manager.get_inventory_usd()
        assert inventory == Decimal("40")  # 40000 * 0.001

    def test_performance_metrics(self):
        """Test performance metrics tracking."""
        metrics = self.manager.get_metrics()

        assert metrics.total_trades == 0
        assert metrics.successful_trades == 0
        assert metrics.net_profit == Decimal("0")
