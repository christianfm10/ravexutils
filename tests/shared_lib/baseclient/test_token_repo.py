"""
Tests for TokenRepository.save() under concurrent load.

Scenario: 3 token pairs are saved simultaneously, all sharing the same
deployer_address and the same dev_wallet_funding object.

This validates:
  1. The atomic _upsert_wallet (INSERT ON CONFLICT) prevents UNIQUE
     violations on the wallets table regardless of coroutine interleaving.
  2. All 3 Token rows are committed successfully.
  3. Only 1 DevWalletFunding row exists (funded_wallet_address is UNIQUE).

NOTE on DevWalletFunding race:
  The DevWalletFunding INSERT still uses SELECT-then-add. Under asyncio,
  all 3 coroutines can SELECT before any commit happens → all 3 queue an
  INSERT → 2 fail silently → only 1 Token saves. If test_2 fails with
  token_count < 3, apply INSERT OR IGNORE (ON CONFLICT DO NOTHING) to
  the DevWalletFunding step in save() as well.
"""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from shared_lib.database.token_repository import TokenRepository
from shared_lib.database.db_manager import AsyncDatabaseManager
from shared_lib.database.entities import (
    DevWalletFunding as DbDevWalletFunding,
    Token as DbToken,
    Wallet as DbWallet,
)
from shared_lib.models.token import DevWalletFunding, TokenItem
from sqlalchemy import func, select
import sys


def simple_excepthook(exc_type, exc_value, exc_traceback):
    print(f"Error: {exc_value}")


sys.excepthook = simple_excepthook

DEPLOYER = "DeployerWallet1111111111111111111111"
MINT = "Mint11111111111111111111111111111111"
FUNDER = "FunderWallet99999999999999999999999999"

PATCH_TARGET = "shared_lib.database.token_repository.get_async_db_manager"


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db_manager(tmp_path):
    """Fresh SQLite DB in a temp directory; tables are created once per test."""
    # Importing TokenRepository already registered entities on Base.metadata
    manager = AsyncDatabaseManager(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        echo=False,
    )
    await manager.create_tables()
    yield manager
    await manager.close()


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_funding() -> DevWalletFunding:
    return DevWalletFunding.model_validate(
        {
            "walletAddress": DEPLOYER,
            "fundingWalletAddress": FUNDER,
            "signature": "SigFundingABC123",
            "amountSol": 1.5,
            "fundedAt": "2026-06-04T00:00:00+00:00",
        }
    )


def _make_pair(
    index: int, funding: DevWalletFunding | None = None, mint: str | None = None
) -> TokenItem:
    return TokenItem.model_validate(
        {
            "pair_address": f"PairAddress{index:03d}",
            "mint": mint or f"Mint{index:03d}111111111111111111111111111",
            "creator": DEPLOYER,
            "name": f"TestToken{index}",
            "symbol": f"TK{index}",
            "uri": None,
            "dev_wallet_funding": funding,
            "dev_tokens": 1,
        }
    )


async def _count(manager: AsyncDatabaseManager, model) -> int:
    async with manager.get_session() as session:
        result = await session.execute(select(func.count()).select_from(model))
        return result.scalar_one()


# ── tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_concurrent_save_same_deployer_no_funding(db_manager):
    """
    3 concurrent saves, same deployer_address, no dev_wallet_funding.

    Verifies the atomic wallet upsert (INSERT ON CONFLICT DO UPDATE) prevents
    UNIQUE violations on wallets regardless of coroutine interleaving.
    """
    repo = TokenRepository(db_manager)
    pairs = [_make_pair(i) for i in range(3)]

    await asyncio.gather(*[repo.save(p) for p in pairs])

    wallet_count = await _count(db_manager, DbWallet)
    token_count = await _count(db_manager, DbToken)

    assert wallet_count == 1, (
        f"Expected 1 wallet for the shared deployer, got {wallet_count}"
    )
    assert token_count == 3, f"Expected 3 tokens, got {token_count}"


@pytest.mark.asyncio
async def test_concurrent_save_same_deployer_and_funding(db_manager):
    """
    3 concurrent saves, same deployer_address AND same dev_wallet_funding.

    Expected final DB state:
      wallets            → 2 rows  (deployer + funder)
      dev_wallet_fundings → 1 row  (funded_wallet_address has UNIQUE constraint)
      tokens              → 3 rows  (each pair_address is distinct)

    If token_count < 3 this test documents the remaining DevWalletFunding
    SELECT-then-add race condition (see module docstring).
    """
    repo = TokenRepository(db_manager)
    funding = _make_funding()
    pairs = [_make_pair(i, funding=funding) for i in range(3)]

    await asyncio.gather(*[repo.save(p) for p in pairs])

    wallet_count = await _count(db_manager, DbWallet)
    dwf_count = await _count(db_manager, DbDevWalletFunding)
    token_count = await _count(db_manager, DbToken)

    assert wallet_count == 2, (
        f"Expected 2 wallets (deployer + funder), got {wallet_count}"
    )
    assert dwf_count == 1, f"Expected 1 DevWalletFunding row, got {dwf_count}"
    assert token_count == 3, (
        f"Expected 3 tokens, got {token_count}. "
        "If this is < 3, the DevWalletFunding INSERT also needs an atomic "
        "ON CONFLICT DO NOTHING (see token_repository.py save() step 2)."
    )


@pytest.mark.asyncio
async def test_concurrent_save_same_mint_no_funding(db_manager):
    """
    3 concurrent saves, same mint, no dev_wallet_funding.

    Verifies the atomic wallet upsert (INSERT ON CONFLICT DO UPDATE) prevents
    UNIQUE violations on wallets regardless of coroutine interleaving.
    """
    repo = TokenRepository(db_manager)
    pairs = [_make_pair(i, mint=MINT) for i in range(3)]

    await asyncio.gather(*[repo.save(p) for p in pairs])

    wallet_count = await _count(db_manager, DbWallet)
    token_count = await _count(db_manager, DbToken)

    assert wallet_count == 1, (
        f"Expected 1 wallet for the shared deployer, got {wallet_count}"
    )
    assert token_count == 3, f"Expected 3 tokens, got {token_count}"


@pytest.mark.asyncio
async def test_delete_stale_tokens(db_manager):
    import time

    repo = TokenRepository(db_manager)

    # Token 1: Stale (None market cap, created_at is 15 minutes ago, so timestamp is older)
    t1 = _make_pair(1)
    t1.created_at = int(time.time()) - 15 * 60
    t1.market_cap_sol = None

    # Token 2: Non-stale (None market cap, created_at is 5 minutes ago)
    t2 = _make_pair(2)
    t2.created_at = int(time.time()) - 5 * 60
    t2.market_cap_sol = None

    # Token 3: Not stale (Has market cap, created_at is 15 minutes ago)
    t3 = _make_pair(3)
    t3.created_at = int(time.time()) - 15 * 60
    t3.market_cap_sol = 100.0

    await repo.save(t1)
    await repo.save(t2)
    await repo.save(t3)

    # Run delete_stale
    deleted = await repo.delete_stale(max_age_minutes=10)
    assert deleted == 1

    # Check database state
    async with db_manager.get_session() as session:
        tokens = (await session.execute(select(DbToken))).scalars().all()
        pair_addresses = {t.pair_address for t in tokens}

    # Token 1 should be deleted.
    # Token 2 should be preserved (too young).
    # Token 3 should be preserved (has market cap).
    assert "PairAddress001" not in pair_addresses
    assert "PairAddress002" in pair_addresses
    assert "PairAddress003" in pair_addresses
