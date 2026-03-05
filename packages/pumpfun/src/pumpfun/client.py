from pumpfun.models.candles import Candles
from shared_lib.baseclient.client import BaseClient
from .models.coin_info import (
    CoinInfoResponse,
)
from .models.user_trades import (
    Trades,
    UserTradesResponse,
)
from .models.user_created_coins import (
    UserCreatedCoinsResponse,
)


class PumpfunClient(BaseClient):
    """Pumpfun Client Class"""

    BASE_URL = "https://frontend-api-v3.pump.fun"
    BASE_V2 = "https://swap-api.pump.fun/v2"
    BASE_ADVANCED = "https://advanced-api-v2.pump.fun"

    DEFAULT_HEADERS = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br",
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/535.36",
    }

    def __init__(
        self,
        **kwargs,
    ):
        """
        Initialize a Pumpfun Client instance

        **Parameters:**
        - `**kwargs` (dict, optional): Opciones adicionales.
            - `verify` (bool): Verify SSL.
            - `timeout` (int): Timeout request.
            - `proxy` (str): Proxy address.

        **Returns:**
        - `PumpfunClient`: Pumpfun Client
        """
        super().__init__(**kwargs)
        self.client.headers.update(self.DEFAULT_HEADERS)

    async def get_coin_info(self, token_address: str) -> CoinInfoResponse:
        """
        Obtiene la información de una memecoin de Pump.fun usando su dirección (mint address).

        :param token_address: Dirección del token en Solana (mint address).
        :return: Diccionario con la información del token o mensaje de error.
        """
        endpoint = f"/coins/{token_address}"
        params = {
            "sync": "true",
        }

        return CoinInfoResponse(**await self._fetch("GET", endpoint, params))

    async def get_user_created_coins(
        self, user_id: str, **kwargs
    ) -> UserCreatedCoinsResponse:
        """
        Obtiene las memecoins creadas por un usuario específico en Pump.fun.
        """

        endpoint = f"/coins-v2/user-created-coins/{user_id}"
        params = {"offset": 0, "limit": 10, "includeNsfw": "false"}
        params.update(**kwargs)

        data = await self._fetch("GET", endpoint, params)

        data = UserCreatedCoinsResponse(**data)
        # data = [UserCreatedCoin(**x) for x in data["coins"]]

        return data

    async def get_user_token_trades(
        self, token_address: str, user_address: str
    ) -> list[Trades]:
        """
        Obtiene las operaciones (trades) realizadas por un desarrollador específico en una memecoin de Pump.fun.
        """

        endpoint = f"/coins/{token_address}/trades/batch"
        payload = {"userAddresses": [f"{user_address}"]}
        self.BASE_URL = self.BASE_V2

        trades = UserTradesResponse(
            **await self._fetch("POST", endpoint, payload=payload)
        )

        return trades.user_trades

    async def get_candles(
        self,
        token_address: str,
        *,
        interval: str = "15s",
        limit: int = 10,
        currency: str = "USD",
        program: str = "pump",
        createdTs: int,
        beforeTs: int | None = None,
        **kwargs,
    ) -> list[Candles]:
        r"""Sends a GET request to the Pump.fun swap API to fetch candle data.

        :param token_address: Token mint.
        :param interval: Time interval for each candle. Example: ``15s``.
        :param \*\*kwargs: Optional query parameters:
            - ``limit`` (int): Maximum number of candles to return. Example: ``1000``.
            - ``currency`` (str): Currency in which the candle values are denominated. Example: ``USD``.
            - ``before_ts`` (int): Unix timestamp to fetch candles before that time. Example: ``1748671695``.
        :return: Diccionario con la información del token o mensaje de error.
        """
        url = f"/coins/{token_address}/candles"
        params = {
            "interval": interval,
            "limit": limit,
            "currency": currency,
            "program": program,
            "createdTs": createdTs,
        }
        if beforeTs is not None:
            params["beforeTs"] = beforeTs
        params.update(**kwargs)
        data = await self._get(url, params=params, base_url=self.BASE_V2)
        data = [data] if isinstance(data, dict) else data

        data = [Candles(**x) for x in data]
        return data
