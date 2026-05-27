"""
Base HTTP client for building API clients using aiohttp.

This module provides an abstract base class for creating async HTTP clients
using aiohttp. It includes support for proxies, custom headers, cookies, and
Cloudflare clearance handling.
"""

import pickle
import pathlib
import heapq
from abc import ABC
from pathlib import Path
from typing import Any
import logging

import aiohttp
from aiohttp import ClientTimeout, CookieJar, TCPConnector
from yarl import URL

from .exceptions import HTTPError, ProxyError, ConfigurationError
from .tls import create_tls_context


class _FixedCookieJar(CookieJar):
    """CookieJar with fixed save()/load() that persist the expiration state.

    The default aiohttp CookieJar.save() only pickles self._cookies, leaving
    self._expirations and self._expire_heap empty on load, so expired cookies
    are never removed after loading from disk.

    This subclass also persists _expirations (absolute Unix timestamps) so the
    heap can be fully reconstructed on load — including cookies that originally
    only had max-age (already converted to absolute time by aiohttp).
    """

    def save(self, file_path: Any) -> None:

        file_path = pathlib.Path(file_path)
        with file_path.open(mode="wb") as f:
            pickle.dump(
                (self._cookies, self._expirations),
                f,
                pickle.HIGHEST_PROTOCOL,
            )

    def load(self, file_path: Any) -> None:

        file_path = pathlib.Path(file_path)
        with file_path.open(mode="rb") as f:
            data = pickle.load(f)

        # Support old files that only contain _cookies (plain dict)
        if isinstance(data, tuple):
            self._cookies, self._expirations = data
        else:
            self._cookies = data
            self._expirations = {}

        # Rebuild the heap from the (absolute) expiration timestamps
        self._expire_heap = list((when, key) for key, when in self._expirations.items())
        heapq.heapify(self._expire_heap)


logger = logging.getLogger(__name__)


