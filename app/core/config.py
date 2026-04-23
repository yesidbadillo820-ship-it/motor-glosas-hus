import logging
import warnings
from pydantic_settings import BaseSettings
from functools import lru_cache

logger = logging.getLogger("motor_glosas")

_DEFAULT_SECRET = "dev-only-secret-key-change-in-production"
# Sentinel explícito: si el admin_password equivale a esto, significa
# que NO se ha configurado la variable de entorno. Cualquier uso en
# producción debe disparar warning + rechazar setear/login.
_UNCONFIGURED_ADMIN_PASSWORD = "CHANGEME_SET_ADMIN_PASSWORD_ENV_VAR"


class Settings(BaseSettings):
    # Base de datos
    database_url: str = "sqlite:///./glosas.db"

    # Seguridad JWT — Token de 1 hora según recomendaciones OWASP
    secret_key: str = _DEFAULT_SECRET
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60  # 1 hora (antes: 24h)

    # Contraseña admin inicial — DEBE definirse con env var ADMIN_PASSWORD.
    # Si queda con el sentinel, check_security_config() emite warning
    # explícito y el endpoint de reset rechaza cualquier valor débil.
    admin_password: str = _UNCONFIGURED_ADMIN_PASSWORD

    # Llaves de IA
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    # Cuál se usa primero: "groq" (rápido/barato) o "anthropic" (mejor calidad).
    # Si falla el primario y hay key del otro, se intenta el fallback.
    primary_ai: str = "groq"
    # Modelo Groq — default Llama 3.3 (estable, sin bucles degenerativos).
    # Otros modelos soportados (cambiar con env GROQ_MODEL):
    #   - "llama-3.3-70b-versatile"    (default, balanceado)
    #   - "llama-3.1-70b-versatile"    (alternativa previa)
    #   - "openai/gpt-oss-120b"        (más rápido/barato pero puede entrar en loops)
    #   - "mixtral-8x7b-32768"         (contexto largo)
    groq_model: str = "llama-3.3-70b-versatile"
    # Modelo Anthropic por defecto (Sonnet 4.6 — última generación)
    anthropic_model: str = "claude-sonnet-4-6"

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

    # Banner informativo en la UI (mantenimiento, capacitación, etc.)
    # Si está vacío no se muestra. Ejemplo de uso en Render:
    #   BANNER_CAPACITACION="Sistema en capacitación · Soporte: soporte@sinacsc.com"
    banner_capacitacion: str = ""

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
    
    if settings.secret_key == _DEFAULT_SECRET:
        warnings.warn(
            "ADVERTENCIA DE SEGURIDAD: Se está usando el SECRET_KEY por defecto. "
            "Define la variable de entorno SECRET_KEY con un valor aleatorio seguro "
            "(mínimo 32 caracteres) antes de desplegar en producción.",
            stacklevel=2,
        )
    
    if settings.admin_password == _UNCONFIGURED_ADMIN_PASSWORD:
        warnings.warn(
            "ADVERTENCIA DE SEGURIDAD: ADMIN_PASSWORD no configurada. "
            "Define la variable de entorno ADMIN_PASSWORD con una contraseña "
            "segura (mínimo 12 caracteres, con mayúsculas, números y símbolos) "
            "antes de usar en producción. Sin esto, el reset controlado del "
            "admin quedará deshabilitado.",
            stacklevel=2,
        )
    elif settings.admin_password in {"admin", "admin123", "password", "123456"}:
        warnings.warn(
            f"ADVERTENCIA DE SEGURIDAD: ADMIN_PASSWORD usa un valor débil "
            f"conocido. Cámbialo inmediatamente por una contraseña fuerte.",
            stacklevel=2,
        )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
