import json
import logging
from typing import Any, Awaitable, Callable, Dict, Optional, TYPE_CHECKING

from shared_lib.baseclient.ws_client import WebSocketClient
from shared_lib.utils.notification import show_alert
from ..urls import WSBaseUrls, EucalyptusEndpoint

if TYPE_CHECKING:
    from telegram import TelegramBot

# WebSocket URL for Axiom cluster
WS_CLUSTER_URL = WSBaseUrls.WS_EUCALYPTUS_URL


class EucalyptusClient(WebSocketClient):
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

    ENDPOINT = EucalyptusEndpoint.endpoint

    HEADERS = {
        "Origin": f"https://{ENDPOINT.domain}",
        "Host": ENDPOINT.host,
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
            ws_url=self.endpoint.str_url,
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

            # Route message to appropriate callback
            await self._route_message("test", data)

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

    async def sub_test(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> None:
        """
        Test subscription method for demonstration.

        ## Parameters:
        - `callback`: Async callback function to handle incoming messages
        """
        self._active_subscriptions["test"] = {
            "callback": callback,
        }
        self._callbacks["test"] = callback
        # Example subscription logic (replace with actual subscription code)
        # await self._send_notification("Subscribed to test channel")
        # Simulate receiving a message
        # test_message = {"room": "new_pairs", "data": {"pair_address": "0x123..."}}
        # await self._route_message(test_message["room"], test_message["data"])

    async def _send_json_message(self, message: dict[str, Any]) -> None:
        return

    async def _build_subscribe_message(self, method: str, **kwargs) -> Dict[str, Any]:
        return {}

    async def _build_unsubscribe_message(self, method: str, **kwargs) -> Dict[str, Any]:
        return {}