class BaseAioHttpClient(ABC):
    """
    Abstract base class for building HTTP API clients using aiohttp.

    This class provides a foundation for creating async HTTP clients with
    built-in support for:
    - Proxy configuration
    - Cookie management (including Cloudflare clearance)
    - Custom headers
    - Automatic JSON response parsing
    - Proper resource cleanup
    - TLS fingerprinting

    Attributes:
        BASE_URL (str): Default base URL for API requests. Should be overridden
                       by subclasses or via constructor.
        session (aiohttp.ClientSession): The underlying aiohttp client session.

    Example:
        >>> class MyAPIClient(BaseAioHttpClient):
        ...     BASE_URL = "https://api.example.com"
        ...
        ...     async def get_user(self, user_id: int):
        ...         return await self._fetch("GET", f"/users/{user_id}")
        ...
        >>> async with MyAPIClient(proxy="proxy.example.com:8080") as client:
        ...     user = await client.get_user(123)
    """

    BASE_URL: str = "https://api.example.com"
    _ORIGIN: str = BASE_URL
    SESSION_FILE: str = "session.dat"

    def __init__(
        self,
        base_url: str | None = None,
        proxy: str | None = None,
        cf_clearance: str | None = None,
        timeout: float = 30.0,
        use_tls_fingerprint: bool = False,
        ecdh_curve: str | None = None,
        cipher_suite: str | None = None,
        load_cookies: bool = False,
        defer_session: bool = False,
        **kwargs: Any,
    ):
        """
        Initialize the base aiohttp client.

        Args:
            base_url: Custom base URL to override the class BASE_URL attribute.
            proxy: Proxy URL in format "host:port" or "http://host:port".
            cf_clearance: Cloudflare clearance cookie value for bypassing
                         Cloudflare protection.
            timeout: Request timeout in seconds. Defaults to 30.0.
            use_tls_fingerprint: Enable browser-like TLS fingerprinting.
            ecdh_curve: ECDH curve for TLS. Defaults to "secp384r1".
            cipher_suite: Custom cipher suite. Uses browser-like suite by default.
            load_cookies: Load cookies from SESSION_FILE on session creation.
            defer_session: If True, skip session creation in __init__. Call
                           ``await init_session()`` manually once inside an event
                           loop. Required when instantiating outside an async
                           context (e.g. TCPConnector and CookieJar need a loop).
            **kwargs: Additional arguments passed to aiohttp.ClientSession.
                     Common options include:
                     - headers: Custom headers dict
                     - cookies: Additional cookies dict
                     - connector: Custom TCPConnector instance
                     - trust_env: Trust environment variables for proxy config

        Raises:
            ConfigurationError: If proxy or configuration is invalid.
        """
        self.proxy = proxy
        self.clearance = cf_clearance
        self.base_url = base_url or self.BASE_URL
        self._use_tls_fingerprint = use_tls_fingerprint
        self._ecdh_curve = ecdh_curve
        self._cipher_suite = cipher_suite
        self._load_cookies = load_cookies

        # Initialize cookies
        self.cookies: dict[str, str] = {}
        if self.clearance is not None:
            self.cookies["cf_clearance"] = self.clearance
            logger.debug("Cloudflare clearance cookie configured")

        # Store user-provided cookie_jar; actual loading happens in _load_cookie_jar()
        self.cookie_jar: _FixedCookieJar | None = kwargs.pop("cookie_jar", None)

        # Configure proxy
        self._proxy_url: str | None = None
        if proxy is not None:
            self._proxy_url = proxy if proxy.startswith("http") else f"http://{proxy}"
            logger.debug("Proxy configured: %s", self._proxy_url)

        self.timeout_config = ClientTimeout(total=timeout)

        # Store user-provided connector; actual creation happens in _build_connector()
        self._user_connector: TCPConnector | None = kwargs.pop("connector", None)

        # Merge default headers with user-provided headers
        self.headers = {
            "Accept": "application/json",
            "User-Agent": "RavexClient/0.1.0",
            **kwargs.pop("headers", {}),
        }
        self.kwargs = kwargs

        if not defer_session:
            if load_cookies:
                self.cookie_jar = self._load_cookie_jar()
            self.session = self._create_session(self._build_connector())
            logger.info("AioHttp client initialized with base URL: %s", self.base_url)

    # ------------------------------------------------------------------
    # Private session-building helpers (sync — no async resources needed)
    # ------------------------------------------------------------------

    def _load_cookie_jar(self) -> _FixedCookieJar:
        """Load cookies from SESSION_FILE or fall back to a provided jar."""
        session_path = Path(self.SESSION_FILE)
        if session_path.exists():
            jar = _FixedCookieJar()
            jar.load(session_path)
            logger.debug("Cookies loaded from %s", session_path)
            return jar
        if self.cookie_jar and "auth-refresh-token" in self.cookie_jar.filter_cookies(
            self._origin_url
        ):
            logger.warning(
                "Session file %s not found – using provided cookie_jar", session_path
            )
            return self.cookie_jar
        raise ConfigurationError(
            f"Session file {session_path} not found for loading cookies"
        )

    def _build_connector(self) -> TCPConnector | None:
        """Create a TCPConnector with optional TLS fingerprinting."""
        if self._user_connector is not None:
            if self._use_tls_fingerprint:
                logger.warning(
                    "TLS fingerprinting requested but 'connector' already provided – ignoring"
                )
            return self._user_connector
        if self._use_tls_fingerprint:
            ssl_context = create_tls_context(
                ecdh_curve=self._ecdh_curve,
                cipher_suite=self._cipher_suite,
            )
            logger.debug("TLS fingerprinting enabled")
            return TCPConnector(ssl=ssl_context)
        return None

    def _create_session(self, connector: TCPConnector | None) -> aiohttp.ClientSession:
        """Instantiate the aiohttp ClientSession with the stored configuration."""
        return aiohttp.ClientSession(
            cookies=self.cookies,
            headers=self.headers,
            timeout=self.timeout_config,
            connector=connector,
            cookie_jar=self.cookie_jar,
            **self.kwargs,
        )

    async def init_session(self) -> None:
        """
        Create the aiohttp session inside a running event loop.

        Must be called after ``__init__`` when ``defer_session=True``. This is
        the recommended pattern when the client is instantiated outside an async
        context, because resources such as ``TCPConnector`` and ``_FixedCookieJar``
        require a running event loop.

        Example::

            client = MyAPIClient(defer_session=True)
            # ... later, inside an async context ...
            await client.init_session()
            async with client:
                data = await client.get_data()
        """
        if self._load_cookies:
            self.cookie_jar = self._load_cookie_jar()
        self.session = self._create_session(self._build_connector())
        logger.info("AioHttp session initialized with base URL: %s", self.base_url)

    async def _fetch(
        self,
        method: str,
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        """
        Perform an HTTP request and return JSON response.

        This is the core method for making HTTP requests. It handles URL
        construction, error handling, and JSON parsing.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH, etc.).
            endpoint: API endpoint path (will be appended to BASE_URL).
            params: Query parameters for the request.
            payload: JSON payload for POST/PUT/PATCH requests.
            headers: Additional headers for this specific request.
            **kwargs: Additional arguments passed to aiohttp request method.

        Returns:
            Parsed JSON response as a dictionary.

        Raises:
            HTTPError: If the request fails or returns an error status code.
            ProxyError: If there's a proxy-related connection issue.

        Example:
            >>> await self._fetch("GET", "/users", params={"page": 1})
            >>> await self._fetch("POST", "/users", payload={"name": "John"})
        """
        url = f"{self.base_url}{endpoint}"

        # Add proxy if configured
        if self._proxy_url and "proxy" not in kwargs:
            kwargs["proxy"] = self._proxy_url

        try:
            if headers:
                self.session.headers.update(headers)
            # self.session.headers.update(**{**self.session.headers, **(headers or {})})
            logger.debug(f"{method} {url}")
            async with self.session.request(
                method,
                url,
                params=params,
                json=payload,
                headers=headers,
                **kwargs,
            ) as response:
                # Raise for status codes >= 400
                response.raise_for_status()
                await response.read()

                logger.debug(f"Response status: {response.status}")

                return response

        except aiohttp.ClientProxyConnectionError as e:
            logger.error(f"Proxy error: {e}")
            raise ProxyError(f"Proxy connection failed: {e}") from e
        except aiohttp.ServerTimeoutError as e:
            logger.error(f"Request timeout: {e}")
            raise HTTPError(f"Request timed out: {e}") from e
        except aiohttp.ClientResponseError as e:
            logger.error(f"HTTP error {e.status}: {e}")
            # Try to get response message
            response_body = None
            try:
                if e.message:
                    response_body = {"message": e.message}
            except Exception:
                pass
            raise HTTPError(
                f"Request failed with status {e.status}",
                status_code=e.status,
                response_body=response_body,
            ) from e
        except aiohttp.ClientConnectionError as e:
            logger.error(f"Connection error: {e}")
            raise HTTPError(f"Connection failed: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise HTTPError(f"Request failed: {e}") from e

    async def _fetch_json(
        self,
        method: str,
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Alias for _fetch to emphasize JSON response.

        This method is identical to _fetch and is provided as an alias
        for clarity when the expected response is JSON.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH, etc.).
            endpoint: API endpoint path (will be appended to BASE_URL).
            params: Query parameters for the request.
            payload: JSON payload for POST/PUT/PATCH requests.
            headers: Additional headers for this specific request.
            **kwargs: Additional arguments passed to aiohttp request method.

        Returns:
            Parsed JSON response.
        """
        try:
            result = await self._fetch(
                method,
                endpoint,
                params=params,
                payload=payload,
                headers=headers,
                **kwargs,
            )
            return await result.json()
        except aiohttp.ContentTypeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            raise HTTPError(f"Invalid JSON response: {e}") from e

    async def _get(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Convenience method for GET requests.

        Args:
            endpoint: API endpoint path.
            params: Query parameters.
            **kwargs: Additional arguments for _fetch.

        Returns:
            Parsed JSON response.
        """
        response = await self._fetch_json("GET", endpoint, params=params, **kwargs)
        return response

    async def _post(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Convenience method for POST requests.

        Args:
            endpoint: API endpoint path.
            payload: JSON payload.
            **kwargs: Additional arguments for _fetch.

        Returns:
            Parsed JSON response.
        """
        response = await self._fetch_json("POST", endpoint, payload=payload, **kwargs)
        return response

    async def _put(
        self,
        endpoint: str,
        payload: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Convenience method for PUT requests.

        Args:
            endpoint: API endpoint path.
            payload: JSON payload.
            **kwargs: Additional arguments for _fetch.

        Returns:
            Parsed JSON response.
        """
        response = await self._fetch_json("PUT", endpoint, payload=payload, **kwargs)
        return response

    async def _delete(
        self,
        endpoint: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Convenience method for DELETE requests.

        Args:
            endpoint: API endpoint path.
            **kwargs: Additional arguments for _fetch.

        Returns:
            Parsed JSON response.
        """
        response = await self._fetch_json("DELETE", endpoint, **kwargs)
        return response

    async def _check_ip(self) -> dict[str, str]:
        """
        Check the current IP address being used for requests.

        This is useful for verifying proxy configuration.

        Returns:
            Dictionary with 'ip' key containing the current IP address.

        Note:
            This method is intended for testing and debugging purposes.
        """
        async with self.session.get("https://api.ipify.org/?format=json") as response:
            response.raise_for_status()
            return await response.json()

    async def close(self) -> None:
        """
        Close the HTTP client and release resources.

        This should be called when the client is no longer needed to
        properly clean up connections and resources.

        Example:
            >>> client = MyAPIClient()
            >>> try:
            ...     await client.get_data()
            ... finally:
            ...     await client.close()
        """
        await self.session.close()
        logger.info("AioHttp client closed")

    async def __aenter__(self):
        """Enable use as async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensure client is closed when exiting context."""
        await self.close()

    @property
    def _origin_url(self) -> URL:
        """Cached :class:`~yarl.URL` for the Axiom origin."""
        return URL(self._ORIGIN)
