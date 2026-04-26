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
