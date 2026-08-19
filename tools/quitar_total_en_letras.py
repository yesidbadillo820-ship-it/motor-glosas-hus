"""quitar_total_en_letras.py — deja el detallado sin el total escrito en palabras.

El detallado que imprime el sistema del hospital cierra con dos totales: el
**número** («VALOR TOTAL ORDEN DE SERVICIO $626.115») y el mismo valor **en
letras** («SEISCIENTOS VEINTISÉIS MIL CIENTO QUINCE PESOS CON CERO CTVS
M/Cte.»).

Este bot **borra el renglón en letras y deja ese espacio vacío**. Todo lo demás
queda igual: los números, el formato, las celdas combinadas, los anchos.

USO (Windows, desde C:\\temp-notas):

    py tools\\quitar_total_en_letras.py ^
        --origen "D:\\...\\POR_FACTURA_31068" ^
        --salida "D:\\...\\POR_FACTURA_31068_SIN_LETRAS"

    REM Ver qué haría, sin escribir nada:
    py tools\\quitar_total_en_letras.py --origen "D:\\..." --salida "D:\\..." --dry-run

Requiere una sola vez: `py -m pip install openpyxl`

Seguro por defecto: **no toca los archivos de origen**, escribe copias nuevas en
la carpeta de salida. Y no borra a ciegas: solo vacía las celdas que de verdad
traen un importe escrito en palabras (las que dicen PESOS y CTVS). Si en alguna
factura no encuentra el renglón, lo dice en vez de callarlo.
"""

from __future__ import annotations

import argparse
import csv
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ajustar_detallado_glosas import (  # noqa: E402
    MARCA_TOTAL_LETRAS,
    Celda,
    IndiceHoja,
    _abrir_libro,
    _norm,
    segmentar_facturas,
)

logger = logging.getLogger("quitar_total_en_letras")

EXTENSIONES = (".xlsx", ".xlsm")

# Un importe en palabras siempre termina igual en este formato: «… PESOS CON
# … CTVS M/Cte.». Se exige esa firma para no vaciar una celda que no sea eso.
_ES_IMPORTE_EN_LETRAS = re.compile(r"\bPESOS\b.*\bCTVS?\b", re.IGNORECASE | re.DOTALL)


@dataclass
class ResultadoArchivo:
    """Qué pasó con un archivo."""

    archivo: str
    estado: str  # LIMPIADO · SIN_LETRAS · ERROR
    borradas: list[str] = field(default_factory=list)  # los textos que se quitaron
    observacion: str = ""


def es_importe_en_letras(texto: object) -> bool:
    """¿Esta celda trae un valor escrito en palabras?"""
    return isinstance(texto, str) and bool(_ES_IMPORTE_EN_LETRAS.search(texto))


def celdas_del_total_en_letras(idx: IndiceHoja) -> list[Celda]:
    """Las celdas con el importe en palabras, una por factura de la hoja.

    Se busca solo en el renglón que empieza por «TOTAL:», que es donde el
    sistema lo imprime. Una hoja puede traer varias facturas apiladas.
    """
    encontradas: list[Celda] = []
    for fac in segmentar_facturas(idx) or [None]:
        desde, hasta = (fac.fila_ini, fac.fila_fin) if fac else (1, idx.max_fila)
        for fila in range(desde, hasta + 1):
            celdas = idx.celdas(fila)
            if not celdas or not _norm(celdas[0].texto).startswith(MARCA_TOTAL_LETRAS):
                continue
            encontradas.extend(c for c in celdas[1:] if es_importe_en_letras(c.valor))
    return encontradas


def procesar_archivo(ruta: Path, destino: Path) -> ResultadoArchivo:
    """Deja una copia del Excel con el total en letras vacío."""
    wb = _abrir_libro(ruta, solo_datos=False)
    try:
        res = ResultadoArchivo(archivo=ruta.name, estado="SIN_LETRAS")
        for ws in wb.worksheets:
            for celda in celdas_del_total_en_letras(IndiceHoja(ws)):
                res.borradas.append(str(celda.valor).strip())
                ws.cell(row=celda.fila, column=celda.col).value = None
        if res.borradas:
            res.estado = "LIMPIADO"
        else:
            res.observacion = "No se encontró ningún total escrito en palabras."
        destino.parent.mkdir(parents=True, exist_ok=True)
        wb.save(destino)
        return res
    finally:
        wb.close()


