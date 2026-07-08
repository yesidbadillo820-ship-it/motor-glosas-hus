"""organizar_cargue_masivo_coosalud.py — Extrae un ZIP de COOSALUD y organiza los Excel en carpetas.

Toma el ZIP que descarga el equipo de cartera (p. ej. `COOSALUD 1.zip`), que trae
cientos de archivos .xlsx sueltos en la raíz, y los reparte en tres carpetas según
su nombre, dejando todo listo para el cargue masivo:

    <ESCRITORIO>\\CARGUE MASIVO COOSALUD\\
        DETALLES\\    <- archivos "DETALLE HUS######.xlsx"
        FACTURAS\\    <- archivos "HUS######.xlsx"        (sin prefijo)
        GLOSAS\\      <- archivos "GLOSAS HUS######.xlsx"

CLASIFICACIÓN (por el nombre del archivo, sin importar mayúsculas/espacios):
    empieza por "DETALLE"  -> DETALLES
    empieza por "GLOSA"    -> GLOSAS     (cubre GLOSA y GLOSAS)
    empieza por "HUS<núm>" -> FACTURAS   (la factura, sin prefijo)
    cualquier otra cosa    -> SIN_CLASIFICAR (se reporta, no se pierde nada)

Es IDEMPOTENTE: si lo corrés dos veces, los archivos que ya estén no se
vuelven a escribir (salvo que uses --sobrescribir).

USO RÁPIDO
----------

    REM Lo normal: extraer el ZIP al Escritorio (D:\\USUARIO CARTERA\\Desktop)
    py organizar_cargue_masivo_coosalud.py --zip "C:\\...\\COOSALUD 1.zip"

    REM Ver qué haría, sin escribir nada (ensayo)
    py organizar_cargue_masivo_coosalud.py --zip "C:\\...\\COOSALUD 1.zip" --dry-run

    REM Elegir otro Escritorio / nombre de carpeta / guardar reporte CSV
    py organizar_cargue_masivo_coosalud.py ^
        --zip     "C:\\...\\COOSALUD 1.zip" ^
        --destino "D:\\USUARIO CARTERA\\Desktop" ^
        --nombre  "CARGUE MASIVO COOSALUD" ^
        --reporte "D:\\USUARIO CARTERA\\Desktop\\reporte_cargue.csv"

No requiere instalar nada: usa solo la librería estándar de Python 3.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
import unicodedata
import zipfile
from pathlib import Path

logger = logging.getLogger("cargue_coosalud")

# --- Nombres de las carpetas destino (igual que en el flujo manual) ---------
CARPETA_DETALLES = "DETALLES"
CARPETA_FACTURAS = "FACTURAS"
CARPETA_GLOSAS = "GLOSAS"
CARPETA_SIN_CLASIFICAR = "SIN_CLASIFICAR"

# Escritorio por defecto del equipo de cartera.
DESTINO_DEFECTO = r"D:\USUARIO CARTERA\Desktop"
NOMBRE_DEFECTO = "CARGUE MASIVO COOSALUD"

# Un archivo de factura es "HUS" seguido de dígitos (sin prefijo DETALLE/GLOSAS).
RE_FACTURA = re.compile(r"^HUS\d+", re.IGNORECASE)


def setup_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )


def _normalizar(nombre: str) -> str:
    """Mayúsculas, sin acentos y sin espacios sobrantes al inicio, para clasificar."""
    sin_acentos = "".join(
        c for c in unicodedata.normalize("NFKD", nombre) if not unicodedata.combining(c)
    )
    return sin_acentos.upper().strip()


def clasificar(nombre_archivo: str) -> str:
    """Devuelve la carpeta destino según el nombre del archivo."""
    base = _normalizar(nombre_archivo)
    if base.startswith("DETALLE"):
        return CARPETA_DETALLES
    if base.startswith("GLOSA"):  # GLOSA / GLOSAS
        return CARPETA_GLOSAS
    if RE_FACTURA.match(base):
        return CARPETA_FACTURAS
    return CARPETA_SIN_CLASIFICAR


def _nombre_base(entrada: str) -> str:
    """Nombre del archivo aunque el ZIP traiga subcarpetas o rutas con \\ o /."""
    # Algunos ZIP de Windows usan backslash como separador interno.
    return entrada.replace("\\", "/").rstrip("/").split("/")[-1]


def organizar_zip(
    zip_path: Path,
    destino_base: Path,
    nombre_carpeta: str,
    *,
    dry_run: bool = False,
    sobrescribir: bool = False,
) -> list[dict]:
    """Extrae y clasifica el ZIP. Devuelve una lista de filas para el reporte."""
    if not zip_path.is_file():
        raise FileNotFoundError(f"No existe el ZIP: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"El archivo no es un ZIP válido: {zip_path}")

    raiz = destino_base / nombre_carpeta
    logger.info("ZIP     : %s", zip_path)
    logger.info("Destino : %s", raiz)
    if dry_run:
        logger.info("MODO ENSAYO (--dry-run): no se escribe nada en disco.\n")

    # Crear el árbol de carpetas destino (salvo en dry-run).
    subcarpetas = [
        CARPETA_DETALLES,
        CARPETA_FACTURAS,
        CARPETA_GLOSAS,
        CARPETA_SIN_CLASIFICAR,
    ]
    if not dry_run:
        for sub in subcarpetas:
            (raiz / sub).mkdir(parents=True, exist_ok=True)

    filas: list[dict] = []

    with zipfile.ZipFile(zip_path) as zf:
        entradas = [e for e in zf.infolist() if not e.is_dir()]
        total = len(entradas)
        logger.info("Archivos dentro del ZIP: %d\n", total)

        for i, entrada in enumerate(entradas, start=1):
            nombre = _nombre_base(entrada.filename)
            if not nombre:
                continue

            carpeta = clasificar(nombre)
            destino_dir = raiz / carpeta
            destino_file = destino_dir / nombre

            estado = "COPIADO"
            if destino_file.exists() and not sobrescribir:
                estado = "YA_EXISTIA"
            elif dry_run:
                estado = "SIMULADO"
            else:
                # Extraer los bytes de esta entrada al archivo destino.
                with zf.open(entrada) as origen, open(destino_file, "wb") as salida:
                    salida.write(origen.read())

            if carpeta == CARPETA_SIN_CLASIFICAR:
                logger.warning("  [%d/%d] SIN CLASIFICAR: %s", i, total, nombre)

            filas.append(
                {
                    "archivo": nombre,
                    "carpeta": carpeta,
                    "estado": estado,
                    "destino": str(destino_file),
                }
            )

    return filas


def resumen(filas: list[dict]) -> dict[str, int]:
    conteo: dict[str, int] = {}
    for f in filas:
        conteo[f["carpeta"]] = conteo.get(f["carpeta"], 0) + 1
    return conteo


def escribir_reporte(filas: list[dict], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=["archivo", "carpeta", "estado", "destino"])
        writer.writeheader()
        writer.writerows(filas)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extrae un ZIP de COOSALUD y reparte los Excel en DETALLES / FACTURAS / GLOSAS.",
    )
    p.add_argument("--zip", required=True, help="Ruta al archivo .zip a procesar.")
    p.add_argument(
        "--destino",
        default=DESTINO_DEFECTO,
        help=f"Carpeta base (Escritorio) donde crear la carpeta. Def: {DESTINO_DEFECTO}",
    )
    p.add_argument(
        "--nombre",
        default=NOMBRE_DEFECTO,
        help=f'Nombre de la carpeta que se crea. Def: "{NOMBRE_DEFECTO}"',
    )
    p.add_argument(
        "--reporte",
        default=None,
        help="Ruta opcional para guardar un CSV con lo que se hizo por archivo.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Ensayo: muestra qué haría sin escribir nada en disco.",
    )
    p.add_argument(
        "--sobrescribir",
        action="store_true",
        help="Reemplaza los archivos que ya existan en el destino.",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Log detallado.")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    setup_logging(args.verbose)

    try:
        filas = organizar_zip(
            Path(args.zip),
            Path(args.destino),
            args.nombre,
            dry_run=args.dry_run,
            sobrescribir=args.sobrescribir,
        )
    except (FileNotFoundError, ValueError) as exc:
        logger.error("ERROR: %s", exc)
        return 1

    conteo = resumen(filas)
    logger.info("\n===== RESUMEN =====")
    for carpeta in [
        CARPETA_DETALLES,
        CARPETA_FACTURAS,
        CARPETA_GLOSAS,
        CARPETA_SIN_CLASIFICAR,
    ]:
        n = conteo.get(carpeta, 0)
        if n or carpeta != CARPETA_SIN_CLASIFICAR:
            logger.info("  %-16s %d", carpeta + ":", n)
    ya = sum(1 for f in filas if f["estado"] == "YA_EXISTIA")
    if ya:
        logger.info("  (ya existían, no se tocaron: %d)", ya)
    logger.info("  TOTAL:           %d", len(filas))

    sin = conteo.get(CARPETA_SIN_CLASIFICAR, 0)
    if sin:
        logger.warning(
            "\nOJO: %d archivo(s) no coincidieron con DETALLE/GLOSAS/HUS. "
            "Quedaron en la carpeta %s para revisión.",
            sin,
            CARPETA_SIN_CLASIFICAR,
        )

    if args.reporte:
        escribir_reporte(filas, Path(args.reporte))
        logger.info("\nReporte CSV: %s", args.reporte)

    logger.info(
        "\nListo. %s", "(ensayo, no se escribió nada)" if args.dry_run else "Carpetas creadas."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
