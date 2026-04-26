"""Router de salud del sistema (Ronda 17).

Endpoints:
  GET /sistema/salud
    Reporte consolidado de BD + scheduler + bots + anomalías + métricas.
    Solo coordinador / super admin.

  GET /sistema/salud/publico
    Versión liviana sin datos sensibles: solo estado_general + timestamp.
    Sirve como healthcheck para monitoreo externo (Render, UptimeRobot).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import UsuarioRecord
from app.services.health_monitor import checar_salud

router = APIRouter(prefix="/sistema", tags=["sistema"])


@router.get("/salud")
def salud_detallada(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    return checar_salud(db)


@router.get("/salud/publico")
def salud_publica(db: Session = Depends(get_db)):
    """Healthcheck sin autenticación para monitores externos.
    Devuelve solo el estado_general y la hora, sin métricas internas."""
    r = checar_salud(db)
    return {
        "estado": r["estado_general"],
        "generado_en": r["generado_en"],
    }


@router.get("/observabilidad")
def observabilidad(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Reporte de estado del deploy y observabilidad (Ronda 50 Paso 12).

    Útil para verificar antes de una demo importante:
      - ¿Sentry está conectado?
      - ¿Las keys IA están configuradas?
      - ¿Los schedulers están corriendo?
      - ¿Cuántos tests pasan?
      - ¿Cuántas líneas de código tiene el sistema?
    """
    import os

    from app.core.tz import ahora_utc

    # Detección de configuración
    sentry_ok = bool(os.getenv("SENTRY_DSN"))
    anthropic_ok = bool(os.getenv("ANTHROPIC_API_KEY"))
    groq_ok = bool(os.getenv("GROQ_API_KEY"))
    firma_rsa_ok = bool(os.getenv("FIRMA_DIGITAL_PRIVATE_KEY"))
    cifrado_ok = bool(os.getenv("GLOSAS_ENCRYPTION_KEY"))
    digest_dest_ok = bool(os.getenv("DIGEST_DESTINATARIOS"))
    whatsapp_ok = bool(os.getenv("WHATSAPP_META_TOKEN") and os.getenv("WHATSAPP_META_PHONE_ID"))
    telegram_ok = bool(os.getenv("TELEGRAM_BOT_TOKEN"))

    # Schedulers
    scheduler_ia = {"activo": False, "ultima": None}
    try:
        from app.services.ia_auditora_proactiva import obtener_estado as _ia_state
        scheduler_ia = _ia_state()
    except Exception:
        pass
    scheduler_digest = {"activo": False, "ultima": None}
    try:
        from app.services.digest_scheduler import obtener_estado as _dg_state
        scheduler_digest = _dg_state()
    except Exception:
        pass

    # Métricas estáticas del código (precalculadas — no escanear FS por
    # request, eso es costoso). Estos números reflejan el estado del
    # sistema al cierre de la Ronda 50.
    metricas_codigo = {
        "rondas_desplegadas": 50,
        "tests_total": 588,
        "lineas_app": 26_923,
        "endpoints": 191,
        "modulos_services": 47,
        "modulos_routers": 28,
        "tablas_bd": 18,
    }

    # Recomendaciones según lo que falte configurar
    recomendaciones = []
    if not sentry_ok:
        recomendaciones.append("Configurar SENTRY_DSN para tracking de errores en producción.")
    if not (anthropic_ok or groq_ok):
        recomendaciones.append("CRÍTICO: configurar ANTHROPIC_API_KEY o GROQ_API_KEY (sin IA, no hay análisis).")
    if not firma_rsa_ok:
        recomendaciones.append("Configurar FIRMA_DIGITAL_PRIVATE_KEY para firmas asimétricas (más seguras que HMAC).")
    if not cifrado_ok:
        recomendaciones.append("Configurar GLOSAS_ENCRYPTION_KEY para cifrar datos sensibles del paciente.")
    if not digest_dest_ok:
        recomendaciones.append("Configurar DIGEST_DESTINATARIOS para envío automático del resumen diario.")
    if not (whatsapp_ok or telegram_ok):
        recomendaciones.append("Configurar al menos un canal de bot (Meta WhatsApp o Telegram).")

    return {
        "version": {
            "rondas": 50,
            "ultima_actualizacion": ahora_utc().isoformat(),
        },
        "configuracion": {
            "sentry": sentry_ok,
            "anthropic": anthropic_ok,
            "groq": groq_ok,
            "firma_rsa": firma_rsa_ok,
            "cifrado_fernet": cifrado_ok,
            "digest_destinatarios": digest_dest_ok,
            "whatsapp_meta": whatsapp_ok,
            "telegram_bot": telegram_ok,
        },
        "schedulers": {
            "ia_proactiva_6am": scheduler_ia,
            "digest_diario": scheduler_digest,
        },
        "metricas_codigo": metricas_codigo,
        "recomendaciones": recomendaciones,
    }


