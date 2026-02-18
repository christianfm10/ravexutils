"""
RavexClient - Base HTTP client for building API clients.

This package provides a flexible and extensible base class for creating
async HTTP clients with built-in support for proxies, authentication,
and error handling.
"""

from .client import BaseClient as Client
from .aiohttp_client import BaseAioHttpClient

__version__ = "0.1.0"
__all__ = [
    "Client",
    "BaseAioHttpClient",
]
