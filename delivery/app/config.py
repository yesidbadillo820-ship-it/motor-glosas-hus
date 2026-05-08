import os
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Domicilios HUS — Panel de Operaciones"
    database_url: str = "sqlite:///./domicilios.db"
    secret_key: str = "cambia-esta-clave-en-produccion-please"
    access_token_expire_minutes: int = 60 * 12
    admin_email: str = "admin@delivery.app"
    admin_password: str = "admin1234"
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
