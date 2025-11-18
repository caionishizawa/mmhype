# Hyperliquid Micro-Market-Maker & Hedge Engine - System Architecture

## Executive Summary

This document describes a production-grade, high-frequency market-making and hedging system for the Hyperliquid exchange. The system provides continuous liquidity using $1 notional orders while capturing micro-spreads and maintaining strict risk controls.

## System Objectives

1. **Continuous Liquidity Provision**: Place and maintain $1 limit orders on both sides of the market
2. **Spread Capture**: Target minimum spread ≥ 0.06% to cover roundtrip fees (0.052%)
3. **Auto-Hedging**: Instantly hedge filled orders with counter-positions at profitable prices
4. **Maker-Only Strategy**: Use only maker orders to benefit from negative fees/rebates
5. **Risk Management**: Strict inventory limits, position controls, and circuit breakers
6. **Sub-Account Isolation**: Separate trading operations using Hyperliquid sub-accounts

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Main Orchestrator                        │
│                    (Event Loop Coordinator)                     │
└───────────┬─────────────────────────────────────────┬───────────┘
            │                                         │
            ▼                                         ▼
┌───────────────────────┐                 ┌──────────────────────┐
│  Market Making Engine │                 │   Hedging Engine     │
│  - Order Placement    │◄────────────────┤  - Fill Detection    │
│  - Spread Calculation │                 │  - Counter Orders    │
│  - Order Refresh      │                 │  - Hedge Validation  │
└───────────┬───────────┘                 └──────────┬───────────┘
            │                                        │
            │         ┌──────────────────┐          │
            └────────►│ Risk Controller  │◄─────────┘
                      │ - Inventory Mgmt │
                      │ - Circuit Breaker│
                      │ - Position Limits│
                      └────────┬─────────┘
                               │
            ┌──────────────────┴───────────────────┐
            │                                      │
            ▼                                      ▼
┌───────────────────────┐              ┌─────────────────────────┐
│ Exchange Connector    │              │   Position Manager      │
│ - REST API Client     │              │ - Balance Tracking      │
│ - WebSocket Client    │              │ - Position Tracking     │
│ - Order Management    │              │ - PnL Calculation       │
│ - Signature/Auth      │              │ - Trade History         │
└───────────┬───────────┘              └─────────────────────────┘
            │
            ▼
┌───────────────────────┐
│   Fee Calculator      │
│ - Fee Computation     │
│ - Spread Requirements │
│ - Profitability Check │
└───────────────────────┘
```

## Module Descriptions

### 1. Exchange Connector
**File**: `src/connectors/hyperliquid_connector.py`

**Responsibilities**:
- REST API integration for order placement, cancellation, and account queries
- WebSocket connection for real-time fills, order updates, and market data
- Authentication and message signing using Hyperliquid's EIP-712 scheme
- Connection management: heartbeats, reconnection logic, error handling
- Nonce management for deterministic order sequencing

**Key Methods**:
- `connect_websocket()`: Establish WebSocket connection
- `subscribe_user_events()`: Subscribe to fill events
- `place_order()`: Place limit order
- `cancel_order()`: Cancel existing order
- `get_balance()`: Query account balance
- `get_open_orders()`: Query open orders
- `transfer_to_subaccount()`: Transfer funds between accounts

### 2. Market Making Engine
**File**: `src/engines/market_maker.py`

**Responsibilities**:
- Calculate optimal bid/ask prices based on market conditions
- Place $1 notional limit orders at calculated prices
- Maintain order book presence at multiple levels
- Implement dynamic spread adjustment based on volatility
- Handle order refresh cycles (cancel/replace)

**Configuration**:
- `base_spread_bps`: Minimum spread in basis points (default: 6)
- `order_notional_usd`: Order size in USD (default: 1.0)
- `num_levels`: Number of order book levels to quote (default: 3)
- `refresh_interval_ms`: Order refresh interval (default: 5000)
- `volatility_multiplier`: Spread adjustment during high volatility

**Logic Flow**:
```
1. Get current mid-price from market data
2. Calculate required spread: max(base_spread, volatility_adjusted_spread)
3. Calculate bid = mid * (1 - spread/2), ask = mid * (1 + spread/2)
4. Round to exchange tick size
5. Place orders if not already present
6. Cancel stale orders beyond TTL
7. Repeat every refresh_interval_ms
```

### 3. Hedging Engine
**File**: `src/engines/hedging_engine.py`

**Responsibilities**:
- Listen to fill events from WebSocket
- Calculate optimal hedge price ensuring profitability
- Place counter limit orders (maker-only)
- Track hedge execution status
- Retry failed hedges with improved pricing

**Hedge Calculation**:
```python
# For a LONG fill (bought), place SHORT hedge
hedge_price = fill_price * (1 + required_offset)

