"""
Base HTTP client for building API clients using aiohttp.

This module provides an abstract base class for creating async HTTP clients
using aiohttp. It includes support for proxies, custom headers, cookies, and
Cloudflare clearance handling.
"""

from abc import ABC
from pathlib import Path
from typing import Any
import logging

import aiohttp
from aiohttp import ClientTimeout, CookieJar, TCPConnector
from yarl import URL

from .exceptions import HTTPError, ProxyError, ConfigurationError
from .tls import create_tls_context


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
            **kwargs: Additional arguments passed to aiohttp.ClientSession.
                     Common options include:
                     - headers: Custom headers dict
                     - cookies: Additional cookies dict
                     - connector: Custom TCPConnector instance
                     - trust_env: Trust environment variables for proxy config

        Raises:
            ConfigurationError: If proxy or configuration is invalid.
        """
        # Store configuration
        self.proxy = proxy
        self.clearance = cf_clearance
        self.base_url = base_url or self.BASE_URL

        # Initialize cookies
        self.cookies: dict[str, str] = {}
        if self.clearance is not None:
            self.cookies["cf_clearance"] = self.clearance
            logger.debug("Cloudflare clearance cookie configured")

        # Load Cookies
        cookie_jar: CookieJar | None = kwargs.pop("cookie_jar", None)
        if load_cookies:
            session_path = Path(self.SESSION_FILE)
            if session_path.exists():
                cookie_jar = CookieJar()
                cookie_jar.load(session_path)
                logger.debug("Cookies loaded from %s", session_path)
            else:
                if cookie_jar and "auth-refresh-token" in cookie_jar.filter_cookies(
                    self._origin_url
                ):
                    logger.warning(
                        "Session file %s not found – starting with empty jar, trying using cookies from provided cookie_jar",
                        session_path,
                    )
                else:
                    raise ConfigurationError(
                        f"Session file {session_path} not found for loading cookies"
                    )
        # Configure proxy if provided
        proxy_url = None
        if self.proxy is not None:
            try:
                # Handle proxy format
                proxy_url = (
                    self.proxy
                    if self.proxy.startswith("http")
                    else f"http://{self.proxy}"
                )
                logger.debug(f"Proxy configured: {proxy_url}")
            except Exception as e:
                raise ConfigurationError(f"Invalid proxy configuration: {e}") from e

        # Configure timeout
        timeout_config = ClientTimeout(total=timeout)

        # Configure TLS fingerprinting if requested
        connector = kwargs.pop("connector", None)
        if use_tls_fingerprint:
            if connector is None:
                ssl_context = create_tls_context(
                    ecdh_curve=ecdh_curve,
                    cipher_suite=cipher_suite,
                )
                connector = TCPConnector(ssl=ssl_context)
                logger.debug("TLS fingerprinting enabled")
            else:
                logger.warning(
                    "TLS fingerprinting requested but 'connector' already provided in kwargs"
                )
        # elif connector is None:
        #     # Use default connector if none provided
        #     connector = TCPConnector()

        # Set default headers
        default_headers = {
            "Accept": "application/json",
            "User-Agent": "RavexClient/0.1.0",
        }

        # Merge with user-provided headers
        user_headers = kwargs.pop("headers", {})
        headers = {**default_headers, **user_headers}

        # Initialize aiohttp session
        self.session = aiohttp.ClientSession(
            cookies=self.cookies,
            headers=headers,
            timeout=timeout_config,
            connector=connector,
            cookie_jar=cookie_jar,
            **kwargs,
        )

        # Store proxy for use in requests
        self._proxy_url = proxy_url

        logger.info(f"AioHttp client initialized with base URL: {self.base_url}")

    async def fetch(
        self,
        method: str,
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        return await self._fetch(
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
            self.session.headers.update(**{**self.session.headers, **(headers or {})})
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

    async def fetch_json(
        self,
        method: str,
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Public method to perform an HTTP request and return JSON response.

        This method is intended to be used by subclasses as the main way to
        perform API requests. It simply calls _fetch_json internally.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE, PATCH, etc.).
            endpoint: API endpoint path (will be appended to BASE_URL).
            params: Query parameters for the request.
            payload: JSON payload for POST/PUT/PATCH requests.
            headers: Additional headers for this specific request.
            **kwargs: Additional arguments passed to aiohttp request method.

        Returns:
            Parsed JSON response as a dictionary.
        """
        return await self._fetch_json(
            method,
            endpoint,
            params=params,
            payload=payload,
            headers=headers,
            **kwargs,
        )

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
        response = await self.fetch_json("GET", endpoint, params=params, **kwargs)
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
        response = await self.fetch_json("POST", endpoint, payload=payload, **kwargs)
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
        response = await self.fetch_json("PUT", endpoint, payload=payload, **kwargs)
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
        response = await self.fetch_json("DELETE", endpoint, **kwargs)
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
