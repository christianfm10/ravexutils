"""
Global state management for the Axiom Monitor.

Replaces raw pair_state dict with PairBuffer — a self-managing buffer that
merges data from two WebSocket sources (new_pairs + pulse) and dispatches
pairs when they are ready for analysis.
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from ..models.token import TokenItem

from .config import DISPATCH_CLEANUP_DELAY_SECONDS, FUNDER_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# Type alias for the callback invoked when a pair is ready for analysis
ReadyCallback = Callable[[TokenItem], Awaitable[None]]


@dataclass
class _PairEntry:
    item: TokenItem
    arrived_at: float = field(default_factory=time.monotonic)
    dispatched: bool = False
    timeout_task: asyncio.Task | None = field(default=None, repr=False, compare=False)


class PairBuffer:
    """
    Merges new_pairs + pulse funder data, dispatching pairs when ready.

    A pair is dispatched to `on_ready` as soon as it has basic info AND either:
    - Dev wallet funding has arrived, OR
    - `funder_timeout` seconds have elapsed (funder may never arrive)

    Early funders (arriving before basic pair info) are cached and attached
    automatically when the pair info arrives.

    ## Memory Management
    No periodic cleanup task needed. Each entry self-destructs
    `dispatch_cleanup_delay` seconds after being dispatched.

    ## Usage
    ```python
    async def analyze_pair(pair: PairItem) -> None:
        print(f"{pair.token_name} | funder: {pair.dev_wallet_funding}")

    init_pair_buffer(on_ready=analyze_pair)
    ```
    """

    def __init__(
        self,
        on_ready: ReadyCallback,
        funder_timeout: float = FUNDER_TIMEOUT_SECONDS,
        dispatch_cleanup_delay: float = DISPATCH_CLEANUP_DELAY_SECONDS,
    ) -> None:
        self._on_ready = on_ready
        self._funder_timeout = funder_timeout
        self._cleanup_delay = dispatch_cleanup_delay
        self._pairs: dict[str, _PairEntry] = {}
        # self._early_funders: dict[str, DevWalletFunding] = {}

    # ── Public API ───────────────────────────────────────────────────────────

    def add_pair(self, data: dict) -> None:
        """Register a new pair from the new_pairs WebSocket."""
        # addr = pair_item.pair_address
        addr = (
            data.get("bonding_curve")
            or data.get("bondingCurveKey")
            or data.get("pair_address")
        )
        if not addr:
            return
        existing = self._pairs.get(addr)

        if existing and existing.dispatched:
            return

        if existing:
            existing_pair = existing.item
            pair_item = existing_pair.model_copy(update=data)
        else:
            pair_item = TokenItem(**data)

        if existing and existing.timeout_task:
            existing.timeout_task.cancel()

        entry = _PairEntry(item=pair_item)
        self._pairs[addr] = entry

        if pair_item.has_nats_arrived and pair_item.has_pumpportal_arrived:
            logger.info(f"Pair {addr} is ready immediately upon arrival")
            self._dispatch(entry)
        else:
            entry.timeout_task = asyncio.create_task(
                self._funder_timeout_dispatch(addr)
            )

    def update_fields(self, pair_address: str, updates: dict) -> None:
        """Apply incremental non-funder field updates to a pending pair."""
        entry = self._pairs.get(pair_address)
        if entry is None or entry.dispatched:
            return
        data = entry.item.model_dump()
        data.update(updates)
        entry.item = TokenItem.model_validate(data)

    # ── Diagnostics ──────────────────────────────────────────────────────────

    @property
    def pending_count(self) -> int:
        """Number of pairs still waiting for funder data."""
        return sum(1 for e in self._pairs.values() if not e.dispatched)

    # ── Internal ─────────────────────────────────────────────────────────────

    def _dispatch(self, entry: _PairEntry) -> None:
        if entry.dispatched:
            return
        entry.dispatched = True
        asyncio.create_task(self._call_on_ready(entry.item))
        asyncio.create_task(self._cleanup_after(entry.item.pair_address))

    async def _call_on_ready(self, pair_item: TokenItem) -> None:
        try:
            await self._on_ready(pair_item)
        except Exception:
            logger.error(
                f"on_ready callback failed for {pair_item.pair_address}",
                exc_info=True,
            )

    async def _funder_timeout_dispatch(self, pair_address: str) -> None:
        await asyncio.sleep(self._funder_timeout)
        entry = self._pairs.get(pair_address)
        if entry and not entry.dispatched:
            logger.warning(
                f"Funder timeout for {pair_address} — dispatching without funder"
            )
            self._dispatch(entry)

    async def _cleanup_after(self, pair_address: str) -> None:
        await asyncio.sleep(self._cleanup_delay)
        self._pairs.pop(pair_address, None)


# Module-level instance — call init_pair_buffer() once at monitor startup
pair_buffer: PairBuffer | None = None


def init_pair_buffer(
    on_ready: ReadyCallback,
    funder_timeout: float = FUNDER_TIMEOUT_SECONDS,
    dispatch_cleanup_delay: float = DISPATCH_CLEANUP_DELAY_SECONDS,
) -> PairBuffer:
    """
    Initialize the global pair buffer. Call once at monitor startup.

    ## Parameters
    - `on_ready`: Async callback invoked when a pair is ready for analysis
    - `funder_timeout`: Seconds to wait for funder before dispatching anyway
    - `dispatch_cleanup_delay`: Seconds after dispatch before removing from buffer

    ## Example
    ```python
    from axiom.monitor.state import init_pair_buffer

    async def analyze_pair(pair: PairItem) -> None:
        print(f"{pair.token_name} | funder: {pair.dev_wallet_funding}")

    init_pair_buffer(on_ready=analyze_pair)
    ```
    """
    global pair_buffer
    pair_buffer = PairBuffer(on_ready, funder_timeout, dispatch_cleanup_delay)
    return pair_buffer


def _buf():
    """Return the global PairBuffer, raising if not initialized."""
    assert pair_buffer is not None, (
        "pair_buffer is not initialized. "
        "Call shared_lib.monitor.state.init_pair_buffer(on_ready=...) at startup."
    )
    return pair_buffer
