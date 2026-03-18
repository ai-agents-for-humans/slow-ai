from pathlib import Path
from typing import Tuple, Type

from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_env_path = Path(__file__).parents[2] / ".env"


class Settings(BaseSettings):
    gemini_api_key: str
    perplexity_key: str
    model_config = SettingsConfigDict(
        env_file=str(_env_path),
        env_file_encoding="utf-8",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: Type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        **kwargs,
    ) -> Tuple[PydanticBaseSettingsSource, ...]:
        return (dotenv_settings,)


settings = Settings()
