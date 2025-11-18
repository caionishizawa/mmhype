"""
Hedging engine - automatic position hedging.
"""
import asyncio
from decimal import Decimal
from typing import Optional
from datetime import datetime, timedelta
import structlog

from ..connectors.hyperliquid_connector import HyperliquidConnector
from ..utils.config import HedgingConfig
from ..utils.models import Fill, Order, OrderSide
from ..utils.fee_calculator import FeeCalculator
from ..risk.risk_controller import RiskController
from ..managers.position_manager import PositionManager

logger = structlog.get_logger(__name__)


class HedgingEngine:
    """
    Hedging engine for automatic position hedging.

    Responsibilities:
    - Listen to fill events
    - Calculate optimal hedge prices
    - Place counter limit orders
    - Retry failed hedges
    - Track hedge execution
    """

    def __init__(
        self,
        config: HedgingConfig,
        connector: HyperliquidConnector,
        fee_calculator: FeeCalculator,
        risk_controller: RiskController,
        position_manager: PositionManager,
    ):
        """
        Initialize hedging engine.

        Args:
            config: Hedging configuration
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

        # Pending hedges tracking
        self.pending_hedges = {}  # {fill_id: hedge_info}

        # Control flags
        self.running = False

        logger.info("hedging_engine_initialized")

    async def start(self):
        """Start the hedging engine."""
        if not self.config.enabled:
            logger.info("hedging_engine_disabled")
            return

        self.running = True

        # Register fill callback
        self.connector.register_fill_callback(self.on_fill)

        # Start hedge monitoring loop
        asyncio.create_task(self._hedge_monitoring_loop())

        logger.info("hedging_engine_started")

    async def stop(self):
        """Stop the hedging engine."""
        self.running = False

        logger.info("hedging_engine_stopped")

    async def on_fill(self, fill: Fill):
        """
        Handle fill event and initiate hedge.

        Args:
            fill: Fill event
        """
        logger.info(
            "fill_received",
            fill_id=fill.fill_id,
            symbol=fill.symbol,
            side=fill.side.value,
            price=float(fill.price),
            quantity=float(fill.quantity),
        )

        # Record fill with risk controller
        self.risk_controller.record_fill(fill)

        # Update position
        self.position_manager.update_position_from_fill(fill)

        # Start trade execution tracking
        trade = self.position_manager.start_trade_execution(
            symbol=fill.symbol,
            entry_fill=fill,
            target_spread_bps=self.config.hedge_offset_bps,
        )

        # Initiate hedge
        await self._initiate_hedge(fill)

    async def _initiate_hedge(self, entry_fill: Fill):
        """
        Initiate hedge for a fill.

        Args:
            entry_fill: Entry fill to hedge
        """
        try:
            # Calculate hedge parameters
            hedge_side = (
                OrderSide.SELL if entry_fill.side == OrderSide.BUY else OrderSide.BUY
            )

            hedge_price, offset_bps = self.fee_calculator.calculate_required_hedge_offset(
                entry_price=entry_fill.price,
                entry_side=entry_fill.side.value,
                safety_margin_bps=Decimal("1.0"),  # Additional 1 bps safety
            )

            # Round hedge price
            hedge_price = self._round_price(hedge_price)

            logger.info(
                "hedge_calculated",
                entry_fill_id=entry_fill.fill_id,
                entry_price=float(entry_fill.price),
                hedge_price=float(hedge_price),
                offset_bps=float(offset_bps),
                hedge_side=hedge_side.value,
            )

            # Place hedge order
            await self._place_hedge_order(
                entry_fill=entry_fill,
                hedge_side=hedge_side,
                hedge_price=hedge_price,
                quantity=entry_fill.quantity,
                attempt=1,
            )

        except Exception as e:
            logger.error(
                "hedge_initiation_failed",
                fill_id=entry_fill.fill_id,
                error=str(e),
            )

    async def _place_hedge_order(
        self,
        entry_fill: Fill,
        hedge_side: OrderSide,
        hedge_price: Decimal,
        quantity: Decimal,
        attempt: int,
    ):
        """
        Place a hedge order.

        Args:
            entry_fill: Entry fill being hedged
            hedge_side: Side of hedge order
            hedge_price: Hedge limit price
            quantity: Quantity to hedge
            attempt: Attempt number
        """
        try:
            # Check risk limits
            order = Order(
                client_order_id=f"hedge_{entry_fill.fill_id}_{attempt}",
                symbol=entry_fill.symbol,
                side=hedge_side,
                order_type="limit",
                price=hedge_price,
                quantity=quantity,
            )

            is_valid, error = self.risk_controller.validate_order(order)

            if not is_valid:
                logger.error(
                    "hedge_order_rejected",
                    fill_id=entry_fill.fill_id,
                    reason=error,
                )
                return

            # Place hedge order
            start_time = datetime.utcnow()

            hedge_order = await self.connector.place_order(
                symbol=entry_fill.symbol,
                side=hedge_side,
                price=hedge_price,
                quantity=quantity,
                post_only=True,
            )

            # Record latency
            latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            self.risk_controller.record_latency(latency_ms)

            # Track pending hedge
            self.pending_hedges[entry_fill.fill_id] = {
                "entry_fill": entry_fill,
                "hedge_order": hedge_order,
                "hedge_price": hedge_price,
                "placed_at": datetime.utcnow(),
                "attempt": attempt,
            }

            # Register callback for hedge fill
            # In a production system, you would track this via WebSocket
            # For now, we'll monitor in the monitoring loop

            logger.info(
                "hedge_order_placed",
                fill_id=entry_fill.fill_id,
                hedge_order_id=hedge_order.order_id,
                hedge_side=hedge_side.value,
                hedge_price=float(hedge_price),
                attempt=attempt,
                latency_ms=latency_ms,
            )

        except Exception as e:
            logger.error(
                "hedge_order_placement_failed",
                fill_id=entry_fill.fill_id,
                attempt=attempt,
                error=str(e),
            )
            self.risk_controller.record_failure()

            # Retry if within limits
            if attempt < self.config.max_hedge_attempts:
                await self._retry_hedge(entry_fill, attempt + 1)

    async def _retry_hedge(self, entry_fill: Fill, attempt: int):
        """
        Retry hedge with improved pricing.

        Args:
            entry_fill: Entry fill to hedge
            attempt: Retry attempt number
        """
        logger.info(
            "retrying_hedge",
            fill_id=entry_fill.fill_id,
            attempt=attempt,
        )

        # Improve pricing slightly
        hedge_side = (
            OrderSide.SELL if entry_fill.side == OrderSide.BUY else OrderSide.BUY
        )

        # Calculate new hedge price with reduced offset (more aggressive)
        improvement_bps = self.config.retry_price_improvement_bps * Decimal(str(attempt))
        adjusted_offset_bps = max(
            self.config.hedge_offset_bps - improvement_bps,
            self.fee_calculator.minimum_profitable_spread_bps(),
        )

        hedge_price, _ = self.fee_calculator.calculate_required_hedge_offset(
            entry_price=entry_fill.price,
            entry_side=entry_fill.side.value,
            safety_margin_bps=adjusted_offset_bps - self.fee_calculator.minimum_profitable_spread_bps(),
        )

        hedge_price = self._round_price(hedge_price)

        # Wait before retry
        await asyncio.sleep(2 ** (attempt - 1))  # Exponential backoff

        await self._place_hedge_order(
            entry_fill=entry_fill,
            hedge_side=hedge_side,
            hedge_price=hedge_price,
            quantity=entry_fill.quantity,
            attempt=attempt,
        )

    async def _hedge_monitoring_loop(self):
        """Monitor pending hedges and handle timeouts."""
        while self.running:
            try:
                await self._check_pending_hedges()
                await asyncio.sleep(5)  # Check every 5 seconds

            except Exception as e:
                logger.error("hedge_monitoring_error", error=str(e))
                await asyncio.sleep(5)

    async def _check_pending_hedges(self):
        """Check pending hedges for fills or timeouts."""
        now = datetime.utcnow()
        timeout = timedelta(seconds=self.config.hedge_timeout_seconds)

        for fill_id, hedge_info in list(self.pending_hedges.items()):
            try:
                # Check if hedge order is still open
                open_orders = await self.connector.get_open_orders(
                    hedge_info["entry_fill"].symbol
                )

                hedge_order_id = hedge_info["hedge_order"].order_id
                hedge_still_open = any(
                    o.get("oid") == hedge_order_id for o in open_orders
                )

                if not hedge_still_open:
                    # Hedge was filled or cancelled
                    # Check if filled
                    # In production, this should be tracked via WebSocket
                    logger.info(
                        "hedge_completed_or_cancelled",
                        fill_id=fill_id,
                        hedge_order_id=hedge_order_id,
                    )

                    # Assume filled for now
                    # Create a fill object (simplified - should come from WebSocket)
                    hedge_fill = Fill(
                        fill_id=f"hedge_{fill_id}",
                        order_id=hedge_order_id,
                        symbol=hedge_info["entry_fill"].symbol,
                        side=hedge_info["hedge_order"].side,
                        price=hedge_info["hedge_price"],
                        quantity=hedge_info["hedge_order"].quantity,
                        fee=Decimal("0"),  # Would come from actual fill
                        timestamp=datetime.utcnow(),
                        is_maker=True,
                    )

                    # Complete trade execution
                    trade_id = f"{hedge_info['entry_fill'].symbol}_{hedge_info['entry_fill'].fill_id}"
                    self.position_manager.complete_trade_execution(
                        trade_id=trade_id,
                        hedge_fill=hedge_fill,
                    )

                    # Record hedge with risk controller
                    self.risk_controller.record_hedge(fill_id)

                    # Remove from pending
                    del self.pending_hedges[fill_id]

                elif now - hedge_info["placed_at"] > timeout:
                    # Timeout - cancel and retry
                    logger.warning(
                        "hedge_timeout",
                        fill_id=fill_id,
                        hedge_order_id=hedge_order_id,
                        elapsed_seconds=(now - hedge_info["placed_at"]).total_seconds(),
                    )

                    # Cancel order
                    await self.connector.cancel_order(
                        hedge_info["entry_fill"].symbol,
                        hedge_order_id,
                    )

                    # Retry if within limits
                    attempt = hedge_info["attempt"]
                    if attempt < self.config.max_hedge_attempts:
                        await self._retry_hedge(
                            hedge_info["entry_fill"],
                            attempt + 1,
                        )

                    # Remove from pending
                    del self.pending_hedges[fill_id]

            except Exception as e:
                logger.error(
                    "hedge_check_error",
                    fill_id=fill_id,
                    error=str(e),
                )

    def _round_price(self, price: Decimal) -> Decimal:
        """
        Round price to exchange tick size.

        Args:
            price: Raw price

        Returns:
            Rounded price
        """
        # Hyperliquid tick sizes vary by price level
        if price >= Decimal("10000"):
            tick_size = Decimal("1")
        elif price >= Decimal("1000"):
            tick_size = Decimal("0.1")
        else:
            tick_size = Decimal("0.01")

        return (price / tick_size).quantize(Decimal("1")) * tick_size

    def get_pending_hedges_count(self) -> int:
        """
        Get count of pending hedges.

        Returns:
            Number of pending hedges
        """
        return len(self.pending_hedges)
