"""Objeciones para DGH — armar el archivo de cargue desde la aplicación.

Es el mismo trabajo que el auditor hacía pidiendo el cruce por chat: sube el
Excel de glosas que mandó la entidad y el export de servicios facturados del
DGH, y la pantalla devuelve los dos archivos de siempre —el que se sube y el
respaldo con la hoja REVISAR— más el resumen del cruce para mirarlo antes de
descargar nada.

**No reimplementa nada.** Los bots de `tools/` son la única fuente de la
verdad: este servicio los importa, les pasa los dos archivos y recoge lo que
producen. Si una regla cambia, cambia en el bot y la pantalla la hereda.

Entidades que sabe leer hoy:

    FAMISANAR    4 columnas; el servicio va escondido en el texto de la glosa
    DISPENSARIO  5 columnas; trae el nombre del servicio en columna propia
    SAVIA SALUD  8 columnas; trae código y nombre del servicio
    SALUD TOTAL  6 columnas; sólo el nombre del servicio, sin código
    SANITAS      7 columnas; ojo, la 2ª se llama «NUMERO DE FACTURA» pero trae
                 el código de glosa

Las reglas fijas del formato (CTNCENCOS vacía, CROTIPOBJ por factura,
SLNSERPRO sin códigos inventados, el 100% de los renglones) están en CLAUDE.md
y las aplica y comprueba el propio bot: acá solo se recoge el veredicto.
"""

from __future__ import annotations

import importlib
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"

# Tamaño máximo por archivo. El export del DGH más grande visto ronda los 2 MB
# (2.264 servicios); 25 MB deja margen sobrado sin permitir un volcado entero.
MAX_BYTES = 25 * 1024 * 1024

CONFIANZAS = ("ALTA", "MEDIA", "BAJA", "SIN CRUCE")


class ErrorObjeciones(RuntimeError):
    """Algo que el auditor puede entender y corregir."""


def _cargar(modulo: str):
    """Importa un bot de `tools/` sin dejar `sys.path` sucio."""
    ruta = str(_TOOLS)
    agregado = ruta not in sys.path
    if agregado:
        sys.path.insert(0, ruta)
    try:
        return importlib.import_module(modulo)
    finally:
        if agregado and ruta in sys.path:
            sys.path.remove(ruta)


# ─── Qué entidad mandó el archivo ────────────────────────────────────────────


@dataclass(frozen=True)
class Entidad:
    """Una entidad que el motor sabe procesar."""

    id: str
    nombre: str
    # Nombre corto para los archivos, el mismo que usa el bot por consola
    # (OBJECIONES_SALUDTOTAL_…, no OBJECIONES_SALUD_…).
    corto: str
    modulo: str
    # Cómo se reconoce su archivo: encabezados que deben estar (normalizados).
    senas: tuple[str, ...]
    columnas: int
    ayuda: str

    def como_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "nombre": self.nombre,
            "corto": self.corto,
            "columnas": self.columnas,
            "ayuda": self.ayuda,
        }


ENTIDADES: tuple[Entidad, ...] = (
    Entidad(
        id="famisanar",
        nombre="FAMISANAR",
        corto="FAMISANAR",
        modulo="organizar_objeciones_famisanar",
        senas=("NRO_FACTURA", "CODIGO_DEVOLUCION", "VALOR DEVOLUCION", "OBSERVACION"),
        columnas=4,
        ayuda="Export DEVYGLOSAS: factura, código de devolución, valor y observación.",
    ),
    Entidad(
        id="dispensario",
        nombre="Dispensario Médico",
        corto="DISPENSARIO",
        modulo="organizar_objeciones_dispensario",
        senas=("FACTURA", "VALOR GLOSA INICIAL", "SERVICIO OBJETADO", "CODIGO GLOSA INICIAL"),
        columnas=5,
        ayuda="Excel de glosa inicial, con el servicio objetado en su propia columna.",
    ),
    Entidad(
        id="savia",
        nombre="SAVIA SALUD",
        corto="SAVIA",
        modulo="organizar_objeciones_savia",
        senas=("NUMERO_FACTURA", "COD_SERVICIO", "VALOR_GLOSA", "MOTIVO_ESP_GLOSA_VALOR_A"),
        columnas=8,
        ayuda="Export de 8 columnas, con el código y el nombre del servicio en columnas propias.",
    ),
    Entidad(
        id="saludtotal",
        nombre="SALUD TOTAL",
        corto="SALUDTOTAL",
        modulo="organizar_objeciones_saludtotal",
        senas=("NUMEROFAC_", "NOMBRESERVICIO", "VALORGLOSATOTALXSERV", "CODMOTVGLOSAESPC"),
        columnas=6,
        ayuda="Export NotificacionGLS. No manda código de servicio: se ubica por nombre y valor.",
    ),
    Entidad(
        id="sanitas",
        nombre="SANITAS",
        corto="SANITAS",
        modulo="organizar_objeciones_sanitas",
        senas=("NUMERO DE FACTURA", "VALOR REAL GLOSA", "CODIGO PROCEDIMIENTO"),
        columnas=7,
        ayuda="Hoja «Glosa». Ojo: la 2ª columna dice «NUMERO DE FACTURA» pero trae el código de glosa.",
    ),
)


