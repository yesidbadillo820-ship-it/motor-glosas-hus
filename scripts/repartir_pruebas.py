#!/usr/bin/env python3
"""Reparte los archivos de prueba entre las máquinas del CI, por DURACIÓN.

POR QUÉ EXISTE (10-09-2026). «Tengo que esperar hasta 15 minutos que un PR
pase una validación» (Yesid). Se bajó a tres máquinas, y ahí se atascó en
unos 5 minutos por una razón concreta: el reparto era por NOMBRE de archivo
—los impares a un grupo, los pares al otro— y los archivos no duran lo mismo.
Medido en el CI de verdad:

    api-1 ....... 2 min 34 s
    api-2 ....... 3 min 51 s
    resto ....... 4 min 46 s   ← este marcaba el reloj

Un grupo terminaba y se quedaba mirando a los otros dos. El reloj lo marca el
más lento, no el promedio, así que la mitad del tiempo comprado se perdía.

CÓMO SE REPARTE AHORA. Con lo que cada archivo TARDA de verdad, medido y
guardado en `tests/duraciones_pruebas.json`. Se reparte de mayor a menor: el
archivo más pesado se le da a la máquina que va más liviana. Es el reparto
goloso de toda la vida y para esto alcanza de sobra — con las mediciones de
hoy deja las cuatro máquinas dentro de un 1 % una de otra.

Es DETERMINISTA: la misma lista sale siempre, así que un fallo se reproduce
corriendo ese grupo. Y no hay archivo que se quede sin correr ni que corra
dos veces: `tests/test_ci/test_reparto_de_pruebas.py` lo comprueba archivo
por archivo en cada corrida.

Un archivo nuevo que todavía no está medido entra igual, con la duración
MEDIANA de los demás. No se queda por fuera nunca: preferimos una máquina un
poco desbalanceada a una prueba que no corre y nadie nota.

CÓMO SE USA:

    python scripts/repartir_pruebas.py --grupos 4 --grupo 2   # los archivos
    python scripts/repartir_pruebas.py --resumen              # ver el reparto

CÓMO SE ACTUALIZAN LAS MEDICIONES (cuando el reparto se desbalancee):

    python -m pytest tests --junitxml=junit.xml
    python scripts/repartir_pruebas.py --medir junit.xml

También sirve con los `junit.xml` que el propio CI guarda como artefactos de
cada grupo: se le pueden pasar varios y los junta.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CARPETA_PRUEBAS = RAIZ / "tests"
ARCHIVO_DURACIONES = CARPETA_PRUEBAS / "duraciones_pruebas.json"


def archivos_de_prueba(raiz: Path | None = None) -> list[str]:
    """Todos los archivos que pytest recogería, en orden y como rutas del repo.

    Se buscan con el mismo patrón que `pytest.ini` (`python_files = test_*.py`),
    así que una carpeta nueva de pruebas entra sola en el reparto en vez de
    quedarse sin correr en silencio.
    """
    base = raiz or RAIZ
    carpeta = base / "tests"
    return sorted(
        p.relative_to(base).as_posix()
        for p in carpeta.rglob("test_*.py")
        if "__pycache__" not in p.parts
    )


def duraciones_medidas(archivo: Path | None = None) -> dict[str, float]:
    """Lo que tardó cada archivo la última vez que se midió. `{}` si no hay."""
    ruta = archivo or ARCHIVO_DURACIONES
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): float(v) for k, v in datos.items() if isinstance(v, (int, float))}


def repartir(archivos: list[str], grupos: int, pesos: dict[str, float]) -> list[list[str]]:
    """Reparte en `grupos` listas, dándole el más pesado al que va más liviano.

    Determinista: ante dos máquinas igual de cargadas gana siempre la de menor
    número, y los archivos de igual peso se ordenan por ruta.
    """
    if grupos < 1:
        raise ValueError("hacen falta al menos 1 grupo")
    conocidos = [pesos[a] for a in archivos if a in pesos]
    # Un archivo sin medir vale lo que la mediana: ni se le teme ni se le
    # ignora. Sin mediciones ninguna, todos pesan igual y el reparto queda
    # por cantidad, que es exactamente lo que había antes.
    por_defecto = statistics.median(conocidos) if conocidos else 1.0

    repartidos: list[list[str]] = [[] for _ in range(grupos)]
    carga = [0.0] * grupos
    for archivo in sorted(archivos, key=lambda a: (-pesos.get(a, por_defecto), a)):
        i = min(range(grupos), key=lambda k: (carga[k], k))
        repartidos[i].append(archivo)
        carga[i] += pesos.get(archivo, por_defecto)
    return [sorted(g) for g in repartidos]


def _medir(entradas: list[str]) -> int:
    """Relee uno o varios junit.xml y reescribe el archivo de duraciones."""
    segundos: dict[str, float] = {}
    for entrada in entradas:
        raiz = ET.parse(entrada).getroot()
        for caso in raiz.iter("testcase"):
            partes = (caso.get("classname") or "").split(".")
            modulo = next((p for p in reversed(partes) if p.startswith("test_")), None)
            if not modulo:
                continue
            ruta = "/".join(partes[: partes.index(modulo) + 1]) + ".py"
            segundos[ruta] = round(segundos.get(ruta, 0.0) + float(caso.get("time") or 0.0), 2)
    if not segundos:
        print("No se pudo leer ninguna duración de esos archivos.", file=sys.stderr)
        return 1
    ARCHIVO_DURACIONES.write_text(
        json.dumps(dict(sorted(segundos.items())), indent=0, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Guardadas {len(segundos)} duraciones en {ARCHIVO_DURACIONES.relative_to(RAIZ)}")
    return 0


def _resumen(grupos: int) -> int:
    archivos = archivos_de_prueba()
    pesos = duraciones_medidas()
    sin_medir = [a for a in archivos if a not in pesos]
    conocidos = [pesos[a] for a in archivos if a in pesos]
    por_defecto = statistics.median(conocidos) if conocidos else 1.0
    print(f"  {len(archivos)} archivos · {len(sin_medir)} sin medir (valen {por_defecto:.2f}s)")
    for i, grupo in enumerate(repartir(archivos, grupos, pesos), start=1):
        total = sum(pesos.get(a, por_defecto) for a in grupo)
        print(f"  grupo {i}: {len(grupo):>4} archivos · {total:7.1f}s de procesador")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--grupos", type=int, default=4, help="en cuántas máquinas se reparte")
    ap.add_argument("--grupo", type=int, help="cuál de ellas imprimir (empieza en 1)")
    ap.add_argument("--resumen", action="store_true", help="ver el reparto completo")
    ap.add_argument("--medir", nargs="+", metavar="JUNIT", help="rehacer las mediciones")
    args = ap.parse_args(argv)

    if args.medir:
        return _medir(args.medir)
    if args.resumen or args.grupo is None:
        return _resumen(args.grupos)
    if not 1 <= args.grupo <= args.grupos:
        print(f"El grupo {args.grupo} no existe: van de 1 a {args.grupos}.", file=sys.stderr)
        return 2

    reparto = repartir(archivos_de_prueba(), args.grupos, duraciones_medidas())
    elegido = reparto[args.grupo - 1]
    if not elegido:
        print(
            f"El grupo {args.grupo} se quedó sin archivos que correr. "
            "Eso es un error de reparto, no un éxito.",
            file=sys.stderr,
        )
        return 1
    print("\n".join(elegido))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
