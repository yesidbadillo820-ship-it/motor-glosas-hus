import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

# R56 P1: trazabilidad request-scoped del usuario para que cualquier
# servicio (incluido glosa_service) pueda atribuir métricas al usuario
# sin tener que pasar el email a través de toda la cadena de llamadas.
user_email_var: ContextVar[str] = ContextVar("user_email", default="")
# glosa_id se setea cuando se crea la glosa en BD; calls IA posteriores
# del mismo request lo heredan automáticamente.
glosa_id_var: ContextVar[Optional[int]] = ContextVar("glosa_id", default=None)

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get(),
        }
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
