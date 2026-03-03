"""
# Axiom Pulse WebSocket Client

WebSocket client for Axiom Trade Pulse analytics connection.
Handles advanced filtering and analytics with binary message encoding.

## Features:
- **Advanced Filtering**: Custom filters for market cap, protocols, liquidity, etc.
- **Binary Encoding**: Efficient data transfer with binary messages
- **Real-time Analytics**: Live filtered token data based on custom criteria
- **Authenticated Connections**: Uses authentication tokens from AuthManager
- **Auto-reconnection**: Automatically reconnects on connection loss

## Usage:
```python
from axiom.auth.auth_manager import AuthManager
from axiom.websocket.pulse_client import AxiomPulseWSClient

# Create authenticated session
auth = AuthManager(username="user@example.com", password="password")
auth.authenticate()

# Create Pulse WebSocket client
ws = AxiomPulseWSClient(auth)

# Define callback
async def on_pulse_data(data):
    print(f"Pulse analytics: {data}")

# Connect and subscribe with custom filters
custom_filters = {
    "type": "userState",
    "state": {
        "tables": {"newPairs": True},
        "filters": {
            "newPairs": {
                "marketCap": {"min": 100000, "max": 1000000}
            }
        }
    }
}
await ws.connect()
await ws.subscribe_pulse(callback=on_pulse_data, user_state=custom_filters)
await ws.start()
```
"""

import base64
import json
import logging
import msgpack
import pathlib
from typing import Any, Awaitable, Callable, Dict, Optional, TYPE_CHECKING

from shared_lib.baseclient.ws_client import WebSocketClient
from shared_lib.utils.notification import show_alert

if TYPE_CHECKING:
    from telegram import TelegramBot
    from axiom.auth.auth_manager import AuthManager

# WebSocket URL for Axiom Pulse
# WS_PULSE_URL = "wss://pulse2.axiom.trade/ws"
WS_PULSE_URL = "wss://pulse.axiom.trade/ws"


def _decode_message_content(content: bytes) -> Any:
    """
    Decode WebSocket message content - try msgpack first, then UTF-8.

    ## Parameters:
    - `content`: Raw message content

    ## Returns:
    - Decoded data (could be list, dict, or string)

    ## Decoding Strategy:
    1. Try msgpack (binary encoding)
    2. Fallback to UTF-8 string
    3. Last resort: base64 encode
    """
    if isinstance(content, bytes):
        try:
            # Try msgpack first (new format)
            decoded = msgpack.unpackb(content, raw=False)
            return decoded
        except Exception:
            try:
                # Fallback to UTF-8 (legacy format)
                return content.decode("utf-8")
            except Exception:
                # Last resort: base64
                return "base64:" + base64.b64encode(content).decode()
    return content


