"""Gate de seguridad: falla si aparece una vulnerabilidad NUEVA.

**Por qué no simplemente «falle si hay alguna».** Hoy las dependencias
fijadas del motor arrastran 22 vulnerabilidades conocidas. Poner el gate en
cero dejaría el CI rojo de forma permanente y bloquearía todos los cambios,
incluidos los arreglos — y subir de golpe starlette, jinja2 y python-jose en
la aplicación que corre en el hospital es exactamente el cambio grande y
arriesgado que no se hace de afán.

**Por qué tampoco `|| true`.** Así estaba antes: el paso siempre terminaba
bien, dijera lo que dijera. Un escáner que nunca falla no es un gate, es un
adorno; el día que entrara una vulnerabilidad nueva y grave, nadie se
enteraría.

**Lo que hace este script.** Compara lo que encuentra contra
`seguridad/vulnerabilidades_conocidas.txt`, que es la lista revisada de lo
que ya se sabe y está pendiente de arreglar. Cualquier cosa fuera de esa
lista tumba el CI. Así el gate es de verdad desde hoy, y la deuda queda a la
vista en un archivo del repositorio en vez de escondida detrás de un
`|| true`.

Uso:
    python scripts/revisar_vulnerabilidades.py [requirements.txt]
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTA = os.path.join(RAIZ, "seguridad", "vulnerabilidades_conocidas.txt")


def conocidas() -> set[str]:
    """Los identificadores ya revisados, uno por línea. `#` es comentario."""
    if not os.path.exists(LISTA):
        return set()
    ids = set()
    with open(LISTA, encoding="utf-8") as f:
        for linea in f:
            linea = linea.split("#", 1)[0].strip()
            if linea:
                ids.add(linea.upper())
    return ids


def encontradas(requisitos: str) -> list[tuple[str, str, str, set[str]]]:
    """(paquete, versión, id, todos-sus-identificadores) de lo que reporta pip-audit.

    La misma vulnerabilidad tiene varios nombres: `PYSEC-2026-1471`,
    `CVE-2025-27516` y `GHSA-cpwx-vrp4-4pq7` son la misma. Cuál sale como
    principal depende de la versión de pip-audit y de la base de datos que
    consulte. Si solo se comparara el principal, una actualización de la
    herramienta pondría el CI en rojo con vulnerabilidades que ya estaban
    anotadas — y un gate que se pone rojo solo se acaba ignorando.
    """
    proc = subprocess.run(
        ["pip-audit", "-r", requisitos, "-f", "json"],
        capture_output=True,
        text=True,
        timeout=900,
    )
    salida = (proc.stdout or "").strip()
    if not salida:
        # pip-audit no pudo correr: eso NO se deja pasar como «todo bien».
        print("ERROR: pip-audit no devolvió nada.", file=sys.stderr)
        print((proc.stderr or "")[-2000:], file=sys.stderr)
        sys.exit(2)
    try:
        datos = json.loads(salida)
    except json.JSONDecodeError as e:
        print(f"ERROR: no se entendió la salida de pip-audit: {e}", file=sys.stderr)
        sys.exit(2)

    deps = datos.get("dependencies", []) if isinstance(datos, dict) else datos
    fuera = []
    for dep in deps:
        for vuln in dep.get("vulns", []) or []:
            ident = vuln.get("id", "?")
            nombres = {ident.upper()}
            nombres.update(str(a).upper() for a in (vuln.get("aliases") or []))
            fuera.append((dep.get("name", "?"), dep.get("version", "?"), ident, nombres))
    return fuera


def main(argv: list[str]) -> int:
    requisitos = argv[1] if len(argv) > 1 else os.path.join(RAIZ, "requirements.txt")
    ya_sabidas = conocidas()
    todas = encontradas(requisitos)

    # Una vulnerabilidad es «conocida» si CUALQUIERA de sus nombres está en
    # la lista: así da igual con cuál la reporte la herramienta.
    nuevas = sorted({(p, v, i) for p, v, i, nombres in todas if not (nombres & ya_sabidas)})
    vigentes = set()
    for _, _, _, nombres in todas:
        vigentes |= nombres

    print(f"Vulnerabilidades encontradas: {len(todas)}")
    print(f"Ya revisadas y anotadas:      {len(ya_sabidas)}")

    # Las que se anotaron y ya no aparecen: se puede limpiar la lista. No es
    # un fallo, pero sí un aviso — una lista que crece y nunca se poda
    # termina tapando cosas de verdad.
    resueltas = sorted(ya_sabidas - vigentes)
    if resueltas:
        print("\nYa no aparecen (se pueden quitar de la lista):")
        for i in resueltas:
            print(f"   · {i}")

    if not nuevas:
        print("\nSin vulnerabilidades nuevas. Gate en verde.")
        return 0

    print(f"\n{len(nuevas)} VULNERABILIDAD(ES) NUEVA(S) — el CI se detiene acá:\n")
    for paquete, version, ident in nuevas:
        print(f"   · {paquete} {version} — {ident}")
    print(
        "\nQué hacer:\n"
        "  1. Si se puede subir la versión del paquete, súbala en requirements.txt.\n"
        "  2. Si no se puede todavía, revise el impacto real y agregue el\n"
        f"     identificador a {os.path.relpath(LISTA, RAIZ)} con la fecha y\n"
        "     el motivo. Anotarla sin mirarla es lo mismo que no tener gate."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
