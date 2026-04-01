from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Base de datos
    database_url: str = "postgresql://hus_user:password@localhost:5432/motor_glosas"

    # Seguridad
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # IA
    groq_api_key: str = ""
    anthropic_api_key: str = ""

    # App
    app_name: str = "Motor Glosas HUS"
    app_version: str = "5.0.0"
    debug: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()          # se instancia una sola vez en toda la app
def get_settings() -> Settings:
    return Settings()
