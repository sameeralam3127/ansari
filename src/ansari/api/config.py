from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ANSARI_", env_file=".env", extra="ignore")

    env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://ansari:ansari@localhost:5432/ansari"
    cors_origins: list[str] = ["http://localhost:3000"]
    github_token: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
