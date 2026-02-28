"""# Axiom Trade Client

Main client interface for interacting with the Axiom Trade platform.
Provides unified access to authentication, REST API endpoints, and WebSocket connections.

## Features

- **Automatic Authentication**: Handles login, token refresh, and secure token storage
- **REST API Access**: Methods for token info, portfolio, and other API endpoints
- **WebSocket Streaming**: Real-time market data through integrated WebSocket client
- **Token Management**: Automatic token refresh and secure encrypted storage
- **Error Handling**: Robust error handling with automatic retry on authentication failures

## Basic Usage

### Initialize with Credentials

```python
from axiomclient import AxiomTradeClient

client = AxiomTradeClient(
    username="user@example.com",
    password="your_password",
    use_saved_tokens=True  # Enable automatic token storage
)

# Login (tokens will be saved automatically)
result = client.login()
if result["success"]:
    print("Login successful!")
```

### Use Saved Tokens

```python
# Initialize without credentials - will load saved tokens
client = AxiomTradeClient(use_saved_tokens=True)

if client.is_authenticated():
    print("Using saved tokens")
else:
    # Need to login
    client.login(email="user@example.com", password="password")
```

### Access REST API

```python
# Get token information
token_info = client.get_token_info("token_address_here")
print(f"Token: {token_info['name']}")

# Get user portfolio
portfolio = client.get_user_portfolio()
print(f"Holdings: {portfolio}")

# Get token by pair address
pair_info = client.get_token_info_by_pair("pair_address_here")
```

### WebSocket Streaming

```python
import asyncio

async def main():
    client = AxiomTradeClient(username="user@example.com", password="password")

    # Connect to WebSocket
    await client.ws.connect()

    # Subscribe to new tokens
    await client.ws.subscribe_new_tokens(
        callback=lambda data: print(f"New token: {data}")
    )

    # Subscribe to token migrations
    await client.ws.subscribe_migrations(
        callback=lambda data: print(f"Migration: {data}")
    )

    # Subscribe to market cap updates
    await client.ws.subscribe_token_mcap(
        tokens=["token1", "token2"],
        callback=lambda data: print(f"Market cap: {data}")
    )

    # Subscribe to Pulse (binary protocol)
    await client.ws.subscribe_pulse(
        callback=lambda data: print(f"Pulse data: {data}")
    )

    # Keep running
    await asyncio.sleep(3600)

    # Clean up
    await client.ws.close()

asyncio.run(main())
```

### Manual Token Management

```python
# Set tokens directly
client.set_tokens(
    access_token="your_access_token",
    refresh_token="your_refresh_token"
)

# Get current tokens
tokens = client.get_tokens()
print(f"Access token: {tokens['access_token']}")
print(f"Expires at: {tokens['expires_at']}")
print(f"Is expired: {tokens['is_expired']}")

# Get detailed token info
info = client.get_token_info_detailed()
print(f"Token valid for: {info['time_until_expiry']} seconds")

# Manual token refresh
if client.refresh_access_token():
    print("Token refreshed successfully")

# Ensure valid authentication (auto-refresh if needed)
if client.ensure_authenticated():
    print("Authentication is valid")
```

### Logout and Clear Data

```python
# Logout and clear all tokens
client.logout()

# Just clear saved tokens from storage
client.clear_saved_tokens()

# Check if saved tokens exist
if client.has_saved_tokens():
    print("Saved tokens available")
```

## Error Handling

All API methods automatically ensure authentication before making requests:

```python
try:
    token_info = client.get_token_info("token_address")
except ValueError as e:
    # Authentication failed
    print(f"Auth error: {e}")
except Exception as e:
    # API request failed
    print(f"API error: {e}")
```

## Configuration

### Custom Storage Directory

```python
client = AxiomTradeClient(
    username="user@example.com",
    password="password",
    storage_dir="/custom/path/to/tokens",
    use_saved_tokens=True
)
```

### Disable Token Storage

```python
client = AxiomTradeClient(
    username="user@example.com",
    password="password",
    use_saved_tokens=False  # Tokens won't be saved
)
```

### Custom Logging Level

```python
import logging

client = AxiomTradeClient(
    username="user@example.com",
    password="password",
    log_level=logging.DEBUG  # Enable debug logging
)
```

## Properties

- `access_token`: Current access token (read-only)
- `refresh_token`: Current refresh token (read-only)
- `ws`: WebSocket client instance
- `auth_manager`: Authentication manager instance
- `auth`: Alias for auth_manager (backward compatibility)

## Thread Safety

The client is not thread-safe. Create separate instances for multi-threaded applications.
For async operations, use the WebSocket client methods with proper asyncio handling.
"""

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Dict, Optional

from aiohttp import CookieJar
from shared_lib.baseclient.aiohttp_client import BaseAioHttpClient
from yarl import URL

# API endpoint constants
API = "api3.axiom.trade"
API_BASE_URL_V6 = f"https://{API}"
API_BASE_URL_V10 = f"https://{API}"

