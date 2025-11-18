"""
Hyperliquid exchange connector for REST and WebSocket API.
"""
import asyncio
import json
import time
from decimal import Decimal
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime
from eth_account import Account
from eth_account.messages import encode_structured_data
import aiohttp
import websockets
import structlog

from ..utils.models import Order, Fill, Balance, OrderSide, OrderStatus

logger = structlog.get_logger(__name__)


class HyperliquidConnector:
    """
    Connector for Hyperliquid exchange API.

    Handles:
    - REST API requests (orders, balances, positions)
    - WebSocket connections (real-time fills, updates)
    - Authentication and signing (EIP-712)
    - Connection management and reconnection
    """

    def __init__(
        self,
        private_key: str,
        rest_url: str = "https://api.hyperliquid.xyz",
        ws_url: str = "wss://api.hyperliquid.xyz/ws",
        vault_address: Optional[str] = None,
        subaccount_address: Optional[str] = None,
    ):
        """
        Initialize Hyperliquid connector.

        Args:
            private_key: Private key for signing transactions
            rest_url: REST API base URL
            ws_url: WebSocket API URL
            vault_address: Vault address (if using vault)
            subaccount_address: Sub-account address (if using sub-account)
        """
        self.private_key = private_key
        self.rest_url = rest_url
        self.ws_url = ws_url
        self.vault_address = vault_address
        self.subaccount_address = subaccount_address

        # Initialize account from private key
        self.account = Account.from_key(private_key)
        self.address = self.account.address

        # HTTP session
        self.session: Optional[aiohttp.ClientSession] = None

        # WebSocket
        self.ws: Optional[websockets.WebSocketClientProtocol] = None
        self.ws_connected = False
        self.ws_reconnect_delay = 5  # seconds

        # Callbacks for WebSocket events
        self.fill_callbacks: List[Callable] = []
        self.order_update_callbacks: List[Callable] = []

        # Nonce management
        self.nonce = int(time.time() * 1000)

        logger.info(
            "hyperliquid_connector_initialized",
            address=self.address,
            rest_url=rest_url,
            ws_url=ws_url,
            vault_address=vault_address,
            subaccount_address=subaccount_address,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()

    async def connect(self):
        """Initialize HTTP session and WebSocket connection."""
        # Create HTTP session
        self.session = aiohttp.ClientSession()

        # Connect WebSocket
        await self.connect_websocket()

        logger.info("hyperliquid_connector_connected")

    async def disconnect(self):
        """Close HTTP session and WebSocket connection."""
        # Close WebSocket
        if self.ws:
            await self.ws.close()
            self.ws_connected = False

        # Close HTTP session
        if self.session:
            await self.session.close()

        logger.info("hyperliquid_connector_disconnected")

    def get_next_nonce(self) -> int:
        """Get next nonce for request signing."""
        self.nonce += 1
        return self.nonce

    def sign_l1_action(
        self,
        action: Dict,
        nonce: Optional[int] = None,
        vault_address: Optional[str] = None,
    ) -> Dict:
        """
        Sign a Layer 1 action using EIP-712.

        Args:
            action: Action to sign
            nonce: Nonce for the action
            vault_address: Vault address (if applicable)

        Returns:
            Signed action with signature
        """
        if nonce is None:
            nonce = self.get_next_nonce()

        # Construct EIP-712 message
        # Note: This is a simplified version. Actual Hyperliquid signing may differ.
        # Refer to official Hyperliquid documentation for exact implementation.
        connection_id = vault_address or self.address

        phantom_agent = {
            "source": "a",  # "a" for API
            "connectionId": connection_id,
        }

        data = {
            "action": action,
            "nonce": nonce,
            "phantomAgent": phantom_agent,
        }

        # Create EIP-712 structured data
        structured_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "HyperliquidTransaction": [
                    {"name": "action", "type": "string"},
                    {"name": "nonce", "type": "uint64"},
                ],
            },
            "primaryType": "HyperliquidTransaction",
            "domain": {
                "name": "Hyperliquid",
                "version": "1",
                "chainId": 1,
                "verifyingContract": "0x0000000000000000000000000000000000000000",
            },
            "message": {
                "action": json.dumps(action),
                "nonce": nonce,
            },
        }

        # Sign the message
        encoded_data = encode_structured_data(structured_data)
        signed_message = self.account.sign_message(encoded_data)

        return {
            "action": action,
            "nonce": nonce,
            "signature": {
                "r": hex(signed_message.r),
                "s": hex(signed_message.s),
                "v": signed_message.v,
            },
        }

    async def _post_request(self, endpoint: str, payload: Dict) -> Dict:
        """
        Make a POST request to Hyperliquid API.

        Args:
            endpoint: API endpoint
            payload: Request payload

        Returns:
            Response data
        """
        url = f"{self.rest_url}{endpoint}"

        try:
            async with self.session.post(url, json=payload) as response:
                response.raise_for_status()
                data = await response.json()
                return data
        except aiohttp.ClientError as e:
            logger.error("api_request_failed", endpoint=endpoint, error=str(e))
            raise

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        price: Decimal,
        quantity: Decimal,
        order_type: str = "limit",
        reduce_only: bool = False,
        post_only: bool = True,
    ) -> Order:
        """
        Place a limit order.

        Args:
            symbol: Trading symbol (e.g., "BTC")
            side: Order side (BUY or SELL)
            price: Limit price
            quantity: Order quantity
            order_type: Order type (default: "limit")
            reduce_only: If True, order can only reduce position
            post_only: If True, order will only execute as maker

        Returns:
            Order object
        """
        # Construct order action
        action = {
            "type": "order",
            "orders": [
                {
                    "asset": symbol,
                    "isBuy": side == OrderSide.BUY,
                    "limitPx": str(price),
                    "sz": str(quantity),
                    "reduceOnly": reduce_only,
                    "orderType": {"limit": {"tif": "Gtc"}},  # Good-til-cancel
                }
            ],
            "grouping": "na",
        }

        # Sign and send
        signed_action = self.sign_l1_action(action, vault_address=self.vault_address)

        response = await self._post_request("/exchange", signed_action)

        # Parse response and create Order object
        # Note: Actual response structure may differ
        client_order_id = f"{symbol}_{side.value}_{int(time.time() * 1000)}"
        order = Order(
            order_id=response.get("status", {}).get("oid"),
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            order_type="limit",
            price=price,
            quantity=quantity,
            status=OrderStatus.OPEN,
        )

        logger.info(
            "order_placed",
            order_id=order.order_id,
            symbol=symbol,
            side=side.value,
            price=float(price),
            quantity=float(quantity),
        )

        return order

    async def cancel_order(self, symbol: str, order_id: str) -> bool:
        """
        Cancel an order.

        Args:
            symbol: Trading symbol
            order_id: Order ID to cancel

        Returns:
            True if successful
        """
        action = {
            "type": "cancel",
            "cancels": [
                {
                    "asset": symbol,
                    "oid": order_id,
                }
            ],
        }

        signed_action = self.sign_l1_action(action, vault_address=self.vault_address)

        response = await self._post_request("/exchange", signed_action)

        logger.info("order_cancelled", order_id=order_id, symbol=symbol)

        return True

    async def cancel_all_orders(self, symbol: Optional[str] = None) -> bool:
        """
        Cancel all open orders.

        Args:
            symbol: If provided, cancel only orders for this symbol

        Returns:
            True if successful
        """
        # Get open orders
        open_orders = await self.get_open_orders(symbol)

        # Cancel each order
        for order in open_orders:
            await self.cancel_order(order["asset"], order["oid"])

        logger.info("all_orders_cancelled", symbol=symbol, count=len(open_orders))

        return True

    async def get_balance(self, account: Optional[str] = None) -> Balance:
        """
        Get account balance.

        Args:
            account: Account address (default: self.address)

        Returns:
            Balance object
        """
        if account is None:
            account = self.subaccount_address or self.address

        payload = {
            "type": "clearinghouseState",
            "user": account,
        }

        response = await self._post_request("/info", payload)

        # Parse balance from response
        margin_summary = response.get("marginSummary", {})
        total_balance = Decimal(margin_summary.get("accountValue", "0"))
        available_balance = Decimal(margin_summary.get("totalMarginUsed", "0"))

        balance = Balance(
            account=account,
            total=total_balance,
            available=total_balance - available_balance,
            locked=available_balance,
        )

        logger.info(
            "balance_retrieved",
            account=account,
            total=float(total_balance),
            available=float(balance.available),
        )

        return balance

    async def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get open orders.

        Args:
            symbol: If provided, filter by symbol

        Returns:
            List of open orders
        """
        account = self.subaccount_address or self.address

        payload = {
            "type": "openOrders",
            "user": account,
        }

        response = await self._post_request("/info", payload)

        orders = response if isinstance(response, list) else []

        if symbol:
            orders = [o for o in orders if o.get("coin") == symbol]

        logger.info("open_orders_retrieved", count=len(orders), symbol=symbol)

        return orders

    async def get_position(self, symbol: str) -> Optional[Dict]:
        """
        Get current position for a symbol.

        Args:
            symbol: Trading symbol

        Returns:
            Position data or None
        """
        account = self.subaccount_address or self.address

        payload = {
            "type": "clearinghouseState",
            "user": account,
        }

        response = await self._post_request("/info", payload)

        # Find position for symbol
        positions = response.get("assetPositions", [])
        for pos in positions:
            if pos.get("position", {}).get("coin") == symbol:
                return pos

        return None

    # WebSocket Methods

    async def connect_websocket(self):
        """Connect to Hyperliquid WebSocket."""
        try:
            self.ws = await websockets.connect(self.ws_url)
            self.ws_connected = True

            # Subscribe to user events
            await self.subscribe_user_events()

            # Start listener task
            asyncio.create_task(self._ws_listener())

            logger.info("websocket_connected", ws_url=self.ws_url)

        except Exception as e:
            logger.error("websocket_connection_failed", error=str(e))
            self.ws_connected = False
            # Schedule reconnection
            asyncio.create_task(self._reconnect_websocket())

    async def _reconnect_websocket(self):
        """Reconnect WebSocket after delay."""
        await asyncio.sleep(self.ws_reconnect_delay)
        await self.connect_websocket()

    async def subscribe_user_events(self):
        """Subscribe to user-specific events (fills, order updates)."""
        account = self.subaccount_address or self.address

        subscription = {
            "method": "subscribe",
            "subscription": {
                "type": "userEvents",
                "user": account,
            },
        }

        await self.ws.send(json.dumps(subscription))
        logger.info("subscribed_to_user_events", account=account)

    async def _ws_listener(self):
        """Listen to WebSocket messages."""
        try:
            async for message in self.ws:
                data = json.loads(message)
                await self._handle_ws_message(data)

        except websockets.exceptions.ConnectionClosed:
            logger.warning("websocket_connection_closed")
            self.ws_connected = False
            # Reconnect
            asyncio.create_task(self._reconnect_websocket())

        except Exception as e:
            logger.error("websocket_listener_error", error=str(e))
            self.ws_connected = False
            asyncio.create_task(self._reconnect_websocket())

    async def _handle_ws_message(self, data: Dict):
        """
        Handle incoming WebSocket message.

        Args:
            data: Message data
        """
        channel = data.get("channel")
        message_data = data.get("data")

        if channel == "userEvents":
            await self._handle_user_event(message_data)
        elif channel == "trades":
            # Handle trade updates if needed
            pass

    async def _handle_user_event(self, event_data: Any):
        """
        Handle user event (fills, order updates).

        Args:
            event_data: Event data
        """
        if not event_data:
            return

        # Check for fills
        fills = event_data.get("fills", [])
        for fill_data in fills:
            fill = self._parse_fill(fill_data)
            # Trigger callbacks
            for callback in self.fill_callbacks:
                asyncio.create_task(callback(fill))

        # Check for order updates
        # Implement if needed

    def _parse_fill(self, fill_data: Dict) -> Fill:
        """
        Parse fill data into Fill object.

        Args:
            fill_data: Raw fill data from WebSocket

        Returns:
            Fill object
        """
        return Fill(
            fill_id=fill_data.get("tid", ""),
            order_id=fill_data.get("oid", ""),
            symbol=fill_data.get("coin", ""),
            side=OrderSide.BUY if fill_data.get("side") == "B" else OrderSide.SELL,
            price=Decimal(fill_data.get("px", "0")),
            quantity=Decimal(fill_data.get("sz", "0")),
            fee=Decimal(fill_data.get("fee", "0")),
            timestamp=datetime.utcnow(),
            is_maker=fill_data.get("feeToken") != "USDC",  # Simplified check
        )

    def register_fill_callback(self, callback: Callable):
        """
        Register a callback for fill events.

        Args:
            callback: Async function to call on fill
        """
        self.fill_callbacks.append(callback)
        logger.info("fill_callback_registered")

    def register_order_update_callback(self, callback: Callable):
        """
        Register a callback for order update events.

        Args:
            callback: Async function to call on order update
        """
        self.order_update_callbacks.append(callback)
        logger.info("order_update_callback_registered")
