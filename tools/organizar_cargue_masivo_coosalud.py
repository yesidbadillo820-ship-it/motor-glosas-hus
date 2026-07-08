"""organizar_cargue_masivo_coosalud.py — Extrae un ZIP de COOSALUD y organiza los Excel en lotes.

Toma el ZIP que descarga el equipo de cartera (con miles de archivos .xlsx sueltos)
y los reparte en tres carpetas según su nombre, y dentro de cada una las divide en
LOTES de máximo 300 archivos, porque el portal de cargue solo deja subir 300 a la vez:

    <ESCRITORIO>\\CARGUE MASIVO COOSALUD\\
        DETALLES\\
            LOTE 01\\   <- hasta 300 "DETALLE HUS######.xlsx"
            LOTE 02\\   <- los siguientes 300
            ...
        FACTURAS\\
            LOTE 01\\   <- hasta 300 "HUS######.xlsx"
            ...
        GLOSAS\\
            LOTE 01\\   <- hasta 300 "GLOSAS HUS######.xlsx"
            ...

Los lotes se arman ordenando por número de factura, así el LOTE 01 de FACTURAS,
DETALLES y GLOSAS corresponde al mismo grupo de facturas.

CLASIFICACIÓN (por el nombre del archivo, sin importar mayúsculas/espacios):
    empieza por "DETALLE"  -> DETALLES
    empieza por "GLOSA"    -> GLOSAS     (cubre GLOSA y GLOSAS)
    empieza por "HUS<núm>" -> FACTURAS   (la factura, sin prefijo)
    cualquier otra cosa    -> SIN_CLASIFICAR (se reporta, no se pierde nada)

Es IDEMPOTENTE: si lo corrés dos veces con el mismo ZIP, los archivos que ya
estén no se vuelven a escribir (salvo que uses --sobrescribir).

USO RÁPIDO
----------

    REM Lo normal: extraer el ZIP al Escritorio (D:\\USUARIO CARTERA\\Desktop)
    py organizar_cargue_masivo_coosalud.py --zip "C:\\...\\COOSALUD 1.zip"

    REM Ver qué haría, sin escribir nada (ensayo)
    py organizar_cargue_masivo_coosalud.py --zip "C:\\...\\COOSALUD 1.zip" --dry-run

    REM Cambiar el tamaño del lote (por defecto 300), destino, nombre o reporte CSV
    py organizar_cargue_masivo_coosalud.py ^
        --zip          "C:\\...\\COOSALUD 1.zip" ^
        --destino      "D:\\USUARIO CARTERA\\Desktop" ^
        --nombre       "CARGUE MASIVO COOSALUD" ^
        --max-por-lote 300 ^
        --reporte      "D:\\USUARIO CARTERA\\Desktop\\reporte_cargue.csv"

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

# Categorías que se dividen en lotes (SIN_CLASIFICAR queda plana, para revisión).
CATEGORIAS_LOTE = [CARPETA_DETALLES, CARPETA_FACTURAS, CARPETA_GLOSAS]

# Escritorio y nombre por defecto del equipo de cartera.
DESTINO_DEFECTO = r"D:\USUARIO CARTERA\Desktop"
NOMBRE_DEFECTO = "CARGUE MASIVO COOSALUD"

# El portal de cargue de COOSALUD solo deja subir 300 archivos por tanda.
MAX_POR_LOTE_DEFECTO = 300

# Un archivo de factura es "HUS" seguido de dígitos (sin prefijo DETALLE/GLOSAS).
RE_FACTURA = re.compile(r"^HUS\d+", re.IGNORECASE)
# Número de factura para ordenar (HUS + dígitos, ignorando ceros a la izquierda).
RE_NUM_FACTURA = re.compile(r"HUS0*(\d+)")


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


def _clave_orden(nombre: str) -> tuple[int, str]:
    """Ordena por número de factura (HUS######) para que los lotes se alineen."""
    m = RE_NUM_FACTURA.search(_normalizar(nombre))
    num = int(m.group(1)) if m else 10**18  # sin número -> al final
    return (num, _normalizar(nombre))


def _nombre_base(entrada: str) -> str:
    """Nombre del archivo aunque el ZIP traiga subcarpetas o rutas con \\ o /."""
    # Algunos ZIP de Windows usan backslash como separador interno.
    return entrada.replace("\\", "/").rstrip("/").split("/")[-1]


def _lote_nombre(indice: int, total_lotes: int) -> str:
    """Nombre de la subcarpeta de lote, con ceros para que ordene bien (LOTE 01)."""
    ancho = max(2, len(str(total_lotes)))
    return f"LOTE {indice:0{ancho}d}"


def organizar_zip(
    zip_path: Path,
    destino_base: Path,
    nombre_carpeta: str,
    *,
    max_por_lote: int = MAX_POR_LOTE_DEFECTO,
    dry_run: bool = False,
    sobrescribir: bool = False,
) -> list[dict]:
    """Extrae, clasifica y divide en lotes. Devuelve una lista de filas para el reporte."""
    if not zip_path.is_file():
        raise FileNotFoundError(f"No existe el ZIP: {zip_path}")
    if not zipfile.is_zipfile(zip_path):
        raise ValueError(f"El archivo no es un ZIP válido: {zip_path}")
    if max_por_lote < 1:
        raise ValueError("--max-por-lote debe ser 1 o más.")

    raiz = destino_base / nombre_carpeta
    logger.info("ZIP     : %s", zip_path)
    logger.info("Destino : %s", raiz)
    logger.info("Lote    : máximo %d archivos por carpeta", max_por_lote)
    if dry_run:
        logger.info("MODO ENSAYO (--dry-run): no se escribe nada en disco.")

    filas: list[dict] = []

    with zipfile.ZipFile(zip_path) as zf:
        entradas = [e for e in zf.infolist() if not e.is_dir()]
        total = len(entradas)
        logger.info("Archivos dentro del ZIP: %d\n", total)

        # 1) Clasificar todas las entradas por categoría.
        por_categoria: dict[str, list] = {}
        for entrada in entradas:
            nombre = _nombre_base(entrada.filename)
            if not nombre:
                continue
            categoria = clasificar(nombre)
            por_categoria.setdefault(categoria, []).append((nombre, entrada))

        # 2) Por cada categoría: ordenar, dividir en lotes y escribir.
        for categoria in CATEGORIAS_LOTE + [CARPETA_SIN_CLASIFICAR]:
            items = por_categoria.get(categoria, [])
            if not items:
                continue
            items.sort(key=lambda par: _clave_orden(par[0]))

            if categoria == CARPETA_SIN_CLASIFICAR:
                # No se lotea: queda plana para revisión manual.
                grupos = [(None, items)]
            else:
                total_lotes = (len(items) + max_por_lote - 1) // max_por_lote
                grupos = [
                    (
                        _lote_nombre(i + 1, total_lotes),
                        items[i * max_por_lote : (i + 1) * max_por_lote],
                    )
                    for i in range(total_lotes)
                ]

            for lote_nombre, grupo in grupos:
                destino_dir = raiz / categoria
                if lote_nombre:
                    destino_dir = destino_dir / lote_nombre
                if not dry_run:
                    destino_dir.mkdir(parents=True, exist_ok=True)

                for nombre, entrada in grupo:
                    destino_file = destino_dir / nombre
                    if destino_file.exists() and not sobrescribir:
                        estado = "YA_EXISTIA"
                    elif dry_run:
                        estado = "SIMULADO"
                    else:
                        with (
                            zf.open(entrada) as origen,
                            open(destino_file, "wb") as salida,
                        ):
                            salida.write(origen.read())
                        estado = "COPIADO"

                    if categoria == CARPETA_SIN_CLASIFICAR:
                        logger.warning("  SIN CLASIFICAR: %s", nombre)

                    filas.append(
                        {
                            "archivo": nombre,
                            "carpeta": categoria,
                            "lote": lote_nombre or "",
                            "estado": estado,
                            "destino": str(destino_file),
                        }
                    )

    return filas


def resumen(filas: list[dict]) -> dict[str, dict]:
    """Cuenta archivos y lotes por categoría."""
    conteo: dict[str, dict] = {}
    for f in filas:
        c = conteo.setdefault(f["carpeta"], {"archivos": 0, "lotes": set()})
        c["archivos"] += 1
        if f["lote"]:
            c["lotes"].add(f["lote"])
    return conteo


def escribir_reporte(filas: list[dict], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=["archivo", "carpeta", "lote", "estado", "destino"])
        writer.writeheader()
        writer.writerows(filas)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Extrae un ZIP de COOSALUD y reparte los Excel en DETALLES / FACTURAS / GLOSAS, en lotes de 300.",
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
        "--max-por-lote",
        type=int,
        default=MAX_POR_LOTE_DEFECTO,
        help=f"Máximo de archivos por lote. Def: {MAX_POR_LOTE_DEFECTO}",
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
            max_por_lote=args.max_por_lote,
            dry_run=args.dry_run,
            sobrescribir=args.sobrescribir,
        )
    except (FileNotFoundError, ValueError) as exc:
        logger.error("ERROR: %s", exc)
        return 1

    conteo = resumen(filas)
    logger.info("\n===== RESUMEN =====")
    for categoria in CATEGORIAS_LOTE:
        c = conteo.get(categoria)
        if not c:
            logger.info("  %-16s 0 archivos", categoria + ":")
            continue
        n_lotes = len(c["lotes"])
        logger.info(
            "  %-16s %d archivos en %d lote(s)",
            categoria + ":",
            c["archivos"],
            n_lotes,
        )
    ya = sum(1 for f in filas if f["estado"] == "YA_EXISTIA")
    if ya:
        logger.info("  (ya existían, no se tocaron: %d)", ya)
    logger.info("  TOTAL:           %d archivos", len(filas))

    sin = conteo.get(CARPETA_SIN_CLASIFICAR)
    if sin:
        logger.warning(
            "\nOJO: %d archivo(s) no coincidieron con DETALLE/GLOSAS/HUS. "
            "Quedaron en la carpeta %s para revisión.",
            sin["archivos"],
            CARPETA_SIN_CLASIFICAR,
        )

    if args.reporte:
        escribir_reporte(filas, Path(args.reporte))
        logger.info("\nReporte CSV: %s", args.reporte)

    logger.info(
        "\nListo. %s",
        "(ensayo, no se escribió nada)" if args.dry_run else "Carpetas y lotes creados.",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
