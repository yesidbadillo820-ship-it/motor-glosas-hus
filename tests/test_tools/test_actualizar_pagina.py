"""El despliegue no puede quedarse colgado ni ser invisible.

24-08-2026. El autodespliegue corre cada 5 minutos y usa un archivo como
candado para no pisarse consigo mismo. Una pasada se quedó colgada en
`git fetch` —GitHub sin contestar— y como nunca soltó el candado, TODAS las
siguientes se saltaron: durante horas el registro solo decía «otra pasada
sigue trabajando» y el hospital se quedó con la versión vieja sin que nada
en pantalla lo delatara.

Dos cosas lo evitan: `git` tiene prohibido esperar y tiene tope de tiempo, y
el auditor cuenta con un bot de doble clic que actualiza a la vista y suelta
el candado si quedó trabado.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
AUTO = RAIZ / "tools" / "autodeploy_motor_local.cmd"
MANUAL = RAIZ / "tools" / "ACTUALIZAR_PAGINA.cmd"
ESTADO = RAIZ / "tools" / "estado_motor.ps1"


def _texto(ruta: Path) -> str:
    return ruta.read_text(encoding="utf-8", errors="ignore")


class TestGitNoSePuedeColgar:
    def test_el_autodespliegue_le_prohibe_a_git_preguntar(self):
        """Sin nadie que escriba usuario y clave, un prompt es un cuelgue."""
        assert "GIT_TERMINAL_PROMPT=0" in _texto(AUTO)

    def test_el_fetch_tiene_tope_de_tiempo(self):
        t = _texto(AUTO)
        assert "WaitForExit(" in t, "el fetch no tiene tope de tiempo: puede colgarse para siempre"
        tope = int(re.search(r"WaitForExit\((\d+)\)", t).group(1))
        assert 30_000 <= tope <= 600_000, f"tope raro: {tope} ms"
        # Y no puede quedar ningún `git fetch` suelto sin vigilancia.
        suelto = re.search(r"^\s*git fetch\b", t, re.M)
        assert suelto is None, "quedó un `git fetch` sin tope de tiempo"

    def test_avisa_el_motivo_en_el_registro(self):
        """Fallar en silencio fue justo lo que costó las horas de atraso."""
        t = _texto(AUTO)
        assert "NO SE PUDO CONSULTAR GITHUB" in t
        assert "3 minutos" in t


class TestElBotDeDobleClic:
    def test_existe_y_conserva_los_finales_de_linea_de_windows(self):
        assert MANUAL.exists(), "falta tools/ACTUALIZAR_PAGINA.cmd"
        crudo = MANUAL.read_bytes()
        assert b"\r\n" in crudo
        assert crudo.count(b"\n") == crudo.count(b"\r\n"), "hay saltos de línea sin CR"

    def test_libera_el_candado_trabado(self):
        t = _texto(MANUAL)
        assert "autodeploy.lock" in t
        assert re.search(r"del .*CANDADO", t), "no suelta el candado trabado"

    def test_tambien_le_pone_tope_y_mordaza_a_git(self):
        t = _texto(MANUAL)
        assert "GIT_TERMINAL_PROMPT=0" in t
        assert "WaitForExit(" in t
        assert re.search(r"^\s*git fetch\b", t, re.M) is None

    def test_reinicia_solo_el_motor_de_produccion(self):
        """El de pruebas (otro puerto) no se toca: ya pasó una vez."""
        t = _texto(MANUAL)
        assert "--port\\s+8080" in t or "--port 8080" in t
        assert "--port 8000" not in t and "--port\\s+8000" not in t

    def test_comprueba_que_la_pagina_volvio_a_responder(self):
        t = _texto(MANUAL)
        assert "/health" in t, "no comprueba que la página conteste"
        # 03-09-2026: la red de seguridad SIGUE, pero ya no arranca uvicorn
        # crudo. Aquel arranque directo dejaba el motor sin SOPORTES_ROOT ni
        # AUTO_PILOT_ENABLED, ocupando el 8080 mientras el vigilante de verdad
        # esperaba parqueado detrás. Ahora entra por el arranque oficial, que
        # prepara el entorno completo — por eso se comprueba la puerta, no la
        # frase de antes.
        assert ":no_subio" in t, "no hay red de seguridad si el motor no vuelve"
        assert "servidor_motor_local.cmd" in t, (
            "la red de seguridad no pasa por el arranque oficial"
        )

    def test_le_dice_al_auditor_lo_que_sigue(self):
        """Sin el Ctrl + F5 el navegador sigue mostrando la pantalla vieja."""
        t = _texto(MANUAL)
        assert "Ctrl + F5" in t
        assert t.rstrip().endswith("pause"), "la ventana se cierra sin que alcance a leer"


class TestLaPantallaDeEstadoDelataElCandado:
    """La falla no se veía: el registro solo repetía «otra pasada sigue
    trabajando» y en la pantalla de estado todo salía bien."""

    def test_avisa_si_el_candado_lleva_mucho_puesto(self):
        t = _texto(ESTADO)
        assert "autodeploy.lock" in t, "la pantalla no mira el candado"
        assert "trabado" in t
        assert "ACTUALIZAR_PAGINA.cmd" in t, "no dice qué hacer para destrabarlo"

    def test_sigue_en_ascii(self):
        """Windows PowerShell lee este archivo como ANSI: con tildes, los
        mensajes salen rotos en pantalla."""
        for n, linea in enumerate(_texto(ESTADO).splitlines(), 1):
            assert all(ord(c) < 128 for c in linea), f"línea {n} tiene tildes"
