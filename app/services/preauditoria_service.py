"""Lógica de negocio de PRE-AUDITORÍA SINAC (v2 — el consolidado como base de datos).

El módulo convierte el consolidado de pre-auditoría en una base de datos web:

  1. Se alimentan dos FUENTES subiendo Excel (upsert, nunca duplican):
     - RADICACIÓN DE CUENTAS: por factura, en qué ENVÍO va + F_RECIBIDO,
       F_FACTURA, VALOR, NIT, ENTIDAD.
     - DGREPORT: por factura, si tuvo correo de factura electrónica (CORREO F.E.).
  2. Al ESCRIBIR un número de envío, el sistema crea automáticamente una fila
     por cada factura de ese envío (autocompletando desde las fuentes) y, si la
     factura ya venía DEVUELTA, la reconoce como subsanación (sin duplicarla).
  3. Cada factura es una entidad CANÓNICA (una fila) + un historial de eventos.
  4. Los datos descriptivos se resuelven por JOIN a la fuente más reciente, así
     que corregir un Excel se refleja solo (auto-sync).

Conserva del módulo v1: el semáforo del plazo (3 días hábiles) y el consecutivo
SINAC de los oficios de devolución (DEV-PRE-AUD-####-AAAA).
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Optional

from sqlalchemy import func as sa_func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.tz import TZ_BOGOTA, a_utc, ahora_utc
from app.models.db import (
    DgReportRecord,
    EnvioCargadoRecord,
    FacturaEventoRecord,
    FacturaPreauditoriaRecord,
    OficioDevolucionRecord,
    OficioRecepcionRecord,
    RadicacionCuentaRecord,
)

# Regla del proceso: una misma factura se acepta devuelta máximo 3 veces.
MAX_DEVOLUCIONES = 3

# Plazo para auditar un oficio: 3 días hábiles (lunes a viernes),
# contados a partir del día siguiente al recibo.
PLAZO_DIAS_HABILES = 3

# resultado_actual
RESULTADO_PENDIENTE = "PENDIENTE"
RESULTADO_RADICAR = "RADICAR"
RESULTADO_DEVUELTA = "DEVUELTA"

# estado (máquina de estado que ve el auditor)
ESTADO_NUEVA = "NUEVA"
ESTADO_RADICADA = "RADICADA"
ESTADO_DEVUELTA_PEND = "DEVUELTA_PEND_SUBSANACION"
ESTADO_EN_SUBSANACION = "EN_SUBSANACION"
ESTADO_SUBSANADA = "SUBSANADA"
ESTADO_NUEV_DEVUELTA = "NUEVAMENTE_DEVUELTA"
ESTADO_BLOQUEADA = "BLOQUEADA_LIMITE"

PREFIJO_CONSECUTIVO = "DEV-PRE-AUD"


# ==================================================================
# Semáforo del plazo (3 días hábiles desde el día siguiente al recibo)
# ==================================================================


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


# ==================================================================
# Consecutivo SINAC de los oficios de devolución
# ==================================================================


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


# ==================================================================
# Parseo de los Excel fuente
# ==================================================================


def _normalizar_encabezado(valor) -> str:
    if valor is None:
        return ""
    texto = str(valor)
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"[^A-Za-z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip().upper()


# Alias de columnas (tras normalizar). Cubre el reporte real de DGH
# "Radicación de Cuentas" y también los encabezados del CONSOLIDADO histórico.
_ALIAS_RADICACION = {
    "envio": {
        "RADICACION CONSECUTIVO",
        "CONSECUTIVO",
        "ENVIO",
        "NO ENVIO",
        "NUMERO ENVIO",
        "NRO ENVIO",
    },
    "factura": {"CXC FACTURA", "FACTURA", "NO FACTURA", "NUMERO FACTURA", "DOCUMENTO"},
    "f_recibido": {
        "RADICACION FECHADOCUMENTO",
        "FECHADOCUMENTO",
        "FECHA DOCUMENTO",
        "F RECIBIDO",
        "FECHA RECIBIDO",
    },
    "f_factura": {"CXC FECHA", "F FACTURA", "FECHA FACTURA"},
    "valor": {"CXC VALOR", "VALOR", "VR FACTURA", "VALOR FACTURA", "VLR FACTURA"},
    "nit": {"RADICACION TERCERO DOCUMENTO", "TERCERO DOCUMENTO", "NIT", "NIT ENTIDAD"},
    "entidad": {
        "RADICACION TERCERO NOMBRECOMPLETONA",
        "TERCERO NOMBRECOMPLETONA",
        "NOMBRECOMPLETONA",
        "ENTIDAD",
        "EMPRESA",
        "EPS",
        "ASEGURADORA",
        "CLIENTE",
    },
    "estado_radicacion": {"RADICACION ESTADOACTUAL", "ESTADOACTUAL", "ESTADO"},
}

_ALIAS_DGREPORT = {
    "factura": {"NUMERO DE FACTURA", "FACTURA", "CXC FACTURA", "NO FACTURA"},
    "fecha_correo": {"FECHA DE ENVIO CORREO", "FECHA CORREO", "FECHA DE ENVIO FACTURA DIAN"},
    "numero_fe": {"CUFE", "NUMERO FE", "NUMERO DE FE", "NUMERO FACTURA ELECTRONICA"},
}


def _mapear_columnas(fila_encabezado, alias: dict) -> dict:
    mapa = {}
    for idx, celda in enumerate(fila_encabezado):
        nombre = _normalizar_encabezado(celda)
        if not nombre:
            continue
        for campo, nombres in alias.items():
            if campo not in mapa and nombre in nombres:
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
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(texto[:19], fmt)
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


def _texto(valor) -> Optional[str]:
    if valor is None:
        return None
    t = str(valor).strip()
    return t or None


def _misma_fecha(a, b) -> bool:
    """Compara solo la parte DÍA de dos fechas (las de la fuente son fechas,
    no timestamps con zona). Robusto a que la BD las devuelva aware y el parser
    naive: evita marcar 'actualizada' toda la fuente en cada re-subida."""
    da = a.date() if isinstance(a, datetime) else a
    db_ = b.date() if isinstance(b, datetime) else b
    return da == db_


def _hallar_encabezado(ws, alias: dict, requeridos: set, max_filas: int = 15):
    """Busca la fila de encabezados (primeras `max_filas`) y devuelve
    (numero_fila, mapa) o (None, None) si no aparece."""
    for numero_fila, fila in enumerate(ws.iter_rows(values_only=True), start=1):
        if numero_fila > max_filas:
            break
        mapa = _mapear_columnas(fila, alias)
        if requeridos <= set(mapa):
            return numero_fila, mapa
    return None, None


def parsear_excel_radicacion(contenido: bytes) -> dict:
    """Lee el Excel de RADICACIÓN DE CUENTAS.

    Devuelve una fila por factura (deduplicada; se descartan las radicaciones
    'Anulado' y, si una factura tiene varias radicaciones válidas, se conserva
    la de mayor F_RECIBIDO). {"facturas": [...], "advertencias": [...]}.
    """
    from openpyxl import load_workbook  # import perezoso

    wb = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    por_factura: dict[str, dict] = {}
    advertencias: list[str] = []
    anuladas = 0
    leidas = 0

    for ws in wb.worksheets:
        fila_hdr, mapa = _hallar_encabezado(ws, _ALIAS_RADICACION, {"factura", "envio"})
        if mapa is None:
            continue
        for numero_fila, fila in enumerate(ws.iter_rows(values_only=True), start=1):
            if numero_fila <= fila_hdr:
                continue

            def _celda(campo):
                idx = mapa.get(campo)
                if idx is None or idx >= len(fila):
                    return None
                return fila[idx]

            factura = (str(_celda("factura") or "").strip() or "").upper()
            if not factura or _normalizar_encabezado(factura) in {"FACTURA", "TOTAL"}:
                continue
            leidas += 1
            estado = _texto(_celda("estado_radicacion"))
            if estado and _normalizar_encabezado(estado).startswith("ANULAD"):
                anuladas += 1
                continue
            f_recibido = _como_fecha(_celda("f_recibido"))
            registro = {
                "factura": factura,
                "envio": str(_celda("envio") or "").strip() or "SIN ENVÍO",
                "f_recibido": f_recibido,
                "f_factura": _como_fecha(_celda("f_factura")),
                "valor": _como_valor(_celda("valor")),
                "nit": _texto(_celda("nit")),
                # ENTIDAD trae espacios al final en la fuente real: strip.
                "entidad": _texto(_celda("entidad")),
                "estado_radicacion": estado,
            }
            previo = por_factura.get(factura)
            if previo is None:
                por_factura[factura] = registro
            else:
                # Conservar la de mayor F_RECIBIDO (re-radicación más reciente).
                pf = previo.get("f_recibido")
                if f_recibido and (pf is None or f_recibido > pf):
                    por_factura[factura] = registro
                advertencias.append(
                    f"Factura {factura} con varias radicaciones válidas: se tomó la más reciente"
                )
        if por_factura:
            break  # primera hoja con datos

    wb.close()
    if anuladas:
        advertencias.append(f"{anuladas} radicación(es) 'Anulado' descartada(s)")
    if not por_factura:
        advertencias.append(
            "No se encontraron facturas: revise que el archivo sea el reporte de "
            "Radicación de Cuentas (columnas Radicacion.Consecutivo y CxC.Factura)."
        )
    return {"facturas": list(por_factura.values()), "advertencias": advertencias, "leidas": leidas}


def parsear_excel_dgreport(contenido: bytes) -> dict:
    """Lee el Excel de DGREPORT. Devuelve una fila por factura (con correo F.E.)."""
    from openpyxl import load_workbook

    wb = load_workbook(BytesIO(contenido), data_only=True, read_only=True)
    por_factura: dict[str, dict] = {}
    advertencias: list[str] = []
    leidas = 0

    for ws in wb.worksheets:
        fila_hdr, mapa = _hallar_encabezado(ws, _ALIAS_DGREPORT, {"factura"})
        if mapa is None:
            continue
        for numero_fila, fila in enumerate(ws.iter_rows(values_only=True), start=1):
            if numero_fila <= fila_hdr:
                continue

            def _celda(campo):
                idx = mapa.get(campo)
                if idx is None or idx >= len(fila):
                    return None
                return fila[idx]

            factura = (str(_celda("factura") or "").strip() or "").upper()
            if not factura or _normalizar_encabezado(factura) in {"FACTURA", "TOTAL"}:
                continue
            leidas += 1
            if factura in por_factura:
                continue
            por_factura[factura] = {
                "factura": factura,
                "correo_fe": "SI",
                "fecha_correo": _como_fecha(_celda("fecha_correo")),
                "numero_fe": _texto(_celda("numero_fe")),
            }
        if por_factura:
            break

    wb.close()
    if not por_factura:
        advertencias.append(
            "No se encontraron facturas: revise que el archivo sea el DGReport "
            "(columna 'NUMERO DE FACTURA')."
        )
    return {"facturas": list(por_factura.values()), "advertencias": advertencias, "leidas": leidas}


# ==================================================================
# Upsert de las fuentes (nunca duplican; la última carga es la verdad)
# ==================================================================


def upsert_radicacion(db: Session, filas: list[dict], archivo: str, usuario: str) -> dict:
    """Inserta/actualiza RADICACIÓN por factura. Reporta nuevas/actualizadas/sin cambio."""
    nuevas = actualizadas = sin_cambio = 0
    ahora = ahora_utc()
    # Pre-cargar las existentes en un dict (evita N queries en cargues masivos).
    numeros = [r["factura"] for r in filas]
    indice: dict[str, RadicacionCuentaRecord] = {}
    for i in range(0, len(numeros), 900):
        for row in db.query(RadicacionCuentaRecord).filter(
            RadicacionCuentaRecord.factura.in_(numeros[i : i + 900])
        ):
            indice[row.factura] = row
    for r in filas:
        existente = indice.get(r["factura"])
        if existente is None:
            nuevo = RadicacionCuentaRecord(
                factura=r["factura"],
                envio=r["envio"],
                f_recibido=r["f_recibido"],
                f_factura=r["f_factura"],
                valor=r["valor"],
                nit=r["nit"],
                entidad=r["entidad"],
                estado_radicacion=r.get("estado_radicacion"),
                fuente_archivo=archivo,
                importado_por=usuario,
            )
            db.add(nuevo)
            indice[r["factura"]] = nuevo  # blinda contra la misma factura repetida en el lote
            nuevas += 1
        else:
            cambio = (
                existente.envio != r["envio"]
                or existente.valor != r["valor"]
                or existente.nit != r["nit"]
                or (existente.entidad or None) != r["entidad"]
                or not _misma_fecha(existente.f_recibido, r["f_recibido"])
                or not _misma_fecha(existente.f_factura, r["f_factura"])
            )
            if cambio:
                existente.envio = r["envio"]
                existente.f_recibido = r["f_recibido"]
                existente.f_factura = r["f_factura"]
                existente.valor = r["valor"]
                existente.nit = r["nit"]
                existente.entidad = r["entidad"]
                existente.estado_radicacion = r.get("estado_radicacion")
                existente.fuente_archivo = archivo
                existente.importado_por = usuario
                existente.actualizado_en = ahora
                actualizadas += 1
            else:
                sin_cambio += 1
    db.commit()
    return {"nuevas": nuevas, "actualizadas": actualizadas, "sin_cambio": sin_cambio}


def upsert_dgreport(db: Session, filas: list[dict], archivo: str, usuario: str) -> dict:
    """Inserta/actualiza DGREPORT por factura."""
    nuevas = actualizadas = sin_cambio = 0
    ahora = ahora_utc()
    numeros = [r["factura"] for r in filas]
    indice: dict[str, DgReportRecord] = {}
    for i in range(0, len(numeros), 900):
        for row in db.query(DgReportRecord).filter(
            DgReportRecord.factura.in_(numeros[i : i + 900])
        ):
            indice[row.factura] = row
    for r in filas:
        existente = indice.get(r["factura"])
        if existente is None:
            nuevo = DgReportRecord(
                factura=r["factura"],
                correo_fe=r.get("correo_fe", "SI"),
                fecha_correo=r.get("fecha_correo"),
                numero_fe=r.get("numero_fe"),
                fuente_archivo=archivo,
                importado_por=usuario,
            )
            db.add(nuevo)
            indice[r["factura"]] = nuevo
            nuevas += 1
        else:
            cambio = existente.correo_fe != r.get(
                "correo_fe", "SI"
            ) or existente.numero_fe != r.get("numero_fe")
            if cambio:
                existente.correo_fe = r.get("correo_fe", "SI")
                existente.fecha_correo = r.get("fecha_correo")
                existente.numero_fe = r.get("numero_fe")
                existente.fuente_archivo = archivo
                existente.importado_por = usuario
                existente.actualizado_en = ahora
                actualizadas += 1
            else:
                sin_cambio += 1
    db.commit()
    return {"nuevas": nuevas, "actualizadas": actualizadas, "sin_cambio": sin_cambio}


# ==================================================================
# Cruce con las fuentes (auto-sync por lectura)
# ==================================================================


def datos_fuente(db: Session, factura: str) -> dict:
    """Resuelve los datos descriptivos de una factura desde las fuentes."""
    rad = (
        db.query(RadicacionCuentaRecord)
        .filter(RadicacionCuentaRecord.factura == factura)
        .one_or_none()
    )
    dg = db.query(DgReportRecord).filter(DgReportRecord.factura == factura).one_or_none()
    return {
        "envio": rad.envio if rad else None,
        "f_recibido": rad.f_recibido if rad else None,
        "f_factura": rad.f_factura if rad else None,
        "valor": rad.valor if rad else 0.0,
        "nit": rad.nit if rad else None,
        "entidad": rad.entidad if rad else None,
        "correo_fe": (dg.correo_fe if dg else "NO"),
    }


def facturas_de_envio(db: Session, envio: str) -> list[RadicacionCuentaRecord]:
    return (
        db.query(RadicacionCuentaRecord)
        .filter(RadicacionCuentaRecord.envio == str(envio).strip())
        .order_by(RadicacionCuentaRecord.factura)
        .all()
    )


# ==================================================================
# Escribir un envío (el corazón del automatismo)
# ==================================================================


def _nuevo_evento(
    factura_row: FacturaPreauditoriaRecord,
    tipo: str,
    *,
    oficio: Optional[OficioRecepcionRecord],
    fuente: dict,
    usuario: str,
    motivo: str = None,
    resultado: str = None,
    oficio_devolucion_id: int = None,
) -> FacturaEventoRecord:
    return FacturaEventoRecord(
        factura_id=factura_row.id,
        factura=factura_row.factura,
        tipo_evento=tipo,
        subsanacion_num=factura_row.num_subsanacion,
        ronda=factura_row.ronda_actual,
        estado_resultante=factura_row.estado,
        envio=factura_row.envio_actual,
        oficio_id=oficio.id if oficio else None,
        oficio_fhus=oficio.numero_radicado if oficio else None,
        f_recibido=oficio.fecha_recibido if oficio else None,
        resultado=resultado if resultado is not None else factura_row.resultado_actual,
        auditor=usuario,
        motivo=motivo,
        oficio_devolucion_id=oficio_devolucion_id,
        valor_snapshot=fuente.get("valor") or 0.0,
        nit_snapshot=fuente.get("nit"),
        entidad_snapshot=fuente.get("entidad"),
        correo_fe_snapshot=fuente.get("correo_fe"),
        fecha_factura_snapshot=fuente.get("f_factura"),
        creado_por=usuario,
    )


def preview_envio(db: Session, oficio: OficioRecepcionRecord, envio: str) -> dict:
    """Simula escribir un envío sin tocar la BD (para confirmar antes)."""
    envio = str(envio).strip()
    ya = db.query(EnvioCargadoRecord).filter(EnvioCargadoRecord.envio == envio).one_or_none()
    src = facturas_de_envio(db, envio)
    facturas = []
    nuevas = reingresos = radicadas = pendientes_otro = 0
    alertas = []
    for r in src:
        canon = (
            db.query(FacturaPreauditoriaRecord)
            .filter(FacturaPreauditoriaRecord.factura == r.factura)
            .one_or_none()
        )
        if canon is None:
            clasif = "NUEVA"
            nuevas += 1
        elif canon.resultado_actual == RESULTADO_DEVUELTA:
            clasif = "REINGRESO"
            reingresos += 1
            if canon.num_devoluciones >= MAX_DEVOLUCIONES:
                alertas.append(
                    f"{r.factura} lleva {canon.num_devoluciones} devoluciones: solo radicar/escalar"
                )
        elif canon.resultado_actual == RESULTADO_RADICAR:
            clasif = "YA_RADICADA"
            radicadas += 1
        else:  # PENDIENTE
            clasif = "YA_ABIERTA"
            pendientes_otro += 1
        dg = db.query(DgReportRecord).filter(DgReportRecord.factura == r.factura).one_or_none()
        facturas.append(
            {
                "factura": r.factura,
                "f_factura": r.f_factura.isoformat() if r.f_factura else None,
                "valor": r.valor,
                "nit": r.nit,
                "entidad": r.entidad,
                "correo_fe": dg.correo_fe if dg else "NO",
                "clasificacion": clasif,
            }
        )
    return {
        "envio": envio,
        "existe_en_fuente": bool(src),
        "ya_cargado": bool(ya),
        "total_en_fuente": len(src),
        "nuevas": nuevas,
        "reingresos": reingresos,
        "ya_radicadas": radicadas,
        "ya_abiertas": pendientes_otro,
        "alertas_limite_devoluciones": alertas,
        "facturas": facturas,
    }


def escribir_envio(db: Session, oficio: OficioRecepcionRecord, envio: str, usuario: str) -> dict:
    """Vuelca al consolidado todas las facturas de un envío.

    - Dedup (punto 3): si el envío ya fue cargado → no recrea.
    - Primera vez: crea la factura canónica + evento ESCRITA.
    - Reingreso (factura ya DEVUELTA): incrementa subsanación, no crea factura
      nueva + evento REINGRESO.
    """
    envio = str(envio).strip()
    ya = db.query(EnvioCargadoRecord).filter(EnvioCargadoRecord.envio == envio).one_or_none()
    if ya:
        return {
            "ya_cargado": True,
            "mensaje": "El envío ya fue cargado.",
            "envio": envio,
            "cargado_en": a_utc(ya.cargado_en).isoformat() if ya.cargado_en else None,
        }

    src = facturas_de_envio(db, envio)
    if not src:
        return {
            "existe_en_fuente": False,
            "mensaje": (
                f"El envío {envio} no existe en la Radicación de Cuentas cargada. "
                "Suba o actualice la fuente."
            ),
            "envio": envio,
        }

    nuevas = reingresos = omitidas = 0
    alertas = []
    advertencias = []
    for r in src:
        dg = db.query(DgReportRecord).filter(DgReportRecord.factura == r.factura).one_or_none()
        fuente = {
            "valor": r.valor,
            "nit": r.nit,
            "entidad": r.entidad,
            "correo_fe": dg.correo_fe if dg else "NO",
            "f_factura": r.f_factura,
        }
        canon = (
            db.query(FacturaPreauditoriaRecord)
            .filter(FacturaPreauditoriaRecord.factura == r.factura)
            .one_or_none()
        )
        if canon is None:
            # PRIMERA VEZ
            canon = FacturaPreauditoriaRecord(
                factura=r.factura,
                envio_actual=envio,
                oficio_actual_id=oficio.id,
                oficio_fhus=oficio.numero_radicado,
                f_recibido=oficio.fecha_recibido,
                estado=ESTADO_NUEVA,
                resultado_actual=RESULTADO_PENDIENTE,
                ronda_actual=1,
                num_subsanacion=0,
                num_devoluciones=0,
                pendiente_subsanacion=0,
                creado_por=usuario,
            )
            db.add(canon)
            db.flush()
            db.add(_nuevo_evento(canon, "ESCRITA", oficio=oficio, fuente=fuente, usuario=usuario))
            nuevas += 1
        elif canon.resultado_actual == RESULTADO_DEVUELTA:
            # REINGRESO / SUBSANACIÓN (no se crea factura nueva)
            canon.ronda_actual += 1
            canon.num_subsanacion = canon.ronda_actual - 1
            canon.envio_actual = envio
            canon.oficio_actual_id = oficio.id
            canon.oficio_fhus = oficio.numero_radicado
            canon.f_recibido = oficio.fecha_recibido
            canon.resultado_actual = RESULTADO_PENDIENTE
            canon.estado = ESTADO_EN_SUBSANACION
            canon.pendiente_subsanacion = 0
            canon.auditor = None
            canon.fecha_auditoria = None
            canon.oficio_devolucion_id = None
            db.flush()
            db.add(_nuevo_evento(canon, "REINGRESO", oficio=oficio, fuente=fuente, usuario=usuario))
            reingresos += 1
            if canon.num_devoluciones >= MAX_DEVOLUCIONES:
                alertas.append(
                    f"{r.factura} ya lleva {canon.num_devoluciones} devoluciones: "
                    "solo debería radicarse o escalarse."
                )
        elif canon.resultado_actual == RESULTADO_RADICAR:
            omitidas += 1
            advertencias.append(f"{r.factura} ya estaba radicada: no se reingresó.")
        else:  # PENDIENTE ya abierta
            omitidas += 1
            advertencias.append(
                f"{r.factura} sigue pendiente en {canon.oficio_fhus or 'otro oficio'}: "
                "resuélvala primero."
            )

    db.add(
        EnvioCargadoRecord(
            envio=envio,
            oficio_id=oficio.id,
            total_facturas=len(src),
            nuevas=nuevas,
            reingresos=reingresos,
            cargado_por=usuario,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Carrera: otra petición cargó el mismo envío entre el chequeo y el commit.
        db.rollback()
        return {"ya_cargado": True, "mensaje": "El envío ya fue cargado.", "envio": envio}
    return {
        "ya_cargado": False,
        "existe_en_fuente": True,
        "envio": envio,
        "total_en_fuente": len(src),
        "nuevas": nuevas,
        "reingresos": reingresos,
        "omitidas": omitidas,
        "alertas_limite_devoluciones": alertas,
        "advertencias": advertencias,
    }


# ==================================================================
# Auditar (radicar / devolver) con contador de devoluciones y tope 3
# ==================================================================


def auditar_factura(
    db: Session,
    canon: FacturaPreauditoriaRecord,
    resultado: str,
    usuario: str,
    motivo: str = None,
    observaciones: str = None,
) -> dict:
    """Aplica RADICAR / DEVUELTA / PENDIENTE (revertir).

    Devuelve {"ok": True, ...} o {"ok": False, "codigo": 400|409, "mensaje": ...}.
    """
    oficio = (
        db.get(OficioRecepcionRecord, canon.oficio_actual_id) if canon.oficio_actual_id else None
    )
    fuente = datos_fuente(db, canon.factura)

    # Guard de estado: solo se puede radicar/devolver una factura PENDIENTE.
    # Para cambiar una decisión ya tomada hay que revertir primero (→ PENDIENTE).
    # Esto evita inflar el contador de devoluciones con doble clic o re-envíos.
    if resultado in (RESULTADO_RADICAR, RESULTADO_DEVUELTA):
        if canon.resultado_actual != RESULTADO_PENDIENTE:
            etiqueta = "radicada" if canon.resultado_actual == RESULTADO_RADICAR else "devuelta"
            return {
                "ok": False,
                "codigo": 409,
                "mensaje": (
                    f"La factura {canon.factura} ya fue {etiqueta} en esta ronda. "
                    "Para cambiar la decisión, primero use 'Dejar pendiente' (revertir)."
                ),
            }

    if resultado == RESULTADO_RADICAR:
        # Regla del proceso: sin soporte de facturación electrónica (CORREO
        # F.E. = NO) la factura no se puede radicar — solo devolverse.
        if (fuente.get("correo_fe") or "NO") != "SI":
            return {
                "ok": False,
                "codigo": 409,
                "mensaje": (
                    f"La factura {canon.factura} no tiene soporte de facturación "
                    "electrónica (CORREO F.E. = NO): solo puede devolverse. Si el "
                    "soporte ya existe, suba el Formato Facturación Electrónica "
                    "actualizado en la pestaña Fuentes."
                ),
            }
        canon.resultado_actual = RESULTADO_RADICAR
        canon.estado = ESTADO_RADICADA if canon.ronda_actual == 1 else ESTADO_SUBSANADA
        canon.pendiente_subsanacion = 0
        canon.motivo_ultima_devolucion = None
        canon.auditor = usuario
        canon.fecha_auditoria = ahora_utc()
        if observaciones is not None:
            canon.observaciones = observaciones
        db.flush()
        tipo = "SUBSANADA" if canon.ronda_actual >= 2 else "RADICADA"
        db.add(
            _nuevo_evento(
                canon,
                tipo,
                oficio=oficio,
                fuente=fuente,
                usuario=usuario,
                resultado=RESULTADO_RADICAR,
            )
        )
        db.commit()
        return {"ok": True}

    if resultado == RESULTADO_DEVUELTA:
        if not (motivo or "").strip():
            return {"ok": False, "codigo": 400, "mensaje": "Para devolver debe escribir el motivo."}
        if canon.num_devoluciones >= MAX_DEVOLUCIONES:
            return {
                "ok": False,
                "codigo": 409,
                "mensaje": (
                    f"La factura {canon.factura} ya fue devuelta {canon.num_devoluciones} veces; "
                    f"el proceso acepta máximo {MAX_DEVOLUCIONES} devoluciones. Debe radicarse "
                    "o escalarse al coordinador."
                ),
            }
        canon.num_devoluciones += 1
        canon.resultado_actual = RESULTADO_DEVUELTA
        canon.motivo_ultima_devolucion = motivo.strip()
        canon.pendiente_subsanacion = 1
        if canon.num_devoluciones >= MAX_DEVOLUCIONES:
            canon.estado = ESTADO_BLOQUEADA
        elif canon.ronda_actual == 1:
            canon.estado = ESTADO_DEVUELTA_PEND
        else:
            canon.estado = ESTADO_NUEV_DEVUELTA
        canon.auditor = usuario
        canon.fecha_auditoria = ahora_utc()
        if observaciones is not None:
            canon.observaciones = observaciones
        db.flush()
        tipo = "NUEVAMENTE_DEVUELTA" if canon.ronda_actual >= 2 else "DEVUELTA"
        db.add(
            _nuevo_evento(
                canon,
                tipo,
                oficio=oficio,
                fuente=fuente,
                usuario=usuario,
                motivo=motivo.strip(),
                resultado=RESULTADO_DEVUELTA,
            )
        )
        db.commit()
        return {"ok": True}

    if resultado == RESULTADO_PENDIENTE:
        # Revertir una auditoría (no si ya salió en un oficio de devolución PDF).
        if canon.oficio_devolucion_id:
            return {
                "ok": False,
                "codigo": 409,
                "mensaje": "Esta factura ya salió en un oficio de devolución; no se puede revertir.",
            }
        if canon.resultado_actual == RESULTADO_DEVUELTA and canon.num_devoluciones > 0:
            canon.num_devoluciones -= 1
        canon.resultado_actual = RESULTADO_PENDIENTE
        canon.estado = ESTADO_NUEVA if canon.ronda_actual == 1 else ESTADO_EN_SUBSANACION
        canon.pendiente_subsanacion = 0
        canon.auditor = None
        canon.fecha_auditoria = None
        canon.motivo_ultima_devolucion = None
        db.flush()
        db.add(
            _nuevo_evento(
                canon,
                "REVERTIDA",
                oficio=oficio,
                fuente=fuente,
                usuario=usuario,
                resultado=RESULTADO_PENDIENTE,
            )
        )
        db.commit()
        return {"ok": True}

    return {"ok": False, "codigo": 400, "mensaje": "Resultado inválido."}


# ==================================================================
# Eliminar un oficio mal registrado (solo administradores)
# ==================================================================


def eliminar_oficio(db: Session, oficio: OficioRecepcionRecord) -> dict:
    """Elimina un oficio de recepción con salvaguardas.

    - Si alguna de sus facturas ya salió en un oficio de devolución (PDF con
      consecutivo emitido), NO se elimina: devuelve el motivo.
    - Facturas de ronda 1 (nacieron en este oficio): se borran con sus eventos.
    - Facturas en subsanación (ronda 2+, reingresaron aquí): NO se borran; se
      revierte el reingreso y vuelven a su estado DEVUELTA anterior, con su
      historial intacto.
    - Se liberan los envíos del ledger para poder re-escribirlos.
    """
    facturas = (
        db.query(FacturaPreauditoriaRecord)
        .filter(FacturaPreauditoriaRecord.oficio_actual_id == oficio.id)
        .all()
    )
    con_pdf = [f.factura for f in facturas if f.oficio_devolucion_id]
    en_pdf_por_evento = (
        db.query(FacturaEventoRecord.factura)
        .filter(
            FacturaEventoRecord.oficio_id == oficio.id,
            FacturaEventoRecord.oficio_devolucion_id.isnot(None),
        )
        .all()
    )
    con_pdf += [r[0] for r in en_pdf_por_evento]
    if con_pdf:
        return {
            "ok": False,
            "codigo": 409,
            "mensaje": (
                f"El oficio {oficio.numero_radicado} tiene factura(s) en un oficio de "
                f"devolución ya emitido ({', '.join(sorted(set(con_pdf))[:5])}...): "
                "no se puede eliminar."
            ),
        }

    borradas = 0
    revertidas = 0
    for f in facturas:
        if f.ronda_actual <= 1:
            db.query(FacturaEventoRecord).filter(FacturaEventoRecord.factura_id == f.id).delete(
                synchronize_session=False
            )
            db.delete(f)
            borradas += 1
        else:
            # Reingreso: revertir a la devolución anterior sin perder historial.
            evento_dev = (
                db.query(FacturaEventoRecord)
                .filter(
                    FacturaEventoRecord.factura_id == f.id,
                    FacturaEventoRecord.tipo_evento.in_(["DEVUELTA", "NUEVAMENTE_DEVUELTA"]),
                    FacturaEventoRecord.oficio_id != oficio.id,
                )
                .order_by(FacturaEventoRecord.creado_en.desc(), FacturaEventoRecord.id.desc())
                .first()
            )
            db.query(FacturaEventoRecord).filter(
                FacturaEventoRecord.factura_id == f.id,
                FacturaEventoRecord.oficio_id == oficio.id,
            ).delete(synchronize_session=False)
            f.ronda_actual -= 1
            f.num_subsanacion = max(0, f.ronda_actual - 1)
            f.resultado_actual = RESULTADO_DEVUELTA
            f.pendiente_subsanacion = 1
            if f.num_devoluciones >= MAX_DEVOLUCIONES:
                f.estado = ESTADO_BLOQUEADA
            elif f.ronda_actual == 1:
                f.estado = ESTADO_DEVUELTA_PEND
            else:
                f.estado = ESTADO_NUEV_DEVUELTA
            if evento_dev:
                f.envio_actual = evento_dev.envio
                f.oficio_actual_id = evento_dev.oficio_id
                f.oficio_fhus = evento_dev.oficio_fhus
                f.f_recibido = evento_dev.f_recibido
                f.auditor = evento_dev.auditor
                f.motivo_ultima_devolucion = evento_dev.motivo
                f.fecha_auditoria = evento_dev.creado_en
            revertidas += 1

    envios = db.query(EnvioCargadoRecord).filter(EnvioCargadoRecord.oficio_id == oficio.id).all()
    for e in envios:
        db.delete(e)
    radicado = oficio.numero_radicado
    db.delete(oficio)
    db.commit()
    return {
        "ok": True,
        "radicado": radicado,
        "facturas_borradas": borradas,
        "subsanaciones_revertidas": revertidas,
        "envios_liberados": len(envios),
    }
