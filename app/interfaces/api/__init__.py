from app.interfaces.api.workflow import router as workflow_router
from app.interfaces.api.scoring import router as scoring_router
from app.interfaces.api.reglas import router as reglas_router
from app.interfaces.api.async_tasks import router as async_router
from app.interfaces.api.usuarios import router as usuarios_router

__all__ = [
    "workflow_router",
    "scoring_router", 
    "reglas_router",
    "async_router",
    "usuarios_router",
]