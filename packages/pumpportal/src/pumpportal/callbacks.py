import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from pumpportal import PumpPortalWSClient

from pumpfun import PumpfunClient
from shared_lib.utils.date import is_unix_timestamp_older_than

pf = PumpfunClient()

logger = logging.getLogger("callbacks")

MY_PK = "YourPublicKeyHere"


def create_callbacks(ws_client: "PumpPortalWSClient"):
    """
    Factory function that creates callback functions with injected dependencies.

    ## Parameters:
    - `ws_client` (PumpPortalWSClient): WebSocket client instance to use for subscriptions and notifications

    ## Returns:
    - `dict`: Dictionary containing all callback functions with client dependency injected

    ## Example:
    ```python
    client = PumpPortalWSClient(context=context)
    callbacks = create_callbacks(client)

    await client.subscribe_new_token(callbacks['new_token'])
    await client.subscribe_migration(callbacks['migration'])
    ```
    """
    counter = 0
    buyed_tokens: dict[str, Any] = {}

    async def should_skip_token(data: dict) -> bool:
        # Example logic: skip tokens with solAmount less than 1.0
        pool = data.get("pool", "")
        is_mayhem = data.get("is_mayhem_mode", False)
        if pool != "pump":
            return True
        if is_mayhem:
            return True
        return False

    async def new_token_callback(data: dict[str, Any]):
        nonlocal counter

        if await should_skip_token(data):
            return

        if counter < 3:
            await ws_client.add_token_trade_keys(keys=[data["mint"]])
            buyed_tokens[data["mint"]] = data["marketCapSol"]
            counter = counter + 1

    async def token_trade_callback(data: dict[str, Any]):
        if buyed_tokens[data["mint"]] == 0:
            buyed_tokens[data["mint"]] = data["marketCapSol"]
            logger.info(
                f"Token {data['mint']} Trade Started: Buy Price set at {buyed_tokens[data['mint']]} SOL"
            )
            return

        if data.get("mint", "") in buyed_tokens:
            buy_price = buyed_tokens[data["mint"]]
            current_price = data["marketCapSol"]
            profit_loss = ((current_price - buy_price) / buy_price) * 100
            if profit_loss < 0.0:
                await ws_client._send_notification(
                    f"🚀 Token {data['mint']} has increased by {profit_loss:.2f}%!\nBuy Price: {buy_price} SOL\nCurrent Price: {current_price} SOL"
                )
                await ws_client.remove_token_trade_keys(keys=[data["mint"]])
            else:
                logger.info(
                    f"Token {data['mint']} Trade Update: Current Price: {current_price} SOL, Buy Price: {buy_price} SOL, P/L: {profit_loss:.2f}%"
                )

    async def new_migration(data: dict[str, Any]):
        token = await pf.get_coin_info(data["mint"])

        if is_unix_timestamp_older_than(token.created_timestamp, seconds=10):
            logger.info(f"Nuevo token migrado mayor a 10 segundos: {token}")
        else:
            logger.info(f"Nuevo token migrado menor o igual a 10 segundos: {token}")

    return {
        "new_token": new_token_callback,
        "token_trade": token_trade_callback,
        "migration": new_migration,
    }
