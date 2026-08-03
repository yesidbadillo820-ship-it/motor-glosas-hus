"""Pruebas del bot de doble clic tools/CARGAR_SIIFA.cmd.

El .cmd no se puede correr acá (es de Windows), pero sí se puede cuidar lo
que de verdad lo rompe: que llame a un script que ya no existe o con una
opción que se renombró. Si eso pasa, el auditor se entera en mitad de un
cargue, con el portal abierto.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
CMD = RAIZ / "tools" / "CARGAR_SIIFA.cmd"


def _llamadas() -> list[tuple[str, list[str]]]:
    """(script, opciones) de cada línea del .cmd que corre un .py del repo."""
    texto = CMD.read_text(encoding="utf-8")
    llamadas = []
    for linea in texto.splitlines():
        if "%PYEXE% tools\\" not in linea:
            continue
        script = re.search(r"tools\\(\S+\.py)", linea).group(1)
        llamadas.append((script, re.findall(r"\s(--[a-z-]+)", linea)))
    return llamadas


def test_el_bot_llama_a_los_tres_scripts_del_flujo():
    scripts = {s for s, _ in _llamadas()}

    assert scripts == {
        "siifa_reporte_seguimientos.py",
        "siifa_redactar_respuestas.py",
        "responder_glosas_siifa.py",
    }


def test_ningun_script_que_llama_el_bot_se_quedo_sin_existir():
    for script, _ in _llamadas():
        assert (RAIZ / "tools" / script).is_file(), f"{script} ya no existe"


def test_todas_las_opciones_que_usa_el_bot_siguen_existiendo():
    """Si alguien renombra una opción, el bot falla en pleno cargue."""
    for script, opciones in _llamadas():
        fuente = (RAIZ / "tools" / script).read_text(encoding="utf-8")
        for opcion in opciones:
            assert f'"{opcion}"' in fuente, f"{script} ya no acepta {opcion}"


def test_el_piloto_va_antes_del_cargue_masivo():
    """La regla del repo: nunca un cargue masivo sin piloto de 1."""
    texto = CMD.read_text(encoding="utf-8")

    assert "--piloto 1" in texto
    assert "goto sinpiloto" in texto, "el bot debe frenar el cargue masivo sin piloto"


def test_la_carpeta_se_valida_antes_de_llegar_al_menu():
    """Si la ruta no sirve, hay que decirlo YA, no siete minutos después.

    Pasó de verdad: se pegó un comando en vez de una carpeta, el bot bajó
    los 2.598 seguimientos y se perdieron al intentar guardarlos.
    """
    texto = CMD.read_text(encoding="utf-8")

    assert "goto carpetamala" in texto, "debe rechazar una ruta que no es carpeta"
    assert "goto carpetasinpermiso" in texto, "debe rechazar una carpeta donde no puede escribir"
    assert texto.index("goto carpetamala") < texto.index(":menu"), "se valida antes del menú"


def test_se_puede_corregir_la_carpeta_sin_cerrar_el_bot():
    texto = CMD.read_text(encoding="utf-8")

    assert "[8] Cambiar la carpeta de trabajo" in texto
    assert 'if "%OPCION%"=="8" goto carpeta' in texto


def test_la_clave_solo_viaja_en_la_variable_de_entorno():
    """Regla del repo: nunca un usuario ni una clave escritos en el código."""
    texto = CMD.read_text(encoding="utf-8")

    assert 'setx SIIFA_USER "%SIIFA_USER%"' in texto
    assert 'setx SIIFA_PASSWORD "%SIIFA_PASSWORD%"' in texto
