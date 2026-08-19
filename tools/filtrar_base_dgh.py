"""filtrar_base_dgh.py — Recorta la base DGH a las facturas de un lote.

La base "SERVICIOS FACTURADOS COOSALUD DGH.xlsx" pesa 70 MB y no se puede
mover fácilmente (correo, chat, etc.). Este script deja solo las filas de las
facturas que se están trabajando, y el archivo resultante pesa unos pocos KB.

Las facturas se pueden indicar de tres formas (elige una):
  --carpeta   la carpeta "CARGUE MASIVO COOSALUD" del lote (lee las cabeceras
              HUS*.xlsx de la subcarpeta FACTURAS). Es lo más cómodo.
  --lista     un TXT con una factura por línea (HUS522791 / 522791 / HUS0000522791).
  --facturas  la lista separada por comas.

USO:
    py filtrar_base_dgh.py "D:\\...\\SERVICIOS FACTURADOS COOSALUD DGH.xlsx" ^
        --carpeta "D:\\USUARIO CARTERA\\Desktop\\CARGUE MASIVO COOSALUD"

    py filtrar_base_dgh.py "D:\\...\\DGH.xlsx" --facturas HUS522791,HUS529124

Genera "BASE_DGH_FILTRADA.xlsx" (o lo que diga --salida).
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

COLS_FACTURA = ("FACTURA", "NUMERO_FACTURA", "NUMERO FACTURA", "CUENTA")


def nfact(v: object) -> str | None:
    """HUS0000522511 / 0000522511 / 522511 / 522511-1 -> 522511."""
    d = re.sub(r"\D", "", str(v or "")).lstrip("0")
    return d or None


def norm(h: object) -> str:
    return re.sub(r"\s+", " ", str(h or "")).strip().upper()


def facturas_de_carpeta(carpeta: Path) -> set[str]:
    """Facturas del lote: nombres HUS######.xlsx de la subcarpeta FACTURAS."""
    facturas: set[str] = set()
    raiz = carpeta / "FACTURAS" if (carpeta / "FACTURAS").is_dir() else carpeta
    for arch in raiz.rglob("*.xlsx"):
        nombre = arch.name.upper()
        if nombre.startswith("~$") or nombre.startswith(("DETALLE", "GLOSAS", "CONSOLIDADO")):
            continue
        f = nfact(arch.stem)
        if f:
            facturas.add(f)
    return facturas


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Recorta la base DGH a las facturas de un lote.")
    p.add_argument("base", help="Ruta de SERVICIOS FACTURADOS COOSALUD DGH.xlsx")
    p.add_argument("--carpeta", default=None, help='Carpeta "CARGUE MASIVO COOSALUD" del lote.')
    p.add_argument("--lista", default=None, help="TXT con una factura por línea.")
    p.add_argument("--facturas", default=None, help="Facturas separadas por coma.")
    p.add_argument("--salida", default=None, help="Xlsx de salida. Def: BASE_DGH_FILTRADA.xlsx")
    args = p.parse_args(argv)

    base = Path(args.base.strip().strip('"'))
    if not base.is_file():
        sys.stderr.write(f"No existe la base: {base}\n")
        return 2

    objetivo: set[str] = set()
    if args.carpeta:
        carpeta = Path(args.carpeta.strip().strip('"'))
        if not carpeta.is_dir():
            sys.stderr.write(f"No existe la carpeta: {carpeta}\n")
            return 2
        objetivo = facturas_de_carpeta(carpeta)
        print(f"Facturas leídas de la carpeta: {len(objetivo)}")
    elif args.lista:
        lista = Path(args.lista.strip().strip('"'))
        if not lista.is_file():
            sys.stderr.write(f"No existe la lista: {lista}\n")
            return 2
        objetivo = {f for f in (nfact(x) for x in lista.read_text(errors="replace").split()) if f}
        print(f"Facturas leídas del TXT: {len(objetivo)}")
    elif args.facturas:
        objetivo = {f for f in (nfact(x) for x in args.facturas.split(",")) if f}
        print(f"Facturas indicadas: {len(objetivo)}")
    else:
        sys.stderr.write("Indica --carpeta, --lista o --facturas.\n")
        return 2
    if not objetivo:
        sys.stderr.write("No encontré ninguna factura que buscar.\n")
        return 2

    print(f"Leyendo la base (son ~70 MB, tarda un poco): {base.name} ...")
    wb = openpyxl.load_workbook(base, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    it = ws.iter_rows(values_only=True)
    headers = list(next(it, []) or [])
    idx = next((i for i, h in enumerate(headers) if norm(h) in COLS_FACTURA), None)
    if idx is None:
        wb.close()
        sys.stderr.write(f"No hallé la columna FACTURA. Encabezados: {headers}\n")
        return 2
    print(f"Columna de factura: '{headers[idx]}' (posición {idx + 1})")

    out = openpyxl.Workbook()
    wo = out.active
    wo.title = ws.title
    wo.append(list(headers))
    total = guardadas = 0
    encontradas: set[str] = set()
    for row in it:
        total += 1
        f = nfact(row[idx]) if idx < len(row) else None
        if f in objetivo:
            wo.append(list(row))
            guardadas += 1
            encontradas.add(f)
    wb.close()

    salida = (
        Path(args.salida.strip().strip('"'))
        if args.salida
        else base.parent / "BASE_DGH_FILTRADA.xlsx"
    )
    try:
        out.save(salida)
    except Exception:
        salida = Path.cwd() / "BASE_DGH_FILTRADA.xlsx"
        out.save(salida)

    print(f"\nFilas leídas de la base: {total:,}")
    print(f"Filas guardadas:         {guardadas:,}")
    print(f"Facturas encontradas:    {len(encontradas)} de {len(objetivo)}")
    faltan = objetivo - encontradas
    if faltan:
        print("OJO, estas NO están en la base (DGH no las tiene):")
        print("  " + ", ".join("HUS" + f for f in sorted(faltan, key=int)))
    print(f"\nListo. Sube este archivo: {salida.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
