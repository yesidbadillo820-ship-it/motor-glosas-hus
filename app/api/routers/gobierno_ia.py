"""Gobierno de IA: cuánto gasta la IA, en qué, quién la usa y con qué caché.

Cada llamada al LLM queda registrada (ai_calls) desde hace meses; lo que
no existía era la vista que las cuenta. Este resumen responde las
preguntas de gobierno: gasto de hoy/semana/mes, qué modelos consumen, qué
usuarios la usan, cuánto ahorra el caché de prompts y qué glosas
resultaron más caras de defender.

Solo lectura. La ven coordinación y administración: el gasto de IA es
información de gestión, no operativa.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.deps import get_coordinador_o_admin
from app.database import get_db
from app.models.db import AICallRecord, UsuarioRecord

router = APIRouter(prefix="/gobierno-ia", tags=["gobierno-ia"])


def _resumen_desde(db: Session, desde: datetime) -> dict:
    fila = (
        db.query(
            func.count(AICallRecord.id),
            func.coalesce(func.sum(AICallRecord.cost_usd), 0.0),
        )
        .filter(AICallRecord.creado_en >= desde)
        .first()
    )
    return {"llamadas": int(fila[0] or 0), "costo_usd": round(float(fila[1] or 0.0), 4)}


@router.get("/resumen")
def resumen_gobierno_ia(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """El tablero de gobierno completo en una llamada (ventana: 30 días)."""
    ahora = datetime.now(timezone.utc)
    desde_30 = ahora - timedelta(days=30)

    gasto = {
        "hoy": _resumen_desde(db, ahora - timedelta(days=1)),
        "semana": _resumen_desde(db, ahora - timedelta(days=7)),
        "mes": _resumen_desde(db, desde_30),
    }

    por_modelo = [
        {
            "proveedor": p,
            "modelo": m,
            "llamadas": int(n),
            "costo_usd": round(float(c or 0), 4),
            "tokens_entrada": int(ti or 0),
            "tokens_salida": int(to or 0),
            "latencia_promedio_ms": int(lat or 0),
        }
        for p, m, n, c, ti, to, lat in db.query(
            AICallRecord.proveedor,
            AICallRecord.modelo,
            func.count(AICallRecord.id),
            func.sum(AICallRecord.cost_usd),
            func.sum(AICallRecord.input_tokens),
            func.sum(AICallRecord.output_tokens),
            func.avg(AICallRecord.latency_ms),
        )
        .filter(AICallRecord.creado_en >= desde_30)
        .group_by(AICallRecord.proveedor, AICallRecord.modelo)
        .order_by(func.sum(AICallRecord.cost_usd).desc())
        .all()
    ]

    por_usuario = [
        {"usuario": u or "(sistema)", "llamadas": int(n), "costo_usd": round(float(c or 0), 4)}
        for u, n, c in db.query(
            AICallRecord.user_email,
            func.count(AICallRecord.id),
            func.sum(AICallRecord.cost_usd),
        )
        .filter(AICallRecord.creado_en >= desde_30)
        .group_by(AICallRecord.user_email)
        .order_by(func.sum(AICallRecord.cost_usd).desc())
        .limit(10)
        .all()
    ]

    # Caché de prompts: cuánto de lo leído vino gratis (o casi) del caché
    tot = (
        db.query(
            func.coalesce(func.sum(AICallRecord.input_tokens), 0),
            func.coalesce(func.sum(AICallRecord.cache_read_input_tokens), 0),
            func.coalesce(func.sum(AICallRecord.cache_creation_input_tokens), 0),
        )
        .filter(AICallRecord.creado_en >= desde_30)
        .first()
    )
    entrada, leido_cache, creado_cache = int(tot[0]), int(tot[1]), int(tot[2])
    base = entrada + leido_cache
    cache = {
        "tokens_leidos_de_cache": leido_cache,
        "tokens_creacion_cache": creado_cache,
        "porcentaje_cacheado": round(100.0 * leido_cache / base, 1) if base else 0.0,
    }

    glosas_caras = [
        {"glosa_id": int(g), "llamadas": int(n), "costo_usd": round(float(c or 0), 4)}
        for g, n, c in db.query(
            AICallRecord.glosa_id,
            func.count(AICallRecord.id),
            func.sum(AICallRecord.cost_usd),
        )
        .filter(AICallRecord.creado_en >= desde_30, AICallRecord.glosa_id.isnot(None))
        .group_by(AICallRecord.glosa_id)
        .order_by(func.sum(AICallRecord.cost_usd).desc())
        .limit(5)
        .all()
    ]

    return {
        "ventana_dias": 30,
        "gasto": gasto,
        "por_modelo": por_modelo,
        "por_usuario": por_usuario,
        "cache": cache,
        "glosas_mas_caras": glosas_caras,
    }


@router.get("/probar-proveedores")
async def probar_proveedores(
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Prueba de conexión: ¿responde cada proveedor de IA configurado?

    Una llamada mínima (dos palabras) a cada proveedor para saber si la
    clave sirve, SIN gastar una glosa. Nació del 04-08-2026: la única
    forma de saber si una clave nueva funcionaba era analizar una glosa
    de verdad y ver si fallaba.
    """
    from app.core.config import get_settings
    from app.services.glosa_service import GlosaService, _causa_corta

    cfg = get_settings()
    svc = GlosaService(
        groq_api_key=cfg.groq_api_key,
        anthropic_api_key=cfg.anthropic_api_key,
        primary_ai=cfg.primary_ai,
    )
    sistema = "Responde solo la palabra LISTO."
    usuario = "Prueba de conexión."

    proveedores = []
    for nombre, clave, fn in (
        ("groq", cfg.groq_api_key, lambda: svc._llamar_groq_con_retry(sistema, usuario)),
        ("anthropic", cfg.anthropic_api_key, lambda: svc._llamar_anthropic(sistema, usuario)),
    ):
        # El prefijo de la clave probada (10 caracteres, no revela nada) es
        # lo que permite comparar contra el log de arranque: si no coinciden,
        # hay otro motor vivo respondiendo con la clave anterior.
        pref = (clave or "")[:10]
        if not clave:
            proveedores.append(
                {
                    "proveedor": nombre,
                    "estado": "SIN CLAVE",
                    "detalle": "no hay clave configurada para este proveedor",
                    "clave_probada": "",
                    "es_principal": cfg.primary_ai == nombre,
                }
            )
            continue
        try:
            contenido, modelo = await fn()
            proveedores.append(
                {
                    "proveedor": nombre,
                    "estado": "OK",
                    "detalle": f"respondió con {modelo}",
                    "clave_probada": pref,
                    "es_principal": cfg.primary_ai == nombre,
                }
            )
        except Exception as e:
            proveedores.append(
                {
                    "proveedor": nombre,
                    "estado": "FALLA",
                    "detalle": _causa_corta(e),
                    "clave_probada": pref,
                    "es_principal": cfg.primary_ai == nombre,
                }
            )

    hay_alguno = any(p["estado"] == "OK" for p in proveedores)
    principal = next((p for p in proveedores if p["es_principal"]), None)
    if principal and principal["estado"] == "OK":
        veredicto = f"Todo listo: {principal['proveedor'].upper()} (tu principal) responde."
    elif hay_alguno:
        ok = next(p for p in proveedores if p["estado"] == "OK")
        veredicto = (
            f"El sistema funciona con {ok['proveedor'].upper()}, pero tu proveedor "
            f"principal no responde: revisá su clave."
        )
    else:
        veredicto = (
            "Ningún proveedor responde: el análisis de glosas no va a funcionar "
            "hasta corregir al menos una clave."
        )

    # Esta prueba la contesta EL motor que atendió la petición. Si hay más de
    # uno vivo, el próximo análisis puede caer en otro con otra clave: decirlo
    # aquí evita el «pero si la prueba salió verde».
    motores = []
    try:
        from app.services.motor_proceso import motores_vivos

        motores = motores_vivos()
    except Exception:
        motores = []
    if len(motores) > 1:
        # 04-08-2026: el aviso anterior mandaba a «cerrar los sobrantes» y el
        # otro motor resultó ser el de la página por internet. Lo que hay que
        # decir no es «cerrá», es «esta prueba vale para ESTE motor».
        mio = next((m for m in motores if m.get("soy_yo")), None)
        otros = ", ".join(f"puerto {m.get('puerto')}" for m in motores if not m.get("soy_yo"))
        veredicto = (
            f"OJO: esta prueba la contestó el motor del puerto "
            f"{(mio or {}).get('puerto', '?')}. En este equipo hay {len(motores)} "
            f"motores ({otros} además de este) y cada uno tiene su propia copia de "
            f"las claves: si trabajás desde la página por internet, probá desde ahí. " + veredicto
        )

    return {
        "principal_configurado": cfg.primary_ai,
        "funciona": hay_alguno,
        "veredicto": veredicto,
        "proveedores": proveedores,
        "motores_vivos": len(motores),
    }
