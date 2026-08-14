"""facturas_ya_en_tramites.py — Arma la lista de facturas cuyo TRÁMITE ya se envió.

Recorre una carpeta con los archivos "MASIVO COOSALUD ..." que ya se le
mandaron a sistemas y escribe un TXT con todas las facturas que traen (una
por línea). Ese TXT se le pasa después a respuesta_tramites_dgh.py con
--omitir-facturas, para que el próximo masivo NO repita facturas.

Repetir una factura en el cargue de trámites hace que DGH la rechace, así que
este paso evita el retrabajo.

USO:
    py facturas_ya_en_tramites.py "D:\\...\\MASIVOS ENVIADOS"
    py facturas_ya_en_tramites.py "D:\\...\\MASIVOS ENVIADOS" --salida lista.txt

También acepta varias carpetas:
    py facturas_ya_en_tramites.py "D:\\carpeta1" "D:\\carpeta2"
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import openpyxl
except ImportError:
    sys.stderr.write("Falta openpyxl. Corre: py -m pip install openpyxl\n")
    sys.exit(2)

COL_FACTURA = "FacturaCartera.Factura"
PATRON = "*.xlsx"


def norm_factura(v: object) -> str | None:
    """HUS0000522511 / 0000522511 / 522511 -> 522511 (solo el número)."""
    d = re.sub(r"\D", "", str(v or "")).lstrip("0")
    return d or None


def facturas_de_archivo(path: Path) -> set[str]:
    """Facturas de un MASIVO de trámites; set vacío si no es uno."""
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # xlsx corrupto o protegido
        print(f"  (ilegible, se salta) {path.name}: {exc}")
        return set()
    try:
        ws = wb[wb.sheetnames[0]]
        filas = ws.iter_rows(values_only=True)
        headers = list(next(filas, []) or [])
        if COL_FACTURA not in headers:
            return set()
        idx = headers.index(COL_FACTURA)
        facturas = set()
        for row in filas:
            if idx < len(row):
                f = norm_factura(row[idx])
                if f:
                    facturas.add(f)
        return facturas
    finally:
        wb.close()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Lista las facturas cuyos trámites ya se enviaron a sistemas."
    )
    p.add_argument("carpetas", nargs="+", help="Carpeta(s) con los MASIVO ya enviados.")
    p.add_argument(
        "--salida",
        default="FACTURAS YA EN TRAMITES.txt",
        help='TXT de salida. Def: "FACTURAS YA EN TRAMITES.txt"',
    )
    args = p.parse_args(argv)

    todas: set[str] = set()
    por_archivo: list[tuple[str, int]] = []
    revisados = 0
    for carpeta in args.carpetas:
        base = Path(carpeta.strip().strip('"'))
        if not base.is_dir():
            print(f"OJO: no es una carpeta, se salta: {base}")
            continue
        print(f"\nRevisando: {base}")
        for arch in sorted(base.rglob(PATRON)):
            if arch.name.startswith("~$"):
                continue
            revisados += 1
            facturas = facturas_de_archivo(arch)
            if facturas:
                nuevas = facturas - todas
                todas |= facturas
                por_archivo.append((arch.name, len(facturas)))
                print(f"  {arch.name:60} {len(facturas):>5} facturas ({len(nuevas)} nuevas)")

    if not por_archivo:
        print(
            f"\nNo encontré ningún MASIVO de trámites en lo revisado "
            f"({revisados} archivo(s) mirados).\n"
            f"Los MASIVO tienen la columna '{COL_FACTURA}'."
        )
        return 1

    salida = Path(args.salida)
    salida.write_text("\n".join(f"HUS{f}" for f in sorted(todas, key=int)) + "\n", encoding="utf-8")

    print("\n===== LISTO =====")
    print(f"  Archivos de trámites encontrados: {len(por_archivo)}")
    print(f"  Facturas distintas ya enviadas:   {len(todas)}")
    print(f"  Lista guardada en: {salida.resolve()}")
    print(
        "\n  Pásasela al bot de trámites así:\n"
        f'    py respuesta_tramites_dgh.py --omitir-facturas "{salida.resolve()}" ...'
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
