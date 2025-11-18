# Hyperliquid Micro-Market-Maker & Hedge Engine

A production-grade, autonomous trading system for the Hyperliquid exchange that provides continuous liquidity through micro market-making while automatically hedging positions to capture risk-free spreads.

## Overview

This system implements a sophisticated market-making strategy that:

- Places $1 notional limit orders continuously on both sides of the market
- Captures micro-spreads greater than or equal to total fee costs (≥ 0.06%)
- Automatically hedges filled orders with counter-positions at profitable prices
- Maintains strict risk controls and position limits
- Operates exclusively with maker orders to minimize trading costs

## Key Features

### Market Making
- **Continuous Liquidity**: Maintains constant presence in the order book
- **Multi-Level Quoting**: Places orders at multiple price levels for better fill rates
- **Dynamic Spreads**: Adjusts spreads based on volatility and market conditions
- **Maker-Only**: All orders are post-only limit orders to capture maker rebates

### Auto-Hedging
- **Instant Hedge Placement**: Automatically places counter-orders when filled
- **Profitable Pricing**: Ensures hedge prices cover all fees plus safety margin
- **Retry Logic**: Attempts multiple times with improved pricing if needed
- **Fill Tracking**: Monitors hedge execution and handles timeouts

### Risk Management
- **Inventory Limits**: Caps maximum exposure in either direction
- **Position Limits**: Controls maximum position notional
- **Circuit Breakers**: Automatically halts trading on anomalies
- **Unhedged Duration Monitoring**: Tracks time positions remain unhedged
- **Latency Monitoring**: Detects and responds to high latency conditions

### Performance
- **Low Latency**: Sub-100ms order placement
- **WebSocket Integration**: Real-time fill detection
- **Efficient Execution**: Optimized cancel/replace cycles
- **Comprehensive Metrics**: Track PnL, fill rates, spreads, and more

## Architecture

The system consists of modular components:

- **Exchange Connector**: REST and WebSocket API integration
- **Market Making Engine**: Continuous order placement and management
- **Hedging Engine**: Automatic position hedging
- **Risk Controller**: Risk limits and circuit breakers
- **Position Manager**: Position tracking and PnL calculation
- **Fee Calculator**: Fee computation and profitability validation

See [ARCHITECTURE.md](ARCHITECTURE.md) for detailed system design.

## Installation

### Prerequisites

- Python 3.11 or higher
- Hyperliquid account with API access
- Private key for signing transactions

### Setup

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/mmhype.git
cd mmhype
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env and add your Hyperliquid private key
```

5. **Configure trading parameters**
```bash
# Edit config/config.yaml to customize trading parameters
# See Configuration section below
```

## Configuration

### Environment Variables (.env)

```bash
# Required
HYPERLIQUID_PRIVATE_KEY=your_private_key_here

# Optional
HYPERLIQUID_VAULT_ADDRESS=your_vault_address
HYPERLIQUID_SUBACCOUNT_ADDRESS=your_subaccount_address
ENVIRONMENT=production
SIMULATION_MODE=false
```

### Trading Configuration (config/config.yaml)

Key parameters:

```yaml
trading:
  symbol: BTC                    # Trading symbol
  order_notional_usd: 1.0       # Order size in USD
  base_spread_bps: 6.0          # Minimum spread (0.06%)
  num_levels: 3                 # Number of order book levels
  refresh_interval_ms: 5000     # Order refresh interval

risk:
  max_inventory_usd: 5.0        # Max inventory either direction
  max_daily_loss_usd: 10.0      # Daily loss limit
  latency_threshold_ms: 500     # Circuit breaker threshold
```

See `config/config.yaml` for all available options.

## Usage

### Running Locally

```bash
python src/main.py
```

### Running with Docker

```bash
# Build image
docker build -t hyperliquid-mm .

# Run container
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# With coverage
pytest --cov=src --cov-report=html

