#!/usr/bin/env python3
"""Diagnóstico del cruce de soportes clínicos del radicador.

Recorre la(s) carpeta(s) de soportes EXACTAMENTE como lo hace el radicador con
--soportes y reporta si encuentra archivos y para qué facturas. Sirve para
saber, en segundos y sin correr las 12 mil facturas, si el problema es la RUTA
(el share no se ve / está vacío desde Python) o el CRUCE (numeración que no
coincide).

Solo LEE. No modifica nada.

Uso:
    py tools\\diag_soportes.py "Y:\\6. JUNIO 2026 - SOPORTES RADICACION"
    py tools\\diag_soportes.py "Y:\\..." "Z:\\..." "X:\\..." --factura HUS521788
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radicar_facturacion as rad  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Diagnóstico del cruce de soportes clínicos (--soportes). Solo lee."
    )
    p.add_argument("raices", nargs="+", type=Path, help="Carpeta(s) de soportes a revisar.")
    p.add_argument(
        "--factura",
        action="append",
        default=[],
        metavar="HUSxxxx",
        help="Factura a verificar en el índice (se puede repetir). Def.: HUS521788.",
    )
    args = p.parse_args(argv)
    facturas = args.factura or ["HUS521788"]

    indice_total: dict[str, list] = {}
    for raiz in args.raices:
        print("=" * 70)
        print(f"RAÍZ: {raiz}")
        print(f"  ¿existe?  {raiz.exists()}   ¿es carpeta?  {raiz.is_dir()}")
        if not raiz.is_dir():
            print("  ⚠ Python NO ve esta carpeta. Revisá la ruta / el disco mapeado / permisos.")
            continue
        # Primer nivel: si sale vacío acá pero en el Explorador ves carpetas, el
        # disco no está visible para el proceso de Python (típico de unidades de
        # red mapeadas por sesión / permisos).
        try:
            top = sorted(e.name for e in os.scandir(raiz))
        except OSError as e:
            print(f"  ⚠ No pude listar el contenido: {e}")
            continue
        print(f"  Entradas en el primer nivel: {len(top)}")
        for name in top[:15]:
            print(f"    - {name}")
        if len(top) > 15:
            print(f"    … (+{len(top) - 15} más)")
        idx = rad.indexar_soportes_clinicos(raiz, rad.PATRON_FACTURA_DEFAULT)
        print(f"  -> indexadas {len(idx)} factura(s) con soporte en esta raíz.")
        ejemplos = list(idx)[:10]
        if ejemplos:
            print(f"  Ejemplos de facturas indexadas: {', '.join(ejemplos)}")
        for fac, rutas in idx.items():
            indice_total.setdefault(fac, []).extend(rutas)

    print("=" * 70)
    print(f"ÍNDICE TOTAL: {len(indice_total)} factura(s) con soporte (todas las raíces).")
    for f in facturas:
        clave = rad.normalizar_factura(f)
        rutas = indice_total.get(clave, [])
        print(f"\n¿'{f}' (clave {clave}) en el índice?  {'SÍ' if rutas else 'NO'}")
        for ruta in rutas[:15]:
            cod, _desc, _ok = rad.clasificar_soporte(Path(ruta).name)
            print(f"    [{cod}] {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
