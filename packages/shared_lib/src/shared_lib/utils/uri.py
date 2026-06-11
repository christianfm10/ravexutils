"""
IPFS / HTTP metadata fetching for token URIs.

A module-level aiohttp session is shared across all calls.
Call :func:`close_session` during cleanup to release the connection pool.

Public API
----------
- ``fetch_token_metadata(uri)`` – GET an IPFS URI and return enriched metadata dict
- ``close_session()``           – gracefully close the shared session
"""

from __future__ import annotations

import logging

import aiohttp

_logger = logging.getLogger(__name__)

_session: aiohttp.ClientSession | None = None


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5))
    return _session


async def close_session() -> None:
    """Close the shared HTTP session. Safe to call even if never opened."""
    global _session
    if _session and not _session.closed:
        await _session.close()
    _session = None


async def fetch_token_metadata(uri: str) -> dict | None:
    """
    GET *uri* (expected to be an IPFS link) and return a dict of token metadata.

    Returns ``None`` on network errors or non-200 responses.

    The returned dict contains the keys that :class:`~shared_lib.models.token.TokenItem`
    understands: ``description``, ``twitter``, ``telegram``, ``website``,
    ``has_<field>`` booleans, ``uri_size``, and ``desc_size``.
    """
    session = await _get_session()
    try:
        async with session.get(uri) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
    except Exception:
        _logger.debug("Failed to fetch metadata from %s", uri, exc_info=True)
        return None

    metadata: dict = {}
    metadata["uri_size"] = len(data)
    metadata["desc_size"] = (
        len(data.get("description", "")) if data.get("description") else None
    )
    for key in ("description", "twitter", "telegram", "website"):
        if key not in data:
            metadata[f"has_{key}"] = False
        elif data[key] is None:
            metadata[key] = None
            metadata[f"has_{key}"] = True
        else:
            metadata[key] = data[key]
            metadata[f"has_{key}"] = True

    return metadata
