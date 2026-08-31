"""El bot de doble clic del curso de noruego tiene que servir en el PC real.

Fallas reales que estas pruebas evitan:

1. **La tubería escapada.** El bot traía ``ipconfig ^| findstr /C:"IPv4"`` en
   una línea suelta. El ``^|`` solo va escapado DENTRO de un ``for /f``; en una
   línea normal el ``|`` le llega a ``ipconfig`` como argumento y el bot imprime
   la ayuda de ``ipconfig`` en vez de la dirección. Pasó el 31-08.
2. **El texto de relleno.** Como no salió la dirección, el bot igual decía
   «escribe http://LA-IP-DE-ARRIBA:8000/...» — y eso fue exactamente lo que el
   usuario escribió en el navegador (error DNS_PROBE_FINISHED_NXDOMAIN).
3. **Finales de línea LF**, que en Windows cierran la ventana sin ejecutar nada.
4. **La carpeta equivocada**, que da «No module named noruego».
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
BOT = RAIZ / "tools" / "NORUEGO.cmd"


def _texto() -> str:
    return BOT.read_bytes().decode("utf-8")


def _lineas_de_comando() -> list[str]:
    """Las líneas que cmd.exe ejecuta: sin comentarios, etiquetas ni echo."""
    utiles = []
    for cruda in _texto().splitlines():
        linea = cruda.strip()
        bajo = linea.lower()
        if not linea or linea.startswith(":") or bajo.startswith(("rem ", "echo")):
            continue
        utiles.append(linea)
    return utiles


def test_el_bot_existe():
    assert BOT.is_file(), "falta tools/NORUEGO.cmd"


def test_conserva_los_finales_de_linea_de_windows():
    crudo = BOT.read_bytes()
    assert not crudo.replace(b"\r\n", b"").count(b"\n"), (
        "NORUEGO.cmd tiene finales de línea de Unix: en Windows la ventana se cierra sola"
    )


def test_se_para_solo_en_la_carpeta_del_repositorio():
    assert 'cd /d "%~dp0.."' in _texto(), "sin esto da «No module named noruego»"


def test_avisa_si_falta_python():
    texto = _texto()
    assert "where python" in texto
    assert "python.org" in texto


def test_no_trae_usuarios_ni_contrasenas():
    bajo = _texto().lower()
    for palabra in ("password", "contraseña", "clave=", "token="):
        assert palabra not in bajo, f"NORUEGO.cmd parece traer una credencial ({palabra})"


def test_la_tuberia_solo_va_escapada_dentro_de_un_for():
    """La causa exacta de que el bot mostrara la ayuda de ipconfig."""
    malas = [
        linea
        for linea in _lineas_de_comando()
        if "^|" in linea and not linea.lower().startswith("for ")
    ]
    assert not malas, (
        f"el «^|» fuera de un for /f hace que el «|» le llegue al programa como argumento: {malas}"
    )


def test_la_direccion_la_calcula_el_programa_no_el_bat():
    """Una sola fuente de verdad: `python -m noruego direccion` arma el enlace."""
    texto = _texto()
    assert "python -m noruego direccion" in texto
    assert "%ENLACE%" in texto, "el bot no imprime el enlace que capturó"


def test_no_ofrece_el_relleno_viejo_como_direccion():
    """«LA-IP-DE-ARRIBA» es literalmente lo que el usuario escribió en Chrome."""
    assert "LA-IP-DE-ARRIBA" not in _texto()


def test_el_relleno_que_queda_va_siempre_con_su_explicacion():
    """Si de verdad no hay IP, el bot explica cómo conseguirla antes de mostrar el hueco."""
    texto = _texto()
    if "ESE-NUMERO" not in texto:
        return
    antes = texto.split("ESE-NUMERO", 1)[0]
    assert "ipconfig" in antes and "IPv4" in antes, (
        "el texto de relleno aparece sin decir antes de dónde se saca el número"
    )


def test_dice_que_agregar_a_la_pantalla_es_del_celular():
    """El usuario lo buscó en el Chrome del PC, donde esa opción no existe."""
    texto = _texto()
    assert "Android" in texto and "iPhone" in texto, "no dice cómo instalarla en cada teléfono"
    assert "doble clic" in texto, "no dice qué hacer en el computador"


def test_el_bot_solo_llama_a_comandos_que_existen():
    """Un subcomando inventado revienta recién abierto el bot."""
    from noruego.cli import construir_parser

    validos = set(construir_parser()._subparsers._group_actions[0].choices)
    llamados = set()
    for linea in _texto().splitlines():
        limpia = linea.strip()
        if limpia.lower().startswith("rem ") or "python -m noruego" not in limpia:
            continue
        resto = limpia.split("python -m noruego", 1)[1].split()
        if resto:
            # Dentro de un for /f el comando va entre comillas simples: ...direccion')
            llamados.add(resto[0].strip("\"')"))
    assert llamados, "el bot no llama a ningún comando del curso"
    assert not (llamados - validos), f"comandos que no existen: {llamados - validos}"


def test_el_gitattributes_mantiene_la_regla_de_crlf():
    reglas = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
    assert "*.cmd text eol=crlf" in reglas


# --- La guía del usuario ---------------------------------------------------
# Dos veces seguidas se copió la dirección de EJEMPLO en vez de la propia:
# primero «LA-IP-DE-ARRIBA», después el 192.168.1.15 de la guía (la máquina
# real era otra). La conclusión es que cualquier dirección impresa como
# ejemplo termina escrita en el navegador, así que no puede haber ninguna.

GUIA = RAIZ / "docs" / "GUIA_CURSO_NORUEGO.md"

#: Una dirección de máquina completa y copiable: http://<numeros>:<puerto>/
DIRECCION_COPIABLE = re.compile(r"https?://\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?/")


def test_la_guia_no_trae_ninguna_direccion_de_ejemplo():
    encontradas = DIRECCION_COPIABLE.findall(GUIA.read_text(encoding="utf-8"))
    assert not encontradas, (
        "la guía muestra una dirección copiable y el usuario la copia en vez "
        f"de la suya: {encontradas}"
    )


def test_el_bot_no_trae_ninguna_direccion_de_ejemplo():
    encontradas = DIRECCION_COPIABLE.findall(_texto())
    assert not encontradas, f"el bot muestra una dirección copiable: {encontradas}"


def test_el_bot_explica_que_hacer_si_el_celular_no_conecta():
    """«Tardó demasiado en responder» es firewall o red, no un enlace malo."""
    texto = _texto()
    assert "New-NetFirewallRule" in texto, "no dice cómo abrir el puerto en el firewall"
    assert "8000" in texto
