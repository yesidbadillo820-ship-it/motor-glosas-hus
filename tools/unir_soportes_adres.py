"""unir_soportes_adres.py — un solo PDF de soportes por factura, en el orden del ADRES.

En la carpeta de cada factura los soportes están sueltos: la respuesta a la
glosa, la epicrisis, la historia clínica, las ayudas diagnósticas, los
medicamentos… Este bot los **une en un solo PDF**, y los pone en el **orden
exacto** que pide el área:

    1. RESPUESTA A GLOSA          6. NOTAS DE ENFERMERÍA
    2. EPICRISIS                  7. INSUMOS
    3. HISTORIA CLÍNICA           8. OTROS
       (consulta de urgencias,    9. DETALLADO (queda en Excel, aparte:
        terapias, curaciones,        NO entra al PDF unido)
        evoluciones, procedimientos)
    4. AYUDAS DIAGNÓSTICAS
    5. MEDICAMENTOS

Dentro de la HISTORIA CLÍNICA se respeta el orden de las cinco subcarpetas de
la lista; dentro de cada grupo, los archivos van en orden natural de nombre
(2 antes que 10).

CÓMO SABE DE QUÉ ES CADA PDF. Por el **nombre del archivo**: busca las palabras
con que el equipo los nombra (EPICRISIS, URGENCIAS, TERAPIA, CURACION,
EVOLUCION, MEDICAMENTOS, ENFERMERIA, INSUMOS…) y las abreviaturas que usa el
auditor (EPI, HC, DX, MED, NTE, INS). Lo que no reconoce **no se pierde**: va al
grupo OTROS y sale listado en el reporte para que el auditor lo revise.

Las palabras se pueden cambiar sin tocar el código, con `--mapa-nombres`.

SIMULA POR DEFECTO. Unir soportes no se deshace de un clic, así que el bot
primero **muestra qué haría** —qué archivo va en qué grupo y en qué orden— y no
escribe nada mientras no se le pase `--aplicar`. El PDF unido queda como
`<FACTURA>_SOPORTES.pdf` dentro de la carpeta de la factura, y nunca se toma a
sí mismo como entrada, así que se puede correr las veces que haga falta.

USO (Windows):

    REM 1) PRIMERO en simulación: muestra el orden y no toca nada.
    py tools\\unir_soportes_adres.py --carpeta "Z:\\...\\TECNICOS\\CAROLINA"

    REM 2) Si el listado se ve bien, con --aplicar sí une.
    py tools\\unir_soportes_adres.py --carpeta "Z:\\...\\TECNICOS\\CAROLINA" --aplicar

    REM Con la lista de facturas a trabajar (columna con HUS...):
    py tools\\unir_soportes_adres.py --carpeta "Z:\\..." --facturas "facturas.xlsx" --aplicar

INSTALACIÓN (una vez):

    py -m pip install pypdf openpyxl
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
# El motor de unión ya existe y está probado: aquí solo se le da el ORDEN.
from organizar_soportes_por_factura import factura_del_nombre  # noqa: E402
from unir_pdfs_carpetas import _cargar_lector_escritor, clave_natural, unir_pdfs  # noqa: E402

logger = logging.getLogger("unir_soportes_adres")

SUFIJO_UNIDO = "_SOPORTES"


# ─── Los nueve grupos, en el orden que pide el área ──────────────────────────


@dataclass(frozen=True)
class Grupo:
    """Un renglón de la lista de soportes."""

    orden: int
    clave: str
    titulo: str
    palabras: tuple[str, ...]


# El orden de esta tupla ES el orden del PDF. Las palabras se comparan sin
# tildes y en mayúsculas contra el nombre del archivo.
GRUPOS: tuple[Grupo, ...] = (
    Grupo(
        1,
        "RESPUESTA",
        "RESPUESTA A GLOSA",
        (
            "RESPUESTA A GLOSA",
            "RESPUESTA GLOSA",
            "RTA GLOSA",
            # Así se llama el PDF que arma respuestas_adres_por_factura.py:
            # RTA_ADRES_HUS311371.pdf. Es la respuesta a glosa del paquete.
            "RTA ADRES",
            "RESPUESTA",
        ),
    ),
    Grupo(2, "EPICRISIS", "EPICRISIS", ("EPICRISIS", "EPICRIS", "EPI")),
    Grupo(
        3,
        "URGENCIAS",
        "HISTORIA CLINICA - CONSULTA DE URGENCIAS",
        ("CONSULTA DE URGENCIAS", "URGENCIAS", "TRIAGE"),
    ),
    Grupo(
        4,
        "TERAPIAS",
        "HISTORIA CLINICA - TERAPIAS",
        ("TERAPIAS", "TERAPIA", "FISIOTERAPIA", "RESPIRATORIA"),
    ),
    Grupo(5, "CURACIONES", "HISTORIA CLINICA - CURACIONES", ("CURACIONES", "CURACION")),
    Grupo(
        6,
        "EVOLUCIONES",
        "HISTORIA CLINICA - EVOLUCIONES",
        ("EVOLUCIONES", "EVOLUCION", "INTERCONSULTA"),
    ),
    Grupo(
        7,
        "PROCEDIMIENTOS",
        "HISTORIA CLINICA - PROCEDIMIENTOS",
        ("PROCEDIMIENTOS", "PROCEDIMIENTO", "DESCRIPCION QUIRURGICA", "QUIRURGICA"),
    ),
    Grupo(8, "HISTORIA", "HISTORIA CLINICA", ("HISTORIA CLINICA", "HISTORIA", "HC")),
    Grupo(
        9,
        "AYUDAS",
        "AYUDAS DIAGNOSTICAS",
        (
            "AYUDAS DIAGNOSTICAS",
            "AYUDA DIAGNOSTICA",
            "LABORATORIO",
            "IMAGENOLOGIA",
            "RADIOGRAFIA",
            "TOMOGRAFIA",
            "ANGIOTOMOGRAFIA",
            "ECOGRAFIA",
            "RESONANCIA",
            "ELECTROMIOGRAFIA",
            "NEUROCONDUCCION",
            # Así vienen nombrados los PDF de exámenes: con el nombre con que
            # salen en el detallado (bloques LABORATORIOS e IMAGENOLOGIA).
            "GLUCOMETRIA",
            "GASES ARTERIALES",
            "LACTATO",
            "HEMOGRAMA",
            "CUADRO HEMATICO",
            "PARCIAL DE ORINA",
            "CREATININA",
            "IONOGRAMA",
            "PORTATILES",
            "ECOCARDIOGRAMA",
            "DOPPLER",
            "ENDOSCOPIA",
            "DX",
        ),
    ),
    Grupo(
        10,
        "MEDICAMENTOS",
        "MEDICAMENTOS",
        ("MEDICAMENTOS", "MEDICAMENTO", "INGESTA", "PLAN DE MANEJO", "MED"),
    ),
    Grupo(
        11,
        "ENFERMERIA",
        "NOTAS DE ENFERMERIA",
        ("NOTAS DE ENFERMERIA", "NOTAS ENFERMERIA", "ENFERMERIA", "NTE"),
    ),
    Grupo(
        12,
        "INSUMOS",
        "INSUMOS",
        (
            "INSUMOS",
            "INSUMO",
            "GASTOS QUIROFANO",
            "GASTOS DE QUIROFANO",
            "QUIROFANO",
            "SOLICITUDES DE ENFERMERIA",
            "INS",
        ),
    ),
    # OTROS es a la vez un grupo con nombre propio —el equipo nombra archivos
    # «OTROS.pdf»— y el cajón donde cae lo que no se reconoce. Con sus palabras,
    # un OTROS.pdf sale RECONOCIDO y no como algo que el auditor deba mirar.
    Grupo(13, "OTROS", "OTROS", ("OTROS", "OTRO", "SOAT", "CERTIFICACION", "REPS")),
)
GRUPO_OTROS = next(g for g in GRUPOS if g.clave == "OTROS")

# El detallado NO entra al PDF: la lista lo pide en Excel, aparte.
PALABRAS_DETALLADO = ("DETALLADO", "DETALLE DE FACTURA")


def _norm(texto: object) -> str:
    """Mayúsculas, sin tildes, sin signos: para comparar nombres de archivo."""
    s = unicodedata.normalize("NFKD", str(texto or "").upper())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", s).split())


def clasificar(nombre: str, mapa: dict[str, str] | None = None) -> Grupo:
    """En qué grupo va un archivo, por su nombre.

    Gana la palabra **más larga** que aparezca, no la primera: así
    «NOTAS DE ENFERMERIA» no se lo lleva «NOTAS», y «CONSULTA DE URGENCIAS» no
    se confunde con «CONSULTA». Lo que no reconoce va a OTROS.
    """
    limpio = _norm(nombre)
    if mapa:
        for palabra, clave in mapa.items():
            if _norm(palabra) and _norm(palabra) in limpio:
                grupo = next((g for g in GRUPOS if g.clave == clave.strip().upper()), None)
                if grupo is not None:
                    return grupo
    mejor: tuple[int, Grupo] = (0, GRUPO_OTROS)
    for grupo in GRUPOS:
        for palabra in grupo.palabras:
            clave = _norm(palabra)
            if clave and _es_palabra(clave, limpio) and len(clave) > mejor[0]:
                mejor = (len(clave), grupo)
    return mejor[1]


def clasificar_con_marca(nombre: str, mapa: dict[str, str] | None = None) -> tuple[Grupo, bool]:
    """(grupo, ¿lo reconoció de verdad?).

    OTROS es a la vez un grupo con nombre propio y el cajón de lo desconocido:
    un archivo llamado «OTROS.pdf» está bien clasificado y NO debe salir en la
    lista de «revisar»; uno llamado «papel raro.pdf» sí.
    """
    grupo = clasificar(nombre, mapa)
    if grupo is not GRUPO_OTROS:
        return grupo, True
    limpio = _norm(nombre)
    caso = any(_es_palabra(_norm(p), limpio) for p in GRUPO_OTROS.palabras if _norm(p))
    if mapa and not caso:
        caso = any(_norm(p) and _norm(p) in limpio for p in mapa)
    return grupo, caso


def _es_palabra(aguja: str, pajar: str) -> bool:
    """¿Aparece `aguja` como palabra completa dentro de `pajar`?

    Con `in` a secas, «INS» (insumos) casaba dentro de «INSTITUCIONAL» y «DX»
    dentro de cualquier código. Las abreviaturas de la lista son cortas: tienen
    que ir sueltas.
    """
    return re.search(rf"(?<![A-Z0-9]){re.escape(aguja)}(?![A-Z0-9])", pajar) is not None


def es_detallado(nombre: str) -> bool:
    limpio = _norm(nombre)
    return any(_norm(p) in limpio for p in PALABRAS_DETALLADO)


# ─── Lo que se encontró en cada carpeta ──────────────────────────────────────


@dataclass
class Soporte:
    """Un PDF de la carpeta, ya clasificado."""

    ruta: Path
    grupo: Grupo
    reconocido: bool = True
    paginas: int = 0


@dataclass
class Factura:
    """Una carpeta de factura y sus soportes en orden."""

    factura: str
    carpeta: Path
    soportes: list[Soporte] = field(default_factory=list)
    detallados: list[Path] = field(default_factory=list)
    destino: Path | None = None
    paginas: int = 0
    omitidos: list[str] = field(default_factory=list)
    estado: str = ""

    def faltantes(self) -> list[str]:
        """Los grupos obligatorios que no aparecieron."""
        presentes = {s.grupo.clave for s in self.soportes}
        return [g.titulo for g in (GRUPOS[0], GRUPOS[1]) if g.clave not in presentes]


ESTADO_UNIDO = "UNIDO"
ESTADO_SIMULADO = "SE UNIRIA"
ESTADO_SIN_PDF = "SIN PDF QUE UNIR"
ESTADO_ERROR = "ERROR"


def _factura_de_carpeta(carpeta: Path) -> str:
    """`HUS379477_PEND. CARTA CORONEL` → `HUS379477`; si no hay número, el nombre.

    Usa el mismo lector que el bot que archiva los soportes: la regla de cómo se
    saca el número de factura de un nombre vive en un solo sitio.
    """
    return factura_del_nombre(carpeta.name) or carpeta.name.strip()


def planificar(
    carpeta: Path,
    facturas: set[str] | None = None,
    mapa: dict[str, str] | None = None,
) -> list[Factura]:
    """Qué se uniría en cada carpeta de factura, sin escribir nada."""
    salida: list[Factura] = []
    for sub in sorted(p for p in carpeta.iterdir() if p.is_dir()):
        numero = _factura_de_carpeta(sub)
        if facturas is not None and _norm(numero) not in facturas:
            continue
        fac = Factura(factura=numero, carpeta=sub)
        pdfs: list[Path] = []
        for ruta in sub.rglob("*"):
            if not ruta.is_file() or ruta.name.startswith(("~$", ".")):
                continue
            if ruta.suffix.lower() in (".xlsx", ".xls") and es_detallado(ruta.name):
                fac.detallados.append(ruta)
                continue
            if ruta.suffix.lower() != ".pdf":
                continue
            if ruta.stem.upper().endswith(SUFIJO_UNIDO):
                continue  # el consolidado de una corrida anterior
            if es_detallado(ruta.name):
                fac.detallados.append(ruta)
                continue
            pdfs.append(ruta)
        # Dentro de cada grupo, orden natural por el nombre del archivo.
        soportes = [
            Soporte(ruta=p, grupo=g, reconocido=ok)
            for p in pdfs
            for g, ok in [clasificar_con_marca(p.name, mapa)]
        ]
        soportes.sort(key=lambda s: (s.grupo.orden, clave_natural(s.ruta.name)))
        fac.soportes = soportes
        fac.destino = sub / f"{numero}{SUFIJO_UNIDO}.pdf"
        fac.estado = ESTADO_SIMULADO if soportes else ESTADO_SIN_PDF
        salida.append(fac)
    return salida


def unir(
    carpeta: Path,
    facturas: set[str] | None = None,
    mapa: dict[str, str] | None = None,
    aplicar: bool = False,
) -> list[Factura]:
    """Une los soportes de cada factura. Sin `aplicar`, solo dice qué haría."""
    plan = planificar(carpeta, facturas, mapa)
    if not aplicar:
        return plan
    PdfReader, PdfWriter = _cargar_lector_escritor()
    for fac in plan:
        if fac.estado != ESTADO_SIMULADO or fac.destino is None:
            continue
        try:
            paginas, omitidos = unir_pdfs(
                [s.ruta for s in fac.soportes], fac.destino, PdfReader, PdfWriter
            )
            fac.paginas, fac.omitidos = paginas, omitidos
            fac.estado = ESTADO_UNIDO if paginas else ESTADO_ERROR
            if not paginas:
                fac.omitidos.append("ningún PDF tenía páginas legibles")
        except Exception as e:  # noqa: BLE001 - una factura mala no tumba el lote
            logger.warning("  %s: %s", fac.factura, e)
            fac.estado = ESTADO_ERROR
            fac.omitidos.append(str(e))
    return plan


# ─── Reporte ─────────────────────────────────────────────────────────────────

COLUMNAS_REPORTE = (
    "FACTURA",
    "ORDEN",
    "GRUPO",
    "ARCHIVO",
    "RECONOCIDO",
    "CARPETA",
    "ESTADO",
    "OBSERVACION",
)


def escribir_reporte(ruta: Path, plan: list[Factura]) -> None:
    """Un renglón por soporte: en qué grupo quedó y en qué orden va."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(COLUMNAS_REPORTE)
        for fac in plan:
            for n, s in enumerate(fac.soportes, start=1):
                w.writerow(
                    [
                        fac.factura,
                        n,
                        s.grupo.titulo,
                        s.ruta.name,
                        "SI" if s.reconocido else "NO - revisar",
                        str(s.ruta.parent),
                        fac.estado,
                        "",
                    ]
                )
            for det in fac.detallados:
                w.writerow(
                    [
                        fac.factura,
                        "",
                        "DETALLADO (no entra al PDF)",
                        det.name,
                        "SI",
                        str(det.parent),
                        fac.estado,
                        "",
                    ]
                )
            if not fac.soportes:
                w.writerow(
                    [
                        fac.factura,
                        "",
                        "",
                        "",
                        "",
                        str(fac.carpeta),
                        fac.estado,
                        "no hay PDF que unir",
                    ]
                )
            for falta in fac.faltantes():
                w.writerow(
                    [
                        fac.factura,
                        "",
                        falta,
                        "",
                        "NO",
                        str(fac.carpeta),
                        fac.estado,
                        "FALTA este soporte",
                    ]
                )
            for om in fac.omitidos:
                w.writerow([fac.factura, "", "", "", "", str(fac.carpeta), ESTADO_ERROR, om])


