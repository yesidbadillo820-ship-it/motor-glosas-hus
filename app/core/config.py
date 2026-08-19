import logging
import warnings
from pydantic import field_validator
from pydantic_settings import BaseSettings
from functools import lru_cache

logger = logging.getLogger("motor_glosas")

_DEFAULT_SECRET = "dev-only-secret-key-change-in-production"
_UNCONFIGURED_ADMIN_PASSWORD = "CHANGEME_SET_ADMIN_PASSWORD_ENV_VAR"


class Settings(BaseSettings):
    # Ronda 30: URL pública para los enlaces de los correos (antes había
    # hosts viejos y contradictorios: onrender.com y fly.dev).
    app_base_url: str = "https://iaglosassinac.help"
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
    # 05-08-2026: llama-4-scout SALIÓ del catálogo de Groq. El diagnóstico
    # del hospital devolvía «Error code: 404 — the model
    # meta-llama/llama-4-scout-17b-16e-instruct does not exist or you do not
    # have access to it», y el panel avisaba «ningún proveedor responde»
    # aunque el motor SÍ funcionaba: cada análisis gastaba un intento
    # muerto y caía al respaldo. Todos los dictámenes de ese día salieron
    # por gpt-oss-120b. Se promueve el que ya estaba haciendo el trabajo.
    groq_model: str = "openai/gpt-oss-120b"
    groq_model_fallback_1: str = "qwen/qwen3-32b"
    groq_model_fallback_2: str = "llama-3.3-70b-versatile"
    groq_model_fallback_3: str = "llama-3.1-8b-instant"
    anthropic_model: str = "claude-sonnet-4-5"
    # Modelo Gemini para OCR de PDF escaneados (no escribe dictamenes).
    #
    # 19-08-2026. Tercer modelo que se muere en este archivo: primero
    # gemini-2.0-flash-exp, despues gemini-2.0-flash («404 - is no longer
    # available. Please update»), igual que llama-4-scout en la cadena de
    # Groq. Cada vez, el OCR deja de funcionar en silencio y nadie se entera
    # hasta que un PDF escaneado no se lee.
    #
    # Se usa el ALIAS `gemini-flash-latest`, que Google mantiene apuntando al
    # Flash vigente. Para OCR el modelo exacto da igual; lo que importa es que
    # no se muera. Si alguna vez se necesita fijar uno, poner GEMINI_MODEL en
    # el .env con un nombre de la lista de `?key=...&models`.
    gemini_model: str = "gemini-flash-latest"

    allowed_origins: str = "http://localhost:3000,http://localhost:8000"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587

    @field_validator("smtp_port", mode="before")
    @classmethod
    def _smtp_port_vacio_usa_default(cls, v):
        """Incidente 3-jul-2026: docker-compose inyectó SMTP_PORT="" (string
        vacío) y Pydantic no parsea "" como int → la app moría al importar
        (crash-loop + 502 en producción). Un env vacío = no configurado."""
        if v is None or (isinstance(v, str) and not v.strip()):
            return 587
        return v

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

    # Token compartido del agente local de lotes (tools/agente_lotes.py).
    # El agente corre headless en el PC del hospital y no puede usar JWT
    # de usuario (expiran a las 8h): se autentica con este token estático
    # vía header X-Agente-Token. Vacío = endpoints del agente deshabilitados
    # (devuelven 503), así un deploy sin configurar no expone la cola.
    agente_lotes_token: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    def get_allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


class ConfiguracionInsegura(RuntimeError):
    """El arranque se aborta: hay una configuración que rompe la seguridad."""