# Specific test file
pytest tests/unit/test_fee_calculator.py
```

## Monitoring

### Logs

Logs are written to:
- Console (stdout) with structured JSON format
- File: `logs/trading.log`

Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

### Metrics

The system tracks:
- Total trades and success rate
- Net PnL (profit/loss)
- Average spread captured
- Average hedge latency
- Inventory and position exposure
- Circuit breaker activations

View metrics in real-time:
```bash
tail -f logs/trading.log | grep performance_report
```

### Performance Reports

The system logs performance reports every minute:
```json
{
  "event": "performance_report",
  "total_trades": 100,
  "successful_trades": 95,
  "net_profit": 4.25,
  "average_spread_bps": 6.8,
  "average_hedge_latency_ms": 145,
  "inventory_usd": 2.1
}
```

## Strategy Details

### Spread Calculation

Minimum spread must cover:
- Entry maker fee: 0.026%
- Exit maker fee: 0.026%
- Safety margin: ~0.01%
- **Total minimum: 0.06% (6 basis points)**

### Hedge Pricing

For a BUY fill at price P:
```
Hedge Price = P × (1 + required_offset)
Where required_offset ≥ 0.0006 (0.06%)
```

For a SELL fill at price P:
```
Hedge Price = P × (1 - required_offset)
```

### Profitability Formula

```
Net Profit = Gross Profit - Total Fees

Where:
Gross Profit = |Exit Price - Entry Price| × Quantity
Total Fees = Entry Fee + Exit Fee
```

## Risk Controls

### Inventory Limits
- Maximum long exposure: 5 USD (configurable)
- Maximum short exposure: 5 USD (configurable)
- Prevents accumulation of directional risk

### Position Limits
- Maximum position notional: 10 USD (configurable)
- Caps total exposure per symbol

### Circuit Breakers

Automatically activated on:
- Daily loss exceeds limit
- Too many consecutive failures
- Sustained high latency
- Unhedged position duration exceeded
- Position imbalance ratio exceeded

### Recovery

Circuit breakers have a cooldown period (default: 5 minutes) before they can be reset.

## Troubleshooting

### Common Issues

**1. WebSocket Disconnections**
- System automatically reconnects
- Fill detection may have brief delays
- Check network connectivity

**2. Orders Not Filling**
- Spread may be too wide
- Adjust `base_spread_bps` in config
- Check market volatility

**3. Circuit Breaker Activated**
- Check logs for activation reason
- Review risk limits in config
- Wait for cooldown period
- Investigate underlying cause

**4. High Latency**
- Check network connection
- Consider running closer to exchange servers
- Review `latency_threshold_ms` setting

### Debug Mode

Enable debug logging:
```yaml
logging:
  level: DEBUG
```

## Development

### Project Structure

```
mmhype/
├── src/
│   ├── connectors/         # Exchange API integration
│   ├── engines/            # Market making and hedging
│   ├── managers/           # Position and state management
│   ├── risk/              # Risk controls
│   ├── utils/             # Utilities and models
│   └── main.py            # Main orchestrator
├── tests/
│   ├── unit/              # Unit tests
│   ├── integration/       # Integration tests
│   └── stress/            # Stress tests
├── config/                # Configuration files
├── logs/                  # Log files
└── data/                  # Data storage
```

### Adding New Features

1. Create module in appropriate directory
2. Add tests in `tests/unit/`
3. Update configuration if needed
4. Document in relevant files
5. Submit pull request

### Code Style

- Python 3.11+ with type hints
- Follow PEP 8 style guide
- Use structured logging (structlog)
- Write comprehensive tests
- Document public APIs

## Safety & Disclaimer

**WARNING**: This software is for educational and research purposes only.

- **Use at your own risk**: Trading cryptocurrencies involves substantial risk
- **No guarantees**: Past performance does not guarantee future results
- **Test thoroughly**: Always test on testnet before live trading
- **Start small**: Begin with minimal capital
- **Monitor closely**: Never leave unattended
- **Understand risks**: Ensure you understand how the system works

## License

MIT License - See LICENSE file for details

## Support

For issues, questions, or contributions:
- GitHub Issues: [github.com/yourusername/mmhype/issues](https://github.com/yourusername/mmhype/issues)
- Documentation: See [ARCHITECTURE.md](ARCHITECTURE.md)

## Acknowledgments

- Built for the Hyperliquid exchange
- Uses EIP-712 signing for authentication
- Inspired by professional market-making practices

---

**Disclaimer**: This is experimental software. Use at your own risk. The authors are not responsible for any losses incurred.