# ─── Lista de facturas a trabajar ────────────────────────────────────────────


def leer_facturas(ruta: Path) -> set[str]:
    """Los números de factura de un Excel de una sola columna (o la que los traiga)."""
    from openpyxl import load_workbook

    wb = load_workbook(filename=str(ruta), data_only=True, read_only=True)
    try:
        numeros: set[str] = set()
        for hoja in wb.worksheets:
            for fila in hoja.iter_rows(values_only=True):
                for celda in fila or ():
                    texto = str(celda or "").strip()
                    if re.fullmatch(r"HUS\s*0*\d+", texto, re.IGNORECASE):
                        numeros.add(_norm(f"HUS{re.sub(r'[^0-9]', '', texto).lstrip('0')}"))
        return numeros
    finally:
        wb.close()


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _cargar_mapa(ruta: Path | None) -> dict[str, str]:
    if ruta is None:
        return {}
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        logger.error("No pude leer el mapa de nombres %s: %s", ruta, e)
        raise SystemExit(2) from None
    if not isinstance(datos, dict):
        logger.error('El mapa debe ser un objeto JSON {"ANGIOTAC": "AYUDAS", ...}')
        raise SystemExit(2)
    return {str(k): str(v) for k, v in datos.items()}


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Une los soportes de cada factura en un solo PDF, en el orden del ADRES.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--carpeta",
        type=Path,
        required=True,
        help="Carpeta del gestor (CAROLINA, CLAUDIA, OSCAR…).",
    )
    p.add_argument(
        "--facturas",
        type=Path,
        help="Excel con las facturas a trabajar. Sin esto, todas las carpetas.",
    )
    p.add_argument(
        "--mapa-nombres", type=Path, help='JSON para agregar palabras: {"ANGIOTAC": "AYUDAS"}.'
    )
    p.add_argument(
        "--aplicar", action="store_true", help="Unir de verdad. Sin esto solo muestra qué haría."
    )
    p.add_argument("--reporte-csv", type=Path, help="Listado de qué archivo quedó en qué grupo.")
    p.add_argument("--log", type=Path, help="Guarda además el log en un archivo.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if args.log is not None:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(args.log, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=handlers)

    if not args.carpeta.is_dir():
        logger.error("No existe la carpeta: %s", args.carpeta)
        return 1

    facturas: set[str] | None = None
    if args.facturas:
        if not args.facturas.is_file():
            logger.error("No existe el Excel de facturas: %s", args.facturas)
            return 1
        facturas = leer_facturas(args.facturas)
        logger.info("Lista de trabajo: %d facturas", len(facturas))

    plan = unir(args.carpeta, facturas, _cargar_mapa(args.mapa_nombres), args.aplicar)
    if args.reporte_csv:
        escribir_reporte(args.reporte_csv, plan)

    if not plan:
        logger.info("\nNo encontré carpetas de factura en %s", args.carpeta)
        return 0

    con_pdf = [f for f in plan if f.soportes]
    sin_pdf = [f for f in plan if not f.soportes]
    errores = [f for f in plan if f.estado == ESTADO_ERROR]
    sin_reconocer = [(f, s) for f in plan for s in f.soportes if not s.reconocido]

    verbo = "Se unieron" if args.aplicar else "Se unirían"
    logger.info(
        "\n%s %d factura(s), %d soporte(s).",
        verbo,
        len(con_pdf),
        sum(len(f.soportes) for f in con_pdf),
    )
    if args.aplicar:
        logger.info("Páginas escritas: %d", sum(f.paginas for f in plan))

    for fac in con_pdf[:3]:
        logger.info("\n  %s → %s", fac.factura, (fac.destino or Path()).name)
        for n, s in enumerate(fac.soportes, start=1):
            marca = "" if s.reconocido else "   <-- no reconocido, va en OTROS"
            logger.info("     %2d. [%s] %s%s", n, s.grupo.titulo, s.ruta.name, marca)
    if len(con_pdf) > 3:
        logger.info(
            "\n  … y %d factura(s) más (el detalle completo va en el reporte CSV).",
            len(con_pdf) - 3,
        )

    if sin_reconocer:
        logger.info(
            "\nArchivos que NO se reconocieron (%d) — quedaron en OTROS:", len(sin_reconocer)
        )
        for fac, s in sin_reconocer[:10]:
            logger.info("   %s: %s", fac.factura, s.ruta.name)
        if len(sin_reconocer) > 10:
            logger.info("   … y %d más, en el reporte CSV.", len(sin_reconocer) - 10)

    faltan = [(f, f.faltantes()) for f in plan if f.faltantes()]
    if faltan:
        logger.info("\nFacturas a las que les falta un soporte obligatorio (%d):", len(faltan))
        for fac, cuales in faltan[:10]:
            logger.info("   %s: falta %s", fac.factura, ", ".join(cuales))
        if len(faltan) > 10:
            logger.info("   … y %d más, en el reporte CSV.", len(faltan) - 10)

    if sin_pdf:
        logger.info(
            "\nCarpetas sin PDF que unir (%d): %s",
            len(sin_pdf),
            ", ".join(f.factura for f in sin_pdf[:12]),
        )
    if errores:
        logger.info("\nCon error (%d):", len(errores))
        for fac in errores:
            logger.info("   %s: %s", fac.factura, "; ".join(fac.omitidos))

    if not args.aplicar:
        logger.info(
            "\n*** SIMULACIÓN: no se escribió ningún PDF. Agregue --aplicar para hacerlo. ***"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
