"""
Custom exceptions for the RavexClient package.

This module provides specialized exceptions for better error handling
when building clients that inherit from BaseClient.
"""


class RavexClientError(Exception):
    """Base exception for all RavexClient errors."""

    def __init__(self, message: str, *args, **kwargs):
        super().__init__(message, *args)
        self.message = message
        self.details = kwargs


class HTTPError(RavexClientError):
    """Raised when an HTTP request fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: dict | None = None,
    ):
        super().__init__(message, status_code=status_code, response_body=response_body)
        self.status_code = status_code
        self.response_body = response_body


class ProxyError(RavexClientError):
    """Raised when there's an issue with the proxy configuration or connection."""

    pass


class AuthenticationError(RavexClientError):
    """Raised when authentication fails."""

    pass


class ConfigurationError(RavexClientError):
    """Raised when there's an issue with client configuration."""

    pass


class TimeoutError(RavexClientError):
    """Raised when a request times out."""

    pass
