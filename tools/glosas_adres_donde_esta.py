"""¿En qué paquete(s) del ADRES está esta factura? — solo mira, no cambia nada.

POR QUÉ EXISTE (caso real 31-08-2026). Yesid buscó la HUS406687 teniendo
escogido arriba el paquete 31073 y la pantalla le contestó «no está en ningún
paquete cargado». Era mentira: la factura sí estaba cargada, pero en el paquete
31078. Con ese mensaje el auditor se queda creyendo que esa glosa nunca llegó.

La pantalla ya quedó corregida (ahora dice en qué paquete está y lleva allá),
pero este comando sirve para revisarlo desde el PC sin tocar nada, y además
muestra **renglón por renglón** lo que el ADRES glosó de esa factura en cada
paquete: es lo que responde la pregunta de si una factura viene glosada dos
veces o una sola.

USO EN EL PC DE CARTERA (PowerShell, desde C:\\motor-glosas\\repo):

    venv\\Scripts\\python.exe tools\\glosas_adres_donde_esta.py HUS406687

Sirve escribiéndola como sea: 406687, HUS406687 o HUS0000406687. Se pueden
pasar varias facturas seguidas.
"""

from __future__ import annotations

import os
import re
import sqlite3
import sys
from pathlib import Path


def clave_factura(texto) -> str:
    """La clave con la que el sistema guarda la factura: solo el número.

    Es la misma regla de `normalizar_factura` (tools/ajustar_detallado_glosas.py),
    que es la que usó el importador al cargar el paquete.
    """
    t = re.sub(r"\s+", "", str(texto or "")).upper()
    m = re.fullmatch(r"(?:HUS)?0*(\d{1,10})", t)
    return m.group(1) if m else t


def _ruta_base() -> str:
    env = os.environ.get("DATABASE_URL", "")
    if "sqlite:///" in env:
        return env.split("sqlite:///")[-1]
    return str(Path(__file__).resolve().parent.parent / "data" / "motorglosas.db")


def _pesos(valor) -> str:
    return f"${valor or 0:,.0f}".replace(",", ".")


def _clave_guardada(con: sqlite3.Connection, escrita: str) -> str:
    """La clave tal como quedó en la base, aunque se escriba distinto."""
    clave = clave_factura(escrita)
    fila = con.execute(
        "SELECT factura_clave FROM glosas_adres WHERE factura_clave=? LIMIT 1", (clave,)
    ).fetchone()
    if fila:
        return fila[0]
    # Por si el importador la guardó con otra forma (con HUS o con ceros).
    parecida = con.execute(
        "SELECT factura_clave FROM glosas_adres "
        "WHERE replace(replace(factura_clave,'HUS',''),' ','') LIKE ? LIMIT 1",
        (f"%{clave}",),
    ).fetchone()
    return parecida[0] if parecida else clave


def revisar(con: sqlite3.Connection, escrita: str, detalle: bool = True) -> None:
    clave = _clave_guardada(con, escrita)
    print("-" * 96)
    print(f"  {escrita}")

    paquetes = con.execute(
        """
        SELECT p.numero_paquete,
               g.paquete_id,
               COUNT(*)                                        AS renglones,
               SUM(CASE WHEN g.glosa_total THEN 1 ELSE 0 END)  AS totales,
               SUM(CASE WHEN g.cuenta_valor THEN g.valor_glosado ELSE 0 END) AS glosado,
               SUM(CASE WHEN COALESCE(g.decision,'')='' AND NOT g.glosa_total
                        THEN 1 ELSE 0 END)                     AS pendientes
          FROM glosas_adres g
          JOIN paquetes_adres p ON p.id = g.paquete_id
         WHERE g.factura_clave = ?
      GROUP BY g.paquete_id
      ORDER BY g.paquete_id DESC
        """,
        (clave,),
    ).fetchall()

    if not paquetes:
        print("    NO está en ningún paquete cargado del ADRES.")
        print("       → si el ADRES sí la glosó, falta cargar ese paquete en «Cargar paquete».")
        return

    if len(paquetes) > 1:
        print(f"    OJO: esta factura está glosada en {len(paquetes)} PAQUETES.")
        print("       Lo que se responda en uno NO cubre el otro: hay que trabajar los dos.")

    for numero, paquete_id, renglones, totales, glosado, pendientes in paquetes:
        a_responder = renglones - (totales or 0)
        print(
            f"    Paquete {numero or paquete_id}: {a_responder} glosa(s) a responder · "
            f"{_pesos(glosado)} glosado · {pendientes} sin decidir"
            + (f" · {totales} renglón(es) de GLOSA TOTAL" if totales else "")
        )
        if not detalle:
            continue
        filas = con.execute(
            """
            SELECT codigo, descripcion, causal_codigo, valor_glosado, cuenta_valor,
                   glosa_total, COALESCE(decision,''), COALESCE(centro_costos,'')
              FROM glosas_adres
             WHERE factura_clave = ? AND paquete_id = ?
          ORDER BY id
            """,
            (clave, paquete_id),
        ).fetchall()
        for cod, desc, causal, valor, cuenta, total, decision, centro in filas:
            marca = "  " if cuenta else " ·"  # «·» = su plata ya la contó otro renglón
            etiqueta = "GLOSA TOTAL" if total else (causal or "sin causal")
            print(
                f"      {marca} {etiqueta:<12} {(cod or '')[:16]:<16} "
                f"{_pesos(valor):>13}  {(decision or 'sin decidir'):<11} "
                f"{(desc or '')[:38]}"
            )
        if any(not f[4] for f in filas):
            print(
                "         («·» al principio = ese renglón no suma: es el mismo servicio "
                "glosado con otra causal.)"
            )


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
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
    print("=" * 96)
    print("  ¿EN QUÉ PAQUETE DEL ADRES ESTÁ ESTA FACTURA?")
    print(f"  Base: {ruta}")
    print("=" * 96)
    for escrita in args:
        revisar(con, escrita)
    print("\n" + "=" * 96)
    print(
        "  La pantalla de Glosas ADRES trabaja sobre el paquete escogido arriba. Si la factura\n"
        "  está en otro, ahora la propia pantalla lo dice y ofrece llevarlo allá."
    )
    con.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
