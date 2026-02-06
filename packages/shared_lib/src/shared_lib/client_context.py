"""
Client Context - Shared configuration and dependencies for clients.

Provides a centralized context object that holds shared dependencies
and configuration for WebSocket clients and other service clients.
"""

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from telegram.setup import TelegramBot


class ClientContext:
    """
    Context object holding shared dependencies and configuration for clients.

    ## Purpose:
    Encapsulates common dependencies (like notification services) that multiple
    clients might need, avoiding parameter bloat and making dependency injection cleaner.

    ## Parameters:
    - `telegram_bot` (TelegramBot | None, optional): Telegram bot for notifications.
        - Default: `None` (no Telegram notifications)
        - Used for sending alerts about connection events, errors, etc.

    - `log_level` (int, optional): Default logging level for clients.
        - Default: `logging.INFO`
        - Can be overridden by individual clients

    ## Attributes:
    - `telegram_bot`: Optional Telegram bot instance
    - `log_level`: Default logging level

    ## Example:
    ```python
    from shared_lib.client_context import ClientContext
    from telegram.setup import TelegramBot

    # Create context with dependencies
    tg_bot = TelegramBot()
    context = ClientContext(
        telegram_bot=tg_bot,
        log_level=logging.DEBUG
    )

    # Pass to clients
    ws_client = PumpPortalWSClient(context=context)
    http_client = SomeOtherClient(context=context)
    ```

    ## Benefits:
    - **Single Source of Truth**: All shared config in one place
    - **Extensible**: Add new dependencies without changing client signatures
    - **Testable**: Easy to create mock contexts for testing
    - **Clean APIs**: Clients accept one context instead of many parameters

    ## Future Extensions:
    Can be extended to include:
    - Database connections
    - Cache instances
    - Metrics collectors
    - Feature flags
    - API keys and credentials
    """

    def __init__(
        self,
        telegram_bot: Optional["TelegramBot"] = None,
        log_level: int = logging.INFO,
    ) -> None:
        self.telegram_bot = telegram_bot
        self.log_level = log_level

    @property
    def has_telegram(self) -> bool:
        """Check if Telegram bot is configured."""
        return self.telegram_bot is not None
