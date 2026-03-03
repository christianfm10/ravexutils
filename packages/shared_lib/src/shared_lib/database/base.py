# check sqlalchemy is installed
try:
    from sqlalchemy.orm import DeclarativeBase
except ImportError:
    raise ImportError(
        "SQLAlchemy is not installed. Please install it with 'uv sync --extra database' or 'uv add sqlalchemy[asyncio]'."
    )


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""

    ...
