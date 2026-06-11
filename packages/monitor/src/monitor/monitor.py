"""
Configurable crypto monitor.

Choose what you want at instantiation time:

    from monitor import Monitor, MonitorConfig

    monitor = Monitor(MonitorConfig(
        use_rich=True,
        subscriptions={"cluster", "pulse", "pumpportal", "notifications"},
        save_to_db=False,
        fetch_metadata=False,
        refresh_token="<your JWT>",
    ))
    asyncio.run(monitor.run())

Valid subscription names
------------------------
- ``"cluster"``       – Axiom ClusterWSClient (new token events)
- ``"pulse"``         – Axiom PulseWSClient (price/volume pulses)
- ``"pumpportal"``    – PumpPortal new-token WebSocket
- ``"nats"``          – pump.fun NATS stream
- ``"notifications"`` – EucalyptusClient (wallet balance trades)
"""

from __future__ import annotations

import asyncio
import json
import logging
import shared_lib.settings  # noqa: F401 – must be first
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from axiom.client import AxiomClient
from axiom.websocket import AxiomClusterWSClient, AxiomPulseWSClient, EucalyptusClient
from pumpfun.ws_client import connect_to_nats
from pumpportal.ws_client import PumpPortalWSClient
from shared_lib.logging import setup_logging
from shared_lib.models.token import TokenItem
from shared_lib.monitor.state2 import _buf, init_pair_buffer
from shared_lib.monitor.config import FIELD_SHORT_MAP, UPDATE_FIELD_MAP
from shared_lib.utils.cex import CEXs
from shared_lib.database.token_repository import TokenRepository
from shared_lib.utils.filters import MessageFilter
from shared_lib.utils.notification import show_alert
from shared_lib.utils.numbers import human_readable_number
from shared_lib.database.db_manager import get_async_db_manager
from shared_lib.utils.uri import close_session, fetch_token_metadata
from telegram import TelegramBot

from shared_lib.utils.rich import (
    make_layout,
    redirect_logs_to_buffer,
    run_display,
)
from rich.live import Live

# ── Valid subscription keys ────────────────────────────────────────────────────

VALID_SUBSCRIPTIONS: frozenset[str] = frozenset(
    {"cluster", "pulse", "pumpportal", "nats", "notifications"}
)


# ── Configuration dataclass ───────────────────────────────────────────────────


@dataclass
class MonitorConfig:
    """All tunable options for :class:`Monitor`."""

    # ── Display ───────────────────────────────────────────────────────────────
    use_rich: bool = True
    """Use Rich split-screen Live display. Falls back to plain logging if False."""
    balances_panel_width: int = 65
    """Fixed width (chars) of the right-hand balances panel."""
    low_balance_threshold: float = 20_000
    """Trigger a desktop alert when a wallet balance drops below this level."""

    # ── Subscriptions ─────────────────────────────────────────────────────────
    subscriptions: set[str] = field(
        default_factory=lambda: {"cluster", "pulse", "pumpportal"}
    )
    """Which WS sources to subscribe to. See module docstring for valid names."""

    # ── Persistence ───────────────────────────────────────────────────────────
    save_to_db: bool = False
    """Persist each ready token to the database via ``save_token_to_db``."""
    fetch_metadata: bool = False
    """Fetch IPFS metadata for tokens that have an ipfs.io URI."""

    # ── Axiom auth ────────────────────────────────────────────────────────────
    auth_token: str = "your_auth_token_here"
    refresh_token: str = ""
    use_tls_fingerprint: bool = True
    load_cookies: bool = True

    # ── Pair buffer tuning ────────────────────────────────────────────────────
    buffer_timeout: float = 5.0
    """Seconds to wait for all WS sources before dispatching a token anyway."""
    dispatch_cleanup_delay: float = 2.0
    """Seconds to keep a dispatched token in the buffer before removing it."""
    timeout_only: bool = False
    """If True, only use the timeout for dispatching tokens (ignore WS flags)."""

    # ── Optional ready callback ───────────────────────────────────────────────
    on_ready: Callable[[TokenItem], Awaitable[None]] | None = None
    """
    Custom callback invoked when a token is ready.
    If provided, replaces the built-in ``on_ready_complete`` logic entirely.
    """


# ── Monitor class ─────────────────────────────────────────────────────────────


