"""Centro de Inteligencia: la lista priorizada de QUÉ HACER HOY.

EL PROBLEMA QUE RESUELVE. La información para dirigir el día ya existe,
pero regada: los vencimientos en una pantalla, los contratos en otra, las
actas a medio cuadrar en el Excel, los análisis que salieron sin contrato
en la línea de tiempo de cada glosa. El coordinador arma la prioridad del
día a memoria — y lo que no se ve, se vence.

Acá el sistema barre TODA la operación y responde una sola pregunta:
«¿qué hay que hacer hoy y por cuánta plata?». Cada acción dice qué pasa,
por qué importa, cuánto vale y a qué pantalla ir a resolverla. La misma
lista la lee el auditor en la pantalla Inteligencia y la usa la IA del
chat para dirigir en vez de solo responder.

PRIORIDADES:
  1 — plata en riesgo YA: glosas ya vencidas, audiencias encima sin acta.
  2 — esta semana: por vencer, contratos que se acaban, defensas a SOAT
      pleno por falta de contrato (hay que confirmar prórrogas).
  3 — orden y aviso: actas con hallazgos, pagadores fuera de malla.

Cada fuente se barre por separado y protegida: si una falla, las demás
igual llegan — un diagnóstico incompleto avisa; uno caído no dirige nada.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.core.logging_utils import logger


def _accion(
    prioridad: int,
    icono: str,
    titulo: str,
    por_que: str,
    pantalla: str,
    etiqueta_boton: str,
    cantidad: int = 0,
    valor: float = 0.0,
    ids: list | None = None,
) -> dict[str, Any]:
    return {
        "prioridad": prioridad,
        "icono": icono,
        "titulo": titulo,
        "por_que": por_que,
        "cantidad": cantidad,
        "valor_en_juego": round(valor, 0),
        "pantalla": pantalla,
        "etiqueta_boton": etiqueta_boton,
        "ids": (ids or [])[:10],
    }


def _cop(v: float) -> str:
    return "$" + f"{v:,.0f}".replace(",", ".")


# ─── Las fuentes, cada una protegida ─────────────────────────────────────


def _vencimientos(db) -> list[dict]:
    from app.repositories.glosa_repository import GlosaRepository

    acciones = []
    alertas = GlosaRepository(db).alertas_proximas(dias_limite=5)
    vencidas = [g for g in alertas if (g.dias_restantes or 0) <= 0]
    por_vencer = [g for g in alertas if (g.dias_restantes or 0) > 0]
    if vencidas:
        valor = sum(float(g.valor_objetado or 0) for g in vencidas)
        acciones.append(
            _accion(
                1,
                "🔴",
                f"{len(vencidas)} glosa(s) YA VENCIDAS sin cerrar",
                f"Hay {_cop(valor)} en riesgo de perderse por término: la EPS puede "
                "ratificar de oficio lo no respondido a tiempo.",
                "vencimientos",
                "Ir a Vencimientos",
                cantidad=len(vencidas),
                valor=valor,
                ids=[g.id for g in vencidas],
            )
        )
    if por_vencer:
        valor = sum(float(g.valor_objetado or 0) for g in por_vencer)
        acciones.append(
            _accion(
                2,
                "🟠",
                f"{len(por_vencer)} glosa(s) vencen en 5 días o menos",
                f"{_cop(valor)} que todavía se salvan si se responden esta semana.",
                "vencimientos",
                "Ir a Vencimientos",
                cantidad=len(por_vencer),
                valor=valor,
                ids=[g.id for g in por_vencer],
            )
        )
    return acciones


def _malla(_db) -> list[dict]:
    from app.services import malla_contractual as mc

    estado = mc.estado_vigencia(date.today())
    acciones = []
    if estado["vencidos"]:
        nombres = ", ".join(
            f"{c['pagador']} ({c['numero'] or 'sin número'})" for c in estado["vencidos"][:4]
        )
        acciones.append(
            _accion(
                2,
                "📄",
                f"{len(estado['vencidos'])} contrato(s) VENCIDOS en la malla",
                f"{nombres}. Sin prórroga confirmada, cada análisis de esos pagadores "
                "se defiende a tarifa SOAT plena — confirmar con contratación.",
                "malla",
                "Ver Contratos",
                cantidad=len(estado["vencidos"]),
            )
        )
    if estado["por_vencer"]:
        nombres = ", ".join(
            f"{c['pagador']} (quedan {c['dias']} días)" for c in estado["por_vencer"][:4]
        )
        acciones.append(
            _accion(
                2,
                "⏳",
                f"{len(estado['por_vencer'])} contrato(s) se vencen pronto",
                f"{nombres}. Renegociar toma semanas: el aviso útil es este, no el del "
                "día del vencimiento.",
                "malla",
                "Ver Contratos",
                cantidad=len(estado["por_vencer"]),
            )
        )
    return acciones


def _verificaciones_sin_contrato(db) -> list[dict]:
    from app.models.db import AuditLogRecord

    desde = datetime.now(timezone.utc) - timedelta(days=30)
    filas = (
        db.query(AuditLogRecord)
        .filter(
            AuditLogRecord.accion == "VERIFICACION_CONTRACTUAL",
            AuditLogRecord.campo.in_(("SIN_CONTRATO_VIGENTE", "PAGADOR_FUERA_DE_MALLA")),
            AuditLogRecord.timestamp >= desde,
        )
        .order_by(AuditLogRecord.id.desc())
        .limit(200)
        .all()
    )
    if not filas:
        return []
    sin_contrato = [f for f in filas if f.campo == "SIN_CONTRATO_VIGENTE"]
    fuera = [f for f in filas if f.campo == "PAGADOR_FUERA_DE_MALLA"]
    acciones = []
    if sin_contrato:
        acciones.append(
            _accion(
                2,
                "⚖️",
                f"{len(sin_contrato)} análisis del mes se defendieron SIN contrato vigente",
                "La malla no tenía contrato el día del hecho y se defendió a SOAT "
                "pleno (lo correcto). Si contratación confirma prórrogas, esas "
                "defensas pueden mejorar: revisar los expedientes.",
                "expediente",
                "Abrir Expediente",
                cantidad=len(sin_contrato),
                ids=[f.registro_id for f in sin_contrato if f.registro_id],
            )
        )
    if fuera:
        acciones.append(
            _accion(
                3,
                "❓",
                f"{len(fuera)} análisis con pagador FUERA de la malla",
                "Ese pagador ni figura en la malla contractual: o es nuevo o el "
                "nombre llegó torcido. Avisar a contratación para completarla.",
                "malla",
                "Ver Contratos",
                cantidad=len(fuera),
                ids=[f.registro_id for f in fuera if f.registro_id],
            )
        )
    return acciones


def _conciliaciones_proximas(db) -> list[dict]:
    from app.models.db import ConciliacionRecord

    ahora = datetime.now(timezone.utc)
    filas = (
        db.query(ConciliacionRecord)
        .filter(ConciliacionRecord.fecha_audiencia.isnot(None))
        .filter(ConciliacionRecord.fecha_audiencia <= ahora + timedelta(days=7))
        .filter(
            (ConciliacionRecord.resultado.is_(None))
            | (ConciliacionRecord.resultado == "")
            | (ConciliacionRecord.resultado == "PROGRAMADA")
        )
        .order_by(ConciliacionRecord.fecha_audiencia)
        .limit(50)
        .all()
    )
    if not filas:
        return []
    # SQLite devuelve fechas sin zona: se normalizan antes de comparar.
    from app.core.tz import a_utc

    encima = [f for f in filas if f.fecha_audiencia and a_utc(f.fecha_audiencia) <= ahora]
    proximas = [f for f in filas if f not in encima]
    acciones = []
    if encima:
        acciones.append(
            _accion(
                1,
                "🧑‍⚖️",
                f"{len(encima)} audiencia(s) de conciliación ya pasaron sin resultado",
                "La audiencia figura programada y vencida sin acta registrada: "
                "cerrar el resultado o reprogramar, que sin acta no hay acuerdo.",
                "conciliacion",
                "Ir a Conciliación",
                cantidad=len(encima),
                ids=[f.id for f in encima],
            )
        )
    if proximas:
        acciones.append(
            _accion(
                2,
                "📅",
                f"{len(proximas)} audiencia(s) de conciliación en los próximos 7 días",
                "Preparar el acta de la mesa ANTES: subir el Excel a Conciliación, "
                "cuadrarlo y llegar con el acta lista para firmar.",
                "conciliacion",
                "Ir a Conciliación",
                cantidad=len(proximas),
                ids=[f.id for f in proximas],
            )
        )
    return acciones


def _actas_con_hallazgos(db) -> list[dict]:
    from app.models.db import AuditLogRecord

    desde = datetime.now(timezone.utc) - timedelta(days=14)
    filas = (
        db.query(AuditLogRecord)
        .filter(
            AuditLogRecord.accion.in_(("ACTA_EXCEL_OPTIMIZADA", "ACTA_EXCEL_PDF")),
            AuditLogRecord.campo == "CON_HALLAZGOS",
            AuditLogRecord.timestamp >= desde,
        )
        .order_by(AuditLogRecord.id.desc())
        .limit(20)
        .all()
    )
    # Un acta se pasa varias veces mientras se corrige: cuenta la última
    # pasada de cada archivo, y solo si sigue con hallazgos.
    vistos: dict[str, Any] = {}
    for f in filas:
        vistos.setdefault(f.valor_nuevo or "acta", f)
    if not vistos:
        return []
    detalles = []
    for nombre, f in list(vistos.items())[:3]:
        try:
            hallazgos = json.loads(f.detalle or "{}").get("resumen", {}).get("hallazgos")
        except Exception:
            hallazgos = None
        detalles.append(f"{nombre}" + (f" ({hallazgos} hallazgos)" if hallazgos else ""))
    return [
        _accion(
            3,
            "🧮",
            f"{len(vistos)} acta(s) de mesa siguen con hallazgos de cuadre",
            "Se subieron a Conciliación y el cuadre encontró problemas sin corregir: "
            + "; ".join(detalles)
            + ". Corregir la hoja REVISION antes de firmar.",
            "conciliacion",
            "Ir a Conciliación",
            cantidad=len(vistos),
        )
    ]


def _bots_con_problemas(db) -> list[dict]:
    """Los trabajos de bots del PC del HUS que fallaron o llevan mucho en
    cola sin que ningún agente los reclame."""
    from app.models.db import TrabajoBotRecord

    desde = datetime.now(timezone.utc) - timedelta(days=7)
    filas = (
        db.query(TrabajoBotRecord)
        .filter(TrabajoBotRecord.creado_en >= desde)
        .order_by(TrabajoBotRecord.id.desc())
        .limit(200)
        .all()
    )
    acciones = []
    errores = [t for t in filas if t.estado == "ERROR"]
    if errores:
        bots = ", ".join(sorted({t.bot_id for t in errores})[:4])
        acciones.append(
            _accion(
                2,
                "🤖",
                f"{len(errores)} trabajo(s) de bots FALLARON esta semana",
                f"Bots con error: {bots}. El motivo exacto está en «Ver registros» "
                "de cada tarjeta; se reintenta con un clic.",
                "automatizacion",
                "Ir a Automatización",
                cantidad=len(errores),
                ids=[t.id for t in errores],
            )
        )
    from app.core.tz import a_utc

    ahora = datetime.now(timezone.utc)
    estancados = [
        t
        for t in filas
        if t.estado == "PENDIENTE"
        and t.creado_en
        and (ahora - a_utc(t.creado_en)).total_seconds() > 3600
    ]
    if estancados:
        acciones.append(
            _accion(
                2,
                "⏸",
                f"{len(estancados)} trabajo(s) llevan más de una hora en cola sin agente",
                "Ningún PC del HUS los ha reclamado: revisar que el agente de bots "
                "(AGENTE_BOTS.cmd) esté abierto en algún equipo.",
                "automatizacion",
                "Ir a Automatización",
                cantidad=len(estancados),
                ids=[t.id for t in estancados],
            )
        )
    return acciones


def _lotes_a_medias(db) -> list[dict]:
    """Lotes que terminaron con facturas sin responder o fallaron."""
    from app.models.db import LoteRecord

    desde = datetime.now(timezone.utc) - timedelta(days=14)
    filas = (
        db.query(LoteRecord)
        .filter(
            LoteRecord.estado.in_(("COMPLETADO_CON_PENDIENTES", "ERROR")),
            LoteRecord.creado_en >= desde,
        )
        .order_by(LoteRecord.id.desc())
        .limit(20)
        .all()
    )
    if not filas:
        return []
    detalle = "; ".join(
        f"{lote.pagador} #{lote.id} ({lote.total_facturas} facturas, {lote.estado.replace('_', ' ').lower()})"
        for lote in filas[:3]
    )
    return [
        _accion(
            2,
            "📦",
            f"{len(filas)} lote(s) de respuesta masiva quedaron a medias",
            f"{detalle}. Las facturas que no entraron al portal siguen sin "
            "responder: revisar el semáforo del lote y relanzar lo pendiente.",
            "automatizacion",
            "Ir a Automatización",
            cantidad=len(filas),
            ids=[lote.id for lote in filas],
        )
    ]


_FUENTES = (
    ("vencimientos", _vencimientos),
    ("malla", _malla),
    ("verificaciones", _verificaciones_sin_contrato),
    ("conciliaciones", _conciliaciones_proximas),
    ("bots", _bots_con_problemas),
    ("lotes", _lotes_a_medias),
    ("actas", _actas_con_hallazgos),
)


def diagnostico(db) -> dict[str, Any]:
    """El barrido completo: acciones ordenadas por prioridad y plata."""
    acciones: list[dict] = []
    fuentes_caidas: list[str] = []
    for nombre, fuente in _FUENTES:
        try:
            acciones.extend(fuente(db))
        except Exception:
            logger.warning(f"[INTELIGENCIA] fuente '{nombre}' falló", exc_info=True)
            fuentes_caidas.append(nombre)

    acciones.sort(key=lambda a: (a["prioridad"], -a["valor_en_juego"]))
    valor_total = sum(a["valor_en_juego"] for a in acciones)
    urgentes = sum(1 for a in acciones if a["prioridad"] == 1)

    if acciones:
        if urgentes:
            titular = (
                f"Hoy hay {urgentes} frente(s) URGENTE(S) y {_cop(valor_total)} en juego. "
                "Empezar por lo rojo."
            )
        else:
            titular = (
                f"Sin incendios hoy. {len(acciones)} frente(s) por atender esta semana, "
                f"{_cop(valor_total)} en juego."
            )
    else:
        titular = (
            "Operación al día: sin vencimientos, sin contratos caídos, sin actas a medio cuadrar."
        )

    return {
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "titular": titular,
        "urgentes": urgentes,
        "valor_en_juego": valor_total,
        "acciones": acciones,
        "fuentes_caidas": fuentes_caidas,
    }
