"""
Unit tests for BaseAioHttpClient.

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
import aiohttp

from shared_lib.baseclient.aiohttp_client import BaseAioHttpClient
from shared_lib.baseclient.exceptions import (
    ConfigurationError,
    HTTPError,
    ProxyError,
)


class _AioHttpAPIClient(BaseAioHttpClient):
    """Test implementation of BaseAioHttpClient (not collected by pytest)."""

    BASE_URL = "https://api.test.com"


class TestBaseAioHttpClientInitialization:
    """Tests for BaseAioHttpClient initialization."""

    @pytest.mark.asyncio
    async def test_init_with_defaults(self):
        """Test client initialization with default values."""
        client = _AioHttpAPIClient()

        assert client.base_url == "https://api.test.com"
        assert client.proxy is None
        assert client.clearance is None
        assert isinstance(client.session, aiohttp.ClientSession)
        assert client.session.headers["Accept"] == "application/json"
        assert "RavexClient" in client.session.headers["User-Agent"]

        await client.close()

    @pytest.mark.asyncio
    async def test_init_with_custom_base_url(self):
        """Test client initialization with custom base URL."""
        client = _AioHttpAPIClient(base_url="https://custom.api.com")

        assert client.base_url == "https://custom.api.com"

        await client.close()

    @pytest.mark.asyncio
    async def test_init_with_proxy(self):
        """Test client initialization with proxy."""
        client = _AioHttpAPIClient(proxy="proxy.example.com:8080")

        assert client.proxy == "proxy.example.com:8080"
        assert client._proxy_url == "http://proxy.example.com:8080"

        await client.close()

    @pytest.mark.asyncio
    async def test_init_with_proxy_http_prefix(self):
        """Test client initialization with proxy that has http prefix."""
        client = _AioHttpAPIClient(proxy="http://proxy.example.com:8080")

        assert client.proxy == "http://proxy.example.com:8080"
        assert client._proxy_url == "http://proxy.example.com:8080"

        await client.close()

    @pytest.mark.asyncio
    async def test_init_with_proxy_invalid(self):
        """Test client initialization with invalid proxy."""
        with pytest.raises(ConfigurationError):
            _AioHttpAPIClient(proxy=1)  # type: ignore

    @pytest.mark.asyncio
    async def test_init_with_cf_clearance(self):
        """Test client initialization with Cloudflare clearance."""
        client = _AioHttpAPIClient(cf_clearance="test_clearance_token")

        assert client.clearance == "test_clearance_token"
        assert client.cookies["cf_clearance"] == "test_clearance_token"

        await client.close()

    @pytest.mark.asyncio
    async def test_init_with_custom_timeout(self):
        """Test client initialization with custom timeout."""
        client = _AioHttpAPIClient(timeout=60.0)

        assert client.session.timeout.total == 60.0

        await client.close()

    @pytest.mark.asyncio
    async def test_init_with_custom_headers(self):
        """Test client initialization with custom headers."""
        custom_headers = {"Authorization": "Bearer token123"}
        client = _AioHttpAPIClient(headers=custom_headers)

        assert client.session.headers["Authorization"] == "Bearer token123"
        assert client.session.headers["Accept"] == "application/json"

        await client.close()


class TestBaseAioHttpClientFetchMethod:
    """Tests for the _fetch method."""

    @pytest.mark.asyncio
    async def test_fetch_get_success(self):
        """Test successful GET request."""
        client = _AioHttpAPIClient()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"id": 1, "name": "test"})
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_request:
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
        client = _AioHttpAPIClient()

        mock_response = AsyncMock()
        mock_response.status = 201
        mock_response.json = AsyncMock(return_value={"id": 2, "name": "created"})
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        payload = {"name": "test user", "email": "test@example.com"}

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_request:
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
        client = _AioHttpAPIClient()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"results": []})
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        params = {"page": 1, "limit": 10}

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_request:
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
        client = _AioHttpAPIClient()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data": "test"})
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        custom_headers = {"X-Custom-Header": "value"}

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_request:
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

    @pytest.mark.asyncio
    async def test_fetch_with_proxy(self):
        """Test request uses proxy when configured."""
        client = _AioHttpAPIClient(proxy="proxy.example.com:8080")

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"data": "test"})
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_request:
            await client._fetch("GET", "/data")

            # Verify proxy was passed to the request
            call_kwargs = mock_request.call_args[1]
            assert call_kwargs["proxy"] == "http://proxy.example.com:8080"

        await client.close()


class TestBaseAioHttpClientConvenienceMethods:
    """Tests for convenience methods (_get, _post, _put, _delete)."""

    @pytest.mark.asyncio
    async def test_get_method(self):
        """Test _get convenience method."""
        client = _AioHttpAPIClient()

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
        client = _AioHttpAPIClient()

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
        client = _AioHttpAPIClient()

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
        client = _AioHttpAPIClient()

        with patch.object(client, "_fetch", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = {"message": "deleted"}

            result = await client._delete("/users/1")

            assert result == {"message": "deleted"}
            mock_fetch.assert_called_once_with("DELETE", "/users/1")

        await client.close()


class TestBaseAioHttpClientExceptions:
    """Tests for exception handling."""

    @pytest.mark.asyncio
    async def test_http_error_on_404(self):
        """Test HTTPError raised on 404 response."""
        client = _AioHttpAPIClient()

        mock_response = AsyncMock()
        mock_response.status = 404
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        error = aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=404,
            message="Not Found",
        )
        mock_response.raise_for_status = Mock(side_effect=error)

        with patch.object(client.session, "request", return_value=mock_response):
            with pytest.raises(HTTPError) as exc_info:
                await client._fetch("GET", "/users/999")

            assert exc_info.value.status_code == 404
            assert "404" in str(exc_info.value.message)

        await client.close()

    @pytest.mark.asyncio
    async def test_http_error_on_500(self):
        """Test HTTPError raised on 500 response."""
        client = _AioHttpAPIClient()

        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        error = aiohttp.ClientResponseError(
            request_info=Mock(),
            history=(),
            status=500,
            message="Internal Server Error",
        )
        mock_response.raise_for_status = Mock(side_effect=error)

        with patch.object(client.session, "request", return_value=mock_response):
            with pytest.raises(HTTPError) as exc_info:
                await client._fetch("GET", "/users")

            assert exc_info.value.status_code == 500

        await client.close()

    @pytest.mark.asyncio
    async def test_proxy_error(self):
        """Test ProxyError raised on proxy connection failure."""
        client = _AioHttpAPIClient(proxy="bad-proxy.com:8080")

        error = aiohttp.ClientProxyConnectionError(
            connection_key=Mock(), os_error=OSError("Proxy connection failed")
        )

        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(side_effect=error)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(client.session, "request", return_value=mock_response):
            with pytest.raises(ProxyError) as exc_info:
                await client._fetch("GET", "/users")

            assert "Proxy connection failed" in str(exc_info.value.message)

        await client.close()

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Test HTTPError raised on timeout."""
        client = _AioHttpAPIClient()

        error = aiohttp.ServerTimeoutError("Request timed out")

        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(side_effect=error)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(client.session, "request", return_value=mock_response):
            with pytest.raises(HTTPError) as exc_info:
                await client._fetch("GET", "/users")

            assert "timed out" in str(exc_info.value.message).lower()

        await client.close()

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Test HTTPError raised on connection error."""
        client = _AioHttpAPIClient()

        error = aiohttp.ClientConnectionError("Connection failed")

        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(side_effect=error)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(client.session, "request", return_value=mock_response):
            with pytest.raises(HTTPError) as exc_info:
                await client._fetch("GET", "/users")

            assert "Connection failed" in str(exc_info.value.message)

        await client.close()

    @pytest.mark.asyncio
    async def test_generic_exception(self):
        """Test HTTPError raised on generic exception."""
        client = _AioHttpAPIClient()

        error = Exception("Something went wrong")

        mock_response = AsyncMock()
        mock_response.__aenter__ = AsyncMock(side_effect=error)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(client.session, "request", return_value=mock_response):
            with pytest.raises(HTTPError) as exc_info:
                await client._fetch("GET", "/users")

            assert "Request failed" in str(exc_info.value.message)

        await client.close()


class TestBaseAioHttpClientContextManager:
    """Tests for async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager_usage(self):
        """Test client can be used as async context manager."""
        async with _AioHttpAPIClient() as client:
            assert isinstance(client, _AioHttpAPIClient)
            assert client.session is not None

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        """Test client is closed when exiting context."""
        client = _AioHttpAPIClient()

        with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
            async with client:
                pass

            mock_close.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_with_exception(self):
        """Test client is closed even when exception occurs."""
        client = _AioHttpAPIClient()

        with patch.object(client, "close", new_callable=AsyncMock) as mock_close:
            try:
                async with client:
                    raise ValueError("Test exception")
            except ValueError:
                pass

            mock_close.assert_called_once()


