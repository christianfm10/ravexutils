from datetime import datetime

from shared_lib.database.base import Base
from sqlalchemy import ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship


class UserCreatedCoinDB(Base):
    """Pump.fun coin created by a user."""

    __tablename__ = "user_created_coins"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    mint: Mapped[str] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    symbol: Mapped[str]
    bonding_curve: Mapped[str]
    creator: Mapped[str] = mapped_column(index=True)
    complete: Mapped[bool] = mapped_column(default=False)
    ath_market_cap: Mapped[float | None]
    ath_market_cap_timestamp: Mapped[int | None]
    created_timestamp: Mapped[int | None]
    description: Mapped[str | None]
    banner_uri: Mapped[str | None]
    website: Mapped[str | None]
    twitter: Mapped[str | None]
    telegram: Mapped[str | None]
    metadata_uri: Mapped[str | None]
    init_price: Mapped[float | None]
    is_active: Mapped[bool | None]
    is_cashback_enabled: Mapped[bool | None]
    migration_timestamp: Mapped[int | None]

    # Timestamps
    inserted_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("idx_user_created_coins_creator", "creator"),
        Index("idx_user_created_coins_complete", "complete"),
    )

    def __repr__(self):
        return (
            f"<UserCreatedCoinDB(mint={self.mint}, "
            f"name={self.name}, symbol={self.symbol}, creator={self.creator})>"
        )


class Funder(Base):
    __tablename__ = "funder"

    txn: Mapped[str] = mapped_column(primary_key=True)
    funder: Mapped[str]
    amount: Mapped[float | None]
    block_time: Mapped[int | None]
    dev_pk: Mapped[str] = mapped_column(
        ForeignKey("user_created_coins.mint"), nullable=False
    )

    dev: Mapped["UserCreatedCoinDB"] = relationship("UserCreatedCoinDB")

    def __repr__(self) -> str:
        return f"<Funder txn={self.txn} funder={self.funder} dev_pk={self.dev_pk}>"
