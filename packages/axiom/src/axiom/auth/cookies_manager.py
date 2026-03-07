import logging
from aiohttp.abc import AbstractCookieJar


class CookieManager:
    """
    # HTTP Cookie Manager

    Manages HTTP cookies for authenticated API requests. Provides a simple
    interface for setting, formatting, and clearing authentication cookies.

    ## Responsibilities:
    - Store authentication cookies (access token, refresh token)
    - Format cookies for HTTP Cookie header
    - Clear cookies on logout

    ## Cookie Format:
    Cookies are formatted as: `name1=value1; name2=value2; name3=value3`

    ## Design Decisions:
    - Uses simple dict storage (no complex cookie jar needed)
    - Focuses specifically on auth cookies (not general-purpose)
    - Thread-safe for basic operations (dict operations are atomic in CPython)

    ## Example:
    ```python
    cookie_mgr = CookieManager()
    cookie_mgr.set_auth_cookies("access_token_value", "refresh_token_value")

    # Get formatted cookie string for HTTP header
    cookie_header = cookie_mgr.get_cookie_header()
    # Returns: "auth-access-token=access_token_value; auth-refresh-token=refresh_token_value"
    ```
    """

    def __init__(self) -> None:
        """
        Initialize cookie manager with empty cookie store.

        ## Side Effects:
        - Creates empty dictionary for cookie storage
        - Initializes logger for debugging
        """
        self.cookies: dict[str, str] = {}
        self.cooks: AbstractCookieJar | None = None
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def set_auth_cookies(self, auth_token: str, refresh_token: str) -> None:
        """
        Set authentication cookies for API requests.

        Updates the internal cookie store with authentication tokens.
        These cookies are required for authenticated API requests to Axiom Trade.

        ## Args:
        - `auth_token` (str): Access token (JWT) for API authentication
        - `refresh_token` (str): Refresh token for obtaining new access tokens

        ## Cookie Names:
        - `auth-access-token`: The active JWT access token
        - `auth-refresh-token`: Long-lived refresh token
        """
        self.cookies["auth-access-token"] = auth_token
        self.cookies["auth-refresh-token"] = refresh_token
        self.logger.debug("Authentication cookies updated in cookie manager")

    def get_cookie_header(self) -> str:
        """
        Format cookies as HTTP Cookie header string.

        Converts the internal cookie dictionary into a properly formatted
        Cookie header value according to RFC 6265.

        ## Returns:
        - `str`: Formatted cookie string (e.g., "name1=value1; name2=value2")
          Returns empty string if no cookies are set

        ## Format:
        Cookies are joined with "; " separator as per HTTP Cookie spec.
        Order is not guaranteed (dict iteration order in Python 3.7+).
        """
        if not self.cookies:
            return ""

        # Format: "name1=value1; name2=value2"
        cookie_pairs = [f"{key}={value}" for key, value in self.cookies.items()]
        return "; ".join(cookie_pairs)

    def clear_auth_cookies(self) -> None:
        """
        Clear authentication cookies from storage.

        Removes auth tokens from cookie store. Used during logout
        or when invalidating the current session.

        ## Side Effects:
        - Removes 'auth-access-token' from cookies
        - Removes 'auth-refresh-token' from cookies
        - Safe to call even if cookies don't exist (no KeyError)
        """
        self.cookies.pop("auth-access-token", None)
        self.cookies.pop("auth-refresh-token", None)
        self.logger.debug("Authentication cookies cleared from cookie manager")

    def has_auth_cookies(self) -> bool:
        """
        Check if authentication cookies are present.

        Verifies that both required auth cookies exist in storage.

        ## Returns:
        - `bool`: True if both access and refresh tokens are present, False otherwise

        ## Note:
        Does not validate token content or expiration, only checks presence.
        """
        return (
            "auth-access-token" in self.cookies and "auth-refresh-token" in self.cookies
        )

    def get_all(self) -> dict[str, str]:
        """
        Get all cookies as a dictionary.

        Returns the internal cookie store as a dictionary of cookie names and values.

        ## Returns:
        - `dict[str, str]`: Dictionary of cookie names to values
          Example: {"auth-access-token": "token_value", "auth-refresh-token": "refresh_value"}
          Returns empty dict if no cookies are set
        """
        return self.cookies.copy()

    def set_all(self, cookies: dict[str, str]) -> None:
        """
        Set multiple cookies at once from a dictionary.

        Updates the internal cookie store with the provided cookies.

        ## Args:
        - `cookies` (dict[str, str]): Dictionary of cookie names to values
          Example: {"auth-access-token": "token_value", "auth-refresh-token": "refresh_value"}

        ## Side Effects:
        - Updates internal cookie store with provided cookies
        - Existing cookies with the same names will be overwritten
        """
        self.cookies.update(cookies)
        self.logger.debug("Multiple cookies set in cookie manager")

    def clear_all(self) -> None:
        """
        Clear all cookies from storage.

        Removes all cookies from the internal store. Use with caution as this will
        remove any non-auth cookies if they are stored here.

        ## Side Effects:
        - Clears entire cookie store, not just auth cookies
        - Use clear_auth_cookies() if you only want to clear auth tokens
        """
        self.cookies.clear()
        self.logger.debug("All cookies cleared from cookie manager")

    async def save(
        self,
        cookies: AbstractCookieJar,
        file: str = "session.dat",
        pattern: str = ".*",
    ):
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
        if self.cooks is not None:
            self.cooks.update_cookies(included_cookies)
        return included_cookies
