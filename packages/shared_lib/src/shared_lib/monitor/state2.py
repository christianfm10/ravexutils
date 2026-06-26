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
from typing import Awaitable, Callable, Iterable

from ..models.token import TokenItem

from .config import DISPATCH_CLEANUP_DELAY_SECONDS, TIMEOUT_SECONDS

logger = logging.getLogger(__name__)

# Type alias for the callback invoked when a pair is ready for analysis
ReadyCallback = Callable[[TokenItem], Awaitable[None]]

# Async function that fetches metadata (website, description, twitter, …) from a URI.
# Returns a dict with the metadata fields, or None on failure.
MetadataFetcher = Callable[[str], Awaitable[dict | None]]
UpdateDbCallback = Callable[[dict], Awaitable[None]]

WS_FLAG_MAP: dict[str, str] = {
    "nats": "has_nats_arrived",
    "pumpportal": "has_pumpportal_arrived",
    "pulse": "has_pulse_arrived",
    "axiom": "has_axiom_arrived",
    "twitter": "has_twitter_arrived",
}


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
        timeout: float = TIMEOUT_SECONDS,
        dispatch_cleanup_delay: float = DISPATCH_CLEANUP_DELAY_SECONDS,
        fetch_metadata: MetadataFetcher | None = None,
        wait_for_ws: Iterable[str] | None = None,
        timeout_only: bool = True,
        fetch_metadata_if_missing_nats: bool = False,
        update_db_callback: UpdateDbCallback | None = None,
    ) -> None:
        self._on_ready = on_ready
        self._timeout = timeout
        self._cleanup_delay = dispatch_cleanup_delay
        self._fetch_metadata = fetch_metadata
        self._timeout_only = timeout_only
        self._wait_for_flags = self._resolve_wait_flags(wait_for_ws)

        self._fetch_metadata_if_missing_nats = fetch_metadata_if_missing_nats
        self._update_db_callback = update_db_callback
        self._pairs: dict[str, _PairEntry] = {}
        self._early_updates: dict[str, dict] = {}

    def _resolve_wait_flags(self, wait_for_ws: Iterable[str] | None) -> set[str]:
        if wait_for_ws is None:
            return set()
        requested = {name.strip().lower() for name in wait_for_ws}
        invalid = requested - set(WS_FLAG_MAP)
        if invalid:
            allowed = ", ".join(sorted(WS_FLAG_MAP))
            raise ValueError(
                f"Invalid wait_for_ws values: {sorted(invalid)}. Allowed: {allowed}"
            )
        return {WS_FLAG_MAP[name] for name in requested}

    def _is_ready(self, item: TokenItem) -> bool:
        return all(getattr(item, flag, False) for flag in self._wait_for_flags)

    def _should_try_metadata_fallback(self, item: TokenItem) -> bool:
        return (
            self._fetch_metadata_if_missing_nats
            and self._fetch_metadata is not None
            and item.token_uri is not None
            and (item.has_pumpportal_arrived or item.has_axiom_arrived)
            and not item.has_nats_arrived
        )

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
            entry = existing
            entry.item = pair_item
        else:
            pair_item = TokenItem(**data)

            entry = _PairEntry(item=pair_item)
            self._pairs[addr] = entry

        if entry.timeout_task is None:
            entry.timeout_task = asyncio.create_task(self._timeout_dispatch(addr))

        if not self._timeout_only and self._is_ready(entry.item):
            self._dispatch(entry)
            return

        if self._should_try_metadata_fallback(entry.item):
            if entry.uri_fetch_task is None or entry.uri_fetch_task.done():
                entry.uri_fetch_task = asyncio.create_task(
                    self._fetch_uri_and_dispatch(addr, entry.item.token_uri or "")
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

    async def _timeout_dispatch(self, address: str) -> None:
        await asyncio.sleep(self._timeout)
        entry = self._pairs.get(address)
        if entry and not entry.dispatched:
            logger.debug(
                f"Timeout for {entry.item.token_address} — dispatching with "
                f"PumpPortal: {entry.item.has_pumpportal_arrived}, "
                f"Nats: {entry.item.has_nats_arrived}, "
                f"Pulse: {entry.item.has_pulse_arrived}, "
                f"Axiom: {entry.item.has_axiom_arrived}, "
                f"TwitterPrev: {entry.item.has_twitter_arrived}, "
                f"Funder: {entry.item.dev_wallet_funding.funding_wallet_address if entry.item.dev_wallet_funding else None}"
            )
            self._dispatch(entry)

    async def _fetch_uri_and_dispatch(self, pair_address: str, uri: str) -> None:
        """Fetch token metadata and dispatch early when fallback is enabled."""
        try:
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
            logger.debug(
                f"URI metadata fetched for {pair_address} — dispatching via fallback"
            )
            self._dispatch(entry)

    async def _cleanup_after(self, pair_address: str) -> None:
        await asyncio.sleep(self._cleanup_delay)
        self._pairs.pop(pair_address, None)

    async def _call_update_db_callback(self, payload: dict) -> None:
        """Run DB update callback safely in background."""
        try:
            await self._update_db_callback(payload)  # type: ignore[misc]
        except Exception:
            logger.error("update_db_callback failed", exc_info=True)

    def update_fields(
        self,
        pair_address: str,
        updates: dict,
        update_db: bool = False,
    ) -> None:
        """Apply updates or route them directly to DB callback.

        If ``update_db`` is True, this method only forwards payload to
        ``update_db_callback`` (when configured) and skips all buffer logic:
        no early update cache, no wait-for-ws checks, and no dispatch.
        """

        entry = self._pairs.get(pair_address)

        if entry is None:
            if update_db:
                if self._update_db_callback is not None:
                    payload = {"pair_address": pair_address, **updates}
                    asyncio.create_task(self._call_update_db_callback(payload))
                else:
                    logger.warning(
                        "update_db=True but no update_db_callback configured for %s",
                        pair_address,
                    )
                return
            self._early_updates[pair_address] = updates
            return
        data = entry.item.model_dump()
        data.update(updates)
        entry.item = TokenItem.model_validate(data)
        if entry.dispatched:
            return

        if not self._timeout_only and self._is_ready(entry.item):
            self._dispatch(entry)
            return

        # if self._should_try_metadata_fallback(entry.item):
        #     if entry.uri_fetch_task is None or entry.uri_fetch_task.done():
        #         entry.uri_fetch_task = asyncio.create_task(
        #             self._fetch_uri_and_dispatch(
        #                 pair_address,
        #                 entry.item.token_uri or "",
        #             )
        #         )


# Module-level instance — call init_pair_buffer() once at monitor startup
pair_buffer: PairBuffer | None = None


def init_pair_buffer(
    on_ready: ReadyCallback,
    timeout: float = TIMEOUT_SECONDS,
    dispatch_cleanup_delay: float = DISPATCH_CLEANUP_DELAY_SECONDS,
    fetch_metadata: MetadataFetcher | None = None,
    wait_for_ws: Iterable[str] | None = None,
    timeout_only: bool = True,
    fetch_metadata_if_missing_nats: bool = False,
    update_db_callback: UpdateDbCallback | None = None,
) -> PairBuffer:
    """
    Initialize the global pair buffer. Call once at monitor startup.

    ## Parameters
    - `on_ready`: Async callback invoked when a pair is ready for analysis
    - `timeout`: Seconds to wait for timeout before dispatching anyway
    - `dispatch_cleanup_delay`: Seconds after dispatch before removing from buffer
    - `fetch_metadata`: Optional async function that fetches metadata from a token URI
        - `wait_for_ws`: Iterable with ws names to require before early dispatch.
            Allowed: nats, pumpportal, pulse, axiom, twitter.
        - `timeout_only`: If True, always wait for timeout and ignore wait_for_ws.
            If False, dispatch immediately when all `wait_for_ws` conditions are met.
        - `fetch_metadata_if_missing_nats`: If True and nats is missing but pumpportal
            + token_uri are available, fetch metadata and dispatch early.
        - `update_db_callback`: Optional async callback for DB-only updates when
            calling `update_fields(..., update_db=True)`.

    ## Example
    ```python
    from axiom.monitor.state import init_pair_buffer

    async def analyze_pair(pair: PairItem) -> None:
        print(f"{pair.token_name} | funder: {pair.dev_wallet_funding}")

    init_pair_buffer(on_ready=analyze_pair)
    """
    global pair_buffer
    pair_buffer = PairBuffer(
        on_ready,
        timeout,
        dispatch_cleanup_delay,
        fetch_metadata,
        wait_for_ws,
        timeout_only,
        fetch_metadata_if_missing_nats,
        update_db_callback,
    )
    return pair_buffer


def _buf():
    """Return the global PairBuffer, raising if not initialized."""
    assert pair_buffer is not None, (
        "pair_buffer is not initialized. "
        "Call shared_lib.monitor.state.init_pair_buffer(on_ready=...) at startup."
    )
    return pair_buffer
