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
import hashlib
import logging
import os
import re

logger = logging.getLogger(__name__)

# Defensas anti-gasto IA (reportadas por el dueño 12-jun-2026 — un lote
# importado consumió $14.50 en 251 calls de claude-sonnet-4-6, agotando
# créditos Anthropic en respuestas que tenían plantilla o pudieron
# reutilizarse de glosas gemelas).
#
# IA_SOLO_COMPLEJAS=1 → el flujo masivo NO llama IA si la glosa clasifica
#   como SIMPLE o MEDIA. Solo COMPLEJA (ratificación, extemporánea, alto
#   valor, multi-código, EPS crítica, texto >800 chars) toca tokens.
#   Las restantes quedan en estado PENDIENTE_MANUAL.
# AUTO_RESPONDER_REUSAR_GEMELOS=1 (default ON) → busca una glosa previa
#   idéntica en (eps, codigo, valor, hash del texto) con dictamen
#   aprobado, y la reusa sin gastar tokens.
_IA_SOLO_COMPLEJAS = os.getenv("IA_SOLO_COMPLEJAS", "0").strip() in ("1", "true", "TRUE")
_AUTO_RESPONDER_REUSAR_GEMELOS = os.getenv("AUTO_RESPONDER_REUSAR_GEMELOS", "1").strip() in (
    "1",
    "true",
    "TRUE",
)


def _firma_concepto(texto: str) -> str:
    """Firma normalizada del texto de la glosa para detectar gemelas.

    Quita espacios extra, valores monetarios y números de factura — lo que
    cambia entre glosas del mismo concepto pero distinta factura. Lo que
    sobrevive: el concepto canónico y el motivo.
    """
    t = (texto or "").upper()
    t = re.sub(r"\$\s*[\d\.,]+", "$VAL", t)
    t = re.sub(r"\bHUS\d{6,}\b", "FAC", t)
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha256(t.encode()).hexdigest()[:24]


def _buscar_dictamen_gemelo(db, glosa, texto_glosa: str) -> dict | None:
    """Busca una glosa gemela ya analizada que sirva de cache.

    Criterio: misma EPS y mismo código de glosa, valor similar (±10%) y
    firma de texto idéntica. Solo glosas con estado RESPONDIDA/RADICADA y
    dictamen suficientemente largo (>=400 chars, descarta placeholders).
    """
    try:
        from app.models.db import GlosaRecord

        if not (glosa.eps and glosa.codigo_glosa):
            return None
        firma = _firma_concepto(texto_glosa)
        if not firma:
            return None
        val = float(glosa.valor_objetado or 0)
        # Tolerancia ±10% sobre el valor (si hay valor); si no hay valor,
        # se ignora ese filtro.
        rango_lo = val * 0.9 if val else 0
        rango_hi = val * 1.1 if val else float("inf")
        candidatos = (
            db.query(GlosaRecord)
            .filter(GlosaRecord.eps == glosa.eps)
            .filter(GlosaRecord.codigo_glosa == glosa.codigo_glosa)
            .filter(GlosaRecord.id != glosa.id)
            .filter(GlosaRecord.estado.in_(["RESPONDIDA", "RADICADA"]))
            .order_by(GlosaRecord.creado_en.desc())
            .limit(40)
            .all()
        )
        for c in candidatos:
            cv = float(c.valor_objetado or 0)
            if val and not (rango_lo <= cv <= rango_hi):
                continue
            if not c.dictamen or len(c.dictamen) < 400:
                continue
            texto_c = (
                getattr(c, "texto_glosa_original", "")
                or getattr(c, "observacion_eps", "")
                or getattr(c, "concepto_glosa", "")
                or ""
            )
            if _firma_concepto(texto_c) == firma:
                return {
                    "glosa_id": c.id,
                    "dictamen": c.dictamen,
                    "codigo_respuesta": c.codigo_respuesta,
                }
        return None
    except Exception as e:
        logger.debug(f"_buscar_dictamen_gemelo falló: {e}")
        return None


