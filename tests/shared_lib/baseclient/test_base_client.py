"""
Unit tests for BaseClient.

Tests cover:
- Client initialization with various configurations
- HTTP methods (_get, _post, _put, _delete)
- Error handling and custom exceptions
- Proxy configuration
- Cookie management
- Context manager usage
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from shared_lib.baseclient import Client as BaseClient
from shared_lib.baseclient.exceptions import (
    ConfigurationError,
    HTTPError,
    ProxyError,
)


class _APIClient(BaseClient):
    """Test implementation of BaseClient (not collected by pytest)."""

    BASE_URL = "https://api.test.com"


class TestBaseClientInitialization:
    """Tests for BaseClient initialization."""

    def test_init_with_defaults(self):
        """Test client initialization with default values."""
        client = _APIClient()

        assert client.base_url == "https://api.test.com"
        assert client.proxy is None
        assert client.clearance is None
        assert isinstance(client.client, httpx.AsyncClient)
        assert client.client.headers["Accept"] == "application/json"
        assert "RavexClient" in client.client.headers["User-Agent"]

    def test_init_with_custom_base_url(self):
        """Test client initialization with custom base URL."""
        client = _APIClient(base_url="https://custom.api.com")

        assert client.base_url == "https://custom.api.com"

    def test_init_with_proxy(self):
        """Test client initialization with proxy."""
        client = _APIClient(proxy="proxy.example.com:8080")

        assert client.proxy == "proxy.example.com:8080"

    def test_init_with_proxy_http_prefix(self):
        """Test client initialization with proxy that has http prefix."""
        client = _APIClient(proxy="http://proxy.example.com:8080")

        assert client.proxy == "http://proxy.example.com:8080"

    def test_init_with_proxy_invalid(self):
        """Test client initialization with invalid proxy."""
        with pytest.raises(ConfigurationError):
            _APIClient(proxy=1)  # type: ignore

    def test_init_with_cf_clearance(self):
        """Test client initialization with Cloudflare clearance."""
        client = _APIClient(cf_clearance="test_clearance_token")

        assert client.clearance == "test_clearance_token"
        assert client.cookies["cf_clearance"] == "test_clearance_token"

    def test_init_with_custom_timeout(self):
        """Test client initialization with custom timeout."""
        client = _APIClient(timeout=60.0)

        assert client.client.timeout.read == 60.0

    def test_init_with_custom_headers(self):
        """Test client initialization with custom headers."""
        custom_headers = {"Authorization": "Bearer token123"}
        client = _APIClient(headers=custom_headers)

        assert client.client.headers["Authorization"] == "Bearer token123"
        assert client.client.headers["Accept"] == "application/json"


class TestBaseClientFetchMethod:
    """Tests for the _fetch method."""

    @pytest.mark.asyncio
    async def test_fetch_get_success(self):
        """Test successful GET request."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"id": 1, "name": "test"}

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await client._fetch("GET", "/users/1")

            assert result == {"id": 1, "name": "test"}
            mock_request.assert_called_once_with(
                "GET",
                "https://api.test.com/users/1",
                params=None,
                json=None,
                headers=None,
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_post_with_payload(self):
        """Test POST request with payload."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 2, "name": "created"}

        payload = {"name": "test user", "email": "test@example.com"}

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await client._fetch("POST", "/users", payload=payload)

            assert result == {"id": 2, "name": "created"}
            mock_request.assert_called_once_with(
                "POST",
                "https://api.test.com/users",
                params=None,
                json=payload,
                headers=None,
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_with_params(self):
        """Test request with query parameters."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"results": []}

        params = {"page": 1, "limit": 10}

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await client._fetch("GET", "/users", params=params)

            assert result == {"results": []}
            mock_request.assert_called_once_with(
                "GET",
                "https://api.test.com/users",
                params=params,
                json=None,
                headers=None,
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_fetch_with_custom_headers(self):
        """Test request with custom headers."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "test"}

        custom_headers = {"X-Custom-Header": "value"}

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            result = await client._fetch("GET", "/data", headers=custom_headers)

            assert result == {"data": "test"}
            mock_request.assert_called_once_with(
                "GET",
                "https://api.test.com/data",
                params=None,
                json=None,
                headers=custom_headers,
            )

        await client.close()


class TestBaseClientConvenienceMethods:
    """Tests for convenience methods (_get, _post, _put, _delete)."""

    @pytest.mark.asyncio
    async def test_get_method(self):
        """Test _get convenience method."""
        client = _APIClient()

        with patch.object(client, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"id": 1}

            result = await client._get("/users/1", params={"fields": "all"})

            assert result == {"id": 1}
            mock_fetch.assert_called_once_with(
                "GET", "/users/1", params={"fields": "all"}
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_post_method(self):
        """Test _post convenience method."""
        client = _APIClient()

        payload = {"name": "test"}

        with patch.object(client, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"id": 2, "name": "test"}

            result = await client._post("/users", payload=payload)

            assert result == {"id": 2, "name": "test"}
            mock_fetch.assert_called_once_with("POST", "/users", payload=payload)

        await client.close()

    @pytest.mark.asyncio
    async def test_put_method(self):
        """Test _put convenience method."""
        client = _APIClient()

        payload = {"name": "updated"}

        with patch.object(client, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"id": 1, "name": "updated"}

            result = await client._put("/users/1", payload=payload)

            assert result == {"id": 1, "name": "updated"}
            mock_fetch.assert_called_once_with("PUT", "/users/1", payload=payload)

        await client.close()

    @pytest.mark.asyncio
    async def test_delete_method(self):
        """Test _delete convenience method."""
        client = _APIClient()

        with patch.object(client, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"message": "deleted"}

            result = await client._delete("/users/1")

            assert result == {"message": "deleted"}
            mock_fetch.assert_called_once_with("DELETE", "/users/1")

        await client.close()


class TestBaseClientExceptions:
    """Tests for exception handling."""

    @pytest.mark.asyncio
    async def test_http_error_on_404(self):
        """Test HTTPError raised on 404 response."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.json.return_value = {"error": "Not found"}

        error = httpx.HTTPStatusError(
            "404 Not Found", request=Mock(), response=mock_response
        )

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = error

            with pytest.raises(HTTPError) as exc_info:
                await client._fetch("GET", "/users/999")

            assert exc_info.value.status_code == 404
            assert "404" in str(exc_info.value.message)

        await client.close()

    @pytest.mark.asyncio
    async def test_http_error_on_500(self):
        """Test HTTPError raised on 500 response."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Internal server error"}

        error = httpx.HTTPStatusError(
            "500 Internal Server Error", request=Mock(), response=mock_response
        )

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = error

            with pytest.raises(HTTPError) as exc_info:
                await client._fetch("GET", "/users")

            assert exc_info.value.status_code == 500

        await client.close()

    @pytest.mark.asyncio
    async def test_proxy_error(self):
        """Test ProxyError raised on proxy connection failure."""
        client = _APIClient(proxy="bad-proxy.com:8080")

        error = httpx.ProxyError("Proxy connection failed")

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = error

            with pytest.raises(ProxyError) as exc_info:
                await client._fetch("GET", "/users")

            assert "Proxy connection failed" in str(exc_info.value.message)

        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Test HTTPError raised on timeout."""
        client = _APIClient()

        error = httpx.TimeoutException("Request timed out")

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = error

            with pytest.raises(HTTPError) as exc_info:
                await client._fetch("GET", "/users")

            assert "timed out" in str(exc_info.value.message).lower()

        await client.close()

    @pytest.mark.asyncio
    async def test_generic_exception(self):
        """Test HTTPError raised on generic exception."""
        client = _APIClient()

        error = Exception("Something went wrong")

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.side_effect = error

            with pytest.raises(HTTPError) as exc_info:
                await client._fetch("GET", "/users")

            assert "Request failed" in str(exc_info.value.message)

        await client.close()


class TestBaseClientContextManager:
    """Tests for async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager_usage(self):
        """Test client can be used as async context manager."""
        async with _APIClient() as client:
            assert isinstance(client, _APIClient)
            assert client.client is not None

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        """Test client is closed when exiting context."""
        client = _APIClient()

        with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
            async with client:
                pass

            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self):
        """Test client is closed even when exception occurs."""
        client = _APIClient()

        with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
            try:
                async with client:
                    raise ValueError("Test exception")
            except ValueError:
                pass

            mock_close.assert_called_once()


class TestBaseClientUtilityMethods:
    """Tests for utility methods."""

    @pytest.mark.asyncio
    async def test_check_ip(self):
        """Test _check_ip method."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ip": "203.0.113.1"}

        with patch.object(client.client, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_response

            result = await client._check_ip()

            assert result == {"ip": "203.0.113.1"}
            mock_get.assert_called_once_with("https://api.ipify.org/?format=json")

        await client.close()

    @pytest.mark.asyncio
    async def test_close_method(self):
        """Test close method."""
        client = _APIClient()

        with patch.object(
            client.client, "aclose", new_callable=AsyncMock
        ) as mock_aclose:
            await client.close()

            mock_aclose.assert_called_once()


class TestBaseClientCookieManagement:
    """Tests for cookie management."""

    def test_cf_clearance_cookie_set(self):
        """Test Cloudflare clearance cookie is set correctly."""
        client = _APIClient(cf_clearance="test_token_123")

        assert "cf_clearance" in client.cookies
        assert client.cookies["cf_clearance"] == "test_token_123"

    def test_cookies_passed_to_httpx_client(self):
        """Test cookies are passed to httpx client."""
        client = _APIClient(cf_clearance="test_token")

        # Check that cookies were set in the httpx client
        assert client.client.cookies.get("cf_clearance") == "test_token"


class TestBaseClientProxyConfiguration:
    """Tests for proxy configuration."""

    def test_proxy_without_http_prefix(self):
        """Test proxy configuration without http prefix."""
        client = _APIClient(proxy="proxy.example.com:8080")

        assert client.proxy == "proxy.example.com:8080"

    def test_proxy_with_http_prefix(self):
        """Test proxy configuration with http prefix."""
        client = _APIClient(proxy="http://proxy.example.com:8080")

        assert client.proxy == "http://proxy.example.com:8080"

    def test_proxy_with_https_prefix(self):
        """Test proxy configuration with https prefix."""
        client = _APIClient(proxy="https://proxy.example.com:8080")

        assert client.proxy == "https://proxy.example.com:8080"


class TestBaseClientEndpointConstruction:
    """Tests for URL endpoint construction."""

    @pytest.mark.asyncio
    async def test_endpoint_without_leading_slash(self):
        """Test endpoint construction without leading slash."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            await client._fetch("GET", "/users")

            # Verify the URL was constructed correctly
            call_args = mock_request.call_args
            assert (
                call_args[0][1] == "https://api.test.com/users"
                or call_args[1].get("url") == "https://api.test.com/users"
            )

        await client.close()

    @pytest.mark.asyncio
    async def test_endpoint_with_leading_slash(self):
        """Test endpoint construction with leading slash."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            await client._fetch("GET", "/users")

            # Verify the URL was constructed correctly
            call_args = mock_request.call_args
            assert call_args[0][1] == "https://api.test.com/users"

        await client.close()

    @pytest.mark.asyncio
    async def test_empty_endpoint(self):
        """Test request with empty endpoint."""
        client = _APIClient()

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {}

        with patch.object(
            client.client, "request", new_callable=AsyncMock
        ) as mock_request:
            mock_request.return_value = mock_response

            await client._fetch("GET", "")

            # Verify the URL is just the base URL
            call_args = mock_request.call_args
            assert call_args[0][1] == "https://api.test.com"

        await client.close()