class Monitor:
    """
    Async monitor that wires together configurable WS subscriptions,
    optional Rich display, and optional DB persistence.

    Extend via subclassing and override :meth:`on_ready_complete` for
    custom dispatch logic.
    """

    def __init__(self, config: MonitorConfig | None = None) -> None:
        self.config = config or MonitorConfig()
        self._validate_config()

        self._logger = logging.getLogger(self.__class__.__name__)
        self._filter = MessageFilter()
        self._tg_bot = TelegramBot()

        # Wallet balance / price state (used by "notifications" sub + Rich display)
        self._balances: dict[str, dict[str, float]] = defaultdict(
            lambda: defaultdict(float)
        )
        self._prices: dict[str, float] = {}

        # DB repository (only instantiated when save_to_db=True)
        self._token_repo = TokenRepository() if self.config.save_to_db else None

    # ── Config validation ─────────────────────────────────────────────────────

    def _validate_config(self) -> None:
        unknown = self.config.subscriptions - VALID_SUBSCRIPTIONS
        if unknown:
            raise ValueError(
                f"Unknown subscription(s): {unknown!r}. "
                f"Valid values: {sorted(VALID_SUBSCRIPTIONS)}"
            )

    # ── Pair buffer init ──────────────────────────────────────────────────────

    def _init_pair_buffer(self) -> None:
        subs = self.config.subscriptions
        kwargs: dict[str, Any] = dict(
            on_ready=self.on_ready_complete,
            timeout=self.config.buffer_timeout,
            dispatch_cleanup_delay=self.config.dispatch_cleanup_delay,
        )

        if self.config.fetch_metadata:
            kwargs["fetch_metadata"] = fetch_token_metadata
            kwargs["fetch_metadata_if_missing_nats"] = True

        if self.config.save_to_db and self._token_repo:
            kwargs["update_db_callback"] = self._token_repo.update

        # Decide whether to wait for multiple WS sources or use simple timeout
        waiting: set[str] = set()
        if "cluster" in subs:
            waiting.add("axiom")
        if "pulse" in subs:
            waiting.add("pulse")
        if "pumpportal" in subs:
            waiting.add("pumpportal")
        if "nats" in subs:
            waiting.add("nats")

        if len(waiting) > 1:
            kwargs["wait_for_ws"] = waiting
            kwargs["timeout_only"] = self.config.timeout_only
        else:
            kwargs["timeout_only"] = False

        init_pair_buffer(**kwargs)

    # ── Token-ready callback ──────────────────────────────────────────────────

    async def on_ready_complete(self, pair: TokenItem) -> None:
        """
        Called by the pair buffer when a new token is fully assembled.

        Override in a subclass for completely custom logic, or pass
        ``on_ready`` in :class:`MonitorConfig` for a one-off override.
        The config callback takes full priority when set.
        """
        # if self.config.on_ready is not None:
        #     await self.config.on_ready(pair)
        #     return

        if pair.is_cashback_enabled:
            return

        funding = pair.dev_wallet_funding
        if funding:
            funding.funding_wallet_address = CEXs.get(
                funding.funding_wallet_address,
                funding.funding_wallet_address,
            )
        if not funding:
            return
        if funding and funding.amount_sol < 1:
            return

        self._logger.info(
            "New token ready: %s (%s) | Creator: %s | Sol: %s SOL | Description: %s | Website: %s |"
            "Funding: %s (%s SOL)",
            pair.token_name,
            pair.token_address,
            pair.deployer_address,
            pair.sol_amount,
            pair.description,
            pair.website,
            funding.funding_wallet_address if funding else "N/A",
            funding.amount_sol if funding else "N/A",
        )
        # show_alert(
        #     title=f"Nuevo token: {pair.token_name}",
        #     message=(
        #         f"Token: {pair.token_ticker}\u2026\n"
        #         f"Sol: {pair.sol_amount} SOL\n"
        #         f"Funding: {funding.funding_wallet_address if funding else 'N/A'} ({funding.amount_sol if funding else 'N/A'} SOL)"
        #     ),
        # )

        if self.config.save_to_db and self._token_repo:
            await self._token_repo.save(pair)

    # ── WS message handlers ───────────────────────────────────────────────────

    async def _handle_cluster(self, data: dict[str, Any]) -> None:
        try:
            content = data.get("content", {})
            if self._filter.should_skip("cluster", content):
                return
            protocol_details = content.get("protocol_details", {})
            content["has_axiom_arrived"] = True
            content["is_cashback_enabled"] = protocol_details.get("cashback", None)
            content["is_offchain_enabled"] = protocol_details.get("isOffchain", None)
            _buf().add_pair(content)
        except Exception:
            self._logger.error("Cluster message error", exc_info=True)

    async def _handle_pumpportal(self, data: dict) -> None:
        if self._filter.should_skip("pumpportal", data):
            return
        data["has_pumpportal_arrived"] = True
        _buf().add_pair(data)

    async def _handle_nats(self, msg) -> None:
        data = json.loads(msg.data.decode())
        if self._filter.should_skip("nats", data):
            return
        data["has_nats_arrived"] = True
        _buf().add_pair(data)

    async def _handle_notification(self, message) -> None:
        """Track per-wallet token balances from EucalyptusClient trade events."""
        wallet: str = message[1]
        token_amount: float = message[9]
        usdt_price: float = message[8] * 1_000_000
        mint: str = message[5]
        trade_type: str = message[13]

        self._prices[mint] = usdt_price

        if trade_type == "buy":
            self._balances[wallet][mint] += token_amount
        elif trade_type == "sell":
            prev = self._balances[wallet][mint]
            self._balances[wallet][mint] = max(
                0.0, self._balances[wallet][mint] - token_amount
            )
            if prev >= self.config.low_balance_threshold > self._balances[wallet][mint]:
                show_alert(
                    title="Balance bajo",
                    message=(
                        f"Wallet: {wallet[:8]}\u2026\n"
                        f"Mint: {mint[:8]}\u2026\n"
                        f"Balance: {human_readable_number(self._balances[wallet][mint])} tokens"
                    ),
                    urgency="critical",
                    sound="complete.oga",
                )

    async def _process_pair_update_message(self, message: list[Any]) -> None:
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
            _, pair_address, changes = message
            updates: dict[str, Any] = {}

            for field_index, new_value in changes:
                field_name = FIELD_SHORT_MAP.get(field_index)
                if field_name is None:
                    continue
                updates[field_name] = new_value

            if updates:
                updates["pair_address"] = pair_address
                if "dev_wallet_funding" in updates:
                    updates["dev_wallet_funding"]["fundingWalletAddress"] = CEXs.get(
                        updates["dev_wallet_funding"]["fundingWalletAddress"],
                        updates["dev_wallet_funding"]["fundingWalletAddress"],
                    )
                    updates.update({"has_pulse_arrived": True})
                # print(updates)
                # _buf().add_pair(updates)
                _buf().update_fields(pair_address, updates)
                self._logger.debug(
                    f"Updated fields for {pair_address}: {', '.join(updates)}"
                )

        except Exception as e:
            self._logger.error(f"Failed to process pair update: {e}", exc_info=True)

    async def _process_new_pairs_message(self, message: list[Any]) -> None:
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
            changes = pair_data[1]
            pair_address = changes[0]
            token_address = changes[1]
            updates: dict[str, Any] = {}
            print(
                f"New pair announcement: {pair_address} (token: {token_address}) with {len(changes)} fields changed"
            )

            if not pair_data:
                return

            for field_index, field in UPDATE_FIELD_MAP.items():
                changed_value = (
                    changes[field_index] if field_index < len(changes) else None
                )
                if changed_value is not None:
                    updates[field] = changed_value

            if updates:
                updates["pair_address"] = pair_address
                # print(updates)
                # _buf().add_pair(updates)
                updates.update({"has_pulse_arrived": True})
                if "dev_wallet_funding" in updates:
                    updates["dev_wallet_funding"]["fundingWalletAddress"] = CEXs.get(
                        updates["dev_wallet_funding"]["fundingWalletAddress"],
                        updates["dev_wallet_funding"]["fundingWalletAddress"],
                    )
                if self.config.save_to_db and self._token_repo:
                    _buf().update_fields(pair_address, updates, update_db=True)
                else:
                    _buf().update_fields(pair_address, updates)
                self._logger.debug(
                    f"Updated fields for {pair_address}: {', '.join(updates)}"
                )
        except Exception as e:
            self._logger.error(
                f"Failed to process new pairs message: {e}", exc_info=True
            )

    async def _dispatch_pulse_message(self, message: list[Any]) -> None:
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
                await self._process_pair_update_message(message)
            elif msg_type == 2:
                await self._process_new_pairs_message(message)
            elif msg_type == 3:
                pass  # Reserved type - no action yet
            else:
                self._logger.warning(f"Unknown pulse message type: {msg_type}")

        except Exception as e:
            self._logger.error(f"Failed to dispatch pulse message: {e}", exc_info=True)

    # ── NATS long-running task ────────────────────────────────────────────────

    async def _run_nats(self) -> None:
        nc = await connect_to_nats()
        try:
            await nc.subscribe("newCoinCreated.prod", cb=self._handle_nats)
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await nc.close()

    async def _cleanup_stale_tokens(self) -> None:
        """Background task: every 60 s delete tokens with no market cap after 60 min."""
        while True:
            await asyncio.sleep(60)
            if self._token_repo:
                await self._token_repo.delete_stale()

    # ── Main entry point ──────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start the monitor. Blocks until Ctrl-C or an unhandled error."""
        setup_logging(markup=True)

        cfg = self.config
        subs = cfg.subscriptions

        client = AxiomClient(
            auth_token=cfg.auth_token,
            refresh_token=cfg.refresh_token,
            use_tls_fingerprint=cfg.use_tls_fingerprint,
            load_cookies=cfg.load_cookies,
            defer_session=True,
        )
        self.db_manager = get_async_db_manager()

        self._init_pair_buffer()

        # ── Build WS clients ──────────────────────────────────────────────────
        ws_pumpportal: PumpPortalWSClient | None = None
        ws_cluster: AxiomClusterWSClient | None = None
        ws_pulse: AxiomPulseWSClient | None = None
        ws_notifications: EucalyptusClient | None = None

        needs_axiom_client = bool(subs & {"cluster", "pulse", "notifications"})
        if needs_axiom_client:
            await client.init_session()

        if "pumpportal" in subs:
            ws_pumpportal = PumpPortalWSClient(heartbeat=30, telegram_bot=self._tg_bot)
            await ws_pumpportal.subscribe_new_token(self._handle_pumpportal)

        if "cluster" in subs:
            ws_cluster = AxiomClusterWSClient(
                log_level=logging.INFO, client=client, telegram_bot=self._tg_bot
            )
            await ws_cluster.subscribe_new_tokens(self._handle_cluster)

        if "pulse" in subs:
            ws_pulse = AxiomPulseWSClient(
                log_level=logging.INFO, client=client, telegram_bot=self._tg_bot
            )
            await ws_pulse.subscribe_pulse(self._dispatch_pulse_message)

        if "notifications" in subs:
            ws_notifications = EucalyptusClient(
                log_level=logging.INFO, client=client, telegram_bot=self._tg_bot
            )
            await ws_notifications.sub_test(self._handle_notification)

        # ── Build async task group ────────────────────────────────────────────
        def _populate_tasks(tg: asyncio.TaskGroup) -> None:
            if ws_cluster:
                tg.create_task(ws_cluster.start(), name="axiom-cluster")
            if ws_pulse:
                tg.create_task(ws_pulse.start(), name="axiom-pulse")
            if ws_pumpportal:
                tg.create_task(ws_pumpportal.start(), name="pumpportal")
            if ws_notifications:
                tg.create_task(ws_notifications.start(), name="notifications")
            if "nats" in subs:
                tg.create_task(self._run_nats(), name="nats")
            # if self._token_repo:
            #     tg.create_task(self._cleanup_stale_tokens(), name="stale-cleanup")

        # ── Run with or without Rich Live ─────────────────────────────────────
        try:
            if cfg.use_rich:
                redirect_logs_to_buffer()
                layout = make_layout(cfg.balances_panel_width)
                with Live(layout, refresh_per_second=10, screen=True):
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(
                            run_display(
                                layout,
                                self._balances,
                                self._prices,
                                cfg.low_balance_threshold,
                            ),
                            name="display",
                        )
                        _populate_tasks(tg)
            else:
                async with asyncio.TaskGroup() as tg:
                    _populate_tasks(tg)

        except* KeyboardInterrupt:
            self._logger.info("Monitor interrupted")

        finally:
            await self._cleanup(client, ws_pumpportal)

    async def _cleanup(
        self,
        client: AxiomClient,
        ws_pumpportal: PumpPortalWSClient | None,
    ) -> None:
        tasks: list[Any] = []
        if ws_pumpportal:
            tasks.append(ws_pumpportal.close())
        tasks.append(close_session())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        try:
            await client.session.close()
        except Exception:
            pass
        self._logger.info("All connections closed")


# ── Quick-start ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    monitor = Monitor(
        MonitorConfig(
            use_rich=False,
            subscriptions={"cluster", "pulse", "pumpportal"},
            # subscriptions={"pumpportal"},
            save_to_db=False,
            fetch_metadata=False,
            refresh_token="<your_refresh_token>",
        )
    )
    try:
        asyncio.run(monitor.run())
    except KeyboardInterrupt:
        pass