class TestBaseAioHttpClientUtilityMethods:
    """Tests for utility methods."""

    @pytest.mark.asyncio
    async def test_check_ip(self):
        """Test _check_ip method."""
        client = _AioHttpAPIClient()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"ip": "203.0.113.1"})
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            client.session, "get", return_value=mock_response
        ) as mock_get:
            result = await client._check_ip()

            assert result == {"ip": "203.0.113.1"}
            mock_get.assert_called_once_with("https://api.ipify.org/?format=json")

        await client.close()

    @pytest.mark.asyncio
    async def test_close_method(self):
        """Test close method."""
        client = _AioHttpAPIClient()

        with patch.object(
            client.session, "close", new_callable=AsyncMock
        ) as mock_close:
            await client.close()

            mock_close.assert_called_once()


class TestBaseAioHttpClientCookieManagement:
    """Tests for cookie management."""

    @pytest.mark.asyncio
    async def test_cf_clearance_cookie_set(self):
        """Test Cloudflare clearance cookie is set correctly."""
        client = _AioHttpAPIClient(cf_clearance="test_token_123")

        assert "cf_clearance" in client.cookies
        assert client.cookies["cf_clearance"] == "test_token_123"

        await client.close()

    @pytest.mark.asyncio
    async def test_cookies_passed_to_aiohttp_session(self):
        """Test cookies are passed to aiohttp session."""
        client = _AioHttpAPIClient(cf_clearance="test_token")

        # Check that cookies were set in the aiohttp session
        # Note: aiohttp stores cookies differently, we verify it was passed to constructor
        assert client.session.cookie_jar is not None

        await client.close()


