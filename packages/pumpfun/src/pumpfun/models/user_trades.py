from pydantic import Field, field_validator, model_validator

from shared_lib.pydantic import APIBaseModel


class Trades(APIBaseModel):
    slot: int = Field(..., alias="slotIndexId")
    tx: str
    timestamp: str
    user_address: str = Field(..., alias="userAddress")
    type: str
    is_bonding_curve: bool = Field(..., alias="isBondingCurve")
    quote_amount: int = Field(..., alias="quoteAmount")
    base_amount: int = Field(..., alias="baseAmount")
    price_usd: float | None = Field(..., alias="priceUSD")
    amount_sol: float | None = Field(..., alias="amountSOL")

    @field_validator("slot", mode="before")
    @classmethod
    def get_slot(cls, v):
        """slot_index_id from 0004209103440010650001 to 000420910344"""
        return int(v[:12])


class UserTradesResponse(APIBaseModel):
    """User Trades on token Response Model"""

    user_trades: list[Trades]

    @model_validator(mode="before")
    def set_user_trades(cls, data):
        if not isinstance(data, dict):
            raise ValueError("Expected a dictionary")

        if len(data) != 1:
            raise ValueError("Expected only one user address in the response")

        try:
            (_, trades) = next(iter(data.items()))
        except StopIteration:
            raise ValueError("Response data is empty")

        return {"user_trades": trades}

    @field_validator("user_trades", mode="before")
    def validate_user_trades(cls, v):
        if not isinstance(v, list):
            raise TypeError("user_trades must be a list")
        # if len(v) == 0:
        #     raise ValueError("user_trades list cannot be empty")
        # if v[-1]["type"] != "buy":
        #     raise ValueError("The last trade must be a 'buy' type")
        return v
