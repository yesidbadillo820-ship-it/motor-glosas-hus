"""IA Auditora Proactiva — Pre-análisis automático de glosas pendientes.

Corre en background dentro del mismo proceso FastAPI (sin cron externo).
Se dispara por dos vías:
  1. Al startup, tarea asyncio que duerme hasta las 6:00 AM y luego cada 24h
  2. Endpoint manual POST /admin/pre-analisis para ejecutar bajo demanda

Para cada glosa pendiente (estado RADICADA/EN_REVISION sin dictamen):
  - Consulta la tarifa pactada (si es TA con CUPS)
  - Llama al motor de análisis solo si no hay match perfecto
  - Guarda el dictamen pre-generado en la BD
  - Cuando el gestor abre la glosa, el dictamen YA está listo

Beneficios:
  - Gestor abre el sistema en la mañana y ve las respuestas ya generadas
  - Llamadas IA se distribuyen en horas de baja demanda (6 AM)
  - Aprovecha caché persistente para glosas idénticas
  - Cero interacción humana requerida para análisis "obvios" (match perfecto)
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Optional

from app.core.logging_utils import logger
from app.database import SessionLocal
from app.models.db import GlosaRecord


# Estado global del scheduler
_SCHEDULER_TASK: Optional[asyncio.Task] = None
_ULTIMA_EJECUCION: Optional[datetime] = None
_EJECUCION_EN_CURSO: bool = False


def _segundos_hasta_proximas_6am() -> float:
    """Calcula segundos desde ahora hasta las próximas 6:00 AM."""
    ahora = datetime.now()
    objetivo = ahora.replace(hour=6, minute=0, second=0, microsecond=0)
    if objetivo <= ahora:
        objetivo += timedelta(days=1)
    return (objetivo - ahora).total_seconds()


async def _loop_pre_analisis():
    """Loop infinito que ejecuta pre-análisis una vez por día a las 6 AM.

    Resistente a excepciones: si una iteración falla, espera 1h y reintenta.
    No detiene el servidor bajo ninguna circunstancia.
    """
    # Primera espera: hasta las 6 AM del próximo día
    while True:
        try:
            espera_s = _segundos_hasta_proximas_6am()
            horas = espera_s / 3600
            logger.info(f"[PRE-ANALISIS] Próxima ejecución en {horas:.1f}h")
            await asyncio.sleep(espera_s)
            await ejecutar_pre_analisis_background()
        except asyncio.CancelledError:
            logger.info("[PRE-ANALISIS] Scheduler cancelado (shutdown)")
            break
        except Exception as e:
            logger.error(f"[PRE-ANALISIS] Error en loop: {e}. Reintentando en 1h.")
            await asyncio.sleep(3600)


async def ejecutar_pre_analisis_background(limite: int = 20) -> dict:
    """Corre el pre-análisis de forma segura, serializada.

    Solo una ejecución a la vez (flag _EJECUCION_EN_CURSO). Si ya hay una
    corriendo, retorna inmediatamente sin duplicar trabajo.

    Retorna estadísticas: cuántas procesó, cuántas saltó, cuántas fallaron.
    """
    global _ULTIMA_EJECUCION, _EJECUCION_EN_CURSO
    if _EJECUCION_EN_CURSO:
        return {"skip": "ya hay ejecución en curso"}
    _EJECUCION_EN_CURSO = True
    try:
        stats = await _procesar_glosas_pendientes(limite=limite)
        _ULTIMA_EJECUCION = datetime.now()
        logger.info(f"[PRE-ANALISIS] Completado: {stats}")
        return stats
    finally:
        _EJECUCION_EN_CURSO = False


async def _procesar_glosas_pendientes(limite: int = 20) -> dict:
    """Busca glosas sin dictamen generado y las pre-analiza.

    Criterio de candidatas:
      - estado IN ('RADICADA', 'EN_REVISION', 'BORRADOR')
      - dictamen IS NULL o vacío
      - creado_en dentro de los últimos 30 días
      - ordenadas por fecha_vencimiento ASC (las más urgentes primero)

    Retorna dict con estadísticas.
    """
    db = SessionLocal()
    procesadas = 0
    saltadas = 0
    fallidas = 0
    match_perfecto = 0
    try:
        hace_30d = datetime.now() - timedelta(days=30)
        candidatas = (
            db.query(GlosaRecord)
            .filter(
                GlosaRecord.estado.in_(["RADICADA", "EN_REVISION", "BORRADOR"])
            )
            .filter(GlosaRecord.creado_en >= hace_30d)
            .filter(
                (GlosaRecord.dictamen.is_(None))
                | (GlosaRecord.dictamen == "")
            )
            .order_by(
                GlosaRecord.fecha_vencimiento.asc().nullslast(),
                GlosaRecord.creado_en.desc(),
            )
            .limit(limite)
            .all()
        )
        if not candidatas:
            return {"procesadas": 0, "mensaje": "no hay glosas pendientes"}

        for g in candidatas:
            try:
                # Intento cero: si es RATIFICADA o EXTEMPORÁNEA, aplicar texto
                # fijo. No gasta tokens, respeta la regla de prioridad
                # (RATIFICADA gana sobre EXTEMPORÁNEA y nunca menciona
                # extemporaneidad si ambas aplican). Ronda 21.
                try:
                    from app.services.texto_fijo_detector import (
                        aplicar_texto_fijo_si_corresponde,
                    )
                    clase = aplicar_texto_fijo_si_corresponde(g)
                    if clase is not None:
                        db.commit()
                        match_perfecto += 1
                        procesadas += 1
                        logger.info(
                            f"[PRE-ANALISIS] Glosa {g.id} pre-rellenada como {clase['tipo']}"
                        )
                        continue
                except Exception as _e_tf:
                    logger.warning(f"[PRE-ANALISIS] Glosa {g.id} texto_fijo falló: {_e_tf}")
                    db.rollback()

                # Solo procesamos glosas con texto original disponible
                if not g.texto_glosa_original or len(g.texto_glosa_original) < 20:
                    saltadas += 1
                    continue
                # Intento rápido: match perfecto de tarifa (sin IA)
                from app.services.tarifa_lookup_service import evaluar_glosa_tarifa
                from app.main import _extraer_cups_servicio, _extraer_valores_glosa

                cups, _ = _extraer_cups_servicio(g.texto_glosa_original, "")
                if cups and (g.codigo_glosa or "").upper().startswith("TA"):
                    vals = _extraer_valores_glosa(g.texto_glosa_original)
                    info = evaluar_glosa_tarifa(
                        db, eps=g.eps or "", cups=cups,
                        valor_facturado=vals.get("facturado", 0.0),
                        valor_objetado=float(g.valor_objetado or 0.0),
                        valor_reconocido=vals.get("reconocido", 0.0),
                    )
                    if info.get("encontrada"):
                        rec = info.get("recomendacion") or {}
                        pact = info.get("valor_pactado_calc") or 0.0
                        fact = vals.get("facturado", 0.0)
                        # Match perfecto → plantilla determinística (0 tokens IA)
                        if (rec.get("accion") == "DEFENDER_TOTAL"
                                and pact > 0
                                and abs(fact - pact) < max(1.0, pact * 0.005)):
                            from app.services.glosa_service import generar_texto_tarifa_match
                            dictamen = generar_texto_tarifa_match(
                                codigo_glosa=g.codigo_glosa or "",
                                valor_objetado=float(g.valor_objetado or 0.0),
                                info_tarifa=info,
                            )
                            g.dictamen = dictamen
                            g.modelo_ia = "pre-analisis/texto_fijo"
                            db.commit()
                            match_perfecto += 1
                            procesadas += 1
                            continue
                # El resto se deja al análisis manual del auditor
                # (no invocamos IA aquí para no consumir tokens en background)
                saltadas += 1
            except Exception as e:
                fallidas += 1
                logger.warning(f"[PRE-ANALISIS] Glosa {g.id} falló: {e}")
                db.rollback()
                continue
        return {
            "procesadas": procesadas,
            "match_perfecto_sin_ia": match_perfecto,
            "saltadas": saltadas,
            "fallidas": fallidas,
            "timestamp": datetime.now().isoformat(),
        }
    finally:
        db.close()


def iniciar_scheduler() -> None:
    """Arranca el loop en segundo plano. Llamar desde lifespan/startup."""
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        return
    try:
        loop = asyncio.get_event_loop()
        _SCHEDULER_TASK = loop.create_task(_loop_pre_analisis())
        logger.info("[PRE-ANALISIS] Scheduler iniciado (6 AM diario)")
    except Exception as e:
        logger.warning(f"[PRE-ANALISIS] No se pudo iniciar scheduler: {e}")


def detener_scheduler() -> None:
    """Detiene el loop (para shutdown limpio)."""
    global _SCHEDULER_TASK
    if _SCHEDULER_TASK and not _SCHEDULER_TASK.done():
        _SCHEDULER_TASK.cancel()
    _SCHEDULER_TASK = None


def obtener_estado() -> dict:
    """Estado actual del scheduler para el endpoint admin."""
    return {
        "scheduler_activo": bool(_SCHEDULER_TASK and not _SCHEDULER_TASK.done()),
        "ejecucion_en_curso": _EJECUCION_EN_CURSO,
        "ultima_ejecucion": _ULTIMA_EJECUCION.isoformat() if _ULTIMA_EJECUCION else None,
    }
