from __future__ import annotations

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Wallet(Base):
    __tablename__ = "wallets"

    wallet_address: Mapped[str] = mapped_column(String, primary_key=True)
    dev_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    migrated_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # One dev can have many tokens
    tokens: Mapped[list[Token]] = relationship("Token", back_populates="dev_wallet")

    # This wallet has funded many other wallets
    funded_wallets: Mapped[list[DevWalletFunding]] = relationship(
        "DevWalletFunding",
        foreign_keys="DevWalletFunding.funder_wallet_address",
        back_populates="funder_wallet",
    )
    # This wallet was funded by at most one other wallet
    funding_received: Mapped[DevWalletFunding | None] = relationship(
        "DevWalletFunding",
        foreign_keys="DevWalletFunding.funded_wallet_address",
        back_populates="funded_wallet",
        uselist=False,
    )


class DevWalletFunding(Base):
    __tablename__ = "dev_wallet_fundings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    funder_wallet_address: Mapped[str] = mapped_column(
        String, ForeignKey("wallets.wallet_address"), nullable=False
    )
    # unique=True enforces that a wallet can only be funded by one wallet
    funded_wallet_address: Mapped[str] = mapped_column(
        String, ForeignKey("wallets.wallet_address"), nullable=False, unique=True
    )
    signature: Mapped[str] = mapped_column(String, nullable=False)
    amount_sol: Mapped[float] = mapped_column(Float, nullable=False)
    funded_at: Mapped[str] = mapped_column(String, nullable=False)

    funder_wallet: Mapped[Wallet] = relationship(
        "Wallet",
        foreign_keys=[funder_wallet_address],
        back_populates="funded_wallets",
    )
    funded_wallet: Mapped[Wallet] = relationship(
        "Wallet",
        foreign_keys=[funded_wallet_address],
        back_populates="funding_received",
    )


class Token(Base):
    __tablename__ = "tokens"

    pair_address: Mapped[str] = mapped_column(String, primary_key=True)
    signature: Mapped[str | None] = mapped_column(String, nullable=True)
    token_address: Mapped[str | None] = mapped_column(
        String, nullable=True, unique=True
    )
    deployer_address: Mapped[str | None] = mapped_column(
        String, ForeignKey("wallets.wallet_address"), nullable=True
    )
    token_name: Mapped[str | None] = mapped_column(String, nullable=True)
    token_ticker: Mapped[str | None] = mapped_column(String, nullable=True)
    token_uri: Mapped[str | None] = mapped_column(String, nullable=True)
    # token_decimals: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # protocol: Mapped[str | None] = mapped_column(String, nullable=True)
    is_cashback_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_offchain_enabled: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sol_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    initial_buy: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_mayhem_mode: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=False
    )
    market_cap_sol: Mapped[float | None] = mapped_column(Float, nullable=True)
    migration_ts: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # supply: Mapped[float | None] = mapped_column(Float, nullable=True)
    # bonding_curve_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
    buy_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    website: Mapped[str | None] = mapped_column(String, nullable=True)
    has_website: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    twitter: Mapped[str | None] = mapped_column(String, nullable=True)
    has_twitter: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    telegram: Mapped[str | None] = mapped_column(String, nullable=True)
    has_telegram: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    desc_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uri_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_description: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    live: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # is_currently_live: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dev_holds_percent: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Many tokens → one dev wallet
    dev_wallet: Mapped[Wallet | None] = relationship("Wallet", back_populates="tokens")
