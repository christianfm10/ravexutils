import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# 2026-02-06T04:24:45.050
def datetime_to_unix_timestamp(dt: datetime, milliseconds: bool = True) -> int:
    """
    Convert a datetime object to a Unix timestamp.

    ## Parameters
    - `dt`: datetime object to convert (should be timezone-aware)
    - `milliseconds`: True to return timestamp in milliseconds, False for seconds

    ## Returns
    - Unix timestamp as an integer (in ms if milliseconds=True, else in seconds)

    ## Notes
    If the datetime is naive (no timezone), it will be treated as UTC.
    """
    if dt.tzinfo is None:
        logger.warning("Naive datetime provided, assuming UTC")
        dt = dt.replace(tzinfo=timezone.utc)

    timestamp = int(dt.timestamp() * 1000) if milliseconds else int(dt.timestamp())
    return timestamp

def string_to_datetime(timestamp_str: str) -> datetime | None:
    """
    Convert an ISO format timestamp string to a datetime object.

    ## Parameters
    - `timestamp_str`: ISO format timestamp string (e.g., "2024-12-22T10:30:00Z")

    ## Returns
    - `datetime` object representing the timestamp in UTC, or None if parsing fails

    ## Notes
    Gracefully handles malformed timestamps by logging and returning None.
    """
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt
    except ValueError as e:
        logger.error(f"Failed to parse timestamp '{timestamp_str}': {e}")
        return None

def timestamp_to_datetime(
    timestamp: int | float, milliseconds: bool = True
) -> datetime | None:
    """
    Convert a Unix timestamp to a datetime object.

    ## Parameters
    - `timestamp`: Unix timestamp (e.g., 1700000000 or 1770069888028)
    - `milliseconds`: True if timestamp is in ms (13 digits), False if in seconds (10 digits)

    ## Returns
    - `datetime` object representing the timestamp in UTC

    ## Notes
    Gracefully handles malformed timestamps by logging and returning None.
    """

    try:
        # Convert to seconds if needed
        ts_seconds = timestamp / 1000 if milliseconds else timestamp

        # Convert Unix timestamp → datetime UTC
        dt = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
        return dt

    except (ValueError, OSError, TypeError) as e:
        logger.error(f"Failed to parse unix timestamp '{timestamp}': {e}")
        return None


def is_timestamp_older_than(
    timestamp: str, seconds: int | None = None, minutes: int | None = None
) -> bool:
    """
    Check if a timestamp is older than a specified duration.

    ## Parameters
    - `timestamp`: ISO format timestamp string (e.g., "2024-12-22T10:30:00Z")
    - `seconds`: Number of seconds to check against (optional)
    - `minutes`: Number of minutes to check against (optional)

    ## Returns
    - `True` if timestamp is older than specified duration
    - `False` otherwise or if parsing fails

    ## Design Notes
    Gracefully handles malformed timestamps by logging and returning False.
    This prevents one bad timestamp from crashing the entire application.
    """
    if seconds is None and minutes is None:
        raise ValueError("Must specify either seconds or minutes")

    try:
        # Parse ISO format with timezone handling
        dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)

        if seconds is not None:
            return now - dt > timedelta(seconds=seconds)
        elif minutes is not None:
            return now - dt > timedelta(minutes=minutes)
        return False

    except (ValueError, AttributeError) as e:
        logger.error(f"Failed to parse timestamp '{timestamp}': {e}")
        return False


def is_unix_timestamp_older_than(
    timestamp: int | float,
    *,
    seconds: int | None = None,
    minutes: int | None = None,
    milliseconds: bool = True,
) -> bool:
    """
    Check if a Unix timestamp is older than a specified duration.

    ## Parameters
    - `timestamp`: Unix timestamp (e.g., 1700000000 or 1770069888028)
    - `seconds`: Number of seconds to check against (optional)
    - `minutes`: Number of minutes to check against (optional)
    - `milliseconds`: True if timestamp is in ms (13 digits), False if in seconds (10 digits)

    ## Returns
    - `True` if timestamp is older than specified duration
    - `False` otherwise or if parsing fails

    ## Notes
    Gracefully handles malformed timestamps by logging and returning False.
    """

    if seconds is None and minutes is None:
        raise ValueError("Must specify either seconds or minutes")

    try:
        # Convert to seconds if needed
        ts_seconds = timestamp / 1000 if milliseconds else timestamp

        # Convert Unix timestamp → datetime UTC
        dt = datetime.fromtimestamp(ts_seconds, tz=timezone.utc)
        now = datetime.now(timezone.utc)

        if seconds is not None:
            return now - dt > timedelta(seconds=seconds)

        if minutes is not None:
            return now - dt > timedelta(minutes=minutes)

        return False

    except (ValueError, OSError, TypeError) as e:
        logger.error(f"Failed to parse unix timestamp '{timestamp}': {e}")
        return False
