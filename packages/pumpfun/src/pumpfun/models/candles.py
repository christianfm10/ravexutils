from shared_lib.pydantic import APIBaseModel


class Candles(APIBaseModel):
    open: str
    low: str
    high: str
    close: str
    timestamp: int
    volume: str
