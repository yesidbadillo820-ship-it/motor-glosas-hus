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
    # 480 min = jornada laboral de 8h. Con 60 min los gestores quedaban en
    # "sesión zombie" a mitad de turno: el panel seguía visible pero todos
    # los fetch devolvían 401 (visto en producción 10-jun-2026 — la página
    # de importar recepción mostraba "No se pudo cargar el historial (401)").
    # Sigue siendo overrideable con ACCESS_TOKEN_EXPIRE_MINUTES en el env.
    access_token_expire_minutes: int = 480
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
    # Modelos Groq para dictamenes — decision 16-jun-2026 (ronda 8 — dueño
    # pidió Llama 4 Maverick + banco de respuestas HUS como few-shots):
    #   1. meta-llama/llama-4-scout-17b-16e-instruct   PRIMARIO —
    #      Llama 4 (abr-2026), arquitectura 17B activos / 128 expertos MoE.
    #      Mejor seguidor de instrucciones largas (system + few-shots) que
    #      gpt-oss-120b; no es razonador con CoT (no agota max_tokens en
    #      razonamiento), respuesta directa. Soporta hasta 8M tokens
    #      contexto — perfecto para el banco de respuestas + contratos +
    #      datos clínicos en el prompt.
    #   2. openai/gpt-oss-120b      FALLBACK 1 — 120B MoE razonador, el
    #      primario anterior. Sigue útil para casos donde Llama no llegue.
    #   3. qwen/qwen3-32b           FALLBACK 2 — razonamiento en español.
    #   4. llama-3.3-70b-versatile  FALLBACK 3 — último recurso.
    # La cadena se aplica en GlosaService._llamar_groq_con_retry: si un
    # modelo falla (429 / error transitorio / deprecado) se prueba el
    # siguiente modelo Groq SIN saltar todavia a Anthropic. Overrideables
    # por env: GROQ_MODEL, GROQ_MODEL_FALLBACK_1, GROQ_MODEL_FALLBACK_2,
    # GROQ_MODEL_FALLBACK_3.
    groq_model: str = "meta-llama/llama-4-scout-17b-16e-instruct"
    groq_model_fallback_1: str = "openai/gpt-oss-120b"
    groq_model_fallback_2: str = "qwen/qwen3-32b"
    groq_model_fallback_3: str = "llama-3.3-70b-versatile"
    anthropic_model: str = "claude-sonnet-4-5"
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
    app_version: str = "5.5.0"
    banner_capacitacion: str = ""
    # Mejora #3 (jun-2026): salida estructurada incremental. Cuando está
    # ON, el LLM emite — además del envelope XML — un bloque
    # <CAMPOS_ESTRUCTURADOS>{...} con los 6 campos críticos ya validados
    # (eps, servicio, contrato, cláusulas, sanción, sub-conceptos). El
    # motor cruza ese JSON contra los valores DETERMINISTAS y, cuando
    # coinciden, se salta los sanitizers frágiles de ese campo. Default
    # OFF: con el flag apagado el pipeline es byte-idéntico al actual
    # (degradación elegante total). Override por env:
    # GLOSA_CAMPOS_ESTRUCTURADOS=true.
    glosa_campos_estructurados: bool = False

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