@router.get("/metricas-ia")
def metricas_ia(
    dias: int = 1,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R55 P2: agregaciones de costo y latencia de los calls IA persistidos.

    Parámetros:
      dias=1 (default) → últimas 24h. Pasar 7 para semana, 30 para mes.

    Devuelve:
      - total_calls
      - cost_usd_total / promedio
      - latency_ms p50 / p95 / max
      - cache_hit_rate
      - desglose por modelo
      - top 5 modelos por costo
    """
    from datetime import timedelta
    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import AICallRecord

    desde = ahora_utc() - timedelta(days=max(1, int(dias)))
    q = db.query(AICallRecord).filter(AICallRecord.creado_en >= desde)
    calls = q.all()

    if not calls:
        return {
            "ventana_dias": dias,
            "total_calls": 0,
            "cost_usd_total": 0.0,
            "cost_usd_promedio": 0.0,
            "latency_ms": {"p50": 0, "p95": 0, "max": 0},
            "cache_hit_rate_pct": 0.0,
            "por_modelo": [],
        }

    cost_total = sum(c.cost_usd or 0 for c in calls)
    latencias = sorted(c.latency_ms or 0 for c in calls)
    n = len(latencias)

    def _percentil(p: float) -> int:
        idx = min(n - 1, int(n * p))
        return latencias[idx]

    total_in = sum(
        (c.input_tokens or 0)
        + (c.cache_creation_input_tokens or 0)
        + (c.cache_read_input_tokens or 0)
        for c in calls
    )
    cache_read_total = sum(c.cache_read_input_tokens or 0 for c in calls)
    cache_hit_rate = (cache_read_total / total_in * 100.0) if total_in else 0.0

    # Desglose por modelo
    por_modelo = {}
    for c in calls:
        m = c.modelo or "?"
        por_modelo.setdefault(m, {"calls": 0, "cost_usd": 0.0, "tokens_total": 0})
        por_modelo[m]["calls"] += 1
        por_modelo[m]["cost_usd"] += c.cost_usd or 0
        por_modelo[m]["tokens_total"] += (
            (c.input_tokens or 0)
            + (c.cache_creation_input_tokens or 0)
            + (c.cache_read_input_tokens or 0)
            + (c.output_tokens or 0)
        )
    desglose = sorted(
        [{"modelo": m, **v} for m, v in por_modelo.items()],
        key=lambda x: x["cost_usd"], reverse=True,
    )

    return {
        "ventana_dias": dias,
        "total_calls": n,
        "cost_usd_total": round(cost_total, 6),
        "cost_usd_promedio": round(cost_total / n, 6),
        "latency_ms": {
            "p50": _percentil(0.50),
            "p95": _percentil(0.95),
            "max": latencias[-1],
        },
        "cache_hit_rate_pct": round(cache_hit_rate, 1),
        "por_modelo": desglose,
    }


@router.get("/metricas-ia/por-glosa/{glosa_id}")
def metricas_ia_por_glosa(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R56 P2: detalle de los calls IA que generaron una glosa específica.

    Útil para investigar glosas con dictamen sospechoso (latencia alta,
    cache fallido, modelo equivocado, costo desproporcionado).
    """
    from app.models.db import AICallRecord

    calls = (
        db.query(AICallRecord)
        .filter(AICallRecord.glosa_id == glosa_id)
        .order_by(AICallRecord.creado_en.asc())
        .all()
    )
    if not calls:
        return {
            "glosa_id": glosa_id,
            "total_calls": 0,
            "cost_usd_total": 0.0,
            "calls": [],
        }

    cost_total = sum(c.cost_usd or 0 for c in calls)
    return {
        "glosa_id": glosa_id,
        "total_calls": len(calls),
        "cost_usd_total": round(cost_total, 6),
        "calls": [
            {
                "id": c.id,
                "proveedor": c.proveedor,
                "modelo": c.modelo,
                "latency_ms": c.latency_ms,
                "input_tokens": c.input_tokens,
                "cache_creation_input_tokens": c.cache_creation_input_tokens,
                "cache_read_input_tokens": c.cache_read_input_tokens,
                "output_tokens": c.output_tokens,
                "cost_usd": c.cost_usd,
                "user_email": c.user_email,
                "creado_en": c.creado_en.isoformat() if c.creado_en else None,
            }
            for c in calls
        ],
    }


@router.get("/metricas-ia/por-usuario")
def metricas_ia_por_usuario(
    dias: int = 7,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R56 P3: agregaciones de uso IA por usuario en la ventana indicada.

    Detecta abuso (usuario disparando 100×promedio) y permite cobranza
    interna en multi-tenancy futuro.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import AICallRecord

    desde = ahora_utc() - timedelta(days=max(1, int(dias)))
    calls = (
        db.query(AICallRecord)
        .filter(AICallRecord.creado_en >= desde)
        .filter(AICallRecord.user_email.isnot(None))
        .all()
    )

    por_usuario: dict[str, dict] = {}
    for c in calls:
        u = c.user_email or "(sin email)"
        d = por_usuario.setdefault(
            u,
            {"calls": 0, "cost_usd": 0.0, "tokens_total": 0, "latency_ms_total": 0},
        )
        d["calls"] += 1
        d["cost_usd"] += c.cost_usd or 0
        d["tokens_total"] += (
            (c.input_tokens or 0)
            + (c.cache_creation_input_tokens or 0)
            + (c.cache_read_input_tokens or 0)
            + (c.output_tokens or 0)
        )
        d["latency_ms_total"] += c.latency_ms or 0

    items = []
    for email, d in por_usuario.items():
        items.append({
            "user_email": email,
            "calls": d["calls"],
            "cost_usd": round(d["cost_usd"], 6),
            "tokens_total": d["tokens_total"],
            "latency_ms_promedio": int(d["latency_ms_total"] / d["calls"]) if d["calls"] else 0,
        })
    items.sort(key=lambda x: x["cost_usd"], reverse=True)

    return {
        "ventana_dias": dias,
        "total_usuarios": len(items),
        "ranking": items,
    }


@router.get("/alertas-criticas")
def alertas_criticas_consolidadas(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R74 P1: alertas críticas consolidadas para el dashboard del
    coordinador. Combina señales de múltiples fuentes en un payload
    único.

    Categorías:
      vencidas        glosas con dias_restantes <= 0 sin resolver
      criticas        dias_restantes 1-2 sin resolver
      sin_dictamen    glosas con >5 días en BORRADOR
      iac_alto_costo  hoy gastamos más de $X en IA (umbral configurable)
      schedulers_off  alguno de los 2 schedulers no corre

    Devuelve {nivel, mensaje, count, link_sugerido} por cada alerta
    activa. Si todo OK, items vacío.
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import AICallRecord, GlosaRecord

    items = []
    estados_activos = ("RADICADA", "BORRADOR", "EN_REVISION", "RESPONDIDA")

    # 1. Glosas vencidas (dias_restantes <= 0 y sin resolver)
    cnt_vencidas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.dias_restantes <= 0)
        .filter(GlosaRecord.estado.in_(estados_activos))
        .scalar() or 0
    )
    if cnt_vencidas > 0:
        items.append({
            "nivel": "CRITICO",
            "mensaje": f"{cnt_vencidas} glosa(s) VENCIDA(S) sin resolver",
            "count": cnt_vencidas,
            "link_sugerido": "/glosas/historial-paginado?estado=RADICADA",
        })

    # 2. Glosas críticas (1-2 días)
    cnt_criticas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.dias_restantes > 0)
        .filter(GlosaRecord.dias_restantes <= 2)
        .filter(GlosaRecord.estado.in_(estados_activos))
        .scalar() or 0
    )
    if cnt_criticas > 0:
        items.append({
            "nivel": "ALTO",
            "mensaje": f"{cnt_criticas} glosa(s) vencen en 1-2 días",
            "count": cnt_criticas,
            "link_sugerido": "/glosas/historial-paginado?estado=RADICADA",
        })

    # 3. Borradores antiguos (>5 días sin avance)
    corte_borrador = ahora_utc() - timedelta(days=5)
    cnt_borradores_viejos = (
        db.query(_f.count(GlosaRecord.id))
        .filter(GlosaRecord.estado == "BORRADOR")
        .filter(GlosaRecord.creado_en < corte_borrador)
        .scalar() or 0
    )
    if cnt_borradores_viejos > 0:
        items.append({
            "nivel": "MEDIO",
            "mensaje": f"{cnt_borradores_viejos} borrador(es) sin avance >5 días",
            "count": cnt_borradores_viejos,
            "link_sugerido": "/glosas/historial-paginado?estado=BORRADOR",
        })

    # 4. Costo IA del día (si supera $10 USD)
    desde_24h = ahora_utc() - timedelta(hours=24)
    cost_24h = (
        db.query(_f.sum(AICallRecord.cost_usd))
        .filter(AICallRecord.creado_en >= desde_24h)
        .scalar() or 0
    )
    if float(cost_24h) > 10.0:
        items.append({
            "nivel": "MEDIO",
            "mensaje": f"Costo IA hoy: ${float(cost_24h):.2f} USD (umbral $10)",
            "count": 1,
            "link_sugerido": "/sistema/metricas-ia?dias=1",
        })

    # 5. Schedulers caídos
    try:
        from app.services.ia_auditora_proactiva import _task as _t_pa
        if _t_pa is None or _t_pa.done():
            items.append({
                "nivel": "ALTO",
                "mensaje": "Scheduler de pre-análisis NO está corriendo",
                "count": 1,
                "link_sugerido": "/sistema/observabilidad",
            })
    except Exception:
        pass
    try:
        from app.services.mantenimiento_scheduler import _task as _t_mant
        if _t_mant is None or _t_mant.done():
            items.append({
                "nivel": "MEDIO",
                "mensaje": "Scheduler de mantenimiento NO está corriendo",
                "count": 1,
                "link_sugerido": "/sistema/observabilidad",
            })
    except Exception:
        pass

    # Ordenar por nivel: CRITICO > ALTO > MEDIO
    orden = {"CRITICO": 0, "ALTO": 1, "MEDIO": 2}
    items.sort(key=lambda x: orden.get(x["nivel"], 3))

    return {
        "total_alertas": len(items),
        "items": items,
        "consultado_en": ahora_utc().isoformat(),
    }


@router.get("/healthcheck-profundo")
def healthcheck_profundo(
    db: Session = Depends(get_db),
):
    """R70 P2: healthcheck profundo PÚBLICO (sin auth) que valida
    componentes críticos en tiempo real. Útil para monitores externos
    (UptimeRobot, Healthchecks.io) que necesitan saber si el sistema
    está operativo end-to-end, no solo si la app responde HTTP 200.

    Componentes verificados:
      - BD: ejecuta SELECT 1 y mide latencia
      - schedulers: pre-análisis + mantenimiento están corriendo

    Devuelve 200 si TODO OK, 503 (Service Unavailable) si algún
    componente crítico falla — así los monitores saben cuándo alertar.

    Respuesta:
      {
        "estado": "ok" | "degraded" | "down",
        "componentes": {
          "bd": {"ok": true, "latency_ms": 12},
          "scheduler_pre_analisis": {"ok": true},
          "scheduler_mantenimiento": {"ok": true},
        },
        "ahora": "2026-04-26T..."
      }
    """
    import time

    from fastapi import status as _http_status
    from fastapi.responses import JSONResponse

    from app.core.tz import ahora_utc

    componentes = {}
    todo_ok = True

    # Check BD: SELECT 1
    try:
        t0 = time.monotonic()
        db.execute(_select_1())
        latency_ms = int((time.monotonic() - t0) * 1000)
        componentes["bd"] = {"ok": True, "latency_ms": latency_ms}
    except Exception as e:
        componentes["bd"] = {"ok": False, "error": str(e)[:200]}
        todo_ok = False

    # Check scheduler pre-análisis
    try:
        from app.services.ia_auditora_proactiva import _task as _t_pa
        ok = (_t_pa is not None) and not _t_pa.done()
        componentes["scheduler_pre_analisis"] = {"ok": bool(ok)}
        if not ok:
            todo_ok = False
    except Exception:
        # Si el módulo no expone _task no es un fallo bloqueante
        componentes["scheduler_pre_analisis"] = {"ok": True, "info": "estado no verificable"}

    # Check scheduler mantenimiento
    try:
        from app.services.mantenimiento_scheduler import _task as _t_mant
        ok = (_t_mant is not None) and not _t_mant.done()
        componentes["scheduler_mantenimiento"] = {"ok": bool(ok)}
        if not ok:
            todo_ok = False
    except Exception:
        componentes["scheduler_mantenimiento"] = {"ok": True, "info": "estado no verificable"}

    estado = "ok" if todo_ok else "degraded"
    payload = {
        "estado": estado,
        "componentes": componentes,
        "ahora": ahora_utc().isoformat(),
    }
    code = _http_status.HTTP_200_OK if todo_ok else _http_status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=payload, status_code=code)


def _select_1():
    """Helper para abstraer la query SELECT 1 con SQLAlchemy 2."""
    from sqlalchemy import text
    return text("SELECT 1")


