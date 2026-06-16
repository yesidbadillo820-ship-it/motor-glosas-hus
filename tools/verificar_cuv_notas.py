"""verificar_cuv_notas.py — Verifica el estado CUV (MinSalud) de notas crédito.

Recorre el share de facturación electrónica y, para cada factura HUS de la
lista, busca su nota crédito y reporta el resultado de la validación del
Ministerio de Salud:

    factura | nota_electronica | estado | codigo_rechazo | observacion | path

ESTADOS:
    OK                  → ResultState:true, CUV asignado, lista para enviar.
    RECHAZADO           → ResultState:false, no se asigno CUV; ver codigo/observacion.
    SIN_RESULTADOSDOKER → tiene RIPS en el share pero no se encuentra el
                          ResultadosDoker_*.json (no se valido o se borro).
    SIN_NOTA_EN_SHARE   → no se encontro nota credito asociada en ningun
                          periodo recorrido del share (puede que sea de un
                          mes que no fue listado, o no haya nota generada).

USO RAPIDO
----------

    # 38 facturas en una sola linea
    py verificar_cuv_notas.py ^
        --facturas "HUS404136,HUS409872,HUS409574,..." ^
        --reporte  "D:\\USUARIO CARTERA\\Documents\\NOTAS ANTIGUAS\\reporte_cuv.csv"

    # O desde un TXT (una factura por linea)
    py verificar_cuv_notas.py ^
        --lista    "D:\\USUARIO CARTERA\\Documents\\NOTAS ANTIGUAS\\facturas.txt" ^
        --reporte  "D:\\USUARIO CARTERA\\Documents\\NOTAS ANTIGUAS\\reporte_cuv.csv"

    # Restringir periodos (default: todos los YYYYMM del share)
    py verificar_cuv_notas.py --lista ... --periodos 202504,202505,202506 ...

DEPENDENCIAS
------------
    Python 3.9+ (stdlib only)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger("verificar_cuv")

# Acepta HUS123456, HUS0000123456, hus123456, etc. Devuelve el numero sin
# ceros a la izquierda (lo que aparece en numFactura del RIPS DIAN).
RE_HUS = re.compile(r"HUS0*(\d{4,})", re.IGNORECASE)


def normalizar_factura(s: str) -> str | None:
    s = (s or "").strip().upper()
    if not s:
        return None
    m = RE_HUS.search(s)
    return m.group(1) if m else None


def cargar_facturas(args) -> set[str]:
    crudas: list[str] = []
    if args.facturas:
        crudas.extend(args.facturas.split(","))
    if args.lista:
        if not args.lista.is_file():
            logger.error(f"--lista no existe: {args.lista}")
            return set()
        texto = args.lista.read_text(encoding="utf-8-sig", errors="replace")
        crudas.extend(x.strip() for x in texto.replace(",", "\n").splitlines() if x.strip())
    normalizadas: set[str] = set()
    for f in crudas:
        n = normalizar_factura(f)
        if n:
            normalizadas.add(n)
    return normalizadas


def _rips_match(carpeta_ne: Path) -> str | None:
    """Si la carpeta tiene un Rips_<NE>.json, devuelve la factura normalizada;
    si no, None. Busca en la carpeta y en su sub RIPS/."""
    candidatos = list(carpeta_ne.glob("Rips_*.json"))
    if not candidatos:
        candidatos = list(carpeta_ne.glob("RIPS/Rips_*.json"))
    if not candidatos:
        return None
    try:
        with candidatos[0].open(encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None
    num_fac = (data.get("numFactura") or "").strip()
    return normalizar_factura(num_fac)


def _resultados_json(carpeta_ne: Path) -> dict | None:
    candidatos = list(carpeta_ne.glob("ResultadosDoker_*.json"))
    if not candidatos:
        candidatos = list(carpeta_ne.glob("RIPS/ResultadosDoker_*.json"))
    if not candidatos:
        return None
    # El nombre del archivo lleva un timestamp; ordenamos para tomar el ultimo.
    candidatos.sort(reverse=True)
    try:
        with candidatos[0].open(encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def procesar_carpeta_ne(carpeta_ne: Path, buscadas: set[str]) -> dict | None:
    factura_norm = _rips_match(carpeta_ne)
    if factura_norm is None or factura_norm not in buscadas:
        return None

    reporte: dict = {
        "factura": f"HUS{factura_norm}",
        "nota_electronica": carpeta_ne.name,
        "carpeta": str(carpeta_ne),
        "estado": "SIN_RESULTADOSDOKER",
        "cuv": "",
        "codigo_rechazo": "",
        "observacion_rechazo": "",
        "path_rechazo": "",
        "n_rechazos": 0,
        "n_notificaciones": 0,
        "fecha_validacion": "",
    }

    res = _resultados_json(carpeta_ne)
    if res is None:
        return reporte

    reporte["fecha_validacion"] = (res.get("FechaRadicacion") or "")[:19]
    if res.get("ResultState"):
        reporte["estado"] = "OK"
        reporte["cuv"] = (res.get("CodigoUnicoValidacion") or "").strip()
    else:
        reporte["estado"] = "RECHAZADO"
        # No copiamos el CUV cuando hay rechazo (es un mensaje, no un hash util)

    validaciones = res.get("ResultadosValidacion") or []
    rechazos = [v for v in validaciones if (v.get("Clase") or "").upper() == "RECHAZADO"]
    notifs = [v for v in validaciones if (v.get("Clase") or "").upper() == "NOTIFICACION"]
    reporte["n_rechazos"] = len(rechazos)
    reporte["n_notificaciones"] = len(notifs)
    if rechazos:
        r0 = rechazos[0]
        reporte["codigo_rechazo"] = r0.get("Codigo", "")
        reporte["observacion_rechazo"] = (r0.get("Observaciones") or "").strip()
        reporte["path_rechazo"] = r0.get("PathFuente", "")
    return reporte


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--base", type=Path,
        default=Path(r"\\172.16.32.83\factura_electronica_net22"),
        help=r"Base UNC del share (default \\172.16.32.83\factura_electronica_net22)"
    )
    parser.add_argument(
        "--subcarpeta", default="FACTURAS_NOTA",
        help="Subcarpeta dentro de cada periodo (default FACTURAS_NOTA)"
    )
    grupo = parser.add_mutually_exclusive_group(required=True)
    grupo.add_argument("--facturas", help="Facturas HUS separadas por coma.")
    grupo.add_argument("--lista", type=Path, help="TXT con una factura por linea.")
    parser.add_argument(
        "--periodos", default=None,
        help="YYYYMM separados por coma. Default: todos los del share."
    )
    parser.add_argument(
        "--paralelos", type=int, default=8,
        help="Threads para acelerar lectura del share (default 8)."
    )
    parser.add_argument(
        "--reporte", type=Path, default=Path("reporte_cuv.csv"),
        help="CSV de salida (default reporte_cuv.csv)."
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    buscadas = cargar_facturas(args)
    if not buscadas:
        logger.error("No se cargo ninguna factura (--facturas / --lista vacios).")
        return 1
    logger.info(f"Facturas a verificar: {len(buscadas)}")

    if not args.base.is_dir():
        logger.error(f"No accesible: {args.base}")
        return 1

    if args.periodos:
        periodos = [p.strip() for p in args.periodos.split(",") if p.strip()]
    else:
        periodos = sorted(
            p.name for p in args.base.iterdir()
            if p.is_dir() and re.fullmatch(r"\d{6}", p.name)
        )
    logger.info(f"Periodos a recorrer: {periodos}")

    pendientes: set[str] = set(buscadas)
    resultados: list[dict] = []

    for periodo in periodos:
        if not pendientes:
            break
        carpeta_periodo = args.base / periodo / args.subcarpeta
        if not carpeta_periodo.is_dir():
            logger.info(f"  {periodo}: sin {args.subcarpeta}/, saltando")
            continue
        try:
            subcarpetas = [p for p in carpeta_periodo.iterdir() if p.is_dir()]
        except OSError as e:
            logger.warning(f"  {periodo}: ERROR listando — {e}")
            continue
        logger.info(f"  {periodo}: {len(subcarpetas)} carpetas NE — escaneando…")

        with ThreadPoolExecutor(max_workers=args.paralelos) as ex:
            futuros = {ex.submit(procesar_carpeta_ne, c, pendientes): c for c in subcarpetas}
            for f in as_completed(futuros):
                try:
                    r = f.result()
                except Exception as e:
                    logger.warning(f"  error en {futuros[f].name}: {e}")
                    continue
                if r is None:
                    continue
                fac_n = r["factura"][3:].lstrip("0") or "0"
                if fac_n in pendientes:
                    pendientes.discard(fac_n)
                    resultados.append(r)
                    cod = f" [{r['codigo_rechazo']}]" if r["codigo_rechazo"] else ""
                    logger.info(
                        f"  ✓ {r['factura']} (NE {r['nota_electronica']}): {r['estado']}{cod}"
                    )

    # Faltantes
    for f in sorted(pendientes):
        resultados.append({
            "factura": f"HUS{f}",
            "nota_electronica": "",
            "carpeta": "",
            "estado": "SIN_NOTA_EN_SHARE",
            "cuv": "",
            "codigo_rechazo": "",
            "observacion_rechazo": "",
            "path_rechazo": "",
            "n_rechazos": 0,
            "n_notificaciones": 0,
            "fecha_validacion": "",
        })

    args.reporte.parent.mkdir(parents=True, exist_ok=True)
    campos = [
        "factura", "nota_electronica", "estado", "cuv",
        "codigo_rechazo", "observacion_rechazo", "path_rechazo",
        "n_rechazos", "n_notificaciones", "fecha_validacion", "carpeta",
    ]
    with args.reporte.open("w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        w.writeheader()
        for r in sorted(resultados, key=lambda x: x["factura"]):
            w.writerow({k: r.get(k, "") for k in campos})

    estados = Counter(r["estado"] for r in resultados)
    logger.info("=" * 60)
    logger.info("RESUMEN")
    for e, n in estados.most_common():
        logger.info(f"  {e}: {n}")
    logger.info(f"  Reporte: {args.reporte}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