def catalogo_entidades() -> list[dict[str, Any]]:
    """Las entidades que la pantalla puede ofrecer."""
    return [e.como_dict() for e in ENTIDADES]


def _encabezados(datos: bytes) -> list[str]:
    """Los encabezados de la primera hoja con contenido, normalizados."""
    from openpyxl import load_workbook

    cruce = _cargar("_cruce_dgh")
    with tempfile.TemporaryDirectory(prefix="objeciones-") as carpeta:
        ruta = Path(carpeta) / "entrada.xlsx"
        ruta.write_bytes(datos)
        try:
            wb = load_workbook(filename=str(ruta), data_only=True, read_only=True)
        except Exception as exc:  # archivo corrupto o que no es Excel
            raise ErrorObjeciones(
                "No pude abrir el archivo: ¿seguro que es un Excel (.xlsx)?"
            ) from exc
        try:
            for ws in wb.worksheets:
                fila = next(ws.iter_rows(values_only=True), None)
                if fila and any(fila):
                    return [cruce.norm_header(c) for c in fila if c is not None]
            return []
        finally:
            wb.close()


def detectar_entidad(datos: bytes) -> Entidad:
    """Adivina de quién es el archivo por sus encabezados.

    Gana la entidad que tenga más señas presentes; si ninguna llega a dos, se
    devuelve un error que dice qué se leyó, en vez de procesar a ciegas con el
    lector equivocado (que es como salen los archivos malos sin que se note).
    """
    cabecera = set(_encabezados(datos))
    if not cabecera:
        raise ErrorObjeciones("El archivo de la entidad está vacío.")

    puntajes = [(sum(1 for s in e.senas if s in cabecera), e) for e in ENTIDADES]
    puntajes.sort(key=lambda p: p[0], reverse=True)
    mejor, entidad = puntajes[0]
    if mejor < 2:
        leidos = ", ".join(sorted(cabecera)[:8])
        raise ErrorObjeciones(
            "No reconozco de qué entidad es este archivo. Encabezados leídos: "
            f"{leidos}. Elegí la entidad a mano si el formato cambió."
        )
    return entidad


def entidad_por_id(id_entidad: str) -> Entidad:
    for e in ENTIDADES:
        if e.id == id_entidad:
            return e
    raise ErrorObjeciones(f"No conozco la entidad '{id_entidad}'.")


# ─── Utilidades ──────────────────────────────────────────────────────────────


def _fecha(valor: str | date | datetime | None) -> datetime:
    if isinstance(valor, datetime):
        return valor
    if isinstance(valor, date):
        return datetime(valor.year, valor.month, valor.day)
    texto = (valor or "").strip()
    if not texto:
        hoy = date.today()
        return datetime(hoy.year, hoy.month, hoy.day)
    try:
        return datetime.strptime(texto, "%Y-%m-%d")
    except ValueError as exc:
        raise ErrorObjeciones(f"Fecha inválida: '{texto}'. Se espera AAAA-MM-DD.") from exc


# ─── El resultado ────────────────────────────────────────────────────────────


@dataclass
class Resultado:
    """Lo que la pantalla necesita mostrar y lo que el auditor descarga."""

    entidad: str
    entidad_id: str
    fecha: str
    facturas: int
    objeciones: int
    valor_total: int
    confianza: dict[str, int] = field(default_factory=dict)
    revisar: list[dict[str, Any]] = field(default_factory=list)
    por_factura: list[dict[str, Any]] = field(default_factory=list)
    reglas_ok: bool = True
    fallas_reglas: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    nombre_objeciones: str = ""
    nombre_cruce: str = ""
    objeciones_xlsx: bytes = b""
    cruce_xlsx: bytes = b""

    @property
    def ubicadas(self) -> int:
        return self.confianza.get("ALTA", 0) + self.confianza.get("MEDIA", 0)

    @property
    def pendientes(self) -> int:
        """Lo que hay que mirar a mano: cruce débil, sin cruce o con alerta."""
        return len(self.revisar)

    def resumen(self) -> dict[str, Any]:
        """El resultado SIN los archivos, para responder en JSON."""
        return {
            "entidad": self.entidad,
            "entidad_id": self.entidad_id,
            "fecha": self.fecha,
            "facturas": self.facturas,
            "objeciones": self.objeciones,
            "valor_total": self.valor_total,
            "confianza": self.confianza,
            "ubicadas": self.ubicadas,
            "pendientes": self.pendientes,
            "revisar": self.revisar,
            "por_factura": self.por_factura,
            "reglas_ok": self.reglas_ok,
            "fallas_reglas": self.fallas_reglas,
            "avisos": self.avisos,
            "nombre_objeciones": self.nombre_objeciones,
            "nombre_cruce": self.nombre_cruce,
        }


