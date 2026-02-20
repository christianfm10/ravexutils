"""Solana RPC WebSocket Client.

Provides WebSocket connection to Solana RPC nodes for real-time blockchain data.
Implements the generic WebSocketClient interface with Solana JSON-RPC 2.0 protocol.
"""

import logging
import json
from typing import Any, Awaitable, Callable, TYPE_CHECKING
from shared_lib.baseclient.ws_client import WebSocketClient
from shared_lib.utils.notification import show_alert

if TYPE_CHECKING:
    from shared_lib.client_context import ClientContext


class SolanaRPCWSClient(WebSocketClient):
    """WebSocket client for Solana RPC using JSON-RPC 2.0 protocol.

    Supports real-time subscriptions for:
    - Account changes (accountSubscribe)
    - Program accounts (programSubscribe)
    - Signature notifications (signatureSubscribe)
    - Slot changes (slotSubscribe)
    - Root changes (rootSubscribe)

    ## Example:
    ```python
    from rpc.ws_client import SolanaRPCWSClient
    from shared_lib.client_context import ClientContext

    async def on_account_change(data):
        print(f"Account updated: {data}")

    # Initialize client
    context = ClientContext(log_level=logging.INFO)
    client = SolanaRPCWSClient(
        context=context,
        ws_url="wss://api.mainnet-beta.solana.com"
    )

    # Connect and subscribe
    await client.connect()
    await client.subscribe_account(
        callback=on_account_change,
        account="YourAccountPubkey...",
        commitment="confirmed"
    )
    await client.start()
    ```
    """

    def __init__(
        self,
        context: "ClientContext | None" = None,
        ws_url: str = "wss://api.mainnet-beta.solana.com",
        **kwargs,
    ) -> None:
        """Initialize Solana RPC WebSocket client.

        ## Parameters:
        - `context` (ClientContext | None): Shared client context
        - `ws_url` (str): Solana RPC WebSocket URL
        - `**kwargs`: Additional parameters passed to WebSocketClient
        """
        super().__init__(context=context, ws_url=ws_url, **kwargs)
        self.logger = logging.getLogger("SolanaRPCWSClient")
        self._request_id = 0
        # Map subscription IDs to callbacks
        self._subscription_callbacks: dict[int, Callable] = {}
        # Map method names to subscription IDs for unsubscribing
        self._method_to_sub_id: dict[str, int] = {}

    def _get_next_id(self) -> int:
        """Get next request ID for JSON-RPC messages."""
        self._request_id += 1
        return self._request_id

    async def _build_subscribe_message(self, method: str, **kwargs) -> dict[str, Any]:
        """Build Solana JSON-RPC 2.0 subscription message.

        ## Solana RPC format:
        ```json
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "accountSubscribe",
            "params": ["account_pubkey", {"commitment": "confirmed"}]
        }
        ```

        ## Args:
        - `method` (str): RPC method name (e.g., "accountSubscribe")
        - `**kwargs`: Contains 'params' list with subscription parameters

        ## Returns:
        - `dict`: JSON-RPC 2.0 formatted message
        """
        params = kwargs.get("params", [])
        request_id = self._get_next_id()

        return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}

    async def _build_unsubscribe_message(self, method: str, **kwargs) -> dict[str, Any]:
        """Build Solana JSON-RPC 2.0 unsubscription message.

        ## Solana RPC format:
        ```json
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "accountUnsubscribe",
            "params": [subscription_id]
        }
        ```

        ## Args:
        - `method` (str): RPC unsubscribe method (e.g., "accountUnsubscribe")
        - `**kwargs`: Contains 'subscription_id' for the subscription to cancel

        ## Returns:
        - `dict`: JSON-RPC 2.0 formatted unsubscribe message
        """
        subscription_id = kwargs.get("subscription_id")
        request_id = self._get_next_id()

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": [subscription_id],
        }

    async def _message_handler(self, message: str) -> None:
        """Parse and route Solana RPC messages.

        Handles two types of messages:
        1. Subscription confirmation (contains "result" with subscription ID)
        2. Notification (contains "params" with subscription data)
        """
        data = json.loads(message)

        # Handle subscription confirmation
        if "result" in data and "id" in data:
            subscription_id: int = data["result"]
            request_id = data["id"]
            self.logger.info(
                f"Subscription confirmed: ID={subscription_id}, RequestID={request_id}"
            )
            return

        # Handle subscription notification
        if "method" in data and "params" in data:
            method: str = data["method"]
            params = data["params"]
            method = method.replace("Notification", "Subscribe")
            callback = self._active_subscriptions.get(method, {}).get("callback")
            if callback:
                await callback(params)
            else:
                self.logger.warning(f"No callback registered for subscription {method}")
            return

            # Extract subscription ID and result
            if isinstance(params, dict):
                subscription_id: int = params.get("subscription", -1)
                result = params.get("result")

                # Route to callback if registered
                callback = self._subscription_callbacks.get(subscription_id)
                if callback:
                    await callback(result)
                else:
                    self.logger.debug(f"No callback for subscription {subscription_id}")
            return

        # Handle errors
        if "error" in data:
            self.logger.error(f"RPC Error: {data['error']}")
            return

        self.logger.debug(f"Unhandled message: {data}")

    async def _send_notification(self, message: str) -> None:
        """Send notification via system alert and Telegram."""
        show_alert(title="Solana RPC Notification", message=message)
        if self._telegram_bot is not None:
            await self._telegram_bot.send_message(message)

    # High-level subscription methods

    async def subscribe_account(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        account: str,
        commitment: str = "confirmed",
        encoding: str = "jsonParsed",
    ) -> bool:
        """Subscribe to account changes.

        ## Args:
        - `callback`: Async function to handle account updates
        - `account`: Account public key to monitor
        - `commitment`: Commitment level ("processed", "confirmed", "finalized")
        - `encoding`: Data encoding ("jsonParsed", "base64", "base58")

        ## Returns:
        - `bool`: True if subscription successful
        """
        method = "accountSubscribe"
        params = [account, {"commitment": commitment, "encoding": encoding}]
        self._active_subscriptions[method] = {
            "callback": callback,
            "params": params,
        }
        return await self.subscribe_method(method, callback, params=params)

    async def subscribe_program(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        program_id: str,
        commitment: str = "confirmed",
        encoding: str = "jsonParsed",
        filters: list[dict] | None = None,
    ) -> bool:
        """Subscribe to all accounts owned by a program.

        ## Args:
        - `callback`: Async function to handle program account updates
        - `program_id`: Program ID to monitor
        - `commitment`: Commitment level
        - `encoding`: Data encoding
        - `filters`: Optional filters for accounts

        ## Returns:
        - `bool`: True if subscription successful
        """
        method = "programSubscribe"
        config: dict[str, Any] = {"commitment": commitment, "encoding": encoding}
        if filters:
            config["filters"] = filters

        params = [program_id, config]
        self._active_subscriptions[method] = {
            "callback": callback,
            "params": params,
        }
        return await self.subscribe_method(method, callback, params=params)

    async def subscribe_signature(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        signature: str,
        commitment: str = "confirmed",
    ) -> bool:
        """Subscribe to signature status updates.

        ## Args:
        - `callback`: Async function to handle signature status
        - `signature`: Transaction signature to monitor
        - `commitment`: Commitment level

        ## Returns:
        - `bool`: True if subscription successful
        """
        method = "signatureSubscribe"
        params = [signature, {"commitment": commitment}]
        self._active_subscriptions[method] = {
            "callback": callback,
            "params": params,
        }
        return await self.subscribe_method(method, callback, params=params)

    async def subscribe_slot(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> bool:
        """Subscribe to slot changes.

        ## Args:
        - `callback`: Async function to handle slot updates

        ## Returns:
        - `bool`: True if subscription successful
        """
        method = "slotSubscribe"
        self._active_subscriptions[method] = {
            "callback": callback,
            "params": [],
        }
        return await self.subscribe_method(method, callback, params=[])

    async def subscribe_root(
        self, callback: Callable[[dict[str, Any]], Awaitable[None]]
    ) -> bool:
        """Subscribe to root changes (finalized slots).

        ## Args:
        - `callback`: Async function to handle root updates

        ## Returns:
        - `bool`: True if subscription successful
        """
        method = "rootSubscribe"
        self._active_subscriptions[method] = {
            "callback": callback,
            "params": [],
        }
        return await self.subscribe_method(method, callback, params=[])


# Global singleton instance
solana_rpc_ws_client = SolanaRPCWSClient()
