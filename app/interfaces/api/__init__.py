from .glosas_router import router as glosas_router
from .contratos_router import router as contratos_router
from .auth_router import router as auth_router
from .analytics_router import router as analytics_router

__all__ = [
    "glosas_router", 
    "contratos_router", 
    "auth_router", 
    "analytics_router",
]