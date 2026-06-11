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

from .config import DISPATCH_CLEANUP_DELAY_SECONDS, TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# Type alias for the callback invoked when a pair is ready for analysis
ReadyCallback = Callable[[TokenItem], Awaitable[None]]

# Async function that fetches metadata (website, description, twitter, …) from a URI.
# Returns a dict with the metadata fields, or None on failure.
MetadataFetcher = Callable[[str], Awaitable[dict | None]]


@dataclass
class _PairEntry:
    item: TokenItem
    arrived_at: float = field(default_factory=time.monotonic)
    dispatched: bool = False
    timeout_task: asyncio.Task | None = field(default=None, repr=False, compare=False)
    uri_fetch_task: asyncio.Task | None = field(default=None, repr=False, compare=False)


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
        funder_timeout: float = TIMEOUT_SECONDS,
        dispatch_cleanup_delay: float = DISPATCH_CLEANUP_DELAY_SECONDS,
        fetch_metadata: MetadataFetcher | None = None,
    ) -> None:
        self._on_ready = on_ready
        self._funder_timeout = funder_timeout
        self._cleanup_delay = dispatch_cleanup_delay
        self._fetch_metadata = fetch_metadata
        self._pairs: dict[str, _PairEntry] = {}
        self._early_updates: dict[str, dict] = {}

    # ── Public API ───────────────────────────────────────────────────────────

    def add_pair(self, data: dict) -> None:
        """Register a new pair from the new_pairs WebSocket."""
        addr = (
            data.get("bonding_curve")
            or data.get("bondingCurveKey")
            or data.get("pair_address")
            or data.get("pairAddress")
        )
        if not addr:
            return
        existing = self._pairs.get(addr)
        if existing and existing.dispatched:
            return

        early_updates = self._early_updates.pop(addr, None)
        if early_updates:
            data.update(early_updates)
            # pair_item = TokenItem.model_validate(data)
        if existing:
            # model_dump uses field names; raw WS data uses aliases.
            # Merge both and re-validate so Pydantic resolves aliases correctly.
            merged = existing.item.model_dump()
            merged.update(data)
            pair_item = TokenItem.model_validate(merged)
        else:
            pair_item = TokenItem(**data)

        #######################
        if existing:
            if existing.timeout_task:
                existing.timeout_task.cancel()
            if existing.uri_fetch_task:
                existing.uri_fetch_task.cancel()

        entry = _PairEntry(item=pair_item)
        self._pairs[addr] = entry

        if pair_item.has_nats_arrived and pair_item.has_pumpportal_arrived:
            logger.debug(f"Pair {addr} is ready immediately upon arrival")
            self._dispatch(entry)
        else:
            entry.timeout_task = asyncio.create_task(self._nats_timeout_dispatch(addr))
            # If pumpportal arrived with a URI, start fetching metadata in parallel
            if (
                (pair_item.has_pumpportal_arrived or pair_item.has_axiom_arrived)
                and not pair_item.has_nats_arrived
                and pair_item.token_uri
                and self._fetch_metadata
            ):
                entry.uri_fetch_task = asyncio.create_task(
                    self._fetch_uri_and_dispatch(addr, pair_item.token_uri)
                )

    # ── Diagnostics ──────────────────────────────────────────────────────────

    # @property
    # def pending_count(self) -> int:
    #     """Number of pairs still waiting for funder data."""
    #     return sum(1 for e in self._pairs.values() if not e.dispatched)

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

    async def _nats_timeout_dispatch(self, pair_address: str) -> None:
        await asyncio.sleep(self._funder_timeout)
        entry = self._pairs.get(pair_address)
        if entry and not entry.dispatched:
            logger.error(
                f"Nats timeout for {pair_address} — dispatching without nats data"
            )
            self._dispatch(entry)

    async def _fetch_uri_and_dispatch(self, pair_address: str, uri: str) -> None:
        """Fetch metadata from the token URI and dispatch if NATS hasn't arrived yet."""
        try:
            logger.debug(f"Fetching URI metadata for {pair_address} from {uri}")
            metadata = await self._fetch_metadata(uri)  # type: ignore[misc]
        except Exception:
            logger.error(f"URI fetch failed for {pair_address}", exc_info=True)
            return

        entry = self._pairs.get(pair_address)
        if entry is None or entry.dispatched:
            return

        if metadata:
            updates = {k: v for k, v in metadata.items() if v is not None}
            if updates:
                entry.item = entry.item.model_copy(update=updates)
            logger.debug(f"URI metadata fetched for {pair_address} — dispatching early")
            if entry.timeout_task:
                entry.timeout_task.cancel()
            self._dispatch(entry)

    async def _cleanup_after(self, pair_address: str) -> None:
        await asyncio.sleep(self._cleanup_delay)
        self._pairs.pop(pair_address, None)

    def update_fields(self, pair_address: str, updates: dict) -> None:
        """Apply incremental non-funder field updates to a pending pair."""
        entry = self._pairs.get(pair_address)
        if entry is None:
            self._early_updates[pair_address] = updates
            return
        if entry.dispatched:
            return
        data = entry.item.model_dump()
        data.update(updates)
        entry.item = TokenItem.model_validate(data)


# Module-level instance — call init_pair_buffer() once at monitor startup
pair_buffer: PairBuffer | None = None


def init_pair_buffer(
    on_ready: ReadyCallback,
    funder_timeout: float = TIMEOUT_SECONDS,
    dispatch_cleanup_delay: float = DISPATCH_CLEANUP_DELAY_SECONDS,
    fetch_metadata: MetadataFetcher | None = None,
) -> PairBuffer:
    """
    Initialize the global pair buffer. Call once at monitor startup.

    ## Parameters
    - `on_ready`: Async callback invoked when a pair is ready for analysis
    - `funder_timeout`: Seconds to wait for funder before dispatching anyway
    - `dispatch_cleanup_delay`: Seconds after dispatch before removing from buffer
    - `fetch_metadata`: Optional async function that fetches metadata from a token URI

    ## Example
    ```python
    from axiom.monitor.state import init_pair_buffer

    async def analyze_pair(pair: PairItem) -> None:
        print(f"{pair.token_name} | funder: {pair.dev_wallet_funding}")

    init_pair_buffer(on_ready=analyze_pair)
    ```
    """
    global pair_buffer
    pair_buffer = PairBuffer(
        on_ready, funder_timeout, dispatch_cleanup_delay, fetch_metadata
    )
    return pair_buffer


def _buf():
    """Return the global PairBuffer, raising if not initialized."""
    assert pair_buffer is not None, (
        "pair_buffer is not initialized. "
        "Call shared_lib.monitor.state.init_pair_buffer(on_ready=...) at startup."
    )
    return pair_buffer
