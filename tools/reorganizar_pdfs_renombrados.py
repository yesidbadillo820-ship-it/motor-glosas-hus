"""reorganizar_pdfs_renombrados.py — Mueve PDFs NC_<NE>_HUS<num>.pdf a la carpeta <NE>.

Útil cuando una corrida previa de renombrar_y_organizar_notas.py los dejó en
carpetas con otro nombre (ej. la "NOTA Credito N°" interna del PDF en vez de
la "Nota Electrónica"). Recorre el árbol de --destino, encuentra todos los
PDFs cuyo nombre matchee el patrón `NC_<NotaElectronica>_HUS<num>.pdf` y,
si están en una carpeta cuyo nombre NO coincide con <NotaElectronica>, los
MUEVE a `<destino>/<NotaElectronica>/`.

Después, opcionalmente, elimina carpetas que queden vacías (--limpiar-vacias).

USO RÁPIDO
----------

    # Ver qué movería sin tocar nada
    py reorganizar_pdfs_renombrados.py ^
        --destino "C:\\notas-extraidas\\documentos" ^
        --dry-run

    # Ejecutar el movimiento + borrar carpetas vacías sobrantes
    py reorganizar_pdfs_renombrados.py ^
        --destino "C:\\notas-extraidas\\documentos" ^
        --limpiar-vacias

    # Si querés crear la carpeta <NE> cuando no exista, agregale --crear-carpetas
    # (por defecto, si <NE> no existe, el PDF se queda donde está y se reporta).
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("reorganizar_pdfs")

RE_NOMBRE = re.compile(r"^NC_(\d{4,})_(HUS\d{6,12})\.pdf$", re.IGNORECASE)


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def buscar_pdfs(base: Path) -> list[tuple[Path, str, str]]:
    """Devuelve [(ruta_pdf, nota_electronica, factura), ...]."""
    resultados = []
    for pdf in base.rglob("NC_*_HUS*.pdf"):
        if not pdf.is_file():
            continue
        m = RE_NOMBRE.match(pdf.name)
        if not m:
            continue
        resultados.append((pdf, m.group(1), m.group(2)))
    return resultados


def reorganizar(
    base: Path,
    crear_carpetas: bool,
    dry_run: bool,
) -> list[dict]:
    pdfs = buscar_pdfs(base)
    logger.info(f"Encontrados {len(pdfs)} PDFs con patrón NC_<NE>_HUS<num>.pdf bajo {base}")

    resultados = []
    for ruta, nota_elec, factura in pdfs:
        carpeta_actual = ruta.parent
        destino_carpeta = base / nota_elec
        destino_final = destino_carpeta / ruta.name
        registro = {
            "pdf_actual": str(ruta),
            "carpeta_actual": carpeta_actual.name,
            "nota_electronica": nota_elec,
            "factura": factura,
            "destino_esperado": str(destino_final),
            "estado": "",
            "detalle": "",
        }

        if carpeta_actual.name == nota_elec:
            registro["estado"] = "YA_OK"
            registro["detalle"] = "Ya está en la carpeta correcta"
            resultados.append(registro)
            continue

        if not destino_carpeta.exists():
            if not crear_carpetas:
                registro["estado"] = "DESTINO_INEXISTENTE"
                registro["detalle"] = (
                    f"No existe {destino_carpeta} (pasá --crear-carpetas si querés crearla)"
                )
                logger.warning(f"{ruta.name}: destino {nota_elec}/ no existe — no movido")
                resultados.append(registro)
                continue
            if not dry_run:
                destino_carpeta.mkdir(parents=True, exist_ok=True)
            logger.info(f"  + creada {destino_carpeta}")

        if destino_final.exists():
            try:
                if destino_final.stat().st_size == ruta.stat().st_size:
                    registro["estado"] = "DUPLICADO"
                    registro["detalle"] = "Destino ya tiene un PDF idéntico"
                    if not dry_run:
                        ruta.unlink()
                        registro["detalle"] += "; origen eliminado"
                    logger.info(
                        f"{ruta.name}: DUPLICADO — eliminado origen en {carpeta_actual.name}/"
                    )
                    resultados.append(registro)
                    continue
            except OSError:
                pass
            registro["estado"] = "CONFLICTO"
            registro["detalle"] = "Destino existe con tamaño distinto; no movido"
            logger.warning(f"{ruta.name}: CONFLICTO en {destino_carpeta.name}/")
            resultados.append(registro)
            continue

        if dry_run:
            registro["estado"] = "DRY_RUN"
            registro["detalle"] = f"mover de {carpeta_actual.name}/ a {nota_elec}/"
            logger.info(f"{ruta.name}: DRY_RUN — {carpeta_actual.name}/ → {nota_elec}/")
            resultados.append(registro)
            continue

        try:
            shutil.move(str(ruta), str(destino_final))
            registro["estado"] = "MOVIDO"
            registro["detalle"] = f"de {carpeta_actual.name}/ a {nota_elec}/"
            logger.info(f"{ruta.name}: MOVIDO — {carpeta_actual.name}/ → {nota_elec}/")
        except OSError as e:
            registro["estado"] = "ERROR"
            registro["detalle"] = f"{type(e).__name__}: {e}"
            logger.error(f"{ruta.name}: ERROR — {e}")

        resultados.append(registro)

    return resultados


def limpiar_carpetas_vacias(base: Path, dry_run: bool) -> int:
    """Elimina subcarpetas vacías directas de base. Devuelve cuántas borró."""
    eliminadas = 0
    for sub in sorted(base.iterdir()):
        if not sub.is_dir():
            continue
        try:
            contenido = list(sub.iterdir())
        except OSError as e:
            logger.warning(f"No pude listar {sub}: {e}")
            continue
        if contenido:
            continue
        if dry_run:
            logger.info(f"DRY_RUN: borraría carpeta vacía {sub.name}/")
        else:
            try:
                sub.rmdir()
                logger.info(f"Borrada carpeta vacía: {sub.name}/")
                eliminadas += 1
            except OSError as e:
                logger.warning(f"No pude borrar {sub}: {e}")
    return eliminadas


def escribir_reporte(resultados: list[dict], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    campos = [
        "pdf_actual",
        "carpeta_actual",
        "nota_electronica",
        "factura",
        "destino_esperado",
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
        "--destino",
        type=Path,
        required=True,
        help="Carpeta base donde están las subcarpetas por nota crédito",
    )
    parser.add_argument(
        "--reporte",
        type=Path,
        default=Path("reporte_reorganizar.csv"),
        help="CSV con el detalle por PDF",
    )
    parser.add_argument(
        "--crear-carpetas",
        action="store_true",
        help="Crear la carpeta destino si no existe (default: saltar PDF)",
    )
    parser.add_argument(
        "--limpiar-vacias",
        action="store_true",
        help="Después de mover, borrar carpetas que queden vacías",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No toca archivos; solo reporta qué haría",
    )
    args = parser.parse_args()

    setup_logging()

    if not args.destino.is_dir():
        logger.error(f"--destino no existe o no es carpeta: {args.destino}")
        return 1

    resultados = reorganizar(args.destino, args.crear_carpetas, args.dry_run)
    escribir_reporte(resultados, args.reporte)

    resumen: dict[str, int] = {}
    for r in resultados:
        resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1

    logger.info("=" * 60)
    logger.info("RESUMEN MOVIMIENTOS")
    logger.info(f"  Total PDFs analizados: {len(resultados)}")
    for estado, n in sorted(resumen.items(), key=lambda kv: -kv[1]):
        logger.info(f"    {estado}: {n}")

    if args.limpiar_vacias:
        logger.info("-" * 60)
        logger.info("LIMPIEZA DE CARPETAS VACÍAS")
        eliminadas = limpiar_carpetas_vacias(args.destino, args.dry_run)
        logger.info(f"  Carpetas vacías eliminadas: {eliminadas}")

    logger.info(f"  Reporte: {args.reporte}")

    problemas = sum(n for k, n in resumen.items() if k in ("CONFLICTO", "ERROR"))
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
