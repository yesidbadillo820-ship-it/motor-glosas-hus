"""¿Lo que dice este Excel ya está en el sistema? — compara y NO cambia nada.

POR QUÉ EXISTE (caso real 20-08-2026). El equipo trabaja con actas y hojas de
Excel por oficio (las 14 facturas del FHUS-AS-I01162-26, por ejemplo) y a la
vez audita en la página. Antes de volver a importar nada hay que saber qué
sabe ya el sistema: si una decisión del Excel ya está registrada, importarla
otra vez no aporta; y si NO está, lo correcto casi siempre es auditarla en la
página (el sistema manda), no meterla por detrás.

Este comando abre la base en SOLO LECTURA y dice, factura por factura, qué
dice el Excel y qué dice el sistema, con una de estas marcas:

  AL DÍA     lo del Excel ya está igual en el sistema.
  ADELANTE   el sistema ya sabe eso y además avanzó (por ejemplo: el Excel la
             muestra devuelta y en la página ya reingresó a otro oficio).
  FALTA      el sistema todavía no tiene esa decisión.
  DIFERENTE  el Excel y el sistema se contradicen: hay que revisarlo a mano.
  NO ESTÁ    esa factura no existe en el sistema.

USO EN EL PC DE CARTERA (PowerShell, desde C:\\motor-glosas\\repo):

    venv\\Scripts\\python.exe tools\\preauditoria_comparar_acta.py "D:\\USUARIO CARTERA\\Downloads\\FHUS-AS-I01162-26.xlsx"

Sirve con el Excel clásico del equipo (18 columnas) y con el consolidado
ADRES: los lee el mismo lector que usa el importador.
"""

from __future__ import annotations

import importlib.util
import os
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _lector():
    """El lector de Excel del importador, sin duplicar esa lógica aquí."""
    ruta = RAIZ / "preauditoria_importar_consolidado.py"
    spec = importlib.util.spec_from_file_location("preauditoria_importar_consolidado", ruta)
    mod = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("preauditoria_importar_consolidado", mod)
    spec.loader.exec_module(mod)
    return mod


def _ruta_base() -> str:
    env = os.environ.get("DATABASE_URL", "")
    if "sqlite:///" in env:
        return env.split("sqlite:///")[-1]
    return str(RAIZ.parent / "data" / "motorglosas.db")


def _fecha(v) -> str:
    return v.strftime("%d/%m/%Y") if hasattr(v, "strftime") else "—"


# El estado interno, dicho como lo diría el auditor.
EN_PALABRAS = {
    "NUEVA": "sin decidir",
    "RADICADA": "radicada",
    "DEVUELTA_PEND_SUBSANACION": "devuelta",
    "EN_SUBSANACION": "reingresó, sin decidir",
    "SUBSANADA": "radicada tras subsanar",
    "NUEVAMENTE_DEVUELTA": "devuelta otra vez",
    "BLOQUEADA_LIMITE": "bloqueada (3 devoluciones)",
}


def _estado_sistema(con: sqlite3.Connection, factura: str) -> dict | None:
    fila = con.execute(
        "SELECT estado, resultado_actual, num_devoluciones, ronda_actual, "
        "oficio_fhus, envio_actual, auditor FROM preaud_facturas WHERE factura=?",
        (factura,),
    ).fetchone()
    if fila is None:
        return None
    return {
        "estado": fila[0],
        "resultado": fila[1],
        "num_dev": fila[2] or 0,
        "ronda": fila[3] or 1,
        "oficio": fila[4],
        "envio": fila[5],
        "auditor": fila[6],
    }


def _en_palabras(estado: str) -> str:
    return EN_PALABRAS.get(estado, (estado or "—").lower())


