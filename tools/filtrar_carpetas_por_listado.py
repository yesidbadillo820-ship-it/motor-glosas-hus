"""filtrar_carpetas_por_listado.py — Aparta carpetas no autorizadas a `_no_en_listado/`.

Lee un Excel/TSV/CSV con la columna `NOTA CREDITO` y, dentro de --destino,
mueve a `<destino>/_no_en_listado/` cualquier subcarpeta cuyo nombre NO esté
en esa lista. Las carpetas válidas se dejan intactas.

Es seguro y reversible: nada se borra; el contenido apartado queda en una
subcarpeta `_no_en_listado/` que vos podés revisar y borrar manualmente.

USO RÁPIDO
----------

    # Dry-run: ver qué carpetas se moverían
    py filtrar_carpetas_por_listado.py ^
        --tsv notas_credito_ejemplo.tsv ^
        --destino "C:\\notas-extraidas\\documentos" ^
        --dry-run

    # Ejecutar
    py filtrar_carpetas_por_listado.py ^
        --excel "C:\\ruta\\al\\excel.xlsx" ^
        --destino "C:\\notas-extraidas\\documentos" ^
        --reporte "C:\\notas-extraidas\\reporte_filtrar.csv"
"""

from __future__ import annotations

import argparse
import csv
import logging
import shutil
import sys
from pathlib import Path

# Reutilizar los lectores de extraer_notas_credito.py
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extraer_notas_credito import leer_notas_delimitado, leer_notas_excel  # noqa: E402

logger = logging.getLogger("filtrar_carpetas")

LIMBO_DIRNAME = "_no_en_listado"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def cargar_listado_valido(args: argparse.Namespace) -> set[str]:
    if args.excel:
        notas = leer_notas_excel(args.excel)
    elif args.csv:
        notas = leer_notas_delimitado(args.csv, sep=",")
    else:
        notas = leer_notas_delimitado(args.tsv, sep="\t")
    return {n["nota"] for n in notas if n.get("nota")}


def contar_archivos(carpeta: Path) -> int:
    try:
        return sum(1 for p in carpeta.rglob("*") if p.is_file())
    except OSError:
        return 0


def filtrar(base: Path, validas: set[str], dry_run: bool) -> list[dict]:
    limbo_dir = base / LIMBO_DIRNAME
    resultados: list[dict] = []

    for sub in sorted(base.iterdir()):
        if not sub.is_dir() or sub.name == LIMBO_DIRNAME:
            continue
        registro = {
            "carpeta": sub.name,
            "ruta_actual": str(sub),
            "archivos_dentro": contar_archivos(sub),
            "estado": "",
            "destino": "",
            "detalle": "",
        }

        if sub.name in validas:
            registro["estado"] = "VALIDA"
            resultados.append(registro)
            continue

        destino = limbo_dir / sub.name
        registro["destino"] = str(destino)

        if destino.exists():
            registro["estado"] = "CONFLICTO"
            registro["detalle"] = f"Ya existe {destino}; no movida"
            logger.warning(f"{sub.name}: CONFLICTO — destino ya existe")
            resultados.append(registro)
            continue

        if dry_run:
            registro["estado"] = "DRY_RUN"
            registro["detalle"] = f"mover a {LIMBO_DIRNAME}/"
            logger.info(
                f"{sub.name}: DRY_RUN → {LIMBO_DIRNAME}/ ({registro['archivos_dentro']} archivos)"
            )
            resultados.append(registro)
            continue

        try:
            limbo_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(sub), str(destino))
            registro["estado"] = "MOVIDA"
            registro["detalle"] = f"a {LIMBO_DIRNAME}/{sub.name}/"
            logger.info(
                f"{sub.name}: MOVIDA → {LIMBO_DIRNAME}/ ({registro['archivos_dentro']} archivos)"
            )
        except OSError as e:
            registro["estado"] = "ERROR"
            registro["detalle"] = f"{type(e).__name__}: {e}"
            logger.error(f"{sub.name}: ERROR — {e}")

        resultados.append(registro)

    return resultados


def escribir_reporte(resultados: list[dict], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    campos = ["carpeta", "ruta_actual", "archivos_dentro", "estado", "destino", "detalle"]
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
    grupo_input = parser.add_mutually_exclusive_group(required=True)
    grupo_input.add_argument("--excel", type=Path, help="Excel con la columna NOTA CREDITO")
    grupo_input.add_argument("--csv", type=Path, help="CSV (separador coma)")
    grupo_input.add_argument("--tsv", type=Path, help="TSV (separador tab)")

    parser.add_argument(
        "--destino",
        type=Path,
        required=True,
        help="Carpeta base con subcarpetas por nota crédito",
    )
    parser.add_argument(
        "--reporte",
        type=Path,
        default=Path("reporte_filtrar.csv"),
        help="CSV con el detalle por carpeta",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No toca archivos; solo reporta",
    )
    args = parser.parse_args()

    setup_logging()

    if not args.destino.is_dir():
        logger.error(f"--destino no existe o no es carpeta: {args.destino}")
        return 1

    validas = cargar_listado_valido(args)
    if not validas:
        logger.error("La lista de notas válidas está vacía. Revisá el input.")
        return 1
    logger.info(f"Listado válido: {len(validas)} notas")
    logger.info(f"Destino: {args.destino}")

    resultados = filtrar(args.destino, validas, args.dry_run)
    escribir_reporte(resultados, args.reporte)

    resumen: dict[str, int] = {}
    total_archivos_apartados = 0
    for r in resultados:
        resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1
        if r["estado"] in ("MOVIDA", "DRY_RUN"):
            total_archivos_apartados += r.get("archivos_dentro", 0)

    logger.info("=" * 60)
    logger.info("RESUMEN")
    logger.info(f"  Carpetas analizadas: {len(resultados)}")
    for k, n in sorted(resumen.items(), key=lambda kv: -kv[1]):
        logger.info(f"    {k}: {n}")
    if total_archivos_apartados:
        accion = "se moverían" if args.dry_run else "movidos"
        logger.info(f"  Archivos {accion}: {total_archivos_apartados}")
    logger.info(f"  Reporte: {args.reporte}")

    problemas = sum(n for k, n in resumen.items() if k in ("CONFLICTO", "ERROR"))
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
