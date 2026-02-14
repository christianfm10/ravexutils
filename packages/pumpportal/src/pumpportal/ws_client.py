import logging
import json
from typing import Any, Awaitable, Callable, TYPE_CHECKING
from shared_lib.baseclient.ws_client import WebSocketClient
from shared_lib.utils.notification import show_alert

if TYPE_CHECKING:
    from shared_lib.client_context import ClientContext

ROOM_NEW_TOKEN = "subscribeNewToken"
ROOM_MIGRATION = "subscribeMigration"
ROOM_ACCOUNT_TRADE = "subscribeAccountTrade"
ROOM_TOKEN_TRADE = "subscribeTokenTrade"

WS_PRIMARY_URL = "wss://pumpportal.fun/api/data"


class PumpPortalWSClient(WebSocketClient):
    """Singleton WebSocket client for PumpPortal API."""

    SUBS_METHOD = "subscribeNewToken"
    UNSUBS_METHOD = f"un{SUBS_METHOD}"
    HEADERS = {}

    WS_PUMP_PORTAL = "wss://pumpportal.fun/api/data"

    def __init__(self, context: "ClientContext | None" = None, **kwargs) -> None:
        """
        Initialize PumpPortal WebSocket client.

        ## Parameters:
        - `context` (ClientContext | None, optional): Shared client context.
            - **Recommended**: Pass configuration via context for cleaner API
            - Contains telegram_bot, log_level, and other shared dependencies
            - See `ClientContext` documentation for details

        - `**kwargs`: Additional keyword arguments passed to parent `WebSocketClient`.
            - Can override context values if needed
            - See `WebSocketClient.__init__` for complete parameter documentation

        ## Initialized Attributes:
        - Inherits all attributes from `WebSocketClient`
        - `_subs_mints` (list[str]): Tracked token mint addresses for trade monitoring
        - `_subs_accounts` (list[str]): Tracked account public keys for trade monitoring
        - `logger`: Specialized logger for "PumpPortalWSClient"

        ## Available Subscriptions:
        - **New Tokens**: `subscribe_new_token()` - Monitor newly created tokens
        - **Migrations**: `subscribe_migration()` - Track token migrations to Raydium
        - **Token Trades**: `subscribe_token_trade(keys=[...])` - Monitor specific token trades
        - **Account Trades**: `subscribe_account_trade(keys=[...])` - Monitor specific wallet trades

        ## Example:
        ```python
        from shared_lib.client_context import ClientContext
        from telegram.setup import TelegramBot

        # Modern approach - with context (recommended)
        tg_bot = TelegramBot()
        context = ClientContext(telegram_bot=tg_bot, log_level=logging.DEBUG)
        client = PumpPortalWSClient(context=context)

        # Legacy approach - still supported
        client = PumpPortalWSClient(telegram_bot=tg_bot, log_level=logging.DEBUG)

        # Usage
        await client.connect()
        await client.subscribe_new_token(my_callback)
        await client.start()
        ```

        ## Design Pattern:
        - Uses **ClientContext** for dependency injection (testable, flexible)
        - Inherits connection management from `WebSocketClient`
        - Automatically reconnects and restores subscriptions on disconnect
        - Thread-safe subscription tracking

        ## Notes:
        - Singleton pattern enabled by default
        - Fixed WebSocket URL: `wss://pumpportal.fun/api/data`
        - Subscription keys stored for reconnection recovery
        """
        # Only initialize once
        # if self._initialized:
        #     return

        super().__init__(context=context, ws_url=WS_PRIMARY_URL, **kwargs)
        self._subs_mints: list[str] = []
        self._subs_accounts: list[str] = []
        self.logger = logging.getLogger("PumpPortalWSClient")

    async def _route_message(self, room: str, data: dict[str, Any]) -> None:
        """
        Route message to appropriate callback based on room name.

        Implements the routing logic that maps room names to registered callbacks.
        Handles both direct room matches and pattern-based matches (token rooms).

        ## Algorithm:
        1. Check for direct room matches (new_pairs, migrations)
        2. If not matched, check if room starts with token prefix (b-)
        3. Extract token address from room name
        4. Find token-specific callback
        5. Execute matched callback with data

        ## Args:
        - `room` (str): Room/channel name from message
        - `data` (dict): Complete message data including room field

        ## Routing Rules:
        - **new_pairs** → callback["new_pairs"]
        - **migrations** → callback["migrations"]
        - **b-{address}** → callback["token_mcap_{address}"]

        ## Side Effects:
        - Executes matched callback function
        - Logs warning if no callback found for room

        ## Example:
        ```python
        # Message: {"room": "b-0x123...", "market_cap": 1000000}
        # Extracts: token_address = "0x123..."
        # Calls: await callbacks["token_mcap_0x123..."](data)
        ```
        """
        # Handle direct room matches
        if room == ROOM_NEW_TOKEN and ROOM_NEW_TOKEN in self._callbacks:
            await self._callbacks[ROOM_NEW_TOKEN](data)
            return
        if room == ROOM_MIGRATION and ROOM_MIGRATION in self._callbacks:
            await self._callbacks[ROOM_MIGRATION](data)
            return
        if room == ROOM_TOKEN_TRADE and ROOM_TOKEN_TRADE in self._callbacks:
            await self._callbacks[ROOM_TOKEN_TRADE](data)
            return
        if room == ROOM_ACCOUNT_TRADE and ROOM_ACCOUNT_TRADE in self._callbacks:
            await self._callbacks[ROOM_ACCOUNT_TRADE](data)
            return

    async def _message_handler(self, message: str) -> None:
        # Parse JSON message
        data = json.loads(message)
        if "message" in data:
            self.logger.info(data["message"])
        elif "name" in data:
            room = ROOM_NEW_TOKEN
            await self._route_message(room, data)
        elif "mint" in data and data.get("mint", "") in self._subs_mints:
            room = ROOM_TOKEN_TRADE
            await self._route_message(room, data)
        elif (
            "traderPublicKey" in data
            and data.get("traderPublicKey", "") in self._subs_accounts
        ):
            room = ROOM_ACCOUNT_TRADE
            await self._route_message(room, data)
        elif "txType" in data and data["txType"] == "migrate":
            room = ROOM_MIGRATION
            await self._route_message(room, data)
        else:
            self.logger.debug(f"No callback found for message: {data}")

    async def subscribe_new_token(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]]
    ):
        # Store subscription for reconnection
        self._active_subscriptions[ROOM_NEW_TOKEN] = {
            "callback": callback,
        }
        await self.subscribe_method(ROOM_NEW_TOKEN, callback)

    async def subscribe_migration(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]]
    ):
        self._active_subscriptions[ROOM_MIGRATION] = {
            "callback": callback,
        }
        await self.subscribe_method(ROOM_MIGRATION, callback)

    async def subscribe_account_trade(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]], keys: list = []
    ):
        self._subs_accounts.extend(keys)
        self._active_subscriptions[ROOM_ACCOUNT_TRADE] = {
            "callback": callback,
            "keys": self._subs_accounts,
        }
        await self.subscribe_method(ROOM_ACCOUNT_TRADE, callback, keys)

    async def add_token_trade_keys(self, keys: list = []):
        """
        Add keys to existing token trade subscription.
        """
        subscription = self._active_subscriptions.get(ROOM_TOKEN_TRADE, {})
        if subscription:
            self._subs_mints.extend(keys)
            self._active_subscriptions[ROOM_TOKEN_TRADE]["keys"] = self._subs_mints
            await self.subscribe_method(
                ROOM_TOKEN_TRADE,
                self._active_subscriptions[ROOM_TOKEN_TRADE]["callback"],
                keys,
            )
        else:
            self.logger.warning(
                "No active token trade subscription found to update. Please subscribe first."
            )

    async def remove_token_trade_keys(self, keys: list = []):
        """
        Remove keys from existing token trade subscription.
        """
        subscription = self._active_subscriptions.get(ROOM_TOKEN_TRADE, {})
        if subscription:
            self._subs_mints = [k for k in self._subs_mints if k not in keys]
            self._active_subscriptions[ROOM_TOKEN_TRADE]["keys"] = self._subs_mints
            await self.unsubscribe_method(f"un{ROOM_TOKEN_TRADE}", keys)
        else:
            self.logger.warning(
                "No active token trade subscription found to update. Please subscribe first."
            )

    async def subscribe_token_trade(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]], keys: list = []
    ):
        self._subs_mints.extend(keys)
        self._active_subscriptions[ROOM_TOKEN_TRADE] = {
            "callback": callback,
            "keys": self._subs_mints,
        }
        await self.subscribe_method(ROOM_TOKEN_TRADE, callback, keys)

    async def unsubscribe_token_trade(self, keys: list = []) -> bool:
        """
        Unsubscribe from token trade updates.

        Leaves the token trade room to stop receiving token trade updates.
        Useful for managing subscriptions and reducing message volume.

        ## Args:
        - `keys` (list, optional): List of keys to specify which token trades to unsubscribe from. Defaults to an empty list.

        ## Returns:
        - `bool`: True if unsubscribe successful, False otherwise

        ## Side Effects:
        - Sends "leave" action to WebSocket server
        - Removes callback from internal registry

        ## Example:
        ```python
        # Subscribe to token trade
        await ws.subscribe_token_trade(callback)

        # Later, unsubscribe when no longer needed
        await ws.unsubscribe_token_trade()
        ```
        """
        if await self.unsubscribe_method(f"un{ROOM_TOKEN_TRADE}", keys):
            self._subs_mints = [k for k in self._subs_mints if k not in keys]
            return True
        return False

    async def unsubscribe_account_trade(self, keys: list = []) -> bool:
        """
        Unsubscribe from account trade updates.

        Leaves the account trade room to stop receiving account trade updates.
        Useful for managing subscriptions and reducing message volume.

        ## Args:
        - None

        ## Returns:
        - `bool`: True if unsubscribe successful, False otherwise

        ## Side Effects:
        - Sends "leave" action to WebSocket server
        - Removes callback from internal registry

        ## Example:
        ```python
        # Subscribe to account trade
        await ws.subscribe_account_trade(callback)

        # Later, unsubscribe when no longer needed
        await ws.unsubscribe_account_trade()
        ```
        """
        if await self.unsubscribe_method(f"un{ROOM_ACCOUNT_TRADE}", keys):
            self._subs_accounts = [k for k in self._subs_accounts if k not in keys]
            return True
        return False
        # Build room name

    async def unsubscribe_migration(self) -> bool:
        """
        Unsubscribe from migration updates.

        Leaves the migrations room to stop receiving migration updates.
        Useful for managing subscriptions and reducing message volume.

        ## Args:
        - None

        ## Returns:
        - `bool`: True if unsubscribe successful, False otherwise

        ## Side Effects:
        - Sends "leave" action to WebSocket server
        - Removes callback from internal registry

        ## Example:
        ```python
        # Subscribe to migrations
        await ws.subscribe_migration(callback)

        # Later, unsubscribe when no longer needed
        await ws.unsubscribe_migration()
        ```
        """
        return await self.unsubscribe_method(ROOM_MIGRATION)
        # Build room name

    async def unsubscribe_new_token(self) -> bool:
        """
        Unsubscribe from market cap updates for a specific token.

        Leaves the token-specific room to stop receiving market cap updates.
        Useful for managing subscriptions and reducing message volume.

        ## Args:
        - `token_address` (str): Token contract address to unsubscribe from

        ## Returns:
        - `bool`: True if unsubscribe successful, False otherwise

        ## Side Effects:
        - Sends "leave" action to WebSocket server
        - Removes callback from internal registry

        ## Example:
        ```python
        # Subscribe to token
        await ws.subscribe_token_mcap(token, callback)

        # Later, unsubscribe when no longer needed
        await ws.unsubscribe_token_mcap(token)
        ```
        """
        return await self.unsubscribe_method(ROOM_NEW_TOKEN)

    async def _send_notification(self, message: str) -> None:
        show_alert(title="PumpPortal Notification", message=message)
        if self._telegram_bot is not None:
            await self._telegram_bot.send_message(message)


pf_ws_client = PumpPortalWSClient()
