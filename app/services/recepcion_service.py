"""
RecepcionService
================

Procesa el archivo Excel enviado por el equipo de recepción de glosas.

Columnas esperadas (en cualquier orden, por nombre de encabezado):
    GESTOR
    FECHA DE ENTREGA
    FECHA RADICACION          (cuando se radicó la factura a la EPS)
    FECHA DOCUMENTO DGH       (cuando la EPS emitió la glosa)
    FECHA RECEPCION           (cuando HUS recibió la glosa)
    ENTIDAD                   (nombre/código EPS)
    FACTURA
    CONSECUTIVO DGH           (identificador único de la glosa)
    VALOR GLOSA
    VENCE                     (fecha límite para responder)
    DEVOLUCION S/N
    DIAS RADICACION VS RECEPCION
    RADICADO                  (texto libre; si contiene "RATIFICADA", se aplica automáticamente el texto de respuesta para ratificadas)

Para cada fila:
- Si la glosa es RATIFICADA -> estado=RATIFICADA + dictamen con TEXTO_RATIFICADA.
- Si fue glosada extemporáneamente (>20 días hábiles entre radicación y DGH) ->
  estado=EXTEMPORANEA + dictamen con el texto estándar.
- Se calcula el semáforo por días hábiles restantes hasta VENCE.
- Upsert por CONSECUTIVO DGH (o por factura si no viene consecutivo).
"""
from __future__ import annotations

import re
from datetime import datetime, date, timedelta
from io import BytesIO
from typing import Optional

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.core.logging_utils import logger
from app.models.db import GlosaRecord
from app.services.glosa_service import (
    FERIADOS_CO,
    DIAS_HABILES_LIMITE_EXTEMPORANEA,
    TEXTO_RATIFICADA,
    generar_texto_extemporanea,
)


# ─── Parámetros de semáforo (días hábiles restantes) ─────────────────────────
SEMAFORO_VERDE_MIN = 11   # >10 días
SEMAFORO_AMARILLO_MIN = 5  # 5-10 días
# <5 días → ROJO; <=0 → NEGRO


# ─── Mapeo de columnas del Excel -> campo interno ────────────────────────────
COLUMN_ALIASES: dict[str, list[str]] = {
    "gestor": ["gestor"],
    "fecha_entrega": ["fecha de entrega", "fecha entrega"],
    "fecha_radicacion": ["fecha radicacion", "fecha de radicacion"],
    "fecha_documento_dgh": ["fecha documento dgh", "fecha dgh"],
    "fecha_recepcion": ["fecha recepcion", "fecha de recepcion"],
    "entidad": ["entidad", "eps"],
    "factura": ["factura"],
    "consecutivo_dgh": ["consecutivo dgh", "consecutivo"],
    "valor_glosa": ["valor glosa", "valor"],
    "vence": ["vence", "fecha vence"],
    "devolucion": ["devolucion s/n", "devolucion", "devolucion s", "s/n"],
    "dias_rad_rec": ["dias radicacion vs recepcion", "dias radicacion recepcion"],
    "radicado": ["radicado"],
}


