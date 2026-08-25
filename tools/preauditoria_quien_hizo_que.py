"""¿Quién hizo qué en este oficio (o en este envío)? — solo mira, no cambia nada.

POR QUÉ EXISTE (25-08-2026). Yesid: «algunos envíos que recepciona y gestiona
la gestora Vanesa quedan como si hubieran sido del gestor Óscar». El sistema
guarda el nombre de la persona en TRES momentos distintos y por caminos
distintos:

  1. quién REGISTRÓ el oficio            → preaud_oficios_recepcion.creado_por
  2. quién ESCRIBIÓ cada envío           → preaud_envios_cargados.cargado_por
  3. quién AUDITÓ cada factura           → preaud_facturas.auditor
     (y, renglón por renglón, quién hizo cada movimiento en el historial)

En los tres casos el nombre sale de la SESIÓN abierta en el navegador, no de
quién esté sentado al computador. Si dos gestores comparten el mismo equipo y
no cierran sesión, todo lo que haga el segundo queda a nombre del primero.
El otro camino posible: las facturas que entraron por importación del Excel
llevan el auditor que decía el Excel (columna AUDITOR), no quien las tocó.

Este comando pone los tres datos uno al lado del otro, con fecha y hora, para
saber cuál de los dos fue.

USO EN EL PC DE CARTERA (PowerShell, desde C:\\motor-glosas\\repo):

    venv\\Scripts\\python.exe tools\\preauditoria_quien_hizo_que.py FHUS-AS-I01197-26
    venv\\Scripts\\python.exe tools\\preauditoria_quien_hizo_que.py 232050
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


def _cuando(v) -> str:
    return str(v)[:16].replace("T", " ") if v else "—"


MARCA_IMPORT = "importacion-historica-excel"


def _oficios_del_envio(con: sqlite3.Connection, envio: str) -> list:
    return [
        r[0]
        for r in con.execute(
            "SELECT DISTINCT oficio_id FROM preaud_envios_cargados WHERE envio=?", (envio,)
        )
        if r[0]
    ]


def informe_oficio(con: sqlite3.Connection, oficio_id: int, solo_envio: str = None) -> None:
    o = con.execute(
        "SELECT numero_radicado, fecha_recibido, creado_por, creado_en "
        "FROM preaud_oficios_recepcion WHERE id=?",
        (oficio_id,),
    ).fetchone()
    if not o:
        print(f"  (el oficio {oficio_id} ya no existe)")
        return
    print("-" * 96)
    print(f"  OFICIO {o[0]}   recibido: {_cuando(o[1])}")
    print(f"    LO REGISTRÓ:  {o[2] or '—'}   ({_cuando(o[3])})")

    envios = con.execute(
        "SELECT envio, cargado_por, cargado_en, total_facturas, nuevas, reingresos "
        "FROM preaud_envios_cargados WHERE oficio_id=? ORDER BY cargado_en, envio",
        (oficio_id,),
    ).fetchall()
    print("\n    ENVÍOS ESCRITOS:")
    if not envios:
        print("      (ninguno)")
    for envio, quien, cuando, total, nuevas, reing in envios:
        if solo_envio and envio != solo_envio:
            continue
        print(
            f"      {envio:<10} lo escribió {(quien or '—')[:28]:<30}{_cuando(cuando):<18}"
            f"{total} factura(s) · {nuevas} nuevas · {reing} reingresos"
        )

    facturas = con.execute(
        "SELECT factura, envio_actual, estado, auditor, fecha_auditoria, creado_por "
        "FROM preaud_facturas WHERE oficio_actual_id=? ORDER BY envio_actual, factura",
        (oficio_id,),
    ).fetchall()
    print("\n    FACTURAS QUE ESTÁN HOY EN EL OFICIO:")
    if not facturas:
        print("      (ninguna)")
    for factura, envio, estado, auditor, cuando, creada_por in facturas:
        if solo_envio and envio != solo_envio:
            continue
        origen = " [vino del Excel]" if creada_por == MARCA_IMPORT else ""
        print(
            f"      {factura:<18}{(envio or '—'):<10}{estado:<26}"
            f"la auditó {(auditor or 'nadie todavía')[:24]:<26}{_cuando(cuando)}{origen}"
        )

    eventos = con.execute(
        "SELECT e.creado_en, e.tipo_evento, e.factura, e.creado_por, e.auditor "
        "FROM preaud_factura_eventos e WHERE e.oficio_id=? "
        "ORDER BY e.creado_en, e.id",
        (oficio_id,),
    ).fetchall()
    print("\n    RENGLÓN POR RENGLÓN (lo que quedó grabado, en orden):")
    if not eventos:
        print("      (sin movimientos)")
    for cuando, tipo, factura, quien, auditor in eventos:
        firma = quien or auditor or "—"
        marca = "  <-- lo trajo la importación del Excel" if quien == MARCA_IMPORT else ""
        print(f"      {_cuando(cuando):<18}{tipo:<22}{factura:<18}{firma[:28]}{marca}")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    buscado = sys.argv[1].strip()
    ruta = sys.argv[2] if len(sys.argv) > 2 else _ruta_base()
    if not Path(ruta).exists():
        print(f"No se encontró la base de datos: {ruta}")
        return 1

    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=30)
    print("=" * 96)
    print(f"  ¿QUIÉN HIZO QUÉ? — {buscado}")
    print(f"  Base: {ruta}")
    print("=" * 96)

    fila = con.execute(
        "SELECT id FROM preaud_oficios_recepcion WHERE numero_radicado=?", (buscado,)
    ).fetchone()
    if fila:
        informe_oficio(con, fila[0])
    else:
        oficios = _oficios_del_envio(con, buscado)
        if not oficios:
            print(
                f"\nNo hay ningún oficio con el radicado {buscado} ni ningún envío con ese "
                "número escrito en un oficio.\nRevise el número tal como aparece en la página."
            )
            con.close()
            return 0
        print(f"\nEl envío {buscado} se escribió en {len(oficios)} oficio(s):\n")
        for oficio_id in oficios:
            informe_oficio(con, oficio_id, solo_envio=buscado)

    print("\n" + "=" * 96)
    print(
        "  CÓMO LEERLO: el nombre sale de la SESIÓN abierta en el navegador, no de quién\n"
        "  esté sentado al computador. Si aquí aparece una persona distinta a la que hizo\n"
        "  el trabajo, es que ese computador tenía abierta la sesión de la otra: cada\n"
        "  gestor debe entrar con su propio usuario y cerrar sesión al terminar.\n"
        "  Las líneas marcadas «lo trajo la importación del Excel» llevan el nombre que\n"
        "  decía la columna AUDITOR del Excel, no el de quien las tocó en la página."
    )
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
