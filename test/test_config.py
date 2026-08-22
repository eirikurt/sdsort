import tomllib

from sdsort.config import Config


def test_load_config_from_toml():
    # Arrange
    toml = tomllib.loads("""
[tool.sdsort]
method-order = ["visibility", "dependency", "name"]
visibility-order = ["dunder", "public", "*"]
""")

    # Act
    config = Config.from_toml(toml)

    # Assert
    assert config.method_order == ["visibility", "dependency", "name"]
    assert config.visibility_order == ["dunder", "public", "*"]
