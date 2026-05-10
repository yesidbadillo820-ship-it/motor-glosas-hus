"""Patch en runtime que agrega fallback Anthropic -> Gemini PDF -> Gemini Vision
al metodo _llamar_anthropic_multimodal de GlosaService.

Resuelve el bug critico reportado por Yesid (HUS, mayo 2026): cuando subis
PDFs en analizar y Anthropic falla por sin creditos, el sistema descartaba
los PDFs y caia a texto plano (perdiendo 60% de la info y produciendo
dictamenes pobres genericos).

Con este patch: si Anthropic multimodal falla:
  1. Intenta Gemini PDF nativo (gratis, modelos 2.5-flash/2.5-pro)
  2. Si Gemini PDF falla (modelo lite no soporta PDF nativo), convierte
     los PDFs a imagenes PNG via pdfplumber y los manda como vision
  3. Solo si los 3 fallan, cae a texto plano

Se aplica desde app/api/routers/__init__.py al primer import de routers,
sin requerir modificar el archivo glosa_service.py (172KB).
"""
from __future__ import annotations
import logging

logger = logging.getLogger("motor_glosas")


def apply():
    """Aplica el monkey patch a GlosaService. Idempotente."""
    try:
        from app.services.glosa_service import GlosaService
    except Exception as e:
        logger.warning(f"[PDF-FALLBACK-PATCH] No se pudo importar GlosaService: {e}")
        return False

    if getattr(GlosaService, "_pdf_fallback_patch_applied", False):
        return True
    GlosaService._pdf_fallback_patch_applied = True

    if not hasattr(GlosaService, "_llamar_anthropic_multimodal"):
        logger.warning("[PDF-FALLBACK-PATCH] GlosaService no tiene _llamar_anthropic_multimodal")
        return False

    original = GlosaService._llamar_anthropic_multimodal

    async def _wrapped_multimodal(self, system, user, pdfs_raw):
        # Intento 1: Anthropic Claude (PDF nativo) — el original
        try:
            return await original(self, system, user, pdfs_raw)
        except Exception as e_anthropic:
            logger.warning(
                f"[PDF-FALLBACK] Anthropic multimodal fallo: {e_anthropic}. "
                f"Probando Gemini PDF nativo..."
            )

        gemini = getattr(self, "gemini", None)
        gemini_model = getattr(self, "gemini_model", "gemini-2.0-flash")

        if not gemini:
            logger.error("[PDF-FALLBACK] Sin Gemini disponible. Re-raise Anthropic error.")
            # Re-ejecutar el original para que el error suba
            return await original(self, system, user, pdfs_raw)

        # Intento 2: Gemini con PDF nativo (gratis)
        try:
            res = await gemini.completar_con_retry(
                system=system,
                user=user,
                modelo=gemini_model,
                temperature=0.2,
                max_tokens=3000,
                pdfs_raw=pdfs_raw,
            )
            logger.info(f"[PDF-FALLBACK] OK Gemini PDF nativo ({res[1]})")
            return res
        except Exception as e_gp:
            logger.warning(
                f"[PDF-FALLBACK] Gemini PDF nativo fallo: {e_gp}. "
                f"Probando Gemini Vision con imagenes..."
            )

        # Intento 3: Gemini Vision con PDFs convertidos a PNG
        try:
            from app.services.pdf_to_images import pdfs_a_imagenes_combinadas
            imagenes = pdfs_a_imagenes_combinadas(
                pdfs_raw, max_imagenes_total=20, dpi=130,
            )
            if not imagenes:
                logger.error("[PDF-FALLBACK] No se pudo convertir ningun PDF a imagen")
                return await original(self, system, user, pdfs_raw)
            res = await gemini.completar_con_retry(
                system=system,
                user=user,
                modelo=gemini_model,
                temperature=0.2,
                max_tokens=3000,
                imagenes_raw=imagenes,
            )
            logger.info(
                f"[PDF-FALLBACK] OK Gemini Vision ({res[1]}) con {len(imagenes)} "
                f"imagenes (de {len(pdfs_raw)} PDFs)"
            )
            return res
        except Exception as e_gi:
            logger.error(f"[PDF-FALLBACK] Gemini Vision tambien fallo: {e_gi}")

        # Si todos fallaron, re-raise via original (que volvera a fallar)
        return await original(self, system, user, pdfs_raw)

    GlosaService._llamar_anthropic_multimodal = _wrapped_multimodal
    logger.info(
        "[PDF-FALLBACK-PATCH] APLICADO: GlosaService.analizar() ahora hace "
        "fallback Anthropic -> Gemini PDF -> Gemini Vision (con imagenes) "
        "preservando los PDFs en cada nivel."
    )
    return True
