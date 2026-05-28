"""
Generic JSON-driven message filter for WebSocket sources.

Define rules in ``filters.json`` (next to this package's root).
Each source section contains field → rule mappings.  Rules:

- ``include``         : list of allowed values (``"*"`` is a wildcard).
- ``exclude``         : list of forbidden values.
- ``exclude_if_true`` : drop the message when the field is truthy.
- ``exclude_if_value``: drop when the field equals this string (case-insensitive).
- ``must_contain``    : the field (string) must contain at least one of these substrings.
- ``min`` / ``max``   : numeric bounds (inclusive).

Dotted paths like ``"protocol_details.isMayhem"`` are supported for nested dicts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DEFAULT_CONFIG = Path(__file__).parent.parent / "filters.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_nested(data: dict, dotted_path: str) -> Any:
    """Resolve ``'a.b.c'`` style paths through nested dicts."""
    val: Any = data
    for key in dotted_path.split("."):
        if not isinstance(val, dict):
            return None
        val = val.get(key)
    return val


def _should_skip_by_rule(value: Any, rule: dict) -> bool:
    """Return ``True`` when *value* violates *rule* (message should be dropped)."""

    # include: value must be one of these ("*" allows everything)
    if "include" in rule:
        allowed = rule["include"]
        if "*" not in allowed:
            ci = rule.get("case_insensitive", False)
            check = value.lower() if ci and isinstance(value, str) else value
            norm = [a.lower() if ci and isinstance(a, str) else a for a in allowed]
            if check not in norm:
                return True

    # exclude: value must NOT be one of these
    if "exclude" in rule:
        if value in rule["exclude"]:
            return True

    # exclude_if_true: drop when the field is truthy
    if rule.get("exclude_if_true") and value:
        return True

    # exclude_if_value: case-insensitive string match
    if "exclude_if_value" in rule:
        target = rule["exclude_if_value"]
        check = value.lower() if isinstance(value, str) else value
        ref = target.lower() if isinstance(target, str) else target
        if check == ref:
            return True

    # must_contain: at least one substring must appear in the field string
    # allow_empty: when True, empty/None values pass through without checking
    if "must_contain" in rule:
        if not value:
            if not rule.get("allow_empty", False):
                return True
        elif not isinstance(value, str):
            return True
        elif not any(sub in value for sub in rule["must_contain"]):
            return True

    # min / max for numeric fields
    if rule.get("min") is not None:
        try:
            if float(value) < float(rule["min"]):
                return True
        except (TypeError, ValueError):
            pass

    if rule.get("max") is not None:
        try:
            if float(value) > float(rule["max"]):
                return True
        except (TypeError, ValueError):
            pass

    return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class MessageFilter:
    """
    Loads filter rules from a JSON config and decides whether an incoming
    WebSocket message should be skipped.

    Example::

        _filter = MessageFilter()
        if _filter.should_skip("pumpportal", data):
            return
    """

    def __init__(self, config_path: str | Path = _DEFAULT_CONFIG) -> None:
        with open(config_path) as fh:
            cfg = json.load(fh)
        self._filters: dict[str, dict] = cfg.get("filters", {})

    def is_enabled(self, source: str) -> bool:
        """Return ``True`` when the source is not explicitly disabled."""
        return self._filters.get(source, {}).get("enabled", True)

    def should_skip(self, source: str, data: dict) -> bool:
        """
        Return ``True`` when *data* should be discarded for *source*.

        Returns ``False`` (pass-through) when no config exists for the source.
        """
        source_cfg = self._filters.get(source)
        if not source_cfg:
            return False

        if not source_cfg.get("enabled", True):
            return True  # entire source disabled

        for field, rule in source_cfg.items():
            if field == "enabled" or not isinstance(rule, dict):
                continue
            value = _get_nested(data, field)
            if _should_skip_by_rule(value, rule):
                return True

        return False
