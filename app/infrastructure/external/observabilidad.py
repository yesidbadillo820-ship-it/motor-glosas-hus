import logging
import json
import traceback
from datetime import datetime
from typing import Any, Optional
from functools import wraps
import uuid


class StructuredLogger:
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter())
            self.logger.addHandler(handler)
    
    def _build_context(self, extra: dict = None) -> dict:
        ctx = {
            "timestamp": datetime.utcnow().isoformat(),
            "service": "motor-glosas"
        }
        if extra:
            ctx.update(extra)
        return ctx
    
    def info(self, message: str, glosa_id: int = None, **kwargs):
        extra = self._build_context({"glosa_id": glosa_id, **kwargs})
        self.logger.info(message, extra=extra)
    
    def warning(self, message: str, glosa_id: int = None, **kwargs):
        extra = self._build_context({"glosa_id": glosa_id, **kwargs})
        self.logger.warning(message, extra=extra)
    
    def error(self, message: str, glosa_id: int = None, error: Exception = None, **kwargs):
        extra = self._build_context({
            "glosa_id": glosa_id,
            "error_type": type(error).__name__ if error else None,
            "traceback": traceback.format_exc() if error else None,
            **kwargs
        })
        self.logger.error(message, extra=extra)
    
    def debug(self, message: str, glosa_id: int = None, **kwargs):
        extra = self._build_context({"glosa_id": glosa_id, **kwargs})
        self.logger.debug(message, extra=extra)
    
    def log_analisis(self, glosa_id: int, eps: str, duracion_ms: float, exitoso: bool):
        self.info(
            f"Análisis de glosa {'completado' if exitoso else 'fallido'}",
            glosa_id=glosa_id,
            eps=eps,
            duracion_ms=duracion_ms,
            exitoso=exitoso
        )
    
    def log_workflow(self, glosa_id: int, estado_anterior: str, estado_nuevo: str, responsable_id: int = None):
        self.info(
            f"Workflow: {estado_anterior} -> {estado_nuevo}",
            glosa_id=glosa_id,
            estado_anterior=estado_anterior,
            estado_nuevo=estado_nuevo,
            responsable_id=responsable_id
        )


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "service": "motor-glosas"
        }
        
        if hasattr(record, "glosa_id"):
            log_obj["glosa_id"] = record.glosa_id
        if hasattr(record, "eps"):
            log_obj["eps"] = record.eps
        if hasattr(record, "error_type"):
            log_obj["error_type"] = record.error_type
        if hasattr(record, "traceback"):
            log_obj["traceback"] = record.traceback
        if hasattr(record, "duracion_ms"):
            log_obj["duracion_ms"] = record.duracion_ms
        
        return json.dumps(log_obj)


def with_trace(glosa_id: int = None):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = StructuredLogger("motor_glosas_v2")
            trace_id = str(uuid.uuid4())[:8]
            start = datetime.now()
            
            logger.info(
                f"[{trace_id}] Iniciando {func.__name__}",
                glosa_id=glosa_id,
                trace_id=trace_id,
                funcion=func.__name__
            )
            
            try:
                result = await func(*args, **kwargs)
                duracion = (datetime.now() - start).total_seconds() * 1000
                
                logger.info(
                    f"[{trace_id}] Completado {func.__name__}",
                    glosa_id=glosa_id,
                    trace_id=trace_id,
                    duracion_ms=round(duracion, 2),
                    exitoso=True
                )
                return result
            except Exception as e:
                duracion = (datetime.now() - start).total_seconds() * 1000
                logger.error(
                    f"[{trace_id}] Error en {func.__name__}",
                    glosa_id=glosa_id,
                    trace_id=trace_id,
                    duracion_ms=round(duracion, 2),
                    error=e
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = StructuredLogger("motor_glosas_v2")
            trace_id = str(uuid.uuid4())[:8]
            start = datetime.now()
            
            logger.info(
                f"[{trace_id}] Iniciando {func.__name__}",
                glosa_id=glosa_id,
                trace_id=trace_id,
                funcion=func.__name__
            )
            
            try:
                result = func(*args, **kwargs)
                duracion = (datetime.now() - start).total_seconds() * 1000
                
                logger.info(
                    f"[{trace_id}] Completado {func.__name__}",
                    glosa_id=glosa_id,
                    trace_id=trace_id,
                    duracion_ms=round(duracion, 2),
                    exitoso=True
                )
                return result
            except Exception as e:
                duracion = (datetime.now() - start).total_seconds() * 1000
                logger.error(
                    f"[{trace_id}] Error en {func.__name__}",
                    glosa_id=glosa_id,
                    trace_id=trace_id,
                    duracion_ms=round(duracion, 2),
                    error=e
                )
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


observabilidad_logger = StructuredLogger("motor_glosas_v2")
