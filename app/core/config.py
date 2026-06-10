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
    # Google Gemini API key — SOLO para OCR/lectura de PDFs escaneados
    # (pdf_service.extraer_con_ocr + cadena multimodal del
    # pdf_fallback_patch). NO genera dictamenes desde jun-2026.
    # Mantenerla configurada: sin ella, todo el OCR de PDFs escaneados
    # cae sobre Anthropic (quema creditos de Claude).
    # Conseguir en: https://aistudio.google.com/apikey
    gemini_api_key: str = ""
    # Proveedor primario de DICTAMENES. Jun-2026 (decision Yesid): la
    # cadena quedo en SOLO Groq (primario, gratis/rapido) + Anthropic
    # (calidad / casos complejos). Gemini y OpenRouter fueron retirados
    # del dictamen — "no las veo trabajando y de pago ya tenemos Claude".
    # Soportado: "groq" | "anthropic". Valores legacy "gemini"/
    # "openrouter" se normalizan a "groq" en GlosaService con un warning.
    # Cadena de fallback automatica:
    #   groq      -> groq -> anthropic
    #   anthropic -> anthropic -> groq
    primary_ai: str = "groq"
    groq_model: str = "llama-3.3-70b-versatile"
    anthropic_model: str = "claude-sonnet-4-6"
    # Modelo Gemini por defecto para OCR (Flash 2.0 GA - gratis 15 RPM /
    # 1500 RPD). ATENCION: gemini-2.0-flash-exp fue deprecado cuando
    # 2.0-flash paso a GA.
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
