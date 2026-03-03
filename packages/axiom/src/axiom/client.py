"""Axiom Trade HTTP client built on top of BaseAioHttpClient.

Provides cookie-based authentication, automatic token refresh, and
convenience methods for the Axiom Trade REST API.
"""

from __future__ import annotations

from http.cookies import SimpleCookie
import logging
from typing import Any, cast

from aiohttp import CookieJar
from shared_lib.baseclient.aiohttp_client import BaseAioHttpClient
from yarl import URL

from axiom.urls import AAllBaseUrls, AxiomTradeApiUrls


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ORIGIN = "https://axiom.trade"
_API_HOST = "api6.axiom.trade"
_DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)
_DEFAULT_HEADERS: dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.5",
    "Content-Type": "application/json",
    "Connection": "keep-alive",
    "Host": _API_HOST,
    "Origin": _ORIGIN,
    "Referer": _ORIGIN + "/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "TE": "trailers",
    "User-Agent": _DEFAULT_USER_AGENT,
}


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class AxiomClient(BaseAioHttpClient):
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

    BASE_URL: str = AAllBaseUrls.BASE_URL_v6
    SESSION_FILE: str = "session.dat"
    _ORIGIN: str = _ORIGIN

    def __init__(
        self,
        auth_token: str | None = None,
        refresh_token: str | None = None,
        storage_dir: str | None = None,  # noqa: ARG002 – reserved for future use
        load_cookies: bool = True,
        log_level: int = logging.INFO,
        use_tls_finger_print: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            base_url=self.BASE_URL,
            headers=_DEFAULT_HEADERS,
            use_tls_fingerprint=use_tls_finger_print,
            cookie_jar=self._build_cookie_jar(auth_token, refresh_token),
            load_cookies=load_cookies,
            **kwargs,
        )

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

    # ------------------------------------------------------------------
    # Cookie helpers
    # ------------------------------------------------------------------

    def _build_cookie_jar(
        self,
        auth_access_token: str | None,
        auth_refresh_token: str | None,
    ) -> CookieJar:
        """Return a :class:`CookieJar` pre-loaded with Axiom auth cookies.

        Only cookies whose values are not *None* are added.
        """
        jar = CookieJar()
        cookie = SimpleCookie()

        tokens = {
            "auth-access-token": auth_access_token,
            "auth-refresh-token": auth_refresh_token,
        }

        for name, value in tokens.items():
            if value is None:
                continue
            cookie[name] = value
            cookie[name]["domain"] = ".axiom.trade"
            cookie[name]["secure"] = True
            cookie[name]["path"] = "/"

        jar.update_cookies(cookie, response_url=URL(_ORIGIN))
        return jar

    def _filtered_cookies(self) -> dict:
        """Return the cookie dict filtered to the Axiom origin.

        Always reads from ``session.cookie_jar`` so it reflects any cookies
        set by the server during previous requests.
        """
        return self.session.cookie_jar.filter_cookies(self._origin_url)

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def refresh_tokens(self) -> bool:
        """Exchange the stored refresh token for a fresh access/refresh token pair.

        Returns
        -------
        bool
            *True* on success, *False* otherwise.
        """
        if "auth-refresh-token" not in self._filtered_cookies():
            self.logger.error("No refresh token available – cannot refresh")
            return False

        try:
            self.logger.info("Refreshing authentication tokens …")
            response = await super()._fetch("POST", AxiomTradeApiUrls.REFRESH_TOKEN)

            if (
                "auth-access-token" in response.cookies
                and "auth-refresh-token" in response.cookies
            ):
                # Persist the live session jar (which holds cookies updated by
                # the server response), not the jar we built at startup.
                cast(CookieJar, self.session.cookie_jar).save(self.SESSION_FILE)
                self.logger.info("Tokens refreshed successfully")
                return True

            self.logger.error(
                "Token refresh failed – status %s, body: %s",
                response.status,
                await response.text(),
            )
            return False

        except Exception:
            self.logger.exception("Unexpected error during token refresh")
            return False

    async def ensure_authenticated(self) -> bool:
        """Ensure the client holds valid authentication tokens.

        * Both cookies present → returns *True* immediately.
        * Only refresh token present → attempts a silent refresh.
        * No tokens → raises :class:`RuntimeError`.

        Returns
        -------
        bool
            *True* when authenticated.

        Raises
        ------
        RuntimeError
            When the session has fully expired and a new login is required.
        """
        cookies = self._filtered_cookies()
        if "auth-access-token" in cookies:
            return True
        if "auth-refresh-token" not in cookies:
            raise RuntimeError("Session expired. A new login is required.")
        return await self.refresh_tokens()

    # ------------------------------------------------------------------
    # Request layer
    # ------------------------------------------------------------------

    async def _fetch(
        self,
        method: str,
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ):
        """Override :meth:`BaseAioHttpClient._fetch` to enforce authentication.

        Calls :meth:`ensure_authenticated` before delegating to the base
        implementation so every request is transparently authenticated.

        Raises
        ------
        ValueError
            When authentication cannot be established.
        """
        if not await self.ensure_authenticated():
            raise ValueError(
                "Authentication failed. Please provide valid tokens or log in."
            )
        self.logger.debug("Cookies: %s", self._filtered_cookies())
        return await super()._fetch(
            method=method,
            endpoint=endpoint,
            params=params,
            payload=payload,
            headers=headers,
            **kwargs,
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
            return await self._get("/dev-tokens-v3", params={"devAddress": dev_address})
        except Exception as exc:
            self.logger.error("Error fetching developer tokens: %s", exc)
            raise Exception(f"Failed to get developer tokens: {exc}") from exc