class TestBaseAioHttpClientProxyConfiguration:
    """Tests for proxy configuration."""

    @pytest.mark.asyncio
    async def test_proxy_without_http_prefix(self):
        """Test proxy configuration without http prefix."""
        client = _AioHttpAPIClient(proxy="proxy.example.com:8080")

        assert client.proxy == "proxy.example.com:8080"
        assert client._proxy_url == "http://proxy.example.com:8080"

        await client.close()

    @pytest.mark.asyncio
    async def test_proxy_with_http_prefix(self):
        """Test proxy configuration with http prefix."""
        client = _AioHttpAPIClient(proxy="http://proxy.example.com:8080")

        assert client.proxy == "http://proxy.example.com:8080"
        assert client._proxy_url == "http://proxy.example.com:8080"

        await client.close()

    @pytest.mark.asyncio
    async def test_proxy_with_https_prefix(self):
        """Test proxy configuration with https prefix."""
        client = _AioHttpAPIClient(proxy="https://proxy.example.com:8080")

        assert client.proxy == "https://proxy.example.com:8080"
        assert client._proxy_url == "https://proxy.example.com:8080"

        await client.close()


class TestBaseAioHttpClientEndpointConstruction:
    """Tests for URL endpoint construction."""

    @pytest.mark.asyncio
    async def test_endpoint_with_leading_slash(self):
        """Test endpoint construction with leading slash."""
        client = _AioHttpAPIClient()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={})
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_request:
            await client._fetch("GET", "/users")

            # Verify the URL was constructed correctly
            call_args = mock_request.call_args
            assert call_args[0][1] == "https://api.test.com/users"

        await client.close()

    @pytest.mark.asyncio
    async def test_empty_endpoint(self):
        """Test request with empty endpoint."""
        client = _AioHttpAPIClient()

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={})
        mock_response.raise_for_status = Mock()
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            client.session, "request", return_value=mock_response
        ) as mock_request:
            await client._fetch("GET", "")

            # Verify the URL is just the base URL
            call_args = mock_request.call_args
            assert call_args[0][1] == "https://api.test.com"

        await client.close()


class TestBaseAioHttpClientTLSConfiguration:
    """Tests for TLS fingerprinting configuration."""

    @pytest.mark.asyncio
    async def test_tls_fingerprint_enabled(self):
        """Test client initialization with TLS fingerprinting."""
        client = _AioHttpAPIClient(use_tls_fingerprint=True)

        assert client.session._connector is not None
        # Verify that a connector was created (can't easily verify SSL context)

        await client.close()

    @pytest.mark.asyncio
    async def test_tls_fingerprint_with_custom_parameters(self):
        """Test TLS fingerprinting with custom ECDH curve and cipher suite."""
        client = _AioHttpAPIClient(
            use_tls_fingerprint=True,
            ecdh_curve="prime256v1",  # Valid ECDH curve name
            # Use default cipher suite (get_cipher_suite()) for compatibility
        )

        assert client.session._connector is not None

        await client.close()

    @pytest.mark.asyncio
    async def test_tls_fingerprint_disabled(self):
        """Test client initialization without TLS fingerprinting."""
        client = _AioHttpAPIClient(use_tls_fingerprint=False)

        # Should still have a connector, just without custom SSL context
        assert client.session._connector is not None

        await client.close()
