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


def test_el_bot_llama_a_los_scripts_del_flujo():
    scripts = {s for s, _ in _llamadas()}

    assert scripts == {
        "siifa_reporte_seguimientos.py",
        "siifa_redactar_respuestas.py",
        "responder_glosas_siifa.py",
        "siifa_verificar_cargue.py",
        "siifa_novedades.py",
        "siifa_estado_tramite.py",
        "siifa_armar_subsanacion.py",
        "siifa_balance.py",
    }


def test_ningun_script_que_llama_el_bot_se_quedo_sin_existir():
    for script, _ in _llamadas():
        assert (RAIZ / "tools" / script).is_file(), f"{script} ya no existe"


def test_todas_las_opciones_que_usa_el_bot_siguen_existiendo():
    """Si alguien renombra una opción, el bot falla en pleno cargue.

    `--ips` no se declara en cada script sino una sola vez, en
    siifa_perfiles.agregar_argumento(), así que se busca también ahí.
    """
    comunes = (RAIZ / "tools" / "siifa_perfiles.py").read_text(encoding="utf-8")
    for script, opciones in _llamadas():
        fuente = (RAIZ / "tools" / script).read_text(encoding="utf-8")
        for opcion in opciones:
            assert f'"{opcion}"' in fuente or f'"{opcion}"' in comunes, (
                f"{script} ya no acepta {opcion}"
            )


def test_el_bot_le_dice_a_cada_script_con_que_ips_trabaja():
    """El auditor maneja cuatro IPS. Un script que se llame sin --ips
    trabajaría con el HUS por defecto: la entidad equivocada, en silencio."""
    for script, opciones in _llamadas():
        if script in (
            "siifa_reporte_seguimientos.py",
            "responder_glosas_siifa.py",
            "siifa_verificar_cargue.py",
        ):
            assert "--ips" in opciones, f"el bot llama a {script} sin decirle la IPS"


def test_elegir_la_ips_es_lo_primero_que_hace_el_bot():
    """De la IPS salen las credenciales, la carpeta y el título de la ventana:
    si se eligiera después, esas tres cosas quedarían de la IPS anterior."""
    texto = CMD.read_text(encoding="utf-8")

    assert texto.index(":elegirips") < texto.index(":credenciales")
    assert texto.index(":elegirips") < texto.index(":carpeta")
    assert "title SIIFA - %IPS%" in texto, "el título distingue una ventana de otra"


def test_cada_ips_trabaja_en_su_propia_carpeta():
    """Compartir carpeta haría que el informe de una pisara al de otra: todos
    los archivos se llaman igual."""
    texto = CMD.read_text(encoding="utf-8")

    assert "%IPS%" in texto[texto.index('set "DEFCARP=') : texto.index('set "DEFCARP=') + 80]


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


def test_el_enter_toma_la_carpeta_de_por_defecto():
    """El orden importa y ya rompió una corrida real.

    Al dar Enter la variable queda vacía. Si primero se le quitan las
    comillas y después se aplica la carpeta por defecto, `%CARPETA:"=%`
    sobre una variable vacía deja de carpeta la basura «"=» — que fue lo
    que pasó: el menú mostró `Carpeta: "=` y ninguna opción funcionó.
    """
    texto = CMD.read_text(encoding="utf-8")
    bloque = texto[texto.index(":carpeta") : texto.index(":menu")]

    defecto = bloque.index('if not defined CARPETA set "CARPETA=%DEFCARP%"')
    sin_comillas = bloque.index('set "CARPETA=%CARPETA:"=%"')

    assert defecto < sin_comillas, "la carpeta por defecto se aplica ANTES de quitar comillas"


def test_lo_que_se_escribe_se_comprueba_antes_de_tocarlo():
    """Misma trampa en la ruta del export de DGH."""
    texto = CMD.read_text(encoding="utf-8")
    bloque = texto[texto.index(":armar") : texto.index(":piloto")]

    assert bloque.index("if not defined DGH goto sindgh") < bloque.index('set "DGH=%DGH:"=%"')


def test_se_puede_corregir_la_carpeta_sin_cerrar_el_bot():
    texto = CMD.read_text(encoding="utf-8")

    assert "[8] Cambiar de IPS o de carpeta" in texto
    assert 'if "%OPCION%"=="8" goto elegirips' in texto


def test_la_clave_solo_viaja_en_la_variable_de_entorno():
    """Regla del repo: nunca un usuario ni una clave escritos en el código."""
    texto = CMD.read_text(encoding="utf-8")

    # Una variable por IPS: SIIFA_USER_HUS, SIIFA_USER_SOCORRO, etc.
    assert 'setx %UVAR% "%UVAL%"' in texto
    assert 'setx %PVAR% "%PVAL%"' in texto
    assert "SIIFA_USER_%IPS%" in texto
    # Y nunca una clave escrita en el propio archivo.
    assert not re.search(r'set "(SIIFA_)?PASSWORD\w*=[^%"\r\n]{3,}"', texto)
