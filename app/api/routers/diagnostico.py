"""
diagnostico.py — Status / Diagnostic page del motor (A.2 del plan UX).

Endpoint admin que devuelve health de TODO el sistema en un solo
JSON:
  - Conexión a la BD (SQLite local en la VM del HUS o Postgres remoto)
  - Estado del indexer de soportes (cuántos archivos, última build)
  - Estados de los schedulers (mantenimiento, soportes-reindex,
    pre-análisis)
  - Disponibilidad de Anthropic + Groq (test ping rápido)
  - Estadísticas de glosas / lotes / usuarios
  - Últimos errores en logs

Uso: el admin entra a /admin/diagnostico (tab del SPA) y ve un panel
verde-amarillo-rojo con cada componente. Si algo está rojo, tiene
botón "Reindexar ahora" para auto-fix.

Nota histórica: este motor migró el 23-jun-2026 de Fly.io + Neon Postgres
a self-hosted en VM Google Cloud + SQLite en volumen local + cloudflared
tunnel ($0/mes). Las labels y mensajes de este endpoint se actualizaron
para reflejar el nuevo stack.
"""

from __future__ import annotations
import os
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.api.deps import get_admin
from app.core.config import get_settings
from app.models.db import (
    UsuarioRecord,
    GlosaRecord,
    LoteImportacionRecord,
    ContratoRecord,
    ClausulaContrato,
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
    # 19-08-2026. Este número estaba escrito a mano y se quedó en 5.4.0
    # mientras la aplicación iba en 5.5.0: el encabezado del panel decía una
    # versión y la sección de abajo otra, en la misma pantalla. Es la tercera
    # vez hoy que un valor copiado a mano se desfasa de su fuente —pasó con la
    # cadena de modelos y con el ejemplo del .env—, así que se lee de donde
    # vive de verdad.
    from app.core.config import get_settings as _get_settings

    out: dict = {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "version": _get_settings().app_version,
        "secciones": {},
    }

    # ─── Quién está atendiendo (va primero: manda sobre todo lo demás) ──
    # 04-08-2026: dos uvicorn vivos sobre el mismo puerto hicieron que el
    # arranque dijera `groq=OK gsk_vn06EE…` y esta misma pantalla dijera
    # `gsk_5CxaRq…`. Si hay más de un motor, ningún otro dato de este panel
    # es confiable: puede venir del motor viejo.
    try:
        from app.services.motor_proceso import estado_motor

        out["secciones"]["motor"] = estado_motor()
    except Exception as e:  # nunca tumbar el diagnóstico por el diagnóstico
        out["secciones"]["motor"] = {
            "estado": "warning",
            "mensaje": f"No se pudo inspeccionar el proceso: {e}",
            "data": {},
        }

    # ─── Qué versión está sirviendo ───────────────────────────────
    #
    # 19-08-2026. Va justo detrás del motor —que manda, porque si hay dos
    # motores corriendo ningún otro dato del panel es confiable—. Hoy se perdieron horas
    # persiguiendo un defecto que ya estaba corregido en disco, porque no
    # había forma de saber si el motor que respondía tenía el código nuevo o
    # seguía con el viejo en memoria. Con el commit y la hora de arranque
    # juntos, esa pregunta se responde de un vistazo.
    try:
        from app.api.routers.sistema import info_version

        _v = info_version()
        out["secciones"]["version"] = {
            "estado": "ok",
            "mensaje": (
                f"Motor {_v['version']} · código {_v['commit']} · "
                f"arrancó el {_v['proceso_arrancado_en']}"
            ),
            "data": {
                "commit": _v["commit"],
                "commit_completo": _v["commit_full"],
                "proceso_arrancado_en": _v["proceso_arrancado_en"],
                "version": _v["version"],
            },
        }
    except Exception as e:  # noqa: BLE001 - el diagnóstico nunca se tumba
        out["secciones"]["version"] = {
            "estado": "warning",
            "mensaje": f"No se pudo leer la versión: {e}",
            "data": {},
        }

    # ─── Base de datos (SQLite local en VM HUS o Postgres remoto) ──
    # Detecta el tipo desde DATABASE_URL: SQLite (self-hosted, default
    # desde 23-jun-2026) o Postgres (Neon antiguo). Mostrar correctamente
    # para que el panel no diga "Neon Postgres" cuando ya migramos.
    try:
        n_glosas = db.query(func.count(GlosaRecord.id)).scalar() or 0
        n_usuarios = db.query(func.count(UsuarioRecord.id)).scalar() or 0
        n_contratos = db.query(func.count(ContratoRecord.eps)).scalar() or 0
        _db_url = os.getenv("DATABASE_URL", "")
        if _db_url.startswith("sqlite"):
            _db_label = "SQLite local (volumen /data)"
        elif "neon" in _db_url.lower():
            _db_label = "Neon Postgres"
        elif _db_url.startswith("postgres"):
            _db_label = "Postgres"
        else:
            _db_label = "Base de datos"
        out["secciones"]["base_de_datos"] = {
            "estado": "ok",
            "mensaje": (
                f"{_db_label} conectada · {n_glosas} glosas, "
                f"{n_usuarios} usuarios, {n_contratos} contratos"
            ),
            "data": {
                "tipo": _db_label,
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
                "El índice de soportes está vacío. Si el motor debe leer el "
                "servidor de radicación, la carpeta se escribe en "
                "«C:\\motor-glosas\\repo\\config\\soportes_root.txt» (una sola "
                "línea, por ejemplo \\\\Prime\\radicacion_2026). Si no, suba los "
                "PDF desde la pantalla «Soportes». Después, botón «Reindexar "
                "soportes» acá mismo."
            )
        elif stats.get("construyendo"):
            # 19-08-2026. Con el servidor real esto pasa de verdad: 432.314
            # archivos tardan un buen rato en recorrerse la primera vez. El
            # panel decía «la última build es vieja (>24h)» —porque no había
            # ninguna todavía— y eso invita a apretar «Reindexar soportes» y
            # empezar de cero un trabajo de horas. Está trabajando: hay que
            # decirlo y dejarlo en paz.
            estado = "ok"
            mensaje = (
                f"Indexando el servidor de radicación… lleva "
                f"{stats['facturas_indexadas']} facturas y "
                f"{stats.get('archivos_indexados', 0)} archivos. "
                "NO le dé «Reindexar soportes»: eso lo haría empezar de nuevo. "
                "Mientras tanto se puede buscar, pero puede que una factura "
                "reciente todavía no aparezca."
            )
        else:
            ultima = stats.get("construido_hace_seg")
            if ultima is None:
                estado = "warning"
                mensaje = (
                    f"{stats['facturas_indexadas']} facturas en el índice, pero "
                    "todavía no ha terminado ninguna revisión completa del "
                    "servidor. Use «Reindexar soportes» para arrancarla."
                )
            elif ultima > 24 * 3600:
                estado = "warning"
                mensaje = (
                    f"{stats['facturas_indexadas']} facturas indexadas, pero la "
                    "última revisión del servidor fue hace más de un día: las "
                    "facturas radicadas desde entonces pueden no aparecer."
                )
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

    # ─── Anthropic API key configurada + test ping ─────────────────
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not anthropic_key:
        out["secciones"]["anthropic"] = {
            "estado": "error",
            "mensaje": (
                "Falta la clave de Anthropic. Sin ella el Auditor Forense no "
                "lee los soportes y el dictamen sale sin citar folios — no da "
                "error, simplemente no mejora. Para ponerla: abra "
                "«notepad C:\\motor-glosas\\repo\\.env», agregue la línea "
                "«ANTHROPIC_API_KEY=» con la clave, guarde, y reinicie con "
                "«C:\\motor-glosas\\repo\\tools\\autodeploy_motor_local.cmd»."
            ),
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
                        return (
                            "error",
                            f"🚨 Sin créditos — recargar en console.anthropic.com/settings/billing. ({err_msg[:120]})",
                            {},
                        )
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
                "primary_ai": os.getenv("PRIMARY_AI", "groq"),
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
        # Cadena de modelos Groq desde Settings (12-jun-2026): primario +
        # 2 fallbacks internos antes de saltar a Anthropic. Espejo de
        # GlosaService._modelos_groq (dedupe por si un override por env
        # repite un modelo). Mismo patrón que la sección Anthropic, que ya
        # muestra su modelo activo.
        cfg = get_settings()
        cadena_groq: list[str] = []
        for _m in (cfg.groq_model, cfg.groq_model_fallback_1, cfg.groq_model_fallback_2):
            if _m and _m not in cadena_groq:
                cadena_groq.append(_m)
        partes_cadena = [f"Primario: {cadena_groq[0]}"] + [
            f"Fallback {i}: {m}" for i, m in enumerate(cadena_groq[1:], start=1)
        ]
        out["secciones"]["groq"] = {
            "estado": "ok",
            "mensaje": (
                f"API key configurada (fallback de Anthropic, prefijo {groq_key[:10]}…) · "
                + " · ".join(partes_cadena)
            ),
            "data": {
                "modelo": cfg.groq_model,
                "modelo_fallback_1": cfg.groq_model_fallback_1,
                "modelo_fallback_2": cfg.groq_model_fallback_2,
                "cadena_modelos": cadena_groq,
            },
        }

    # ─── Gemini API key + ping (SOLO OCR de PDFs escaneados) ────────
    # Jun-2026: Gemini ya no genera dictámenes — quedó como fallback de
    # lectura de PDFs (pdf_service + pdf_fallback_patch). Sin esta key,
    # todo el OCR de escaneados cae sobre Anthropic (quema créditos).
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if not gemini_key:
        out["secciones"]["gemini"] = {
            "estado": "warning",
            "mensaje": (
                "GEMINI_API_KEY no configurada — sin ella el OCR de PDFs "
                "escaneados depende 100% de Anthropic (gasta créditos de "
                "Claude). Agrega clave en aistudio.google.com/apikey (gratis)."
            ),
            "data": {},
        }
    else:
        # 19-08-2026. Acá estaba el CUARTO modelo escrito a mano que se
        # desfasa: `os.getenv("GEMINI_MODEL", "gemini-2.0-flash")`. Como el
        # .env del hospital no define esa variable, el panel usaba el valor de
        # respaldo —un modelo que Google retiró— e ignoraba la configuración,
        # que ya decía `gemini-flash-latest`. Resultado: el panel reportaba un
        # 404 permanente de un modelo que el motor ya no usa.
        from app.core.config import get_settings as _cfg_gemini

        gemini_modelo = os.getenv("GEMINI_MODEL") or _cfg_gemini().gemini_model

        def _do_ping_gemini():
            try:
                import httpx as _httpx_g

                # Key por header x-goog-api-key, NUNCA en la URL: el logger
                # INFO de httpx escribe la URL completa y la key quedaba en
                # texto plano en los logs de Fly (visto en prod 10-jun-2026).
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_modelo}:generateContent"
                payload = {
                    "contents": [{"role": "user", "parts": [{"text": "ping"}]}],
                    "generationConfig": {"maxOutputTokens": 4, "temperature": 0},
                }
                with _httpx_g.Client(timeout=10.0) as client:
                    rg = client.post(url, json=payload, headers={"x-goog-api-key": gemini_key})
                if rg.status_code == 200:
                    return (
                        "ok",
                        f"API key OK · ping {gemini_modelo} exitoso · {gemini_key[:10]}…",
                        {},
                    )
                if rg.status_code in (400, 401, 403):
                    return "error", f"API key INVALIDA o sin permisos (HTTP {rg.status_code})", {}
                if rg.status_code == 429:
                    return (
                        "warning",
                        "Rate limit del tier gratis hit (HTTP 429). Esperar 60s o usar Anthropic/Groq.",
                        {},
                    )
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
                "rol": "solo OCR de PDFs escaneados (no genera dictámenes)",
                "free_tier_info": "15 RPM / 1500 RPD para Flash · 2 RPM / 50 RPD para Pro",
            },
        }

    # ─── Sentry (registro de errores) ─────────────────────────────
    #
    # 19-08-2026. Esta seccion mostraba un aviso ambar PERMANENTE diciendo que
    # los errores se pierden si no se configura Sentry. Yesid intento crear la
    # cuenta y se topo con que sentry.io le exige entrar por Fly.io -su correo
    # quedo amarrado a ese inicio de sesion-, asi que no puede activarlo.
    #
    # Un aviso que el auditor no puede resolver, dia tras dia, enseña a
    # ignorar los avisos. Es la misma leccion del ticker de noticias, que
    # llevaba tres meses en ambar sin que nadie pudiera hacer nada.
    #
    # Asi que el aviso solo sale cuando Sentry SI esta configurado, para
    # confirmar que quedo funcionando. Si no lo esta, esta pantalla se queda
    # callada: la integracion sigue montada y basta con poner SENTRY_DSN en el
    # .env para que se active y vuelva a aparecer acá en verde.
    sentry_dsn = os.getenv("SENTRY_DSN", "")
    if sentry_dsn:
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
                f"Sentry activo · {cliente_info}"
                if sentry_activo
                else f"SENTRY_DSN configurado pero el cliente no quedó activo ({cliente_info})"
            ),
            "data": {
                "dsn_prefix": sentry_dsn[:30] + "..." if len(sentry_dsn) > 30 else sentry_dsn,
                "environment": os.getenv("SENTRY_ENVIRONMENT", "production"),
                "traces_sample_rate": os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"),
            },
        }

    # ─── PostHog (product analytics) ──────────────────────────────
    #
    # 19-08-2026. Mismo caso que Sentry: aviso ambar permanente con
    # instrucciones de un servidor Linux (`sudo nano /opt/motor-glosas/.env`,
    # `docker compose restart`) que en el PC de cartera —Windows— nadie puede
    # seguir. Y ademas PostHog manda datos de uso a un tercero, cosa que en un
    # hospital hay que decidir a conciencia, no dejar como un pendiente que
    # parpadea. Solo se reporta si esta configurado.
    posthog_key = os.getenv("POSTHOG_API_KEY", "")
    if posthog_key:
        try:
            from app.services.posthog_service import disponible as ph_disponible

            activo = ph_disponible()
        except Exception:
            activo = False
        out["secciones"]["posthog"] = {
            "estado": "ok" if activo else "warning",
            "mensaje": (
                "PostHog activo · trackeando glosa_analizada, "
                "recepcion_importada, lote_auto_responder_completo"
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
            .scalar()
            or 0
        )
        n_procesando = (
            db.query(func.count(LoteImportacionRecord.id))
            .filter(LoteImportacionRecord.estado == "PROCESANDO")
            .scalar()
            or 0
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
            .scalar()
            or 0
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

    # ─── Volumen de datos montado (self-hosted: /data en la VM HUS) ──
    # Mantenemos la clave "volumen_fly" del JSON por backwards-compat con
    # el frontend que la consume — el mensaje y el label sí están
    # actualizados al stack actual (Google Cloud VM + bind mount Docker).
    try:
        soportes_root = os.getenv("SOPORTES_ROOT", "/data/soportes")
        existe = os.path.exists(soportes_root)
        try:
            disponible_bytes = __import__("shutil").disk_usage(soportes_root).free if existe else 0
            mb_disponible = round(disponible_bytes / (1024 * 1024), 1) if disponible_bytes else 0
        except Exception:
            mb_disponible = -1
        out["secciones"]["volumen_fly"] = {
            "estado": "ok" if existe else "error",
            "mensaje": (
                f"Volumen de datos montado en {soportes_root}, {mb_disponible} MB disponibles"
                if existe
                else (
                    f"No se llega a la carpeta de datos ({soportes_root}). "
                    "Si es una carpeta de red, revise que el PC tenga acceso; "
                    "si es local, que exista. La ruta se configura en "
                    "«C:\\motor-glosas\\repo\\config\\soportes_root.txt»."
                )
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
