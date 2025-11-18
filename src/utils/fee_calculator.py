"""
Fee calculation and profitability validation for Hyperliquid trading.
"""
from decimal import Decimal
from typing import Tuple
import structlog

logger = structlog.get_logger(__name__)


class FeeCalculator:
    """
    Calculates fees and validates trade profitability.

    Hyperliquid Fee Structure:
    - Maker Fee: Typically -0.00026 to 0.00035 (varies by tier)
    - Taker Fee: 0.035% to 0.06%

    For this system, we assume:
    - Maker Fee: 0.026% per side (conservative estimate)
    - Roundtrip Fee: 0.052%
    """

    def __init__(
        self,
        maker_fee_bps: Decimal = Decimal("2.6"),  # 0.026%
        taker_fee_bps: Decimal = Decimal("35"),   # 0.35%
    ):
        """
        Initialize fee calculator.

        Args:
            maker_fee_bps: Maker fee in basis points (default: 2.6 bps = 0.026%)
            taker_fee_bps: Taker fee in basis points (default: 35 bps = 0.35%)
        """
        self.maker_fee_bps = maker_fee_bps
        self.taker_fee_bps = taker_fee_bps
        self.maker_fee_decimal = maker_fee_bps / Decimal("10000")
        self.taker_fee_decimal = taker_fee_bps / Decimal("10000")

        logger.info(
            "fee_calculator_initialized",
            maker_fee_bps=float(maker_fee_bps),
            taker_fee_bps=float(taker_fee_bps),
        )

    def calculate_maker_fee(self, notional: Decimal) -> Decimal:
        """
        Calculate maker fee for a trade.

        Args:
            notional: Notional value of the trade (price * quantity)

        Returns:
            Fee amount in USD
        """
        return notional * self.maker_fee_decimal

    def calculate_taker_fee(self, notional: Decimal) -> Decimal:
        """
        Calculate taker fee for a trade.

        Args:
            notional: Notional value of the trade (price * quantity)

        Returns:
            Fee amount in USD
        """
        return notional * self.taker_fee_decimal

    def calculate_roundtrip_fee(self, notional: Decimal, both_maker: bool = True) -> Decimal:
        """
        Calculate total fee for a roundtrip trade (entry + exit).

        Args:
            notional: Notional value of the trade
            both_maker: If True, both legs are maker orders. If False, one is taker.

        Returns:
            Total fee for roundtrip
        """
        if both_maker:
            # Both legs are maker orders
            return self.calculate_maker_fee(notional) * Decimal("2")
        else:
            # One maker, one taker
            return self.calculate_maker_fee(notional) + self.calculate_taker_fee(notional)

    def minimum_profitable_spread_bps(self, both_maker: bool = True) -> Decimal:
        """
        Calculate minimum spread required to be profitable after fees.

        Args:
            both_maker: If True, both legs are maker orders

        Returns:
            Minimum spread in basis points
        """
        if both_maker:
            # Roundtrip maker fee: 0.026% * 2 = 0.052%
            min_spread = self.maker_fee_bps * Decimal("2")
        else:
            # One maker + one taker
            min_spread = self.maker_fee_bps + self.taker_fee_bps

        # Add small buffer for safety (0.01% = 1 bps)
        buffer_bps = Decimal("1.0")
        return min_spread + buffer_bps

    def calculate_required_hedge_offset(
        self,
        entry_price: Decimal,
        entry_side: str,
        safety_margin_bps: Decimal = Decimal("1.0"),
    ) -> Tuple[Decimal, Decimal]:
        """
        Calculate required hedge price to ensure profitability.

        Args:
            entry_price: Price at which entry order was filled
            entry_side: Side of entry order ("buy" or "sell")
            safety_margin_bps: Additional safety margin in bps (default: 1 bps)

        Returns:
            Tuple of (hedge_price, offset_bps)
        """
        # Calculate minimum offset needed
        min_offset_bps = self.minimum_profitable_spread_bps(both_maker=True)
        total_offset_bps = min_offset_bps + safety_margin_bps

        # Convert to decimal
        offset_decimal = total_offset_bps / Decimal("10000")

        if entry_side.lower() == "buy":
            # Entry was a buy, hedge is a sell at higher price
            hedge_price = entry_price * (Decimal("1") + offset_decimal)
        else:
            # Entry was a sell, hedge is a buy at lower price
            hedge_price = entry_price * (Decimal("1") - offset_decimal)

        return hedge_price, total_offset_bps

    def validate_trade_profitability(
        self,
        entry_price: Decimal,
        exit_price: Decimal,
        quantity: Decimal,
        entry_side: str,
    ) -> Tuple[bool, Decimal]:
        """
        Validate if a trade cycle is profitable after fees.

        Args:
            entry_price: Entry fill price
            exit_price: Exit/hedge fill price
            quantity: Trade quantity
            entry_side: Side of entry trade ("buy" or "sell")

        Returns:
            Tuple of (is_profitable, net_profit)
        """
        # Calculate notional
        entry_notional = entry_price * quantity
        exit_notional = exit_price * quantity

        # Calculate fees
        entry_fee = self.calculate_maker_fee(entry_notional)
        exit_fee = self.calculate_maker_fee(exit_notional)
        total_fees = entry_fee + exit_fee

        # Calculate gross profit
        if entry_side.lower() == "buy":
            # Bought at entry_price, sold at exit_price
            gross_profit = exit_notional - entry_notional
        else:
            # Sold at entry_price, bought at exit_price
            gross_profit = entry_notional - exit_notional

        # Calculate net profit
        net_profit = gross_profit - total_fees

        is_profitable = net_profit > Decimal("0")

        logger.info(
            "trade_profitability_check",
            entry_price=float(entry_price),
            exit_price=float(exit_price),
            quantity=float(quantity),
            entry_side=entry_side,
            gross_profit=float(gross_profit),
            total_fees=float(total_fees),
            net_profit=float(net_profit),
            is_profitable=is_profitable,
        )

        return is_profitable, net_profit

    def calculate_spread_bps(self, price1: Decimal, price2: Decimal) -> Decimal:
        """
        Calculate spread between two prices in basis points.

        Args:
            price1: First price
            price2: Second price

        Returns:
            Spread in basis points
        """
        spread = abs(price2 - price1)
        mid_price = (price1 + price2) / Decimal("2")
        spread_bps = (spread / mid_price) * Decimal("10000")
        return spread_bps

    def adjust_spread_for_volatility(
        self,
        base_spread_bps: Decimal,
        volatility_estimate: Decimal,
        volatility_multiplier: Decimal = Decimal("1.5"),
    ) -> Decimal:
        """
        Adjust spread based on market volatility.

        Args:
            base_spread_bps: Base spread in basis points
            volatility_estimate: Estimated volatility (e.g., recent price std dev)
            volatility_multiplier: Multiplier to apply during high volatility

        Returns:
            Adjusted spread in basis points
        """
        # Simple volatility adjustment: widen spread when volatility is high
        # If volatility > 0.1%, increase spread
        volatility_threshold = Decimal("0.001")  # 0.1%

        if volatility_estimate > volatility_threshold:
            adjusted_spread = base_spread_bps * volatility_multiplier
        else:
            adjusted_spread = base_spread_bps

        # Ensure adjusted spread is still above minimum
        min_spread = self.minimum_profitable_spread_bps()
        return max(adjusted_spread, min_spread)
