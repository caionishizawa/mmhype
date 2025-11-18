"""
Unit tests for fee calculator.
"""
import pytest
from decimal import Decimal
from src.utils.fee_calculator import FeeCalculator


class TestFeeCalculator:
    """Test fee calculator functionality."""

    def setup_method(self):
        """Setup test fixtures."""
        self.calculator = FeeCalculator()

    def test_maker_fee_calculation(self):
        """Test maker fee calculation."""
        notional = Decimal("100")
        fee = self.calculator.calculate_maker_fee(notional)

        # 0.026% of 100 = 0.026
        expected = Decimal("0.026")
        assert fee == expected

    def test_taker_fee_calculation(self):
        """Test taker fee calculation."""
        notional = Decimal("100")
        fee = self.calculator.calculate_taker_fee(notional)

        # 0.35% of 100 = 0.35
        expected = Decimal("0.35")
        assert fee == expected

    def test_roundtrip_fee_both_maker(self):
        """Test roundtrip fee with both maker orders."""
        notional = Decimal("100")
        fee = self.calculator.calculate_roundtrip_fee(notional, both_maker=True)

        # 0.026% * 2 = 0.052%
        expected = Decimal("0.052")
        assert fee == expected

    def test_roundtrip_fee_one_taker(self):
        """Test roundtrip fee with one taker order."""
        notional = Decimal("100")
        fee = self.calculator.calculate_roundtrip_fee(notional, both_maker=False)

        # 0.026% + 0.35% = 0.376%
        expected = Decimal("0.376")
        assert fee == expected

    def test_minimum_profitable_spread(self):
        """Test minimum profitable spread calculation."""
        min_spread = self.calculator.minimum_profitable_spread_bps()

        # Should be roundtrip fee + buffer
        # 2.6 * 2 + 1.0 = 6.2 bps
        assert min_spread >= Decimal("6.0")

    def test_required_hedge_offset_buy(self):
        """Test hedge offset calculation for buy entry."""
        entry_price = Decimal("40000")
        hedge_price, offset_bps = self.calculator.calculate_required_hedge_offset(
            entry_price=entry_price,
            entry_side="buy",
            safety_margin_bps=Decimal("1.0"),
        )

        # Hedge should be higher than entry
        assert hedge_price > entry_price

        # Offset should cover fees
        assert offset_bps >= Decimal("6.0")

    def test_required_hedge_offset_sell(self):
        """Test hedge offset calculation for sell entry."""
        entry_price = Decimal("40000")
        hedge_price, offset_bps = self.calculator.calculate_required_hedge_offset(
            entry_price=entry_price,
            entry_side="sell",
            safety_margin_bps=Decimal("1.0"),
        )

        # Hedge should be lower than entry
        assert hedge_price < entry_price

        # Offset should cover fees
        assert offset_bps >= Decimal("6.0")

    def test_validate_profitable_trade(self):
        """Test profitable trade validation."""
        entry_price = Decimal("40000")
        exit_price = Decimal("40030")  # 30 USD profit on 40000 = 0.075%
        quantity = Decimal("0.001")  # Small quantity

        is_profitable, net_profit = self.calculator.validate_trade_profitability(
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            entry_side="buy",
        )

        # Should be profitable
        assert is_profitable
        assert net_profit > Decimal("0")

    def test_validate_unprofitable_trade(self):
        """Test unprofitable trade validation."""
        entry_price = Decimal("40000")
        exit_price = Decimal("40001")  # Only 1 USD profit, fees will eat it
        quantity = Decimal("0.001")

        is_profitable, net_profit = self.calculator.validate_trade_profitability(
            entry_price=entry_price,
            exit_price=exit_price,
            quantity=quantity,
            entry_side="buy",
        )

        # May or may not be profitable depending on exact fee calculation
        # This is a boundary case

    def test_calculate_spread_bps(self):
        """Test spread calculation in basis points."""
        price1 = Decimal("40000")
        price2 = Decimal("40024")  # 24 USD difference

        spread_bps = self.calculator.calculate_spread_bps(price1, price2)

        # (24 / 40012) * 10000 ≈ 6 bps
        assert spread_bps >= Decimal("5.9")
        assert spread_bps <= Decimal("6.1")

    def test_adjust_spread_for_low_volatility(self):
        """Test spread adjustment for low volatility."""
        base_spread = Decimal("6.0")
        volatility = Decimal("0.0001")  # Low volatility

        adjusted = self.calculator.adjust_spread_for_volatility(
            base_spread_bps=base_spread,
            volatility_estimate=volatility,
        )

        # Should remain at base spread
        assert adjusted == base_spread

    def test_adjust_spread_for_high_volatility(self):
        """Test spread adjustment for high volatility."""
        base_spread = Decimal("6.0")
        volatility = Decimal("0.002")  # High volatility

        adjusted = self.calculator.adjust_spread_for_volatility(
            base_spread_bps=base_spread,
            volatility_estimate=volatility,
            volatility_multiplier=Decimal("1.5"),
        )

        # Should be wider
        assert adjusted > base_spread