# ─── El armado, entidad por entidad ──────────────────────────────────────────


def _filas_famisanar(bot, ruta: Path, fecha: datetime, servicios, trazas) -> list[dict]:
    return bot.construir_registros(
        ruta,
        fecha=fecha,
        consecutivo=1,
        codigo_sufijo="01",
        mapa_codigos=None,
        servicios_dgh=servicios,
        trazas=trazas,
    )


def _filas_dispensario(bot, ruta: Path, fecha: datetime, servicios, trazas) -> list[dict]:
    objeciones = bot.leer_excel_glosa_inicial(ruta)
    filas = bot.filas_desde_excel(objeciones, fecha, servicios, trazas)
    # Ese bot devuelve listas posicionales; acá se usan dicts como los demás.
    return [dict(zip(bot.ENCABEZADOS, f, strict=True)) for f in filas]


def _filas_savia(bot, ruta: Path, fecha: datetime, servicios, trazas) -> list[dict]:
    return bot.construir_registros(
        ruta,
        fecha=fecha,
        consecutivo=1,
        codigo_sufijo="01",
        mapa_codigos=None,
        servicios_dgh=servicios,
        trazas=trazas,
    )


def _filas_saludtotal(bot, ruta: Path, fecha: datetime, servicios, trazas) -> list[dict]:
    return bot.construir_registros(
        ruta, fecha=fecha, consecutivo=1, servicios_dgh=servicios, trazas=trazas
    )


def _filas_sanitas(bot, ruta: Path, fecha: datetime, servicios, trazas) -> list[dict]:
    return bot.construir_filas(bot.leer_sanitas(ruta), fecha, servicios, trazas)


_ARMADORES = {
    "famisanar": _filas_famisanar,
    "dispensario": _filas_dispensario,
    "savia": _filas_savia,
    "saludtotal": _filas_saludtotal,
    "sanitas": _filas_sanitas,
}


