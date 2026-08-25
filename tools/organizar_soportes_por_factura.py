"""organizar_soportes_por_factura.py — cada soporte, en la carpeta de su factura.

En la carpeta del gestor los soportes se van acumulando sueltos:

    CAROLINA\\
        HUS352904\\                              ← carpetas que ya existen
        HUS383781\\
        HUS392861-MEDICAMENTOS.pdf              ← sueltos, sin carpeta
        HUS400387 ANGIOTOMOGRAFIA.pdf
        HUS382278- INTERCONSULTAS, FOLIO 17.pdf

Este bot los mete **cada uno en la carpeta de su factura**, y **crea la carpeta
si no existe**. El número de factura se toma del comienzo del nombre del
archivo (`HUS` seguido de dígitos), que es como los nombra el equipo.

USO (Windows, desde C:\\temp-notas):

    REM 1) PRIMERO en simulación: muestra qué haría y no toca nada.
    py tools\\organizar_soportes_por_factura.py --carpeta "Z:\\...\\CAROLINA"

    REM 2) Si el listado se ve bien, con --aplicar sí mueve.
    py tools\\organizar_soportes_por_factura.py --carpeta "Z:\\...\\CAROLINA" --aplicar

Mover archivos **no se deshace**, así que el bot simula por defecto: hay que
pedirle `--aplicar` a propósito.

Nunca pisa un archivo: si en la carpeta destino ya hay uno con el mismo nombre,
al nuevo le agrega ` (2)`, ` (3)`… Los archivos que no empiezan por un número de
factura se quedan donde están y salen listados al final.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("organizar_soportes")

# Así nombra el equipo los soportes: HUS + el número, y enseguida el separador
# que sea (guion, guion bajo, espacio, dos guiones…).
_RE_FACTURA = re.compile(r"^\s*(HUS\s*0*(\d+))", re.IGNORECASE)
# Algunos soportes no EMPIEZAN por el número: los arma el motor con su propio
# prefijo (`RTA_ADRES_HUS311371.pdf`) o vienen del ADRES con el código de
# habilitación adelante (`680010079201_HUS378523_FACOSTE.pdf`).
_RE_FACTURA_ADENTRO = re.compile(r"HUS\s*0*(\d+)", re.IGNORECASE)

ESTADO_MOVIDO = "MOVIDO"
ESTADO_RENOMBRADO = "MOVIDO Y RENOMBRADO"
ESTADO_YA_ESTABA = "YA ESTABA EN SU CARPETA"
ESTADO_SIN_FACTURA = "SIN NÚMERO DE FACTURA"
ESTADO_ERROR = "ERROR"


@dataclass
class Movimiento:
    """Qué se hizo con un archivo."""

    archivo: str
    factura: str = ""
    carpeta: str = ""
    nombre_final: str = ""
    estado: str = ""
    carpeta_creada: bool = False
    observacion: str = ""


def factura_del_nombre(nombre: str) -> str:
    """El número de factura con el que empieza el nombre, o cadena vacía.

    `HUS392861-MEDICAMENTOS.pdf` → `HUS392861`.
    `HUS 0000352890 recibido.pdf` → `HUS352890` (sin espacio ni ceros de
    relleno, que es como se llaman las carpetas).
    `RTA_ADRES_HUS311371.pdf` → `HUS311371` (el número no va al principio).
    `HUS1 vs HUS2.pdf` → `""` (nombra dos facturas: no se adivina).
    """
    m = _RE_FACTURA.match(nombre)
    if m:
        return f"HUS{m.group(2)}"
    # Si no empieza por el número, sirve igual mientras el nombre nombre UNA
    # sola factura: `RTA_ADRES_HUS311371.pdf` → HUS311371. Con dos números
    # distintos no se adivina — se queda donde está y sale en el listado.
    numeros = {n.lstrip("0") or "0" for n in _RE_FACTURA_ADENTRO.findall(nombre)}
    return f"HUS{numeros.pop()}" if len(numeros) == 1 else ""


def nombre_libre(carpeta: Path, nombre: str) -> tuple[Path, bool]:
    """(ruta libre en la carpeta, ¿hubo que renombrar?).

    No se pisa nada: si el nombre está ocupado, se prueba ` (2)`, ` (3)`…
    """
    destino = carpeta / nombre
    if not destino.exists():
        return destino, False
    tallo, sufijo = Path(nombre).stem, Path(nombre).suffix
    for n in range(2, 1000):
        candidato = carpeta / f"{tallo} ({n}){sufijo}"
        if not candidato.exists():
            return candidato, True
    raise ValueError(f"No hay un nombre libre para {nombre!r} en {carpeta}")


def planificar(carpeta: Path, patron: str = "*.pdf") -> list[Movimiento]:
    """Qué habría que mover, sin mover nada.

    Solo mira los archivos que están **sueltos** en la carpeta: lo que ya está
    dentro de una subcarpeta se deja quieto.
    """
    planes: list[Movimiento] = []
    carpetas_previstas: set[Path] = set()
    for ruta in sorted(carpeta.glob(patron)):
        if not ruta.is_file() or ruta.name.startswith(("~$", ".")):
            continue
        factura = factura_del_nombre(ruta.name)
        if not factura:
            planes.append(
                Movimiento(
                    archivo=ruta.name,
                    estado=ESTADO_SIN_FACTURA,
                    observacion="El nombre no empieza por un número de factura (HUS…).",
                )
            )
            continue
        destino_carpeta = carpeta / factura
        nueva = not destino_carpeta.exists() and destino_carpeta not in carpetas_previstas
        if nueva:
            carpetas_previstas.add(destino_carpeta)
        planes.append(
            Movimiento(
                archivo=ruta.name,
                factura=factura,
                carpeta=factura,
                nombre_final=ruta.name,
                estado=ESTADO_MOVIDO,
                carpeta_creada=nueva,
            )
        )
    return planes


def organizar(carpeta: Path, patron: str = "*.pdf", aplicar: bool = False) -> list[Movimiento]:
    """Mueve cada soporte a la carpeta de su factura. Si `aplicar` es False,
    solo dice qué haría."""
    planes = planificar(carpeta, patron)
    if not aplicar:
        return planes

    for plan in planes:
        if plan.estado != ESTADO_MOVIDO:
            continue
        origen = carpeta / plan.archivo
        destino_carpeta = carpeta / plan.factura
        try:
            destino_carpeta.mkdir(exist_ok=True)
            destino, renombrado = nombre_libre(destino_carpeta, origen.name)
            shutil.move(str(origen), str(destino))
            plan.nombre_final = destino.name
            if renombrado:
                plan.estado = ESTADO_RENOMBRADO
                plan.observacion = (
                    f"Ya había un archivo llamado «{origen.name}» en esa carpeta; "
                    "este se guardó con otro nombre para no pisarlo."
                )
        except Exception as e:  # noqa: BLE001 - un archivo malo no tumba el lote
            logger.warning("  %s: %s", plan.archivo, e)
            plan.estado = ESTADO_ERROR
            plan.observacion = str(e)
    return planes


def escribir_reporte(ruta: Path, movimientos: list[Movimiento]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(
            [
                "ARCHIVO",
                "FACTURA",
                "CARPETA",
                "NOMBRE FINAL",
                "ESTADO",
                "CARPETA NUEVA",
                "OBSERVACION",
            ]
        )
        for m in movimientos:
            w.writerow(
                [
                    m.archivo,
                    m.factura,
                    m.carpeta,
                    m.nombre_final,
                    m.estado,
                    "SI" if m.carpeta_creada else "",
                    m.observacion,
                ]
            )


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Mete cada soporte suelto en la carpeta de su factura.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--carpeta", type=Path, required=True, help="La carpeta del gestor.")
    p.add_argument("--patron", default="*.pdf", help="Qué archivos mover (por defecto, los PDF).")
    p.add_argument(
        "--aplicar",
        action="store_true",
        help="Mover de verdad. Sin esto solo muestra qué haría.",
    )
    p.add_argument("--reporte-csv", type=Path, help="Listado de lo que se movió y a dónde.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.carpeta.is_dir():
        logger.error("No existe la carpeta: %s", args.carpeta)
        return 1

    movimientos = organizar(args.carpeta, args.patron, args.aplicar)
    if args.reporte_csv:
        escribir_reporte(args.reporte_csv, movimientos)

    a_mover = [m for m in movimientos if m.estado in (ESTADO_MOVIDO, ESTADO_RENOMBRADO)]
    sin_factura = [m for m in movimientos if m.estado == ESTADO_SIN_FACTURA]
    errores = [m for m in movimientos if m.estado == ESTADO_ERROR]
    nuevas = sorted({m.carpeta for m in movimientos if m.carpeta_creada})

    if not movimientos:
        print(f"\nNo hay archivos sueltos que organizar en {args.carpeta}")
        return 0

    verbo = "Se movieron" if args.aplicar else "Se moverían"
    print(f"\n{verbo} {len(a_mover)} archivo(s) a {len({m.carpeta for m in a_mover})} carpeta(s).")

    if nuevas:
        etiqueta = "Carpetas creadas" if args.aplicar else "Carpetas que se crearían"
        print(f"\n{etiqueta} ({len(nuevas)}) — revise que sean facturas de verdad:")
        for carpeta in nuevas:
            print(f"   {carpeta}")

    renombrados = [m for m in movimientos if m.estado == ESTADO_RENOMBRADO]
    if renombrados:
        print(f"\nOJO — {len(renombrados)} archivo(s) se guardaron con otro nombre:")
        for m in renombrados:
            print(f"   {m.archivo}  →  {m.carpeta}\\{m.nombre_final}")

    if sin_factura:
        print(f"\nSe quedaron donde estaban ({len(sin_factura)}), no dicen de qué factura son:")
        for m in sin_factura:
            print(f"   {m.archivo}")

    if errores:
        print(f"\nCon error ({len(errores)}):")
        for m in errores:
            print(f"   {m.archivo}: {m.observacion}")

    if not args.aplicar:
        print("\n*** SIMULACIÓN: no se movió nada. Agregue --aplicar para hacerlo. ***")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
