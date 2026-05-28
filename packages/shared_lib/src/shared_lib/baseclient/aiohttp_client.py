"""
Base HTTP client for building API clients using aiohttp.

This module provides an abstract base class for creating async HTTP clients
using aiohttp. It includes support for proxies, custom headers, cookies, and
Cloudflare clearance handling.
"""

import json
import pathlib
import heapq
from abc import ABC
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, ClassVar, cast
import logging

import aiohttp
from aiohttp import ClientTimeout, CookieJar, TCPConnector

from .endpoint import Endpoint
from .exceptions import HTTPError, ProxyError, ConfigurationError
from .tls import create_tls_context


class _FixedCookieJar(CookieJar):
    """Persistent CookieJar with JSON-based save/load.

    The default aiohttp CookieJar.save() uses pickle (arbitrary code execution
    risk on load) and only persists _cookies, losing expiration state. This
    subclass:
    - Uses JSON instead of pickle (safe against tampered session files)
    - Also persists _expirations so expired cookies are purged after reload

    Note: existing session files saved with pickle are not compatible and must
    be deleted before using this version.
    """

    def save(self, file_path: Any) -> None:
        file_path = pathlib.Path(file_path)
        data = {
            # Stored as a list so tuple keys serialise cleanly as JSON arrays.
            "cookies": [
                {
                    "key": list(key) if isinstance(key, tuple) else [key],
                    "entries": {
                        name: {
                            "value": morsel.value,
                            "expires": morsel["expires"],
                            "path": morsel["path"],
                            "comment": morsel["comment"],
                            "domain": morsel["domain"],
                            "max-age": morsel["max-age"],
                            "secure": bool(morsel["secure"]),
                            "httponly": bool(morsel["httponly"]),
                            "version": morsel["version"],
                            "samesite": morsel["samesite"],
                        }
                        for name, morsel in sc.items()
                    },
                }
                for key, sc in self._cookies.items()
            ],
            "expirations": [
                {"key": list(key), "when": when}
                for key, when in self._expirations.items()
            ],
        }
        with file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f)

    def load(self, file_path: Any) -> None:
        file_path = pathlib.Path(file_path)
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        self._cookies.clear()
        for entry in data.get("cookies", []):
            raw_key = entry["key"]
            # Reconstruct the original key type: tuple for multi-part keys
            # (newer aiohttp), plain string for single-part (older aiohttp).
            key: tuple | str = tuple(raw_key) if len(raw_key) > 1 else raw_key[0]
            sc = SimpleCookie()
            for name, attrs in entry["entries"].items():
                sc[name] = attrs.get("value", "")
                for attr, val in attrs.items():
                    if attr != "value" and val:
                        sc[name][attr] = val
            self._cookies[key] = sc  # type: ignore[assignment]

        self._expirations = {  # type: ignore[assignment]
            tuple(entry["key"]): entry["when"] for entry in data.get("expirations", [])
        }
        self._expire_heap = [  # type: ignore[assignment]
            (entry["when"], tuple(entry["key"]))
            for entry in data.get("expirations", [])
        ]
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

    # Set ENDPOINT on a subclass to auto-populate BASE_URL and _ORIGIN.
    # Example:
    #   class MyClient(BaseAioHttpClient):
    #       ENDPOINT = Endpoint.from_url("https://api.example.com")
    ENDPOINT: ClassVar[Endpoint]

    base_url: str = "https://api.example.com"
    origin: str = "https://api.example.com"
    host: str | None = "api.example.com"
    domain: str | None = "example.com"
    SESSIONS_DIR: Path = Path("sessions")
    SESSION_FILE: str = "session.json"
    DEFAULT_PROFILE: str = "default"
    session_path: Path = SESSIONS_DIR / "BaseAioHttpClient" / SESSION_FILE

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Auto-populate BASE_URL and _ORIGIN when ENDPOINT is set."""
        super().__init_subclass__(**kwargs)
        if cls.__name__ != "AuthAioHttpClient" and (not hasattr(cls, "ENDPOINT")):
            raise ConfigurationError(
                "Subclasses of BaseAioHttpClient must define an ENDPOINT class variable of type Endpoint. Example:\n\n"
                "    class MyClient(BaseAioHttpClient):\n"
                "        ENDPOINT = Endpoint.from_url('https://api.example.com')\n"
            )
            # print("ENDPOINT found in subclass:", cls.ENDPOINT)

        # if "ENDPOINT" not in cls.__dict__:

        cls.endpoint: Endpoint = cast(Endpoint, cls.__dict__.get("ENDPOINT", ""))

    def __init__(
        self,
        base_url: str | None = None,
        proxy: str | None = None,
        cf_clearance: str | None = None,
        session_path: str | Path | None = None,
        profile: str | None = None,
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
            profile: Profile name used to differentiate session files.
                     The session file will be named ``session_{profile}.json``
                     (derived from SESSION_FILE's stem). Defaults to
                     ``DEFAULT_PROFILE`` (``"default"``). Ignored when
                     ``session_path`` is provided explicitly.
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
        self.base_url = base_url or self.endpoint.str_url
        self._use_tls_fingerprint = use_tls_fingerprint
        self._ecdh_curve = ecdh_curve
        self._cipher_suite = cipher_suite
        self._load_cookies = load_cookies
        self.profile: str = profile if profile is not None else self.DEFAULT_PROFILE
        if session_path is not None:
            self.session_path = Path(session_path)
        else:
            _stem = Path(self.SESSION_FILE).stem
            _suffix = Path(self.SESSION_FILE).suffix
            _filename = f"{_stem}_{self.profile}{_suffix}"
            self.session_path = (
                Path(self.SESSIONS_DIR) / self.__class__.__name__ / _filename
            )

        # Store user-provided cookie_jar; actual loading happens in _load_cookie_jar()
        # cf_clearance (if any) is injected into the jar at session creation time.
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

        logger.info("Deferred session initialization: %s", defer_session)
        if not defer_session:
            if load_cookies:
                self.cookie_jar = self._load_cookie_jar()
            self.session = self._create_session(self._build_connector())
            logger.info("AioHttp client initialized with base URL: %s", self.base_url)

    # ------------------------------------------------------------------
    # Private session-building helpers (sync — no async resources needed)
    # ------------------------------------------------------------------

    def _filtered_cookies(self) -> dict:
        """Return the cookie dict filtered to the origin.

        Always reads from ``session.cookie_jar`` so it reflects any cookies
        set by the server during previous requests.
        """
        return self.session.cookie_jar.filter_cookies(self.endpoint.root_origin)

    def _load_cookie_jar(self) -> _FixedCookieJar:
        """Load cookies from SESSION_FILE into a fresh jar."""
        if not self.session_path.exists():
            raise ConfigurationError(
                f"Session file not found: '{self.session_path}'. "
                "Create it first (or run save_cookies()) with content like:\n"
                '{"cookies": [], "expirations": []}'
            )
        jar = _FixedCookieJar()
        jar.load(self.session_path)
        logger.debug("Cookies loaded from %s", self.session_path)
        return jar

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
        # Inject cf_clearance once at creation; from then on the jar is authoritative.
        initial_cookies = {"cf_clearance": self.clearance} if self.clearance else None
        if initial_cookies:
            logger.debug("Cloudflare clearance cookie configured")

        return aiohttp.ClientSession(
            cookies=initial_cookies,
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

    def save_cookies(self, path: Path | None = None) -> None:
        """Persist the current session cookies to disk.

        Args:
            path: Destination file. Defaults to SESSION_FILE.

        Raises:
            RuntimeError: If the session has no cookie jar (defer_session=True
                          and init_session() was never called).
        """
        if self.cookie_jar is None:
            raise RuntimeError("No cookie jar available – session not yet initialized.")
        target = Path(path) if path is not None else self.session_path
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.touch()
        self.cookie_jar.save(target)
        logger.debug("Cookies saved to %s", target)

    async def __aenter__(self):
        """Enable use as async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensure client is closed when exiting context."""
        await self.close()
