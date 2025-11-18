"""
Configuration management for the trading system.
"""
import os
import yaml
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ExchangeConfig(BaseModel):
    """Exchange connection configuration."""
    name: str = "hyperliquid"
    rest_url: str = "https://api.hyperliquid.xyz"
    ws_url: str = "wss://api.hyperliquid.xyz/ws"
    testnet: bool = False
    testnet_rest_url: str = "https://api.hyperliquid-testnet.xyz"
    testnet_ws_url: str = "wss://api.hyperliquid-testnet.xyz/ws"


class TradingConfig(BaseModel):
    """Trading strategy configuration."""
    symbol: str = "BTC"
    order_notional_usd: Decimal = Decimal("1.0")
    base_spread_bps: Decimal = Decimal("6.0")  # 0.06%
    min_profitable_spread_bps: Decimal = Decimal("6.0")  # Must cover 0.052% fees
    num_levels: int = 3
    refresh_interval_ms: int = 5000
    volatility_multiplier: Decimal = Decimal("1.5")
    max_order_ttl_seconds: int = 30


class HedgingConfig(BaseModel):
    """Hedging configuration."""
    enabled: bool = True
    hedge_offset_bps: Decimal = Decimal("6.0")  # Minimum offset for profitable hedge
    max_hedge_attempts: int = 5
    hedge_timeout_seconds: int = 60
    retry_price_improvement_bps: Decimal = Decimal("1.0")


class RiskConfig(BaseModel):
    """Risk management configuration."""
    max_inventory_usd: Decimal = Decimal("5.0")
    max_position_notional_usd: Decimal = Decimal("10.0")
    max_unhedged_duration_seconds: int = 30
    max_daily_loss_usd: Decimal = Decimal("10.0")
    max_position_imbalance_ratio: Decimal = Decimal("0.8")
    latency_threshold_ms: int = 500
    max_consecutive_failures: int = 10
    circuit_breaker_cooldown_seconds: int = 300


class SubAccountConfig(BaseModel):
    """Sub-account configuration."""
    enabled: bool = False
    subaccount_address: Optional[str] = None


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = "INFO"
    format: str = "json"
    file_enabled: bool = True
    file_path: str = "logs/trading.log"
    console_enabled: bool = True
    max_file_size_mb: int = 100
    backup_count: int = 10


class MonitoringConfig(BaseModel):
    """Monitoring and metrics configuration."""
    enabled: bool = False
    prometheus_port: int = 8000
    metrics_interval_seconds: int = 60


class Config(BaseModel):
    """Main configuration model."""
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    hedging: HedgingConfig = Field(default_factory=HedgingConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    subaccount: SubAccountConfig = Field(default_factory=SubAccountConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)


class Settings(BaseSettings):
    """Environment-based settings."""
    # Hyperliquid API credentials
    hyperliquid_private_key: str = Field(default="", alias="HYPERLIQUID_PRIVATE_KEY")
    hyperliquid_vault_address: Optional[str] = Field(default=None, alias="HYPERLIQUID_VAULT_ADDRESS")
    hyperliquid_subaccount_address: Optional[str] = Field(default=None, alias="HYPERLIQUID_SUBACCOUNT_ADDRESS")

    # Environment
    environment: str = Field(default="development", alias="ENVIRONMENT")
    debug: bool = Field(default=False, alias="DEBUG")

    # Simulation mode
    simulation_mode: bool = Field(default=False, alias="SIMULATION_MODE")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


def load_config(config_path: str = "config/config.yaml") -> Config:
    """
    Load configuration from YAML file.

    Args:
        config_path: Path to configuration file

    Returns:
        Config object
    """
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config_dict = yaml.safe_load(f)
        return Config(**config_dict)
    else:
        # Return default configuration
        return Config()


def load_settings() -> Settings:
    """
    Load settings from environment variables.

    Returns:
        Settings object
    """
    return Settings()
