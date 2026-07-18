"""Runtime configuration for the ANSARI backend."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings, loaded from .env in local development."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"
    database_url: str = "postgresql+psycopg://ansari:ansari@localhost:5432/ansari"
    openai_api_key: str = ""


settings = Settings()
