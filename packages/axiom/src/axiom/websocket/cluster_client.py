"""
# Axiom Cluster WebSocket Client

WebSocket client for Axiom Trade cluster connections (regular channels).
Handles new tokens, migrations, SOL price, and token market cap updates.

## Features:
- **New Tokens**: Real-time notifications when new tokens are listed
- **Token Market Cap**: Live market cap updates for specific tokens
- **Token Migrations**: Notifications about token contract migrations
- **SOL Price**: Real-time Solana price updates
- **Authenticated Connections**: Uses authentication tokens from AuthManager
- **Auto-reconnection**: Automatically reconnects on connection loss

## Usage:
```python
from axiom.auth.auth_manager import AuthManager
from axiom.websocket.cluster_client import AxiomClusterWSClient

# Create authenticated session
auth = AuthManager(username="user@example.com", password="password")
auth.authenticate()

# Create WebSocket client
ws = AxiomClusterWSClient(auth)

# Define callback
async def on_new_token(data):
    print(f"New token: {data['token_name']} at {data['pair_address']}")

# Connect and subscribe
await ws.connect()
await ws.subscribe("new_pairs", callback=on_new_token)
await ws.start()
```
"""

import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, TYPE_CHECKING

from shared_lib.baseclient.ws_client import WebSocketClient
from shared_lib.utils.notification import show_alert

if TYPE_CHECKING:
    from telegram import TelegramBot

# WebSocket URL for Axiom cluster
WS_CLUSTER_URL = "wss://cluster3.axiom.trade/"

# Room/channel names for WebSocket subscriptions
ROOM_NEW_PAIRS = "new_pairs"
ROOM_MIGRATIONS = "migrations"
ROOM_SOL_PRICE = "sol_price"
ROOM_TOKEN_PREFIX = "b-"  # Token-specific rooms use format: b-{token_address}


