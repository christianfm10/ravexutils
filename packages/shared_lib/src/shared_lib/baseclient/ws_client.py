import asyncio
import logging
import json
from abc import ABC, abstractmethod
from typing import Any, Awaitable, Callable, Optional, TYPE_CHECKING
import aiohttp
from shared_lib.baseclient.aiohttp_client import BaseAioHttpClient

if TYPE_CHECKING:
    from telegram import TelegramBot
    from shared_lib.client_context import ClientContext

WS_PRIMARY_URL = "wss://pumpportal.fun/api/data"


class WebSocketClient(ABC):
    HEADERS = {}

    def __init__(
        self,
        context: Optional["ClientContext"] = None,
        log_level: Optional[int] = None,
        ws_url: str = WS_PRIMARY_URL,
        telegram_bot: Optional["TelegramBot"] = None,
        client: Optional["BaseAioHttpClient"] = None,
    ) -> None:
        """
        Initialize WebSocket client with connection and notification settings.

        ## Parameters:
        - `context` (ClientContext | None, optional): Shared client context with dependencies.
            - **Recommended approach**: Pass all shared config via context
            - If provided, extracts `telegram_bot` and `log_level` from context
            - Individual parameters override context values
            - See `ClientContext` documentation for details

        - `log_level` (int | None, optional): Logging level for client operations.
            - Default: `logging.INFO` (or from context)
            - Options: `logging.DEBUG`, `logging.INFO`, `logging.WARNING`, `logging.ERROR`
            - Overrides context.log_level if both provided

        - `ws_url` (str, optional): WebSocket server URL to connect to.
            - Default: `WS_PRIMARY_URL` ("wss://pumpportal.fun/api/data")
            - Must be a valid WSS (secure WebSocket) URL

        - `telegram_bot` (TelegramBot | None, optional): Telegram bot instance for notifications.
            - Default: `None` (or from context)
            - Overrides context.telegram_bot if both provided
            - **Deprecated**: Use `context` parameter instead for cleaner API

        ## Initialized Attributes:
        - `ws_url`: Stored WebSocket URL
        - `ws`: WebSocket connection (initially None)
        - `_callbacks`: Registry for message routing callbacks
        - `logger`: Logger instance for debugging
        - `_telegram_bot`: Optional Telegram bot for notifications

        ## Example:
        ```python
        from shared_lib.client_context import ClientContext
        from telegram.setup import TelegramBot

        # Modern approach - with context (recommended)
        tg_bot = TelegramBot()
        context = ClientContext(telegram_bot=tg_bot, log_level=logging.DEBUG)
        client = WebSocketClient(context=context)

        # Legacy approach - direct parameters (still supported)
        client = WebSocketClient(
            log_level=logging.DEBUG,
            telegram_bot=tg_bot
        )

        # Override context values
        client = WebSocketClient(
            context=context,
            log_level=logging.WARNING  # Override context log_level
        )
        ```

        ## Migration Guide:
        ```python
        # Before:
        client = WebSocketClient(
            telegram_bot=tg_bot,
            log_level=logging.DEBUG
        )

        # After:
        context = ClientContext(
            telegram_bot=tg_bot,
            log_level=logging.DEBUG
        )
        client = WebSocketClient(context=context)
        ```
        """
        # Extract values from context if provided, allow individual params to override
        effective_log_level = (
            log_level
            if log_level is not None
            else (context.log_level if context else logging.INFO)
        )
        effective_telegram_bot = (
            telegram_bot
            if telegram_bot is not None
            else (context.telegram_bot if context else None)
        )

        self.ws_url = ws_url
        self.ws: Any = None  # Main WebSocket for regular channels
        self._callbacks: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {}
        # Setup logger for debugging and monitoring
        self.logger = logging.getLogger("WebSocketClient")
        self.logger.setLevel(effective_log_level)

        # Reconnection configuration
        self._max_reconnect_attempts = 5
        self._reconnect_delay_seconds = 5
        self._is_reconnecting = False
        #
        # Store subscriptions for reconnection
        self._active_subscriptions: dict[str, Any] = {}

        # Initialize Telegram bot if provided
        self._telegram_bot = effective_telegram_bot

        # Store HTTP client or configuration for lazy initialization
        self._http_client = client
        self._http_client_config = {
            "base_url": WS_PRIMARY_URL,
        }
        # Session will be created when first needed
        self._session: Any = None

    async def start(self) -> None:
        """
        Start the WebSocket client and begin processing messages.

        Ensures connection is established and then enters the message handler loop.
        This method blocks until the WebSocket connection is closed.

        ## Process:
        1. Check if connection exists
        2. If not connected, attempt to connect
        3. Enter message handler loop (blocks here)
        4. Return when connection closes or error occurs

        ## Returns:
        - None (blocks until connection closes)

        ## Side Effects:
        - Establishes WebSocket connection if needed
        - Processes all incoming messages
        - Executes registered callbacks
        - Blocks the current task

        ## Usage:
        ```python
        # Setup client and subscriptions
        ws = AxiomTradeWebSocketClient(auth)
        await ws.connect()
        await ws.subscribe_new_tokens(callback)

        # Start processing messages (blocks)
        await ws.start()

        # Code here runs after connection closes
        print("WebSocket closed")
        ```

        ## Note:
        This is typically the last call in your async function as it blocks
        until the WebSocket closes. Consider running in a background task
        if you need concurrent operations.
        """
        # Ensure connection exists
        if not self.ws:
            if not await self.connect():
                self.logger.error("Cannot start: connection failed")
                return

        # Enter message processing loop (blocks here)
        await self._connection_handler()

    async def close(self) -> None:
        """
        Close all WebSocket connections gracefully.

        Sends close frame to servers and cleans up connection resources.
        Also closes the aiohttp session if it was created by this client.

        ## Side Effects:
        - Closes main WebSocket connection
        - Closes aiohttp session if owned by this client
        - Logs closure events
        - Stops message handler loops

        ## Example:
        ```python
        try:
            await ws.start()  # Blocks while processing
        finally:
            await ws.close()  # Always close all connections
        ```
        """
        # Close main WebSocket
        if self.ws:
            await self.ws.close()
            self.logger.info(f"✅ Main {self.__class__.__name__} connection closed")

        # Close session if we created it (not provided by user)
        if self._session is not None and self._http_client is None:
            await self._session.close()
            self._session = None
            self.logger.debug("Closed aiohttp session")

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure aiohttp session is created (lazy initialization)."""
        if self._session is None:
            if self._http_client is not None:
                # Use provided client's session
                self._session = self._http_client.session
            else:
                # Create new session
                self._session = aiohttp.ClientSession()
                self.logger.debug("Created new aiohttp session for WebSocket")
        return self._session

    async def connect(self) -> bool:
        """
        Establish WebSocket connection to server.

        Uses aiohttp for WebSocket connections with support for custom headers
        and proxy configuration.

        ## Process:
        1. Ensure aiohttp session is initialized
        2. Attempt WebSocket connection
        3. Handle authentication and connection errors

        ## Returns:
        - `bool`: True if connection successful, False otherwise

        ## Headers:
        - Custom headers from self.HEADERS
        - Supports authentication tokens in headers

        ## Error Handling:
        - Checks for HTTP 401 (authentication failure)
        - Logs detailed error information
        - Returns False on any connection error

        ## Side Effects:
        - Sets self.ws to connected WebSocket instance
        - Logs connection attempts and results

        ## Example:
        ```python
        if await ws.connect():
            print("Connected successfully")
        else:
            print("Connection failed")
        ```
        """
        try:
            # Ensure session exists
            session = await self._ensure_session()

            # Attempt WebSocket connection using aiohttp
            self.logger.info(f"Attempting to connect to WebSocket: {self.ws_url}")
            self.ws = await session.ws_connect(
                self.ws_url,
                headers=self.HEADERS,
                # timeout=aiohttp.ClientWSTimeout(ws_receive=5),  # Connection timeout
                # heartbeat=30,
            )
            self.logger.info(f"✅ Connected to {self.ws_url} server")

            return True

        except aiohttp.WSServerHandshakeError as e:
            # Handle WebSocket handshake errors
            if e.status == 401:
                self.logger.error(
                    "❌ WebSocket authentication failed - invalid or missing tokens"
                )
                self.logger.error(
                    "Please check that your tokens are valid and not expired"
                )
            else:
                self.logger.error(
                    f"❌ WebSocket handshake failed: status={e.status}, message={e.message}"
                )
            self.logger.error(f"Error details: {e}")
            return False

        except aiohttp.ClientError as e:
            self.logger.error(f"❌ Failed to connect to WebSocket: {e}")
            return False

        except Exception as e:
            self.logger.error(f"❌ Unexpected error connecting to WebSocket: {e}")
            return False

    @abstractmethod
    async def _message_handler(self, message: str) -> None:
        """Parse and handle incoming WebSocket messages.

        Subclasses must implement this to handle protocol-specific message formats.

        ## Args:
        - `message` (str): Raw message string from WebSocket
        """
        ...

    @abstractmethod
    async def _send_notification(self, message: str) -> None:
        """Send notification to user via configured channels.

        Subclasses must implement this to handle notifications.

        ## Args:
        - `message` (str): Notification message to send
        """
        ...

    @abstractmethod
    async def _build_subscribe_message(self, method: str, **kwargs) -> dict[str, Any]:
        """Build protocol-specific subscription message.

        Subclasses must implement this to build subscription messages
        according to their WebSocket protocol.

        ## Args:
        - `method` (str): Subscription method/channel name
        - `**kwargs`: Protocol-specific parameters (e.g., keys, params, etc.)

        ## Returns:
        - `dict`: Message dictionary to be JSON-serialized and sent

        ## Examples:
        ```python
        # PumpPortal format
        {"method": "subscribeNewToken", "keys": []}

        # Solana RPC format
        {"jsonrpc": "2.0", "id": 1, "method": "accountSubscribe", "params": [...]}

        # Generic room-based format
        {"action": "subscribe", "room": "trades", "filters": {...}}
        ```
        """
        ...

    @abstractmethod
    async def _build_unsubscribe_message(self, method: str, **kwargs) -> dict[str, Any]:
        """Build protocol-specific unsubscription message.

        Subclasses must implement this to build unsubscription messages
        according to their WebSocket protocol.

        ## Args:
        - `method` (str): Unsubscription method/channel name
        - `**kwargs`: Protocol-specific parameters

        ## Returns:
        - `dict`: Message dictionary to be JSON-serialized and sent
        """
        ...

    async def _connection_handler(self) -> None:
        """
        Handle incoming WebSocket messages in continuous loop.

        Receives messages from WebSocket, parses JSON, identifies the room/channel,
        and routes to the appropriate callback function.

        ## Process:
        1. Loop over incoming messages asynchronously
        2. Parse JSON message
        3. Extract room identifier
        4. Match room to registered callback
        5. Execute callback with message data

        ## Message Routing:
        - **new_pairs**: Direct room match
        - **migrations**: Direct room match
        - **b-{address}**: Token-specific room (extracts address from room name)

        ## Error Handling:
        - Catches JSON parsing errors (logs and continues)
        - Catches callback execution errors (logs and continues)
        - Handles WebSocket connection close gracefully
        - Logs all errors with context for debugging

        ## Design Decisions:
        - Runs in infinite loop until connection closes
        - Non-blocking: errors in one message don't stop processing
        - Flexible callback routing based on room naming patterns
        - Logs warnings for rooms without registered callbacks

        ## Side Effects:
        - Executes callbacks (may have their own side effects)
        - Logs message processing events
        - Blocks until WebSocket connection closes

        ## Example Message Flow:
        ```
        1. Receive: {"room": "new_pairs", "pair_address": "0x..."}
        2. Parse JSON
        3. Extract room: "new_pairs"
        4. Find callback: self._callbacks["new_pairs"]
        5. Execute: await callback(data)
        ```
        """
        if not self.ws:
            self.logger.error("Cannot handle messages: WebSocket not connected")
            return

        try:
            # Async iteration over WebSocket messages using aiohttp
            async for msg in self.ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    try:
                        print(msg)
                        print(msg.data)
                        await self._message_handler(msg.data)

                    except json.JSONDecodeError as e:
                        self.logger.error(
                            f"Failed to parse WebSocket message as JSON: {msg.data[:100]}..."
                        )
                        self.logger.debug(f"JSON decode error: {e}")

                    except Exception as e:
                        self.logger.error(
                            f"Error handling WebSocket message: {e}", exc_info=True
                        )

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    self.logger.error(f"WebSocket error: {self.ws.exception()}")
                    break

                elif msg.type in (
                    aiohttp.WSMsgType.CLOSE,
                    aiohttp.WSMsgType.CLOSING,
                    aiohttp.WSMsgType.CLOSED,
                ):
                    self.logger.warning(f"WebSocket closing: {msg.type}")
                    break
            self.logger.warning(f"Connection ended. Close code: {self.ws.close_code}")

        except aiohttp.ClientError as e:
            self.logger.warning(
                f"⚠️ {self.__class__.__name__} WebSocket connection error: {e}"
            )

            # Send Telegram notification about disconnection
            await self._send_notification(
                f"⚠️ <b>WebSocket {self.__class__.__name__} Disconnected</b>\n"
                f"Connection: main\n"
                f"Error: {str(e)}\n"
                f"Status: Attempting reconnection..."
            )

            # Attempt to reconnect
            if await self._reconnect(connection_type="main"):
                self.logger.info(
                    f"✅ {self.__class__.__name__} WebSocket reconnected, resuming message handling"
                )
                # Recursively restart handler after successful reconnection
                await self._connection_handler()
            else:
                self.logger.error(
                    f"❌ Failed to reconnect {self.__class__.__name__} WebSocket"
                )

        except Exception as e:
            self.logger.error(f"❌ WebSocket message handler error: {e}", exc_info=True)

    async def subscribe_method(
        self,
        method: str,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        **kwargs,
    ) -> bool:
        """Generic subscription method that uses protocol-specific message builder.

        ## Args:
        - `method` (str): Subscription method/channel name
        - `callback` (Callable): Async callback function to handle messages
        - `**kwargs`: Protocol-specific parameters passed to _build_subscribe_message

        ## Returns:
        - `bool`: True if subscription successful, False otherwise
        """
        if not self.ws:
            if not await self.connect():
                return False
        # Register callback
        self._callbacks[method] = callback
        try:
            # Build protocol-specific message
            message = await self._build_subscribe_message(method, **kwargs)
            # Send JSON message to server
            await self._send_json_message(message)
            keys_info = (
                f" with keys: {kwargs.get('keys', [])}" if "keys" in kwargs else ""
            )
            self.logger.info(f"✅ Subscribed to {method}{keys_info}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Failed to subscribe to {method}: {e}")
            return False

    async def unsubscribe_method(self, method: str, **kwargs) -> bool:
        """Generic unsubscription method that uses protocol-specific message builder.

        ## Args:
        - `method` (str): Unsubscription method/channel name
        - `**kwargs`: Protocol-specific parameters passed to _build_unsubscribe_message

        ## Returns:
        - `bool`: True if unsubscription successful, False otherwise
        """
        # Remove callback from registry
        self._callbacks.pop(method, None)

        try:
            # Build protocol-specific message
            message = await self._build_unsubscribe_message(method, **kwargs)
            # Send JSON message to server
            await self._send_json_message(message)
            keys_info = f" {kwargs.get('keys', [])}" if "keys" in kwargs else ""
            self.logger.info(f"✅ Unsubscribed{keys_info} from {method} updates")
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to unsubscribe from {method} updates: {e}")
            return False

    async def _send_json_message(self, message: dict[str, Any]) -> None:
        """Send JSON message to WebSocket server.

        Generic method to send any message dictionary as JSON to the WebSocket.
        Used by subscribe/unsubscribe methods after building protocol-specific messages.

        ## Args:
        - `message` (dict): Message dictionary to JSON-serialize and send

        ## Raises:
        - `RuntimeError`: If WebSocket is not connected
        """
        if not self.ws:
            raise RuntimeError("WebSocket not connected")

        await self.ws.send_json(message)

    async def _reconnect(self, connection_type: str = "main") -> bool:
        """
        Attempt to reconnect to WebSocket with exponential backoff.

        ## Parameters
        - `connection_type`: Type of connection to reconnect ("main" or "pulse")

        ## Returns
        - `bool`: True if reconnection successful, False otherwise

        ## Reconnection Strategy
        1. Close existing connections
        2. Wait with exponential backoff
        3. Attempt to reconnect
        4. Restore all active subscriptions
        5. Retry up to max_reconnect_attempts

        ## Design Notes
        Uses exponential backoff to avoid overwhelming the server.
        Automatically restores all subscriptions that were active before disconnect.
        """
        if self._is_reconnecting:
            self.logger.debug("Reconnection already in progress")
            return False

        self._is_reconnecting = True

        try:
            for attempt in range(1, self._max_reconnect_attempts + 1):
                self.logger.info(
                    f"🔄 Reconnection attempt {attempt}/{self._max_reconnect_attempts} "
                    f"for {connection_type} WebSocket..."
                )

                # Wait with exponential backoff
                if attempt > 1:
                    delay = self._reconnect_delay_seconds * (2 ** (attempt - 2))
                    self.logger.info(f"Waiting {delay} seconds before retry...")
                    await asyncio.sleep(delay)

                try:
                    # Close existing connection if any
                    if self.ws:
                        await self.ws.close()
                        self.ws = None

                    # Attempt reconnection
                    success = await self.connect()

                    if not success:
                        continue

                    # Restore subscriptions for main connection
                    self.logger.info("Restoring subscriptions...")
                    for room, sub_info in self._active_subscriptions.items():
                        try:
                            # Build subscription message using protocol-specific builder
                            # Extract kwargs from sub_info (excluding callback)
                            kwargs = {
                                k: v for k, v in sub_info.items() if k != "callback"
                            }
                            message = await self._build_subscribe_message(
                                room, **kwargs
                            )
                            await self._send_json_message(message)
                            self.logger.info(f"✅ Restored subscription: {room}")
                        except Exception as e:
                            self.logger.error(
                                f"Failed to restore subscription {room}: {e}"
                            )

                    self.logger.info(
                        f"✅ Successfully reconnected {connection_type} WebSocket"
                    )

                    # Send Telegram notification about successful reconnection
                    await self._send_notification(
                        f"✅ <b>WebSocket {self.__class__.__name__} Reconnected</b>\n"
                        f"Connection: {connection_type}\n"
                        f"Status: Successfully restored after {attempt} attempt(s)"
                    )

                    return True

                except Exception as e:
                    self.logger.error(
                        f"Reconnection attempt {attempt} failed: {e}",
                        exc_info=(attempt == self._max_reconnect_attempts),
                    )

            self.logger.error(
                f"❌ Failed to reconnect after {self._max_reconnect_attempts} attempts"
            )
            return False

        finally:
            self._is_reconnecting = False