def _archivos(origenes: list[Path], patron: str, recursivo: bool) -> list[Path]:
    salida: list[Path] = []
    for origen in origenes:
        if origen.is_file():
            salida.append(origen)
            continue
        busca = origen.rglob(patron) if recursivo else origen.glob(patron)
        salida.extend(busca)
    return sorted(
        {
            r
            for r in salida
            if r.suffix.lower() in EXTENSIONES and not r.name.startswith(("~$", "."))
        }
    )


def procesar(
    origenes: list[Path],
    salida: Path,
    patron: str = "*.xlsx",
    recursivo: bool = False,
    reporte: Path | None = None,
) -> list[ResultadoArchivo]:
    archivos = _archivos(origenes, patron, recursivo)
    if not archivos:
        raise ValueError(f"No se encontró ningún Excel en {[str(o) for o in origenes]}")
    resultados = []
    for n, ruta in enumerate(archivos, 1):
        try:
            res = procesar_archivo(ruta, salida / ruta.name)
        except Exception as e:  # noqa: BLE001 - un archivo malo no tumba el lote
            logger.warning("  %s: %s", ruta.name, e)
            res = ResultadoArchivo(archivo=ruta.name, estado="ERROR", observacion=str(e))
        resultados.append(res)
        if n % 50 == 0:
            logger.info("  %d/%d…", n, len(archivos))
    if reporte:
        escribir_reporte(reporte, resultados)
    return resultados


def escribir_reporte(ruta: Path, resultados: list[ResultadoArchivo]) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh, delimiter=";")
        w.writerow(["ARCHIVO", "ESTADO", "CUANTOS", "LO_QUE_SE_QUITO", "OBSERVACION"])
        for r in resultados:
            w.writerow(
                [r.archivo, r.estado, len(r.borradas), " | ".join(r.borradas), r.observacion]
            )


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Deja el detallado sin el total escrito en letras.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--origen", type=Path, nargs="+", required=True, help="Carpeta(s) o archivo(s).")
    p.add_argument("--salida", type=Path, required=True, help="Carpeta donde dejar las copias.")
    p.add_argument("--patron", default="*.xlsx", help="Qué archivos tomar de la carpeta.")
    p.add_argument("--recursivo", action="store_true", help="Entrar también en las subcarpetas.")
    p.add_argument("--reporte-csv", type=Path, help="Listado de lo que se quitó en cada archivo.")
    p.add_argument("--dry-run", action="store_true", help="Solo mostrar qué haría.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.dry_run:
        archivos = _archivos(args.origen, args.patron, args.recursivo)
        print(f"Se procesarían {len(archivos)} archivo(s). No se escribió nada.")
        for r in archivos[:10]:
            print(f"   {r.name}")
        return 0

    try:
        resultados = procesar(
            args.origen, args.salida, args.patron, args.recursivo, args.reporte_csv
        )
    except ValueError as e:
        logger.error("%s", e)
        return 1

    limpiados = [r for r in resultados if r.estado == "LIMPIADO"]
    sin = [r for r in resultados if r.estado == "SIN_LETRAS"]
    errores = [r for r in resultados if r.estado == "ERROR"]
    print(f"\nArchivos procesados   : {len(resultados)}")
    print(f"  con el total en letras quitado : {len(limpiados)}")
    if sin:
        print(f"  sin total en letras            : {len(sin)}")
        for r in sin[:10]:
            print(f"     {r.archivo}")
    if errores:
        print(f"  con error                      : {len(errores)}")
        for r in errores[:10]:
            print(f"     {r.archivo}: {r.observacion}")
    print(f"\nQuedaron en: {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
