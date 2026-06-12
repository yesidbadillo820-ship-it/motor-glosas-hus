"""consolidar_carpetas_notas.py — Deja solo los 3 archivos finales por carpeta de nota.

Para cada subcarpeta de --destino (ej. 309414/), busca el PDF renombrado
NC_<NE>_HUS<num>.pdf, extrae <NE> y <factura>, y:

1. Renombra `ad*.xml` → `XML_<NE>_<factura>.xml`
2. Mueve `RIPS/ResultadosDoker_*.json` → `CUV_<NE>_<factura>.json` (en la carpeta padre)
3. Mueve TODO lo demás (resto de .xml/.pdf originales, .zip, RIPS/, etc.) a
   `<destino>/_papelera/<NE>/<archivo>`. NO se borra nada por defecto.

Si querés borrar definitivo en vez de mover a papelera, pasá `--borrar`.

GARANTÍA: si después de los pasos 1-2 no quedan los 3 archivos finales
(PDF + XML + JSON), la carpeta se marca como INCOMPLETO y NO se toca el
"resto" (no se mueve a papelera ni se borra). Así no se pierde nada por
un mismatch.

Estado final esperado por carpeta:
    NC_<NE>_HUS<num>.pdf
    XML_<NE>_HUS<num>.xml
    CUV_<NE>_HUS<num>.json

USO RÁPIDO
----------

    # Dry-run (no toca archivos, solo reporta)
    py consolidar_carpetas_notas.py ^
        --destino "C:\\notas-extraidas\\documentos" ^
        --dry-run

    # Ejecutar moviendo el resto a _papelera/ (default, reversible)
    py consolidar_carpetas_notas.py ^
        --destino "C:\\notas-extraidas\\documentos" ^
        --reporte "C:\\notas-extraidas\\reporte_consolidar.csv"

    # Eliminar el resto definitivamente (sin papelera)
    py consolidar_carpetas_notas.py --destino ... --borrar

    # Solo procesar una carpeta específica (testing)
    py consolidar_carpetas_notas.py --destino ... --solo 309414
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("consolidar_carpetas")

RE_PDF_NOMBRADO = re.compile(r"^NC_(\d{4,})_(HUS\d{6,12})\.pdf$", re.IGNORECASE)
PAPELERA = "_papelera"


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


def buscar_pdf_renombrado(carpeta: Path) -> tuple[Path, str, str] | None:
    for p in carpeta.iterdir():
        if not p.is_file():
            continue
        m = RE_PDF_NOMBRADO.match(p.name)
        if m:
            return p, m.group(1), m.group(2)
    return None


def buscar_xml_origen(carpeta: Path) -> Path | None:
    """Busca `ad*.xml` (es el XML de la factura electrónica DIAN)."""
    for p in carpeta.iterdir():
        if not p.is_file() or p.suffix.lower() != ".xml":
            continue
        if p.name.lower().startswith("ad"):
            return p
    return None


def buscar_json_origen(carpeta: Path) -> Path | None:
    """Busca RIPS/ResultadosDoker_*.json (CUV del DIAN)."""
    rips = carpeta / "RIPS"
    if not rips.is_dir():
        return None
    for p in rips.iterdir():
        if not p.is_file() or p.suffix.lower() != ".json":
            continue
        if "resultadosdoker" in p.name.lower():
            return p
    return None


def procesar_carpeta(carpeta: Path, base: Path, borrar: bool, dry_run: bool, aceptar_sin_json: bool = False) -> dict:
    registro = {
        "carpeta": carpeta.name,
        "nota_electronica": "",
        "factura": "",
        "pdf_final": "",
        "xml_final": "",
        "json_final": "",
        "items_a_papelera": "",
        "estado": "",
        "detalle": "",
    }

    info = buscar_pdf_renombrado(carpeta)
    if not info:
        registro["estado"] = "SIN_PDF_RENOMBRADO"
        registro["detalle"] = "No hay PDF con patrón NC_<NE>_HUS<num>.pdf"
        logger.warning(f"{carpeta.name}: SIN_PDF_RENOMBRADO")
        return registro

    pdf, nota_elec, factura = info
    registro["nota_electronica"] = nota_elec
    registro["factura"] = factura
    registro["pdf_final"] = pdf.name

    nombre_xml_final = f"XML_{nota_elec}_{factura}.xml"
    nombre_json_final = f"CUV_{nota_elec}_{factura}.json"
    nombres_finales = {pdf.name, nombre_xml_final, nombre_json_final}

    # ── PASO 1: renombrar ad*.xml → XML_<NE>_<factura>.xml ────────────────
    xml_destino = carpeta / nombre_xml_final
    if xml_destino.exists():
        registro["xml_final"] = nombre_xml_final  # ya renombrado de antes
    else:
        xml_origen = buscar_xml_origen(carpeta)
        if xml_origen is None:
            registro["estado"] = "FALTA_XML"
            registro["detalle"] = "No encontré ad*.xml en la carpeta"
            logger.warning(f"{carpeta.name}: FALTA_XML — no toco la papelera")
            return registro
        if dry_run:
            logger.info(f"  DRY: renombraría {xml_origen.name} → {nombre_xml_final}")
        else:
            try:
                xml_origen.rename(xml_destino)
                logger.info(f"  + {xml_origen.name} → {nombre_xml_final}")
            except OSError as e:
                registro["estado"] = "ERROR_RENOMBRAR_XML"
                registro["detalle"] = f"{type(e).__name__}: {e}"
                logger.error(f"{carpeta.name}: ERROR_RENOMBRAR_XML — {e}")
                return registro
        registro["xml_final"] = nombre_xml_final

    # ── PASO 2: mover RIPS/ResultadosDoker_*.json → CUV_<NE>_<factura>.json ──
    json_destino = carpeta / nombre_json_final
    sin_json = False
    if json_destino.exists():
        registro["json_final"] = nombre_json_final
    else:
        json_origen = buscar_json_origen(carpeta)
        if json_origen is None:
            if not aceptar_sin_json:
                registro["estado"] = "FALTA_JSON"
                registro["detalle"] = "No encontré RIPS/ResultadosDoker_*.json"
                logger.warning(f"{carpeta.name}: FALTA_JSON — no toco la papelera")
                return registro
            # Con --aceptar-sin-json: seguimos consolidando solo con PDF+XML
            sin_json = True
            nombres_finales.discard(nombre_json_final)
            logger.info(f"  ⚠ {carpeta.name}: sin JSON — consolido solo PDF+XML")
        else:
            if dry_run:
                logger.info(f"  DRY: movería RIPS/{json_origen.name} → {nombre_json_final}")
            else:
                try:
                    shutil.move(str(json_origen), str(json_destino))
                    logger.info(f"  + RIPS/{json_origen.name} → {nombre_json_final}")
                except OSError as e:
                    registro["estado"] = "ERROR_MOVER_JSON"
                    registro["detalle"] = f"{type(e).__name__}: {e}"
                    logger.error(f"{carpeta.name}: ERROR_MOVER_JSON — {e}")
                    return registro
            registro["json_final"] = nombre_json_final

    # ── PASO 3: limpiar el resto (mover a papelera o borrar) ─────────────
    a_eliminar = []
    for item in carpeta.iterdir():
        if item.name in nombres_finales:
            continue
        a_eliminar.append(item)

    # Nombres apartados para el reporte (sin paths absolutos)
    registro["items_a_papelera"] = ";".join(sorted(i.name for i in a_eliminar))

    if not a_eliminar:
        registro["estado"] = "OK_SIN_JSON" if sin_json else "OK"
        return registro

    if dry_run:
        for item in a_eliminar:
            kind = "DIR" if item.is_dir() else "FILE"
            logger.info(f"  DRY: apartaría {kind} {item.name}")
        registro["estado"] = "OK"
        return registro

    if borrar:
        for item in a_eliminar:
            try:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                logger.info(f"  - eliminado: {item.name}")
            except OSError as e:
                registro["estado"] = "ERROR_LIMPIAR"
                registro["detalle"] = f"{type(e).__name__} en {item.name}: {e}"
                logger.error(f"{carpeta.name}: ERROR_LIMPIAR {item.name} — {e}")
                return registro
        registro["estado"] = "OK"
        return registro

    # Default: mover a _papelera/<NE>/
    papelera_carpeta = base / PAPELERA / nota_elec
    papelera_carpeta.mkdir(parents=True, exist_ok=True)
    for item in a_eliminar:
        try:
            destino_papelera = papelera_carpeta / item.name
            if destino_papelera.exists():
                shutil.rmtree(
                    destino_papelera
                ) if destino_papelera.is_dir() else destino_papelera.unlink()
            shutil.move(str(item), str(destino_papelera))
            logger.info(f"  → {PAPELERA}/{nota_elec}/{item.name}")
        except OSError as e:
            registro["estado"] = "ERROR_LIMPIAR"
            registro["detalle"] = f"{type(e).__name__} en {item.name}: {e}"
            logger.error(f"{carpeta.name}: ERROR_LIMPIAR {item.name} — {e}")
            return registro

    registro["estado"] = "OK_SIN_JSON" if sin_json else "OK"
    return registro


def escribir_reporte(resultados: list[dict], ruta: Path) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    campos = [
        "carpeta",
        "nota_electronica",
        "factura",
        "pdf_final",
        "xml_final",
        "json_final",
        "items_a_papelera",
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
        help="Carpeta base con subcarpetas por nota crédito",
    )
    parser.add_argument(
        "--reporte",
        type=Path,
        default=Path("reporte_consolidar.csv"),
        help="CSV con el detalle por carpeta",
    )
    parser.add_argument(
        "--borrar",
        action="store_true",
        help="Eliminar los archivos extras (default: mover a _papelera/)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="No toca nada; solo reporta",
    )
    parser.add_argument(
        "--solo",
        type=str,
        default=None,
        help="Procesar solo esta carpeta (útil para testing)",
    )
    parser.add_argument(
        "--aceptar-sin-json",
        action="store_true",
        help=(
            "Consolidar también las carpetas que no traen el CUV JSON del RIPS "
            "(deja solo PDF+XML como finales). Útil para notas viejas donde el "
            "validador DIAN nunca generó el CUV. Estado final: OK_SIN_JSON."
        ),
    )
    args = parser.parse_args()

    setup_logging()

    if not args.destino.is_dir():
        logger.error(f"--destino no existe o no es carpeta: {args.destino}")
        return 1

    if args.solo:
        carpeta_solo = args.destino / args.solo
        if not carpeta_solo.is_dir():
            logger.error(f"--solo: no existe la carpeta {carpeta_solo}")
            return 1
        carpetas = [carpeta_solo]
    else:
        carpetas = [d for d in sorted(args.destino.iterdir()) if d.is_dir() and d.name != PAPELERA]

    modo = (
        "DRY-RUN (no toca nada)"
        if args.dry_run
        else ("BORRAR definitivo" if args.borrar else f"mover a {PAPELERA}/")
    )
    logger.info(f"Procesando {len(carpetas)} carpetas | modo: {modo}")
    logger.info(f"Destino: {args.destino}")

    resultados = []
    for i, c in enumerate(carpetas, 1):
        logger.info(f"[{i}/{len(carpetas)}] {c.name}")
        resultados.append(procesar_carpeta(
            c, args.destino, args.borrar, args.dry_run,
            aceptar_sin_json=args.aceptar_sin_json,
        ))

    escribir_reporte(resultados, args.reporte)

    resumen: dict[str, int] = {}
    for r in resultados:
        resumen[r["estado"]] = resumen.get(r["estado"], 0) + 1

    logger.info("=" * 60)
    logger.info("RESUMEN")
    logger.info(f"  Carpetas: {len(resultados)}")
    for k, n in sorted(resumen.items(), key=lambda kv: -kv[1]):
        logger.info(f"    {k}: {n}")
    logger.info(f"  Reporte: {args.reporte}")

    problemas = sum(n for k, n in resumen.items() if k not in ("OK",))
    return 0 if problemas == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
