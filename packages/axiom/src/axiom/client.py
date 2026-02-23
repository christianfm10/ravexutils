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

import logging
from typing import Any, Dict, Optional

# from axiom.websocket._client import AxiomWebSocketClient
from shared_lib.baseclient.aiohttp_client import BaseAioHttpClient
from yarl import URL
from .auth.auth_manager import AuthManager

# API endpoint constants
API_BASE_URL_V6 = "https://api8.axiom.trade"
API_BASE_URL_V10 = "https://api8.axiom.trade"

# HTTP headers for API requests
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)
# DEFAULT_HEADERS = (
#     "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:136.0) Gecko/20100101 Firefox/136.0",
# )
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.5",
    "Content-Type": "application/json",
    "Connection": "keep-alive",
    "Host": "api8.axiom.trade",
    "Origin": "https://axiom.trade",
    "Referer": "https://axiom.trade/",
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
        use_saved_tokens: bool = True,
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
        super().__init__(
            base_url=API_BASE_URL_V6,
            headers=DEFAULT_HEADERS,
            use_tls_fingerprint=use_tls_finger_print,
            **kwargs,
        )

        # Initialize authentication manager
        self.auth_manager = AuthManager(
            username=username,
            password=password,
            auth_token=auth_token,
            refresh_token=refresh_token,
            storage_dir=storage_dir,
            use_saved_tokens=use_saved_tokens,
        )

        # Backward compatibility alias
        self.auth = self.auth_manager
        self.session.cookie_jar.update_cookies(self.auth_manager.get_refresh_cookies())

        # Setup logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(log_level)

        # Default headers for API requests
        self.base_headers = DEFAULT_HEADERS.copy()

    @property
    def access_token(self) -> Optional[str]:
        """## Access Token Property

        Get the current access token used for API authentication.

        ### Returns

        - `Optional[str]`: Current access token, or None if not authenticated

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")
        client.login()

        token = client.access_token
        if token:
            print(f"Authenticated with token: {token[:20]}...")
        ```
        """
        return (
            self.auth_manager.tokens.access_token if self.auth_manager.tokens else None
        )

    @property
    def refresh_token(self) -> Optional[str]:
        """## Refresh Token Property

        Get the current refresh token used for obtaining new access tokens.

        ### Returns

        - `Optional[str]`: Current refresh token, or None if not authenticated

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")
        client.login()

        refresh = client.refresh_token
        if refresh:
            # Save for later use
            save_token_to_config(refresh)
        ```
        """
        return (
            self.auth_manager.tokens.refresh_token if self.auth_manager.tokens else None
        )

    async def login(
        self, email: Optional[str] = None, password: Optional[str] = None
    ) -> Dict[str, Any]:
        """## Login to Axiom Trade

        Authenticate with email and password. Performs the full OTP-based authentication
        flow if needed. Tokens are automatically saved if `use_saved_tokens=True`.

        ### Parameters

        - `email` (Optional[str]): Email address for login. Falls back to username
          provided in constructor if not specified.

        - `password` (Optional[str]): Password for login. Falls back to password
          provided in constructor if not specified.

        ### Returns

        - `Dict[str, Any]`: Login result containing:
            - `success` (bool): True if login succeeded, False otherwise
            - `access_token` (str): JWT access token (on success)
            - `refresh_token` (str): JWT refresh token (on success)
            - `expires_at` (float): Token expiration timestamp (on success)
            - `message` (str): Human-readable status message

        ### Raises

        - `ValueError`: If email and password are not provided and not available from constructor

        ### Example

        ```python
        # Login with credentials
        client = AxiomTradeClient()
        result = client.login(email="user@example.com", password="password")

        if result["success"]:
            print(f"Login successful! Token expires at {result['expires_at']}")
        else:
            print(f"Login failed: {result['message']}")

        # Login using constructor credentials
        client = AxiomTradeClient(username="user@example.com", password="password")
        result = client.login()  # Uses stored credentials
        ```
        """
        # Use provided credentials or fall back to constructor values
        email = email or self.auth_manager.username
        password = password or self.auth_manager.password

        if not email or not password:
            raise ValueError(
                "Email and password are required for login. "
                "Provide them in login() call or constructor."
            )

        # Update auth manager credentials
        self.auth_manager.username = email
        self.auth_manager.password = password

        # Perform authentication
        success = self.auth_manager.authenticate()

        if success and self.auth_manager.tokens:
            self.logger.info("Login successful for %s", email)
            return {
                "success": True,
                "access_token": self.auth_manager.tokens.access_token,
                "refresh_token": self.auth_manager.tokens.refresh_token,
                "expires_at": self.auth_manager.tokens.expires_at,
                "message": "Login successful",
            }
        else:
            self.logger.warning("Login failed for %s", email)
            return {"success": False, "message": "Login failed"}

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        """## Set Authentication Tokens

        Manually set access and refresh tokens without performing login.
        Useful when tokens are obtained from external sources or saved configurations.

        ### Parameters

        - `access_token` (str): JWT access token for API authentication
        - `refresh_token` (str): JWT refresh token for obtaining new access tokens

        ### Example

        ```python
        client = AxiomTradeClient(use_saved_tokens=False)

        # Set tokens from external source
        client.set_tokens(
            access_token="eyJhbGc...",
            refresh_token="eyJhbGc..."
        )

        # Now can use API
        portfolio = client.get_user_portfolio()
        ```
        """
        self.auth_manager._set_tokens(access_token, refresh_token)
        self.logger.debug("Tokens set manually")

    def get_tokens(self) -> Dict[str, Any]:
        """## Get Current Tokens

        Retrieve information about current authentication tokens.

        ### Returns

        - `Dict[str, Any]`: Token information containing:
            - `access_token` (Optional[str]): Current access token or None
            - `refresh_token` (Optional[str]): Current refresh token or None
            - `expires_at` (Optional[float]): Expiration timestamp or None
            - `is_expired` (bool): Whether tokens are expired

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")
        client.login()

        tokens = client.get_tokens()
        print(f"Access token: {tokens['access_token'][:20]}...")
        print(f"Expires at: {tokens['expires_at']}")
        print(f"Is expired: {tokens['is_expired']}")

        # Check expiration
        if tokens['is_expired']:
            client.refresh_access_token()
        ```
        """
        tokens = self.auth_manager.tokens
        return {
            "access_token": tokens.access_token if tokens else None,
            "refresh_token": tokens.refresh_token if tokens else None,
            "expires_at": tokens.expires_at if tokens else None,
            "is_expired": tokens.is_expired if tokens else True,
        }

    def is_authenticated(self) -> bool:
        """## Check Authentication Status

        Check if the client has valid (non-expired) authentication tokens.

        ### Returns

        - `bool`: True if authenticated with valid tokens, False otherwise

        ### Example

        ```python
        client = AxiomTradeClient(use_saved_tokens=True)

        if client.is_authenticated():
            print("Ready to use API")
        else:
            print("Need to login")
            client.login(email="user@example.com", password="password")
        ```
        """
        return self.auth_manager.is_authenticated()

    def refresh_access_token(self) -> bool:
        """## Refresh Access Token

        Manually refresh the access token using the stored refresh token.
        This is usually called automatically by `ensure_authenticated()`.

        ### Returns

        - `bool`: True if refresh was successful, False otherwise

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")
        client.login()

        # Later, when token expires
        if not client.is_authenticated():
            if client.refresh_access_token():
                print("Token refreshed successfully")
            else:
                print("Refresh failed, need to login again")
                client.login()
        ```
        """
        success = self.auth_manager.refresh_tokens()
        if success:
            self.logger.debug("Access token refreshed successfully")
        else:
            self.logger.warning("Failed to refresh access token")
        return success

    async def refresh_tokens(self):
        """## Async Token Refresh

        Asynchronous version of token refresh method. Useful for refreshing tokens in
        async contexts without blocking the event loop.

        ### Returns

        - `bool`: True if refresh was successful, False otherwise

        """
        if not self.auth_manager.tokens or not self.auth_manager.tokens.refresh_token:
            self.logger.error("No refresh token available for token refresh")
            return False

        try:
            self.logger.info("Refreshing authentication tokens...")

            await self.load()
            # API endpoint for token refresh
            endpoint = "/refresh-access-token"
            response = await super()._fetch(
                "POST",
                endpoint,
            )
            await self.save(cookiess=self.session.cookie_jar)

            if self.auth_manager.process_refresh_response({}, response.cookies):
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
        if not self.auth_manager.tokens:
            if self.auth_manager.username and self.auth_manager.password:
                result = await self.login()
                return result["success"]
            return False

        # Tokens valid
        if not self.auth_manager.tokens.is_expired:
            return True

        # Try refresh
        if await self.refresh_tokens():
            self.logger.info("Refreshing expired tokens...")
            return True

        # Refresh failed - try re-authentication
        if self.auth_manager.username and self.auth_manager.password:
            self.logger.info("Refresh failed, attempting re-authentication")
            result = await self.login()
            return result["success"]

        return False

    def logout(self) -> None:
        """## Logout

        Clear all authentication data including in-memory tokens and saved tokens
        from secure storage. After logout, you'll need to login again to use the API.

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")
        client.login()

        # Use API...

        # Logout when done
        client.logout()

        # Now must login again
        print(client.is_authenticated())  # False
        ```
        """
        self.auth_manager.logout()
        self.logger.info("Logged out successfully")

    def clear_saved_tokens(self) -> bool:
        """## Clear Saved Tokens

        Remove saved tokens from secure storage without affecting in-memory tokens.
        The client will remain authenticated until tokens expire.

        ### Returns

        - `bool`: True if tokens were cleared successfully, False otherwise

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")
        client.login()

        # Clear saved tokens but keep session active
        if client.clear_saved_tokens():
            print("Saved tokens cleared")

        # Still authenticated in memory
        print(client.is_authenticated())  # True

        # But won't load saved tokens on next run
        ```
        """
        success = self.auth_manager.clear_saved_tokens()
        if success:
            self.logger.debug("Saved tokens cleared from storage")
        return success

    def has_saved_tokens(self) -> bool:
        """## Check for Saved Tokens

        Check if encrypted tokens exist in secure storage.

        ### Returns

        - `bool`: True if saved tokens exist, False otherwise

        ### Example

        ```python
        client = AxiomTradeClient(use_saved_tokens=True)

        if client.has_saved_tokens():
            print("Found saved tokens, loading...")
            # Tokens loaded automatically on init
        else:
            print("No saved tokens, need to login")
            client.login(email="user@example.com", password="password")
        ```
        """
        return self.auth_manager.has_saved_tokens()

    def get_token_info_detailed(self) -> Dict[str, Any]:
        """## Get Detailed Token Information

        Get comprehensive information about current authentication tokens including
        expiration details and validity status.

        ### Returns

        - `Dict[str, Any]`: Detailed token information containing:
            - `has_tokens` (bool): Whether tokens are available
            - `is_authenticated` (bool): Whether tokens are valid
            - `access_token` (Optional[str]): Current access token
            - `refresh_token` (Optional[str]): Current refresh token
            - `expires_at` (Optional[float]): Expiration timestamp
            - `is_expired` (bool): Whether tokens are expired
            - `time_until_expiry` (Optional[float]): Seconds until expiration

        ### Example

        ```python
        client = AxiomTradeClient(username="user@example.com", password="password")
        client.login()

        info = client.get_token_info_detailed()
        print(f"Authenticated: {info['is_authenticated']}")
        print(f"Expires in: {info['time_until_expiry']} seconds")
        print(f"Is expired: {info['is_expired']}")

        # Check if token needs refresh
        if info['time_until_expiry'] and info['time_until_expiry'] < 300:
            print("Token expires soon, refreshing...")
            client.refresh_access_token()
        ```
        """
        return self.auth_manager.get_token_info()

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
        print("Cookies :", self.session.cookie_jar.filter_cookies(URL(self.base_url)))
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
            params = {"devAddress": dev_address, "v": 1771633387195}
            return await self._get("/dev-tokens-v3", params=params)
        except Exception as e:
            self.logger.error("Error getting token info: %s", e)
            raise Exception(f"Failed to get token info: {e}") from e

    async def save(self, file: str = "session.dat", pattern: str = ".*", cookiess=None):
        """
        save all cookies (or a subset, controlled by `pattern`) to a file to be restored later

        :param file:
        :type file:
        :param pattern: regex style pattern string.
               any cookie that has a  domain, key or value field which matches the pattern will be included.
               default = ".*"  (all)

               eg: the pattern "(cf|.com|nowsecure)" will include those cookies which:
                    - have a string "cf" (cloudflare)
                    - have ".com" in them, in either domain, key or value field.
                    - contain "nowsecure"
        :type pattern: str
        :return:
        :rtype:
        """
        import re

        import pathlib
        import pickle

        re_pattern: re.Pattern = re.compile(pattern)
        save_path = pathlib.Path(file).resolve()

        # cookies = await self.session.cookie_jar.get_all(requests_cookie_format=False)
        cookies = self.session.cookie_jar
        cookies.clear(lambda cookie: cookie["domain"] == "")
        print("Cookies::", cookies)
        # print(cookies.keys())
        # print(cookies.values())

        included_cookies = []
        for cookie in cookies:
            # for match in re_pattern.finditer(str(cookie.__dict__)):
            # self.logger.debug(
            #     "saved cookie for matching pattern '%s' => (%s: %s)",
            #     re_pattern.pattern,
            #     cookie.name,
            #     cookie.value,
            # )
            print("Cookie :", cookie.keys())
            print("Cookie :", cookie.values())
            print("Cookie :", cookie)
            included_cookies.append(cookie)
            # break
        pickle.dump(included_cookies, save_path.open("w+b"))

    async def load(self, file: str = "session.dat", pattern: str = ".*"):
        """
        load all cookies (or a subset, controlled by `pattern`) from a file created by :py:meth:`~save_cookies`.

        :param file:
        :type file:
        :param pattern: regex style pattern string.
               any cookie that has a  domain, key or value field which matches the pattern will be included.
               default = ".*"  (all)

               eg: the pattern "(cf|.com|nowsecure)" will include those cookies which:
                    - have a string "cf" (cloudflare)
                    - have ".com" in them, in either domain, key or value field.
                    - contain "nowsecure"
        :type pattern: str
        :return:
        :rtype:
        """
        import re
        import pathlib
        import pickle

        re_pattern: re.Pattern = re.compile(pattern)
        save_path = pathlib.Path(file).resolve()
        cookies = pickle.load(save_path.open("r+b"))
        included_cookies = []

        for cookie in cookies:
            for match in re_pattern.finditer(str(cookie.__dict__)):
                included_cookies.append(cookie)
                self.logger.debug(
                    "loaded cookie for matching pattern '%s' => (%s: %s)",
                    re_pattern.pattern,
                    cookie.name,
                    cookie.value,
                )
                break
        self.session.cookie_jar.update_cookies(included_cookies)
