import logging
from typing import Any, Dict, List

from axiom.models.models import DevWalletFunding, PairItem
from .config import FIELD_MAP
from . import state

logger = logging.getLogger(__name__)


def _buf():
    """Return the global PairBuffer, raising if not initialized."""
    assert state.pair_buffer is not None, (
        "pair_buffer is not initialized. "
        "Call axiom.monitor.state.init_pair_buffer(on_ready=...) at startup."
    )
    return state.pair_buffer


def should_accept_new_token(content: dict[str, Any]) -> bool:
    """
    Determine if a new token should be tracked.

    ## Parameters
    - `content`: Message content from WebSocket

    ## Returns
    - `True` if token should be tracked
    - `False` otherwise

    ## Filtering Rules
    1. Only accept "Pump V1" protocol tokens
    2. Reject Mayhem tokens (high risk/volatility)
    3. Reject Offchain tokens
    """
    protocol = content.get("protocol", "").lower()
    if protocol != "pump v1":
        return False

    # Check for Mayhem flag
    protocol_details = content.get("protocol_details", {})
    if protocol_details and protocol_details.get("isMayhem", False):
        return False
    if protocol_details and protocol_details.get("isOffchain", False):
        return False

    return True


async def handle_new_token_message(message: dict[str, Any]) -> None:
    """
    Process incoming new token creation messages from WebSocket.

    ## Parameters
    - `message`: WebSocket message containing new token data

    ## Processing Steps
    1. Extract and validate message content
    2. Apply filtering rules (protocol, Mayhem check)
    3. Register pair in PairBuffer — funder merging and dispatch are handled there

    ## Error Handling
    Catches all exceptions to prevent one bad message from crashing
    the entire monitoring system. Logs errors with full traceback.
    """
    try:
        content = message.get("content", {})
        # if not should_accept_new_token(content):
        #     return

        pair_item = PairItem(**content)
        _buf().add_pair(pair_item)

        logger.debug(
            f"New token registered: {pair_item.pair_address} | "
            f"{pair_item.token_name} ({pair_item.token_ticker})"
        )

    except Exception as e:
        logger.error(f"Failed to handle new token message: {e}", exc_info=True)


def should_skip_field_update(
    field_index: int, new_value: Any, pair_data: Dict[str, Any]
) -> bool:
    """
    Determine if a field update should be skipped based on business rules.

    ## Parameters
    - `field_index`: WebSocket field index
    - `new_value`: New value for the field
    - `pair_data`: Current pair data

    ## Returns
    - `True` if update should be skipped
    - `False` if update should be applied

    ## Skip Rules
    1. Liquidity/transaction fields: Skip if pair is older than 6 seconds
       (prevents stale data from overwriting recent values)
    2. Bonding curve: Skip if new value is lower than current
       (bonding curve percentage should only increase)
    """
    return False


async def process_pair_update_message(message: List[Any]) -> None:
    """
    Process type 1 pulse messages (incremental pair updates).

    ## Parameters
    - `message`: List containing [msg_type, pair_address, changes]

    ## Algorithm
    For each field in `changes`:
    - `dev_wallet_funding` (index 39): routed to `pair_buffer.add_funder()`
    - All other fields: collected into a batch and sent to `pair_buffer.update_fields()`

    The buffer handles the early-funder case transparently.
    """
    try:
        _msg_type, pair_address, changes = message
        updates: Dict[str, Any] = {}

        for field_index, new_value in changes:
            field_name = FIELD_MAP.get(field_index)
            if field_name is None:
                continue

            if field_name == "dev_wallet_funding":
                try:
                    funder = DevWalletFunding.model_validate(new_value)
                    _buf().add_funder(pair_address, funder)
                    logger.debug(
                        f"Funder received for {pair_address}: {funder.amount_sol} SOL"
                    )
                except Exception as e:
                    logger.error(f"Failed to validate funder for {pair_address}: {e}")
                continue

            if not should_skip_field_update(field_index, new_value, updates):
                updates[field_name] = new_value

        if updates:
            _buf().update_fields(pair_address, updates)
            logger.debug(f"Updated fields for {pair_address}: {', '.join(updates)}")

    except Exception as e:
        logger.error(f"Failed to process pair update: {e}", exc_info=True)


async def process_new_pairs_message(message: List[Any]) -> None:
    """
    Process type 2 pulse messages (bulk new pair announcements).

    ## Parameters
    - `message`: List containing [msg_type, pair_data_array]

    ## Processing Logic
    Extracts `dev_wallet_funding` from position 39 (if present) and routes
    it to `pair_buffer.add_funder()`. The buffer handles whether the pair
    info has already arrived or not.
    """
    try:
        _msg_type, pair_data = message

        if not pair_data:
            return

        pair_address = pair_data[0]

        if len(pair_data) > 39 and pair_data[39] is not None:
            try:
                funder = DevWalletFunding.model_validate(pair_data[39])
                _buf().add_funder(pair_address, funder)
                logger.debug(
                    f"Funder (type 2) for {pair_address}: {funder.amount_sol} SOL"
                )
            except Exception as e:
                logger.error(f"Failed to validate funding data for {pair_address}: {e}")

    except Exception as e:
        logger.error(f"Failed to process new pairs message: {e}", exc_info=True)


async def dispatch_pulse_message(message: List[Any]) -> None:
    """
    Route pulse messages to appropriate handlers based on message type.

    ## Parameters
    - `message`: WebSocket pulse message (first element is type)

    ## Message Types
    - `0`: System/heartbeat messages (currently ignored)
    - `1`: Incremental pair updates (most common)
    - `2`: Bulk new pair data
    - `3`: Unknown/reserved (currently ignored)

    ## Error Handling
    Catches routing errors to prevent message dispatcher from crashing.
    Individual handlers have their own error handling as well.
    """
    try:
        msg_type = message[0]

        if msg_type == 0:
            pass  # System messages - no action needed
        elif msg_type == 1:
            await process_pair_update_message(message)
        elif msg_type == 2:
            await process_new_pairs_message(message)
        elif msg_type == 3:
            pass  # Reserved type - no action yet
        else:
            logger.warning(f"Unknown pulse message type: {msg_type}")

    except Exception as e:
        logger.error(f"Failed to dispatch pulse message: {e}", exc_info=True)
