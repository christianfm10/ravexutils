from __future__ import annotations

import json

from shared_lib.utils.filters import (
    _get_nested,
    _should_skip_by_rule,
    MessageFilter,
)


def test_get_nested():
    data = {"a": {"b": {"c": 42}}}
    assert _get_nested(data, "a.b.c") == 42
    assert _get_nested(data, "a.b") == {"c": 42}
    assert _get_nested(data, "a.x") is None
    assert _get_nested(data, "x.y.z") is None
    assert _get_nested(data, "a.b.c.d") is None


def test_rule_include():
    # 1. include: "*" wildcard allows everything (should NOT skip)
    rule_star = {"include": ["*"]}
    assert _should_skip_by_rule("anything", rule_star) is False
    assert _should_skip_by_rule(123, rule_star) is False

    # 2. include matches exact value
    rule_exact = {"include": ["apple", "banana"]}
    assert _should_skip_by_rule("apple", rule_exact) is False
    assert _should_skip_by_rule("banana", rule_exact) is False
    assert _should_skip_by_rule("orange", rule_exact) is True

    # 3. include is case sensitive by default
    assert _should_skip_by_rule("Apple", rule_exact) is True

    # 4. include with case_insensitive = True
    rule_ci = {"include": ["apple", "banana"], "case_insensitive": True}
    assert _should_skip_by_rule("Apple", rule_ci) is False
    assert _should_skip_by_rule("BANANA", rule_ci) is False
    assert _should_skip_by_rule("orange", rule_ci) is True


def test_rule_exclude():
    # exclude: value in list should skip (return True)
    rule = {"exclude": ["apple", 42]}
    assert _should_skip_by_rule("apple", rule) is True
    assert _should_skip_by_rule(42, rule) is True
    assert _should_skip_by_rule("banana", rule) is False
    assert _should_skip_by_rule(100, rule) is False


def test_rule_exclude_if_true():
    rule = {"exclude_if_true": True}
    # True, non-empty, truthy values should skip (return True)
    assert _should_skip_by_rule(True, rule) is True
    assert _should_skip_by_rule("hello", rule) is True
    assert _should_skip_by_rule(1, rule) is True

    # Falsy values should NOT skip (return False)
    assert _should_skip_by_rule(False, rule) is False
    assert _should_skip_by_rule("", rule) is False
    assert _should_skip_by_rule(0, rule) is False
    assert _should_skip_by_rule(None, rule) is False


def test_rule_exclude_if_value():
    rule = {"exclude_if_value": "ForbiddenValue"}
    # Case-insensitive check
    assert _should_skip_by_rule("ForbiddenValue", rule) is True
    assert _should_skip_by_rule("forbiddenvalue", rule) is True
    assert _should_skip_by_rule("FORBIDDENVALUE", rule) is True
    assert _should_skip_by_rule("AllowedValue", rule) is False

    # Non-string exclude_if_value handling
    rule_num = {"exclude_if_value": 42}
    assert _should_skip_by_rule(42, rule_num) is True
    assert _should_skip_by_rule(100, rule_num) is False


def test_rule_must_contain():
    rule = {"must_contain": ["sol", "pump"]}

    # Matches contains
    assert _should_skip_by_rule("solana token", rule) is False
    assert _should_skip_by_rule("mypumpcoin", rule) is False

    # Does not contain -> should skip (return True)
    assert _should_skip_by_rule("bitcoin", rule) is True

    # Empty/None values with allow_empty default (False) -> should skip
    assert _should_skip_by_rule("", rule) is True
    assert _should_skip_by_rule(None, rule) is True

    # Non-string value when not empty -> should skip (isnot string type)
    assert _should_skip_by_rule(12345, rule) is True

    # Must contain with allow_empty = True
    rule_allow_empty = {"must_contain": ["sol", "pump"], "allow_empty": True}
    assert _should_skip_by_rule("", rule_allow_empty) is False
    assert _should_skip_by_rule(None, rule_allow_empty) is False
    assert _should_skip_by_rule("bitcoin", rule_allow_empty) is True


def test_rule_min_max():
    rule_min = {"min": 10.5}
    assert _should_skip_by_rule(11, rule_min) is False
    assert _should_skip_by_rule(10.5, rule_min) is False
    assert _should_skip_by_rule(10.0, rule_min) is True

    rule_max = {"max": 20.0}
    assert _should_skip_by_rule(15, rule_max) is False
    assert _should_skip_by_rule(20.0, rule_max) is False
    assert _should_skip_by_rule(20.1, rule_max) is True

    rule_range = {"min": 5, "max": 10}
    assert _should_skip_by_rule(7, rule_range) is False
    assert _should_skip_by_rule(4, rule_range) is True
    assert _should_skip_by_rule(11, rule_range) is True

    # Invalid numeric conversion should not raise exception, just pass (isnot skipped)
    assert _should_skip_by_rule("not-a-number", rule_range) is False
    assert _should_skip_by_rule(None, rule_range) is False


def test_message_filter_from_file(tmp_path):
    config_data = {
        "filters": {
            "pumpportal": {
                "enabled": True,
                "protocol": {"include": ["pump-v1", "pump-v2"]},
                "details.isMayhem": {"exclude_if_true": True},
                "market_cap": {"min": 50.0, "max": 1000.0},
            },
            "disabled_source": {
                "enabled": False,
            },
        }
    }
    config_file = tmp_path / "filters.json"
    config_file.write_text(json.dumps(config_data))

    msg_filter = MessageFilter(config_path=config_file)

    assert msg_filter.is_enabled("pumpportal") is True
    assert msg_filter.is_enabled("disabled_source") is False
    assert msg_filter.is_enabled("non_existent") is True  # defaults to True

    # Test unknown source returns False (does not skip)
    assert msg_filter.should_skip("unknown", {"any": "data"}) is False

    # Test disabled source returns True (skips everything)
    assert msg_filter.should_skip("disabled_source", {"any": "data"}) is True

    # Test pumpportal messages
    # 1. Valid message
    msg_valid = {
        "protocol": "pump-v1",
        "details": {"isMayhem": False},
        "market_cap": 100.0,
    }
    assert msg_filter.should_skip("pumpportal", msg_valid) is False

    # 2. Invalid protocol (not in allowed list)
    msg_invalid_protocol = {
        "protocol": "raydium",
        "details": {"isMayhem": False},
        "market_cap": 100.0,
    }
    assert msg_filter.should_skip("pumpportal", msg_invalid_protocol) is True

    # 3. Mayhem is True -> matches exclude_if_true
    msg_mayhem = {
        "protocol": "pump-v1",
        "details": {"isMayhem": True},
        "market_cap": 100.0,
    }
    assert msg_filter.should_skip("pumpportal", msg_mayhem) is True

    # 4. Market cap too low (< min)
    msg_low_cap = {
        "protocol": "pump-v1",
        "details": {"isMayhem": False},
        "market_cap": 10.0,
    }
    assert msg_filter.should_skip("pumpportal", msg_low_cap) is True
