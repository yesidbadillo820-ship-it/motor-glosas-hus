"""
diagnostico.py — Status / Diagnostic page del motor (A.2 del plan UX).

Endpoint admin que devuelve health de TODO el sistema en un solo
JSON:
  - Conexión a DB Neon
  - Estado del indexer de soportes (cuántos archivos, última build)
  - Estado de noticias (cuántas indexadas, última fetch)
  - Estados de los schedulers (mantenimiento, soportes-reindex,
    pre-análisis, noticias)
  - Disponibilidad de Anthropic + Groq (test ping rápido)
  - Estadísticas de glosas / lotes / usuarios
  - Últimos errores en logs

Uso: el admin entra a /admin/diagnostico (tab del SPA) y ve un panel
verde-amarillo-rojo con cada componente. Si algo está rojo, tiene
botones "Reindexar ahora" / "Refrescar noticias" para auto-fix.
"""
from __future__ import annotations
import os
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from app.database import get_db
from app.api.deps import get_admin
from app.models.db import (
    UsuarioRecord, GlosaRecord, NoticiaSaludRecord,
    LoteImportacionRecord, ContratoRecord, ClausulaContrato,
)

logger = logging.getLogger("motor_glosas")

router = APIRouter(prefix="/admin/diagnostico", tags=["diagnostico"])


_PING_CACHE: dict = {}
_PING_TTL_S = 15 * 60


def _ping_cached(key: str, fn):
    now = datetime.now(timezone.utc)
    cached = _PING_CACHE.get(key)
    if cached is not None:
        estado, mensaje, data, ts = cached
        if (now - ts).total_seconds() < _PING_TTL_S:
            return estado, mensaje, data
    estado, mensaje, data = fn()
    _PING_CACHE[key] = (estado, mensaje, data, now)
    return estado, mensaje, data


