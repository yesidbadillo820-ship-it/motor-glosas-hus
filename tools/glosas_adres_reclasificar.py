"""Pone la clasificación que falta a las glosas del ADRES ya cargadas.

POR QUÉ EXISTE (caso real 02-09-2026). En el paquete 31073 las glosas con
causal 4302 quedaron «sin clasificar»: esa causal no salió en el paquete del
que se aprendió la tabla (el 31068) y el sistema, antes que inventar, las dejó
en blanco. Yesid confirmó que la 4302 es de TARIFAS y la tabla ya quedó
corregida — pero la clasificación se guarda al CARGAR el paquete, así que lo
ya cargado no se arregla solo. Este comando lo arregla sin tener que volver a
subir el Excel.

QUÉ HACE (y qué no):

  · Busca las glosas SIN clasificación cuya causal ya está en la tabla y les
    pone la clasificación de la tabla. A las que siguen sin decidir les pone
    también la sugerencia de esa familia (por ejemplo TARIFAS → SE OBJETA).
  · NO toca nada que ya tenga clasificación, ni lo decidido por el equipo,
    ni las causales que reparte un SUPER ADMIN (la 4506).
  · Primero muestra el ENSAYO (no cambia nada). Para aplicar de verdad hay
    que agregarle la palabra: aplicar.

USO EN EL PC DE CARTERA (PowerShell, desde C:\\motor-glosas\\repo):

    venv\\Scripts\\python.exe tools\\glosas_adres_reclasificar.py            ← ensayo
    venv\\Scripts\\python.exe tools\\glosas_adres_reclasificar.py aplicar    ← ya en serio
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from preauditar_glosas_adres import (  # noqa: E402
    CAUSALES_DE_DOS_AREAS,
    CLASIFICACION_POR_CAUSAL,
    sugerir,
)


def _ruta_base() -> str:
    env = os.environ.get("DATABASE_URL", "")
    if "sqlite:///" in env:
        return env.split("sqlite:///")[-1]
    return str(Path(__file__).resolve().parent.parent / "data" / "motorglosas.db")


def reclasificar(con: sqlite3.Connection, aplicar: bool = False) -> int:
    """Devuelve cuántas glosas se cambiaron (o se cambiarían, en el ensayo)."""
    filas = con.execute(
        """
        SELECT g.id, COALESCE(p.numero_paquete, g.paquete_id), g.causal_codigo,
               COALESCE(g.decision,''), COALESCE(g.confianza,''),
               COALESCE(g.requiere_asignacion,0), COALESCE(g.area_asignada_por,'')
          FROM glosas_adres g
     LEFT JOIN paquetes_adres p ON p.id = g.paquete_id
         WHERE COALESCE(g.clasificacion,'') = ''
           AND COALESCE(g.causal_codigo,'') <> ''
      ORDER BY g.paquete_id DESC, g.causal_codigo
        """
    ).fetchall()

    cambiadas = 0
    conteo: dict[tuple[str, str, str], int] = {}  # (paquete, causal, nueva) → n
    sin_arreglo: dict[str, int] = {}  # causal que sigue por fuera de la tabla → n
    for id_, paquete, causal, decision, confianza, reparte, asignada_por in filas:
        if causal in CAUSALES_DE_DOS_AREAS or reparte or asignada_por:
            continue  # esas las reparte un SUPER ADMIN, no un comando
        nueva = CLASIFICACION_POR_CAUSAL.get(causal, "")
        if not nueva:
            sin_arreglo[causal] = sin_arreglo.get(causal, 0) + 1
            continue
        conteo[(str(paquete), causal, nueva)] = conteo.get((str(paquete), causal, nueva), 0) + 1
        cambiadas += 1
        if not aplicar:
            continue
        con.execute("UPDATE glosas_adres SET clasificacion=? WHERE id=?", (nueva, id_))
        # La sugerencia solo se pone donde no hay ni decisión ni sugerencia:
        # lo que el equipo ya trabajó no se pisa.
        if not decision and not confianza:
            s, c, m = sugerir(nueva, causal)
            con.execute(
                "UPDATE glosas_adres SET sugerencia=?, confianza=?, motivo=? WHERE id=?",
                (s, c, m, id_),
            )

    if not conteo and not sin_arreglo:
        print("  No hay ninguna glosa sin clasificar. No hay nada que arreglar.")
        return 0

    for (paquete, causal, nueva), n in sorted(conteo.items()):
        print(f"  Paquete {paquete}: {n} glosa(s) con causal {causal} → {nueva}")
    for causal, n in sorted(sin_arreglo.items()):
        print(
            f"  OJO: {n} glosa(s) con causal {causal} siguen sin clasificar — "
            "esa causal no está en la tabla. Avisar para agregarla."
        )

    if aplicar:
        con.commit()
        print(f"\n  LISTO: se clasificaron {cambiadas} glosa(s).")
    else:
        print(
            f"\n  ENSAYO: se clasificarían {cambiadas} glosa(s). No se cambió nada.\n"
            "  Para aplicar de verdad:  "
            "venv\\Scripts\\python.exe tools\\glosas_adres_reclasificar.py aplicar"
        )
    return cambiadas


def main() -> int:
    args = [a for a in sys.argv[1:]]
    aplicar = any(a.lower() in ("aplicar", "--aplicar") for a in args)
    rutas = [a for a in args if a.lower().endswith(".db")]
    ruta = rutas[0] if rutas else _ruta_base()
    if not Path(ruta).exists():
        print(f"No se encontró la base de datos: {ruta}")
        return 1

    print("=" * 96)
    print("  CLASIFICAR LAS GLOSAS DEL ADRES QUE QUEDARON EN BLANCO")
    print(f"  Base: {ruta}" + ("" if aplicar else "   (modo ensayo: solo mira)"))
    print("=" * 96)
    # En el ensayo la base se abre en SOLO LECTURA: ni queriendo puede escribir.
    con = (
        sqlite3.connect(ruta, timeout=30)
        if aplicar
        else sqlite3.connect(f"file:{ruta}?mode=ro", uri=True, timeout=30)
    )
    try:
        reclasificar(con, aplicar=aplicar)
    finally:
        con.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
