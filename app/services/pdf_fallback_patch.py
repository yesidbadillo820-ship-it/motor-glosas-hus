"""Monkey patch: cadena de fallback de PDFs para GlosaService.

Problema:
    El archivo glosa_service.py es demasiado grande (>100KB) para
    editarse via tooling MCP. Para corregir el bug critico "la IA
    deja de leer PDFs cuando Anthropic falla", aplicamos un parche
    en runtime que envuelve `_llamar_anthropic_multimodal` con una
    cadena de 3 niveles que PRESERVA los PDFs en cada nivel:

        Nivel A: Anthropic Claude (PDF nativo)
              -> si falla:
        Nivel B: Gemini Flash (PDF nativo, gratis)
              -> si falla:
        Nivel C: Gemini Vision (PDFs convertidos a PNGs)

    Solo si los 3 niveles fallan se levanta excepcion para que el
    caller decida (ej. cae a modo solo-texto).

Aplicacion:
    Llamar `apply()` una sola vez al iniciar la app (idempotente).
    Lo hace `app/api/routers/__init__.py` cuando los routers se
    cargan por primera vez.
"""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger("motor_glosas")

_FLAG = "_pdf_fallback_patch_applied"


def apply() -> bool:
    """Aplica el monkey patch. Retorna True si se aplico, False si ya estaba."""
    try:
        from app.services.glosa_service import GlosaService
    except Exception as e:
        logger.warning(f"[pdf_fallback_patch] no se pudo importar GlosaService: {e}")
        return False

    if getattr(GlosaService, _FLAG, False):
        return False

    original = GlosaService._llamar_anthropic_multimodal

    async def _llamar_anthropic_multimodal_con_fallback(
        self: Any,
        system: str,
        user: str,
        pdfs_raw: list[tuple[str, bytes]],
    ) -> tuple[str, str]:
        # ---- Nivel A: Anthropic Claude (PDF nativo) ----
        try:
            return await original(self, system, user, pdfs_raw)
        except Exception as e_a:
            logger.warning(f"[FALLBACK-A] Anthropic multimodal fallo: {e_a}")

        # ---- Nivel B: Gemini Flash con PDFs nativos ----
        gemini = getattr(self, "gemini", None)
        gemini_model = getattr(self, "gemini_model", None) or "gemini-2.0-flash"
        if gemini is not None:
            try:
                texto, modelo = await gemini.completar_con_retry(
                    system=system,
                    user=user,
                    modelo=gemini_model,
                    temperature=0.2,
                    max_tokens=3000,
                    pdfs_raw=pdfs_raw,
                )
                logger.info(f"[FALLBACK-B] Gemini PDF nativo OK ({modelo})")
                return texto, modelo
            except Exception as e_b:
                logger.warning(f"[FALLBACK-B] Gemini PDF nativo fallo: {e_b}")
        else:
            logger.warning("[FALLBACK-B] Gemini no disponible (sin api key)")

        # ---- Nivel C: Gemini Vision con PDFs -> imagenes PNG ----
        if gemini is not None:
            try:
                from app.services.pdf_to_images import pdfs_a_imagenes_combinadas
                imagenes = pdfs_a_imagenes_combinadas(
                    pdfs_raw, max_imagenes_total=20, dpi=130,
                )
                if not imagenes:
                    raise RuntimeError("conversion PDF->PNG vacia")
                texto, modelo = await gemini.completar_con_retry(
                    system=system,
                    user=user,
                    modelo=gemini_model,
                    temperature=0.2,
                    max_tokens=3000,
                    imagenes_raw=imagenes,
                )
                logger.info(
                    f"[FALLBACK-C] Gemini Vision OK con {len(imagenes)} imgs "
                    f"de {len(pdfs_raw)} PDFs ({modelo})"
                )
                return texto, modelo
            except Exception as e_c:
                logger.warning(f"[FALLBACK-C] Gemini Vision fallo: {e_c}")

        raise RuntimeError(
            "Cadena multimodal agotada: Anthropic + Gemini PDF + Gemini Vision fallaron"
        )

    GlosaService._llamar_anthropic_multimodal = _llamar_anthropic_multimodal_con_fallback
    setattr(GlosaService, _FLAG, True)
    logger.info("[pdf_fallback_patch] aplicado: A=Anthropic B=Gemini-PDF C=Gemini-Vision")
    return True
