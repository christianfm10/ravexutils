"""
# Cloudflare Bypass Module

This module provides functionality to bypass Cloudflare protection and obtain
cf_clearance cookies using browser automation.

## Design Decisions:
- Uses nodriver (undetected-chromedriver) for stealth browser automation
- Session persistence to avoid repeated Cloudflare challenges
- Proxy support for distributed scraping scenarios
- Async/await pattern for non-blocking I/O operations
"""

import logging
from pathlib import Path
from typing import Optional, List

import nodriver as uc
from nodriver.cdp.network import Cookie

# Configure module logger
logger = logging.getLogger(__name__)

# Constants
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/137.0.0.0 Safari/537.36"
)
DEFAULT_TIMEOUT = 100
DEFAULT_SESSION_DIR = "sessions"
CLOUDFLARE_COOKIE_NAME = "cf_clearance"
CLOUDFLARE_VERIFICATION_TEXT = "Verify you are human"
CLOUDFLARE_CHALLENGE_WAIT_TIMEOUT = 5  # Short timeout to check for challenge presence
PROXY_VERIFICATION_URL = "https://httpbin.org/ip"


class CloudflareBypassError(Exception):
    """
    # Cloudflare Bypass Error

    Base exception for Cloudflare bypass operations.
    Provides more specific error handling than generic exceptions.
    """

    pass


class BrowserInitializationError(CloudflareBypassError):
    """
    # Browser Initialization Error

    Raised when browser fails to initialize properly.
    """

    pass


class NavigationError(CloudflareBypassError):
    """
    # Navigation Error

    Raised when navigation to target URL fails.
    """

    pass


class CookieRetrievalError(CloudflareBypassError):
    """
    # Cookie Retrieval Error

    Raised when cf_clearance cookie cannot be obtained.
    """

    pass


