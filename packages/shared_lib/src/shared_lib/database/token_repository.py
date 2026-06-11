"""
Repository for all database operations on the Token entity.

Handles upsert of the full token graph (Wallet → DevWalletFunding → Token)
and partial updates by pair_address.
"""

from __future__ import annotations

import logging

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

from shared_lib.database.db_manager import get_async_db_manager
from shared_lib.database.entities import DevWalletFunding as DbDevWalletFunding
from shared_lib.database.entities import Token as DbToken
from shared_lib.database.entities import Wallet as DbWallet
from shared_lib.models.token import TokenItem

_logger = logging.getLogger(__name__)


class TokenRepository:
    """CRUD operations on the Token entity and its related Wallet graph."""

    @staticmethod
    async def _upsert_wallet(
        session: AsyncSession,
        wallet_address: str,
        dev_tokens: int | None = None,
        migrated_tokens: int | None = None,
    ) -> None:
        """
        Atomic wallet upsert safe for concurrent sessions.

        Uses ``INSERT … ON CONFLICT DO UPDATE`` so SQLite serialises the write
        itself — no Python-level SELECT→INSERT race possible.
        Non-None fields overwrite the existing row; None fields keep whatever
        is already stored (via COALESCE).
        """

        dialect = session.bind.dialect.name

        if dialect == "sqlite":
            insert_stmt = sqlite_insert(DbWallet)
        elif dialect == "postgresql":
            insert_stmt = postgres_insert(DbWallet)
        else:
            raise NotImplementedError(
                f"Unsupported database dialect for upsert: {dialect}"
            )
        stmt = insert_stmt.values(
            wallet_address=wallet_address,
            dev_tokens=dev_tokens,
            migrated_tokens=migrated_tokens,
        )
        await session.execute(
            stmt.on_conflict_do_update(
                index_elements=["wallet_address"],
                set_={
                    "dev_tokens": func.coalesce(
                        stmt.excluded.dev_tokens, DbWallet.dev_tokens
                    ),
                    "migrated_tokens": func.coalesce(
                        stmt.excluded.migrated_tokens, DbWallet.migrated_tokens
                    ),
                },
            )
        )

    async def save(self, pair: TokenItem) -> None:
        """
        Upsert a fully-assembled token into the database.

        Writes (in order):
        1. ``Wallet`` row for the deployer
        2. ``Wallet`` row for the funder + ``DevWalletFunding`` link (if present)
        3. ``Token`` row

        All three writes share a single session/transaction; on any error
        the whole operation is rolled back and the exception is logged.
        """
        try:
            db = await get_async_db_manager()
            async with db.get_session() as session:
                # 1. Deployer wallet
                if pair.deployer_address:
                    await TokenRepository._upsert_wallet(
                        session,
                        pair.deployer_address,
                        dev_tokens=pair.dev_tokens,
                        migrated_tokens=pair.migrated_tokens,
                    )

                # 2. Funder wallet + DevWalletFunding link
                if pair.dev_wallet_funding:
                    funder = pair.dev_wallet_funding.funding_wallet_address
                    funded = pair.dev_wallet_funding.wallet_address
                    await TokenRepository._upsert_wallet(session, funder)
                    result = await session.execute(
                        select(DbDevWalletFunding).where(
                            DbDevWalletFunding.funded_wallet_address == funded
                        )
                    )
                    if result.scalar_one_or_none() is None:
                        session.add(
                            DbDevWalletFunding(
                                funder_wallet_address=funder,
                                funded_wallet_address=funded,
                                signature=pair.dev_wallet_funding.signature,
                                amount_sol=pair.dev_wallet_funding.amount_sol,
                                funded_at=pair.dev_wallet_funding.funded_at,
                            )
                        )

                # 3. Token
                await session.merge(
                    DbToken(
                        pair_address=pair.pair_address,
                        signature=pair.signature,
                        token_address=pair.token_address,
                        deployer_address=pair.deployer_address,
                        token_name=pair.token_name,
                        token_ticker=pair.token_ticker,
                        token_uri=pair.token_uri,
                        is_cashback_enabled=pair.is_cashback_enabled,
                        is_offchain_enabled=pair.is_offchain_enabled,
                        sol_amount=pair.sol_amount,
                        initial_buy=pair.initial_buy,
                        is_mayhem_mode=pair.is_mayhem_mode,
                        market_cap_sol=pair.market_cap_sol,
                        created_at=pair.created_at,
                        buy_amount=pair.buy_amount,
                        website=pair.website,
                        has_website=pair.has_website,
                        twitter=pair.twitter,
                        has_twitter=pair.has_twitter,
                        telegram=pair.telegram,
                        has_telegram=pair.has_telegram,
                        description=pair.description,
                        has_description=pair.has_description,
                        desc_size=getattr(pair, "desc_size", None),
                        uri_size=getattr(pair, "uri_size", None),
                        dev_holds_percent=pair.dev_holds_percent,
                    )
                )
        except Exception:
            _logger.error(
                "Failed to save token %s to DB", pair.pair_address, exc_info=True
            )

    async def update(self, data: dict) -> None:
        """
        Partially update an existing token by ``pair_address``.

        Handles:
        - Token columns: any key matching a column on :class:`~.entities.Token`
        - ``dev_tokens`` / ``migrated_tokens``: applied to the deployer Wallet
        - ``dev_wallet_funding`` dict: upserts funder Wallet + DevWalletFunding

        Unknown keys are silently ignored.
        If no token with the given ``pair_address`` exists, the call is a no-op.
        """
        try:
            _logger.warning(f"update: {data}")
            db = await get_async_db_manager()
            async with db.get_session() as session:
                pair_address = data.get("pair_address")
                if not pair_address:
                    _logger.warning("update() called without pair_address — skipping")
                    return

                result = await session.execute(
                    select(DbToken).where(DbToken.pair_address == pair_address)
                )
                token = result.scalar_one_or_none()
                if token is None:
                    _logger.warning("No token found for pair_address=%s", pair_address)
                    return

                # ── 1. Update Token columns ───────────────────────────────────
                _skip = {"dev_wallet_funding", "dev_tokens", "migrated_tokens"}
                for key, value in data.items():
                    if key not in _skip and hasattr(token, key):
                        setattr(token, key, value)

                # ── 2. Update deployer Wallet (dev_tokens / migrated_tokens) ──
                wallet_updates = {
                    k: data[k] for k in ("dev_tokens", "migrated_tokens") if k in data
                }
                if wallet_updates and token.deployer_address:
                    result_w = await session.execute(
                        select(DbWallet).where(
                            DbWallet.wallet_address == token.deployer_address
                        )
                    )
                    deployer = result_w.scalar_one_or_none()
                    if deployer is not None:
                        for k, v in wallet_updates.items():
                            setattr(deployer, k, v)

                # ── 3. Upsert DevWalletFunding ────────────────────────────────
                dwf_raw = data.get("dev_wallet_funding")
                if dwf_raw:
                    funded = dwf_raw.get("walletAddress")
                    funder = dwf_raw.get("fundingWalletAddress")
                    signature = dwf_raw.get("signature")
                    if funded and funder:
                        await TokenRepository._upsert_wallet(session, funder)
                        result_dwf = await session.execute(
                            select(DbDevWalletFunding).where(
                                DbDevWalletFunding.signature == signature,
                            )
                        )
                        if result_dwf.scalar_one_or_none() is None:
                            session.add(
                                DbDevWalletFunding(
                                    funder_wallet_address=funder,
                                    funded_wallet_address=funded,
                                    signature=dwf_raw.get("signature"),
                                    amount_sol=dwf_raw.get("amountSol"),
                                    funded_at=dwf_raw.get("fundedAt"),
                                )
                            )
        except Exception:
            _logger.error(
                "Failed to update token %s in DB",
                data.get("pair_address"),
                exc_info=True,
            )

    async def delete_stale(self, max_age_minutes: int = 10) -> int:
        """
        Delete:

        1. Tokens where ``market_cap_sol`` is NULL and ``created_at`` is
           older than *max_age_minutes*.
        2. Wallets not referenced by any ``DevWalletFunding`` row — neither
           as ``funder_wallet_address`` nor as ``funded_wallet_address``.

        Tokens are deleted first so their FK reference to wallets is gone
        before the wallet cleanup runs.  Returns the total rows deleted.
        """
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        ).isoformat()
        try:
            db = await get_async_db_manager()
            async with db.get_session() as session:
                # 1. Stale tokens (no market cap, past cutoff)
                token_result = await session.execute(
                    delete(DbToken)
                    .where(DbToken.market_cap_sol.is_(None))
                    .where(DbToken.created_at.isnot(None))
                    .where(DbToken.created_at < cutoff)
                )
                deleted_tokens: int = token_result.rowcount  # type: ignore[union-attr]

                # 2. Orphan wallets — not referenced by any funding row or token
                funder_sq = select(DbDevWalletFunding.funder_wallet_address)
                funded_sq = select(DbDevWalletFunding.funded_wallet_address)
                deployer_sq = select(DbToken.deployer_address).where(
                    DbToken.deployer_address.isnot(None)
                )
                wallet_result = await session.execute(
                    delete(DbWallet)
                    .where(DbWallet.wallet_address.not_in(funder_sq))
                    .where(DbWallet.wallet_address.not_in(funded_sq))
                    .where(DbWallet.wallet_address.not_in(deployer_sq))
                )
                deleted_wallets: int = wallet_result.rowcount  # type: ignore[union-attr]

                if deleted_tokens or deleted_wallets:
                    _logger.info(
                        "Deleted %d stale token(s) and %d orphan wallet(s) "
                        "(no market cap older than %d min / not in fundings)",
                        deleted_tokens,
                        deleted_wallets,
                        max_age_minutes,
                    )
                return deleted_tokens + deleted_wallets
        except Exception:
            _logger.error("Failed to delete stale tokens/wallets", exc_info=True)
            return 0