@router.get("")
def diagnostico_completo(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Devuelve health del sistema completo. Solo admin/coordinador.

    Cada sección incluye:
      - estado: "ok" | "warning" | "error"
      - mensaje: descripción humana
      - data: detalles técnicos
    """
    out: dict = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "version": "5.4.0",
        "secciones": {},
    }

    # ─── DB Neon Postgres ──────────────────────────────────────────
    try:
        n_glosas = db.query(func.count(GlosaRecord.id)).scalar() or 0
        n_usuarios = db.query(func.count(UsuarioRecord.id)).scalar() or 0
        n_contratos = db.query(func.count(ContratoRecord.eps)).scalar() or 0
        out["secciones"]["base_de_datos"] = {
            "estado": "ok",
            "mensaje": f"Neon Postgres conectado · {n_glosas} glosas, {n_usuarios} usuarios, {n_contratos} contratos",
            "data": {
                "glosas": n_glosas,
                "usuarios": n_usuarios,
                "contratos": n_contratos,
            },
        }
    except Exception as e:
        out["secciones"]["base_de_datos"] = {
            "estado": "error",
            "mensaje": f"No se pudo consultar la BD: {e}",
            "data": {},
        }

    # ─── Indexer de soportes ───────────────────────────────────────
    try:
        from app.services.soportes_autodiscovery_service import get_indexer
        indexer = get_indexer()
        stats = indexer.stats()
        if stats.get("facturas_indexadas", 0) == 0:
            estado = "warning"
            mensaje = (
                "Indexer sin archivos. "
                "Verificá que el jump-box (tools/jumpbox_sync.py) esté corriendo "
                "y subiendo soportes al volumen Fly."
            )
        else:
            ultima = stats.get("construido_hace_seg")
            if ultima is None or ultima > 24 * 3600:
                estado = "warning"
                mensaje = f"{stats['facturas_indexadas']} facturas indexadas pero la última build es vieja (>24h)"
            else:
                estado = "ok"
                horas = ultima / 3600 if ultima else 0
                mensaje = f"{stats['facturas_indexadas']} facturas, {stats.get('archivos_indexados', 0)} archivos, build hace {horas:.1f}h"
        out["secciones"]["soportes_indexer"] = {
            "estado": estado,
            "mensaje": mensaje,
            "data": stats,
        }
    except Exception as e:
        out["secciones"]["soportes_indexer"] = {
            "estado": "error",
            "mensaje": f"Indexer falló: {e}",
            "data": {},
        }

    # ─── Noticias salud Colombia ──────────────────────────────────
    try:
        n_activas = (
            db.query(func.count(NoticiaSaludRecord.id))
            .filter(NoticiaSaludRecord.activa == 1)
            .scalar() or 0
        )
        ultima_noticia = (
            db.query(NoticiaSaludRecord.indexada_en)
            .order_by(desc(NoticiaSaludRecord.indexada_en))
            .first()
        )
        ultima_fecha = ultima_noticia[0] if ultima_noticia else None
        por_fuente = dict(
            db.query(NoticiaSaludRecord.fuente, func.count(NoticiaSaludRecord.id))
            .filter(NoticiaSaludRecord.activa == 1)
            .group_by(NoticiaSaludRecord.fuente)
            .all()
        )
        if n_activas == 0:
            estado = "warning"
            mensaje = (
                "0 noticias indexadas. El scheduler corre cada 4h. "
                'Click "Refrescar ahora" para forzar fetch.'
            )
        elif ultima_fecha and (datetime.now(timezone.utc) - ultima_fecha) > timedelta(hours=12):
            estado = "warning"
            mensaje = f"{n_activas} noticias activas pero la última fetch fue hace >12h"
        else:
            estado = "ok"
            mensaje = f"{n_activas} noticias activas, fuentes: {', '.join(por_fuente.keys()) or 'ninguna'}"
        out["secciones"]["noticias"] = {
            "estado": estado,
            "mensaje": mensaje,
            "data": {
                "total_activas": n_activas,
                "por_fuente": por_fuente,
                "ultima_indexada": ultima_fecha.isoformat() if ultima_fecha else None,
            },
        }
    except Exception as e:
        out["secciones"]["noticias"] = {
            "estado": "error",
            "mensaje": f"Query falló: {e}",
            "data": {},
        }

    # ─── Anthropic API key configurada + test ping ─────────────────
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        out["secciones"]["anthropic"] = {
            "estado": "error",
            "mensaje": "ANTHROPIC_API_KEY no configurada en Fly Secrets",
            "data": {},
        }
    else:
        def _do_ping_anthropic():
            try:
                import httpx
                timeout = httpx.Timeout(connect=8.0, read=15.0, write=8.0, pool=5.0)
                with httpx.Client(timeout=timeout) as client:
                    resp = client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": anthropic_key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": "claude-haiku-4-5-20251001",
                            "max_tokens": 4,
                            "messages": [{"role": "user", "content": "ok"}],
                        },
                    )
                if resp.status_code == 200:
                    return "ok", f"API key OK · ping Haiku exitoso · {anthropic_key[:10]}…", {}
                if resp.status_code == 400:
                    err_msg = ""
                    try:
                        err_msg = resp.json().get("error", {}).get("message", "")
                    except Exception:
                        err_msg = resp.text[:120]
                    if "credit" in err_msg.lower():
                        return "error", f"🚨 Sin créditos — recargar en console.anthropic.com/settings/billing. ({err_msg[:120]})", {}
                    return "warning", f"HTTP 400: {err_msg[:120]}", {}
                if resp.status_code in (401, 403):
                    return "error", f"API key inválida o revocada (HTTP {resp.status_code})", {}
                if resp.status_code == 429:
                    return "warning", "Rate limit hit (429) — esperá 60s", {}
                if resp.status_code == 529:
                    return "warning", "Anthropic overloaded (529) — temporal", {}
                return "warning", f"HTTP {resp.status_code} inesperado", {}
            except Exception as e:
                return "warning", f"No se pudo hacer ping: {e}", {}

        cache_key = f"anthropic::{anthropic_key[:6]}"
        ping_estado, ping_msg, _ = _ping_cached(cache_key, _do_ping_anthropic)

        out["secciones"]["anthropic"] = {
            "estado": ping_estado,
            "mensaje": ping_msg,
            "data": {
                "primary_ai": os.getenv("PRIMARY_AI", "anthropic"),
                "modelo_default": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5"),
                "tool_use_habilitado": os.getenv("TOOL_USE_HABILITADO", "0") == "1",
                "multi_agent_habilitado": os.getenv("MULTI_AGENT_HABILITADO", "0") == "1",
                "key_prefix": anthropic_key[:12],
            },
        }

    # ─── Groq API key configurada ─────────────────────────────────
    groq_key = os.getenv("GROQ_API_KEY", "")
    if not groq_key:
        out["secciones"]["groq"] = {
            "estado": "warning",
            "mensaje": "GROQ_API_KEY no configurada — sin fallback si Anthropic falla",
            "data": {},
        }
    else:
        out["secciones"]["groq"] = {
            "estado": "ok",
            "mensaje": f"API key configurada (fallback de Anthropic, prefijo {groq_key[:10]}…)",
            "data": {
                "modelo": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            },
        }

    # ─── Gemini API key + ping (tercer proveedor, free tier) ────────
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        out["secciones"]["gemini"] = {
            "estado": "warning",
            "mensaje": "GEMINI_API_KEY no configurada — agrega clave en aistudio.google.com/apikey (15 RPM gratis)",
            "data": {},
        }
    else:
        gemini_modelo = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

        def _do_ping_gemini():
            try:
                import httpx as _httpx_g
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_modelo}:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                    "generationConfig": {"maxOutputTokens": 4, "temperature": 0},
                }
                with _httpx_g.Client(timeout=10.0) as client:
                    rg = client.post(url, json=payload)
                if rg.status_code == 200:
                    return "ok", f"API key OK · ping {gemini_modelo} exitoso · {gemini_key[:10]}…", {}
                if rg.status_code in (400, 401, 403):
                    return "error", f"API key INVALIDA o sin permisos (HTTP {rg.status_code})", {}
                if rg.status_code == 429:
                    return "warning", "Rate limit del tier gratis hit (HTTP 429). Esperar 60s o usar Anthropic/Groq.", {}
                return "warning", f"Ping HTTP {rg.status_code}: {rg.text[:120]}", {}
            except Exception as _eg:
                return "warning", f"No se pudo hacer ping: {str(_eg)[:120]}", {}

        cache_key = f"gemini::{gemini_modelo}::{gemini_key[:6]}"
        ping_estado, ping_msg, _ = _ping_cached(cache_key, _do_ping_gemini)
        out["secciones"]["gemini"] = {
            "estado": ping_estado,
            "mensaje": ping_msg,
            "data": {
                "modelo": gemini_modelo,
                "key_prefix": gemini_key[:10],
                "free_tier_info": "15 RPM / 1500 RPD para Flash · 2 RPM / 50 RPD para Pro",
            },
        }

    # ─── OpenRouter API key + ping (cuarto proveedor — DeepSeek/Llama) ─
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    if not openrouter_key:
        out["secciones"]["openrouter"] = {
            "estado": "warning",
            "mensaje": (
                "OPENROUTER_API_KEY no configurada — recomendado para tener "
                "DeepSeek V3 como fallback barato (30× mas que Sonnet). "
                "Conseguir en openrouter.ai/keys (~$5 = miles de queries)."
            ),
            "data": {},
        }
    else:
        openrouter_modelo = os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat")

        def _do_ping_openrouter():
            try:
                import httpx as _httpx_or
                with _httpx_or.Client(timeout=10.0) as client:
                    r_or = client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {openrouter_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://motor-glosas-hus.fly.dev",
                            "X-Title": "Motor Glosas HUS",
                        },
                        json={
                            "model": openrouter_modelo,
                            "messages": [{"role": "user", "content": "ping"}],
                            "max_tokens": 3,
                            "temperature": 0,
                        },
                    )
                if r_or.status_code == 200:
                    return "ok", f"API key OK · ping {openrouter_modelo} exitoso · {openrouter_key[:10]}…", {}
                if r_or.status_code in (401, 403):
                    return "error", f"API key INVALIDA o sin permisos (HTTP {r_or.status_code})", {}
                if r_or.status_code == 429:
                    return "warning", "Rate limit hit — esperar 60s o agregar credito en openrouter.ai/credits", {}
                if r_or.status_code == 402:
                    return "error", "Sin credito — agregar fondos en openrouter.ai/credits", {}
                return "warning", f"Ping HTTP {r_or.status_code}: {r_or.text[:120]}", {}
            except Exception as _eor:
                return "warning", f"No se pudo hacer ping: {str(_eor)[:120]}", {}

        cache_key = f"openrouter::{openrouter_modelo}::{openrouter_key[:6]}"
        ping_estado, ping_msg, _ = _ping_cached(cache_key, _do_ping_openrouter)
        out["secciones"]["openrouter"] = {
            "estado": ping_estado,
            "mensaje": ping_msg,
            "data": {
                "modelo": openrouter_modelo,
                "key_prefix": openrouter_key[:10],
                "rol": "Fallback #1 (DeepSeek V3, ~30× mas barato que Sonnet)",
            },
        }

    # ─── Sentry (error tracking) ──────────────────────────────────
    sentry_dsn = os.getenv("SENTRY_DSN", "")
    if not sentry_dsn:
        out["secciones"]["sentry"] = {
            "estado": "warning",
            "mensaje": (
                "SENTRY_DSN no configurado — los errores en producción "
                "se pierden silenciosamente. Setup en 5 min: crear cuenta "
                "en sentry.io (free 5K events/mes), copiar DSN del "
                "proyecto y `fly secrets set SENTRY_DSN=https://...`"
            ),
            "data": {},
        }
    else:
        # Verificación liviana: ¿el SDK quedó inicializado con un cliente activo?
        sentry_activo = False
        cliente_info = ""
        try:
            import sentry_sdk
            cliente = sentry_sdk.Hub.current.client
            if cliente and cliente.dsn:
                sentry_activo = True
                # Sólo mostramos el host del DSN (sin la key)
                from urllib.parse import urlparse
                host = urlparse(cliente.dsn).hostname or "?"
                cliente_info = f"host={host} env={cliente.options.get('environment', '?')}"
        except Exception as _es:
            cliente_info = f"verif. falló: {str(_es)[:80]}"

        out["secciones"]["sentry"] = {
            "estado": "ok" if sentry_activo else "warning",
            "mensaje": (
                f"Sentry activo · {cliente_info}" if sentry_activo
                else f"SENTRY_DSN configurado pero el cliente no quedó activo ({cliente_info})"
            ),
            "data": {
                "dsn_prefix": sentry_dsn[:30] + "..." if len(sentry_dsn) > 30 else sentry_dsn,
                "environment": os.getenv("SENTRY_ENVIRONMENT", "production"),
                "traces_sample_rate": os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"),
            },
        }

    # ─── Telegram bot (alertas push) ──────────────────────────────
    telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not telegram_token:
        out["secciones"]["telegram"] = {
            "estado": "warning",
            "mensaje": (
                "TELEGRAM_BOT_TOKEN no configurado — los gestores no "
                "reciben alertas push de glosas urgentes. Setup en 2 min: "
                "@BotFather → /newbot → copiar token → "
                "`fly secrets set TELEGRAM_BOT_TOKEN=123:abc...`. Tras "
                "eso registrar webhook (curl -X POST .../setWebhook)."
            ),
            "data": {},
        }
    else:
        # Verificación liviana sin hacer ping (que cuesta network).
        # El usuario puede llamar /telegram/health autenticado para el ping real.
        vinculados = 0
        try:
            from sqlalchemy import func as _f
            from app.models.db import UsuarioRecord
            vinculados = (
                db.query(_f.count(UsuarioRecord.id))
                .filter(UsuarioRecord.telegram_chat_id.isnot(None))
                .filter(UsuarioRecord.activo == 1)
                .scalar() or 0
            )
        except Exception:
            pass
        out["secciones"]["telegram"] = {
            "estado": "ok",
            "mensaje": (
                f"Bot configurado · {vinculados} gestor/es vinculado/s. "
                f"Resumen diario corre a las 8:00 AM. "
                f"Probar: GET /telegram/health (autenticado)."
            ),
            "data": {
                "token_prefix": telegram_token[:10] + "...",
                "webhook_secret_set": bool(os.getenv("TELEGRAM_WEBHOOK_SECRET")),
                "vinculados": vinculados,
            },
        }

    # ─── PostHog (product analytics) ──────────────────────────────
    posthog_key = os.getenv("POSTHOG_API_KEY", "")
    if not posthog_key:
        out["secciones"]["posthog"] = {
            "estado": "warning",
            "mensaje": (
                "POSTHOG_API_KEY no configurada — no estamos midiendo "
                "qué gestores usan qué features ni dónde se traban. "
                "Setup en 3 min: posthog.com (free 1M eventos/mes), "
                "Project Settings → API Key → "
                "`fly secrets set POSTHOG_API_KEY=phc_...`"
            ),
            "data": {},
        }
    else:
        try:
            from app.services.posthog_service import disponible as ph_disponible
            activo = ph_disponible()
        except Exception:
            activo = False
        out["secciones"]["posthog"] = {
            "estado": "ok" if activo else "warning",
            "mensaje": (
                f"PostHog activo · trackeando glosa_analizada, "
                f"recepcion_importada, lote_auto_responder_completo"
                if activo
                else "POSTHOG_API_KEY configurada pero cliente no quedó activo"
            ),
            "data": {
                "key_prefix": posthog_key[:10],
                "host": os.getenv("POSTHOG_HOST", "https://us.posthog.com"),
            },
        }

    # ─── Lotes de importación recientes (últimos 7 días) ──────────
    try:
        umbral_lote = datetime.now(timezone.utc) - timedelta(days=7)
        n_lotes = (
            db.query(func.count(LoteImportacionRecord.id))
            .filter(LoteImportacionRecord.iniciado_en >= umbral_lote)
            .scalar() or 0
        )
        n_procesando = (
            db.query(func.count(LoteImportacionRecord.id))
            .filter(LoteImportacionRecord.estado == "PROCESANDO")
            .scalar() or 0
        )
        out["secciones"]["lotes_importacion"] = {
            "estado": "warning" if n_procesando > 5 else "ok",
            "mensaje": f"{n_lotes} lotes en últimos 7 días, {n_procesando} en PROCESANDO actualmente",
            "data": {"total_7d": n_lotes, "procesando_ahora": n_procesando},
        }
    except Exception as e:
        out["secciones"]["lotes_importacion"] = {"estado": "error", "mensaje": str(e), "data": {}}

    # ─── Cláusulas de contratos extraídas ─────────────────────────
    try:
        n_clausulas = db.query(func.count(ClausulaContrato.id)).scalar() or 0
        contratos_con_pdf = (
            db.query(func.count(ContratoRecord.eps))
            .filter(ContratoRecord.pdf_path.isnot(None))
            .scalar() or 0
        )
        out["secciones"]["clausulas_contratos"] = {
            "estado": "ok" if n_clausulas > 0 else "warning",
            "mensaje": f"{n_clausulas} cláusulas extraídas de {contratos_con_pdf} contratos con PDF subido",
            "data": {
                "clausulas_total": n_clausulas,
                "contratos_con_pdf": contratos_con_pdf,
            },
        }
    except Exception as e:
        out["secciones"]["clausulas_contratos"] = {"estado": "error", "mensaje": str(e), "data": {}}

    # ─── Volumen de Fly montado ───────────────────────────────────
    try:
        soportes_root = os.getenv("SOPORTES_ROOT", "/data/soportes")
        existe = os.path.exists(soportes_root)
        try:
            disponible_bytes = (
                __import__("shutil").disk_usage(soportes_root).free if existe else 0
            )
            mb_disponible = round(disponible_bytes / (1024 * 1024), 1) if disponible_bytes else 0
        except Exception:
            mb_disponible = -1
        out["secciones"]["volumen_fly"] = {
            "estado": "ok" if existe else "error",
            "mensaje": (
                f"Volumen montado en {soportes_root}, {mb_disponible} MB disponibles"
                if existe
                else f"Volumen NO montado en {soportes_root}"
            ),
            "data": {"path": soportes_root, "existe": existe, "mb_disponibles": mb_disponible},
        }
    except Exception as e:
        out["secciones"]["volumen_fly"] = {"estado": "error", "mensaje": str(e), "data": {}}

    # Estado global agregado
    estados = [s.get("estado") for s in out["secciones"].values()]
    if "error" in estados:
        out["estado_global"] = "error"
    elif "warning" in estados:
        out["estado_global"] = "warning"
    else:
        out["estado_global"] = "ok"

    return out
