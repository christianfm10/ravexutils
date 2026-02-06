"""
Base HTTP client for building API clients.

This module provides an abstract base class for creating async HTTP clients
using httpx. It includes support for proxies, custom headers, cookies, and
Cloudflare clearance handling.
"""

from abc import ABC
from typing import Any
import logging

import httpx

from .exceptions import HTTPError, ProxyError, ConfigurationError


logger = logging.getLogger(__name__)


class BaseClient(ABC):
    """
    Abstract base class for building HTTP API clients.

    This class provides a foundation for creating async HTTP clients with
    built-in support for:
    - Proxy configuration
    - Cookie management (including Cloudflare clearance)
    - Custom headers
    - Automatic JSON response parsing
    - Proper resource cleanup

    Attributes:
        BASE_URL (str): Default base URL for API requests. Should be overridden
                       by subclasses or via constructor.
        client (httpx.AsyncClient): The underlying httpx async client.

    Example:
        >>> class MyAPIClient(BaseClient):
        ...     BASE_URL = "https://api.example.com"
        ...
        ...     async def get_user(self, user_id: int):
        ...         return await self._fetch("GET", f"/users/{user_id}")
        ...
        >>> async with MyAPIClient(proxy="proxy.example.com:8080") as client:
        ...     user = await client.get_user(123)
    """

    BASE_URL: str = "https://api.example.com"

    def __init__(
        self,
        base_url: str | None = None,
        proxy: str | None = None,
        cf_clearance: str | None = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ):
        """
        Initialize the base client.

        Args:
            base_url: Custom base URL to override the class BASE_URL attribute.
            proxy: Proxy URL in format "host:port" or "http://host:port".
            cf_clearance: Cloudflare clearance cookie value for bypassing
                         Cloudflare protection.
            timeout: Request timeout in seconds. Defaults to 30.0.
            **kwargs: Additional arguments passed to httpx.AsyncClient.
                     Common options include:
                     - headers: Custom headers dict
                     - cookies: Additional cookies dict
                     - verify: SSL verification (bool or path to cert)
                     - follow_redirects: Whether to follow redirects (bool)

        Raises:
            ConfigurationError: If proxy format is invalid.
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

        # Configure proxy if provided
        if self.proxy is not None:
            try:
                # Handle proxy format
                proxy_url = (
                    self.proxy
                    if self.proxy.startswith("http")
                    else f"http://{self.proxy}"
                )
                kwargs["proxy"] = proxy_url
                logger.debug(f"Proxy configured: {proxy_url}")
            except Exception as e:
                raise ConfigurationError(f"Invalid proxy configuration: {e}") from e

        # Set default timeout
        if "timeout" not in kwargs:
            kwargs["timeout"] = timeout

        # Initialize httpx client
        self.client = httpx.AsyncClient(cookies=self.cookies, **kwargs)

        # Set default headers
        default_headers = {
            "Accept": "application/json",
            "User-Agent": "RavexClient/0.1.0",
        }
        self.client.headers.update(default_headers)

        logger.info(f"Client initialized with base URL: {self.base_url}")

    async def _fetch(
        self,
        method: str,
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
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
            **kwargs: Additional arguments passed to httpx request method.

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

        try:
            logger.debug(f"{method} {url}")
            response = await self.client.request(
                method,
                url,
                params=params,
                json=payload,
                headers=headers,
                **kwargs,
            )
            response.raise_for_status()

            logger.debug(f"Response status: {response.status_code}")
            return response.json()

        except httpx.ProxyError as e:
            logger.error(f"Proxy error: {e}")
            raise ProxyError(f"Proxy connection failed: {e}") from e
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e}")
            raise HTTPError(
                f"Request failed with status {e.response.status_code}",
                status_code=e.response.status_code,
                response_body=e.response.json()
                if hasattr(e.response, "json")
                else None,
            ) from e
        except httpx.TimeoutException as e:
            logger.error(f"Request timeout: {e}")
            raise HTTPError(f"Request timed out: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise HTTPError(f"Request failed: {e}") from e

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
        return await self._fetch("GET", endpoint, params=params, **kwargs)

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
        return await self._fetch("POST", endpoint, payload=payload, **kwargs)

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
        return await self._fetch("PUT", endpoint, payload=payload, **kwargs)

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
        return await self._fetch("DELETE", endpoint, **kwargs)

    async def _check_ip(self) -> dict[str, str]:
        """
        Check the current IP address being used for requests.

        This is useful for verifying proxy configuration.

        Returns:
            Dictionary with 'ip' key containing the current IP address.

        Note:
            This method is intended for testing and debugging purposes.
        """
        response = await self.client.get("https://api.ipify.org/?format=json")
        response.raise_for_status()
        return response.json()

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
        await self.client.aclose()
        logger.info("Client closed")

    async def __aenter__(self):
        """Enable use as async context manager."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Ensure client is closed when exiting context."""
        await self.close()
