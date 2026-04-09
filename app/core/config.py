import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Base de datos
    database_url: str = "sqlite:///./glosas.db"

    # Seguridad JWT — Token de 1 hora según recomendaciones OWASP
    secret_key: str = "dev-only-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60  # 1 hora (antes: 24h)

    # Contraseña admin inicial — leer desde variable de entorno
    admin_password: str = "admin123"

    # Llaves de IA
    groq_api_key: str = ""
    anthropic_api_key: str = ""

    # CORS — lista de orígenes permitidos (en producción NO usar "*")
    allowed_origins: str = "http://localhost:3000,http://localhost:8000"

    # Metadatos de la app
    app_name: str = "Motor Glosas HUS"
    app_version: str = "5.1.0"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }

    def get_allowed_origins(self) -> list[str]:
        """Retorna la lista de orígenes CORS permitidos."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache()
def get_settings() -> Settings:
    return Settings()
