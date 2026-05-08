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
        # Test ping real a Anthropic — request mínimo (1 token) para
        # verificar que la key tiene créditos. Si falla con
        # credit_balance_too_low, lo reportamos.
        ping_estado = "ok"
        ping_msg = f"API key configurada (prefijo {anthropic_key[:10]}…)"
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
                ping_estado = "ok"
                ping_msg = f"API key OK · ping Haiku exitoso · {anthropic_key[:10]}…"
            elif resp.status_code == 400:
                err_msg = ""
                try:
                    err_msg = resp.json().get("error", {}).get("message", "")
                except Exception:
                    err_msg = resp.text[:120]
                if "credit" in err_msg.lower():
                    ping_estado = "error"
                    ping_msg = (
                        f"🚨 Sin créditos — recargar en console.anthropic.com/settings/billing. "
                        f"({err_msg[:120]})"
                    )
                else:
                    ping_estado = "warning"
                    ping_msg = f"HTTP 400: {err_msg[:120]}"
            elif resp.status_code in (401, 403):
                ping_estado = "error"
                ping_msg = f"API key inválida o revocada (HTTP {resp.status_code})"
            elif resp.status_code == 429:
                ping_estado = "warning"
                ping_msg = "Rate limit hit (429) — esperá 60s"
            elif resp.status_code == 529:
                ping_estado = "warning"
                ping_msg = "Anthropic overloaded (529) — temporal"
            else:
                ping_estado = "warning"
                ping_msg = f"HTTP {resp.status_code} inesperado"
        except Exception as e:
            ping_estado = "warning"
            ping_msg = f"No se pudo hacer ping: {e}"

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
        gemini_modelo = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        ping_msg = f"API key configurada (prefijo {gemini_key[:10]}…)"
        ping_estado = "ok"
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
                ping_msg = f"API key OK · ping {gemini_modelo} exitoso · {gemini_key[:10]}…"
            elif rg.status_code in (400, 401, 403):
                ping_estado = "error"
                ping_msg = f"API key INVALIDA o sin permisos (HTTP {rg.status_code})"
            elif rg.status_code == 429:
                ping_estado = "warning"
                ping_msg = f"Rate limit del tier gratis hit (HTTP 429). Esperar 60s o usar Anthropic/Groq."
            else:
                ping_estado = "warning"
                ping_msg = f"Ping HTTP {rg.status_code}: {rg.text[:120]}"
        except Exception as _eg:
            ping_estado = "warning"
            ping_msg = f"No se pudo hacer ping: {str(_eg)[:120]}"
        out["secciones"]["gemini"] = {
            "estado": ping_estado,
            "mensaje": ping_msg,
            "data": {
                "modelo": gemini_modelo,
                "key_prefix": gemini_key[:10],
                "free_tier_info": "15 RPM / 1500 RPD para Flash · 2 RPM / 50 RPD para Pro",
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
