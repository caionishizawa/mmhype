"""
Main orchestrator for the Hyperliquid market making system.
"""
import asyncio
import signal
import sys
from pathlib import Path
import structlog

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.config import load_config, load_settings, Config, Settings
from src.utils.logger import setup_logging
from src.utils.fee_calculator import FeeCalculator
from src.connectors.hyperliquid_connector import HyperliquidConnector
from src.managers.position_manager import PositionManager
from src.risk.risk_controller import RiskController
from src.engines.market_maker import MarketMaker
from src.engines.hedging_engine import HedgingEngine

logger = structlog.get_logger(__name__)


class TradingSystem:
    """
    Main trading system orchestrator.

    Coordinates all modules and manages the system lifecycle.
    """

    def __init__(self, config: Config, settings: Settings):
        """
        Initialize trading system.

        Args:
            config: System configuration
            settings: Environment settings
        """
        self.config = config
        self.settings = settings

        # Components (initialized in setup)
        self.connector: HyperliquidConnector = None
        self.fee_calculator: FeeCalculator = None
        self.position_manager: PositionManager = None
        self.risk_controller: RiskController = None
        self.market_maker: MarketMaker = None
        self.hedging_engine: HedgingEngine = None

        # Control flags
        self.running = False
        self.shutdown_event = asyncio.Event()

        logger.info("trading_system_initialized", environment=settings.environment)

    async def setup(self):
        """Initialize all system components."""
        logger.info("setting_up_trading_system")

        # Validate credentials
        if not self.settings.hyperliquid_private_key:
            raise ValueError("HYPERLIQUID_PRIVATE_KEY not set in environment")

        # Determine API URLs
        if self.config.exchange.testnet:
            rest_url = self.config.exchange.testnet_rest_url
            ws_url = self.config.exchange.testnet_ws_url
        else:
            rest_url = self.config.exchange.rest_url
            ws_url = self.config.exchange.ws_url

        # Initialize connector
        self.connector = HyperliquidConnector(
            private_key=self.settings.hyperliquid_private_key,
            rest_url=rest_url,
            ws_url=ws_url,
            vault_address=self.settings.hyperliquid_vault_address,
            subaccount_address=self.settings.hyperliquid_subaccount_address,
        )

        await self.connector.connect()

        # Initialize fee calculator
        self.fee_calculator = FeeCalculator()

        # Initialize position manager
        self.position_manager = PositionManager(fee_calculator=self.fee_calculator)

        # Initialize risk controller
        self.risk_controller = RiskController(
            config=self.config.risk,
            position_manager=self.position_manager,
        )

        # Initialize market maker
        self.market_maker = MarketMaker(
            config=self.config.trading,
            connector=self.connector,
            fee_calculator=self.fee_calculator,
            risk_controller=self.risk_controller,
            position_manager=self.position_manager,
        )

        # Initialize hedging engine
        self.hedging_engine = HedgingEngine(
            config=self.config.hedging,
            connector=self.connector,
            fee_calculator=self.fee_calculator,
            risk_controller=self.risk_controller,
            position_manager=self.position_manager,
        )

        logger.info("trading_system_setup_complete")

    async def start(self):
        """Start the trading system."""
        logger.info("starting_trading_system")

        self.running = True

        # Start hedging engine first (to listen for fills)
        await self.hedging_engine.start()

        # Start market maker
        asyncio.create_task(self.market_maker.start())

        # Start monitoring loops
        asyncio.create_task(self._risk_monitoring_loop())
        asyncio.create_task(self._performance_reporting_loop())

        logger.info("trading_system_started")

    async def stop(self):
        """Stop the trading system."""
        logger.info("stopping_trading_system")

        self.running = False

        # Stop market maker
        await self.market_maker.stop()

        # Stop hedging engine
        await self.hedging_engine.stop()

        # Disconnect from exchange
        await self.connector.disconnect()

        logger.info("trading_system_stopped")

    async def _risk_monitoring_loop(self):
        """Monitor risk metrics and circuit breakers."""
        while self.running:
            try:
                # Check unhedged duration
                self.risk_controller.check_unhedged_duration()

                # Check position imbalance
                self.risk_controller.check_position_imbalance()

                # Check circuit breaker cooldown
                if self.risk_controller.is_circuit_breaker_active():
                    if self.risk_controller.check_circuit_breaker_cooldown():
                        logger.info("circuit_breaker_cooldown_elapsed")
                        # Don't auto-reset - require manual intervention
                        # self.risk_controller.reset_circuit_breaker()

                # Log risk summary
                risk_summary = self.risk_controller.get_risk_summary()
                logger.debug("risk_summary", **risk_summary)

                await asyncio.sleep(10)  # Check every 10 seconds

            except Exception as e:
                logger.error("risk_monitoring_error", error=str(e))
                await asyncio.sleep(10)

    async def _performance_reporting_loop(self):
        """Report performance metrics periodically."""
        while self.running:
            try:
                await asyncio.sleep(60)  # Report every minute

                # Get metrics
                metrics = self.position_manager.get_metrics()
                position_summary = self.position_manager.get_position_summary()

                logger.info(
                    "performance_report",
                    total_trades=metrics.total_trades,
                    successful_trades=metrics.successful_trades,
                    failed_trades=metrics.failed_trades,
                    net_profit=float(metrics.net_profit),
                    average_spread_bps=float(metrics.average_spread_captured_bps),
                    average_hedge_latency_ms=float(metrics.average_hedge_latency_ms),
                    inventory_usd=position_summary["inventory_usd"],
                    active_trades=position_summary["active_trades"],
                )

            except Exception as e:
                logger.error("performance_reporting_error", error=str(e))
                await asyncio.sleep(60)

    async def run(self):
        """Run the trading system until shutdown."""
        try:
            await self.setup()
            await self.start()

            # Wait for shutdown signal
            await self.shutdown_event.wait()

        except KeyboardInterrupt:
            logger.info("keyboard_interrupt_received")
        except Exception as e:
            logger.error("trading_system_error", error=str(e), exc_info=True)
        finally:
            await self.stop()

    def request_shutdown(self):
        """Request graceful shutdown."""
        logger.info("shutdown_requested")
        self.shutdown_event.set()


async def main():
    """Main entry point."""
    # Load configuration
    config_path = "config/config.yaml"
    config = load_config(config_path)
    settings = load_settings()

    # Setup logging
    setup_logging(config.logging)

    logger.info(
        "starting_hyperliquid_market_maker",
        environment=settings.environment,
        simulation_mode=settings.simulation_mode,
        symbol=config.trading.symbol,
    )

    # Create trading system
    system = TradingSystem(config=config, settings=settings)

    # Setup signal handlers
    def signal_handler(sig, frame):
        logger.info("signal_received", signal=sig)
        system.request_shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run system
    await system.run()

    logger.info("hyperliquid_market_maker_shutdown_complete")


if __name__ == "__main__":
    asyncio.run(main())