def veredicto(excel_res: str, hubo_dev: bool, sis: dict | None) -> tuple[str, str]:
    """La marca y la frase que explica qué hacer con esa factura."""
    if sis is None:
        return "NO ESTÁ", "no existe en el sistema: escriba su envío en el oficio que la trajo."
    res = sis["resultado"]
    if excel_res == "DEVUELTA":
        if res == "DEVUELTA":
            return "AL DÍA", ""
        if sis["num_dev"] >= 1:
            return (
                "ADELANTE",
                f"el sistema ya la devolvió y siguió: hoy está {_en_palabras(sis['estado'])}"
                f" en {sis['oficio'] or 'otro oficio'}.",
            )
        return "FALTA", "el sistema no tiene registrada esa devolución: devuélvala en la página."
    if excel_res == "RADICAR":
        if res == "RADICAR":
            return "AL DÍA", ""
        if res == "DEVUELTA":
            return "DIFERENTE", "el Excel dice radicar y el sistema la tiene devuelta: revísela."
        return "FALTA", "el sistema la tiene sin decidir: radíquela en la página."
    # El Excel todavía no decide nada.
    if res == "PENDIENTE" and sis["num_dev"] == 0:
        return "AL DÍA", ""
    return "ADELANTE", f"el sistema ya avanzó: hoy está {_en_palabras(sis['estado'])}."


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    ruta_excel = sys.argv[1]
    ruta_db = sys.argv[2] if len(sys.argv) > 2 else _ruta_base()
    if not Path(ruta_excel).exists():
        print(f"No se encontró el Excel: {ruta_excel}")
        return 1
    if not Path(ruta_db).exists():
        print(f"No se encontró la base de datos: {ruta_db}")
        return 1

    pasadas, avisos = _lector().leer_excel(ruta_excel)
    con = sqlite3.connect(f"file:{ruta_db}?mode=ro", uri=True, timeout=30)

    print("=" * 100)
    print(f"  ¿YA ESTÁ EN EL SISTEMA? — {Path(ruta_excel).name}")
    print(f"  Base: {ruta_db}")
    print("=" * 100)
    if not pasadas:
        print("\nEl Excel no trae ninguna fila de factura (columna FACTURA con HUS…).")
        con.close()
        return 0
    for a in avisos[:10]:
        print(f"  AVISO: {a}")

    print(f"\n{len(pasadas)} fila(s) de factura en el Excel:\n")
    print(f"  {'FACTURA':<16}{'ENVÍO':<9}{'EL EXCEL DICE':<24}{'EL SISTEMA DICE':<46}MARCA")
    cuenta: dict[str, int] = {}
    pendientes: list[tuple[str, str, str]] = []
    for p in pasadas:
        sis = _estado_sistema(con, p.factura)
        marca, que_hacer = veredicto(p.resultado_final, p.hubo_devolucion, sis)
        cuenta[marca] = cuenta.get(marca, 0) + 1
        dice_excel = p.resultado_final
        if p.resultado_final == "DEVUELTA" and p.f_dev is not None:
            dice_excel = f"DEVUELTA {_fecha(p.f_dev)}"
        dice_sis = (
            f"{_en_palabras(sis['estado'])} en {sis['oficio'] or '—'}"
            if sis
            else "no está en el consolidado"
        )
        print(f"  {p.factura:<16}{(p.envio or '—'):<9}{dice_excel:<24}{dice_sis[:44]:<46}{marca}")
        if marca in ("FALTA", "DIFERENTE", "NO ESTÁ"):
            pendientes.append((p.factura, marca, que_hacer))

    print("\nRESUMEN")
    for marca in ("AL DÍA", "ADELANTE", "FALTA", "DIFERENTE", "NO ESTÁ"):
        if cuenta.get(marca):
            print(f"  {cuenta[marca]:>4}  {marca}")
    if not pendientes:
        print("\nTodo lo que dice este Excel ya está en el sistema: no hay nada que cargar.")
    else:
        print(f"\n{len(pendientes)} factura(s) piden acción:")
        for factura, marca, que_hacer in pendientes:
            print(f"   {factura} — {marca}: {que_hacer}")
        print(
            "\nLo normal es resolverlas EN LA PÁGINA (botón Auditar del consolidado o del\n"
            "oficio): así queda el auditor, la fecha y el historial. Volver a importar el\n"
            "Excel solo sirve para historia vieja que nadie tocó en la página."
        )
    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
