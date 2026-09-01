"""Los bots de doble clic tienen que funcionar en el PC del auditor.

Dos fallas reales que estas pruebas evitan:

1. **Finales de línea LF.** En Windows, un ``.cmd`` guardado con finales de
   línea de Unix hace que la ventana se cierre sin ejecutar nada. El repo ya
   tiene la regla en ``.gitattributes``, pero no había nada que la verificara.
2. **La carpeta equivocada.** ``python -m icfes`` solo encuentra el módulo si
   la consola está parada en la carpeta del repositorio. Un bot que no se
   posicione solo falla con «No module named icfes», que fue exactamente lo
   que pasó la primera vez que se usó desde PowerShell.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
TOOLS = RAIZ / "tools"

#: Los bots del sistema ICFES.
BOTS_ICFES = ("ICFES.cmd", "ICFES_APP.cmd")


def _todos_los_cmd() -> list[Path]:
    return sorted(TOOLS.glob("*.cmd"))


def test_hay_bots_en_tools():
    assert _todos_los_cmd(), "no se encontró ningún .cmd en tools/"


@pytest.mark.parametrize("nombre", BOTS_ICFES)
def test_el_bot_del_icfes_existe(nombre):
    assert (TOOLS / nombre).is_file(), f"falta tools/{nombre}"


@pytest.mark.parametrize("nombre", BOTS_ICFES)
def test_el_bot_se_para_solo_en_la_carpeta_del_repositorio(nombre):
    """La causa exacta del «No module named icfes» de la primera prueba real."""
    texto = (TOOLS / nombre).read_bytes().decode("utf-8")
    assert 'cd /d "%~dp0.."' in texto or "cd /d %~dp0.." in texto, (
        f"{nombre} no vuelve a la carpeta del repositorio antes de llamar a Python"
    )


@pytest.mark.parametrize("nombre", BOTS_ICFES)
def test_el_bot_avisa_si_falta_python(nombre):
    texto = (TOOLS / nombre).read_bytes().decode("utf-8")
    assert "where python" in texto, f"{nombre} no verifica que Python esté instalado"
    assert "python.org" in texto, f"{nombre} no dice dónde instalar Python"


def test_todos_los_cmd_conservan_finales_de_linea_de_windows():
    """Con LF, la ventana se cierra sin ejecutar nada en el PC del hospital."""
    malos = []
    for archivo in _todos_los_cmd():
        crudo = archivo.read_bytes()
        # Un LF que no venga precedido de CR delata el problema.
        if crudo.replace(b"\r\n", b"").count(b"\n"):
            malos.append(archivo.name)
    assert not malos, f"estos .cmd tienen finales de línea de Unix: {', '.join(malos)}"


def test_el_gitattributes_mantiene_la_regla():
    reglas = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert "*.cmd text eol=crlf" in reglas


@pytest.mark.parametrize("nombre", BOTS_ICFES)
def test_el_bot_no_trae_usuarios_ni_contrasenas(nombre):
    """Regla del repo: nunca se commitean credenciales."""
    texto = (TOOLS / nombre).read_bytes().decode("utf-8").lower()
    for palabra in ("password", "contraseña", "clave=", "token="):
        assert palabra not in texto, f"{nombre} parece traer una credencial"


def test_el_menu_llama_solo_a_comandos_que_existen():
    """Un menú que llame a un subcomando inventado falla recién abierto."""
    from icfes.cli import construir_parser

    validos = set(construir_parser()._subparsers._group_actions[0].choices)
    texto = (TOOLS / "ICFES.cmd").read_bytes().decode("utf-8")
    llamados = set()
    for linea in texto.splitlines():
        limpia = linea.strip()
        # Las líneas "rem" son comentarios y también nombran el comando.
        if limpia.lower().startswith("rem ") or "python -m icfes" not in limpia:
            continue
        resto = limpia.split("python -m icfes", 1)[1].split()
        if resto:
            llamados.add(resto[0].strip('"'))
    desconocidos = llamados - validos
    assert not desconocidos, f"el menú llama a comandos que no existen: {desconocidos}"
