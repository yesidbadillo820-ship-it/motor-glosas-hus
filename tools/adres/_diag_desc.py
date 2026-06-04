r"""_diag_desc.py — Diagnóstico (descartable) de por qué quedan descripciones vacías.

Para los códigos SOAT / precios que el FUR SERVICIOS deja sin descripción,
muestra DOS cosas leyendo directamente el PDF de la factura:

  1) Qué descripciones trae la representación DIAN a ese precio unitario.
     - 1 sola (modulo cortes) → debería enlazar; si no, revisar parser.
     - varias distintas       → CHOQUE real: un código de tarifa cubre
                                 varios procedimientos. El cruce por precio
                                 no puede (ni debe) resolverlo.

  2) Qué descripción trae el "Detalle de Cargos" (págs 1-7, reporte
     FCRPFacturaEntidad) para ese código SOAT — ahí el código y el nombre
     van en la misma fila, así que es la fuente correcta para desambiguar.

Uso:
    py tools\adres\_diag_desc.py <carpeta_o_pdf> [cod1 cod2 ...] [-- precio1 precio2 ...]

Sin argumentos extra usa los 9 del caso HUS428139.
"""

from __future__ import annotations

import sys
from pathlib import Path

from factura_pdf_lectura import (
    _candidatos_dian_pdf,
    _clave_desc,
    hallar_factura_pdf,
    leer_factura_pdf,
)

CODS_DEFECTO = ["21102", "39140", "19482", "21105"]
PRECIOS_DEFECTO = ["95400", "83400", "80900"]


def _resolver_pdf(arg: str) -> Path | None:
    p = Path(arg)
    if p.is_dir():
        return hallar_factura_pdf(p)
    if p.is_file() and p.suffix.lower() == ".pdf":
        return p
    return None


def main() -> int:
    if len(sys.argv) < 2:
        sys.stderr.write(__doc__ or "")
        return 1

    pdf = _resolver_pdf(sys.argv[1])
    if not pdf:
        sys.stderr.write(f"No encontré un PDF de factura en: {sys.argv[1]}\n")
        return 1

    args = sys.argv[2:]
    if "--" in args:
        i = args.index("--")
        cods = args[:i] or CODS_DEFECTO
        precios = args[i + 1 :] or PRECIOS_DEFECTO
    else:
        cods = args or CODS_DEFECTO
        precios = PRECIOS_DEFECTO

    print(f"PDF: {pdf.name}\n")

    # --- (1) DIAN: candidatos por precio ---
    print("=" * 70)
    print("(1) REPRESENTACIÓN DIAN — descripciones por precio unitario")
    print("=" * 70)
    candidatos = _candidatos_dian_pdf(pdf)
    print(f"  precios distintos en el DIAN: {len(candidatos)}\n")
    for vr in precios:
        descs = candidatos.get(vr)
        if not descs:
            print(f"  ${vr}: (no aparece en el DIAN con código genérico válido)")
            continue
        claves = {_clave_desc(d) for d in descs}
        veredicto = "ÚNICO (debería enlazar)" if len(claves) == 1 else f"CHOQUE: {len(claves)} servicios distintos"
        print(f"  ${vr}: {len(descs)} renglón(es) → {veredicto}")
        for d in dict.fromkeys(descs):  # distintas, preservando orden
            print(f"        • {d!r}")
    print()

    # --- (2) Detalle de Cargos: código SOAT → nombre en la misma fila ---
    print("=" * 70)
    print("(2) DETALLE DE CARGOS (págs 1-7) — código SOAT + nombre por fila")
    print("=" * 70)
    try:
        lineas = leer_factura_pdf(pdf)
    except Exception as e:
        print(f"  No pude parsear el Detalle de Cargos: {e}")
        return 0
    print(f"  líneas leídas del Detalle: {len(lineas)}\n")
    objetivo = set(cods)
    encontradas = 0
    for ln in lineas:
        if ln.get("codigo") in objetivo:
            encontradas += 1
            print(
                f"  cod={ln['codigo']:<8} ${ln.get('vr_unitario',''):>8} "
                f"x{ln.get('cantidad',''):<3} → {ln.get('descripcion','')!r}"
            )
    if not encontradas:
        print("  (ninguno de los códigos objetivo apareció en el Detalle de Cargos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