class AxiomClusterWSClient(WebSocketClient):
    """
    WebSocket client for Axiom Trade cluster connections.

    Handles regular channels: new tokens, migrations, SOL price, and token market cap updates.
    Uses JSON messages and room-based subscription model.

    ## Attributes:
    - `auth_manager` (AuthManager): Authentication manager for token access
    - `ws` (WebSocket): WebSocket connection
    - `_callbacks` (dict): Callback registry for message routing

    ## Supported Subscriptions:
    - `new_pairs`: New token listings
    - `migrations`: Token contract migrations
    - `sol_price`: Solana price updates
    - `b-{address}`: Token-specific market cap updates
    """

    HEADERS = {
        "Origin": "https://axiom.trade",
        # "Host": "cluster3.axiom.trade",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    def __init__(
        self,
        # auth_manager: "AuthManager",
        log_level: int = logging.INFO,
        telegram_bot: Optional["TelegramBot"] = None,
        client: Optional[Any] = None,
    ) -> None:
        """
        Initialize Axiom Cluster WebSocket client.

        ## Parameters:
        - `auth_manager`: Authenticated AuthManager instance with valid tokens
        - `log_level`: Logging level (default: INFO)
        - `telegram_bot`: Optional Telegram bot for notifications

        ## Raises:
        - `ValueError`: If auth_manager is None or invalid
        """
        # if not auth_manager:
        #     raise ValueError("auth_manager is required")

        # self.auth_manager = auth_manager

        # Call parent constructor
        super().__init__(
            log_level=log_level,
            ws_url=WS_CLUSTER_URL,
            telegram_bot=telegram_bot,
            client=client,
        )

        # Override logger name
        self.logger = logging.getLogger("AxiomClusterWS")
        self.logger.setLevel(log_level)

    async def _message_handler(self, message: Any) -> None:
        """
        Handle incoming WebSocket messages.

        Parses JSON messages and routes to appropriate callbacks based on room.

        ## Parameters:
        - `message`: WebSocket message (aiohttp.WSMessage)

        ## Message Format:
        ```json
        {
            "room": "new_pairs",
            "pair_address": "0x...",
            "data": {...}
        }
        ```

        ## Routing:
        - `new_pairs` → callback["new_pairs"]
        - `migrations` → callback["migrations"]
        - `sol_price` → callback["sol_price"]
        - `b-{address}` → callback["token_mcap_{address}"]
        """
        try:
            # Parse JSON message
            data = json.loads(message)
            room = data.get("room", "")

            # Route message to appropriate callback
            await self._route_message(room, data)

        except json.JSONDecodeError as e:
            self.logger.error(
                f"Failed to parse message as JSON: {message.data[:100]}..."
            )
            self.logger.debug(f"JSON decode error: {e}")
        except Exception as e:
            self.logger.error(f"Error handling message: {e}", exc_info=True)

    async def _route_message(self, room: str, data: Dict[str, Any]) -> None:
        """
        Route message to appropriate callback based on room name.

        ## Parameters:
        - `room`: Room/channel name from message
        - `data`: Complete message data

        ## Routing Rules:
        - `new_pairs` → callback["new_pairs"]
        - `migrations` → callback["migrations"]
        - `sol_price` → callback["sol_price"]
        - `b-{address}` → callback["token_mcap_{address}"]
        """
        # Handle direct room matches
        if room in self._callbacks:
            await self._callbacks[room](data)
            return
        # Handle token-specific rooms (format: b-{token_address})
        if room.startswith(ROOM_TOKEN_PREFIX):
            token_address = room[len(ROOM_TOKEN_PREFIX) :]
            callback_key = f"token_mcap_{token_address}"

            if callback_key in self._callbacks:
                await self._callbacks[callback_key](data)
                return
            else:
                self.logger.debug(f"No callback registered for room: {room}")
        else:
            self.logger.debug(f"Unhandled room type: {room}")

    async def _send_notification(self, message: str) -> None:
        """
        Send notification via system alert and Telegram.

        ## Parameters:
        - `message`: Notification message to send
        """
        show_alert(title="Axiom Cluster Notification", message=message)
        if self._telegram_bot is not None:
            await self._telegram_bot.send_message(message)

    async def _build_subscribe_message(self, method: str, **kwargs) -> dict[str, Any]:
        """
        Build subscribe message for Axiom cluster protocol.

        ## Parameters:
        - `method`: Subscription method/room name
        - `**kwargs`: Additional parameters (unused for cluster)

        ## Returns:
        - `dict`: Subscribe message in format: `{"action": "join", "room": "room_name"}`

        ## Example:
        ```python
        msg = await client._build_subscribe_message("new_pairs")
        # Returns: {"action": "join", "room": "new_pairs"}
        ```
        """
        return {"action": "join", "room": method}

    async def _build_unsubscribe_message(self, method: str, **kwargs) -> dict[str, Any]:
        """
        Build unsubscribe message for Axiom cluster protocol.

        ## Parameters:
        - `method`: Subscription method/room name
        - `**kwargs`: Additional parameters (unused for cluster)

        ## Returns:
        - `dict`: Unsubscribe message in format: `{"action": "leave", "room": "room_name"}`

        ## Example:
        ```python
        msg = await client._build_unsubscribe_message("new_pairs")
        # Returns: {"action": "leave", "room": "new_pairs"}
        ```
        """
        return {"action": "leave", "room": method}

    # Wrapper methods for cleaner API

    async def subscribe(
        self,
        room: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
        callback_key: Optional[str] = None,
    ) -> bool:
        """
        Subscribe to a room with a callback.

        ## Parameters:
        - `room`: Room name to subscribe to
        - `callback`: Async function called when messages arrive
        - `callback_key`: Optional custom key for callback registration (defaults to room name)

        ## Returns:
        - `bool`: True if subscription successful
        """
        # Use custom callback key if provided, otherwise use room name
        key = callback_key or room

        # Register callback before subscribing
        self._callbacks[key] = callback

        # Subscribe using parent class method
        return await self.subscribe_method(room, callback)

    async def unsubscribe(self, room: str, callback_key: Optional[str] = None) -> bool:
        """
        Unsubscribe from a room.

        ## Parameters:
        - `room`: Room name to unsubscribe from
        - `callback_key`: Optional custom key used during subscription (defaults to room name)

        ## Returns:
        - `bool`: True if unsubscribe successful
        """
        # Use custom callback key if provided, otherwise use room name
        key = callback_key or room

        # Remove callback
        self._callbacks.pop(key, None)

        # Unsubscribe using parent class method
        return await self.unsubscribe_method(room)

    # Convenience methods for common subscriptions

    async def subscribe_new_tokens(
        self, callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> bool:
        """
        Subscribe to new token listing notifications.

        ## Parameters:
        - `callback`: Async function called when new token data arrives

        ## Returns:
        - `bool`: True if subscription successful

        ## Example:
        ```python
        async def on_new_token(data):
            print(f"New token: {data['token_name']}")

        await ws.subscribe_new_tokens(on_new_token)
        ```
        """
        self._active_subscriptions[ROOM_NEW_PAIRS] = {
            "callback": callback,
        }
        return await self.subscribe_method(ROOM_NEW_PAIRS, callback=callback)

    async def subscribe_migrations(
        self, callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> bool:
        """
        Subscribe to token migration notifications.

        ## Parameters:
        - `callback`: Async function called when migration data arrives

        ## Returns:
        - `bool`: True if subscription successful
        """
        self._active_subscriptions[ROOM_MIGRATIONS] = {
            "callback": callback,
        }
        return await self.subscribe_method(ROOM_MIGRATIONS, callback=callback)

    async def subscribe_sol_price(
        self, callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> bool:
        """
        Subscribe to SOL price updates.

        ## Parameters:
        - `callback`: Async function called when price data arrives

        ## Returns:
        - `bool`: True if subscription successful
        """
        self._active_subscriptions[ROOM_SOL_PRICE] = {
            "callback": callback,
        }
        return await self.subscribe_method(ROOM_SOL_PRICE, callback=callback)

    async def subscribe_token_mcap(
        self, token_address: str, callback: Callable[[Dict[str, Any]], Awaitable[None]]
    ) -> bool:
        """
        Subscribe to market cap updates for a specific token.

        ## Parameters:
        - `token_address`: Token contract address
        - `callback`: Async function called when market cap data arrives

        ## Returns:
        - `bool`: True if subscription successful

        ## Example:
        ```python
        async def on_mcap_update(data):
            print(f"Market cap: ${data['market_cap']:,.2f}")

        token = "0x1234567890abcdef..."
        await ws.subscribe_token_mcap(token, on_mcap_update)
        ```
        """
        room = f"{ROOM_TOKEN_PREFIX}{token_address}"
        callback_key = f"token_mcap_{token_address}"
        self._active_subscriptions[callback_key] = {
            "callback": callback,
        }
        return await self.subscribe_method(
            room, callback=callback, callback_key=callback_key
        )

    async def unsubscribe_token_mcap(self, token_address: str) -> bool:
        """
        Unsubscribe from market cap updates for a specific token.

        ## Parameters:
        - `token_address`: Token contract address to unsubscribe from

        ## Returns:
        - `bool`: True if unsubscribe successful
        """
        room = f"{ROOM_TOKEN_PREFIX}{token_address}"
        callback_key = f"token_mcap_{token_address}"
        return await self.unsubscribe(room, callback_key=callback_key)
