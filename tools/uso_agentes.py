"""¿Cuánto se ha usado el Constructor de Agentes? — solo mira, no cambia nada.

19-08-2026. Yesid preguntó qué hace ese panel y cuánto se ha usado desde que
existe. Lo segundo no se podía responder mirando la pantalla: la ficha del
agente guarda quién la creó y cuándo, pero NO cuántas veces se ha corrido ni
cuándo fue la última. Eso solo queda en el registro de auditoría.

La base se abre en modo LECTURA: este programa no puede cambiar nada.
"""

import sqlite3, sys
from pathlib import Path

db = Path(r"C:\motor-glosas\repo\data\motorglosas.db")
if not db.exists():
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else db
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)

print("\n=== AGENTES CREADOS ===")
filas = con.execute(
    "SELECT id, nombre, creado_por, creado_en, activo FROM agentes ORDER BY id"
).fetchall()
if not filas:
    print("  Ninguno. Nadie ha creado un agente todavía.")
for i, n, quien, cuando, act in filas:
    print(
        f"  #{i}  {n:<40} por {quien or '?'}  {str(cuando)[:16]}  {'activo' if act else 'RETIRADO'}"
    )

print("\n=== VECES QUE SE HAN CORRIDO ===")
usos = con.execute(
    "SELECT accion, COUNT(*), MIN(timestamp), MAX(timestamp) FROM audit_log "
    "WHERE accion LIKE 'AGENTE_%' GROUP BY accion"
).fetchall()
if not usos:
    print("  Cero. El panel no se ha usado nunca.")
for a, n, pri, ult in usos:
    print(f"  {a:<18} {n:>4} vez(ces)   primera: {str(pri)[:16]}   última: {str(ult)[:16]}")

print("\n=== QUIÉN LOS HA CORRIDO ===")
for quien, n in con.execute(
    "SELECT usuario_email, COUNT(*) FROM audit_log WHERE accion='AGENTE_CORRIDO' "
    "GROUP BY usuario_email ORDER BY 2 DESC"
).fetchall():
    print(f"  {quien:<35} {n} corrida(s)")
con.close()
print()