def check_security_config() -> None:
    settings = get_settings()
    # E00: docker-compose inyecta SECRET_KEY: ${SECRET_KEY}; si la variable no
    # está en el .env, llega VACÍA y hasta ahora nadie lo detectaba — se
    # firmaban los tokens de sesión con cadena vacía. Esto no es una
    # advertencia: es motivo para no arrancar.
    clave = (settings.secret_key or "").strip()
    if not clave:
        raise ConfiguracionInsegura(
            "SECRET_KEY está vacía: los tokens de sesión se firmarían con una clave "
            "nula y cualquiera podría falsificarlos. Definí SECRET_KEY en el .env "
            "(mínimo 32 caracteres aleatorios) antes de arrancar."
        )
    if len(clave) < 32 and clave != _DEFAULT_SECRET:
        warnings.warn(
            "ADVERTENCIA DE SEGURIDAD: SECRET_KEY tiene menos de 32 caracteres.",
            stacklevel=2,
        )
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


# Claves que el resto del sistema busca en el ENTORNO del proceso, no en
# esta configuración. Sin este puente, un .env perfectamente válido dejaba
# la mitad del sistema a ciegas.
_CLAVES_AL_ENTORNO = (
    ("GROQ_API_KEY", "groq_api_key"),
    ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    ("GEMINI_API_KEY", "gemini_api_key"),
    ("PRIMARY_AI", "primary_ai"),
)


def _exportar_claves_al_entorno(settings: "Settings") -> None:
    """Publica al entorno del proceso lo que vino del archivo .env.

    Incidente 04-08-2026: pydantic-settings lee el .env hacia la
    configuración pero NO lo exporta a os.environ. El motor de dictámenes
    recibe las claves por inyección y funcionaba, pero el asistente, el
    auditor forense, el extractor de cláusulas, los multi-agentes y el
    diagnóstico de arranque leen os.getenv — y veían todo AUSENTE con un
    .env correcto. El log llegó a decir «groq=AUSENTE» teniendo la clave
    cargada, y eso mandó la búsqueda del problema por el camino errado.

    Nunca pisa una variable que ya venga del entorno real (docker/systemd
    mandan sobre el archivo).
    """
    import os as _os

    for nombre_env, campo in _CLAVES_AL_ENTORNO:
        if _os.environ.get(nombre_env):
            continue
        valor = getattr(settings, campo, "") or ""
        if valor:
            _os.environ[nombre_env] = valor


# Modelos que el proveedor ya retiró: responden 404 y dejan el OCR muerto en
# silencio. Se ignoran aunque el .env los mande, porque un archivo de
# configuración viejo en un PC no puede tumbar una herramienta.
#
# 19-08-2026. El .env del PC de cartera traía `gemini-2.0-flash`, retirado por
# Google. Con Anthropic además bloqueada por la red del hospital, eso dejaba al
# Auditor Forense sin ningún camino: su cadena de respaldo es Anthropic →
# Gemini PDF → Gemini Vision, y los tres estaban caídos. Corregir el .env a
# mano en cada máquina no es una solución; esto sí.
MODELOS_GEMINI_RETIRADOS = frozenset(
    {
        "gemini-2.0-flash",
        "gemini-2.0-flash-exp",
        "gemini-1.5-flash",
        "gemini-1.5-pro",
    }
)

# El alias que Google mantiene apuntando al Flash vigente.
GEMINI_VIVO = "gemini-flash-latest"


def modelo_gemini_vigente(pedido: str | None = None) -> str:
    """El modelo de Gemini que se va a usar de verdad, garantizado vivo.

    Recibe lo que diga la configuración (o None para tomarla) y devuelve eso
    mismo, SALVO que sea un modelo retirado — ahí devuelve el alias vigente y
    lo deja anotado en el registro, para que se vea por qué no se obedeció.
    """
    import logging

    valor = (pedido if pedido is not None else get_settings().gemini_model) or ""
    valor = valor.strip()
    if not valor:
        return GEMINI_VIVO
    if valor in MODELOS_GEMINI_RETIRADOS:
        logging.getLogger("motor_glosas").warning(
            "GEMINI_MODEL pide «%s», que el proveedor ya retiró (404). Se usa «%s». "
            "Corrija la línea GEMINI_MODEL del .env para quitar este aviso.",
            valor,
            GEMINI_VIVO,
        )
        return GEMINI_VIVO
    return valor


@lru_cache()
def get_settings() -> Settings:
    settings = Settings()
    _exportar_claves_al_entorno(settings)
    return settings
