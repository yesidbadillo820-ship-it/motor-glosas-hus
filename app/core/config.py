import os
import logging
from pydantic_settings import BaseSettings
from functools import lru_cache

logger = logging.getLogger("motor_glosas")


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

    # Configuración email SMTP para alertas
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alertas_email: str = ""

    # Metadatos de la app
    app_name: str = "Motor Glosas HUS"
    app_version: str = "5.4.0"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_allowed_origins(self) -> list[str]:
        """Retorna la lista de orígenes CORS permitidos."""
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


def check_security_config() -> None:
    """Verifica configuración de seguridad y emite advertencias."""
    settings = get_settings()
    
    if settings.secret_key == "dev-only-secret-key-change-in-production":
        logger.warning(
            "⚠️ SEGURIDAD: Usando SECRET_KEY por defecto en producción. "
            "Configure la variable de entorno SECRET_KEY con un valor seguro."
        )
    
    if settings.admin_password == "admin123":
        logger.warning(
            "⚠️ SEGURIDAD: Contraseña admin por defecto. "
            "Configure ADMIN_PASSWORD con una contraseña segura."
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
