from shared_lib.pydantic import APIBaseModel
from pydantic import Field


class PumpPortalBaseModel(APIBaseModel):
    sol_amount: float
    creator: str = Field(alias="traderPublicKey")
    mint: str
    name: str | None = None
    symbol: str | None = None
    tx_type: str
    uri: str | None = None
    signature: str
    is_scam: bool = False
    pool: str
    market_cap_sol: float = 0.0