# For a SHORT fill (sold), place LONG hedge
hedge_price = fill_price * (1 - required_offset)

# Where required_offset >= 0.0006 (0.06%)
```

**Fill Event Handler**:
```
1. Receive fill event from WebSocket
2. Validate fill: price, quantity, direction, timestamp
3. Calculate hedge price with required offset
4. Check risk limits (inventory, position size)
5. Place hedge limit order
6. Monitor hedge fill within timeout
7. If not filled, cancel and replace with better price
8. Log complete cycle: entry → hedge → profit
```

### 4. Risk Controller
**File**: `src/risk/risk_controller.py`

**Responsibilities**:
- Enforce inventory limits (max long/short exposure)
- Circuit breaker activation on anomalies
- Validate all orders before placement
- Monitor position concentration
- Track unhedged exposure duration

**Risk Parameters**:
```yaml
max_inventory_usd: 5.0          # Max inventory in either direction
max_unhedged_duration_sec: 30    # Max time to hold unhedged position
max_daily_loss_usd: 10.0         # Daily loss limit
latency_threshold_ms: 500        # Circuit breaker on high latency
max_position_imbalance: 0.8      # Ratio threshold for long/short balance
```

**Circuit Breaker Triggers**:
- Latency > threshold
- Daily loss > limit
- Position imbalance > threshold
- Too many consecutive failed orders
- WebSocket disconnection > threshold duration

### 5. Position Manager
**File**: `src/managers/position_manager.py`

**Responsibilities**:
- Track current positions across sub-accounts
- Calculate real-time PnL
- Maintain trade history
- Compute performance metrics

**Tracked Metrics**:
- Current inventory (long/short)
- Unrealized PnL
- Realized PnL (per trade cycle)
- Total fees paid
- Net profit
- Fill rate
- Average spread captured
- Hedge latency

### 6. Fee Calculator
**File**: `src/utils/fee_calculator.py`

**Responsibilities**:
- Calculate Hyperliquid maker/taker fees
- Compute minimum profitable spread
- Validate trade profitability
- Track fee tier status

**Fee Structure** (Hyperliquid):
```
Maker Fee: -0.00026 to 0.00035 (varies by tier)
Taker Fee: 0.035% to 0.06%

Assumption for this system:
Maker: 0.026% per side → 0.052% roundtrip
Required Spread: >= 0.06% for safety margin
```

### 7. Configuration System
**File**: `config/config.yaml`

Centralized configuration for:
- Exchange credentials (API key, vault address)
- Trading parameters (spreads, sizes, intervals)
- Risk limits
- Sub-account addresses
- Logging levels
- Network endpoints

### 8. Main Orchestrator
**File**: `src/main.py`

**Responsibilities**:
- Initialize all modules
- Start event loop
- Coordinate market making and hedging engines
- Handle graceful shutdown
- Restart on failures

**Startup Sequence**:
```
1. Load configuration
2. Initialize logging
3. Connect to Hyperliquid (REST + WebSocket)
4. Initialize all modules
5. Start market making loop
6. Start hedging event listener
7. Start risk monitoring loop
8. Enter main event loop
```

## Data Flow

### Order Placement Flow
```
Market Maker → Risk Controller → Exchange Connector → Hyperliquid
                     ↓
              Position Manager (update)
```

### Fill Event Flow
```
Hyperliquid → WebSocket → Hedging Engine → Risk Controller
                                ↓
                        Exchange Connector → Place Hedge Order
                                ↓
                        Position Manager (update PnL)
