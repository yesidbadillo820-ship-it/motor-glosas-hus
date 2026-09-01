"""¿Por qué esta factura sale sin facturación electrónica? — solo mira.

POR QUÉ EXISTE (caso real 26-08-2026). Tres facturas salían en la página con
«Correo F.E.: NO» teniendo facturación electrónica, y sin correo el sistema NO
DEJA RADICAR: el auditor queda obligado a devolver una factura que estaba bien.

El dato del correo no lo escribe nadie a mano: sale de cruzar la factura con el
**Formato de Facturación Electrónica** (el Excel del DGH que se sube en
«Fuentes»). Si la factura no está en ese archivo, o está escrita distinto
—«544942» en vez de «HUS0000544942»—, el cruce falla y la página la muestra
sin correo.

Este comando dice cuál de las dos cosas pasó, factura por factura, y no cambia
nada.

USO EN EL PC DE CARTERA (PowerShell, desde C:\\motor-glosas\\repo):

    venv\\Scripts\\python.exe tools\\preauditoria_revisar_fe.py HUS544942 HUS542599 HUS544936

Sirve escribiéndolas como sea: 544942, HUS544942 o HUS0000544942.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path


def canonizar(texto) -> str:
    """El número escrito en la forma larga: HUS + 10 dígitos."""
    t = re.sub(r"\s+", "", str(texto or "")).upper()
    m = re.fullmatch(r"(?:HUS)?0*(\d{1,10})", t)
    return "HUS" + m.group(1).zfill(10) if m else t


def _ruta_base() -> str:
    env = os.environ.get("DATABASE_URL", "")
    if "sqlite:///" in env:
        return env.split("sqlite:///")[-1]
    return str(Path(__file__).resolve().parent.parent / "data" / "motorglosas.db")


def _cuando(v) -> str:
    return str(v)[:16].replace("T", " ") if v else "—"


def revisar(con: sqlite3.Connection, escrita: str) -> None:
    factura = canonizar(escrita)
    print("-" * 92)
    encabezado = f"  {escrita}"
    if factura != escrita.upper().strip():
        encabezado += f"   (en el sistema se llama {factura})"
    print(encabezado)

    fe = con.execute(
        "SELECT correo_fe, fuente_archivo, actualizado_en, importado_en "
        "FROM preaud_fuente_dgreport WHERE factura=?",
        (factura,),
    ).fetchone()
    if fe:
        print(
            f"    FACTURACIÓN ELECTRÓNICA: SÍ está en el Formato F.E. "
            f"(archivo {fe[1] or '—'}, {_cuando(fe[2] or fe[3])})"
        )
    else:
        # ¿Estará guardada con otra forma de escribir el número?
        solo_numero = re.sub(r"\D", "", factura).lstrip("0")
        parecidas = con.execute(
            "SELECT factura, fuente_archivo FROM preaud_fuente_dgreport "
            "WHERE replace(replace(factura,'HUS',''),' ','') LIKE ? LIMIT 5",
            (f"%{solo_numero}",),
        ).fetchall()
        if parecidas:
            print("    FACTURACIÓN ELECTRÓNICA: está, pero con el número escrito DISTINTO:")
            for p in parecidas:
                print(f"       guardada como «{p[0]}» (archivo {p[1] or '—'})")
            print("       → suba otra vez el Formato F.E.: el sistema ya lo escribe igual.")
        else:
            print("    FACTURACIÓN ELECTRÓNICA: NO aparece en el Formato F.E. cargado.")
            print("       → baje del DGH el Formato F.E. actualizado y súbalo en «Fuentes».")

    rad = con.execute(
        "SELECT envio, valor, entidad, fuente_archivo, actualizado_en "
        "FROM preaud_fuente_radicacion WHERE factura=?",
        (factura,),
    ).fetchone()
    if rad:
        print(
            f"    RADICACIÓN: envío {rad[0]} · {rad[2] or '—'} · ${rad[1] or 0:,.0f} "
            f"(archivo {rad[3] or '—'}, {_cuando(rad[4])})".replace(",", ".")
        )
    else:
        print("    RADICACIÓN: no está en la fuente de Radicación de Cuentas.")

    canon = con.execute(
        "SELECT estado, oficio_fhus, envio_actual, auditor FROM preaud_facturas WHERE factura=?",
        (factura,),
    ).fetchone()
    if canon:
        print(
            f"    EN EL CONSOLIDADO: {canon[0]} · oficio {canon[1] or '—'} · "
            f"envío {canon[2] or '—'} · auditor {canon[3] or 'nadie todavía'}"
        )
    else:
        print("    EN EL CONSOLIDADO: todavía no está (no se ha escrito su envío).")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    args = sys.argv[1:]
    ruta = _ruta_base()
    if args[-1].lower().endswith(".db"):
        ruta = args.pop()
    if not args:
        print(__doc__)
        return 1
    if not Path(ruta).exists():
        print(f"No se encontró la base de datos: {ruta}")
        return 1

    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=30)
    print("=" * 92)
    print("  ¿POR QUÉ SALE SIN FACTURACIÓN ELECTRÓNICA?")
    print(f"  Base: {ruta}")
    print("=" * 92)
    for escrita in args:
        revisar(con, escrita)
    print("\n" + "=" * 92)
    print(
        "  El «Correo F.E.» no se escribe a mano: sale de cruzar la factura con el Formato de\n"
        "  Facturación Electrónica que se sube en «Fuentes». Sin ese cruce la página no deja\n"
        "  radicar, y por eso una factura buena termina devuelta."
    )
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
