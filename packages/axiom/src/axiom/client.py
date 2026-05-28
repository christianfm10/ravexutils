"""Axiom Trade HTTP client built on top of BaseAioHttpClient.

Provides cookie-based authentication, automatic token refresh, and
convenience methods for the Axiom Trade REST API.
"""

from __future__ import annotations
import logging
import aiohttp
from typing import Any
from shared_lib.baseclient.auth_aiohttp_client import AuthAioHttpClient

from axiom.urls import AxiomTradeApiUrls, AxiomEndpoint


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AxiomClient(AuthAioHttpClient):
    """Axiom Trade REST client.

    Wraps :class:`BaseAioHttpClient` with Axiom-specific authentication:
    cookie-based token injection, automatic token refresh via
    ``/refresh-access-token``, and an ``ensure_authenticated`` guard that
    is called transparently before every request.

    Parameters
    ----------
    auth_token:
        Initial ``auth-access-token`` cookie value.
    refresh_token:
        Initial ``auth-refresh-token`` cookie value.
    storage_dir:
        Reserved for future persistent-session support.
    load_cookies:
        When *True* the base class attempts to load a previous session from
        :attr:`SESSION_FILE`.
    log_level:
        Python logging level for this client's logger.
    use_tls_finger_print:
        Forward TLS-fingerprinting flag to the base class.
    **kwargs:
        Extra keyword arguments forwarded to :class:`BaseAioHttpClient`.
    """

    # BASE_URL: str = AAllBaseUrls.BASE_URL_v8
    SESSION_FILE: str = "session3.json"
    ENDPOINT = AxiomEndpoint.endpoint

    _DEFAULT_HEADERS: dict[str, str] = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/json",
        "Connection": "keep-alive",
        "Host": ENDPOINT.host,
        "Origin": ENDPOINT.origin,
        "Referer": ENDPOINT.origin + "/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "TE": "trailers",
        "User-Agent": _DEFAULT_USER_AGENT,
    }

    def __init__(
        self,
        auth_token: str | None = None,
        refresh_token: str | None = None,
        storage_dir: str | None = None,  # noqa: ARG002 – reserved for future use
        load_cookies: bool = True,
        log_level: int = logging.INFO,
        use_tls_fingerprint: bool = True,
        defer_session: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            auth_token=auth_token,
            refresh_token=refresh_token,
            base_url=self.endpoint.str_url,
            headers=self._DEFAULT_HEADERS,
            use_tls_fingerprint=use_tls_fingerprint,
            load_cookies=load_cookies,
            defer_session=defer_session,
            **kwargs,
        )

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

    async def refresh_request(self) -> aiohttp.ClientResponse:
        """Make the actual refresh request to the server."""
        self.session.headers.update({"Host": self.endpoint.host})
        return await self._fetch_unauthenticated(
            "POST", AxiomTradeApiUrls.REFRESH_TOKEN
        )

    # ------------------------------------------------------------------
    # API endpoints
    # ------------------------------------------------------------------

    async def get_token_info(self, token_address: str) -> dict[str, Any]:
        """Fetch on-chain/market information for *token_address*.

        Parameters
        ----------
        token_address:
            Blockchain address of the token to look up.

        Returns
        -------
        dict[str, Any]
            Token data returned by the Axiom API.
        """
        self.logger.debug("Fetching token info for %s", token_address)
        try:
            return await self._get(f"/token/{token_address}")
        except Exception as exc:
            self.logger.error("Error fetching token info: %s", exc)
            raise Exception(f"Failed to get token info: {exc}") from exc

    # https://api7.axiom.trade/pair-chart-v2?pairAddress=9WrdaWu9BpezUU9g4pPR4H6A3q1PA1hztSvNg18chmm1&from=1779156360000&to=1779156689000&currency=USD&interval=1s&countBars=329&showOutliers=false&openTrading=1770351529012&pairCreatedAt=1770351885050&lastTransactionTime=1774963855029&isNew=false&isMigrated=true&tokenAddress=7k3r2EH7NhVjqs5yJp7LpmUiytVQ9tX8fP4BHUgcpump&v=1779156629235

    async def get_pair_chart(
        self,
        pair_address: str,
        from_timestamp: int,
        to_timestamp: int,
        currency: str = "USD",
        interval: str = "1s",
        count_bars: int = 329,
        show_outliers: bool = False,
        open_trading: int = 1770351529012,
        pair_created_at: int = 1770351885050,
        last_transaction_time: int = 1774963855029,
        is_new: bool = False,
        is_migrated: bool = True,
        token_address: str = "7k3r2EH7NhVjqs5yJp7LpmUiytVQ9tX8fP4BHUgcpump",
        v: int = 1779156629235,
    ) -> dict[str, Any]:
        """Fetch historical price chart data for *pair_address*.

        Parameters
        ----------
        pair_address:
            Blockchain address of the pair to look up.
        from_timestamp:
            Start timestamp for the chart data.
        to_timestamp:
            End timestamp for the chart data.

        Returns
        -------
        dict[str, Any]
            Chart data returned by the Axiom API.
        """
        self.logger.debug(
            "Fetching pair chart for %s from %d to %d",
            pair_address,
            from_timestamp,
            to_timestamp,
        )
        try:
            return await self._get(
                f"/pair-chart-v2?pairAddress={pair_address}&from={from_timestamp}&to={to_timestamp}"
            )
        except Exception as exc:
            self.logger.error("Error fetching pair chart: %s", exc)
            raise Exception(f"Failed to get pair chart: {exc}") from exc

    # https://api6.axiom.trade/pair-info?pairAddress=7C3MJJhFd5RwvGG9ihx84ScA3wFxGmkwMaL56mB5dSph&v=1779125758400
    async def get_pair_info(self, pair_address: str) -> dict[str, Any]:
        """Fetch on-chain/market information for *pair_address*.

        Parameters
        ----------
        pair_address:
            Blockchain address of the pair to look up.
        Returns
        -------
        dict[str, Any]
            Pair data returned by the Axiom API.
        """
        self.logger.debug("Fetching pair info for %s", pair_address)
        try:
            return await self._get(
                f"/pair-info?pairAddress={pair_address}&v=1779125758400"
            )
        except Exception as exc:
            self.logger.error("Error fetching pair info: %s", exc)
            raise Exception(f"Failed to get pair info: {exc}") from exc

    async def get_dev_tokens(self, dev_address: str) -> dict[str, Any]:
        """Return all tokens associated with *dev_address*.

        Parameters
        ----------
        dev_address:
            Wallet address of the developer.

        Returns
        -------
        dict[str, Any]
            Developer token list returned by the Axiom API.
        """
        self.logger.debug("Fetching developer tokens for %s", dev_address)
        try:
            return await self._get("/dev-tokens-v4", params={"devAddress": dev_address})
        except Exception as exc:
            self.logger.error("Error fetching developer tokens: %s", exc)
            raise Exception(f"Failed to get developer tokens: {exc}") from exc

    async def get_user_portfolio(self) -> dict[str, Any]:
        """## Get User Portfolio

        Retrieve the authenticated user's portfolio information including holdings,
        positions, and balances.

        ### Returns

        - `Dict[str, Any]`: Portfolio information from the API

        ### Raises

        - `ValueError`: If authentication fails
        - `httpx.HTTPStatusError`: If the API request fails
        - `Exception`: For other errors during the request

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")
        client.login()

        # Get portfolio
        portfolio = client.get_user_portfolio()
        print(f"Total value: ${portfolio['totalValue']}")
        print(f"Holdings: {len(portfolio['holdings'])} tokens")

        for holding in portfolio['holdings']:
            print(f"- {holding['symbol']}: {holding['amount']} tokens")
        ```
        """
        self.logger.debug("Fetching my portfolio")
        try:
            payload = {}
            # TODO: The API seems to require a payload for this endpoint, but the docs don't specify what it should contain. The following is based on observed traffic and may need adjustments.
            # payload = {
            #     "walletAddressRaw": "MyAddresss",
            #     "isOtherWallet": False,
            #     "tokenAddressToAmountMap": {
            #         "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": 1982722336,
            #         "9uGU1v6HhKugg93rx1YjNV8CbCxYB7UhrvfKPEdEAVfM": 11801446167,
            #     },
            #     "userSolBalance": 0.007297883,
            #     "v": 1772913021691,
            # }
            return await self._post("/portfolio-fast-active-v2", payload=payload)
        except Exception as exc:
            self.logger.error(f"Error fetching my portfolio: {exc}")
            raise Exception(f"Failed to get portfolio: {exc} ") from exc

    """
    https://api9.axiom.trade/add-tracked-wallet-v2
{
	"alertsOnBubble": true,
	"alertsOnFeed": true,
	"alertsOnToast": true,
	"emoji": "👻",
	"groupId": 1724325,
	"name": "B3qZZEt8syHx8MDspjeAuUzDMLogAFv2kw84cueZKXwX",
	"trackedWalletAddress": "3qS5FQ5VpHJ3FTifVywf4hqkbGtExNvjTFGNtW4kz2bb",
	"v": 1779334817199
}
    
    """

    async def add_tracked_wallet(
        self, wallet_address: str, name: str, group_id: int
    ) -> dict[str, Any]:
        """Add a wallet to the user's tracked wallets list.

        Parameters
        ----------
        wallet_address:
            Blockchain address of the wallet to track.
        name:
            User-friendly name for the tracked wallet.
        group_id:
            ID of the group to which the tracked wallet belongs.
            This is likely used for organizing tracked wallets into groups in the UI.
        Returns
        -------
        dict[str, Any]
            API response confirming the addition of the tracked wallet.
        """
        # group id = 1724325
        self.logger.debug(
            f"Adding tracked wallet {wallet_address} with name '{name}' to group {group_id}"
        )
        try:
            payload = {
                "alertsOnBubble": False,
                "alertsOnFeed": True,
                "alertsOnToast": True,
                "emoji": "👻",  # This could be parameterized if desired
                "groupId": group_id,
                "name": name,
                "trackedWalletAddress": wallet_address,
                "v": 1779334817199,  # This version parameter may need to be updated based on API requirements
            }
            return await self._post("/add-tracked-wallet-v2", payload=payload)
        except Exception as exc:
            self.logger.error(f"Error adding tracked wallet: {exc}")
            raise Exception(f"Failed to add tracked wallet: {exc}") from exc
