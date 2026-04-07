import logging
import json
from datetime import datetime
from typing import Optional, Any
from functools import wraps
import time
import traceback


class JsonFormatter(logging.Formatter):
    """Formatter para logging estructurado en JSON"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        if hasattr(record, "glosa_id"):
            log_data["glosa_id"] = record.glosa_id
        
        if hasattr(record, "eps"):
            log_data["eps"] = record.eps
        
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


class ObservabilityService:
    """
    Servicio de observabilidad: logging estructurado, métricas y trazabilidad.
    """
    
    def __init__(self, name: str = "motor_glosas"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter())
            self.logger.addHandler(handler)
    
    def log_info(
        self,
        message: str,
        glosa_id: Optional[int] = None,
        eps: Optional[str] = None,
        **kwargs
    ):
        """Log informativo con contexto"""
        extra = {"glosa_id": glosa_id, "eps": eps}
        extra.update({k: v for k, v in kwargs.items() if v is not None})
        self.logger.info(message, extra=extra)
    
    def log_error(
        self,
        message: str,
        exception: Optional[Exception] = None,
        glosa_id: Optional[int] = None,
        eps: Optional[str] = None,
        **kwargs
    ):
        """Log de error con trazabilidad"""
        extra = {"glosa_id": glosa_id, "eps": eps}
        extra.update({k: v for k, v in kwargs.items() if v is not None})
        
        if exception:
            self.logger.error(f"{message}: {str(exception)}", extra=extra)
            self.logger.debug(traceback.format_exc())
        else:
            self.logger.error(message, extra=extra)
    
    def log_warning(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.warning(message, extra=extra)
    
    def log_debug(self, message: str, **kwargs):
        extra = {k: v for k, v in kwargs.items() if v is not None}
        self.logger.debug(message, extra=extra)


observability = ObservabilityService()


def log_ejecucion(func):
    """Decorador para logging automático de funciones"""
    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        start_time = time.time()
        glosa_id = kwargs.get("glosa_id") or (args[0] if args else None)
        
        observability.log_info(
            f"Iniciando {func.__name__}",
            glosa_id=glosa_id,
            function=func.__name__
        )
        
        try:
            result = await func(*args, **kwargs)
            duration = time.time() - start_time
            observability.log_info(
                f"Completado {func.__name__}",
                glosa_id=glosa_id,
                duration_ms=round(duration * 1000, 2),
                function=func.__name__
            )
            return result
        except Exception as e:
            duration = time.time() - start_time
            observability.log_error(
                f"Error en {func.__name__}",
                exception=e,
                glosa_id=glosa_id,
                duration_ms=round(duration * 1000, 2),
                function=func.__name__
            )
            raise
    
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        start_time = time.time()
        
        observability.log_info(
            f"Iniciando {func.__name__}",
            function=func.__name__
        )
        
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            observability.log_info(
                f"Completado {func.__name__}",
                duration_ms=round(duration * 1000, 2),
                function=func.__name__
            )
            return result
        except Exception as e:
            duration = time.time() - start_time
            observability.log_error(
                f"Error en {func.__name__}",
                exception=e,
                duration_ms=round(duration * 1000, 2),
                function=func.__name__
            )
            raise
    
    import asyncio
    if asyncio.iscoroutinefunction(func):
        return async_wrapper
    return sync_wrapper


class MetricsCollector:
    """Recolector de métricas simple"""
    
    def __init__(self):
        self._metrics = {
            "total_glosas": 0,
            "glosas_procesadas": 0,
            "glosas_extemporaneas": 0,
            "tiempo_respuesta_promedio_ms": 0,
            "glosas_por_estado": {},
            "glosas_por_eps": {},
        }
    
    def increment(self, metric: str, value: int = 1):
        if metric in self._metrics:
            self._metrics[metric] += value
    
    def set(self, metric: str, value: Any):
        self._metrics[metric] = value
    
    def get_all(self) -> dict:
        return self._metrics.copy()
    
    def get(self, metric: str) -> Any:
        return self._metrics.get(metric)


metrics = MetricsCollector()