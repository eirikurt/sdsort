default_config = {"x": 1}


class Settings:
    config: dict = default_config


settings = Settings()
config = settings.config or default_config
