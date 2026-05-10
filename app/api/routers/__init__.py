from app.api.routers.auth_router import router as auth_router
from app.api.routers.glosas import router as glosas_router
from app.api.routers.contratos import router as contratos_router
from app.api.routers.analytics import router as analytics_router

# Aplicar parche de fallback de PDFs (Anthropic -> Gemini PDF -> Gemini Vision).
# Necesario porque la IA dejo de leer PDFs cuando Anthropic falla: el codigo
# original descartaba los PDFs y caia a modo solo-texto, generando dictamenes
# genericos. El parche envuelve GlosaService._llamar_anthropic_multimodal y
# preserva los PDFs en cada nivel del fallback.
try:
    from app.services.pdf_fallback_patch import apply as _apply_pdf_patch
    _apply_pdf_patch()
except Exception as _e:  # pragma: no cover
    import logging
    logging.getLogger("motor_glosas").warning(
        f"pdf_fallback_patch no aplicado: {_e}"
    )

__all__ = ["auth_router", "glosas_router", "contratos_router", "analytics_router"]
