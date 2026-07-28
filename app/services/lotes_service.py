"""Lotes de portal — Fase 1 de la app unificada (jul-2026).

Orquesta el ciclo de vida de un lote: parsear el Excel consolidado que sube
el auditor (reutilizando el parser canónico de tools/responder_glosas_
coosalud.py, que es el mismo que usa el bot en el PC del hospital), crear
las filas por factura, y manejar la cola de tareas que el agente local
reclama y reporta.
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.db import (
    FACTURA_LOTE_ESTADOS_EXITO,
    FACTURA_LOTE_ESTADO_PENDIENTE,
    LOTE_ESTADO_COMPLETADO,
    LOTE_ESTADO_COMPLETADO_CON_PENDIENTES,
    LOTE_ESTADO_EN_COLA,
    LOTE_ESTADO_EN_PROCESO,
    LOTE_ESTADO_ERROR,
    TAREA_ESTADO_COMPLETADA,
    TAREA_ESTADO_ERROR,
    TAREA_ESTADO_PENDIENTE,
    TAREA_ESTADO_RECLAMADA,
    FacturaLoteRecord,
    LoteRecord,
    TareaLoteRecord,
)

logger = logging.getLogger("motor_glosas")

PAGADORES_SOPORTADOS = {"COOSALUD"}
MAX_EXCEL_BYTES = 20 * 1024 * 1024  # consolidados reales pesan < 5 MB


def parsear_excel_coosalud(contenido: bytes, hoja: str, incluir_calidad: bool) -> dict[str, dict]:
    """Parsea el Excel consolidado con el MISMO parser del bot.

    tools/responder_glosas_coosalud.leer_excel es la fuente de verdad
    (match tolerante de hoja, exclusión de CALIDAD, RE9502 sin soporte):
    si la app parseara distinto de lo que después ejecuta el bot, el
    semáforo de la UI mentiría. leer_excel lee de disco, así que el
    upload pasa por un archivo temporal.

    Lanza ValueError si falta la hoja o alguna columna obligatoria.
    """
    from tools.responder_glosas_coosalud import leer_excel

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(contenido)
        ruta = Path(tmp.name)
    try:
        return leer_excel(ruta, hoja, incluir_calidad=incluir_calidad)
    finally:
        ruta.unlink(missing_ok=True)


def crear_lote(
    db: Session,
    *,
    contenido: bytes,
    nombre_archivo: str,
    pagador: str,
    hoja: str,
    incluir_calidad: bool,
    creado_por: str,
) -> LoteRecord:
    """Parsea el Excel, crea el lote con sus facturas y encola la tarea."""
    pagador = pagador.strip().upper()
    if pagador not in PAGADORES_SOPORTADOS:
        raise ValueError(
            f"Pagador '{pagador}' no soportado todavía. Disponibles: {sorted(PAGADORES_SOPORTADOS)}"
        )
    facturas = parsear_excel_coosalud(contenido, hoja, incluir_calidad)
    if not facturas:
        raise ValueError("El Excel no tiene facturas con glosas para responder.")

    lote = LoteRecord(
        creado_por=creado_por,
        pagador=pagador,
        nombre_archivo=nombre_archivo,
        hoja=hoja,
        incluir_calidad=1 if incluir_calidad else 0,
        estado=LOTE_ESTADO_EN_COLA,
        total_facturas=len(facturas),
        total_glosas=sum(len(g["ids"]) for f in facturas.values() for g in f["grupos"]),
        total_calidad=sum(f["calidad"] for f in facturas.values()),
        excel_archivo=contenido,
    )
    db.add(lote)
    db.flush()

    for factura, info in sorted(facturas.items()):
        db.add(
            FacturaLoteRecord(
                lote_id=lote.id,
                factura=factura,
                grupos=len(info["grupos"]),
                glosas=sum(len(g["ids"]) for g in info["grupos"]),
                calidad=info["calidad"],
                requiere_soporte=1 if any(g["es_soporte"] for g in info["grupos"]) else 0,
                estado=FACTURA_LOTE_ESTADO_PENDIENTE,
            )
        )
    db.add(TareaLoteRecord(lote_id=lote.id, tipo=f"RESPONDER_{pagador}"))
    db.commit()
    db.refresh(lote)
    logger.info(
        f"Lote {lote.id} creado por {creado_por}: {pagador} '{nombre_archivo}' "
        f"({lote.total_facturas} facturas, {lote.total_glosas} glosas)."
    )
    return lote


def reclamar_tarea(db: Session, agente: str) -> TareaLoteRecord | None:
    """Entrega la tarea pendiente más antigua al agente, o None si no hay.

    El claim es un UPDATE condicionado por estado==PENDIENTE: si dos
    agentes piden a la vez, solo uno ve rowcount=1 y el otro reintenta
    con la siguiente (en la práctica hay un solo agente, pero el guard
    evita corridas dobles del mismo lote).
    """
    while True:
        tarea = (
            db.query(TareaLoteRecord)
            .filter(TareaLoteRecord.estado == TAREA_ESTADO_PENDIENTE)
            .order_by(TareaLoteRecord.id)
            .first()
        )
        if tarea is None:
            return None
        filas = (
            db.query(TareaLoteRecord)
            .filter(
                TareaLoteRecord.id == tarea.id,
                TareaLoteRecord.estado == TAREA_ESTADO_PENDIENTE,
            )
            .update(
                {
                    "estado": TAREA_ESTADO_RECLAMADA,
                    "agente": agente,
                    "reclamada_en": datetime.now(timezone.utc),
                }
            )
        )
        if filas:
            db.query(LoteRecord).filter(LoteRecord.id == tarea.lote_id).update(
                {"estado": LOTE_ESTADO_EN_PROCESO}
            )
            db.commit()
            db.refresh(tarea)
            return tarea
        db.rollback()


def aplicar_resultados(db: Session, lote_id: int, resultados: list[dict]) -> int:
    """Actualiza el estado por factura con lo que reportó el agente.

    Cada resultado es una fila del CSV del bot: {factura, estado, detalle}.
    Facturas desconocidas (p. ej. residuales que el bot encontró en el
    portal pero no estaban en el Excel) se agregan al lote para que la UI
    las muestre en vez de perderlas. Devuelve cuántas filas aplicó.
    """
    aplicadas = 0
    for r in resultados:
        factura = str(r.get("factura", "")).strip()
        estado = str(r.get("estado", "")).strip()
        if not factura or not estado:
            continue
        fila = (
            db.query(FacturaLoteRecord)
            .filter(
                FacturaLoteRecord.lote_id == lote_id,
                FacturaLoteRecord.factura == factura,
            )
            .first()
        )
        if fila is None:
            fila = FacturaLoteRecord(lote_id=lote_id, factura=factura)
            db.add(fila)
        fila.estado = estado
        fila.detalle = str(r.get("detalle", "") or "") or None
        aplicadas += 1
    return aplicadas


def completar_tarea(
    db: Session,
    tarea: TareaLoteRecord,
    *,
    exito: bool,
    resultados: list[dict],
    error: str | None = None,
) -> LoteRecord:
    """Cierra la tarea, aplica los resultados y calcula el estado del lote."""
    aplicar_resultados(db, tarea.lote_id, resultados)
    tarea.estado = TAREA_ESTADO_COMPLETADA if exito else TAREA_ESTADO_ERROR
    tarea.terminada_en = datetime.now(timezone.utc)
    tarea.error = error

    lote = db.query(LoteRecord).filter(LoteRecord.id == tarea.lote_id).first()
    facturas = db.query(FacturaLoteRecord).filter(FacturaLoteRecord.lote_id == tarea.lote_id).all()
    conteo: dict[str, int] = {}
    for f in facturas:
        conteo[f.estado] = conteo.get(f.estado, 0) + 1
    pendientes = sum(n for estado, n in conteo.items() if estado not in FACTURA_LOTE_ESTADOS_EXITO)
    if not exito:
        lote.estado = LOTE_ESTADO_ERROR
    elif pendientes:
        lote.estado = LOTE_ESTADO_COMPLETADO_CON_PENDIENTES
    else:
        lote.estado = LOTE_ESTADO_COMPLETADO
    resumen = {"estados": conteo, "pendientes": pendientes}
    lote.resumen = json.dumps(resumen, ensure_ascii=False)
    tarea.resultado = json.dumps(
        {"filas_reportadas": len(resultados), **resumen}, ensure_ascii=False
    )
    db.commit()
    db.refresh(lote)
    logger.info(
        f"Lote {lote.id} → {lote.estado} "
        f"({len(resultados)} filas del agente, {pendientes} pendientes)."
    )
    return lote
