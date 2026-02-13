from shared_lib.pydantic import APIBaseModel


class UserCreatedCoin(APIBaseModel):
    name: str
    symbol: str
    mint: str
    bonding_curve: str
    ath_market_cap: float | None = None
    created_timestamp: int | None = None
    description: str | None = None
    website: str | None = None
    twitter: str | None = None
    metadata_uri: str | None = None


class UserCreatedCoinsResponse(APIBaseModel):
    coins: list[UserCreatedCoin]
    count: int
