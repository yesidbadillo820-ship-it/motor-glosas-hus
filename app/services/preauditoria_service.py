"""Lógica de negocio de PRE-AUDITORÍA SINAC.

Cubre:
  - Importar el Excel del consecutivo de DGH (facturas de un oficio).
  - Semáforo del plazo de auditoría: 3 días hábiles contados a partir
    del día siguiente al recibo del oficio.
  - Rondas de una factura (1.ª vez vs. subsanación) y regla de máximo
    3 devoluciones por factura.
  - Consecutivo SINAC de los oficios de devolución (DEV-PRE-AUD-####-AAAA).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.core.tz import TZ_BOGOTA, a_utc
from app.models.db import (
    FacturaPreauditoriaRecord,
    OficioDevolucionRecord,
    OficioRecepcionRecord,
)

# Regla del proceso: una misma factura se acepta devuelta máximo 3 veces.
MAX_DEVOLUCIONES = 3

# Plazo para auditar un oficio: 3 días hábiles (lunes a viernes),
# contados a partir del día siguiente al recibo.
PLAZO_DIAS_HABILES = 3

RESULTADO_PENDIENTE = "PENDIENTE"
RESULTADO_RADICAR = "RADICAR"
RESULTADO_DEVUELTA = "DEVUELTA"

PREFIJO_CONSECUTIVO = "DEV-PRE-AUD"


# ------------------------------------------------------------------
# Semáforo del plazo (3 días hábiles desde el día siguiente al recibo)
# ------------------------------------------------------------------


def _es_habil(d: date) -> bool:
    return d.weekday() < 5  # lunes=0 ... viernes=4


def _sumar_dias_habiles(desde: date, n: int) -> date:
    """El n-ésimo día hábil DESPUÉS de `desde` (sin contar `desde`)."""
    d = desde
    restantes = n
    while restantes > 0:
        d += timedelta(days=1)
        if _es_habil(d):
            restantes -= 1
    return d


def _dias_habiles_entre(desde: date, hasta: date) -> int:
    """Días hábiles de `desde` a `hasta`, ambos inclusive (0 si desde>hasta)."""
    if desde > hasta:
        return 0
    total = 0
    d = desde
    while d <= hasta:
        if _es_habil(d):
            total += 1
        d += timedelta(days=1)
    return total


def calcular_semaforo(
    fecha_recibido: datetime,
    hoy: Optional[date] = None,
    completado: bool = False,
) -> dict:
    """Semáforo del plazo de un oficio.

    Estados: COMPLETADO (todo auditado), VERDE (va bien), AMARILLO
    (penúltimo día), ROJO (último día) y VENCIDO (se pasó el plazo).
    """
    fecha_recibido = a_utc(fecha_recibido)
    recibido_local = fecha_recibido.astimezone(TZ_BOGOTA).date()
    if hoy is None:
        hoy = datetime.now(TZ_BOGOTA).date()
    fecha_limite = _sumar_dias_habiles(recibido_local, PLAZO_DIAS_HABILES)
    dias_restantes = _dias_habiles_entre(hoy, fecha_limite)

    if completado:
        estado = "COMPLETADO"
    elif hoy > fecha_limite:
        estado = "VENCIDO"
    elif dias_restantes >= 3:
        estado = "VERDE"
    elif dias_restantes == 2:
        estado = "AMARILLO"
    else:
        estado = "ROJO"

    return {
        "estado": estado,
        "fecha_limite": fecha_limite.isoformat(),
        "dias_habiles_restantes": dias_restantes if hoy <= fecha_limite else 0,
        "dias_vencido": (hoy - fecha_limite).days if hoy > fecha_limite else 0,
    }


# ------------------------------------------------------------------
# Rondas y regla de máximo 3 devoluciones
# ------------------------------------------------------------------


def devoluciones_previas(db: Session, factura: str, excluir_id: Optional[int] = None) -> int:
    """Cuántas veces ya fue DEVUELTA esta factura (en cualquier oficio)."""
    q = db.query(sa_func.count(FacturaPreauditoriaRecord.id)).filter(
        FacturaPreauditoriaRecord.factura == factura,
        FacturaPreauditoriaRecord.resultado == RESULTADO_DEVUELTA,
    )
    if excluir_id is not None:
        q = q.filter(FacturaPreauditoriaRecord.id != excluir_id)
    return int(q.scalar() or 0)


def calcular_ronda(db: Session, factura: str, oficio_id: Optional[int] = None) -> int:
    """Ronda de esta llegada: 1 + veces que la factura ya vino en otros oficios."""
    q = db.query(sa_func.count(FacturaPreauditoriaRecord.id)).filter(
        FacturaPreauditoriaRecord.factura == factura
    )
    if oficio_id is not None:
        q = q.filter(FacturaPreauditoriaRecord.oficio_id != oficio_id)
    return int(q.scalar() or 0) + 1


def estado_subsanacion(registro: FacturaPreauditoriaRecord) -> Optional[str]:
    """Para rondas 2+: SUBSANADA si se radicó, NUEVAMENTE DEVUELTA si no.

    En ronda 1 (primera llegada) no aplica y devuelve None.
    """
    if registro.ronda <= 1:
        return None
    if registro.resultado == RESULTADO_RADICAR:
        return "SUBSANADA"
    if registro.resultado == RESULTADO_DEVUELTA:
        return "NUEVAMENTE DEVUELTA"
    return "EN REVISIÓN"


# ------------------------------------------------------------------
# Consecutivo SINAC de los oficios de devolución
# ------------------------------------------------------------------


def siguiente_consecutivo(db: Session, anio: Optional[int] = None) -> tuple[str, int, int]:
    """Siguiente consecutivo DEV-PRE-AUD-####-AAAA (reinicia cada año)."""
    if anio is None:
        anio = datetime.now(TZ_BOGOTA).year
    ultimo = (
        db.query(sa_func.max(OficioDevolucionRecord.numero))
        .filter(OficioDevolucionRecord.anio == anio)
        .scalar()
    )
    numero = int(ultimo or 0) + 1
    return f"{PREFIJO_CONSECUTIVO}-{numero:04d}-{anio}", numero, anio


