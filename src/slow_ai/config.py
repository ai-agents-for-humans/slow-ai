from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    gemini_api_key: str
    model_config =  SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8")


settings = Settings()
print(settings.gemini_api_key)
