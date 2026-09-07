"""Programa de consola del curso de noruego.

Sirve para tres cosas: revisar que el contenido esté bien, ver qué trae el
curso y generar la aplicación web.

    python -m noruego revisar         # valida el léxico y el curso
    python -m noruego curso           # muestra módulos y lecciones
    python -m noruego leccion s1      # muestra los ejercicios de una lección
    python -m noruego exportar        # genera la aplicación web
    python -m noruego direccion       # el enlace para abrirla en el celular
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

from .curso import MODULOS, buscar_leccion, todas_las_lecciones
from .ejercicios import generar, material
from .exportar_web import exportar
from .lexico import cargar, revisar
from .red import PUERTO_POR_DEFECTO, enlace_de_esta_maquina

Salida = Callable[[str], None]

#: Donde se genera la aplicación por defecto: dentro de `static/`, que la
#: aplicación del hospital ya sirve por HTTP. Así queda accesible desde el
#: celular sin montar nada nuevo.
DESTINO_POR_DEFECTO = Path("static/noruego")

#: Una lección con menos ejercicios que esto no alcanza para enseñar nada.
MINIMO_EJERCICIOS = 6


def cmd_revisar(args, salida: Salida) -> int:
    lx = cargar()
    salida(lx.resumen())
    salida("")
    avisos = revisar(lx)
    problemas = 0

    salida("LECCIONES")
    for modulo, leccion, _ in todas_las_lecciones():
        ejercicios = generar(lx, leccion, semilla=0)
        marca = "  " if len(ejercicios) >= MINIMO_EJERCICIOS else "!!"
        if marca == "!!":
            problemas += 1
        if args.detalle or marca == "!!":
            salida(
                f"{marca} {modulo.clave}/{leccion.clave:<6} {len(ejercicios):>3} ejercicios"
                f"  ({len(material(lx, leccion))} elementos de material)"
            )
    salida(f"   {len(todas_las_lecciones())} lecciones · {len(MODULOS)} módulos")
    salida("")
    if avisos:
        salida(f"AVISOS DEL LÉXICO: {len(avisos)}")
        for aviso in avisos:
            salida(f"  · {aviso}")
    else:
        salida("AVISOS DEL LÉXICO: ninguno.")
    if problemas:
        salida(f"\n{problemas} lecciones no llegan a {MINIMO_EJERCICIOS} ejercicios.")
    return 1 if (problemas or avisos) else 0


def cmd_curso(args, salida: Salida) -> int:
    lx = cargar()
    for modulo in MODULOS:
        salida(f"\n{modulo.icono}  {modulo.titulo}  [{modulo.nivel.value}]")
        salida(f"    {modulo.descripcion}")
        for leccion in modulo.lecciones:
            cuantos = len(generar(lx, leccion, semilla=0))
            salida(f"    · {leccion.clave:<7}{leccion.titulo:<38}{cuantos:>3} ejercicios")
    return 0


def cmd_leccion(args, salida: Salida) -> int:
    encontrada = buscar_leccion(args.clave)
    if not encontrada:
        raise SystemExit(f"No existe la lección «{args.clave}». Usa «python -m noruego curso».")
    modulo, leccion = encontrada
    lx = cargar()
    salida(f"{modulo.titulo} · {leccion.titulo}")
    salida(f"Objetivo: {leccion.objetivo}\n")
    for numero, ejercicio in enumerate(generar(lx, leccion, semilla=args.semilla), 1):
        salida(f"{numero:>3}. [{ejercicio.tipo.value}] {ejercicio.enunciado}")
        if ejercicio.contexto:
            salida(f"     {ejercicio.contexto}")
        if ejercicio.opciones:
            for indice, opcion in enumerate(ejercicio.opciones):
                marca = "✓" if indice == ejercicio.correcta else " "
                salida(f"       {marca} {opcion}")
        if ejercicio.respuesta:
            salida(f"       → {ejercicio.respuesta}")
        if ejercicio.orden:
            salida(f"       → {' '.join(ejercicio.orden)}")
    return 0


def cmd_exportar(args, salida: Salida) -> int:
    destino = Path(args.salida)
    indice = exportar(destino)
    peso = sum(f.stat().st_size for f in destino.iterdir() if f.is_file()) / 1024
    salida(f"Aplicación generada en: {destino}/")
    salida(f"Archivos: {', '.join(sorted(f.name for f in destino.iterdir()))}")
    salida(f"Tamaño total: {peso:.0f} KB")
    salida("")
    salida("Para abrirla en el celular:")
    salida("  1. Levanta el servidor:  uvicorn app.main:app --host 0.0.0.0 --port 8000")
    salida("  2. En el celular, en la misma red wifi, abre:")
    url = enlace_de_esta_maquina()
    if url:
        salida(f"       {url}")
    else:
        salida("       http://LA-IP-DE-ESTE-PC:8000/static/noruego/index.html")
        salida("       (no se pudo leer la IP; mírala con «python -m noruego direccion»)")
    salida("  3. En el menú del navegador del CELULAR, «Agregar a la pantalla de inicio».")
    salida("")
    salida(f"También funciona con doble clic en {indice} (sin instalación ni caché).")
    return 0


def cmd_direccion(args, salida: Salida) -> int:
    """Imprime SOLO el enlace, para que el bot de Windows lo capture tal cual."""
    url = enlace_de_esta_maquina(args.puerto)
    if url is None:
        return 1
    salida(url)
    return 0


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="noruego", description="Curso de noruego para hispanohablantes."
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("revisar", help="Validar el léxico y el curso.")
    p.add_argument("--detalle", action="store_true", help="Mostrar todas las lecciones.")

    sub.add_parser("curso", help="Ver los módulos y las lecciones.")

    p = sub.add_parser("leccion", help="Ver los ejercicios de una lección.")
    p.add_argument("clave", help="Clave de la lección (por ejemplo: s1, g3, n2).")
    p.add_argument("--semilla", type=int, default=0, help="Variante a generar.")

    p = sub.add_parser("exportar", help="Generar la aplicación web.")
    p.add_argument("--salida", default=str(DESTINO_POR_DEFECTO), help="Carpeta de destino.")

    p = sub.add_parser("direccion", help="El enlace para abrir la app en el celular.")
    p.add_argument("--puerto", type=int, default=PUERTO_POR_DEFECTO, help="Puerto del servidor.")
    return parser


def main(argv: Sequence[str] | None = None, salida: Salida = print) -> int:
    args = construir_parser().parse_args(argv)
    return {
        "revisar": cmd_revisar,
        "curso": cmd_curso,
        "leccion": cmd_leccion,
        "exportar": cmd_exportar,
        "direccion": cmd_direccion,
    }[args.comando](args, salida)
