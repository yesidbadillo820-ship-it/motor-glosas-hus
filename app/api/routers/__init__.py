from app.api.routers.auth_router import router as auth_router
from app.api.routers.glosas import router as glosas_router
from app.api.routers.contratos import router as contratos_router
from app.api.routers.analytics import router as analytics_router

__all__ = ["auth_router", "glosas_router", "contratos_router", "analytics_router"]