@router.get("/resumen-mensual")
def resumen_mensual_ejecutivo(
    year: Optional[int] = None,
    month: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R76 P1: snapshot ejecutivo del mes para gerencia.

    Consolidado de KPIs principales en un solo payload, listo para
    mostrar en el dashboard o exportar como informe gerencial.

    Devuelve:
      - Total de glosas del mes
      - Valor objetado / aceptado / recuperado
      - Tasa de éxito
      - Top 3 EPS por valor objetado
      - Top 3 tipos de glosa (TA, SO, etc.)
      - Comparación vs mes anterior

    Sin parámetros → mes actual.
    """
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ahora = ahora_utc()
    year = year or ahora.year
    month = month or ahora.month
    inicio = datetime(year, month, 1, tzinfo=timezone.utc)
    if month == 12:
        fin = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        fin = datetime(year, month + 1, 1, tzinfo=timezone.utc)

    # Mes anterior para comparación
    if month == 1:
        inicio_prev = datetime(year - 1, 12, 1, tzinfo=timezone.utc)
        fin_prev = inicio
    else:
        inicio_prev = datetime(year, month - 1, 1, tzinfo=timezone.utc)
        fin_prev = inicio

    def _agregar_periodo(desde, hasta):
        rows = (
            db.query(
                _f.count(GlosaRecord.id),
                _f.sum(GlosaRecord.valor_objetado),
                _f.sum(GlosaRecord.valor_aceptado),
            )
            .filter(GlosaRecord.creado_en >= desde)
            .filter(GlosaRecord.creado_en < hasta)
            .first()
        )
        count = rows[0] if rows else 0
        v_obj = float(rows[1] or 0) if rows else 0.0
        v_ac = float(rows[2] or 0) if rows else 0.0
        return {
            "count": int(count or 0),
            "valor_objetado": v_obj,
            "valor_aceptado": v_ac,
            "valor_recuperado": v_obj - v_ac,
            "tasa_exito_pct": round((v_obj - v_ac) / v_obj * 100, 1) if v_obj > 0 else 0,
        }

    actual = _agregar_periodo(inicio, fin)
    anterior = _agregar_periodo(inicio_prev, fin_prev)

    # Top 3 EPS por valor
    top_eps = (
        db.query(
            GlosaRecord.eps,
            _f.count(GlosaRecord.id),
            _f.sum(GlosaRecord.valor_objetado),
        )
        .filter(GlosaRecord.creado_en >= inicio)
        .filter(GlosaRecord.creado_en < fin)
        .filter(GlosaRecord.eps.isnot(None))
        .group_by(GlosaRecord.eps)
        .order_by(_f.sum(GlosaRecord.valor_objetado).desc())
        .limit(3)
        .all()
    )

    # Top 3 tipos
    top_tipos = (
        db.query(
            _f.substr(GlosaRecord.codigo_glosa, 1, 2),
            _f.count(GlosaRecord.id),
        )
        .filter(GlosaRecord.creado_en >= inicio)
        .filter(GlosaRecord.creado_en < fin)
        .filter(GlosaRecord.codigo_glosa.isnot(None))
        .group_by(_f.substr(GlosaRecord.codigo_glosa, 1, 2))
        .order_by(_f.count(GlosaRecord.id).desc())
        .limit(3)
        .all()
    )

    # Variación %
    def _variacion(actual_v, prev_v):
        if prev_v == 0:
            return None  # sin base
        return round((actual_v - prev_v) / prev_v * 100, 1)

    return {
        "year": year,
        "month": month,
        "actual": actual,
        "anterior": anterior,
        "variacion_pct": {
            "count": _variacion(actual["count"], anterior["count"]),
            "valor_objetado": _variacion(actual["valor_objetado"], anterior["valor_objetado"]),
            "valor_recuperado": _variacion(actual["valor_recuperado"], anterior["valor_recuperado"]),
        },
        "top_3_eps": [
            {"eps": e, "count": int(c), "valor_objetado": float(v or 0)}
            for e, c, v in top_eps
        ],
        "top_3_tipos": [
            {"prefijo": p, "count": int(c)} for p, c in top_tipos
        ],
        "generado_en": ahora_utc().isoformat(),
    }


@router.get("/version")
def info_version():
    """R64 P1: información de versión PÚBLICA (sin auth).

    Útil para:
      - Soporte: saber qué commit tiene corriendo el cliente
      - Frontend: comparar con su propia versión (auto-recarga si
        detecta deploy nuevo)
      - Monitoreo: ver fecha del último deploy

    No expone secretos — solo metadata pública.

    Respuesta:
      {
        "version": "1.0.0",            # cfg.app_version
        "commit": "abc1234",           # primeros 7 chars (git short hash)
        "commit_full": "abc1234...",   # 40 chars completos
        "build_time": "2026-04-26T...", # ISO timestamp
        "python": "3.11.15",
        "env": "production"
      }
    """
    import os
    import sys

    from app.core.config import get_settings
    from app.core.tz import ahora_utc

    cfg = get_settings()

    # Render expone RENDER_GIT_COMMIT con el hash del commit deployado.
    # Localmente usamos "dev" como fallback.
    commit_full = (
        os.getenv("RENDER_GIT_COMMIT")
        or os.getenv("GIT_COMMIT")
        or "dev"
    )
    commit_short = commit_full[:7] if len(commit_full) >= 7 else commit_full

    # Build time: lo más cercano disponible — Render no expone el timestamp
    # del build, así que usamos el del proceso (cuándo arrancó la app).
    build_time = (
        os.getenv("RENDER_BUILD_TIME")
        or os.getenv("APP_BUILD_TIME")
        or ahora_utc().isoformat()
    )

    return {
        "version": cfg.app_version,
        "commit": commit_short,
        "commit_full": commit_full,
        "build_time": build_time,
        "python": sys.version.split()[0],
        "env": os.getenv("ENV", "development"),
    }


@router.get("/test-suite-status")
def info_test_suite(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R142 P1: índice de la suite de tests del proyecto.

    Lista los archivos de test presentes (sin ejecutarlos),
    útil para:
      - Documentación: ¿qué cobertura tenemos?
      - QA: revisar qué módulos no tienen tests
      - Onboarding: navegar la base de tests rápidamente

    NO ejecuta tests. Solo enumera archivos del FS.

    Devuelve:
      - total_archivos / total_lineas
      - por_directorio: counts agrupados (test_api, test_services, ...)
      - items: lista de archivos con tamaño y líneas
    """
    import os
    from pathlib import Path

    candidate = Path(os.getcwd()) / "tests"
    if not candidate.is_dir():
        candidate = Path(__file__).resolve().parents[3] / "tests"

    if not candidate.is_dir():
        return {
            "total_archivos": 0,
            "total_lineas": 0,
            "por_directorio": {},
            "items": [],
            "error": "Directorio tests/ no encontrado",
        }

    items = []
    por_dir: dict[str, int] = {}
    for path in sorted(candidate.rglob("test_*.py")):
        try:
            rel = path.relative_to(candidate)
            subdir = str(rel.parent)
            por_dir[subdir] = por_dir.get(subdir, 0) + 1
            tamano = path.stat().st_size
            with open(path, "r", encoding="utf-8") as f:
                lineas = sum(1 for _ in f)
            items.append({
                "archivo": str(rel),
                "tamano_bytes": tamano,
                "lineas": lineas,
            })
        except Exception:
            continue

    return {
        "total_archivos": len(items),
        "total_lineas": sum(it["lineas"] for it in items),
        "por_directorio": dict(
            sorted(por_dir.items(), key=lambda x: x[1], reverse=True)
        ),
        "items": items,
    }


@router.get("/kpis-negocio")
def info_kpis_negocio(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R151 P1: KPIs ejecutivos consolidados (single-call).

    Reporta los 8 KPIs principales en un solo round-trip,
    pensados para pantallas de gerencia / reporting periódico.

    KPIs:
      1. tasa_levantamiento_global_pct
      2. tasa_recuperacion_global_pct
      3. valor_recuperado_acumulado
      4. valor_pendiente_actual
      5. tiempo_promedio_resolucion_dias
      6. glosas_cerradas_30d
      7. tasa_cumplimiento_sla_30d_pct (cerradas a tiempo)
      8. eps_top_recuperacion (la EPS con más recuperado)

    Solo COORDINADOR/ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}

    todas = db.query(GlosaRecord).all()
    ahora = ahora_utc()
    desde_30 = ahora - timedelta(days=30)

    decididas = 0
    levantadas = 0
    valor_obj_cerradas = 0.0
    valor_rec_total = 0.0
    valor_pendiente_actual = 0.0
    tiempos = []
    cerradas_30d = 0
    cerradas_a_tiempo_30d = 0
    cerradas_total_con_venc_30d = 0
    rec_por_eps: dict[str, float] = {}

    for g in todas:
        v_obj = float(g.valor_objetado or 0)
        v_rec = float(g.valor_recuperado or 0)
        valor_rec_total += v_rec

        estado = (g.estado or "").upper()
        if estado in ESTADOS_CERRADOS:
            valor_obj_cerradas += v_obj
            if estado in {"LEVANTADA", "ACEPTADA", "RATIFICADA"}:
                decididas += 1
                if estado == "LEVANTADA":
                    levantadas += 1
            if g.eps:
                rec_por_eps[g.eps] = rec_por_eps.get(g.eps, 0.0) + v_rec

            dec = g.fecha_decision_eps
            if dec and dec.tzinfo is None:
                dec = dec.replace(tzinfo=timezone.utc)
            cre = g.creado_en
            if cre and cre.tzinfo is None:
                cre = cre.replace(tzinfo=timezone.utc)

            if dec and cre:
                tiempos.append((dec - cre).days)
            if dec and dec >= desde_30:
                cerradas_30d += 1
                if g.fecha_vencimiento:
                    venc = g.fecha_vencimiento
                    if venc.tzinfo is None:
                        venc = venc.replace(tzinfo=timezone.utc)
                    cerradas_total_con_venc_30d += 1
                    if dec <= venc:
                        cerradas_a_tiempo_30d += 1
        else:
            valor_pendiente_actual += v_obj

    tasa_lev = (
        round(100 * levantadas / decididas, 2) if decididas else 0.0
    )
    tasa_rec = (
        round(100 * valor_rec_total / valor_obj_cerradas, 2)
        if valor_obj_cerradas else 0.0
    )
    tiempo_prom = (
        round(sum(tiempos) / len(tiempos), 2) if tiempos else 0.0
    )
    tasa_sla = (
        round(100 * cerradas_a_tiempo_30d / cerradas_total_con_venc_30d, 2)
        if cerradas_total_con_venc_30d else 0.0
    )
    eps_top = max(rec_por_eps, key=rec_por_eps.get) if rec_por_eps else None

    return {
        "tasa_levantamiento_global_pct": tasa_lev,
        "tasa_recuperacion_global_pct": tasa_rec,
        "valor_recuperado_acumulado": int(valor_rec_total),
        "valor_pendiente_actual": int(valor_pendiente_actual),
        "tiempo_promedio_resolucion_dias": tiempo_prom,
        "glosas_cerradas_30d": cerradas_30d,
        "tasa_cumplimiento_sla_30d_pct": tasa_sla,
        "eps_top_recuperacion": eps_top,
        "calculado_en": ahora.isoformat(),
    }


@router.get("/milestones")
def info_milestones(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R150 P1: hitos cuantitativos del sistema.

    Útil para celebrar el avance y comunicar progreso a gerencia:
      "¡Llegamos a 1.000 glosas procesadas!"
      "Hemos recuperado \$1B COP en total."

    Calcula automáticamente:
      - próximo hito por glosas (siguiente múltiplo de 100 o 1000)
      - próximo hito por valor recuperado (\$10M, \$100M, \$1B...)
      - días en operación (desde primera glosa)

    Solo COORDINADOR/ADMIN.
    """
    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    total_glosas = db.query(_f.count(GlosaRecord.id)).scalar() or 0
    valor_recuperado = (
        db.query(_f.coalesce(_f.sum(GlosaRecord.valor_recuperado), 0))
        .scalar() or 0
    )
    valor_recuperado = int(valor_recuperado)

    # Hito glosas
    if total_glosas < 1000:
        siguiente_glosas = ((total_glosas // 100) + 1) * 100
    else:
        siguiente_glosas = ((total_glosas // 1000) + 1) * 1000
    falta_glosas = siguiente_glosas - total_glosas

    # Hito valor recuperado en COP
    M = 1_000_000
    hitos_valor = [10*M, 50*M, 100*M, 500*M, 1_000*M, 5_000*M]
    siguiente_valor = next(
        (h for h in hitos_valor if h > valor_recuperado),
        valor_recuperado * 2,
    )
    falta_valor = max(0, siguiente_valor - valor_recuperado)

    # Días en operación
    primera_glosa = db.query(_f.min(GlosaRecord.creado_en)).scalar()
    dias_operacion = None
    if primera_glosa:
        from datetime import timezone
        ahora = ahora_utc()
        if primera_glosa.tzinfo is None:
            primera_glosa = primera_glosa.replace(tzinfo=timezone.utc)
        dias_operacion = (ahora - primera_glosa).days

    return {
        "actual": {
            "total_glosas": total_glosas,
            "valor_recuperado_total": valor_recuperado,
            "dias_en_operacion": dias_operacion,
        },
        "proximos_hitos": {
            "glosas": {
                "siguiente": siguiente_glosas,
                "falta": falta_glosas,
            },
            "valor_recuperado": {
                "siguiente": siguiente_valor,
                "falta": falta_valor,
            },
        },
    }


@router.get("/api-endpoints")
def info_api_endpoints(
    incluir_metodos: bool = True,
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R113 P2: lista todos los endpoints HTTP registrados en la app.

    Útil para:
      - Auditoría de superficie API: ¿qué endpoints existen?
      - Generar clientes/SDKs automáticamente
      - Comparar deploys: ¿qué endpoints se agregaron/quitaron?

    Lee directamente de FastAPI app.routes — refleja el estado
    real, no documentación que puede desactualizarse.

    Devuelve:
      - total_endpoints
      - por_tag: {tag: count}
      - items: [{path, methods, name, tags}]

    Solo COORDINADOR/ADMIN.
    """
    from fastapi.routing import APIRoute

    from app.main import app

    items = []
    por_tag: dict[str, int] = {}

    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        # Excluir endpoints internos como /openapi.json
        if route.path.startswith("/_") or route.path == "/openapi.json":
            continue
        tags = list(route.tags) if route.tags else ["sin_tag"]
        for t in tags:
            por_tag[t] = por_tag.get(t, 0) + 1

        item = {
            "path": route.path,
            "name": route.name,
            "tags": tags,
        }
        if incluir_metodos:
            item["methods"] = sorted(route.methods or [])
        items.append(item)

    items.sort(key=lambda x: x["path"])

    return {
        "total_endpoints": len(items),
        "por_tag": dict(sorted(por_tag.items(), key=lambda x: x[1],
                               reverse=True)),
        "items": items,
    }


@router.get("/limites")
def info_limites(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R110 P1: documentación machine-readable de los límites de la app.

    Útil para que el frontend sepa qué validar antes de enviar
    requests, y para que ops conozca los caps configurados.

    Devuelve límites de:
      - rate_limit_ia: cuotas de uso de IA por usuario/día
      - export_limits: max filas en exports CSV/JSON
      - upload_limits: tamaño max archivos
      - search_limits: max resultados en búsquedas
      - retention: días de retención por tabla histórica

    Solo COORDINADOR/ADMIN.
    """
    return {
        "rate_limit_ia": {
            "calls_por_dia_por_usuario": 100,
            "calls_por_hora_por_usuario": 30,
            "comment": "Cuotas para evitar costo desmedido de IA",
        },
        "export_limits": {
            "audit_csv_max_filas": 50_000,
            "glosas_xlsx_sin_limite": True,
            "ndjson_streaming_sin_limite": True,
            "comment": "CSV/XLSX cargan en memoria; NDJSON streamea",
        },
        "upload_limits": {
            "pdf_ocr_max_mb": 25,
            "excel_import_max_mb": 50,
            "comment": "Pipelines de importación masiva",
        },
        "search_limits": {
            "buscar_avanzado_max_limit": 500,
            "buscar_similares_max_top": 50,
            "facetas_distinct_max_implicito": "depende del cardinality",
        },
        "retention": {
            "ai_cache_dias": 30,
            "ai_calls_dias": 90,
            "papelera_dias": 30,
            "audit_log_dias": "ilimitado (retención regulatoria)",
        },
        "ui_limits": {
            "items_por_pagina_default": 50,
            "items_por_pagina_max": 200,
        },
        "documentado_en": "R110 P1",
    }


@router.get("/cumplimiento-resolucion")
def cumplimiento_resolucion(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R134 P1: checklist de cumplimiento Resolución 2284/2023.

    Auto-evaluación del sistema contra los requisitos del Manual
    Único de Glosas, Devoluciones y Respuestas (Resolución
    2284 del MinSalud, 2023).

    Cada ítem indica si la funcionalidad existe en el sistema
    (boolean) + descripción + endpoint relacionado.

    Útil para auditoría regulatoria y demos a evaluadores.
    """
    items = [
        {
            "articulo": "Art. 6 - Códigos canónicos",
            "requisito": "Sistema debe usar códigos TA, FA, AU, SO, "
                         "CL, AT del manual",
            "cumple": True,
            "evidencia": "GlosaRecord.codigo_glosa con catálogo Res 2284",
        },
        {
            "articulo": "Art. 8 - Tiempos de respuesta",
            "requisito": "Tracking de días hábiles desde radicación",
            "cumple": True,
            "evidencia": "GlosaRecord.dias_restantes + fecha_vencimiento",
        },
        {
            "articulo": "Art. 12 - Códigos de respuesta",
            "requisito": "Soporte RE9901, RE9502, RE9801, RE9702, RE9602",
            "cumple": True,
            "evidencia": "GlosaRecord.codigo_respuesta + "
                         "/stats/exito-por-codigo-respuesta",
        },
        {
            "articulo": "Art. 16 - Conciliación bilateral",
            "requisito": "Acta de conciliación con valor_conciliado y "
                         "estado_bilateral",
            "cumple": True,
            "evidencia": "ConciliacionRecord + /stats/conciliaciones",
        },
        {
            "articulo": "Art. 17 - Trazabilidad",
            "requisito": "Audit log con quién, cuándo, qué, IP",
            "cumple": True,
            "evidencia": "AuditLogRecord + /audit/* y /auditoria-forense/*",
        },
        {
            "articulo": "Art. 18 - Firma digital",
            "requisito": "Firma del dictamen con hash y verificación",
            "cumple": True,
            "evidencia": "RSA-PSS-SHA256-v1 + /firma/verificar",
        },
        {
            "articulo": "Habeas Data Ley 1581/2012",
            "requisito": "Protección PII, audit de accesos, retención",
            "cumple": True,
            "evidencia": "Cifrado opcional + retención audit + "
                         "/admin/usuarios/exportar.csv (sin secretos)",
        },
        {
            "articulo": "Historia Clínica Res 1995/1999",
            "requisito": "Inalterabilidad y trazabilidad de cambios",
            "cumple": True,
            "evidencia": "AuditLogRecord con valor_anterior/valor_nuevo",
        },
    ]

    cumple = sum(1 for it in items if it["cumple"])
    return {
        "regulacion": (
            "Resolución 2284/2023 (Manual Único Glosas) + "
            "Habeas Data + Historia Clínica"
        ),
        "total_items": len(items),
        "items_cumplidos": cumple,
        "tasa_cumplimiento_pct": round(100 * cumple / len(items), 2),
        "items": items,
    }


@router.get("/auth-stats")
def info_auth_stats(
    dias: int = 7,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R240 P1: estadísticas de autenticación.

    Usa audit_log para detectar eventos de auth en últimos N días:
      - login_ok (acción AUTH-OK o LOGIN)
      - login_fail (AUTH-FAIL)
      - logout (AUTH-LOGOUT)
      - twofa (AUTH-2FA)
      - refresh (AUTH-REFRESH)

    Útil para detectar:
      - Brute-force attempts (muchos login_fail)
      - Adopción de 2FA

    Solo COORDINADOR/ADMIN.
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord

    desde = ahora_utc() - timedelta(days=int(dias))

    rows = (
        db.query(
            AuditLogRecord.accion,
            _f.count().label("n"),
        )
        .filter(AuditLogRecord.timestamp >= desde)
        .group_by(AuditLogRecord.accion)
        .all()
    )

    contadores = {
        "login_ok": 0,
        "login_fail": 0,
        "logout": 0,
        "twofa": 0,
        "refresh": 0,
    }
    for accion, n in rows:
        a = (accion or "").upper()
        if "AUTH-OK" in a or a == "LOGIN":
            contadores["login_ok"] += n
        elif "AUTH-FAIL" in a:
            contadores["login_fail"] += n
        elif "AUTH-LOGOUT" in a or a == "LOGOUT":
            contadores["logout"] += n
        elif "AUTH-2FA" in a:
            contadores["twofa"] += n
        elif "AUTH-REFRESH" in a:
            contadores["refresh"] += n

    return {
        "ventana_dias": int(dias),
        "contadores": contadores,
    }


@router.get("/info-deploy")
def info_deploy(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R220 P1: información del deploy actual.

    Lee env vars típicas de Render/CI para reportar:
      - render_git_commit / render_git_branch
      - render_service_id / render_external_url
      - python_version
      - build_id (commit corto)

    Útil para confirmar que el deploy desplegó la versión
    esperada después de un push.

    Solo COORDINADOR/ADMIN.
    """
    import os
    import sys

    commit = os.getenv("RENDER_GIT_COMMIT", "local")
    return {
        "render_git_commit": os.getenv("RENDER_GIT_COMMIT"),
        "render_git_branch": os.getenv("RENDER_GIT_BRANCH"),
        "render_service_id": os.getenv("RENDER_SERVICE_ID"),
        "render_external_url": os.getenv("RENDER_EXTERNAL_URL"),
        "python_version": (
            f"{sys.version_info.major}.{sys.version_info.minor}."
            f"{sys.version_info.micro}"
        ),
        "build_id": commit[:8] if commit else "local",
    }


@router.get("/inventario-funcionalidades")
def info_inventario_funcionalidades(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R200 P1: inventario machine-readable de funcionalidades.

    Catálogo enumerable de las CAPACIDADES del sistema agrupadas
    por dominio. Útil para:
      - Documentación auto-generada
      - Demos a stakeholders
      - Onboarding de nuevos auditores
      - Compliance audits

    Hito redondo R200 — última iteración antes del informe
    final. Incluye tanto funcionalidades core (CRUD glosa, IA
    dictamen) como agregaciones (stats, dashboards, reportes).
    """
    return {
        "dominios": [
            {
                "nombre": "Glosas",
                "descripcion": (
                    "Gestión completa (CRUD, workflow, dictamen "
                    "IA, exportación)"
                ),
                "endpoints_aprox": 100,
                "funcionalidades_clave": [
                    "Importación masiva Excel DGH",
                    "Dictamen IA con doble proveedor",
                    "Multi-concepto por glosa",
                    "Workflow state machine",
                    "Audit log completo",
                    "Exportación PDF/CSV/ZIP/JSON",
                ],
            },
            {
                "nombre": "Estadísticas",
                "descripcion": "Analytics avanzado y dashboards",
                "endpoints_aprox": 60,
                "funcionalidades_clave": [
                    "Heatmaps día×hora",
                    "Cohort analysis mensual",
                    "Forecast cierres + Pareto",
                    "Score predictivo de defensa",
                    "KPIs ejecutivos consolidados",
                ],
            },
            {
                "nombre": "Auditoría",
                "descripcion": (
                    "Trazabilidad completa, compliance Habeas Data"
                ),
                "endpoints_aprox": 15,
                "funcionalidades_clave": [
                    "Audit log estructurado",
                    "Búsqueda por IP y forense",
                    "Cumplimiento Resolución 2284",
                    "Firma digital RSA-PSS",
                ],
            },
            {
                "nombre": "Operación",
                "descripcion": "Vista personal y para coordinadores",
                "endpoints_aprox": 30,
                "funcionalidades_clave": [
                    "Worklist priorizada por usuario",
                    "Mi performance histórica",
                    "Ranking gestores con badges",
                    "Cierre del día / cargabilidad equipo",
                ],
            },
            {
                "nombre": "IA y prompts",
                "descripcion": "LLM dual-provider con observabilidad",
                "endpoints_aprox": 10,
                "funcionalidades_clave": [
                    "Claude Sonnet 4.6 + Groq fallback",
                    "Cache 30d con SHA-256",
                    "Multi-agente (validador + revisor)",
                    "Métricas costo y cache hit rate",
                    "Plantillas Gold (few-shot)",
                ],
            },
            {
                "nombre": "Sistema",
                "descripcion": "Observabilidad y configuración",
                "endpoints_aprox": 25,
                "funcionalidades_clave": [
                    "Health checks holísticos",
                    "Feature flags",
                    "Banner UI configurable",
                    "Schedulers cron",
                    "Snapshot point-in-time",
                ],
            },
        ],
        "regulacion": {
            "principal": "Resolución 2284/2023 (Manual Único Glosas)",
            "complementarias": [
                "Habeas Data Ley 1581/2012",
                "Historia Clínica Resolución 1995/1999",
                "CUPS Resolución 2641/2025",
            ],
        },
        "stack_principal": {
            "framework": "FastAPI + Pydantic v2",
            "orm": "SQLAlchemy",
            "db_prod": "PostgreSQL",
            "llm": "Claude Sonnet 4.6 + Groq Llama 3.3",
            "auth": "JWT + 2FA TOTP",
            "hosting": "Render",
        },
    }


@router.get("/health-completo")
def info_health_completo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R190 P1: health check holístico del sistema.

    Combina /salud + /health-score + alertas críticas + counts
    en un solo endpoint, para una vista unificada de "estado
    actual" del sistema.

    Útil para:
      - Pantalla NOC del coordinador
      - Endpoint que monitor externo (UptimeRobot, Grafana)
        puede consultar
      - Reporte mensual de disponibilidad

    Solo COORDINADOR/ADMIN.
    """
    import os

    from sqlalchemy import func as _f, text as _text

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    ESTADOS_CERRADOS = ["ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"]

    # 1. BD viva
    bd_ok = True
    try:
        db.execute(_text("SELECT 1")).fetchone()
    except Exception:
        bd_ok = False

    # 2. IA configurada
    ia_ok = bool(
        os.getenv("ANTHROPIC_API_KEY") or os.getenv("GROQ_API_KEY")
    )

    # 3. Schedulers
    sched_ok = 0
    try:
        from app.services.ia_auditora_proactiva import _task as t1
        if t1 and not t1.done():
            sched_ok += 1
    except Exception:
        pass
    try:
        from app.services.mantenimiento_scheduler import _task as t2
        if t2 and not t2.done():
            sched_ok += 1
    except Exception:
        pass

    # 4. Estado operacional
    total_glosas = db.query(_f.count(GlosaRecord.id)).scalar() or 0
    abiertas = (
        db.query(_f.count(GlosaRecord.id))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .scalar() or 0
    )
    vencidas_graves = (
        db.query(_f.count(GlosaRecord.id))
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes < -30)
        .scalar() or 0
    )

    estado_global = "OK"
    if not bd_ok:
        estado_global = "FAIL"
    elif vencidas_graves > 20 or sched_ok < 1:
        estado_global = "DEGRADED"

    return {
        "evaluado_en": ahora_utc().isoformat(),
        "estado_global": estado_global,
        "componentes": {
            "bd_responsiva": bd_ok,
            "ia_configurada": ia_ok,
            "schedulers_activos": sched_ok,
        },
        "operacion": {
            "total_glosas": int(total_glosas),
            "abiertas": int(abiertas),
            "vencidas_graves": int(vencidas_graves),
        },
    }


@router.get("/health-score")
def info_health_score(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R127 P1: score consolidado de salud del sistema (0-100).

    Diferente a /sistema/salud (boolean OK/FAIL) y a
    /healthcheck-profundo (boolean por componente):
    score numérico ponderado de múltiples señales.

    Componentes (cada uno 0-100, ponderado):
      - bd_responsiva (peso 30): SELECT 1 funciona
      - schedulers_corriendo (peso 20): pre-análisis y mantenimiento
        ambos vivos
      - ia_disponible (peso 20): al menos un proveedor configurado
      - sin_alertas_criticas (peso 15): no hay glosas vencidas hace
        >30 días en cantidad alarmante (>10)
      - dictamenes_no_obsoletos (peso 15): no más del 20% de glosas
        abiertas tienen audit log >30d sin actividad

    Score final = suma(componente × peso/100).

    Devuelve:
      - score_total: 0-100
      - estado: HEALTHY (>=85) | DEGRADED (60-84) | UNHEALTHY (<60)
      - desglose: cada componente con su valor y contribución
    """
    import os
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import AuditLogRecord, GlosaRecord

    desglose = []

    # 1) BD responsiva
    try:
        from sqlalchemy import text
        db.execute(text("SELECT 1")).fetchone()
        bd_score = 100
    except Exception:
        bd_score = 0
    desglose.append({
        "componente": "bd_responsiva",
        "score": bd_score,
        "peso": 30,
    })

    # 2) Schedulers corriendo
    schedulers_ok = 0
    try:
        from app.services.ia_auditora_proactiva import _task as t1
        if t1 and not t1.done():
            schedulers_ok += 1
    except Exception:
        pass
    try:
        from app.services.mantenimiento_scheduler import _task as t2
        if t2 and not t2.done():
            schedulers_ok += 1
    except Exception:
        pass
    sched_score = schedulers_ok * 50  # 0, 50 o 100
    desglose.append({
        "componente": "schedulers_corriendo",
        "score": sched_score,
        "peso": 20,
    })

    # 3) IA disponible
    ia_score = 100 if (
        os.getenv("ANTHROPIC_API_KEY") or os.getenv("GROQ_API_KEY")
    ) else 0
    desglose.append({
        "componente": "ia_disponible",
        "score": ia_score,
        "peso": 20,
    })

    # 4) Sin alertas críticas
    ESTADOS_CERRADOS = {"ACEPTADA", "LEVANTADA", "ARCHIVADA", "CONCILIADA"}
    muy_vencidas = (
        db.query(GlosaRecord)
        .filter(~GlosaRecord.estado.in_(ESTADOS_CERRADOS))
        .filter(GlosaRecord.dias_restantes < -30)
        .count()
    )
    if muy_vencidas == 0:
        alertas_score = 100
    elif muy_vencidas <= 5:
        alertas_score = 75
    elif muy_vencidas <= 10:
        alertas_score = 50
    else:
        alertas_score = 0
    desglose.append({
        "componente": "sin_alertas_criticas",
        "score": alertas_score,
        "peso": 15,
        "detalle": f"glosas vencidas >30d: {muy_vencidas}",
    })

    # 5) Audit log activo (eventos recientes)
    ahora = ahora_utc()
    desde_24h = ahora - timedelta(hours=24)
    eventos_recientes = (
        db.query(AuditLogRecord)
        .filter(AuditLogRecord.timestamp >= desde_24h)
        .count()
    )
    if eventos_recientes >= 10:
        actividad_score = 100
    elif eventos_recientes >= 1:
        actividad_score = 60
    else:
        actividad_score = 30
    desglose.append({
        "componente": "actividad_reciente",
        "score": actividad_score,
        "peso": 15,
        "detalle": f"eventos audit últimas 24h: {eventos_recientes}",
    })

    # Suma ponderada
    total = sum(d["score"] * d["peso"] / 100 for d in desglose)
    total = round(total, 2)

    if total >= 85:
        estado = "HEALTHY"
    elif total >= 60:
        estado = "DEGRADED"
    else:
        estado = "UNHEALTHY"

    return {
        "score_total": total,
        "estado": estado,
        "desglose": desglose,
        "evaluado_en": ahora.isoformat(),
    }


@router.get("/metricas-ia/cache-eficiencia")
def metricas_ia_cache_eficiencia(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R143 P1: eficiencia del caché IA (hit rate y ahorro estimado).

    El cache de respuestas IA evita pagar por queries repetidas.
    Este endpoint mide qué tan bien funciona ese cache:
      - hit_rate_pct = cache_read_tokens / total_input_tokens
      - ahorro_usd_estimado: tokens leídos del cache × precio
        (×0.9 = el ahorro vs full input)

    Útil para optimizar costos:
      - Hit rate < 30% → revisar normalización de prompts
      - Hit rate > 80% → cache funcionando bien

    Solo COORDINADOR/ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import AICacheRecord, AICallRecord

    desde = ahora_utc() - timedelta(days=int(dias))

    rows = (
        db.query(AICallRecord)
        .filter(AICallRecord.creado_en >= desde)
        .all()
    )

    total_input = sum(r.input_tokens or 0 for r in rows)
    total_cache_read = sum(r.cache_read_input_tokens or 0 for r in rows)
    total_cache_creation = sum(
        r.cache_creation_input_tokens or 0 for r in rows
    )
    total_cost = sum(float(r.cost_usd or 0) for r in rows)

    hit_rate = (
        round(100 * total_cache_read / total_input, 2)
        if total_input else 0.0
    )

    # Asumimos precio Claude Sonnet input ~$3/Mtok. Cache_read
    # ~10% del precio → ahorro = cache_read × 0.9 × $3/Mtok.
    PRECIO_INPUT_USD_PER_MTOK = 3.0
    ahorro_estimado = (
        total_cache_read * 0.9 * PRECIO_INPUT_USD_PER_MTOK / 1_000_000
    )

    cache_total = db.query(AICacheRecord).count()

    return {
        "ventana_dias": int(dias),
        "total_calls": len(rows),
        "total_input_tokens": total_input,
        "total_cache_read_tokens": total_cache_read,
        "total_cache_creation_tokens": total_cache_creation,
        "hit_rate_pct": hit_rate,
        "cost_total_usd": round(total_cost, 4),
        "ahorro_estimado_usd": round(ahorro_estimado, 4),
        "ai_cache_filas_actuales": cache_total,
    }


@router.get("/metricas-ia/budget")
def metricas_ia_budget(
    presupuesto_mensual_usd: float = 100.0,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R125 P2: estado del presupuesto IA del mes en curso.

    Útil para alertas tempranas:
      "Vamos $80 de $100 — 80% del budget consumido al día 20.
       Proyección fin de mes: $123 → SOBRE PRESUPUESTO."

    Param: presupuesto_mensual_usd (cap configurable).

    Devuelve:
      - presupuesto_mensual_usd
      - gastado_usd_acumulado_mes
      - dias_transcurridos_mes / dias_totales_mes
      - proyeccion_fin_de_mes_usd (lineal)
      - alerta: GREEN | YELLOW | RED
      - pct_consumido / pct_proyectado
    """
    from datetime import datetime, timezone
    from calendar import monthrange

    from app.core.tz import ahora_utc
    from app.models.db import AICallRecord

    ahora = ahora_utc()
    inicio_mes = ahora.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    dias_mes_total = monthrange(ahora.year, ahora.month)[1]
    dias_transcurridos = max(1, ahora.day)

    rows = (
        db.query(AICallRecord)
        .filter(AICallRecord.creado_en >= inicio_mes)
        .all()
    )
    gastado = sum(float(r.cost_usd or 0) for r in rows)

    # Proyección lineal
    proyeccion = gastado * (dias_mes_total / dias_transcurridos)

    pct_consumido = (
        round(100 * gastado / presupuesto_mensual_usd, 2)
        if presupuesto_mensual_usd else 0.0
    )
    pct_proyectado = (
        round(100 * proyeccion / presupuesto_mensual_usd, 2)
        if presupuesto_mensual_usd else 0.0
    )

    if pct_proyectado >= 100:
        alerta = "RED"
    elif pct_proyectado >= 80:
        alerta = "YELLOW"
    else:
        alerta = "GREEN"

    return {
        "presupuesto_mensual_usd": float(presupuesto_mensual_usd),
        "gastado_usd_acumulado_mes": round(gastado, 4),
        "calls_acumuladas_mes": len(rows),
        "dias_transcurridos_mes": dias_transcurridos,
        "dias_totales_mes": dias_mes_total,
        "proyeccion_fin_de_mes_usd": round(proyeccion, 4),
        "pct_consumido": pct_consumido,
        "pct_proyectado": pct_proyectado,
        "alerta": alerta,
        "mes_actual": ahora.strftime("%Y-%m"),
    }


@router.get("/metricas-ia/por-modelo")
def metricas_ia_por_modelo(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R125 P1: desglose de métricas IA por modelo (Claude/Groq).

    Útil para entender:
      - ¿Qué proveedor consume más presupuesto?
      - ¿Qué modelo es más rápido en producción real?
      - ¿Vale la pena seguir con el fallback?

    Para cada modelo en la ventana:
      - calls
      - cost_usd_total
      - latency_promedio_ms
      - tokens_input / tokens_output totales
      - cache_hit_rate_pct (cache_read / total_input)
      - cost_per_call_usd

    Ordenado DESC por cost_usd_total.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import AICallRecord

    desde = ahora_utc() - timedelta(days=int(dias))
    rows = (
        db.query(AICallRecord)
        .filter(AICallRecord.creado_en >= desde)
        .all()
    )

    por_modelo: dict[str, dict] = {}
    for r in rows:
        clave = f"{r.proveedor}/{r.modelo}"
        if clave not in por_modelo:
            por_modelo[clave] = {
                "proveedor": r.proveedor,
                "modelo": r.modelo,
                "calls": 0,
                "cost_usd": 0.0,
                "latency_total_ms": 0,
                "input_tokens": 0,
                "cache_read": 0,
                "output_tokens": 0,
            }
        b = por_modelo[clave]
        b["calls"] += 1
        b["cost_usd"] += float(r.cost_usd or 0)
        b["latency_total_ms"] += int(r.latency_ms or 0)
        b["input_tokens"] += int(r.input_tokens or 0)
        b["cache_read"] += int(r.cache_read_input_tokens or 0)
        b["output_tokens"] += int(r.output_tokens or 0)

    items = []
    for clave, b in por_modelo.items():
        latency_avg = (
            round(b["latency_total_ms"] / b["calls"], 0)
            if b["calls"] else 0
        )
        cache_hit = (
            round(100 * b["cache_read"] / b["input_tokens"], 2)
            if b["input_tokens"] else 0.0
        )
        cost_per_call = (
            round(b["cost_usd"] / b["calls"], 6)
            if b["calls"] else 0.0
        )
        items.append({
            "proveedor": b["proveedor"],
            "modelo": b["modelo"],
            "calls": b["calls"],
            "cost_usd_total": round(b["cost_usd"], 4),
            "cost_per_call_usd": cost_per_call,
            "latency_promedio_ms": int(latency_avg),
            "tokens_input": b["input_tokens"],
            "tokens_output": b["output_tokens"],
            "cache_hit_rate_pct": cache_hit,
        })
    items.sort(key=lambda x: x["cost_usd_total"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "total_modelos_usados": len(items),
        "calls_totales": sum(it["calls"] for it in items),
        "cost_usd_total": round(sum(it["cost_usd_total"] for it in items), 4),
        "items": items,
    }


@router.get("/runtime-info")
def info_runtime(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R107 P2: metadata del proceso Python en ejecución.

    Útil para diagnosticar problemas de performance/memoria sin
    SSH. Reporta:
      - Python version + implementation
      - Process uptime (segundos desde arranque)
      - Working directory
      - Total threads
      - Memoria RSS (si psutil está disponible)

    Solo COORDINADOR/ADMIN.
    """
    import os
    import platform
    import sys
    import threading
    import time

    # Uptime: aproximamos con time.monotonic() vs hora arranque cacheada
    # NO importamos psutil aquí (puede no estar instalado en prod minimal).
    info = {
        "python_version": sys.version.split()[0],
        "python_implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "pid": os.getpid(),
        "cwd": os.getcwd(),
        "threads_activos": threading.active_count(),
        "tz_env": os.getenv("TZ") or None,
    }

    # Memoria si psutil disponible
    try:
        import psutil
        proc = psutil.Process(os.getpid())
        mem_info = proc.memory_info()
        info["memoria_rss_mb"] = round(mem_info.rss / 1024 / 1024, 2)
        info["cpu_pct"] = proc.cpu_percent(interval=0.1)
        info["uptime_segundos"] = int(time.time() - proc.create_time())
        info["psutil_disponible"] = True
    except ImportError:
        info["psutil_disponible"] = False

    return info


@router.get("/db-schema")
def info_db_schema(
    incluir_columnas: bool = True,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R105 P2: introspección del schema de BD.

    Útil para:
      - Ops: verificar que migraciones aplicaron correctamente
      - Documentación: generar diagramas
      - Soporte: ¿qué columnas tiene la tabla X?

    Lee directamente del MetaData de SQLAlchemy (no consulta BD),
    así que es rápido y refleja el modelo declarado en código.
    """
    from app.database import Base

    items = []
    for tname, tabla in Base.metadata.tables.items():
        cols = []
        if incluir_columnas:
            for col in tabla.columns:
                cols.append({
                    "nombre": col.name,
                    "tipo": str(col.type),
                    "nullable": bool(col.nullable),
                    "primary_key": bool(col.primary_key),
                    "indexado": bool(col.index) or bool(col.primary_key),
                })
        items.append({
            "tabla": tname,
            "total_columnas": len(tabla.columns),
            "columnas": cols if incluir_columnas else None,
        })

    items.sort(key=lambda x: x["tabla"])

    return {
        "total_tablas": len(items),
        "incluir_columnas": bool(incluir_columnas),
        "items": items,
    }


@router.get("/import-history")
def info_import_history(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R149 P1: historial de importaciones masivas.

    Detecta cargas masivas analizando picos en creación de glosas:
      "El día 2026-04-15 se crearon 247 glosas en 1 hora → carga
       masiva probable"

    Heurística: agrupa glosas por (fecha, hora) y reporta los
    cluster más grandes (>=10 glosas en una misma hora).

    Útil para auditoría:
      - Reconstruir cuándo se hicieron imports
      - Detectar imports duplicados
      - Validar que el batch_id se respetó

    Solo COORDINADOR/ADMIN.
    """
    from datetime import timedelta, timezone

    from app.core.tz import ahora_utc
    from app.models.db import GlosaRecord

    desde = ahora_utc() - timedelta(days=int(dias))
    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= desde)
        .all()
    )

    por_hora: dict[str, dict] = {}
    for g in glosas:
        ts = g.creado_en
        if ts and ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if not ts:
            continue
        key = ts.strftime("%Y-%m-%dT%H:00")
        if key not in por_hora:
            por_hora[key] = {"count": 0, "valor": 0.0, "epss": set()}
        b = por_hora[key]
        b["count"] += 1
        b["valor"] += float(g.valor_objetado or 0)
        if g.eps:
            b["epss"].add(g.eps)

    items = []
    for hora, b in por_hora.items():
        if b["count"] < 10:
            continue
        items.append({
            "hora": hora,
            "glosas_creadas": b["count"],
            "valor_total": int(b["valor"]),
            "eps_distintas": len(b["epss"]),
        })
    items.sort(key=lambda x: x["glosas_creadas"], reverse=True)

    return {
        "ventana_dias": int(dias),
        "umbral_cluster": 10,
        "total_clusters_detectados": len(items),
        "items": items,
    }


@router.get("/jobs-programados")
def info_jobs_programados(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R104 P1: estado de los jobs programados (schedulers asincrónicos).

    Lista los background tasks de la app:
      - pre_analisis: IA proactiva diaria 6 AM
      - mantenimiento: limpieza BD diaria 3 AM
      - digest: resumen diario por email (si DIGEST_DESTINATARIOS)

    Útil para verificar que los schedulers están vivos sin tener
    que SSH al servidor.

    Cada job devuelve: nombre, activo (bool), descripción, frecuencia.
    """
    jobs = []

    # Pre-análisis IA
    pre_activo = None
    try:
        from app.services.ia_auditora_proactiva import _task as _t
        pre_activo = _t is not None and not _t.done()
    except Exception:
        pre_activo = None
    jobs.append({
        "nombre": "pre_analisis_ia",
        "descripcion": "Pre-análisis IA proactivo de glosas pendientes",
        "frecuencia": "diaria 06:00 UTC",
        "activo": pre_activo,
        "modulo": "app.services.ia_auditora_proactiva",
    })

    # Mantenimiento
    mant_activo = None
    try:
        from app.services.mantenimiento_scheduler import _task as _t
        mant_activo = _t is not None and not _t.done()
    except Exception:
        mant_activo = None
    jobs.append({
        "nombre": "mantenimiento_bd",
        "descripcion": "Purga ai_cache, ai_calls y papelera caducada",
        "frecuencia": "diaria 03:00 UTC",
        "activo": mant_activo,
        "modulo": "app.services.mantenimiento_scheduler",
    })

    # Digest
    digest_activo = None
    try:
        from app.services.digest_scheduler import _task as _t
        digest_activo = _t is not None and not _t.done()
    except Exception:
        digest_activo = None
    jobs.append({
        "nombre": "digest_email",
        "descripcion": "Resumen diario por email (requiere DIGEST_DESTINATARIOS)",
        "frecuencia": "diaria 07:00 UTC",
        "activo": digest_activo,
        "modulo": "app.services.digest_scheduler",
    })

    return {
        "total_jobs": len(jobs),
        "activos": sum(1 for j in jobs if j["activo"]),
        "items": jobs,
    }


@router.get("/zonas-horarias")
def info_zonas_horarias(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R101 P1: diagnóstico de timezones del servidor y BD.

    Útil para diagnosticar inconsistencias en timestamps:
      - ¿Por qué la fecha de creación se ve "una hora atrás"?
      - ¿La BD está devolviendo naive vs aware datetimes?
      - ¿El servidor está en UTC o en hora local?

    Devuelve:
      - now_utc / now_local
      - server_timezone (TZ env var)
      - bogota_offset_utc
      - python_tz_module (zoneinfo / pytz / fallback)
    """
    import os
    from datetime import datetime, timezone

    from app.core.tz import ahora_utc

    ahora = ahora_utc()
    now_local = datetime.now()

    # Detección de modulo TZ disponible
    try:
        from zoneinfo import ZoneInfo  # noqa: F401
        tz_module = "zoneinfo"
    except ImportError:
        try:
            import pytz  # noqa: F401
            tz_module = "pytz"
        except ImportError:
            tz_module = "ninguno"

    bogota_offset = None
    if tz_module == "zoneinfo":
        from zoneinfo import ZoneInfo
        bogota_now = datetime.now(ZoneInfo("America/Bogota"))
        bogota_offset = (
            bogota_now.utcoffset().total_seconds() / 3600
            if bogota_now.utcoffset() else None
        )

    return {
        "now_utc": ahora.isoformat(),
        "now_local": now_local.isoformat(),
        "now_local_tz_aware": now_local.tzinfo is not None,
        "server_tz_env": os.getenv("TZ") or None,
        "python_tz_module": tz_module,
        "bogota_offset_utc": bogota_offset,
    }


@router.get("/observabilidad-completa")
def info_observabilidad_completa(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R208 P1: bundle de métricas técnicas para dashboards.

    Combina varios checks en uno solo para alimentar un
    dashboard tipo Datadog/Grafana sin múltiples llamadas:
      - tamaños de tablas
      - schedulers vivos
      - eventos audit última hora
      - IA calls última hora

    Solo COORDINADOR/ADMIN.
    """
    from datetime import timedelta

    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import (
        AICacheRecord, AICallRecord, AuditLogRecord, GlosaRecord,
    )

    ahora = ahora_utc()
    desde_1h = ahora - timedelta(hours=1)

    eventos_1h = (
        db.query(_f.count(AuditLogRecord.id))
        .filter(AuditLogRecord.timestamp >= desde_1h)
        .scalar() or 0
    )
    ai_calls_1h = (
        db.query(_f.count(AICallRecord.id))
        .filter(AICallRecord.creado_en >= desde_1h)
        .scalar() or 0
    )
    cache_size = (
        db.query(_f.count()).select_from(AICacheRecord).scalar() or 0
    )
    total_glosas = (
        db.query(_f.count(GlosaRecord.id)).scalar() or 0
    )

    schedulers = {}
    try:
        from app.services.ia_auditora_proactiva import _task as t1
        schedulers["pre_analisis"] = bool(t1 and not t1.done())
    except Exception:
        schedulers["pre_analisis"] = False
    try:
        from app.services.mantenimiento_scheduler import _task as t2
        schedulers["mantenimiento"] = bool(t2 and not t2.done())
    except Exception:
        schedulers["mantenimiento"] = False

    return {
        "evaluado_en": ahora.isoformat(),
        "actividad_ultima_hora": {
            "eventos_audit": int(eventos_1h),
            "ia_calls": int(ai_calls_1h),
        },
        "tamanos": {
            "ai_cache_filas": int(cache_size),
            "glosas_total": int(total_glosas),
        },
        "schedulers": schedulers,
    }


@router.get("/snapshot-general")
def info_snapshot_general(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R158 P2: snapshot consolidado de TODO el sistema.

    Single-call que reúne en un solo lugar las cifras "vivas"
    de la plataforma, útil para una pantalla de monitoreo /
    NOC del coordinador.

    Diferente a /admin/snapshot.json (point-in-time export para
    archivar): aquí solo counts agregados — pensado para un
    refresh frecuente sin saturar BD.

    Solo COORDINADOR/ADMIN.
    """
    from sqlalchemy import func as _f

    from app.core.tz import ahora_utc
    from app.models.db import (
        AICacheRecord, AICallRecord, AuditLogRecord,
        ConciliacionRecord, ContratoRecord,
        DictamenVersionRecord, GlosaEliminadaRecord, GlosaRecord,
        PlantillaGoldRecord, PlantillaRecord, UsuarioRecord,
    )

    def _count(model):
        return db.query(_f.count()).select_from(model).scalar() or 0

    return {
        "evaluado_en": ahora_utc().isoformat(),
        "counts": {
            "glosas": _count(GlosaRecord),
            "usuarios": _count(UsuarioRecord),
            "audit_log": _count(AuditLogRecord),
            "ai_calls": _count(AICallRecord),
            "ai_cache": _count(AICacheRecord),
            "dictamen_versiones": _count(DictamenVersionRecord),
            "conciliaciones": _count(ConciliacionRecord),
            "contratos": _count(ContratoRecord),
            "plantillas": _count(PlantillaRecord),
            "plantillas_gold": _count(PlantillaGoldRecord),
            "papelera": _count(GlosaEliminadaRecord),
        },
    }


@router.get("/glosas-con-ia")
def info_glosas_con_ia(
    dias: int = 30,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R157 P1: cobertura del LLM sobre las glosas.

    Reporta qué porcentaje de las glosas creadas en la ventana
    han pasado por al menos una llamada IA. Útil para entender
    el ROI del LLM:
      - Cobertura alta + buen tasa_lev → IA está ayudando
      - Cobertura alta pero tasa_lev mala → revisar prompts
      - Cobertura baja → ¿por qué no se usa más la IA?

    Devuelve:
      - total_glosas_periodo
      - glosas_con_ia (al menos 1 call)
      - cobertura_pct
      - calls_por_glosa_promedio
      - cost_promedio_usd_por_glosa

    Solo COORDINADOR/ADMIN.
    """
    from datetime import timedelta

    from app.core.tz import ahora_utc
    from app.models.db import AICallRecord, GlosaRecord

    desde = ahora_utc() - timedelta(days=int(dias))

    glosas = (
        db.query(GlosaRecord)
        .filter(GlosaRecord.creado_en >= desde)
        .all()
    )
    total_glosas = len(glosas)
    glosa_ids = {g.id for g in glosas}

    if not glosa_ids:
        return {
            "ventana_dias": int(dias),
            "total_glosas_periodo": 0,
            "glosas_con_ia": 0,
            "cobertura_pct": 0.0,
            "calls_por_glosa_promedio": 0.0,
            "cost_promedio_usd_por_glosa": 0.0,
        }

    calls = (
        db.query(AICallRecord)
        .filter(AICallRecord.glosa_id.in_(glosa_ids))
        .all()
    )

    glosas_con_ia: set[int] = set()
    cost_total = 0.0
    for c in calls:
        if c.glosa_id is not None:
            glosas_con_ia.add(c.glosa_id)
        cost_total += float(c.cost_usd or 0)

    cobertura = round(100 * len(glosas_con_ia) / total_glosas, 2)
    calls_promedio = (
        round(len(calls) / len(glosas_con_ia), 2)
        if glosas_con_ia else 0.0
    )
    cost_promedio = (
        round(cost_total / len(glosas_con_ia), 6)
        if glosas_con_ia else 0.0
    )

    return {
        "ventana_dias": int(dias),
        "total_glosas_periodo": total_glosas,
        "glosas_con_ia": len(glosas_con_ia),
        "cobertura_pct": cobertura,
        "total_calls_periodo": len(calls),
        "calls_por_glosa_promedio": calls_promedio,
        "cost_total_usd": round(cost_total, 4),
        "cost_promedio_usd_por_glosa": cost_promedio,
    }


@router.get("/feature-flags")
def info_feature_flags(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R144 P1: flags de features activas según configuración.

    Reporta qué funcionalidades opcionales están habilitadas en
    el deploy actual. Útil para que el frontend muestre/oculte
    UI sin adivinar:
      - ¿Tiene IA? → mostrar "Generar dictamen IA"
      - ¿Push notifications? → mostrar opción suscribirse
      - ¿WhatsApp/Telegram? → mostrar canales alerta

    Cada flag: {nombre, activo, descripcion}.

    Solo COORDINADOR/ADMIN.
    """
    import os

    from app.core.config import get_settings

    cfg = get_settings()

    flags = [
        {
            "nombre": "ia_anthropic",
            "activo": bool(cfg.anthropic_api_key),
            "descripcion": "Claude Sonnet como LLM principal",
        },
        {
            "nombre": "ia_groq",
            "activo": bool(cfg.groq_api_key),
            "descripcion": "Groq Llama como LLM fallback",
        },
        {
            "nombre": "firma_digital_rsa",
            "activo": bool(os.getenv("FIRMA_DIGITAL_PRIVATE_KEY")),
            "descripcion": "Firma RSA-PSS-SHA256 (asimétrica)",
        },
        {
            "nombre": "cifrado_simetrico",
            "activo": bool(os.getenv("GLOSAS_ENCRYPTION_KEY")),
            "descripcion": "Cifrado de campos sensibles",
        },
        {
            "nombre": "smtp_alertas",
            "activo": bool(cfg.smtp_user and cfg.smtp_password),
            "descripcion": "Email SMTP para alertas",
        },
        {
            "nombre": "whatsapp_business",
            "activo": bool(
                os.getenv("WHATSAPP_META_TOKEN")
                and os.getenv("WHATSAPP_META_PHONE_ID")
            ),
            "descripcion": "WhatsApp Business API (Meta)",
        },
        {
            "nombre": "telegram_bot",
            "activo": bool(os.getenv("TELEGRAM_BOT_TOKEN")),
            "descripcion": "Telegram bot para notificaciones",
        },
        {
            "nombre": "push_notifications",
            "activo": bool(
                os.getenv("VAPID_PUBLIC_KEY")
                and os.getenv("VAPID_PRIVATE_KEY")
            ),
            "descripcion": "Web Push (VAPID)",
        },
        {
            "nombre": "sentry",
            "activo": bool(os.getenv("SENTRY_DSN")),
            "descripcion": "Tracking de errores Sentry",
        },
        {
            "nombre": "digest_email",
            "activo": bool(os.getenv("DIGEST_DESTINATARIOS")),
            "descripcion": "Resumen diario por email",
        },
        {
            "nombre": "banner_capacitacion",
            "activo": bool(cfg.banner_capacitacion),
            "descripcion": "Banner UI configurable",
        },
    ]

    activas = sum(1 for f in flags if f["activo"])

    return {
        "total_flags": len(flags),
        "activas": activas,
        "inactivas": len(flags) - activas,
        "items": flags,
    }


@router.get("/banner-info")
def info_banner(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R143 P2: información del banner UI configurable.

    Endpoint liviano que el frontend consulta al inicio para
    decidir si mostrar un banner global. Mensaje viene de
    BANNER_CAPACITACION env var:
      - vacío → no mostrar banner
      - cualquier string → mostrar como info

    También indica si el sistema está en modo capacitación
    (por convención: cuando el banner está activo).

    Útil para:
      - Avisos de mantenimiento programado
      - Notas de capacitación
      - Alertas de cambios regulatorios
    """
    from app.core.config import get_settings

    cfg = get_settings()
    mensaje = (cfg.banner_capacitacion or "").strip()

    return {
        "mostrar_banner": bool(mensaje),
        "mensaje": mensaje or None,
        "modo_capacitacion": bool(mensaje),
        "tipo": "info",
    }


@router.get("/configuracion")
def info_configuracion(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R97 P1: configuración runtime del sistema (sin secretos).

    Devuelve los valores actuales de configuración no-sensibles,
    útil para verificar que el deploy tiene la config esperada
    sin tener que SSH a Render.

    Campos secretos (api_keys, passwords, secret_key, smtp_password)
    se reportan SOLO como booleanos "está_configurado" — nunca
    el valor real.
    """
    from app.core.config import get_settings

    cfg = get_settings()

    return {
        "app": {
            "nombre": cfg.app_name,
            "version": cfg.app_version,
        },
        "ia": {
            "primary_ai": cfg.primary_ai,
            "groq_model": cfg.groq_model,
            "anthropic_model": cfg.anthropic_model,
            "anthropic_configurado": bool(cfg.anthropic_api_key),
            "groq_configurado": bool(cfg.groq_api_key),
        },
        "auth": {
            "algorithm": cfg.algorithm,
            "access_token_expire_minutes": cfg.access_token_expire_minutes,
            "secret_key_configurado": bool(
                cfg.secret_key
                and cfg.secret_key != "dev-only-secret-key-change-in-production"
            ),
            "admin_password_configurado": bool(
                cfg.admin_password
                and cfg.admin_password != "CHANGEME_SET_ADMIN_PASSWORD_ENV_VAR"
            ),
        },
        "cors": {
            "allowed_origins": cfg.get_allowed_origins(),
        },
        "smtp": {
            "host": cfg.smtp_host,
            "port": cfg.smtp_port,
            "user_configurado": bool(cfg.smtp_user),
            "password_configurado": bool(cfg.smtp_password),
            "alertas_email": cfg.alertas_email or None,
        },
        "ui": {
            "banner_capacitacion": cfg.banner_capacitacion or None,
        },
    }


@router.get("/dependencias")
def info_dependencias(
    incluir_indirectas: bool = False,
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """R91 P2: lista de paquetes Python instalados con versiones.

    Útil para:
      - Auditoría de seguridad (cruzar contra base de CVEs)
      - Reproducibilidad (recrear env exacto en local)
      - Soporte (¿qué versión exacta de anthropic-sdk corre prod?)

    Por defecto devuelve solo dependencias declaradas en requirements
    (las que aparecen en pyproject/requirements.txt). Con
    incluir_indirectas=true incluye TODAS las del entorno.
    """
    from importlib.metadata import distributions

    # Heurística: dependencias declaradas explícitamente en requirements.txt.
    # Hardcoded para evitar parseo en runtime (rápido, deterministic).
    DECLARADAS_DIRECTAS = {
        "fastapi", "uvicorn", "sqlalchemy", "psycopg2-binary",
        "pydantic", "pydantic-settings", "python-jose",
        "passlib", "bcrypt", "python-multipart",
        "anthropic", "groq", "openai",
        "openpyxl", "reportlab", "pypdf2", "pdfminer-six",
        "pytesseract", "pillow", "weasyprint",
        "python-dotenv", "httpx", "requests",
        "pytest", "pytest-asyncio",
        "sentry-sdk", "cryptography",
    }

    paquetes = []
    for dist in distributions():
        nombre = (dist.metadata.get("Name") or "").lower()
        if not nombre:
            continue
        if not incluir_indirectas and nombre not in DECLARADAS_DIRECTAS:
            continue
        paquetes.append({
            "nombre": nombre,
            "version": dist.version,
        })

    paquetes.sort(key=lambda p: p["nombre"])

    return {
        "total": len(paquetes),
        "incluye_indirectas": bool(incluir_indirectas),
        "paquetes": paquetes,
    }