class AxiomPulseWSClient(WebSocketClient):
    """
    WebSocket client for Axiom Trade Pulse analytics connection.

    Handles advanced filtering and analytics with binary message encoding.
    Separate connection from cluster for specialized Pulse data streams.

    ## Attributes:
    - `auth_manager` (AuthManager): Authentication manager for token access
    - `ws` (WebSocket): WebSocket connection to Pulse endpoint
    - `_callbacks` (dict): Callback registry (uses "pulse" key)
    - `_pulse_user_state` (dict): Stored filter configuration

    ## Message Format:
    - Uses binary encoding (msgpack) for efficiency
    - Supports custom filters and table selections
    """

    HEADERS = {
        "Origin": "https://axiom.trade",
        "Host": "pulse2.axiom.trade",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    def __init__(
        self,
        # auth_manager: "AuthManager",
        log_level: int = logging.INFO,
        telegram_bot: Optional["TelegramBot"] = None,
        client: Any | None = None,
    ) -> None:
        """
        Initialize Axiom Pulse WebSocket client.

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
            ws_url=WS_PULSE_URL,
            telegram_bot=telegram_bot,
            client=client,
        )

        # Override logger name
        self.logger = logging.getLogger("AxiomPulseWS")
        self.logger.setLevel(log_level)

        # Store Pulse configuration for reconnection
        self._pulse_user_state: Optional[dict[str, Any]] = None

    async def _message_handler(self, message: Any) -> None:
        """
        Handle incoming Pulse WebSocket messages (binary format).

        Receives binary-encoded messages, decodes them, and routes to callback.

        ## Parameters:
        - `message`: WebSocket message (aiohttp.WSMessage) with binary data

        ## Message Encoding:
        Pulse uses binary encoding (msgpack) for efficiency. Messages are decoded
        using `_decode_message_content()` which handles:
        - msgpack binary data
        - UTF-8 fallback
        - Base64-encoded fallback for non-UTF-8 data
        """
        decoded_message = None  # Initialize to avoid unbound variable error
        try:
            # Decode binary message
            decoded_message = _decode_message_content(message)

            # Route to Pulse callback if registered
            if "pulse" in self._callbacks:
                await self._callbacks["pulse"](decoded_message)
            else:
                self.logger.debug("Pulse message received but no callback registered")

        except json.JSONDecodeError as e:
            msg_preview = (
                str(decoded_message)[:100]
                if decoded_message
                else str(message.data)[:100]
            )
            self.logger.error(
                f"Failed to parse Pulse message as JSON: {msg_preview}..."
            )
            self.logger.debug(f"JSON decode error: {e}")
        except Exception as e:
            self.logger.error(f"Error handling Pulse message: {e}", exc_info=True)

    async def _send_notification(self, message: str) -> None:
        """
        Send notification via system alert and Telegram.

        ## Parameters:
        - `message`: Notification message to send
        """
        show_alert(title="Axiom Pulse Notification", message=message)
        if self._telegram_bot is not None:
            await self._telegram_bot.send_message(message)

    async def _build_subscribe_message(self, method: str, **kwargs) -> dict[str, Any]:
        """
        Build subscribe message for Axiom Pulse protocol.

        ## Parameters:
        - `method`: Subscription method (unused for Pulse, always "pulse")
        - `**kwargs`: Additional parameters
          - `user_state`: Filter configuration dict

        ## Returns:
        - `dict`: Pulse user state configuration with filters

        ## Example:
        ```python
        msg = await client._build_subscribe_message(
            "pulse",
            user_state={"type": "userState", "state": {...}}
        )
        ```
        """
        user_state = kwargs.get("user_state")

        if user_state:
            return user_state

        # Load default configuration
        return self._load_default_pulse_config()

    async def _build_unsubscribe_message(self, method: str, **kwargs) -> dict[str, Any]:
        """
        Build unsubscribe message for Axiom Pulse protocol.

        Note: Pulse doesn't have explicit unsubscribe - handled by connection close.

        ## Parameters:
        - `method`: Subscription method
        - `**kwargs`: Additional parameters

        ## Returns:
        - `dict`: Empty dict (unsubscribe via connection close)
        """
        return {}

    # Wrapper methods for cleaner API

    async def subscribe(
        self,
        method: str,
        callback: Callable[[Dict[str, Any]], Awaitable[None]],
        **kwargs,
    ) -> bool:
        """
        Subscribe to Pulse analytics with callback.

        ## Parameters:
        - `method`: Subscription method (always "pulse" for Pulse protocol)
        - `callback`: Async function called when Pulse messages arrive
        - `**kwargs`: Additional parameters (e.g., user_state filters)

        ## Returns:
        - `bool`: True if subscription successful
        """
        return await self.subscribe_method(method, callback, **kwargs)

    async def unsubscribe(self, method: str, **kwargs) -> bool:
        """
        Unsubscribe from Pulse analytics.

        Note: Pulse protocol doesn't actually support unsubscription,
        but this method removes the callback and sends an empty message.

        ## Parameters:
        - `method`: Subscription method (always "pulse" for Pulse protocol)
        - `**kwargs`: Additional parameters (unused)

        ## Returns:
        - `bool`: True if unsubscribe successful
        """
        return await self.unsubscribe_method(method, **kwargs)

    def _load_default_pulse_config(self) -> Dict[str, Any]:
        """
        Load default Pulse configuration from pulse_send_message.json.

        ## Returns:
        - `dict`: Default Pulse filter configuration

        ## Config Location:
        Looks for `pulse_send_message.json` in the same directory as this file.
        Falls back to minimal config if file not found.
        """
        # Get path to pulse_send_message.json in same directory
        config_path = pathlib.Path(__file__).parent / "pulse_send_message.json"

        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            self.logger.debug("Loaded default Pulse configuration")
            return config
        except Exception as e:
            self.logger.warning(
                f"Failed to load pulse_send_message.json, using minimal config: {e}"
            )
            # Fallback to minimal configuration
            return {
                "type": "userState",
                "state": {
                    "tables": {
                        "newPairs": True,
                        "finalStretch": True,
                        "migrated": True,
                    },
                    "filters": {"newPairs": {}, "finalStretch": {}, "migrated": {}},
                },
            }

    async def subscribe_pulse(
        self,
        callback: Callable[[Any], Awaitable[None]],
        user_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Subscribe to Pulse analytics with optional custom filters.

        ## Parameters:
        - `callback`: Async function called when Pulse data arrives
        - `user_state`: Optional custom filter configuration
          If None, loads default configuration from pulse_send_message.json

        ## Returns:
        - `bool`: True if subscription successful

        ## Filter Configuration:
        ```python
        user_state = {
            "type": "userState",
            "state": {
                "tables": {
                    "newPairs": True,
                    "finalStretch": True,
                    "migrated": True
                },
                "filters": {
                    "newPairs": {
                        "marketCap": {"min": 100000, "max": 1000000},
                        "protocols": {"pump": True},
                        "liquidity": {"min": 50000}
                    }
                }
            }
        }
        ```

        ## Example:
        ```python
        async def on_pulse_data(data):
            print(f"Pulse: {data}")

        # Subscribe with default filters
        await ws.subscribe_pulse(on_pulse_data)

        # Subscribe with custom filters
        await ws.subscribe_pulse(on_pulse_data, user_state=custom_filters)
        ```
        """
        # Store user state for reconnection
        self._pulse_user_state = user_state

        # Store callback with "pulse" key
        self._callbacks["pulse"] = callback

        # Store subscription info for reconnection
        self._active_subscriptions["pulse"] = {
            "type": "pulse",
            "callback": callback,
            "user_state": user_state,
        }

        # Get user state configuration
        config = user_state if user_state else self._load_default_pulse_config()

        try:
            # Connect if not already connected
            if not self.ws:
                if not await self.connect():
                    self.logger.error("Failed to connect to Pulse WebSocket")
                    return False

            # Send initial user state configuration
            await self._send_json_message(config)
            self.logger.info("✅ Subscribed to Pulse analytics")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to subscribe to Pulse: {e}")
            return False
