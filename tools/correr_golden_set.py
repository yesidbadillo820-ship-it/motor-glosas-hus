"""Corre el golden set de calidad y muestra un reporte legible.

Uso:
    python tools/correr_golden_set.py

Útil para validar manualmente el pipeline determinista del motor tras un
cambio, sin necesidad de pytest. Sale con código 1 si hay fallos.
"""

from __future__ import annotations

import os
import sys

# Permitir correr standalone desde la raíz del repo (sys.path no incluye
# el cwd cuando se invoca como script).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    from tests.golden.evaluador import evaluar_todo

    r = evaluar_todo()
    print("═══ GOLDEN SET DE CALIDAD — Motor Glosas HUS ═══")
    print(
        f"Total criterios: {r['total_criterios']} · "
        f"Aprobados: {r['aprobados']} · Fallidos: {r['fallidos']}"
    )
    print()
    for caso_id, criterios in r["detalle_por_caso"].items():
        ok_caso = all(c["ok"] for c in criterios)
        icono = "✅" if ok_caso else "❌"
        print(f"{icono} {caso_id} ({sum(c['ok'] for c in criterios)}/{len(criterios)})")
        for c in criterios:
            if not c["ok"]:
                print(f"     ✗ {c['criterio']}: {c['detalle']}")
    print()
    if r["fallidos"] == 0:
        print("RESULTADO: ✅ TODOS LOS CRITERIOS DE CALIDAD PASAN")
        return 0
    print(f"RESULTADO: ❌ {r['fallidos']} CRITERIO(S) FALLARON")
    return 1


if __name__ == "__main__":
    sys.exit(main())