class CloudflareBypass:
    """
    # Cloudflare Bypass Manager

    Manages browser automation for bypassing Cloudflare protection and obtaining
    cf_clearance cookies.

    ## Features:
    - Stealth browser automation using nodriver
    - Session persistence for reusing cookies
    - Proxy support for IP rotation
    - Automatic Cloudflare challenge solving

    ## Usage:
    ```python
    bypass = CloudflareBypass(
        target_url="https://example.com",
        proxy="http://proxy:port",
        headless=True
    )
    success = await bypass.run()
    if success:
        cookie = bypass.cf_clearance
    ```
    """

    def __init__(
        self,
        target_url: str,
        proxy: Optional[str] = None,
        headless: bool = False,
        session_dir: str = DEFAULT_SESSION_DIR,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """
        # Initialize Cloudflare Bypass

        Sets up the bypass manager with configuration parameters.

        ## Parameters:
        - `target_url`: The URL to access after bypassing Cloudflare
        - `proxy`: Optional proxy server (format: "http://host:port")
        - `headless`: Run browser in headless mode (default: False)
        - `session_dir`: Directory to store session files (default: "sessions")
        - `timeout`: Maximum time to wait for Cloudflare challenge (default: 100s)

        ## Design Note:
        Session files are named based on proxy to maintain separate cookies
        for different IP addresses, preventing cookie/IP mismatch issues.
        """
        # Validate input parameters
        if not target_url:
            raise ValueError("target_url cannot be empty")

        if timeout <= 0:
            raise ValueError("timeout must be positive")

        # Core configuration
        self.target_url: str = target_url
        self.proxy: Optional[str] = proxy
        self.headless: bool = headless
        self.timeout: int = timeout

        # Initialize session management
        self.session_dir: Path = Path(session_dir)
        self.session_file: Path = self._create_session_file_path()

        # Browser state - initialized as None and set during runtime
        self.browser: Optional[uc.Browser] = None
        self.tab: Optional[uc.Tab] = None
        self.tab_ip: Optional[uc.Tab] = None
        self.user_agent: str = DEFAULT_USER_AGENT
        self.cf_clearance: Optional[Cookie] = None

    def _create_session_file_path(self) -> Path:
        """
        # Create Session File Path

        Generates a unique session file path based on proxy configuration.

        ## Algorithm:
        1. Create session directory if it doesn't exist
        2. Generate session ID from proxy string (sanitized) or use "default"
        3. Return path to session file

        ## Returns:
        Path object pointing to the session file

        ## Design Note:
        Special characters in proxy strings are replaced to create valid filenames.
        This ensures each proxy gets its own session file, preventing cookie conflicts.
        """
        try:
            self.session_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create session directory: {e}")
            raise CloudflareBypassError(f"Cannot create session directory: {e}")

        # Generate unique session ID based on proxy
        if self.proxy:
            # Sanitize proxy string for use in filename
            session_id = (
                self.proxy.replace(":", "_").replace("/", "_").replace("@", "_")
            )
        else:
            session_id = "default"

        return self.session_dir / f"session_{session_id}.dat"

    def _build_browser_arguments(self) -> List[str]:
        """
        # Build Browser Arguments

        Constructs Chrome command-line arguments for stealth and functionality.

        ## Returns:
        List of browser arguments

        ## Design Note:
        These arguments are carefully selected to:
        - Bypass SSL certificate validation (for proxies with MITM)
        - Disable popup blocking (for better automation)
        - Configure proxy if provided
        """
        browser_args = [
            "--disable-popup-blocking",  # Allow automated popup handling
            "--ignore-ssl-errors",  # Handle SSL issues with proxies
            "--ignore-certificate-errors",  # Additional SSL error handling
        ]

        if self.proxy:
            browser_args.append(f"--proxy-server={self.proxy}")

        return browser_args

    async def initialize_browser(self) -> None:
        """
        # Initialize Browser

        Starts the browser with configured arguments and retrieves user agent.

        ## Raises:
        - `BrowserInitializationError`: If browser fails to start

        ## Design Note:
        Uses nodriver's stealth capabilities to avoid detection by Cloudflare.
        User agent is extracted from browser to ensure consistency in requests.
        """
        try:
            browser_args = self._build_browser_arguments()

            self.browser = await uc.start(
                browser_args=browser_args, headless=self.headless
            )

            # Extract actual user agent from browser
            if self.browser and self.browser.info:
                self.user_agent = self.browser.info.get(
                    "User-Agent", DEFAULT_USER_AGENT
                )

            logger.debug(f"Browser initialized successfully with UA: {self.user_agent}")

        except Exception as e:
            error_msg = f"Browser initialization failed: {e}"
            logger.error(error_msg)
            raise BrowserInitializationError(error_msg) from e

    async def load_existing_session(self) -> bool:
        """
        # Load Existing Session

        Attempts to load previously saved cookies from session file.

        ## Returns:
        True if session was loaded, False if no session exists

        ## Design Note:
        Only loads cookies matching "cf" pattern (Cloudflare cookies) to avoid
        loading unnecessary cookies and maintaining session size.
        """
        if not self.browser:
            logger.warning("Cannot load session: browser not initialized")
            return False

        if not self.session_file.exists():
            logger.debug(f"No existing session found at {self.session_file}")
            return False

        try:
            await self.browser.cookies.load(str(self.session_file), pattern="cf")
            logger.info(f"Successfully loaded session from {self.session_file}")
            return True

        except Exception as e:
            logger.warning(f"Failed to load session: {e}")
            return False

    async def save_current_session(self) -> None:
        """
        # Save Current Session

        Persists current Cloudflare cookies to session file for future use.

        ## Raises:
        - `CloudflareBypassError`: If session cannot be saved

        ## Design Note:
        Only saves cookies matching "cf" pattern to keep session files minimal
        and focused on Cloudflare-specific cookies.
        """
        if not self.browser:
            logger.warning("Cannot save session: browser not initialized")
            return

        try:
            await self.browser.cookies.save(str(self.session_file), pattern="cf")
            logger.info(f"Session saved successfully to {self.session_file}")

        except Exception as e:
            error_msg = f"Failed to save session: {e}"
            logger.error(error_msg)
            raise CloudflareBypassError(error_msg) from e

    async def verify_proxy_connection(self) -> bool:
        """
        # Verify Proxy Connection

        Tests proxy connectivity by accessing a public IP checking service.

        ## Returns:
        True if proxy is working, False otherwise

        ## Design Note:
        This is an important validation step to fail fast if the proxy is down,
        rather than waiting for timeout during Cloudflare challenge.
        """
        if not self.browser:
            logger.warning("Cannot verify proxy: browser not initialized")
            return False

        if not self.proxy:
            # No proxy configured, skip verification
            return True

        try:
            self.tab_ip = await self.browser.get(PROXY_VERIFICATION_URL)
            logger.debug("Proxy connection verified successfully")
            return True

        except Exception as e:
            logger.error(f"Proxy verification failed: {e}")
            return False

    async def is_cloudflare_challenge_present(self) -> bool:
        """
        # Check for Cloudflare Challenge Presence

        Detects whether a Cloudflare challenge page is currently displayed.

        ## Returns:
        True if Cloudflare challenge is present, False otherwise

        ## Algorithm:
        Uses a short timeout to check for the presence of Cloudflare's
        verification text without blocking for a long time.

        ## Design Note:
        This non-blocking check allows us to quickly determine if we need to
        solve a challenge, avoiding unnecessary wait times when the page loads
        directly without Cloudflare protection.
        """
        if not self.tab:
            logger.warning("Cannot check for challenge: tab not initialized")
            return False

        try:
            # Use a short timeout to quickly check for challenge presence
            await self.tab.wait_for(
                text=CLOUDFLARE_VERIFICATION_TEXT,
                timeout=CLOUDFLARE_CHALLENGE_WAIT_TIMEOUT,
            )
            logger.info("Cloudflare challenge detected on page")
            return True

        except Exception:
            # Challenge text not found within timeout - page loaded normally
            logger.debug("No Cloudflare challenge detected - page loaded directly")
            return False

    async def solve_cloudflare_challenge(self) -> None:
        """
        # Solve Cloudflare Challenge

        Attempts to solve the Cloudflare challenge using nodriver's verification.

        ## Raises:
        - `NavigationError`: If challenge cannot be completed

        ## Algorithm:
        1. Use nodriver's built-in CF verification
        2. Wait additional time for challenge completion and cookie setting

        ## Design Note:
        The 10-second wait after verification gives Cloudflare time to process
        the challenge completion and set cookies properly. This is crucial as
        cookies may not be immediately available after verification.
        """
        try:
            logger.info("Attempting to solve Cloudflare challenge")

            if self.tab is None:
                raise NavigationError("Tab not initialized for challenge solving")
            # Attempt to solve the challenge
            await self.tab.verify_cf(template_image="cf_image.jpeg", flash=True)
            logger.debug("Cloudflare verification method executed")

            # Wait for challenge completion and cookie setting
            await self.tab.wait(10)
            logger.info("Cloudflare challenge completed successfully")

        except Exception as e:
            error_msg = f"Failed to solve Cloudflare challenge: {e}"
            logger.error(error_msg)
            raise NavigationError(error_msg) from e

    async def handle_cloudflare_protection(self) -> None:
        """
        # Handle Cloudflare Protection

        Intelligently detects and solves Cloudflare challenges only when necessary.

        ## Algorithm:
        1. Check if Cloudflare challenge is present
        2. If present, attempt to solve it
        3. If not present, skip challenge solving (page loaded normally)

        ## Raises:
        - `NavigationError`: If challenge solving fails

        ## Design Note:
        This approach is more efficient than always waiting for challenges:
        - Saves time when cookies are valid and no challenge appears
        - Prevents unnecessary timeouts on direct page loads
        - Only performs challenge solving when actually needed
        """
        if await self.is_cloudflare_challenge_present():
            await self.solve_cloudflare_challenge()
        else:
            logger.info(
                "Page loaded without Cloudflare challenge - proceeding normally"
            )

    async def navigate_to_target_url(self) -> None:
        """
        # Navigate to Target URL

        Opens the target URL in a new tab and handles Cloudflare protection.

        ## Raises:
        - `NavigationError`: If navigation fails or proxy verification fails

        ## Design Note:
        Opens in a new tab (instead of current tab) to keep proxy verification
        tab separate, which can be useful for debugging.
        """
        if not self.browser:
            raise NavigationError("Browser not initialized")

        # Verify proxy is working before attempting navigation
        if not await self.verify_proxy_connection():
            raise NavigationError("Proxy verification failed")

        try:
            # Navigate to target URL in new tab
            self.tab = await self.browser.get(self.target_url, new_tab=True)
            logger.debug(f"Navigated to target URL: {self.target_url}")

            # Intelligently handle Cloudflare protection (only solve if needed)
            await self.handle_cloudflare_protection()

        except NavigationError:
            # Re-raise NavigationError without wrapping
            raise
        except Exception as e:
            error_msg = f"Navigation to target URL failed: {e}"
            logger.error(error_msg)
            raise NavigationError(error_msg) from e

    async def retrieve_cf_clearance_cookie(self) -> bool:
        """
        # Retrieve CF Clearance Cookie

        Extracts the cf_clearance cookie from browser cookies.

        ## Returns:
        True if cookie was found, False otherwise

        ## Algorithm:
        1. Fetch all cookies from browser in requests-compatible format
        2. Search for cookie named "cf_clearance"
        3. Store cookie reference for external use

        ## Design Note:
        Returns boolean for flow control while storing the actual cookie
        object for later retrieval via the cf_clearance property.
        """
        if not self.browser:
            logger.warning("Cannot retrieve cookies: browser not initialized")
            return False

        try:
            cookies = await self.browser.cookies.get_all(requests_cookie_format=True)

            # Search for cf_clearance cookie
            for cookie in cookies:
                if cookie.name == CLOUDFLARE_COOKIE_NAME:
                    self.cf_clearance = cookie
                    logger.info("Successfully obtained cf_clearance cookie")
                    logger.debug(f"Cookie value: {cookie.value[:20]}...")
                    return True

            # Cookie not found
            logger.warning(f"No {CLOUDFLARE_COOKIE_NAME} cookie found in browser")
            return False

        except Exception as e:
            logger.error(f"Failed to retrieve cookies: {e}")
            return False

    async def cleanup_browser_resources(self) -> None:
        """
        # Cleanup Browser Resources

        Properly closes browser tabs and stops the browser process.

        ## Design Note:
        This is a critical cleanup step to prevent:
        - Memory leaks from unclosed browser processes
        - Orphaned Chrome processes consuming system resources
        - File descriptor leaks

        Safe to call multiple times (idempotent).
        """
        # Close tab if open
        if self.tab:
            try:
                await self.tab.close()
                logger.debug("Tab closed successfully")
            except Exception as e:
                logger.warning(f"Error closing tab: {e}")
            finally:
                self.tab = None

        # Close IP verification tab if open
        if self.tab_ip:
            try:
                await self.tab_ip.close()
                logger.debug("IP verification tab closed successfully")
            except Exception as e:
                logger.warning(f"Error closing IP tab: {e}")
            finally:
                self.tab_ip = None

        # Stop browser
        if self.browser:
            try:
                self.browser.stop()
                logger.debug("Browser stopped successfully")
            except Exception as e:
                logger.warning(f"Error stopping browser: {e}")
            finally:
                self.browser = None

    async def run(self, update_cf: bool = True) -> bool:
        """
        # Run Cloudflare Bypass

        Main execution flow that orchestrates the entire bypass process.

        ## Parameters:
        - `update_cf`: Whether to navigate to target and get fresh cookie (default: True)
                      Set to False to only load existing session without navigation

        ## Returns:
        True if bypass succeeded and cf_clearance cookie was obtained, False otherwise

        ## Algorithm:
        1. Initialize browser with stealth configuration
        2. Load existing session if available (optimization)
        3. Navigate to target URL and solve Cloudflare challenge (if update_cf=True)
        4. Extract cf_clearance cookie
        5. Save session for future use
        6. Cleanup resources

        ## Error Handling:
        All exceptions are caught and logged. Returns False on any failure.
        Cleanup is always performed via finally block to prevent resource leaks.

        ## Design Note:
        The update_cf parameter allows reusing existing cookies without navigation,
        which is useful when cookies are still valid and you want to avoid
        triggering Cloudflare challenges unnecessarily.
        """
        try:
            # Step 1: Initialize browser
            await self.initialize_browser()

            # Step 2: Load existing session (may avoid need for challenge)
            session_loaded = await self.load_existing_session()
            if session_loaded:
                logger.info("Existing session loaded, attempting to use cached cookies")

            # Step 3: Navigate and solve Cloudflare challenge if requested
            if update_cf:
                await self.navigate_to_target_url()
            else:
                logger.info("Skipping navigation (update_cf=False)")

            # Step 4: Extract cf_clearance cookie
            if not await self.retrieve_cf_clearance_cookie():
                logger.error("Failed to obtain cf_clearance cookie")
                return False

            # Step 5: Save session for future use
            await self.save_current_session()

            logger.info("Cloudflare bypass completed successfully")
            return True

        except BrowserInitializationError as e:
            logger.error(f"Browser initialization failed: {e}")
            return False

        except NavigationError as e:
            logger.error(f"Navigation failed: {e}")
            return False

        except CookieRetrievalError as e:
            logger.error(f"Cookie retrieval failed: {e}")
            return False

        except CloudflareBypassError as e:
            logger.error(f"Cloudflare bypass error: {e}")
            return False

        except Exception as e:
            logger.exception(f"Unexpected error during execution: {e}")
            return False

        finally:
            # Always cleanup resources to prevent leaks
            await self.cleanup_browser_resources()
