import tomllib

import pytest

from sdsort.config import Config, ConfigError


def test_load_config_from_toml():
    # Arrange
    toml = tomllib.loads("""
[tool.sdsort]
method-order = ["visibility", "call", "name"]
visibility-order = ["dunder", "public", "*"]
""")

    # Act
    config = Config.from_toml(toml)

    # Assert
    assert config.method_order == ["visibility", "call", "name"]
    assert config.visibility_order == ["dunder", "public", "*"]


def test_unknown_method_order_value_is_rejected():
    toml = tomllib.loads("""
[tool.sdsort]
method-order = ["visibility", "no-such-attribute"]
""")

    with pytest.raises(ConfigError, match="no-such-attribute"):
        Config.from_toml(toml)


def test_unknown_visibility_order_value_is_rejected():
    toml = tomllib.loads("""
[tool.sdsort]
method-order = ["visibility"]
visibility-order = ["dunder", "no-such-visibility"]
""")

    with pytest.raises(ConfigError, match="no-such-visibility"):
        Config.from_toml(toml)


def test_key_spelled_with_underscores_is_rejected():
    # sdsort reads "method-order". Spelled with an underscore, the key is not recognised, and
    # without this the whole table would silently do nothing.
    toml = tomllib.loads("""
[tool.sdsort]
method_order = ["call", "name"]
""")

    with pytest.raises(ConfigError, match="method_order"):
        Config.from_toml(toml)


def test_value_that_is_not_a_list_is_rejected():
    # Iterating a bare string would otherwise treat each of its characters as an entry.
    toml = tomllib.loads("""
[tool.sdsort]
method-order = "call"
""")

    with pytest.raises(ConfigError, match="method-order.*must be a list"):
        Config.from_toml(toml)


def test_list_entry_that_is_not_a_string_is_rejected():
    toml = tomllib.loads("""
[tool.sdsort]
method-order = ["call", 3]
""")

    with pytest.raises(ConfigError, match="3"):
        Config.from_toml(toml)


def test_duplicate_values_are_rejected():
    toml = tomllib.loads("""
[tool.sdsort]
method-order = ["visibility", "call", "visibility"]
""")

    with pytest.raises(ConfigError, match="duplicate.*visibility"):
        Config.from_toml(toml)


def test_every_problem_is_reported_at_once():
    # Fixing a configuration one error per run would be tedious.
    toml = tomllib.loads("""
[tool.sdsort]
no-such-key = ["call"]
visibility-order = ["dunder", "no-such-visibility", "dunder"]
""")

    with pytest.raises(ConfigError) as raised:
        Config.from_toml(toml)

    message = str(raised.value)
    assert "no-such-key" in message, message
    assert "no-such-visibility" in message, message
    assert "duplicate" in message, message
