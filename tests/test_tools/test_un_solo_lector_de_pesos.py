"""Nadie vuelve a escribir su propio lector de pesos.

POR QUÉ EXISTE ESTA PRUEBA. En `tools/` llegaron a convivir **diez** copias
de la misma regla —cómo se lee "$ 950.000" en un archivo de un pagador— y
**cuatro de las diez estaban mal**:

    savia._num                        "1.365,50"  → 136.550     ×100
    completar_tramite_glosas_aceptadas "1.234.567" → 0          leía cero
    convertir_tramite_masivo._num      "1.234.567" → 0          leía cero
    generar_acta_conciliacion.num      "$ 950.000" → 950,00     ÷1000
    hoja_maestra_conciliacion._num     "$ 950.000" → 950,00     ÷1000
    explorador_radicacion._parse_valor "$ 950.000" → 950,00     ÷1000

Esos números salían en el Excel que se carga al ERP, en el acta de
conciliación y en el informe de gerencia. No aparecieron por descuido:
aparecieron porque **nada lo impedía**. Cada herramienta nueva resolvía el
problema otra vez, y quien la escribía no tenía forma de saber que ya estaba
resuelto.

Arreglar las diez sin poner esta guardia habría durado hasta la herramienta
número once.

QUÉ HACE. Recorre `tools/` y busca funciones que parezcan un lector de pesos
—que manipulen separadores decimales y produzcan un número—. Si encuentra una
fuera de `_dinero.py`, falla y dice cuál.

QUÉ HACER SI ESTA PRUEBA FALLA. No agregue el archivo a la lista de abajo:
use `from _dinero import a_numero` (o `a_entero`). La lista es para funciones
que **formatean** pesos para mostrarlos, no para leerlos.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"

# El único lugar donde puede vivir la regla.
_DUENO = "_dinero.py"

# Funciones que tocan separadores pero NO leen pesos: dan formato para mostrar,
# escriben celdas o parsean otra cosa. Cada excepción va con su motivo.
_PERMITIDAS: dict[str, str] = {
    "tools/suite_cartera_hus/suite_cartera_hus.py::_fmt_pesos": (
        "formatea para mostrar en pantalla; no lee"
    ),
    "tools/suite_cartera_hus/nucleo/cruces_dgh.py::consolidar": (
        "arma el consolidado; el valor ya viene leído por a_numero"
    ),
    "tools/suite_cartera_hus/nucleo/cruces_dgh.py::generar_objeciones": (
        "escribe el archivo de salida; el valor ya viene leído"
    ),
    "tools/tablero_cartera.py::_parse_valor": (
        "ya delega en el parser del núcleo con respaldo local documentado"
    ),
    "tools/txt_a_excel.py::valor_celda": (
        "decide el tipo de celda de Excel; protege el texto de facturación"
    ),
    "tools/responder_glosas_simed.py::leer_excel_respuestas": (
        "lee la columna de respuesta, que es texto libre"
    ),
    # ── Extracción desde texto libre: otro problema ──────────────────────
    # Estas no leen una celda: barren un PDF o un correo buscando cifras con
    # una expresión regular. Aplican la misma regla de los tres dígitos, pero
    # el trabajo es distinto (encontrar montos, no convertir uno conocido) y
    # devuelven un conjunto, no un valor.
    "tools/adres/validar_furips.py::extraer_montos": (
        "barre el texto del FURIPS buscando montos; devuelve un conjunto"
    ),
    "tools/generar_informe_baja_cartera.py::extraer_montos": (
        "barre el texto del informe buscando montos; devuelve una lista"
    ),
    # ── Formateo para mostrar: van al revés ──────────────────────────────
    "tools/glosas_dispensario/glosa_motor.py::money": (
        "formatea un número como '$1.234.567' para el texto de la respuesta"
    ),
    "tools/preauditar_glosas_adres.py::_moneda": (
        "réplica del TEXT($#.##0) de la macro: formatea para mostrar; no lee"
    ),
    "tools/suite_cartera_hus/suite_cartera_hus.py::_fmt_pesos_compacto": (
        "formatea para mostrar en pantalla; no lee"
    ),
    # ── Rangos de páginas de PDF: no son pesos ───────────────────────────
    "tools/suite_cartera_hus/nucleo/pdf_tools.py::parse_paginas": (
        "parsea rangos de páginas ('1-3,7'), no valores monetarios"
    ),
    "tools/suite_cartera_hus/suite_cartera_hus.py::_pdf_reordenar": (
        "reordena páginas de un PDF; los números son páginas"
    ),
    "tools/suite_cartera_hus/suite_cli.py::cmd_pdf": (
        "recibe rangos de páginas por línea de comandos"
    ),
    # ── Tarifas en UVB: la regla de los pesos aquí está MAL ──────────────
    # La Circular 047/2025 escribe las tarifas menores a 1 UVB con TRES
    # decimales (Ley 2294/2023, art. 313, parágrafo primero): el hematocrito
    # vale 0,567 UVB. Con la regla de los pesos —tres dígitos detrás = miles—
    # `a_numero("0,567")` devuelve 567.0, mil veces más. Comprobado:
    #     a_numero("0,602") -> 602.0   y   a_numero("0,567") -> 567.0
    # Serían $6.866.400 en vez de $6.900. Por eso este lector es propio, y
    # además devuelve None —no 0— cuando el texto no es un número: su trabajo
    # es decidir si una palabra del PDF escaneado ES una tarifa.
    "tools/generar_soat_uvb_2026_json.py::_a_float": (
        "lee tarifas en UVB de un PDF escaneado, no pesos: con tres decimales "
        "la regla de los pesos multiplica por mil"
    ),
    "tools/verificar_catalogos_soat.py::_pesos": ("formatea para mostrar en pantalla; no lee"),
    # ── main(): arman la salida, el valor ya viene leído ─────────────────
    "tools/consolidar_coosalud.py::main": "arma la salida; el valor ya viene leído",
    "tools/responder_glosas_coosalud.py::main": "arma la salida; el valor ya viene leído",
    "tools/responder_glosas_fomag.py::main": "arma la salida; el valor ya viene leído",
}


def _codigo_sin_texto(nodo: ast.AST) -> str:
    """El código de la función, sin docstrings ni cadenas de texto.

    Importa: varias de las funciones ya corregidas **citan el código viejo en
    su docstring** para explicar qué hacían mal. Si la búsqueda mirara el texto,
    la guardia acusaría justo a las que ya se arreglaron.
    """
    partes: list[str] = []
    for hijo in ast.walk(nodo):
        if isinstance(hijo, ast.Constant) and isinstance(hijo.value, str):
            continue  # docstrings y literales de texto: no son código
        if isinstance(hijo, ast.Call):
            partes.append(ast.dump(hijo))
    return " ".join(partes)


def _parece_lector_de_pesos(nodo: ast.AST) -> bool:
    """¿Esta función manipula separadores decimales y devuelve un número?"""
    codigo = _codigo_sin_texto(nodo)
    # `.replace(<sep>, …)` donde el separador es un punto o una coma.
    toca_separadores = "attr='replace'" in codigo and (
        "value='.'" in codigo or "value=','" in codigo
    )
    produce_numero = "id='float'" in codigo or "id='int'" in codigo
    return toca_separadores and produce_numero


def _lectores_encontrados() -> list[tuple[str, str, int]]:
    hallazgos: list[tuple[str, str, int]] = []
    for ruta in sorted(_TOOLS.rglob("*.py")):
        if ruta.name == _DUENO:
            continue
        texto = ruta.read_text(encoding="utf-8", errors="ignore")
        try:
            arbol = ast.parse(texto)
        except SyntaxError:  # un guion suelto que no compila no es el tema aquí
            continue
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if _parece_lector_de_pesos(nodo):
                rel = ruta.relative_to(_TOOLS.parent).as_posix()
                hallazgos.append((rel, nodo.name, nodo.lineno))
    return hallazgos


def test_no_hay_otro_lector_de_pesos():
    nuevos = [
        (archivo, funcion, linea)
        for archivo, funcion, linea in _lectores_encontrados()
        if f"{archivo}::{funcion}" not in _PERMITIDAS
    ]
    if nuevos:
        detalle = "\n".join(f"  {a}:{ln}  {f}()" for a, f, ln in nuevos)
        pytest.fail(
            "Apareció otro lector de pesos en tools/:\n"
            f"{detalle}\n\n"
            "En este repositorio la regla vive en UN solo sitio. Reemplácelo por:\n"
            "    from _dinero import a_numero   # o a_entero, si son pesos enteros\n\n"
            "Llegaron a convivir diez copias y cuatro estaban mal: una multiplicaba\n"
            "por cien, dos leían cero y tres dividían por mil. Los números salían en\n"
            "el Excel que se carga al ERP.\n\n"
            "Si la función FORMATEA pesos para mostrarlos (no los lee), agréguela a\n"
            "_PERMITIDAS en este archivo, con el motivo."
        )


def test_las_excepciones_siguen_existiendo():
    """Una excepción que ya no aplica es una puerta abierta que nadie vigila."""
    encontradas = {f"{a}::{f}" for a, f, _ in _lectores_encontrados()}
    huerfanas = sorted(set(_PERMITIDAS) - encontradas)
    assert not huerfanas, (
        "Estas excepciones ya no corresponden a ninguna función real; "
        f"quítelas de _PERMITIDAS: {huerfanas}"
    )