def _normalizar(texto: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def _mapear_cabeceras(fila_encabezado: tuple) -> dict[str, int]:
    """Devuelve {nombre_interno: índice_columna}."""
    indices: dict[str, int] = {}
    for idx, celda in enumerate(fila_encabezado):
        valor = _normalizar(str(celda or ""))
        if not valor:
            continue
        for nombre_interno, aliases in COLUMN_ALIASES.items():
            if valor in aliases and nombre_interno not in indices:
                indices[nombre_interno] = idx
                break
    return indices


def _a_fecha(valor) -> Optional[datetime]:
    """Acepta datetime, date, o string con varios formatos comunes."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    s = str(valor).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _a_float(valor) -> float:
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    s = re.sub(r"[^\d]", "", str(valor))
    return float(s) if s else 0.0


def _dias_habiles(desde: datetime, hasta: datetime) -> int:
    """Cuenta días hábiles (excluye sábados, domingos y festivos Colombia)."""
    if desde >= hasta:
        return 0
    dias = 0
    curr = desde
    while curr < hasta:
        curr += timedelta(days=1)
        if curr.weekday() < 5 and curr.strftime("%Y-%m-%d") not in FERIADOS_CO:
            dias += 1
    return dias


def _semaforo(dias_restantes: int) -> str:
    if dias_restantes <= 0:
        return "NEGRO"
    if dias_restantes < SEMAFORO_AMARILLO_MIN:
        return "ROJO"
    if dias_restantes < SEMAFORO_VERDE_MIN:
        return "AMARILLO"
    return "VERDE"


def _es_ratificada(radicado_valor: str) -> bool:
    if not radicado_valor:
        return False
    return "RATIFICADA" in str(radicado_valor).upper()


def _dictamen_ratificada(eps: str, factura: str, radicado_info: str) -> str:
    return f"""
    <div style="background:#ede9fe;border-left:4px solid #7c3aed;padding:20px;margin:15px 0;border-radius:8px;">
        <h4 style="color:#5b21b6;margin:0 0 10px 0;">RESPUESTA A GLOSA RATIFICADA</h4>
        <p style="font-size:12px;color:#6d28d9;margin:0 0 10px 0;">
            <b>EPS:</b> {eps} | <b>Factura:</b> {factura} | <b>Observación recepción:</b> {radicado_info}
        </p>
        <p style="font-size:13px;line-height:1.8;color:#4c1d95;white-space:pre-wrap;">{TEXTO_RATIFICADA}</p>
    </div>
    """.strip()


def _dictamen_extemporanea(eps: str, factura: str, dias_transcurridos: int) -> str:
    texto = generar_texto_extemporanea(dias_transcurridos)
    return f"""
    <div style="background:#fee2e2;border-left:4px solid #dc2626;padding:20px;margin:15px 0;border-radius:8px;">
        <h4 style="color:#991b1b;margin:0 0 10px 0;">GLOSA EXTEMPORÁNEA ({dias_transcurridos} DÍAS HÁBILES)</h4>
        <p style="font-size:12px;color:#b91c1c;margin:0 0 10px 0;">
            <b>EPS:</b> {eps} | <b>Factura:</b> {factura}
        </p>
        <p style="font-size:13px;line-height:1.8;color:#7f1d1d;white-space:pre-wrap;">{texto}</p>
    </div>
    """.strip()


class ResumenImportacion:
    def __init__(self):
        self.total = 0
        self.creadas = 0
        self.actualizadas = 0
        self.ratificadas = 0
        self.extemporaneas = 0
        self.errores: list[str] = []
        self.por_gestor: dict[str, list[dict]] = {}
        self.semaforo: dict[str, int] = {"VERDE": 0, "AMARILLO": 0, "ROJO": 0, "NEGRO": 0}

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "creadas": self.creadas,
            "actualizadas": self.actualizadas,
            "ratificadas": self.ratificadas,
            "extemporaneas": self.extemporaneas,
            "errores": self.errores,
            "por_gestor": self.por_gestor,
            "semaforo": self.semaforo,
        }


class RecepcionService:
    def __init__(self, db: Session):
        self.db = db

    def procesar_excel(self, contenido: bytes) -> ResumenImportacion:
        resumen = ResumenImportacion()
        try:
            wb = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
        except Exception as e:
            resumen.errores.append(f"Archivo Excel inválido: {e}")
            return resumen

        ws = wb.active
        filas = ws.iter_rows(values_only=True)

        try:
            cabecera = next(filas)
        except StopIteration:
            resumen.errores.append("Archivo vacío")
            return resumen

        indices = _mapear_cabeceras(cabecera)
        required = {"entidad", "factura", "vence", "fecha_recepcion"}
        faltantes = required - set(indices.keys())
        if faltantes:
            resumen.errores.append(
                f"Faltan columnas obligatorias: {', '.join(sorted(faltantes))}"
            )
            return resumen

        hoy = datetime.now()

        for num_fila, fila in enumerate(filas, start=2):
            if all(c is None or str(c).strip() == "" for c in fila):
                continue

            def _get(key: str):
                i = indices.get(key)
                return fila[i] if i is not None and i < len(fila) else None

            try:
                entidad = str(_get("entidad") or "").strip().upper()
                factura = str(_get("factura") or "").strip()
                if not entidad or not factura:
                    continue

                consecutivo = str(_get("consecutivo_dgh") or "").strip()
                gestor = str(_get("gestor") or "").strip().upper() or "SIN ASIGNAR"
                radicado_info = str(_get("radicado") or "").strip()
                devolucion = str(_get("devolucion") or "").strip().upper()[:1]

                fecha_entrega = _a_fecha(_get("fecha_entrega"))
                fecha_rad = _a_fecha(_get("fecha_radicacion"))
                fecha_dgh = _a_fecha(_get("fecha_documento_dgh"))
                fecha_rec = _a_fecha(_get("fecha_recepcion"))
                fecha_vence = _a_fecha(_get("vence"))
                valor = _a_float(_get("valor_glosa"))

                if fecha_vence is None or fecha_rec is None:
                    resumen.errores.append(f"Fila {num_fila}: fechas VENCE/RECEPCION inválidas")
                    continue

                # Extemporaneidad: días hábiles entre FECHA RADICACION y FECHA DOCUMENTO DGH
                dias_transcurridos = 0
                es_extemporanea = False
                if fecha_rad and fecha_dgh:
                    dias_transcurridos = _dias_habiles(fecha_rad, fecha_dgh)
                    es_extemporanea = dias_transcurridos > DIAS_HABILES_LIMITE_EXTEMPORANEA

                # Semáforo: días hábiles restantes hasta VENCE
                dias_restantes = _dias_habiles(hoy, fecha_vence) if fecha_vence > hoy else 0
                semaforo = _semaforo(dias_restantes)

                # Ratificación
                ratificada = _es_ratificada(radicado_info)

                if ratificada:
                    estado = "RATIFICADA"
                    dictamen = _dictamen_ratificada(entidad, factura, radicado_info)
                    resumen.ratificadas += 1
                elif es_extemporanea:
                    estado = "EXTEMPORANEA"
                    dictamen = _dictamen_extemporanea(entidad, factura, dias_transcurridos)
                    resumen.extemporaneas += 1
                else:
                    estado = "RADICADA"
                    dictamen = (
                        f'<div style="padding:15px;background:#f8fafc;border-radius:8px;">'
                        f'<b>Glosa importada desde recepción.</b><br>'
                        f'Pendiente de análisis y respuesta por el gestor asignado.'
                        f'</div>'
                    )

                # Upsert por (factura + consecutivo_dgh) o solo factura si no hay consecutivo
                q = self.db.query(GlosaRecord).filter(GlosaRecord.factura == factura)
                if consecutivo:
                    q = q.filter(GlosaRecord.consecutivo_dgh == consecutivo)
                existente = q.first()

                campos = dict(
                    eps=entidad,
                    paciente="N/A",
                    factura=factura,
                    consecutivo_dgh=consecutivo or None,
                    gestor_nombre=gestor,
                    fecha_radicacion_factura=fecha_rad,
                    fecha_documento_dgh=fecha_dgh,
                    fecha_recepcion=fecha_rec,
                    fecha_entrega=fecha_entrega,
                    fecha_vencimiento=fecha_vence,
                    es_devolucion=devolucion or None,
                    radicado_info=radicado_info or None,
                    valor_objetado=valor,
                    valor_aceptado=0.0,
                    etapa="RESPUESTA A GLOSA",
                    estado=estado,
                    dictamen=dictamen,
                    dias_restantes=dias_restantes,
                    prioridad=semaforo,
                    workflow_state=estado,
                    modelo_ia="importacion_recepcion",
                )

                if existente:
                    for k, v in campos.items():
                        setattr(existente, k, v)
                    resumen.actualizadas += 1
                else:
                    self.db.add(GlosaRecord(**campos))
                    resumen.creadas += 1

                resumen.total += 1
                resumen.semaforo[semaforo] = resumen.semaforo.get(semaforo, 0) + 1
                resumen.por_gestor.setdefault(gestor, []).append({
                    "factura": factura,
                    "consecutivo_dgh": consecutivo,
                    "eps": entidad,
                    "valor": valor,
                    "vence": fecha_vence.strftime("%d/%m/%Y"),
                    "fecha_entrega": fecha_entrega.strftime("%d/%m/%Y") if fecha_entrega else "N/A",
                    "semaforo": semaforo,
                    "estado": estado,
                })

            except Exception as e:
                resumen.errores.append(f"Fila {num_fila}: {e}")
                logger.warning(f"Error procesando fila {num_fila}: {e}")
                continue

        try:
            self.db.commit()
        except Exception as e:
            logger.error(f"Error guardando importación: {e}")
            self.db.rollback()
            resumen.errores.append(f"Error al guardar: {e}")

        return resumen
