from shared_lib.database.base import Base
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    func,
)


class UserCreatedCoinDB(Base):
    """Pump.fun coin created by a user."""

    __tablename__ = "user_created_coins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mint = Column(String, nullable=False, unique=True, index=True)
    name = Column(String, nullable=False)
    symbol = Column(String, nullable=False)
    bonding_curve = Column(String, nullable=False)
    creator = Column(String, nullable=False, index=True)
    complete = Column(Boolean, nullable=False, default=False)
    ath_market_cap = Column(Float, nullable=True)
    ath_market_cap_timestamp = Column(Integer, nullable=True)
    created_timestamp = Column(Integer, nullable=True)
    description = Column(String, nullable=True)
    banner_uri = Column(String, nullable=True)
    website = Column(String, nullable=True)
    twitter = Column(String, nullable=True)
    metadata_uri = Column(String, nullable=True)
    init_price = Column(Float, nullable=True)
    is_active = Column(Boolean, nullable=True)

    # Timestamps
    inserted_at = Column(DateTime, default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, default=func.now(), onupdate=func.now(), nullable=False
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
