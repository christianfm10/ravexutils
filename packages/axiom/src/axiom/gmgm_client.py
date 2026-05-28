import logging
import uuid
from typing import Any

from shared_lib.baseclient.aiohttp_client import BaseAioHttpClient
from axiom.models.models import HoldingData, HoldingResponse
from axiom.urls import GMGNEndpoint


class GMGNClient(BaseAioHttpClient):
    """GMGM Trade REST client.

    Wraps :class:`BaseAioHttpClient` with GMGM-specific authentication:
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
    use_tls_fingerprint:
        Forward TLS-fingerprinting flag to the base class.
    **kwargs:
        Extra keyword arguments forwarded to :class:`BaseAioHttpClient`.
    """

    ENDPOINT = GMGNEndpoint.endpoint

    _DEFAULT_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 OPR/126.0.0.0",
        "Origin": ENDPOINT.origin,
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        # "Authorization": "Bearer <token>",
        "Referer": "https://gmgn.ai/sol/address/8QDuV9VVGz1w5rxdFK5grQryrG9drmWGGvNJ6wThRxuS",
        # "Upgrade": "websocket",
        # "Sec-WebSocket-Version": "13",
        # "Sec-WebSocket-Extensions": "permessage-deflate; client_max_window_bits",
    }
    # BASE_URL: str = "https://gmgn.ai/vas/api/v1"

    def __init__(
        self,
        storage_dir: str | None = None,  # noqa: ARG002 – reserved for future use
        load_cookies: bool = True,
        log_level: int = logging.INFO,
        use_tls_fingerprint: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            base_url=self.endpoint.str_url,
            headers=self._DEFAULT_HEADERS,
            use_tls_fingerprint=use_tls_fingerprint,
            load_cookies=load_cookies,
            **kwargs,
        )

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

        app_version = "20260521-238-9c19614"
        self.params = {
            "device_id": str(uuid.uuid4()),
            "fp_did": uuid.uuid4().hex,
            "client_id": f"gmgn_web_{app_version}",
            "from_app": "gmgn",
            "app_ver": app_version,
            "tz_name": "America/Lima",
            "tz_offset": "-18000",
            "app_lang": "en-US",
            "os": "web",
            "worker": "0",
            # "uuid": uuid.uuid4().hex[:16],
            # "reconnect": "0",
        }

    # ------------------------------------------------------------------
    # Cookie helpers
    # ------------------------------------------------------------------

    async def get_wallet_activity(self, wallet_address: str) -> Any:
        """Example method to demonstrate authenticated API call."""
        url = f"{GMGNEndpoint.vas_path}/wallet_activity/sol"

        payload = {
            "type": "buy",
            **self.params,
            "wallet": wallet_address,
            "limit": 50,
            "cost": 10,
        }

        try:
            return await self._get(url, params=payload)
        except Exception as exc:
            self.logger.error(f"Error getting wallet activity: {exc}")
            raise Exception(f"Failed to get wallet activity: {exc}") from exc

    # https://gmgn.ai/pf/api/v1/wallet/sol/8QDuV9VVGz1w5rxdFK5grQryrG9drmWGGvNJ6wThRxuS/holdings?device_id=b848ecad-59e8-4ecb-aee6-b4cff671dcea&fp_did=b2fd0c271d8ef018ff326dc43c3ad112&client_id=gmgn_web_20260521-238-9c19614&from_app=gmgn&app_ver=20260521-238-9c19614&tz_name=America%2FLima&tz_offset=-18000&app_lang=en-US&os=web&worker=0&limit=50&order_by=last_active_timestamp&direction=desc&hide_airdrop=true&hide_abnormal=false&hide_closed=false&sellout=true&showsmall=true&tx30d=true
    async def get_wallet_holdings(
        self, wallet_address: str, cursor: str | None = None
    ) -> HoldingData:
        """Example method to demonstrate authenticated API call."""
        url = f"{GMGNEndpoint.pf_path}/wallet/sol/{wallet_address}/holdings"
        dict_cursor = {}
        if cursor:
            dict_cursor = {"cursor": cursor}

        payload = {
            **self.params,
            "limit": 50,
            **dict_cursor,
            "order_by": "last_active_timestamp",
            "direction": "desc",
            "hide_airdrop": "true",
            "hide_abnormal": "false",
            "hide_closed": "false",
            "sellout": "true",
            "showsmall": "true",
            # "tx30d": "true",
        }

        try:
            result = HoldingResponse(**await self._get(url, params=payload))
            if not result.message == "success":
                raise Exception(
                    f"Failed to get wallet holdings: {result.reason} {result.code}"
                )
            return result.data

        except Exception as exc:
            self.logger.error(f"Error getting wallet holdings: {exc}")
            raise Exception(f"Failed to get wallet holdings: {exc}") from exc
