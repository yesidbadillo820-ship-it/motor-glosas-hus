r"""Cuenta las glosas sin asumir el nombre de la tabla.

Pregunta primero a sqlite_master qué tablas existe de verdad, ubica la de
GlosaRecord por su firma de columnas, y recién ahí cuenta. Uso:

    .\venv\Scripts\python.exe verificar_glosas.py
"""

import glob
import os
import sqlite3
from datetime import datetime

# Columnas que solo tiene la tabla de glosas (GlosaRecord). No se busca por
# nombre: el nombre puede cambiar, la firma no.
FIRMA = {"valor_objetado", "valor_aceptado", "creado_en"}

hoy = datetime.now()
archivos = sorted(glob.glob("*.db") + glob.glob("data/*.db") + glob.glob("**/*.db", recursive=True))
vistos = set()

for ruta in archivos:
    real = os.path.realpath(ruta)
    if real in vistos:
        continue
    vistos.add(real)
    try:
        con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    except sqlite3.Error as e:
        print(f"[!] {ruta}: no se pudo abrir ({e})")
        continue
    try:
        tablas = [
            r[0]
            for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        if not tablas:
            continue
        print(f"\n=== {ruta} ===")
        print(f"    tablas: {', '.join(tablas)}")
        for t in tablas:
            cols = {r[1] for r in con.execute(f'PRAGMA table_info("{t}")')}
            if not FIRMA.issubset(cols):
                continue
            total = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            print(f"\n    >>> tabla de glosas encontrada: «{t}»")
            print(f"        TOTAL DE GLOSAS (todas): {total}")
            mes = con.execute(
                f"SELECT COUNT(*) FROM \"{t}\" WHERE strftime('%Y-%m', creado_en) = ?",
                (hoy.strftime("%Y-%m"),),
            ).fetchone()[0]
            print(
                f"        De ESTE mes ({hoy.strftime('%Y-%m')}): {mes}   <- lo que muestra el encabezado"
            )
            print("        Ultimos meses:")
            for m, n, v in con.execute(
                f"SELECT strftime('%Y-%m', creado_en) AS m, COUNT(*), "
                f'COALESCE(SUM(valor_objetado),0) FROM "{t}" '
                "GROUP BY m ORDER BY m DESC LIMIT 6"
            ):
                print(
                    f"          {m or '(sin fecha)'}: {n:>5} glosas   $ {v:,.0f}".replace(",", ".")
                )
    finally:
        con.close()

if not vistos:
    print("No se encontro ningun archivo .db. Corra el script dentro de C:\\motor-glosas\\repo")
