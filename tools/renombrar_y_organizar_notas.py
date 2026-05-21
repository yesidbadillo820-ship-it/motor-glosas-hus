"""renombrar_y_organizar_notas.py — Renombra PDFs de notas crédito y los mete en su carpeta.

Lee todos los PDFs de una carpeta de origen, extrae de cada uno:
  - Nota Electrónica del PDF (ej. 309352)  ← coincide con NOTA CREDITO del Excel
  - NOTA Credito N° del PDF (ej. 251233)   ← ID interno del CRRP, solo informativo
  - Factura HUS (ej. HUS0000466879)

Renombra cada PDF como:  NC_<NotaElectronica>_<Factura>.pdf
Y lo copia (o mueve) a:  <destino>\\<NotaElectronica>\\

IMPORTANTE: por defecto NO crea carpetas nuevas. Si la carpeta destino no
existe, el PDF se salta y se reporta como CARPETA_INEXISTENTE. Esto evita
generar carpetas paralelas cuando hay un mismatch entre el PDF y el Excel
original. Si querés crearlas igual, pasá --crear-carpetas.

USO RÁPIDO
----------

    py renombrar_y_organizar_notas.py ^
        --origen "D:\\USUARIO CARTERA\\Desktop\\Nueva carpeta (2)" ^
        --destino "C:\\notas-extraidas\\documentos" ^
        --reporte "C:\\notas-extraidas\\reporte_renombrado.csv"

    # Mover en lugar de copiar (los PDFs originales se eliminan)
    py renombrar_y_organizar_notas.py --origen ... --destino ... --mover

    # Crear carpetas nuevas cuando no existan (NO recomendado salvo casos puntuales)
    py renombrar_y_organizar_notas.py --origen ... --destino ... --crear-carpetas

    # Dry-run: solo reporta qué haría, sin tocar archivos
    py renombrar_y_organizar_notas.py --origen ... --destino ... --dry-run

DEPENDENCIAS
------------

- Python 3.9+
- pdfplumber (recomendado) o pypdf como fallback:
    py -m pip install pdfplumber
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("renombrar_notas")


# ─── Backend PDF ───────────────────────────────────────────────────────────

_BACKEND = None


def _cargar_backend() -> str:
    global _BACKEND
    if _BACKEND is not None:
        return _BACKEND
    try:
        import pdfplumber  # noqa: F401

        _BACKEND = "pdfplumber"
        return _BACKEND
    except ImportError:
        pass
    try:
        from pypdf import PdfReader  # noqa: F401

        _BACKEND = "pypdf"
        return _BACKEND
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader  # noqa: F401

        _BACKEND = "pypdf2"
        return _BACKEND
    except ImportError:
        pass
    sys.stderr.write(
        "ERROR: necesitás pdfplumber, pypdf o PyPDF2.\nInstalá con: py -m pip install pdfplumber\n"
    )
    sys.exit(2)


def extraer_texto_pdf(ruta: Path) -> str:
    backend = _cargar_backend()
    if backend == "pdfplumber":
        import pdfplumber

        with pdfplumber.open(str(ruta)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    if backend == "pypdf":
        from pypdf import PdfReader

        reader = PdfReader(str(ruta))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    if backend == "pypdf2":
        from PyPDF2 import PdfReader

        reader = PdfReader(str(ruta))
        return "\n".join((p.extract_text() or "") for p in reader.pages)
    return ""


# ─── Extracción de campos ──────────────────────────────────────────────────

RE_NOTA_ELECTRONICA = re.compile(r"Nota\s+Electr[oó]nica\s*[:.]?\s*(\d{4,})", re.IGNORECASE)
RE_NOTA_CREDITO = re.compile(r"NOTA\s+Cr[eé]dito\s+N[^\d\n]{0,5}(\d{4,})", re.IGNORECASE)
RE_FACTURA = re.compile(r"\b(HUS\d{6,12})\b")
# Sanitizador para nombres de archivo en Windows
RE_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def extraer_datos(texto: str) -> dict:
    datos = {"nota_electronica": "", "nota_credito": "", "factura": "", "facturas_todas": []}

    m = RE_NOTA_ELECTRONICA.search(texto)
    if m:
        datos["nota_electronica"] = m.group(1).strip()

    m = RE_NOTA_CREDITO.search(texto)
    if m:
        datos["nota_credito"] = m.group(1).strip()

    facturas = list(dict.fromkeys(RE_FACTURA.findall(texto)))
    if facturas:
        datos["factura"] = facturas[0]
        datos["facturas_todas"] = facturas

    return datos


def sanitizar(nombre: str) -> str:
    return RE_INVALIDOS.sub("_", nombre).strip()


def nombre_destino(datos: dict) -> str | None:
    ne = datos["nota_electronica"]
    fac = datos["factura"]
    if not ne or not fac:
        return None
    return sanitizar(f"NC_{ne}_{fac}.pdf")


# ─── Procesamiento ─────────────────────────────────────────────────────────


def procesar_pdf(
    pdf: Path,
    destino_base: Path,
    mover: bool,
    crear_carpetas: bool,
    dry_run: bool,
) -> dict:
    resultado = {
        "archivo_origen": str(pdf),
        "nota_electronica": "",
        "nota_credito": "",
        "factura": "",
        "facturas_todas": "",
        "nuevo_nombre": "",
        "destino_final": "",
        "estado": "",
        "detalle": "",
    }

    try:
        texto = extraer_texto_pdf(pdf)
    except Exception as e:
        resultado["estado"] = "ERROR_LECTURA"
        resultado["detalle"] = f"{type(e).__name__}: {e}"
        logger.error(f"{pdf.name}: ERROR_LECTURA — {e}")
        return resultado

    if not texto.strip():
        resultado["estado"] = "PDF_VACIO_O_ESCANEADO"
        resultado["detalle"] = "El PDF no devolvió texto extraíble"
        logger.warning(f"{pdf.name}: PDF_VACIO_O_ESCANEADO")
        return resultado

    datos = extraer_datos(texto)
    resultado["nota_electronica"] = datos["nota_electronica"]
    resultado["nota_credito"] = datos["nota_credito"]
    resultado["factura"] = datos["factura"]
    resultado["facturas_todas"] = ";".join(datos["facturas_todas"])

    faltantes = []
    if not datos["nota_electronica"]:
        faltantes.append("Nota Electrónica")
    if not datos["factura"]:
        faltantes.append("Factura HUS")
    if faltantes:
        resultado["estado"] = "DATOS_INCOMPLETOS"
        resultado["detalle"] = "Faltan: " + ", ".join(faltantes)
        logger.warning(f"{pdf.name}: DATOS_INCOMPLETOS — faltan {faltantes}")
        return resultado

    nuevo = nombre_destino(datos)
    resultado["nuevo_nombre"] = nuevo

    # La "Nota Electrónica" del PDF es el número que coincide con la columna
    # NOTA CREDITO del Excel original — por eso es el nombre de la carpeta destino.
    # El "NOTA Credito N°" del PDF es un ID interno del sistema CRRP, no se usa.
    carpeta_destino = destino_base / sanitizar(datos["nota_electronica"])
    destino_final = carpeta_destino / nuevo
    resultado["destino_final"] = str(destino_final)

    if not carpeta_destino.exists():
        if not crear_carpetas:
            resultado["estado"] = "CARPETA_INEXISTENTE"
            resultado["detalle"] = (
                f"No existe {carpeta_destino} (pasá --crear-carpetas si querés crearla)"
            )
            logger.warning(f"{pdf.name}: CARPETA_INEXISTENTE — {carpeta_destino.name}")
            return resultado
        if not dry_run:
            carpeta_destino.mkdir(parents=True, exist_ok=True)
        logger.info(f"  + carpeta creada: {carpeta_destino}")

    if destino_final.exists():
        try:
            if destino_final.stat().st_size == pdf.stat().st_size:
                resultado["estado"] = "YA_EXISTE"
                resultado["detalle"] = "Destino ya tiene un PDF idéntico"
                logger.info(f"{pdf.name}: YA_EXISTE — omitido")
                return resultado
        except OSError:
            pass

    if dry_run:
        resultado["estado"] = "DRY_RUN"
        resultado["detalle"] = f"{'mover' if mover else 'copiar'} → {destino_final}"
        logger.info(f"{pdf.name}: DRY_RUN → {destino_final.relative_to(destino_base.parent)}")
        return resultado

    try:
        if mover:
            shutil.move(str(pdf), str(destino_final))
        else:
            shutil.copy2(str(pdf), str(destino_final))
        resultado["estado"] = "OK"
        resultado["detalle"] = f"{'movido' if mover else 'copiado'}"
        logger.info(f"{pdf.name}: OK → {destino_final.relative_to(destino_base.parent)}")
    except OSError as e:
        resultado["estado"] = "ERROR_COPIA"
        resultado["detalle"] = f"{type(e).__name__}: {e}"
        logger.error(f"{pdf.name}: ERROR_COPIA — {e}")

    return resultado


def setup_logging(log_file: Path | None = None) -> None:
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers)


def escribir_reporte(resultados: list[dict], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    campos = [
        "archivo_origen",
        "nota_electronica",
        "nota_credito",
        "factura",
        "facturas_todas",
        "nuevo_nombre",
        "destino_final",
        "estado",
        "detalle",
    ]
    with ruta.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=campos)
        writer.writeheader()
        for r in resultados:
            writer.writerow({k: r.get(k, "") for k in campos})
    logger.info(f"Reporte guardado en: {ruta}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--origen", type=Path, required=True, help="Carpeta con los PDFs a renombrar"
    )
    parser.add_argument(
        "--destino",
        type=Path,
        required=True,
        help="Carpeta base donde están las subcarpetas por nota crédito",
    )
    parser.add_argument(
        "--reporte",
        type=Path,
        default=Path("reporte_renombrado.csv"),
        help="CSV con el resultado de cada PDF",
    )
    parser.add_argument(
        "--mover",
        action="store_true",
        help="Mover los PDFs (los elimina del origen). Por defecto copia.",
    )
    parser.add_argument(
        "--crear-carpetas",
        action="store_true",
        help=(
            "Crear la carpeta destino si no existe. Por defecto se salta el PDF y "
            "se reporta CARPETA_INEXISTENTE."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No toca archivos; solo reporta qué haría.",
    )
    parser.add_argument("--log", type=Path, default=None, help="Archivo de log opcional")
    args = parser.parse_args()

    setup_logging(args.log)
    _cargar_backend()
    logger.info(f"Backend PDF: {_BACKEND}")

    if not args.origen.is_dir():
        logger.error(f"--origen no existe o no es carpeta: {args.origen}")
        return 1
    if not args.destino.exists():
        logger.error(f"--destino no existe: {args.destino}")
        return 1

    pdfs = sorted(p for p in args.origen.iterdir() if p.is_file() and p.suffix.lower() == ".pdf")
    if not pdfs:
        logger.error(f"No hay PDFs en {args.origen}")
        return 1
    logger.info(f"Encontrados {len(pdfs)} PDFs en {args.origen}")
    logger.info(f"Destino base: {args.destino}")
    logger.info(
        f"Modo: {'MOVER' if args.mover else 'COPIAR'}"
        f"{' (DRY-RUN, sin tocar archivos)' if args.dry_run else ''}"
    )

    resultados = []
    for i, pdf in enumerate(pdfs, start=1):
        logger.info(f"[{i}/{len(pdfs)}] {pdf.name}")
        resultados.append(
            procesar_pdf(
                pdf,
                args.destino,
                mover=args.mover,
                crear_carpetas=args.crear_carpetas,
                dry_run=args.dry_run,
            )
        )

    escribir_reporte(resultados, args.reporte)

    resumen: dict[str, int] = {}
    for r in resultados:
        resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1

    logger.info("=" * 60)
    logger.info("RESUMEN")
    logger.info(f"  Total PDFs: {len(resultados)}")
    for estado, n in sorted(resumen.items(), key=lambda kv: -kv[1]):
        logger.info(f"    {estado}: {n}")
    logger.info(f"  Reporte: {args.reporte}")

    problemas = sum(n for k, n in resumen.items() if k not in ("OK", "YA_EXISTE", "DRY_RUN"))
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