```

## Technology Stack

### Core
- **Language**: Python 3.11+
- **Async Framework**: asyncio
- **HTTP Client**: aiohttp
- **WebSocket**: websockets
- **Cryptography**: eth_account (for EIP-712 signing)

### Data & Config
- **Configuration**: PyYAML
- **Data Models**: Pydantic
- **Logging**: structlog

### Testing
- **Unit Tests**: pytest
- **Async Tests**: pytest-asyncio
- **Mocking**: unittest.mock, aioresponses

### Deployment
- **Containerization**: Docker
- **Orchestration**: Docker Compose / Kubernetes (optional)
- **Monitoring**: Prometheus + Grafana (optional)

## Performance Requirements

- **Order Placement Latency**: < 100ms
- **Hedge Latency**: < 200ms from fill to hedge order placed
- **WebSocket Reconnection**: < 5s
- **Order Refresh Cycle**: Configurable, default 5s
- **Market Data Latency**: < 50ms via WebSocket

## Security & Safety

### Key Management
- API keys stored in environment variables or secure vault
- Never log sensitive credentials
- Use read-only permissions where possible

### Order Safety
- All orders include price limits (no market orders)
- Position limits enforced before order placement
- Sanity checks on all calculated prices
- Atomic operations for critical state changes

### Error Handling
- Graceful degradation on API failures
- Exponential backoff for retries
- Dead letter queue for failed operations
- Alert on critical failures

## Sub-Account Architecture

```
Main Account (Vault)
    ↓ transfer
Sub-Account (Market Maker)
    ↓ isolated inventory
    ├── Long positions
    ├── Short positions
    └── Cash balance
```

**Benefits**:
- Risk isolation
- Separate PnL tracking
- Independent position limits
- Easier reconciliation

## Monitoring & Observability

### Metrics Tracked
- **Performance**: Fill rate, spread captured, hedge latency
- **Risk**: Current inventory, position imbalance, unrealized PnL
- **System**: WebSocket uptime, API latency, error rate
- **Profitability**: Realized PnL, fees paid, net profit

### Logging Levels
- **DEBUG**: All order placements, fills, calculations
- **INFO**: Hedge executions, position updates, performance summaries
- **WARNING**: Risk limit approaches, retry attempts
- **ERROR**: Failed orders, WebSocket disconnections, circuit breaker activations
- **CRITICAL**: System failures, unrecoverable errors

### Dashboard (Optional)
Real-time visualization of:
- Current positions and inventory
- Open orders
- Recent fills and hedges
- PnL chart
- System health indicators

## Deployment Architecture

### Development Mode
```bash
python src/main.py --config config/config.dev.yaml --mode simulation
```

### Production Mode
```bash
docker run -d \
  -v /path/to/config:/app/config \
  -v /path/to/logs:/app/logs \
  --env-file .env \
  hyperliquid-mm:latest
```

### High Availability (Optional)
- Multiple instances with leader election
- Shared state via Redis
- Load balancing across instances
- Automatic failover

## Risk Scenarios & Mitigations

| Scenario | Risk | Mitigation |
|----------|------|------------|
| Large unhedged fill | Directional exposure | Fast hedge with retry logic, position limits |
| WebSocket disconnect | Missed fills | REST API fallback polling, reconnection logic |
| API rate limiting | Order failures | Request throttling, backoff logic |
| Market volatility spike | Adverse fills | Dynamic spread widening, circuit breaker |
| Exchange outage | Stuck positions | Multi-exchange support (future), manual intervention alerts |
| Network latency | Execution delays | Latency monitoring, circuit breaker, geographic proximity |

## Future Enhancements

1. **Multi-Asset Support**: Extend beyond BTC to other liquid markets
2. **Advanced Strategies**: Grid trading, inventory skewing, adverse selection mitigation
3. **Machine Learning**: Spread optimization, fill prediction
4. **Multi-Exchange**: Arbitrage opportunities across venues
5. **Advanced Analytics**: Performance attribution, trade cost analysis
6. **GUI Dashboard**: Real-time monitoring and manual controls

## Testing Strategy

### Unit Tests
- Individual module functionality
- Fee calculations
- Price calculations
- Risk limit enforcement

### Integration Tests
- Exchange connector with mock API
- End-to-end order flow
- WebSocket event handling

### Stress Tests
- High-frequency order cycles
- Reconnection scenarios
- Concurrent operations

### Simulation Mode
- Replay historical data
- Test strategies without real funds
- Performance profiling

## Performance Benchmarks

Target metrics for production deployment:

- **Uptime**: 99.9%
- **Fill Detection Latency**: p50 < 50ms, p99 < 200ms
- **Hedge Placement Latency**: p50 < 100ms, p99 < 300ms
- **Spread Capture**: Average ≥ 0.08%
- **Profitability**: Net positive after fees

## Conclusion

This architecture provides a robust, scalable foundation for a professional market-making system. The modular design allows for independent testing, deployment, and enhancement of components while maintaining strict risk controls and high performance.