# Límite de glosas procesadas en paralelo. Considera dos restricciones:
#   1. Rate-limit Anthropic (3-5 paralelas seguro para Claude Sonnet)
#   2. Memoria del proceso (Render Free = 512 MB). Cada call IA mantiene en
#      memoria el prompt + respuesta + PDFs decodificados; con 3 paralelas
#      llegamos a OOM kills. Bajamos a 2 para reducir picos.
_MAX_CONCURRENCIA = 2
_SEMAFORO = asyncio.Semaphore(_MAX_CONCURRENCIA)

# Python 3.11+: `asyncio.create_task` sólo guarda referencia débil a la
# task. Si nadie más la referencia, el GC puede recolectarla antes de
# que termine — perdiendo el resultado sin warning. Mantenemos un set
# fuerte a nivel módulo y la sacamos al terminar (callback).
# Ver https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
_BG_TASKS: set[asyncio.Task] = set()


def _texto_glosa_para_ia(db, glosa) -> str:
    """Texto de la glosa que la IA debe LEER para responder.

    Prioridad:
      1. texto_glosa_original — el importador de recepción lo compila
         desde las hojas I/R (CONCEPTO real de la EPS: código, CUPS,
         valor y observación).
      2. Conceptos vinculados en BD (ConceptoGlosaRecord) — cubre glosas
         importadas antes de que el importador compilara el texto.
      3. concepto_glosa (descripción oficial del código).
      4. dictamen — último recurso (puede ser el placeholder "Pendiente
         de análisis...", por eso va al final; antes iba SEGUNDO y la IA
         de las glosas importadas leía el placeholder en vez del
         concepto de la EPS — bug reportado 2026-06-10).
    """
    texto = (glosa.texto_glosa_original or "").strip()
    if texto:
        return texto
    try:
        from app.services.recepcion_service import componer_texto_desde_conceptos

        texto = (componer_texto_desde_conceptos(db, glosa) or "").strip()
        if texto:
            return texto
    except Exception as e:
        logger.debug(f"[auto-responder] componer texto desde conceptos falló glosa={glosa.id}: {e}")
    return (glosa.concepto_glosa or "").strip() or (glosa.dictamen or "").strip()


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
            logger.debug(f"[auto-responder] indexer lookup falló glosa={glosa_id}: {e}")

        # Texto real de la glosa (conceptos de la EPS) — compartido entre
        # el detector pre-IA y la llamada al cerebro IA.
        texto_glosa_ia = _texto_glosa_para_ia(db, g)

        # Reglas pre-IA (gratis)
        evaluacion = evaluar(
            codigo_glosa=g.codigo_glosa,
            texto_glosa=texto_glosa_ia,
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
                evaluacion,
                codigo_glosa=g.codigo_glosa or "—",
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

        # ── Defensa anti-gasto IA (11-jun-2026, reporte del dueño) ──────
        # El import masivo estaba llamando a Claude para CADA glosa, incluso
        # las que tienen plantilla determinística disponible — el lote del
        # 12-jun consumió $14.50 en 251 calls de Sonnet y agotó créditos.
        # Tres capas gratis antes de la IA:

        # 1) Texto fijo (RATIFICADA / EXTEMPORÁNEA / DMBUG TA con tarifa
        #    pactada): plantilla determinística, 0 tokens.
        try:
            from app.services.texto_fijo_detector import aplicar_texto_fijo_si_corresponde

            tf = aplicar_texto_fijo_si_corresponde(g)
            if tf:
                g.dictamen = tf["dictamen_html"]
                g.estado = tf.get("estado_sugerido") or "RESPONDIDA"
                g.modelo_ia = tf["modelo_ia"]
                db.commit()
                logger.info(
                    f"[auto-responder] glosa={glosa_id} resuelta por texto fijo "
                    f"({tf['tipo']}) — 0 tokens IA"
                )
                return {
                    "glosa_id": glosa_id,
                    "estado": tf.get("estado_sugerido") or "RESPONDIDA",
                    "modelo": tf["modelo_ia"],
                }
        except Exception as _e_tf:
            logger.debug(f"[auto-responder] texto_fijo_detector falló glosa={glosa_id}: {_e_tf}")

        # 2) Reuso de dictamen GEMELO: glosa previa idéntica
        #    (eps, codigo_glosa, valor_objetado, hash del texto) con
        #    dictamen aprobado por QG y radicada o cerrada. Evita gastar
        #    IA en glosas repetitivas (DMBUG ratifica el mismo lote a
        #    distintas facturas, FOMAG recicla 10 plantillas, etc.).
        if _IA_SOLO_COMPLEJAS or _AUTO_RESPONDER_REUSAR_GEMELOS:
            gemelo = _buscar_dictamen_gemelo(db, g, texto_glosa_ia)
            if gemelo is not None:
                g.dictamen = gemelo["dictamen"]
                g.codigo_respuesta = gemelo["codigo_respuesta"] or g.codigo_respuesta
                g.modelo_ia = f"cache_gemela/{gemelo['glosa_id']}"
                g.estado = "RESPONDIDA"
                g.workflow_state = "BORRADOR"
                db.commit()
                logger.info(
                    f"[auto-responder] glosa={glosa_id} reusa dictamen de glosa "
                    f"gemela #{gemelo['glosa_id']} — 0 tokens IA"
                )
                return {
                    "glosa_id": glosa_id,
                    "estado": "REUSO_GEMELO",
                    "modelo": g.modelo_ia,
                }

        # 3) IA_SOLO_COMPLEJAS=1 (variable Fly): si esta glosa NO clasifica
        #    como COMPLEJA por el router (ratificación, extemporánea, alto
        #    valor, multi-código, texto largo, EPS crítica), se marca como
        #    "pendiente análisis manual" SIN gastar tokens. Solo las glosas
        #    realmente difíciles van a Claude.
        if _IA_SOLO_COMPLEJAS:
            try:
                from app.services.ia_router import enrutar
                from app.utils.moneda import parse_valor_cop

                d = enrutar(
                    eps=g.eps or "",
                    valor=float(g.valor_objetado or 0) or parse_valor_cop(texto_glosa_ia),
                    texto_glosa=texto_glosa_ia,
                    codigo_glosa=g.codigo_glosa or "",
                )
                if d.complejidad != "COMPLEJA":
                    g.dictamen = (
                        "<div style='background:#eef2ff;border-left:4px solid #4f46e5;"
                        "padding:16px;border-radius:8px;'>"
                        "<b>PENDIENTE DE ANÁLISIS MANUAL</b><br/>"
                        f"Clasificación: {d.complejidad}. La política institucional "
                        "(IA_SOLO_COMPLEJAS=1) reserva la IA para glosas complejas. "
                        "El gestor debe abrir esta glosa y analizarla manualmente o "
                        "marcar la EPS como crítica para forzar el análisis IA."
                        "</div>"
                    )
                    g.estado = "PENDIENTE_MANUAL"
                    g.modelo_ia = f"skip/IA_SOLO_COMPLEJAS/{d.complejidad}"
                    db.commit()
                    logger.info(
                        f"[auto-responder] glosa={glosa_id} salteada por "
                        f"IA_SOLO_COMPLEJAS (complejidad={d.complejidad}) — 0 tokens IA"
                    )
                    return {
                        "glosa_id": glosa_id,
                        "estado": "PENDIENTE_MANUAL",
                        "modelo": g.modelo_ia,
                    }
            except Exception as _e_sc:
                logger.debug(
                    f"[auto-responder] IA_SOLO_COMPLEJAS check falló glosa={glosa_id}: {_e_sc}"
                )

        # Llamada al cerebro IA con los datos mínimos
        try:
            return await _ejecutar_ia_y_persistir(db, g, texto=texto_glosa_ia)
        except Exception as e:
            logger.warning(f"[AUTO-RESPONDER] Glosa {glosa_id} falló en IA: {e}")
            # En caso de error, dejar la glosa pendiente para el gestor
            return {
                "glosa_id": glosa_id,
                "estado": "ERROR",
                "error": str(e)[:200],
            }
    finally:
        db.close()


async def _ejecutar_ia_y_persistir(db, glosa, texto: str | None = None) -> dict:
    """Llama al motor IA de glosa_service y guarda el dictamen en la
    glosa existente.

    `texto` es el texto de la glosa (conceptos EPS) ya resuelto por el
    caller; si viene None se recalcula con _texto_glosa_para_ia.
    """
    from app.services.glosa_service import GlosaService
    from app.models.schemas import GlosaInput

    eps = (glosa.eps or "").strip() or "OTRA / SIN DEFINIR"
    texto = (texto if texto is not None else _texto_glosa_para_ia(db, glosa)).strip()
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
        groq_model_fallback_1=_cfg.groq_model_fallback_1,
        groq_model_fallback_2=_cfg.groq_model_fallback_2,
        groq_model_fallback_3=getattr(_cfg, "groq_model_fallback_3", "llama-3.3-70b-versatile"),
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

    # PostHog: medir conversión real del auto-responder.
    try:
        from app.services.posthog_service import capture

        capture(
            event="lote_auto_responder_completo",
            distinct_id="auto-responder",
            properties={
                "total": len(glosa_ids),
                "respondidas": respondidas,
                "requieren_soportes": req_soportes,
                "ya_procesadas": ya_procesadas,
                "errores": errores,
                "tasa_respondidas": (round(respondidas / len(glosa_ids), 3) if glosa_ids else 0),
            },
        )
    except Exception:
        pass

    # Memoria (Render Free 512 MB): el `detalle` puede contener referencias
    # a dictámenes HTML grandes (varios KB c/u) × N glosas. En lotes de
    # 50-100 glosas eso son varios MB que no se liberan hasta que la
    # task background termine. Compactamos el detalle a solo los IDs
    # antes de devolver, y forzamos GC.
    detalle_compacto = [
        {"glosa_id": r.get("glosa_id"), "estado": r.get("estado")} for r in resultados
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


def _registrar_bg_task(task: asyncio.Task, etiqueta: str) -> asyncio.Task:
    """Guarda referencia fuerte a la task y loguea fallos no-capturados.

    Sin esto, Python 3.11+ puede recolectar la task antes de que termine
    porque create_task sólo guarda weakref. El callback la saca del set
    cuando termina (éxito o error) y deja registro si lanzó excepción
    no manejada — esos errores serían invisibles de otro modo.
    """
    _BG_TASKS.add(task)

    def _on_done(t: asyncio.Task) -> None:
        _BG_TASKS.discard(t)
        if t.cancelled():
            logger.warning(f"[AUTO-RESPONDER] Task {etiqueta} cancelada")
            return
        exc = t.exception()
        if exc is not None:
            logger.error(
                f"[AUTO-RESPONDER] Task {etiqueta} terminó con excepción "
                f"no capturada: {type(exc).__name__}: {exc}",
                exc_info=exc,
            )

    task.add_done_callback(_on_done)
    return task


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
        task = loop.create_task(procesar_lote(glosa_ids))
        _registrar_bg_task(task, f"procesar_lote({len(glosa_ids)})")
        logger.info(
            f"[AUTO-RESPONDER] Lote de {len(glosa_ids)} glosas encolado para auto-procesamiento"
        )
    except Exception as e:
        logger.error(f"[AUTO-RESPONDER] No se pudo lanzar lote: {e}")


def _actualizar_estado_recepcion(rec_id: int | None, envio: dict) -> None:
    """Actualiza ImportacionRecepcionRecord.estado según el resultado del
    envío (usa solo la columna `estado` ya existente — sin migración):
      ENVIADO          → al menos un correo salió y ningún gestor sin email
      PARCIAL          → salieron correos pero hubo gestores sin email
      SIN_DESTINATARIOS→ no salió ningún correo
    """
    if not rec_id:
        return
    try:
        from app.database import SessionLocal
        from app.models.db import ImportacionRecepcionRecord

        enviados = int(envio.get("enviados", 0) or 0)
        sin_email = envio.get("gestores_sin_email") or []
        if enviados <= 0:
            nuevo = "SIN_DESTINATARIOS"
        elif sin_email:
            nuevo = "PARCIAL"
        else:
            nuevo = "ENVIADO"
        s = SessionLocal()
        try:
            rec = (
                s.query(ImportacionRecepcionRecord)
                .filter(ImportacionRecepcionRecord.id == rec_id)
                .first()
            )
            # No pisar SIN_ARCHIVO (prune) — solo si sigue en LISTO.
            if rec and rec.estado in ("LISTO", "PARCIAL", "SIN_DESTINATARIOS"):
                rec.estado = nuevo
                s.commit()
                logger.info(
                    f"[EXCEL-EMAIL] rec_id={rec_id} estado→{nuevo} "
                    f"(enviados={enviados}, sin_email={len(sin_email)})"
                )
        finally:
            s.close()
    except Exception as e:
        logger.warning(f"[EXCEL-EMAIL] no se pudo actualizar estado rec_id={rec_id}: {e}")


async def procesar_lote_y_enviar_excel(
    glosa_ids: list[int],
    excel_original: bytes,
    resumen: dict,
    ids_ia: list[int] | None = None,
    rec_id: int | None = None,
) -> dict:
    """Procesa el lote IA y, al terminar, manda a cada gestor el Excel
    original anotado con las respuestas generadas.

    Pensado para correr en background tras `/glosas/importar-recepcion`.
    Abre su propia sesión DB para el email — la del endpoint ya cerró.

    Logging agresivo en cada checkpoint para que si falla en producción
    Fly logs muestre exactamente dónde se cayó (lote IA, generación del
    .xlsx, o envío SMTP).
    """
    # ids_ia = subconjunto a procesar con IA (creadas/actualizadas). Si es
    # None se usa glosa_ids (compat). En una reimportación 100% duplicada
    # ids_ia llega vacío: NO se re-corre la IA (los dictámenes ya existen)
    # pero el Excel-respuesta SÍ se envía con glosa_ids (todas las tocadas).
    if ids_ia is None:
        ids_ia = glosa_ids
    logger.info(
        f"[EXCEL-EMAIL] ➡️  start: glosa_ids={len(glosa_ids)}, "
        f"ids_ia={len(ids_ia)}, "
        f"excel_bytes={len(excel_original) if excel_original else 0}, "
        f"resumen.total={resumen.get('total', '?')}"
    )

    if ids_ia:
        try:
            resultado_lote = await procesar_lote(ids_ia)
            logger.info(
                f"[EXCEL-EMAIL] ✅ lote IA terminado: "
                f"{resultado_lote.get('respondidas', 0)} respondidas, "
                f"{resultado_lote.get('requieren_soportes', 0)} requieren soportes, "
                f"{resultado_lote.get('errores', 0)} errores"
            )
        except Exception as e:
            logger.error(
                f"[EXCEL-EMAIL] ❌ procesar_lote crasheó: {type(e).__name__}: {e}",
                exc_info=True,
            )
            # Intentamos seguir con el envío del Excel original aunque la IA
            # haya fallado — el gestor al menos recibe el archivo crudo.
            resultado_lote = {"total": len(ids_ia), "error_lote": str(e)[:200]}
    else:
        logger.info(
            "[EXCEL-EMAIL] ↪️  sin glosas para IA (reimportación duplicada): "
            "se omite el lote y se envía el Excel-respuesta con los "
            "dictámenes ya existentes"
        )
        resultado_lote = {"total": 0, "lote_omitido": True}

    from app.database import SessionLocal
    from app.services.email_service import (
        enviar_excel_recepcion_con_respuestas,
    )

    db_email = SessionLocal()
    try:
        logger.info("[EXCEL-EMAIL] ➡️  llamando enviar_excel_recepcion_con_respuestas")
        envio = await enviar_excel_recepcion_con_respuestas(
            resumen=resumen,
            excel_original=excel_original,
            glosa_ids=glosa_ids,
            db=db_email,
        )
        resultado_lote["excel_emails"] = envio
        logger.info(f"[EXCEL-EMAIL] ✅ envío terminó: {envio}")
        _actualizar_estado_recepcion(rec_id, envio)
    except Exception as e:
        logger.error(
            f"[EXCEL-EMAIL] ❌ enviar_excel_recepcion_con_respuestas crasheó: "
            f"{type(e).__name__}: {e}",
            exc_info=True,
        )
        resultado_lote["excel_emails"] = {"error": str(e)[:200]}
        if rec_id:
            try:
                from app.database import SessionLocal
                from app.models.db import ImportacionRecepcionRecord

                s = SessionLocal()
                try:
                    rec = (
                        s.query(ImportacionRecepcionRecord)
                        .filter(ImportacionRecepcionRecord.id == rec_id)
                        .first()
                    )
                    if rec and rec.estado == "LISTO":
                        rec.estado = "ERROR"
                        s.commit()
                finally:
                    s.close()
            except Exception:
                pass
    finally:
        db_email.close()
    return resultado_lote


def lanzar_lote_y_enviar_excel_background(
    glosa_ids: list[int],
    excel_original: bytes,
    resumen: dict,
    ids_ia: list[int] | None = None,
    rec_id: int | None = None,
) -> None:
    """Variante de `lanzar_lote_background` que, al terminar el lote,
    dispara el envío del Excel-respuesta a cada gestor.

    `glosa_ids`: TODAS las glosas tocadas (creadas+actualizadas+duplicadas)
    — se usan para construir el Excel-respuesta.
    `ids_ia`: subconjunto a procesar con IA. Si None == glosa_ids. Si llega
    vacío (reimportación 100% duplicada) NO se corre IA pero el Excel SÍ
    se envía. Esto corrige el bug por el que reimportar un Excel ya
    cargado no enviaba ningún correo a los gestores.
    """
    if ids_ia is None:
        ids_ia = glosa_ids
    if not glosa_ids:
        logger.warning(
            "[AUTO-RESPONDER] No se lanza lote+excel: glosa_ids vacío "
            "(la importación no tocó ninguna glosa)"
        )
        return
    if not excel_original:
        logger.warning(
            "[AUTO-RESPONDER] No se lanza lote+excel: excel_original vacío "
            "— se llamará al lote sin envío de Excel"
        )
        if ids_ia:
            lanzar_lote_background(ids_ia)
        return
    try:
        loop = asyncio.get_event_loop()
        task = loop.create_task(
            procesar_lote_y_enviar_excel(
                glosa_ids,
                excel_original,
                resumen,
                ids_ia,
                rec_id,
            )
        )
        _registrar_bg_task(
            task,
            f"procesar_lote_y_enviar_excel({len(glosa_ids)})",
        )
        logger.info(
            f"[AUTO-RESPONDER] {len(glosa_ids)} glosas tocadas "
            f"({len(ids_ia)} para IA) — Excel-respuesta programado "
            f"(excel={len(excel_original)} bytes)"
        )
    except Exception as e:
        logger.error(
            f"[AUTO-RESPONDER] No se pudo lanzar lote+excel: {type(e).__name__}: {e}",
            exc_info=True,
        )