# HTTP headers for API requests
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)
# DEFAULT_HEADERS = (
#     "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
# )
ORIGIN = "https://axiom.trade"
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.5",
    "Content-Type": "application/json",
    "Connection": "keep-alive",
    "Host": API,
    "Origin": ORIGIN,
    "Referer": ORIGIN + "/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-site",
    "TE": "trailers",
    "User-Agent": DEFAULT_USER_AGENT,
}


class AxiomClient(BaseAioHttpClient):
    """# Axiom Trade Client

    Main client for interacting with Axiom Trade API and WebSocket streams.
    Provides unified access to authentication, REST endpoints, and real-time data.

    ## Attributes

    - `auth_manager` (AuthManager): Handles authentication and token management
    - `auth` (AuthManager): Alias for auth_manager (backward compatibility)
    - `ws` (AxiomWebSocketClient): WebSocket client for real-time data streams
    - `logger` (logging.Logger): Logger instance for this client
    - `base_headers` (Dict[str, str]): Default HTTP headers for API requests

    ## Properties

    - `access_token`: Current access token (None if not authenticated)
    - `refresh_token`: Current refresh token (None if not authenticated)

    ## Authentication Flow

    1. Initialize with credentials or saved tokens
    2. Call `login()` or let methods auto-authenticate via `ensure_authenticated()`
    3. Tokens are automatically refreshed when needed
    4. Tokens can be saved securely to disk for future use

    ## Example

    ```python
    # Basic usage
    client = AxiomTradeClient(
        username="user@example.com",
        password="password",
        use_saved_tokens=True
    )

    # Login
    result = client.login()

    # Access REST API
    portfolio = client.get_user_portfolio()

    # Use WebSocket
    await client.ws.connect()
    await client.ws.subscribe_new_tokens(callback=handler)
    ```
    """

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        storage_dir: Optional[str] = None,
        load_cookies: bool = True,
        log_level: int = logging.INFO,
        use_tls_finger_print: bool = True,
        **kwargs: Any,
    ) -> None:
        """## Initialize Axiom Trade Client

        Creates a new client instance with authentication management and WebSocket support.

        ### Parameters

        - `username` (Optional[str]): Email address for automatic login. If provided with
          password, enables automatic authentication. Can be omitted if using saved tokens
          or setting tokens manually.

        - `password` (Optional[str]): Password for automatic login. Required if username
          is provided for authentication.

        - `auth_token` (Optional[str]): Existing access token to use instead of logging in.
          Useful when tokens are managed externally. Should be provided with refresh_token.

        - `refresh_token` (Optional[str]): Existing refresh token for automatic token renewal.
          Should be provided with auth_token.

        - `storage_dir` (Optional[str]): Custom directory for storing encrypted tokens.
          Defaults to `~/.axiom_tokens/` if not specified. Tokens are encrypted using
          Fernet encryption for security.

        - `use_saved_tokens` (bool): Enable automatic loading and saving of tokens to disk.
          When True, tokens are loaded from storage on initialization and saved after
          successful authentication. Defaults to True.

        - `log_level` (int): Logging level for the client and WebSocket client.
          Defaults to logging.INFO. Use logging.DEBUG for verbose output.

        ### Raises

        - `ValueError`: If invalid parameters are provided (e.g., username without password)

        ### Example

        ```python
        # With credentials (will auto-login)
        client = AxiomTradeClient(
            username="user@example.com",
            password="password"
        )

        # With saved tokens
        client = AxiomTradeClient(use_saved_tokens=True)

        # With manual tokens
        client = AxiomTradeClient(
            auth_token="access_token_here",
            refresh_token="refresh_token_here",
            use_saved_tokens=False
        )

        # With custom storage and logging
        client = AxiomTradeClient(
            username="user@example.com",
            password="password",
            storage_dir="/custom/path",
            log_level=logging.DEBUG
        )
        ```
        """
        # Initialize base HTTP client
        cookie_jar = self._build_cookie_jar(auth_token, refresh_token)
        super().__init__(
            base_url=API_BASE_URL_V6,
            headers=DEFAULT_HEADERS,
            use_tls_fingerprint=use_tls_finger_print,
            cookie_jar=cookie_jar,
            load_cookies=load_cookies,
            **kwargs,
        )
        # for cookie in cookies:
        for cookie in self.session.cookie_jar:
            print(cookie)
            print(cookie["domain"])
        print(self.session.cookie_jar.filter_cookies(URL("https://axiom.trade/")))

        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

        # Default headers for API requests
        self.base_headers = DEFAULT_HEADERS.copy()

    def _build_cookie_jar(
        self, auth_access_token: Optional[str], auth_refresh_token: Optional[str]
    ):
        jar = CookieJar()
        from http.cookies import SimpleCookie

        cookie = SimpleCookie()

        tokens = {
            # "auth-access-token": auth_access_token,
            "auth-refresh-token": auth_refresh_token,
        }
        gmt_now = datetime.now(timezone.utc) + timedelta(
            days=1
        )  # Set expiration far in the future
        expires_date = gmt_now.strftime("%a, %d-%b-%y %H:%M:%S GMT")
        # print(f"Current GMT time: {gmt_now}")

        for name, value in tokens.items():
            cookie[name] = value or ""
            cookie[name]["domain"] = ".axiom.trade"
            cookie[name]["secure"] = True
            # cookie[name]["expires"] = str(expires_date)  # 24-Feb-26 13:47:44 GMT
            cookie[name]["path"] = "/"

        jar.update_cookies(cookie, response_url=URL(ORIGIN))

        return jar

    async def refresh_tokens(self):
        """## Async Token Refresh

        Asynchronous version of token refresh method. Useful for refreshing tokens in
        async contexts without blocking the event loop.

        ### Returns

        - `bool`: True if refresh was successful, False otherwise

        """
        cookies = self.session.cookie_jar.filter_cookies(URL(ORIGIN))
        if "auth-refresh-token" not in cookies:
            self.logger.error("No refresh token available for token refresh")
            return False

        try:
            self.logger.info("Refreshing authentication tokens...")

            # await self.auth_manager.cookie_manager.load()
            # API endpoint for token refresh
            endpoint = "/refresh-access-token"
            response = await super()._fetch(
                "POST",
                endpoint,
            )
            # await self.auth_manager.cookie_manager.save(cookies=self.session.cookie_jar)

            if (
                "auth-access-token" in response.cookies
                and "auth-refresh-token" in response.cookies
            ):
                self.session.cookie_jar.save("session2.dat")

                # if self.auth_manager.process_refresh_response({}, response.cookies):
                self.logger.info("✅ Tokens refreshed successfully")
                return True
            else:
                self.logger.error(
                    f"❌ Token refresh failed - Status: {response.status}, "
                    f"Response: {await response.text()}"
                )
                return False

        except Exception as e:
            self.logger.error(f"❌ Token refresh unexpected error: {e}", exc_info=True)
            return False

    async def ensure_authenticated(self) -> bool:
        """## Ensure Valid Authentication

        Ensure the client has valid authentication tokens. Automatically refreshes
        expired tokens or re-authenticates if refresh fails.

        This method is called automatically by API methods before making requests.

        ### Returns

        - `bool`: True if valid authentication is available, False otherwise

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")

        # Ensure authentication before making requests
        if client.ensure_authenticated():
            # Safe to use API
            portfolio = client.get_user_portfolio()
        else:
            print("Authentication failed")

        # API methods call this automatically
        token_info = client.get_token_info("token_address")  # Auto-authenticates
        ```
        """
        # if self.session.cookie_jar.c
        cookies = self.session.cookie_jar.filter_cookies(URL(ORIGIN))
        if "auth-access-token" in cookies and "auth-refresh-token" in cookies:
            return True
        if "auth-refresh-token" not in cookies:
            raise Exception("Sesión expirada. Requiere login.")

        if await self.refresh_tokens():
            self.logger.info("Tokens refreshed successfully")
            return True
        return False

    async def _fetch(
        self,
        method: str,
        endpoint: str = "",
        params: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ):
        """Override _fetch to add authentication headers automatically."""
        # Ensure valid authentication
        if not await self.ensure_authenticated():
            raise ValueError(
                "Authentication failed. Please login first or check your credentials."
            )

        # await self.save()
        # Get authenticated headers and merge with any provided headers
        # auth_headers = self.auth_manager.get_authenticated_headers(headers or {})

        # Call parent _fetch with authenticated headers
        print("Cookies :", self.session.cookie_jar.filter_cookies(URL(ORIGIN)))
        return await super()._fetch(
            method=method,
            endpoint=endpoint,
            params=params,
            payload=payload,
            headers=headers,
            **kwargs,
        )

    async def get_token_info(self, token_address: str) -> Dict[str, Any]:
        """## Get Token Information

        Retrieve detailed information about a specific token by its address.

        ### Parameters

        - `token_address` (str): The blockchain address of the token

        ### Returns

        - `Dict[str, Any]`: Token information from the API

        ### Raises

        - `ValueError`: If authentication fails
        - `httpx.HTTPStatusError`: If the API request fails
        - `Exception`: For other errors during the request

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")
        await client.login()

        # Get token info by address
        token_info = await client.get_token_info("0x1234567890abcdef...")
        print(f"Token name: {token_info['name']}")
        print(f"Token symbol: {token_info['symbol']}")
        print(f"Market cap: {token_info['marketCap']}")
        ```
        """
        self.logger.debug("Getting token info for %s", token_address)

        try:
            return await self._get(f"/token/{token_address}")
        except Exception as e:
            self.logger.error("Error getting token info: %s", e)
            raise Exception(f"Failed to get token info: {e}") from e

    async def get_dev_tokens(self, dev_address: str) -> dict[str, Any]:
        self.logger.debug("Getting developer tokens for %s", dev_address)
        try:
            params = {"devAddress": dev_address}
            return await self._get("/dev-tokens-v3", params=params)
        except Exception as e:
            self.logger.error("Error getting token info: %s", e)
            raise Exception(f"Failed to get token info: {e}") from e
