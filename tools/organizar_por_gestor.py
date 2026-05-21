"""organizar_por_gestor.py — Mueve carpetas <NOTA>/ a <GESTOR>/<NOTA>/.

Lee un Excel/TSV/CSV con columnas `GESTOR` y `NOTA CREDITO`, y dentro de
--destino reorganiza así:

    <destino>/<NOTA>/...   →   <destino>/<GESTOR>/<NOTA>/...

Si una nota no tiene gestor asignado (`#N/D`, vacío, etc.) o no está en el
listado, la carpeta queda intacta y se reporta para revisión.

Carpetas que ya estén dentro de un nombre de gestor existente NO se vuelven
a mover (idempotente).

USO RÁPIDO
----------

    # Dry-run
    py organizar_por_gestor.py ^
        --tsv notas_credito_gestores.tsv ^
        --destino "C:\\notas-extraidas\\documentos" ^
        --dry-run

    # Ejecutar
    py organizar_por_gestor.py ^
        --tsv notas_credito_gestores.tsv ^
        --destino "C:\\notas-extraidas\\documentos" ^
        --reporte "C:\\notas-extraidas\\reporte_gestor.csv"
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
import sys
from pathlib import Path

# Reutilizar los lectores
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extraer_notas_credito import leer_notas_delimitado, leer_notas_excel  # noqa: E402

logger = logging.getLogger("organizar_gestor")

VALORES_NULOS = {"", "#N/D", "#N/A", "N/D", "NA", "NULL", "NONE", "-"}
RE_INVALIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def sanitizar_gestor(g: str) -> str:
    s = (g or "").strip().upper()
    s = RE_INVALIDOS.sub("_", s)
    return s


def es_nulo(valor: str) -> bool:
    return (valor or "").strip().upper() in VALORES_NULOS


def cargar_mapeo(args: argparse.Namespace) -> dict[str, str]:
    """Devuelve {nota_str: gestor_normalizado}."""
    if args.excel:
        filas = leer_notas_excel(args.excel)
    elif args.csv:
        filas = leer_notas_delimitado(args.csv, sep=",")
    else:
        filas = leer_notas_delimitado(args.tsv, sep="\t")

    mapeo: dict[str, str] = {}
    duplicados_gestor_distinto = 0
    for f in filas:
        nota = (f.get("nota") or "").strip()
        gestor_raw = (f.get("GESTOR") or "").strip()
        if not nota or es_nulo(nota):
            continue
        gestor = "" if es_nulo(gestor_raw) else sanitizar_gestor(gestor_raw)
        if nota in mapeo and mapeo[nota] != gestor:
            duplicados_gestor_distinto += 1
            logger.warning(
                f"Nota {nota} aparece con dos gestores: '{mapeo[nota]}' y '{gestor}' "
                f"(me quedo con el primero)"
            )
            continue
        mapeo.setdefault(nota, gestor)
    if duplicados_gestor_distinto:
        logger.warning(
            f"{duplicados_gestor_distinto} duplicados con gestor distinto fueron ignorados"
        )
    return mapeo


def organizar(base: Path, mapeo: dict[str, str], dry_run: bool) -> list[dict]:
    gestores_validos = {g for g in mapeo.values() if g}
    resultados: list[dict] = []

    items = sorted(base.iterdir())
    for sub in items:
        if not sub.is_dir():
            continue
        # Saltar carpetas "especiales" (papelera, limbo, etc.) y carpetas que YA sean gestores
        if sub.name.startswith("_"):
            continue
        if sub.name.upper() in gestores_validos:
            # Es ya una carpeta de gestor (con subcarpetas dentro). No se toca.
            continue

        registro = {
            "carpeta": sub.name,
            "ruta_actual": str(sub),
            "gestor": "",
            "destino": "",
            "estado": "",
            "detalle": "",
        }

        if sub.name not in mapeo:
            registro["estado"] = "NO_EN_LISTADO"
            registro["detalle"] = "La carpeta no aparece en el listado de gestores"
            logger.warning(f"{sub.name}: NO_EN_LISTADO")
            resultados.append(registro)
            continue

        gestor = mapeo[sub.name]
        if not gestor:
            registro["estado"] = "SIN_GESTOR"
            registro["detalle"] = "El listado tiene la nota pero el gestor está vacío/#N/D"
            logger.warning(f"{sub.name}: SIN_GESTOR")
            resultados.append(registro)
            continue

        registro["gestor"] = gestor
        carpeta_gestor = base / gestor
        destino_final = carpeta_gestor / sub.name
        registro["destino"] = str(destino_final)

        if destino_final.exists():
            registro["estado"] = "YA_EN_DESTINO"
            registro["detalle"] = "Ya existe la carpeta en el destino"
            logger.info(f"{sub.name}: YA_EN_DESTINO ({gestor}/)")
            resultados.append(registro)
            continue

        if dry_run:
            registro["estado"] = "DRY_RUN"
            registro["detalle"] = f"mover a {gestor}/{sub.name}/"
            logger.info(f"{sub.name}: DRY_RUN → {gestor}/")
            resultados.append(registro)
            continue

        try:
            carpeta_gestor.mkdir(parents=True, exist_ok=True)
            shutil.move(str(sub), str(destino_final))
            registro["estado"] = "MOVIDA"
            registro["detalle"] = f"a {gestor}/{sub.name}/"
            logger.info(f"{sub.name}: MOVIDA → {gestor}/")
        except OSError as e:
            registro["estado"] = "ERROR"
            registro["detalle"] = f"{type(e).__name__}: {e}"
            logger.error(f"{sub.name}: ERROR — {e}")

        resultados.append(registro)

    return resultados


def escribir_reporte(resultados: list[dict], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    campos = ["carpeta", "ruta_actual", "gestor", "destino", "estado", "detalle"]
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
    grupo_input.add_argument("--excel", type=Path, help="Excel con GESTOR + NOTA CREDITO")
    grupo_input.add_argument("--csv", type=Path, help="CSV (separador coma)")
    grupo_input.add_argument("--tsv", type=Path, help="TSV (separador tab)")

    parser.add_argument(
        "--destino",
        type=Path,
        required=True,
        help="Carpeta base con subcarpetas por nota",
    )
    parser.add_argument(
        "--reporte",
        type=Path,
        default=Path("reporte_gestor.csv"),
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

    mapeo = cargar_mapeo(args)
    if not mapeo:
        logger.error("El listado no devolvió ninguna nota válida.")
        return 1
    con_gestor = sum(1 for g in mapeo.values() if g)
    sin_gestor = len(mapeo) - con_gestor
    logger.info(f"Listado: {len(mapeo)} notas ({con_gestor} con gestor, {sin_gestor} sin gestor)")
    logger.info(f"Destino: {args.destino}")

    resultados = organizar(args.destino, mapeo, args.dry_run)
    escribir_reporte(resultados, args.reporte)

    resumen: dict[str, int] = {}
    por_gestor: dict[str, int] = {}
    for r in resultados:
        resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1
        if r["estado"] in ("MOVIDA", "DRY_RUN", "YA_EN_DESTINO") and r["gestor"]:
            por_gestor[r["gestor"]] = por_gestor.get(r["gestor"], 0) + 1

    logger.info("=" * 60)
    logger.info("RESUMEN")
    logger.info(f"  Carpetas evaluadas: {len(resultados)}")
    for k, n in sorted(resumen.items(), key=lambda kv: -kv[1]):
        logger.info(f"    {k}: {n}")
    if por_gestor:
        logger.info("  Por gestor:")
        for g, n in sorted(por_gestor.items()):
            logger.info(f"    {g}: {n}")
    logger.info(f"  Reporte: {args.reporte}")

    problemas = sum(n for k, n in resumen.items() if k == "ERROR")
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
