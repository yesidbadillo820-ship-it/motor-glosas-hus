"""Convierte el Excel HOMOLOGADOR_DE_CUPS_A_SOAT.xlsx a JSON comprimido.

Genera app/data/cups_soat_homologacion.json.gz a partir del Excel oficial
de homologación CUPS (Manual Único Res. 2775) → SOAT (Manual Tarifario).

Uso:
    python tools/generar_cups_soat_json.py /ruta/al/HOMOLOGADOR.xlsx

El Excel tiene 5 columnas:
    0: COD. CUPS RES. 2775     (código CUPS de 6 dígitos)
    1: COD. SOAT              (código SOAT numérico)
    2: Descripción SOAT
    3: COD. CUPS RES. 2775    (duplicado de col 0)
    4: DESCRIPCIÓN SERVICIO O PROCEDIMIENTO  (descripción del CUPS)

Salida JSON:
    {
      "_meta": {...},
      "cups_a_soat": {
        "012403": [
          {"soat": "1101", "desc_soat": "...", "desc_cups": "..."},
          ...
        ]
      }
    }

Un CUPS puede mapear a varios SOAT (multi-mapeo ~11.7%).
"""

from __future__ import annotations

import gzip
import json
import os
import sys
from collections import OrderedDict

# Ruta de salida relativa a la raíz del repo.
_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app",
    "data",
    "cups_soat_homologacion.json.gz",
)


def generar(src_xlsx: str, out_path: str = _OUT) -> dict:
    import openpyxl  # import local para no exigir openpyxl en producción

    wb = openpyxl.load_workbook(src_xlsx, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]

    cups_a_soat: "OrderedDict[str, list[dict]]" = OrderedDict()
    n = 0
    for r in ws.iter_rows(min_row=2, values_only=True):
        cups, soat, desc_soat, _cups2, desc_cups = r[0], r[1], r[2], r[3], r[4]
        if cups is None or soat is None:
            continue
        cups_s = str(cups).strip()
        soat_s = str(soat).strip()
        entry = {
            "soat": soat_s,
            "desc_soat": str(desc_soat).strip() if desc_soat else "",
            "desc_cups": str(desc_cups).strip() if desc_cups else "",
        }
        if cups_s not in cups_a_soat:
            cups_a_soat[cups_s] = []
        if not any(e["soat"] == soat_s for e in cups_a_soat[cups_s]):
            cups_a_soat[cups_s].append(entry)
        n += 1

    data = {
        "_meta": {
            "fuente": "Homologación CUPS (Manual Único Res. 2775) → Manual Tarifario SOAT",
            "descripcion": (
                "Mapeo oficial de código CUPS a código SOAT con descripciones. "
                "Un CUPS puede mapear a varios SOAT (multi-mapeo ~11.7%)."
            ),
            "filas_origen": n,
            "cups_unicos": len(cups_a_soat),
            "soat_unicos": len({e["soat"] for v in cups_a_soat.values() for e in v}),
            "version": "2025-06-30",
        },
        "cups_a_soat": cups_a_soat,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with gzip.open(out_path, "wt", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    return data["_meta"]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python tools/generar_cups_soat_json.py /ruta/al/HOMOLOGADOR.xlsx")
        sys.exit(1)
    meta = generar(sys.argv[1])
    print(f"JSON.gz generado en {_OUT}")
    print(json.dumps(meta, ensure_ascii=False, indent=2))
