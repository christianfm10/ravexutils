"""Solana RPC WebSocket Client.

Provides WebSocket connection to Solana RPC nodes for real-time blockchain data.
Implements the generic WebSocketClient interface with Solana JSON-RPC 2.0 protocol.
"""

import logging
import json
import os
from typing import Any, Awaitable, Callable, TYPE_CHECKING, Literal
from pumpportal.trade import PUMPPORTAL_API_KEY
from shared_lib.baseclient.ws_client import WebSocketClient
from shared_lib.utils.notification import show_alert
from yarl import URL
from shared_lib.baseclient.endpoint import Endpoint

if TYPE_CHECKING:
    from shared_lib.client_context import ClientContext


class PumpportalEndpoint:
    base_url = URL("wss://api.mainnet-beta.solana.com")
    endpoint = Endpoint.from_url(url=base_url)


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

    ENDPOINT = PumpportalEndpoint.endpoint

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

        rpc_ws_url = os.getenv("RPC_WS_URL")
        rpc_api_key = os.getenv("RPC_API_KEY")
        if rpc_ws_url and rpc_api_key:
            self.endpoint = Endpoint.from_url(f"{rpc_ws_url}?api-key={rpc_api_key}")
            logging.info(f"Using RPC URL from environment: {ws_url}")
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
        method, request_id = method.split("|") if "|" in method else (method, None)

        if not request_id:
            self.logger.warning(
                "Method name does not contain request ID. Consider using method|request_id format for better tracking."
            )
            request_id = self._get_next_id()
        # request_id = self._get_next_id()

        return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}

    async def _build_unsubscribe_message(self, method: str, **kwargs) -> dict[str, Any]:
        """Build Solana JSON-RPC 2.0 unsubscription message.

        ## Solana RPC format:
        ```json
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "accountUnsubscribe",
            "params": subscription_ids
        }
        ```

        ## Args:
        - `method` (str): RPC unsubscribe method (e.g., "accountUnsubscribe")
        - `**kwargs`: Contains 'subscription_ids' for the subscriptions to cancel

        ## Returns:
        - `dict`: JSON-RPC 2.0 formatted unsubscribe message
        """
        subscription_ids = kwargs.get("subscription_ids")
        request_id = self._get_next_id()

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": subscription_ids,
        }

    async def _message_handler(self, message: str) -> None:
        """Parse and route Solana RPC messages.

        Handles two types of messages:
        1. Subscription confirmation (contains "result" with subscription ID)
        2. Notification (contains "params" with subscription data)
        """
        data = json.loads(message)

        # Handle subscription confirmation
        # if "result" in data and "id" in data:
        #     subscription_id: int = data["result"]
        #     request_id = data["id"]
        #     method_id = f"{data.get('method', 'unknown')}|{request_id}"
        #     self._active_subscriptions[method_id]["subscription_id"] = subscription_id
        #     self.logger.info(
        #         f"Subscription confirmed: ID={subscription_id}, RequestID={request_id}"
        #     )
        #     return

        # Handle subscription notification
        if "method" in data and "params" in data:
            method: str = data["method"]
            params = data["params"]
            method = method.replace("Notification", "Subscribe")
            # method_id = f"{method}|{data.get('id', 'unknown')}"
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

    async def subscribe_logs(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        filter: dict[str, Any] | Literal["all", "allWithVotes"] | None = None,
        commitment: str = "confirmed",
        mentions: str | None = None,
    ) -> bool:
        """Subscribe to log messages.

        ## Args:
        - `callback`: Async function to handle log messages
        - `filter`: Optional filter for log messages
        - `commitment`: Commitment level
        - `mentions`: Optional mentions filter

        ## Returns:
        - `bool`: True if subscription successful
        """
        method = "logsSubscribe"
        config: dict[str, Any] = {"commitment": commitment}

        # Solana/Helius logsSubscribe expects params as:
        # ["all" | "allWithVotes" | {"mentions": [<pubkey>]}, {"commitment": ...}]
        if filter is not None:
            log_filter: dict[str, Any] | Literal["all", "allWithVotes"] = filter
            if mentions is not None:
                self.logger.warning(
                    "Both 'filter' and 'mentions' were provided. 'mentions' is ignored because 'filter' takes precedence."
                )
        elif mentions is not None:
            log_filter = {"mentions": [mentions]}
        else:
            log_filter = "all"

        params: list[Any] = [log_filter, config]
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

    async def subscribe_transaction(
        self,
        callback: Callable[[dict[str, Any]], Awaitable[None]],
        account_include: list[str] | None = None,
        account_exclude: list[str] | None = None,
        account_required: list[str] | None = None,
        vote: bool | None = None,
        failed: bool | None = None,
        signature: str | None = None,
        commitment: str = "confirmed",
        encoding: str = "jsonParsed",
        transaction_details: str = "full",
        show_rewards: bool = True,
        max_supported_transaction_version: int = 0,
        request_id: int | None = None,
    ) -> bool:
        """Subscribe to real-time transaction events with custom filters (Helius Enhanced WebSocket).

        ## Args:
        - `callback`: Async function to handle transaction notifications
        - `account_include`: Accounts to receive updates for (tx must include at least one). Up to 50,000.
        - `account_exclude`: Accounts to exclude from updates. Up to 50,000.
        - `account_required`: Accounts that must all be included in a tx. Up to 50,000.
        - `vote`: Include or exclude vote-related transactions
        - `failed`: Include or exclude failed transactions
        - `signature`: Filter to a specific transaction signature
        - `commitment`: Commitment level ("processed", "confirmed", "finalized")
        - `encoding`: Encoding format ("base58", "base64", "jsonParsed")
        - `transaction_details`: Detail level ("full", "signatures", "accounts", "none")
        - `show_rewards`: Whether to include reward data
        - `max_supported_transaction_version`: Highest tx version to receive (0 = legacy + versioned)

        ## Returns:
        - `bool`: True if subscription successful

        ## Example:
        ```python
        await client.subscribe_transaction(
            callback=on_transaction,
            account_include=["675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"],
            commitment="processed",
            encoding="jsonParsed",
            transaction_details="full",
        )
        ```
        """
        method = "transactionSubscribe"

        # Build filter object
        tx_filter: dict[str, Any] = {}
        if account_include is not None:
            tx_filter["accountInclude"] = account_include
        if account_exclude is not None:
            tx_filter["accountExclude"] = account_exclude
        if account_required is not None:
            tx_filter["accountRequired"] = account_required
        if vote is not None:
            tx_filter["vote"] = vote
        if failed is not None:
            tx_filter["failed"] = failed
        if signature is not None:
            tx_filter["signature"] = signature

        # Build options object
        options: dict[str, Any] = {
            "commitment": commitment,
            "encoding": encoding,
            "transactionDetails": transaction_details,
            "showRewards": show_rewards,
            "maxSupportedTransactionVersion": max_supported_transaction_version,
        }
        request_id = self._get_next_id() if request_id is None else request_id
        method_id = f"{method}|{request_id}"

        params = [tx_filter, options]
        self._active_subscriptions[method] = {
            # "method": method,
            "callback": callback,
            "params": params,
            # "id": request_id,
        }
        return await self.subscribe_method(method, callback, params=params)


# Global singleton instance
# solana_rpc_ws_client = SolanaRPCWSClient()
