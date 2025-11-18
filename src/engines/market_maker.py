"""
Market making engine - continuous liquidity provision.
"""
import asyncio
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import structlog

from ..connectors.hyperliquid_connector import HyperliquidConnector
from ..utils.config import TradingConfig
from ..utils.models import Order, OrderSide, MarketData
from ..utils.fee_calculator import FeeCalculator
from ..risk.risk_controller import RiskController
from ..managers.position_manager import PositionManager

logger = structlog.get_logger(__name__)


class MarketMaker:
    """
    Market making engine for continuous liquidity provision.

    Responsibilities:
    - Calculate optimal bid/ask prices
    - Place and maintain orders at multiple levels
    - Refresh orders periodically
    - Adapt spreads based on volatility
    """

    def __init__(
        self,
        config: TradingConfig,
        connector: HyperliquidConnector,
        fee_calculator: FeeCalculator,
        risk_controller: RiskController,
        position_manager: PositionManager,
    ):
        """
        Initialize market maker.

        Args:
            config: Trading configuration
            connector: Exchange connector
            fee_calculator: Fee calculator
            risk_controller: Risk controller
            position_manager: Position manager
        """
        self.config = config
        self.connector = connector
        self.fee_calculator = fee_calculator
        self.risk_controller = risk_controller
        self.position_manager = position_manager

        # Active orders tracking
        self.active_orders: Dict[str, Order] = {}

        # Market data
        self.current_market_data: Optional[MarketData] = None

        # Control flags
        self.running = False
        self.paused = False

        # Price precision (Hyperliquid specific)
        self.price_decimals = 1  # Adjust based on symbol
        self.size_decimals = 4

        logger.info("market_maker_initialized", symbol=config.symbol)

    async def start(self):
        """Start the market making loop."""
        self.running = True

        logger.info("market_maker_started", symbol=self.config.symbol)

        # Start main loop
        await self._market_making_loop()

    async def stop(self):
        """Stop the market making loop."""
        self.running = False

        # Cancel all orders
        await self.cancel_all_orders()

        logger.info("market_maker_stopped")

    def pause(self):
        """Pause market making (stop placing new orders)."""
        self.paused = True
        logger.info("market_maker_paused")

    def resume(self):
        """Resume market making."""
        self.paused = False
        logger.info("market_maker_resumed")

    async def _market_making_loop(self):
        """Main market making loop."""
        while self.running:
            try:
                # Check if paused or circuit breaker active
                if self.paused or self.risk_controller.is_circuit_breaker_active():
                    await asyncio.sleep(1)
                    continue

                # Get current market price
                mid_price = await self._get_mid_price()

                if mid_price is None:
                    logger.warning("failed_to_get_market_price")
                    await asyncio.sleep(self.config.refresh_interval_ms / 1000)
                    continue

                # Calculate optimal quotes
                quotes = self._calculate_quotes(mid_price)

                # Place or update orders
                await self._manage_orders(quotes)

                # Remove stale orders
                await self._remove_stale_orders()

                # Wait for next refresh
                await asyncio.sleep(self.config.refresh_interval_ms / 1000)

            except Exception as e:
                logger.error("market_making_loop_error", error=str(e))
                self.risk_controller.record_failure()
                await asyncio.sleep(5)  # Back off on error

    async def _get_mid_price(self) -> Optional[Decimal]:
        """
        Get current mid price from market.

        Returns:
            Mid price or None if unavailable
        """
        try:
            # In a real implementation, this would fetch from market data
            # For now, we'll use a placeholder
            # You should implement this to fetch from Hyperliquid's market data API

            # Placeholder: fetch best bid/ask
            # This is a simplified version - implement proper market data fetching
            position = await self.connector.get_position(self.config.symbol)

            if position:
                # Use position's current price as reference
                current_price = Decimal(
                    position.get("position", {}).get("entryPx", "0")
                )
                if current_price > Decimal("0"):
                    return current_price

            # Fallback: use a default price (ONLY FOR TESTING)
            # In production, you MUST fetch real market data
            logger.warning("using_fallback_price")
            return Decimal("40000")  # Placeholder for BTC

        except Exception as e:
            logger.error("failed_to_fetch_mid_price", error=str(e))
            return None

    def _calculate_quotes(self, mid_price: Decimal) -> List[Dict]:
        """
        Calculate bid and ask quotes at multiple levels.

        Args:
            mid_price: Current mid price

        Returns:
            List of quote dictionaries
        """
        quotes = []

        # Get base spread
        base_spread_bps = self.config.base_spread_bps

        # Adjust for volatility if needed
        # TODO: Implement volatility calculation
        volatility = Decimal("0")
        adjusted_spread_bps = self.fee_calculator.adjust_spread_for_volatility(
            base_spread_bps, volatility, self.config.volatility_multiplier
        )

        # Ensure spread meets minimum profitable requirement
        min_spread_bps = self.fee_calculator.minimum_profitable_spread_bps()
        spread_bps = max(adjusted_spread_bps, min_spread_bps)

        # Convert spread to decimal
        spread_decimal = spread_bps / Decimal("10000")

        # Calculate quantity from notional
        quantity = self.config.order_notional_usd / mid_price
        quantity = self._round_size(quantity)

        # Generate quotes at multiple levels
        for level in range(self.config.num_levels):
            # Increase spread for each level
            level_spread = spread_decimal * (Decimal("1") + Decimal(str(level)) * Decimal("0.5"))

            # Calculate bid and ask prices
            bid_price = mid_price * (Decimal("1") - level_spread)
            ask_price = mid_price * (Decimal("1") + level_spread)

            # Round to tick size
            bid_price = self._round_price(bid_price)
            ask_price = self._round_price(ask_price)

            quotes.append({
                "side": OrderSide.BUY,
                "price": bid_price,
                "quantity": quantity,
                "level": level,
            })

            quotes.append({
                "side": OrderSide.SELL,
                "price": ask_price,
                "quantity": quantity,
                "level": level,
            })

        logger.debug(
            "quotes_calculated",
            mid_price=float(mid_price),
            spread_bps=float(spread_bps),
            num_quotes=len(quotes),
        )

        return quotes

    def _round_price(self, price: Decimal) -> Decimal:
        """
        Round price to exchange tick size.

        Args:
            price: Raw price

        Returns:
            Rounded price
        """
        # Hyperliquid tick sizes vary by price level
        # Simplified rounding - adjust based on actual requirements
        if price >= Decimal("10000"):
            tick_size = Decimal("1")
        elif price >= Decimal("1000"):
            tick_size = Decimal("0.1")
        else:
            tick_size = Decimal("0.01")

        return (price / tick_size).quantize(Decimal("1")) * tick_size

    def _round_size(self, size: Decimal) -> Decimal:
        """
        Round size to exchange lot size.

        Args:
            size: Raw size

        Returns:
            Rounded size
        """
        # Round to size decimals
        quantizer = Decimal("1e-{}".format(self.size_decimals))
        return size.quantize(quantizer)

    async def _manage_orders(self, quotes: List[Dict]):
        """
        Place or update orders based on quotes.

        Args:
            quotes: List of quote dictionaries
        """
        # Get current orders
        existing_orders = {
            f"{o.side.value}_{o.price}": o for o in self.active_orders.values()
        }

        # Check which quotes need new orders
        for quote in quotes:
            key = f"{quote['side'].value}_{quote['price']}"

            if key not in existing_orders:
                # Need to place new order
                await self._place_order(
                    quote["side"], quote["price"], quote["quantity"]
                )

    async def _place_order(
        self, side: OrderSide, price: Decimal, quantity: Decimal
    ) -> Optional[Order]:
        """
        Place a new limit order.

        Args:
            side: Order side
            price: Limit price
            quantity: Order quantity

        Returns:
            Order object or None if failed
        """
        try:
            # Create order object
            client_order_id = f"{self.config.symbol}_{side.value}_{int(datetime.utcnow().timestamp() * 1000)}"

            order = Order(
                client_order_id=client_order_id,
                symbol=self.config.symbol,
                side=side,
                order_type="limit",
                price=price,
                quantity=quantity,
            )

            # Validate with risk controller
            is_valid, error = self.risk_controller.validate_order(order)

            if not is_valid:
                logger.warning(
                    "order_rejected_by_risk_controller",
                    side=side.value,
                    price=float(price),
                    reason=error,
                )
                return None

            # Place order via connector
            start_time = datetime.utcnow()

            placed_order = await self.connector.place_order(
                symbol=self.config.symbol,
                side=side,
                price=price,
                quantity=quantity,
                post_only=True,
            )

            # Record latency
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.risk_controller.record_latency(latency_ms)

            # Track order
            self.active_orders[placed_order.order_id] = placed_order

            self.risk_controller.record_success()

            logger.info(
                "order_placed",
                order_id=placed_order.order_id,
                side=side.value,
                price=float(price),
                quantity=float(quantity),
                latency_ms=latency_ms,
            )

            return placed_order

        except Exception as e:
            logger.error(
                "order_placement_failed",
                side=side.value,
                price=float(price),
                error=str(e),
            )
            self.risk_controller.record_failure()
            return None

    async def _remove_stale_orders(self):
        """Remove orders that exceed TTL."""
        now = datetime.utcnow()
        ttl = timedelta(seconds=self.config.max_order_ttl_seconds)

        stale_orders = [
            order
            for order in self.active_orders.values()
            if now - order.timestamp > ttl
        ]

        for order in stale_orders:
            await self._cancel_order(order.order_id)

    async def _cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if successful
        """
        try:
            if order_id not in self.active_orders:
                return False

            order = self.active_orders[order_id]

            await self.connector.cancel_order(self.config.symbol, order_id)

            # Remove from active orders
            del self.active_orders[order_id]

            logger.info("order_cancelled", order_id=order_id)

            return True

        except Exception as e:
            logger.error("order_cancellation_failed", order_id=order_id, error=str(e))
            return False

    async def cancel_all_orders(self) -> bool:
        """
        Cancel all active orders.

        Returns:
            True if successful
        """
        try:
            await self.connector.cancel_all_orders(self.config.symbol)

            self.active_orders.clear()

            logger.info("all_orders_cancelled", symbol=self.config.symbol)

            return True

        except Exception as e:
            logger.error("cancel_all_orders_failed", error=str(e))
            return False

    def remove_filled_order(self, order_id: str):
        """
        Remove a filled order from active orders.

        Args:
            order_id: Order ID that was filled
        """
        if order_id in self.active_orders:
            del self.active_orders[order_id]
            logger.info("filled_order_removed", order_id=order_id)

    def get_active_orders(self) -> List[Order]:
        """
        Get list of active orders.

        Returns:
            List of active orders
        """
        return list(self.active_orders.values())
