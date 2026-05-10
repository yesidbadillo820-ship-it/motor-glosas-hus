import logging
import warnings
from pydantic_settings import BaseSettings
from functools import lru_cache

logger = logging.getLogger("motor_glosas")

_DEFAULT_SECRET = "dev-only-secret-key-change-in-production"
_UNCONFIGURED_ADMIN_PASSWORD = "CHANGEME_SET_ADMIN_PASSWORD_ENV_VAR"


class Settings(BaseSettings):
    database_url: str = "sqlite:///./glosas.db"
    secret_key: str = _DEFAULT_SECRET
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    admin_password: str = _UNCONFIGURED_ADMIN_PASSWORD

    # Llaves de IA
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    # Google Gemini API key (tier gratis muy generoso: 15 RPM, 1500 RPD)
    # Conseguir en: https://aistudio.google.com/apikey
    gemini_api_key: str = ""
    # Cual se usa primero. Default "gemini" (gratis, calidad alta, lee PDFs nativos).
    # Tambien soportado: "anthropic" | "groq". El fallback automatico es:
    #   gemini    -> gemini -> anthropic -> groq
    #   anthropic -> anthropic -> gemini -> groq
    #   groq      -> gemini -> anthropic -> groq  (groq SIEMPRE ultimo recurso)
    primary_ai: str = "gemini"
    groq_model: str = "llama-3.3-70b-versatile"
    anthropic_model: str = "claude-sonnet-4-6"
    # Modelo Gemini por defecto (Flash 2.0 GA - gratis 15 RPM / 1500 RPD).
    # ATENCION: gemini-2.0-flash-exp fue deprecado cuando 2.0-flash paso a GA.
    # Modelos validos en v1beta (mayo 2026):
    #   - "gemini-2.0-flash"        (default, GA, balanceado)
    #   - "gemini-2.0-flash-lite"   (mas barato, mismo tier)
    #   - "gemini-2.5-flash"        (newer, mejor calidad)
    #   - "gemini-2.5-flash-lite"   (recomendado: sin thinking, rapido)
    #   - "gemini-2.5-pro"          (top calidad, 5 RPM/25 RPD free)
    #   - "gemini-1.5-flash"        (legacy estable)
    #   - "gemini-1.5-pro"          (legacy mejor calidad)
    gemini_model: str = "gemini-2.0-flash"

    allowed_origins: str = "http://localhost:3000,http://localhost:8000"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alertas_email: str = ""
    app_name: str = "Motor Glosas HUS"
    app_version: str = "5.4.0"
    banner_capacitacion: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


def check_security_config() -> None:
    settings = get_settings()
    if settings.secret_key == _DEFAULT_SECRET:
        warnings.warn(
            "ADVERTENCIA DE SEGURIDAD: Se esta usando el SECRET_KEY por defecto. "
            "Define la variable de entorno SECRET_KEY con un valor aleatorio seguro "
            "(minimo 32 caracteres) antes de desplegar en produccion.",
            stacklevel=2,
        )
    if settings.admin_password == _UNCONFIGURED_ADMIN_PASSWORD:
        warnings.warn(
            "ADVERTENCIA DE SEGURIDAD: ADMIN_PASSWORD no configurada.",
            stacklevel=2,
        )
    elif settings.admin_password in {"admin", "admin123", "password", "123456"}:
        warnings.warn(
            "ADVERTENCIA DE SEGURIDAD: ADMIN_PASSWORD usa un valor debil conocido.",
            stacklevel=2,
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
