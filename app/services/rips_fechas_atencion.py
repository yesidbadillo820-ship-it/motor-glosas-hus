"""Las fechas de ingreso y egreso que dice el RIPS de una factura.

POR QUÉ EXISTE (08-09-2026, pedido de Yesid). Para saber si una cuenta del
ADRES se está pasando del plazo hay que partir de la **fecha de egreso**, y
la fecha de egreso está en el RIPS, no en la carátula de la factura ni en el
oficio. Este módulo abre el archivo `Rips_HUSxxxx.json` del servidor de
facturación electrónica y saca esas dos fechas.

NO SE REESCRIBE EL LECTOR DE RIPS. El motor ya tiene uno completo y probado
(`preauditoria_rips.py`), hecho contra la Resolución 2275 de 2023 y
verificado con archivos reales del HIS. Este módulo solo lo usa: abre el
archivo, se lo entrega y toma del resultado la atención. Así, el día que el
Ministerio cambie un campo, se arregla en un solo lugar.

De dónde salen las dos fechas (esa cascada es la del lector, no de aquí):

  · si hay HOSPITALIZACIÓN, del primer episodio: `fechaInicioAtencion` y
    `fechaEgreso`;
  · si no, de URGENCIAS, igual;
  · si no (cuenta ambulatoria), del recorrido de consultas y
    procedimientos: la primera fecha es el ingreso y la última el egreso.

LO QUE ESTE MÓDULO NO HACE: no adivina. Si el archivo no existe, no se puede
leer, no es un RIPS o no trae fechas, devuelve el motivo y ya. Una fecha de
egreso inventada mandaría a devolver una cuenta que estaba bien, o dejaría
prescribir una que se podía cobrar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.core.logging_utils import logger

# Un RIPS de una cuenta hospitalaria grande pesa unos pocos MB. Cualquier
# cosa por encima de esto no es un RIPS de una factura: no se abre, para no
# tumbar el servidor leyendo un archivo equivocado.
MAX_BYTES_RIPS = 60 * 1024 * 1024


@dataclass(frozen=True)
class FechasAtencion:
    """Lo que el RIPS dice de la atención. `problema` explica los vacíos."""

    factura: str = ""
    fecha_ingreso: Optional[datetime] = None
    fecha_egreso: Optional[datetime] = None
    tipo_atencion: str = ""  # HOSPITALIZACION | URGENCIAS | AMBULATORIO
    archivo: str = ""
    problema: str = ""
    # El RIPS NO trajo fecha de salida y se dedujo de la última atención.
    # Pasa en las cuentas ambulatorias: si la factura son 20 sesiones y el
    # RIPS trae una sola línea, la «última atención» es la PRIMERA sesión, y
    # el egreso deducido se queda corto. Caso HUS559324 (08-09-2026): el RIPS
    # decía 13/02/2025 y el egreso real, según la factura, fue el 14/03/2025.
    egreso_deducido: bool = False

    @property
    def completas(self) -> bool:
        return self.fecha_ingreso is not None and self.fecha_egreso is not None

    def a_dict(self) -> dict[str, Any]:
        return {
            "factura": self.factura,
            "fecha_ingreso": self.fecha_ingreso.isoformat() if self.fecha_ingreso else None,
            "fecha_egreso": self.fecha_egreso.isoformat() if self.fecha_egreso else None,
            "tipo_atencion": self.tipo_atencion,
            "archivo": self.archivo,
            "problema": self.problema,
            "completas": self.completas,
            "egreso_deducido": self.egreso_deducido,
        }


def cargar_json(ruta: str | Path) -> tuple[Optional[dict], str]:
    """Abre el archivo y devuelve (contenido, problema).

    Tolera el BOM que dejan algunos exportadores de Windows y los archivos
    guardados en la codificación vieja del HIS. Nunca lanza excepción: el
    servidor de soportes se cae o se desconecta, y una pre-auditoría no se
    puede quedar trabada por eso.
    """
    p = Path(ruta)
    try:
        if not p.is_file():
            return None, f"no se encontró el archivo: {p}"
        tamano = p.stat().st_size
        if tamano == 0:
            return None, f"el archivo está vacío: {p.name}"
        if tamano > MAX_BYTES_RIPS:
            return None, f"el archivo pesa {tamano // (1024 * 1024)} MB: no se abrió ({p.name})"
        crudo = p.read_bytes()
    except OSError as e:  # share caído, permisos, ruta larga de Windows
        return None, f"no se pudo leer {p.name}: {e}"

    for codificacion in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            datos = json.loads(crudo.decode(codificacion))
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if not isinstance(datos, dict):
            return None, f"{p.name} no tiene la forma de un RIPS (no es un objeto JSON)"
        return datos, ""
    return None, f"{p.name} no se pudo interpretar como JSON"


def fechas_de_datos(datos: dict, archivo: str = "") -> FechasAtencion:
    """Saca las fechas de un RIPS ya cargado, usando el lector del motor."""
    from app.services.preauditoria_rips import RipsFactura, es_rips, traducir

    if not es_rips(datos):
        return FechasAtencion(
            archivo=archivo,
            problema="el archivo no es un RIPS (no trae el arreglo `usuarios`)",
        )
    try:
        rips = RipsFactura.model_validate(datos)
        payload, _omisiones = traducir(rips)
    except Exception as e:  # pydantic: estructura que no cumple la norma
        logger.warning("RIPS ilegible (%s): %s", archivo or "sin nombre", e)
        return FechasAtencion(
            archivo=archivo,
            problema=f"el RIPS no cumple la estructura de la Resolución 2275: {str(e)[:200]}",
        )

    atencion = payload.atencion
    faltantes = []
    if atencion.fecha_ingreso is None:
        faltantes.append("fecha de ingreso")
    if atencion.fecha_egreso is None:
        faltantes.append("fecha de egreso")

    # En las cuentas ambulatorias el lector no encuentra una fecha de salida:
    # toma la última fecha de atención que haya. Eso es una deducción, no un
    # dato, y quien lo use tiene que saberlo.
    deducido = bool(atencion.fecha_egreso) and (atencion.tipo or "") == "AMBULATORIO"

    return FechasAtencion(
        factura=payload.factura or "",
        fecha_ingreso=atencion.fecha_ingreso,
        fecha_egreso=atencion.fecha_egreso,
        tipo_atencion=atencion.tipo or "",
        archivo=archivo,
        problema=("el RIPS no trae " + " ni ".join(faltantes)) if faltantes else "",
        egreso_deducido=deducido,
    )


def fechas_de_archivo(ruta: str | Path) -> FechasAtencion:
    """Abre el RIPS del disco y saca las fechas. No lanza excepciones."""
    p = Path(ruta)
    datos, problema = cargar_json(p)
    if datos is None:
        return FechasAtencion(archivo=p.name, problema=problema)
    return fechas_de_datos(datos, archivo=p.name)
