import logging
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional
from contextvars import ContextVar

# Redacción de secretos en mensajes de log (defensa en profundidad).
# El logger INFO de httpx escribe URLs completas; si una API key viaja
# como query param (p.ej. ?key=AIza... de Gemini) terminaba en texto
# plano en los logs de Fly — visto en producción el 10-jun-2026.
# Aunque los call sites ya usan headers, este filtro garantiza que
# cualquier futuro descuido no exponga credenciales.
_PAT_SECRETO_EN_TEXTO = re.compile(
    r"(?i)\b(key|api[_-]?key|apikey|token|password|secret|authorization)"
    r"(=|:\s*)([^\s&\"']{6,})"
)


def _redactar_secretos(texto: str) -> str:
    """Reemplaza el valor de parámetros sensibles por un marcador.

    "…?key=AIzaSyAZm7Hiq…" → "…?key=***REDACTADO***"
    Conserva los primeros 4 chars para poder correlacionar sin exponer.
    """
    if not texto:
        return texto

    def _sub(m: "re.Match[str]") -> str:
        valor = m.group(3)
        return f"{m.group(1)}{m.group(2)}{valor[:4]}***REDACTADO***"

    return _PAT_SECRETO_EN_TEXTO.sub(_sub, texto)


request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# R56 P1: trazabilidad request-scoped del usuario para que cualquier
# servicio (incluido glosa_service) pueda atribuir métricas al usuario
# sin tener que pasar el email a través de toda la cadena de llamadas.
user_email_var: ContextVar[str] = ContextVar("user_email", default="")
# glosa_id se setea cuando se crea la glosa en BD; calls IA posteriores
# del mismo request lo heredan automáticamente.
glosa_id_var: ContextVar[Optional[int]] = ContextVar("glosa_id", default=None)
# E00: IP de origen del request. La columna audit_log.ip existe desde siempre
# y estaba SIEMPRE en NULL, porque ninguna de las 68 llamadas a
# AuditRepository.registrar() la pasaba. Capturarla acá evita tocar 68 sitios
# y hace que "quién hizo qué" incluya "desde dónde".
client_ip_var: ContextVar[str] = ContextVar("client_ip", default="")


class StructuredFormatter(logging.Formatter):
    def format(self, record):
        # R80 P1: incluir glosa_id y user_email en cada log line si están
        # disponibles en el ContextVar request-scoped. Permite filtrar logs
        # de Render/Sentry por glosa o por usuario sin parsear strings.
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": _redactar_secretos(record.getMessage()),
            "request_id": request_id_var.get(),
        }
        # Solo emitir los campos opcionales si tienen valor (evita ruido)
        try:
            email = user_email_var.get()
            if email:
                log_obj["user_email"] = email
        except Exception:
            pass
        try:
            gid = glosa_id_var.get()
            if gid is not None:
                log_obj["glosa_id"] = gid
        except Exception:
            pass
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_obj)


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)

    return logging.getLogger("motor_glosas")


def get_request_id() -> str:
    return request_id_var.get()


def set_request_id(req_id: Optional[str] = None) -> str:
    req_id = req_id or str(uuid.uuid4())[:8]
    request_id_var.set(req_id)
    return req_id


logger = setup_logging()


def clave_para_log(clave: str | None) -> str:
    """Cómo se nombra una credencial en el registro, sin entregarla.

    09-09-2026, hallazgo de los análisis de código del auditor. El motor
    logueaba los primeros 10 caracteres de cada clave de IA («OK sk-ant-api03…»)
    y los primeros 8 de la de PostHog. En el arranque, y en un archivo que se
    comparte al depurar.

    Diez caracteres no dejan usar la clave, pero sí dicen **de qué proveedor
    es y de qué tipo** —«sk-ant-api03» es inconfundible—, y sobre todo:
    reducen a la mitad el trabajo de quien ya tenga una copia parcial. Una
    credencial no se publica «un poquito».

    Lo único que el registro necesita responder es si la clave ESTÁ. Eso se
    dice sin mostrar nada de ella.
    """
    if not clave or not str(clave).strip():
        return "AUSENTE"
    return "CONFIGURADA"


def huella_de_clave(clave: str | None) -> str:
    """Una huella corta y estable de una credencial, para usarla de índice.

    09-09-2026. Varias cachés se indexaban con `clave[:6]` — un pedazo literal
    de la credencial. Como índice funciona igual, pero deja el fragmento
    escrito en memoria y en cualquier volcado. Un hash sirve para lo mismo
    (distinguir una clave de otra) sin llevar nada de la clave adentro.
    """
    import hashlib

    if not clave or not str(clave).strip():
        return "sin-clave"
    return hashlib.sha256(str(clave).encode("utf-8")).hexdigest()[:12]