# ------------------------------------------------------------------
# Importación del Excel del consecutivo DGH
# ------------------------------------------------------------------

# Nombres de columna aceptados (tras normalizar: mayúsculas, sin tildes,
# sin espacios dobles). Cubre el export de DGH y el consolidado que ya
# maneja el equipo (CONSOLIDADO_PRE_AUDITORIA).
_ALIAS_COLUMNAS = {
    "envio": {"ENVIO", "NO ENVIO", "N ENVIO", "NUM ENVIO", "NUMERO ENVIO", "NRO ENVIO"},
    "factura": {"FACTURA", "NO FACTURA", "NUM FACTURA", "NUMERO FACTURA", "DOCUMENTO"},
    "fecha_factura": {"F FACTURA", "F_FACTURA", "FECHA FACTURA", "FECHA"},
    "valor": {"VALOR", "VR FACTURA", "VALOR FACTURA", "VLR FACTURA", "TOTAL"},
    "nit": {"NIT", "NIT ENTIDAD"},
    "entidad": {"ENTIDAD", "EMPRESA", "ERP", "EPS", "ASEGURADORA", "CLIENTE"},
    "correo_fe": {"CORREO F E", "CORREO FE", "CORREO F.E.", "CORREO"},
}


def _normalizar_encabezado(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Za-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip().upper()


def _mapear_columnas(fila_encabezado) -> dict:
    mapa = {}
    for idx, celda in enumerate(fila_encabezado):
        nombre = _normalizar_encabezado(celda)
        if not nombre:
            continue
        for campo, alias in _ALIAS_COLUMNAS.items():
            if campo not in mapa and nombre in alias:
                mapa[campo] = idx
    return mapa


def _como_fecha(valor) -> Optional[datetime]:
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    texto = str(valor).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt)
        except ValueError:
            continue
    return None


def _como_valor(valor) -> float:
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = re.sub(r"[^0-9,.\-]", "", str(valor))
    # Formato colombiano: punto de miles, coma decimal.
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return 0.0


def parsear_excel_dgh(contenido: bytes) -> dict:
    """Lee el Excel del consecutivo DGH y devuelve las facturas.

    Busca la fila de encabezados en las primeras 15 filas de cada hoja
    (debe traer al menos FACTURA; ENVIO/VALOR/ENTIDAD se toman si vienen).
    Devuelve {"facturas": [...], "advertencias": [...]}.
    """
    from openpyxl import load_workbook  # import perezoso, como en otros servicios

    wb = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    facturas: list[dict] = []
    advertencias: list[str] = []
    vistas: set[str] = set()

    for ws in wb.worksheets:
        filas = ws.iter_rows(values_only=True)
        mapa = None
        for numero_fila, fila in enumerate(filas, start=1):
            if mapa is None:
                if numero_fila > 15:
                    break
                candidato = _mapear_columnas(fila)
                if "factura" in candidato:
                    mapa = candidato
                continue

            factura_cruda = fila[mapa["factura"]] if mapa["factura"] < len(fila) else None
            factura = str(factura_cruda or "").strip().upper()
            if not factura or _normalizar_encabezado(factura) in {"FACTURA", "TOTAL"}:
                continue
            if factura in vistas:
                advertencias.append(f"Factura repetida en el archivo (se tomó una sola vez): {factura}")
                continue
            vistas.add(factura)

            def _celda(campo):
                idx = mapa.get(campo)
                if idx is None or idx >= len(fila):
                    return None
                return fila[idx]

            correo = str(_celda("correo_fe") or "").strip().upper() or None
            if correo and correo not in ("SI", "NO"):
                correo = None
            facturas.append(
                {
                    "factura": factura,
                    "envio": str(_celda("envio") or "").strip() or "SIN ENVÍO",
                    "fecha_factura": _como_fecha(_celda("fecha_factura")),
                    "valor": _como_valor(_celda("valor")),
                    "nit": str(_celda("nit") or "").strip() or None,
                    "entidad": str(_celda("entidad") or "").strip() or None,
                    "correo_fe": correo,
                }
            )
        if facturas:
            break  # la primera hoja con datos es la que vale

    wb.close()
    if not facturas:
        advertencias.append(
            "No se encontraron facturas: revise que el archivo tenga una "
            "columna FACTURA (formato del consecutivo DGH)."
        )
    return {"facturas": facturas, "advertencias": advertencias}


def resumen_por_envio(facturas: list[FacturaPreauditoriaRecord]) -> list[dict]:
    """Cuántas facturas (y por qué valor) trae cada número de envío."""
    grupos: dict[str, dict] = {}
    for f in facturas:
        g = grupos.setdefault(
            f.envio or "SIN ENVÍO",
            {"envio": f.envio or "SIN ENVÍO", "cantidad_facturas": 0, "valor_total": 0.0},
        )
        g["cantidad_facturas"] += 1
        g["valor_total"] += float(f.valor or 0)
    return sorted(grupos.values(), key=lambda g: str(g["envio"]))


def oficio_completado(facturas: list[FacturaPreauditoriaRecord]) -> bool:
    return bool(facturas) and all(
        f.resultado in (RESULTADO_RADICAR, RESULTADO_DEVUELTA) for f in facturas
    )
