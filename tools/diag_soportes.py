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
    p.add_argument(
        "--origen",
        type=Path,
        default=None,
        help="Share de FE del lote (opcional): cruza el lote real contra el índice "
        "y hace deep-dive de la(s) factura(s) para ver si el cruce le pega.",
    )
    args = p.parse_args(argv)
    facturas = args.factura or ["HUS521788"]

    # El mismo perfil (y patrón de factura) que usa el radicador: si el JSON de
    # perfiles cambia el patrón, el diagnóstico debe diagnosticar ESE cruce.
    cfg = rad.cargar_perfiles(None)

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
        idx = rad.indexar_soportes_clinicos(raiz, cfg.patron_factura)
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

    if args.origen is not None:
        _cruzar_con_lote(args.origen, indice_total, facturas, cfg)
    return 0


def _cruzar_con_lote(
    origen: Path,
    indice_total: dict[str, list],
    facturas: list[str],
    cfg: rad.ConfigRadicacion,
) -> None:
    """Cruza el lote real (share de FE) contra el índice de soportes y hace un
    deep-dive de cada factura pedida: qué factura_norm calcula el lote, si el
    cruce le pega y en qué estado queda. Aísla el bug de "numeración que no
    coincide" del de "el share no tiene el soporte"."""
    print("=" * 70)
    print(f"LOTE (origen): {origen}")
    if not origen.is_dir():
        print("  ⚠ Python NO ve el origen. Revisá la ruta / permisos.")
        return
    items = rad.descubrir_auto(origen, {}, cfg, cfg.patron_factura)
    # Clave barata por el nombre/hint de carpeta (sin leer el RIPS todavía).
    por_clave: dict[str, tuple] = {}
    for fh, arch, carp, ent in items:
        por_clave.setdefault(rad.normalizar_factura(fh), (fh, arch, carp, ent))
    en_indice = sum(1 for k in por_clave if k in indice_total)
    total = len(por_clave)
    pct = 100 * en_indice / max(1, total)
    print(f"  Facturas en el lote: {total:,}")
    print(f"  De ellas, con carpeta de soporte en el índice: {en_indice:,} ({pct:.0f}%)")
    solo_indice = len(indice_total) - en_indice
    print(f"  Facturas del índice que NO están en el lote: {max(0, solo_indice):,}")

    for f in facturas:
        clave = rad.normalizar_factura(f)
        print(f"\n  ── deep-dive {f} (clave por carpeta: {clave}) ──")
        item = por_clave.get(clave)
        if item is None:
            print(f"    NO aparece en el lote {origen} con esa clave.")
            continue
        fh, arch, carp, ent = item
        # SIN cruce y CON cruce, para ver el efecto real del índice.
        base = rad.procesar_factura(fh, arch, carp, ent, cfg)
        cruz = rad.procesar_factura(fh, arch, carp, ent, cfg, indice_total)
        print(f"    factura_norm que calcula el lote : {cruz.factura_norm}")
        print(
            f"    ¿esa clave está en el índice?     {'SÍ' if cruz.factura_norm in indice_total else 'NO'}"
        )
        print(
            f"    estado SIN cruce  : {base.estado}  (faltan: {base.soportes_esperados_faltantes})"
        )
        print(
            f"    estado CON cruce  : {cruz.estado}  (faltan: {cruz.soportes_esperados_faltantes})"
        )
        print(f"    soportes anexados por el cruce   : {len(cruz.soportes_clinicos)}")
        for ruta in cruz.soportes_clinicos[:12]:
            print(f"        + {ruta}")


if __name__ == "__main__":
    raise SystemExit(main())
