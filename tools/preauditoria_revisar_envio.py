"""Revisa un envío: qué facturas trae la fuente y de qué cargue viene cada una.

POR QUÉ EXISTE (caso real 19-08-2026, envío 232047). Al escribir un envío la
página trae TODAS las facturas que la fuente de Radicación tenga con ese
número. Esa fuente se actualiza factura por factura: cuando facturación saca
una factura de un envío, la factura simplemente deja de venir en el Excel
nuevo — pero su fila vieja se queda con el envío anterior y el sistema la
sigue arrastrando. Resultado: la página mostraba 13 facturas donde el DGH y el
Excel mostraban 12.

Este comando NO cambia nada: solo mira y dice, factura por factura, de qué
cargue del Excel viene y si está o no en el consolidado. La que aparezca con
fecha vieja mientras el resto se actualizó ayer es la sospechosa.

USO EN EL PC DE CARTERA (PowerShell o cmd, desde C:\\motor-glosas\\repo):

    venv\\Scripts\\python.exe tools\\preauditoria_revisar_envio.py 232047

Para quitar una factura que no corresponde NO se usa este comando: se usa el
botón 🗑 de esa fila en la ventana del oficio (solo administradores).
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path


def _ruta_base() -> str:
    env = os.environ.get("DATABASE_URL", "")
    if "sqlite:///" in env:
        return env.split("sqlite:///")[-1]
    return str(Path(__file__).resolve().parent.parent / "data" / "motorglosas.db")


def _fecha(v) -> str:
    return str(v)[:16].replace("T", " ") if v else "—"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    envio = sys.argv[1].strip()
    ruta = sys.argv[2] if len(sys.argv) > 2 else _ruta_base()
    if not Path(ruta).exists():
        print(f"No se encontró la base de datos: {ruta}")
        return 1

    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=30)
    filas = con.execute(
        "SELECT factura, valor, fuente_archivo, importado_en, actualizado_en "
        "FROM preaud_fuente_radicacion WHERE envio=? ORDER BY factura",
        (envio,),
    ).fetchall()

    print("=" * 78)
    print(f"  ENVÍO {envio} — qué trae la fuente de Radicación de Cuentas")
    print(f"  Base: {ruta}")
    print("=" * 78)
    if not filas:
        print("\nEse envío no está en la fuente de Radicación. Suba el Excel del DGH.")
        con.close()
        return 0

    ultimas = [f[4] or f[3] for f in filas if (f[4] or f[3])]
    mas_reciente = max(ultimas) if ultimas else None
    print(f"\n{len(filas)} factura(s) en la fuente:\n")
    print(f"  {'FACTURA':<18}{'VALOR':>14}  {'ACTUALIZADA':<18}{'EN EL OFICIO':<28}ARCHIVO")
    sospechosas = []
    for factura, valor, archivo, imp, act in filas:
        cuando = act or imp
        canon = con.execute(
            "SELECT estado, oficio_fhus FROM preaud_facturas WHERE factura=?", (factura,)
        ).fetchone()
        donde = f"{canon[1] or '—'} ({canon[0]})" if canon else "no está cargada"
        marca = ""
        # Misma regla que usa la página: si el resto del envío se actualizó
        # mucho después, esta fila quedó de un cargue anterior.
        if mas_reciente and cuando and str(cuando)[:10] < str(mas_reciente)[:10]:
            marca = "  <-- OJO"
            sospechosas.append((factura, cuando, donde))
        print(
            f"  {factura:<18}{valor or 0:>14,.0f}  {_fecha(cuando):<18}{donde[:26]:<28}"
            f"{(archivo or '—')[:24]}{marca}"
        )

    if sospechosas:
        print(
            f"\nOJO: {len(sospechosas)} factura(s) quedaron de un cargue ANTERIOR del Excel "
            f"(el resto se actualizó el {_fecha(mas_reciente)}):"
        )
        for factura, cuando, donde in sospechosas:
            print(f"   {factura} — actualizada el {_fecha(cuando)} · en el sistema: {donde}")
        print(
            "\nCompare esa(s) factura(s) contra el DGH. Si facturación ya las sacó del\n"
            "envío, quítelas del oficio con el botón 🗑 de su fila (solo administradores).\n"
            "La fila de la fuente se corrige sola la próxima vez que esa factura venga\n"
            "en el Excel con su envío nuevo."
        )
    else:
        print("\nTodas las filas vienen del mismo cargue: no hay facturas rezagadas.")
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
