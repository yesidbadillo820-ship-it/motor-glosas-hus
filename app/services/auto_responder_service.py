"""Auto-responder de glosas importadas masivamente.

Orquesta el procesamiento en background después de la importación
del Excel de recepción:

  Para cada glosa nueva:
    1. Aplica detector REQUIERE_SOPORTES (gratis, sin tokens)
       • Si requiere → marca estado=REQUIERE_SOPORTES, guarda
         dictamen-placeholder con la lista de soportes a aportar.
       • Si NO requiere → llama al cerebro IA (Haiku/Sonnet/Opus
         según routing) para generar dictamen completo.

  Concurrencia: hasta 3 glosas en paralelo (semáforo asyncio).
  Resiliente: si una glosa falla, el resto sigue procesando.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Límite de glosas procesadas en paralelo. Considera dos restricciones:
#   1. Rate-limit Anthropic (3-5 paralelas seguro para Claude Sonnet)
#   2. Memoria del proceso (Render Free = 512 MB). Cada call IA mantiene en
#      memoria el prompt + respuesta + PDFs decodificados; con 3 paralelas
#      llegamos a OOM kills. Bajamos a 2 para reducir picos.
_MAX_CONCURRENCIA = 2
_SEMAFORO = asyncio.Semaphore(_MAX_CONCURRENCIA)


async def procesar_glosa_id(glosa_id: int) -> dict:
    """Procesa una sola glosa en una NUEVA sesión DB.

    Retorna {'glosa_id', 'estado', 'modelo', 'requirio_soportes'}.
    Idempotente: si la glosa ya tiene dictamen real (no placeholder),
    no la re-procesa.
    """
    from app.database import SessionLocal
    from app.models.db import GlosaRecord
    from app.services.detector_requiere_soportes import (
        evaluar,
        mensaje_para_dictamen,
    )

    db = SessionLocal()
    try:
        g = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
        if not g:
            return {"glosa_id": glosa_id, "estado": "NO_ENCONTRADA"}

        # Idempotencia: si ya tiene dictamen útil, no re-procesar
        dict_actual = (g.dictamen or "").strip()
        if (
            len(dict_actual) > 200
            and "PENDIENTE DE ANÁLISIS" not in dict_actual.upper()
            and "REQUIERE SOPORTES" not in dict_actual.upper()
        ):
            return {
                "glosa_id": glosa_id,
                "estado": "YA_PROCESADA",
                "modelo": g.modelo_ia,
            }

        # Auto-detección: ¿la factura tiene soportes en el servidor?
        # Si sí, el detector no marca REQUIERE_SOPORTES porque los PDFs
        # están disponibles para que la IA los referencie.
        soportes_count = 0
        try:
            from app.services.soportes_autodiscovery_service import get_indexer
            if g.factura:
                soportes_count = len(get_indexer().lookup(g.factura) or [])
        except Exception as e:
            logger.debug(
                f"[auto-responder] indexer lookup falló glosa={glosa_id}: {e}"
            )

        # Reglas pre-IA (gratis)
        evaluacion = evaluar(
            codigo_glosa=g.codigo_glosa,
            texto_glosa=(g.texto_glosa_original or g.dictamen or g.concepto_glosa or ""),
            contexto_pdf="",  # importación masiva no trae PDFs locales
            valor_objetado=float(g.valor_objetado or 0),
            cups=g.cups_servicio,
            soportes_servidor_count=soportes_count,
        )

        if soportes_count > 0:
            logger.info(
                f"[auto-responder] glosa={glosa_id} factura={g.factura} "
                f"tiene {soportes_count} soporte(s) en servidor — relajando "
                f"reglas de detector REQUIERE_SOPORTES"
            )

        if evaluacion["requiere"]:
            g.dictamen = mensaje_para_dictamen(
                evaluacion, codigo_glosa=g.codigo_glosa or "—",
            )
            g.estado = "REQUIERE_SOPORTES"
            g.modelo_ia = "detector_pre_ia"
            db.commit()
            return {
                "glosa_id": glosa_id,
                "estado": "REQUIERE_SOPORTES",
                "modelo": "detector_pre_ia",
                "requirio_soportes": True,
                "motivo": evaluacion.get("motivo", ""),
            }

        # Llamada al cerebro IA con los datos mínimos
        try:
            return await _ejecutar_ia_y_persistir(db, g)
        except Exception as e:
            logger.warning(
                f"[AUTO-RESPONDER] Glosa {glosa_id} falló en IA: {e}"
            )
            # En caso de error, dejar la glosa pendiente para el gestor
            return {
                "glosa_id": glosa_id,
                "estado": "ERROR",
                "error": str(e)[:200],
            }
    finally:
        db.close()


async def _ejecutar_ia_y_persistir(db, glosa) -> dict:
    """Llama al motor IA de glosa_service y guarda el dictamen en la
    glosa existente."""
    from app.services.glosa_service import GlosaService
    from app.models.schemas import GlosaInput

    eps = (glosa.eps or "").strip() or "OTRA / SIN DEFINIR"
    texto = (
        glosa.texto_glosa_original
        or glosa.dictamen
        or glosa.concepto_glosa
        or ""
    ).strip()
    if len(texto) < 15:
        return {
            "glosa_id": glosa.id,
            "estado": "TEXTO_INSUFICIENTE",
        }

    # Auto-detección de soportes en el servidor de archivos del HUS.
    # Si la factura ya tiene PDFs subidos (FEV, HEV, RIPS, etc.), se
    # mencionan en el contexto del prompt para que la IA pueda
    # referenciarlos por nombre en el dictamen ("conforme a la historia
    # clínica HEV_900006037_HUS487120.pdf radicada en el expediente").
    contexto_soportes = ""
    try:
        from app.services.soportes_autodiscovery_service import get_indexer
        if glosa.factura:
            soportes = get_indexer().lookup(glosa.factura)
            if soportes:
                tipos_unicos = sorted({s["tipo_codigo"] for s in soportes})
                ejemplos = [s["nombre_archivo"] for s in soportes[:5]]
                contexto_soportes = (
                    f"\n\n[SOPORTES EN EXPEDIENTE]\n"
                    f"La factura {glosa.factura} cuenta con {len(soportes)} "
                    f"soporte(s) radicado(s) en el servidor del HUS, tipos: "
                    f"{', '.join(tipos_unicos)}. Archivos: "
                    f"{', '.join(ejemplos)}"
                    f"{'...' if len(soportes) > 5 else ''}. "
                    f"Puedes referenciar estos soportes en el dictamen como "
                    f"prueba documental."
                )
    except Exception as e:
        logger.debug(f"[auto-responder] enriquecer contexto soportes falló: {e}")
        contexto_soportes = ""

    glosa_input = GlosaInput(
        eps=eps,
        etapa=glosa.etapa or "RESPUESTA",
        fecha_radicacion=None,
        fecha_recepcion=None,
        valor_aceptado=str(int(glosa.valor_aceptado or 0)),
        tabla_excel=texto + contexto_soportes,
        numero_factura=glosa.factura,
        numero_radicado=glosa.numero_radicado,
        tono="conciliador",
        modo_respuesta="defender",
    )

    from app.core.config import get_settings
    _cfg = get_settings()
    service = GlosaService(
        groq_api_key=_cfg.groq_api_key,
        anthropic_api_key=_cfg.anthropic_api_key,
        primary_ai=_cfg.primary_ai,
        anthropic_model=_cfg.anthropic_model,
        groq_model=_cfg.groq_model,
        gemini_api_key=_cfg.gemini_api_key,
        gemini_model=_cfg.gemini_model,
    )
    resultado = await service.analizar(glosa_input, contexto_pdf="")

    # Actualizar la glosa existente con el dictamen generado
    glosa.dictamen = resultado.dictamen
    glosa.modelo_ia = resultado.modelo_ia
    glosa.score = float(resultado.score or 0.0)
    if not glosa.codigo_glosa and resultado.codigo_glosa:
        glosa.codigo_glosa = resultado.codigo_glosa
    glosa.estado = "RESPONDIDA"
    glosa.workflow_state = "BORRADOR"  # gestor revisa antes de radicar
    db.commit()

    return {
        "glosa_id": glosa.id,
        "estado": "RESPONDIDA",
        "modelo": resultado.modelo_ia,
        "requirio_soportes": False,
    }


async def procesar_lote(glosa_ids: list[int]) -> dict:
    """Procesa un lote de glosas en paralelo controlado.

    Devuelve resumen agregado: cuántas auto-respondidas, cuántas
    REQUIERE_SOPORTES, cuántas con error.
    """
    if not glosa_ids:
        return {"total": 0, "respondidas": 0, "requieren_soportes": 0, "errores": 0}

    async def _con_semaforo(gid):
        async with _SEMAFORO:
            try:
                return await procesar_glosa_id(gid)
            except Exception as e:
                logger.error(f"[AUTO-RESPONDER] worker {gid}: {e}")
                return {"glosa_id": gid, "estado": "ERROR", "error": str(e)[:200]}

    resultados = await asyncio.gather(
        *[_con_semaforo(gid) for gid in glosa_ids],
        return_exceptions=False,
    )

    respondidas = sum(1 for r in resultados if r.get("estado") == "RESPONDIDA")
    req_soportes = sum(1 for r in resultados if r.get("estado") == "REQUIERE_SOPORTES")
    errores = sum(1 for r in resultados if r.get("estado") in ("ERROR", "TEXTO_INSUFICIENTE"))
    ya_procesadas = sum(1 for r in resultados if r.get("estado") == "YA_PROCESADA")

    logger.info(
        f"[AUTO-RESPONDER] Lote completo: {len(glosa_ids)} glosas, "
        f"respondidas={respondidas} requieren_soportes={req_soportes} "
        f"ya_procesadas={ya_procesadas} errores={errores}"
    )

    # Memoria (Render Free 512 MB): el `detalle` puede contener referencias
    # a dictámenes HTML grandes (varios KB c/u) × N glosas. En lotes de
    # 50-100 glosas eso son varios MB que no se liberan hasta que la
    # task background termine. Compactamos el detalle a solo los IDs
    # antes de devolver, y forzamos GC.
    detalle_compacto = [
        {"glosa_id": r.get("glosa_id"), "estado": r.get("estado")}
        for r in resultados
    ]
    del resultados
    try:
        import gc as _gc
        _gc.collect()
    except Exception as e:
        logger.debug(f"[auto-responder] gc.collect post-lote falló: {e}")

    return {
        "total": len(glosa_ids),
        "respondidas": respondidas,
        "requieren_soportes": req_soportes,
        "ya_procesadas": ya_procesadas,
        "errores": errores,
        "detalle": detalle_compacto,
    }


def lanzar_lote_background(glosa_ids: list[int]) -> None:
    """Crea una task asyncio que procesa el lote sin bloquear al caller.

    Pensado para ser llamado desde un endpoint FastAPI usando
    asyncio.create_task — el response al cliente se devuelve
    inmediatamente y el procesamiento corre en el event loop.
    """
    if not glosa_ids:
        return
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(procesar_lote(glosa_ids))
        logger.info(
            f"[AUTO-RESPONDER] Lote de {len(glosa_ids)} glosas encolado "
            "para auto-procesamiento"
        )
    except Exception as e:
        logger.error(f"[AUTO-RESPONDER] No se pudo lanzar lote: {e}")


async def procesar_lote_y_enviar_excel(
    glosa_ids: list[int],
    excel_original: bytes,
    resumen: dict,
) -> dict:
    """Procesa el lote IA y, al terminar, manda a cada gestor el Excel
    original anotado con las respuestas generadas.

    Pensado para correr en background tras `/glosas/importar-recepcion`.
    Abre su propia sesión DB para el email — la del endpoint ya cerró.
    """
    resultado_lote = await procesar_lote(glosa_ids)

    from app.database import SessionLocal
    from app.services.email_service import (
        enviar_excel_recepcion_con_respuestas,
    )

    db_email = SessionLocal()
    try:
        envio = await enviar_excel_recepcion_con_respuestas(
            resumen=resumen,
            excel_original=excel_original,
            glosa_ids=glosa_ids,
            db=db_email,
        )
        resultado_lote["excel_emails"] = envio
    except Exception as e:
        logger.error(
            f"[AUTO-RESPONDER] Falló el envío del Excel-respuesta: {e}"
        )
        resultado_lote["excel_emails"] = {"error": str(e)[:200]}
    finally:
        db_email.close()
    return resultado_lote


def lanzar_lote_y_enviar_excel_background(
    glosa_ids: list[int],
    excel_original: bytes,
    resumen: dict,
) -> None:
    """Variante de `lanzar_lote_background` que, al terminar el lote,
    dispara el envío del Excel-respuesta a cada gestor."""
    if not glosa_ids:
        return
    try:
        loop = asyncio.get_event_loop()
        loop.create_task(
            procesar_lote_y_enviar_excel(glosa_ids, excel_original, resumen)
        )
        logger.info(
            f"[AUTO-RESPONDER] Lote de {len(glosa_ids)} glosas encolado + "
            "envío Excel-respuesta programado para al terminar"
        )
    except Exception as e:
        logger.error(
            f"[AUTO-RESPONDER] No se pudo lanzar lote+excel: {e}"
        )
