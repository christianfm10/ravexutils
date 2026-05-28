import aiohttp
from aiohttp import TCPConnector
import logging
from abc import abstractmethod
from http.cookies import SimpleCookie
from typing import Any, cast
from .aiohttp_client import BaseAioHttpClient, _FixedCookieJar


class AuthAioHttpClient(BaseAioHttpClient):
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

    SESSION_FILE: str = "session.json"
    refresh_token_name = "auth-refresh-token"
    auth_token_name = "auth-access-token"

    def __init__(
        self,
        auth_token: str | None = None,
        refresh_token: str | None = None,
        load_cookies: bool = True,
        log_level: int = logging.INFO,
        use_tls_fingerprint: bool = True,
        defer_session: bool = False,
        **kwargs: Any,
    ) -> None:
        self.auth_token = auth_token
        self.refresh_token = refresh_token

        super().__init__(
            defer_session=defer_session,
            load_cookies=load_cookies,
            use_tls_fingerprint=use_tls_fingerprint,
            **kwargs,
        )

        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

    # ------------------------------------------------------------------
    # Cookie helpers
    # ------------------------------------------------------------------
    def _create_session(self, connector: TCPConnector | None) -> aiohttp.ClientSession:
        """Instantiate the aiohttp ClientSession with the stored configuration."""
        # Inject cf_clearance once at creation; from then on the jar is authoritative.
        if not self.cookie_jar:
            self.cookie_jar = self._build_cookie_jar(
                self.auth_token, self.refresh_token
            )
        return super()._create_session(connector)

    def _build_cookie_jar(
        self,
        auth_access_token: str | None,
        auth_refresh_token: str | None,
    ) -> _FixedCookieJar:
        """Return a :class:`CookieJar` pre-loaded with Axiom auth cookies.

        Only cookies whose values are not *None* are added.
        """
        jar = _FixedCookieJar()
        cookie = SimpleCookie()

        tokens = {
            # "auth-access-token": auth_access_token,
            self.refresh_token_name: auth_refresh_token,
        }

        for name, value in tokens.items():
            if value is None:
                continue
            cookie[name] = value
            cookie[name]["domain"] = self.endpoint.domain  # ".axiom.trade"
            cookie[name]["secure"] = True
            cookie[name]["path"] = "/"

        jar.update_cookies(cookie, response_url=self.endpoint.root_origin)
        return jar

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    @abstractmethod
    async def refresh_request(self) -> aiohttp.ClientResponse:
        """Make the actual refresh request to the server."""

    async def refresh_tokens(self) -> bool:
        """Exchange the stored refresh token for a fresh access/refresh token pair.

        Returns
        -------
        bool
            *True* on success, *False* otherwise.
        """
        if self.refresh_token_name not in self._filtered_cookies():
            self.logger.error("No refresh token available – cannot refresh")
            return False

        try:
            self.logger.info("Refreshing authentication tokens …")
            response = await self.refresh_request()

            if (
                self.auth_token_name in response.cookies
                and self.refresh_token_name in response.cookies
            ):
                # Persist the live session jar (which holds cookies updated by
                # the server response), not the jar we built at startup.
                self.logger.info("Saving refreshed tokens to %s", self.SESSION_FILE)
                self.save_cookies()
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

        if self.auth_token_name in cookies:
            return True
        if self.refresh_token_name not in cookies:
            self.logger.error("No authentication tokens available. Please log in.")
            return False
        self.logger.warning("Access token expired. Attempting to refresh …")
        return await self.refresh_tokens()

    # ------------------------------------------------------------------
    # Request layer
    # ------------------------------------------------------------------

    async def _fetch_unauthenticated(
        self,
        method: str,
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """Send a request bypassing the authentication guard.

        Use this exclusively for endpoints that do not require a valid access
        token (e.g. login, token refresh). Calling :meth:`_fetch` from inside
        :meth:`refresh_request` would re-enter :meth:`ensure_authenticated`
        and cause an infinite loop.
        """
        return await BaseAioHttpClient._fetch(
            self,
            method,
            endpoint,
            params=params,
            payload=payload,
            headers=headers,
            **kwargs,
        )

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
        RuntimeError
            When authentication cannot be established.
        """
        if not await self.ensure_authenticated():
            raise RuntimeError(
                "Authentication failed. Please provide valid tokens or log in."
            )
        self.logger.debug("Cookies: %s", self._filtered_cookies())
        return await BaseAioHttpClient._fetch(
            self,
            method=method,
            endpoint=endpoint,
            params=params,
            payload=payload,
            headers=headers,
            **kwargs,
        )
