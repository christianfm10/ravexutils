import logging
from typing import Any
from pumpfun import PumpfunClient
from shared_lib.utils.date import is_unix_timestamp_older_than
from pumpportal import pf_ws_client

pf = PumpfunClient()

logger = logging.getLogger("callbacks")
counter = 0

buyed_tokens: dict[str, Any] = {}
MY_PK = "YourPublicKeyHere"


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
    global counter

    if await should_skip_token(data):
        return
    # print(f"🔔 New Token Event: {data}")
    if counter < 3:
        await pf_ws_client.subscribe_token_trade(
            callback=token_trade_callback, keys=[data["mint"]]
        )
        # print(f"Buy price for {data['symbol']}: {data['marketCapSol']} SOL")
        buyed_tokens[data["mint"]] = data["marketCapSol"]
        # buyed_tokens[data["mint"]] = 0
        # print(f"🔔 New Token Event Subscribed to trades for: {data}")
        # logger.info(f"Nuevo token detectado: {token}")
        counter = counter + 1


async def token_trade_callback(data: dict[str, Any]):
    # print(f"🔔 Token Token Trade Event: {data}")
    if buyed_tokens[data["mint"]] == 0:
        buyed_tokens[data["mint"]] = data["marketCapSol"]
        logger.info(
            f"Token {data['mint']} Trade Started: Buy Price set at {buyed_tokens[data['mint']]} SOL"
        )
        return
    # print(data)
    # if buyed_tokens.get(data["mint"], None) is None and data["txType"] == "buy":
    #     if data["traderPublicKey"] == MY_PK:
    #         buyed_tokens[data["mint"]] = data["marketCapSol"]
    #         logger.info(
    #             f"Token {data['mint']} Trade Started by me: Buy Price set at {buyed_tokens[data['mint']]} SOL"
    #         )

    if data.get("mint", "") in buyed_tokens:
        buy_price = buyed_tokens[data["mint"]]
        current_price = data["marketCapSol"]
        profit_loss = ((current_price - buy_price) / buy_price) * 100
        if profit_loss < 0.0:
            await pf_ws_client._send_notification(
                f"🚀 Token {data['mint']} has increased by {profit_loss:.2f}%!\nBuy Price: {buy_price} SOL\nCurrent Price: {current_price} SOL"
            )
            await pf_ws_client.unsubscribe_token_trade(keys=[data["mint"]])
        else:
            logger.info(
                f"Token {data['mint']} Trade Update: Current Price: {current_price} SOL, Buy Price: {buy_price} SOL, P/L: {profit_loss:.2f}%"
            )


async def new_migration(data: dict[str, Any]):
    # logger.info(f"🔔 Token Migration Event: {data}")
    token = await pf.get_coin_info(data["mint"])

    if is_unix_timestamp_older_than(token.created_timestamp, seconds=10):
        logger.info(f"Nuevo token migrado mayor a 10 segundos: {token}")
    else:
        logger.info(f"Nuevo token migrado menor o igual a 10 segundos: {token}")