def procesar(
    archivo_entidad: bytes,
    archivo_dgh: bytes,
    entidad_id: str | None = None,
    fecha: str | date | datetime | None = None,
) -> Resultado:
    """Arma los dos archivos a partir de los dos Excel que subió el auditor."""
    if not archivo_entidad:
        raise ErrorObjeciones("Falta el archivo de glosas de la entidad.")
    if not archivo_dgh:
        raise ErrorObjeciones(
            "Falta el export de servicios facturados del DGH. Sin él no se puede "
            "saber a qué servicio va cada objeción y el archivo saldría sin códigos."
        )
    for datos, cual in ((archivo_entidad, "de la entidad"), (archivo_dgh, "del DGH")):
        if len(datos) > MAX_BYTES:
            raise ErrorObjeciones(f"El archivo {cual} pesa más de {MAX_BYTES // (1024 * 1024)} MB.")

    entidad = entidad_por_id(entidad_id) if entidad_id else detectar_entidad(archivo_entidad)
    momento = _fecha(fecha)
    cruce = _cargar("_cruce_dgh")
    bot = _cargar(entidad.modulo)
    avisos: list[str] = []

    # Todo pasa dentro de una carpeta temporal que se borra sola: los archivos
    # del auditor no quedan tirados en el servidor.
    with tempfile.TemporaryDirectory(prefix="objeciones-") as carpeta:
        base = Path(carpeta)
        ruta_dgh = base / "servicios_dgh.xlsx"
        ruta_entidad = base / "glosas_entidad.xlsx"
        salida_obj = base / "objeciones.xlsx"
        salida_cruce = base / "cruce.xlsx"
        ruta_dgh.write_bytes(archivo_dgh)
        ruta_entidad.write_bytes(archivo_entidad)

        try:
            servicios = cruce.leer_servicios_dgh(ruta_dgh, avisar=avisos.append)
        except ValueError as exc:
            raise ErrorObjeciones(str(exc)) from exc

        trazas: list[dict] = []
        try:
            filas = _ARMADORES[entidad.id](bot, ruta_entidad, momento, servicios, trazas)
        except ValueError as exc:
            raise ErrorObjeciones(str(exc)) from exc
        if not filas:
            raise ErrorObjeciones("El archivo de la entidad no trae ninguna objeción.")

        # Las reglas fijas se comprueban sobre lo que se va a entregar.
        fallas = cruce.verificar_reglas(
            [
                {
                    "factura": f["CRNCXC"],
                    "slnserpro": f["SLNSERPRO"],
                    "ctncencos": f["CTNCENCOS"],
                    "crotipobj": f["CROTIPOBJ"],
                    "codigo_glosa": f["CRNCONOBJ"],
                }
                for f in filas
            ],
            servicios,
        )

        _escribir_objeciones(bot, entidad.id, filas, salida_obj)
        cruce.escribir_reporte_cruce(trazas, salida_cruce, entidad=entidad.nombre)

        sufijo = momento.strftime("%d%m%Y")
        corto = entidad.corto
        facturas = sorted({f["CRNCXC"] for f in filas})
        return Resultado(
            entidad=entidad.nombre,
            entidad_id=entidad.id,
            fecha=momento.strftime("%Y-%m-%d"),
            facturas=len(facturas),
            objeciones=len(filas),
            valor_total=sum(int(f["CROVALOBJ"] or 0) for f in filas),
            confianza={k: sum(1 for t in trazas if t["confianza"] == k) for k in CONFIANZAS},
            revisar=_filas_revisar(trazas),
            por_factura=_por_factura(filas, trazas),
            reglas_ok=not fallas,
            fallas_reglas=fallas,
            avisos=avisos,
            nombre_objeciones=f"OBJECIONES_{corto}_{sufijo}.xlsx",
            nombre_cruce=f"CRUCE_{corto}_{sufijo}.xlsx",
            objeciones_xlsx=salida_obj.read_bytes(),
            cruce_xlsx=salida_cruce.read_bytes(),
        )


def _escribir_objeciones(bot, entidad_id: str, filas: list[dict], salida: Path) -> None:
    """Cada bot escribe su Excel; el formato de celdas es el suyo."""
    if entidad_id == "saludtotal":
        bot.escribir_consolidado(filas, salida)
    elif entidad_id == "dispensario":
        bot.escribir_excel([[f[c] for c in bot.ENCABEZADOS] for f in filas], salida)
    elif entidad_id == "sanitas":
        bot.escribir_objeciones(filas, salida)
    else:
        bot.escribir_consolidado(filas, salida)


def _filas_revisar(trazas: list[dict]) -> list[dict[str, Any]]:
    """Lo que el auditor tiene que mirar, listo para la tabla de la pantalla."""
    return [
        {
            "factura": t["factura"],
            "codigo_glosa": t["codigo_objecion"],
            "valor": t["valor"],
            "servicio_entidad": t["desc_entidad"],
            "codigo_entidad": t["cod_entidad"],
            "servicio_dgh": t["servicio_dgh"],
            "codigo_dgh": t["cod_dgh"],
            "confianza": t["confianza"],
            "motivos": t["motivos"],
            "aviso": t["aviso"],
        }
        for t in trazas
        if t["aviso"] or t["confianza"] in ("BAJA", "SIN CRUCE")
    ]


def _por_factura(filas: list[dict], trazas: list[dict]) -> list[dict[str, Any]]:
    """Una línea por factura: cuántas objeciones, cuánto y qué falta."""
    resumen: dict[str, dict[str, Any]] = {}
    for f in filas:
        d = resumen.setdefault(
            f["CRNCXC"],
            {"factura": f["CRNCXC"], "objeciones": 0, "valor": 0, "sin_codigo": 0, "tipo": 0},
        )
        d["objeciones"] += 1
        d["valor"] += int(f["CROVALOBJ"] or 0)
        d["sin_codigo"] += 1 if not f["SLNSERPRO"] else 0
        d["tipo"] = f["CROTIPOBJ"]
    pendientes: dict[str, int] = {}
    for t in trazas:
        if t["aviso"] or t["confianza"] in ("BAJA", "SIN CRUCE"):
            pendientes[t["factura"]] = pendientes.get(t["factura"], 0) + 1
    for factura, d in resumen.items():
        d["revisar"] = pendientes.get(factura, 0)
    return sorted(resumen.values(), key=lambda d: d["factura"])
