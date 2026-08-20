"""Después de un despliegue, el motor tiene que volver solo.

20-08-2026. El portal se cayó TRES veces en una mañana, y las tres las levantó
Yesid a mano. La causa no era el código: el autodeploy MATA el motor para
aplicar la versión nueva y confía en que el vigilante lo resucite.

El vigilante es una ventana de consola con un bucle. Si alguien la cierra, o
la sesión de Windows se cierra, no queda nadie que levante el motor — y el
hospital se queda sin portal hasta que una persona lo note. No hay alerta: la
única señal es el «Bad gateway» de Cloudflare.

Un despliegue que puede dejar el sistema caído indefinidamente no es un
despliegue. Ahora la tarea comprueba que el motor volvió y, si no, lo arranca
ella misma sin depender del vigilante.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CMD = RAIZ / "tools" / "autodeploy_motor_local.cmd"


def _texto() -> str:
    return CMD.read_text(encoding="utf-8", errors="ignore")


class TestLaRedDeSeguridad:
    def test_comprueba_que_el_motor_volvio(self):
        """No basta con matarlo y confiar: hay que mirar si subió."""
        t = _texto()
        # Tras el kill tiene que haber una comprobación del puerto 8080.
        despues = t.split("deploy aplicado", 1)
        assert len(despues) == 2, "no se encontró el punto donde se aplica el deploy"
        assert "uvicorn app.main:app" in despues[1], "no se verifica que el motor volvió"

    def test_lo_arranca_si_no_volvio(self):
        t = _texto()
        assert "se arranca directo" in t
        assert re.search(r"start\s+\"\"\s+/b.*uvicorn app\.main:app", t), (
            "no hay arranque directo del motor"
        )

    def test_espera_antes_de_comprobar(self):
        """Preguntar de inmediato daría un falso negativo: tarda en subir."""
        t = _texto()
        assert re.search(r"timeout /t \d+ /nobreak", t)

    def test_deja_constancia_en_el_registro(self):
        """Si la red de seguridad actuó, tiene que quedar escrito."""
        t = _texto()
        assert "el motor NO volvio solo" in t
        assert "motor levantado por la red de seguridad" in t

    def test_avisa_si_ni_asi_sube(self):
        assert "ALERTA: el motor sigue caido" in _texto()

    def test_no_depende_solo_del_vigilante(self):
        """El arranque directo NO puede ser una llamada al vigilante."""
        t = _texto()
        bloque = t.split("se arranca directo", 1)[1]
        assert "arrancar_motor_glosas.cmd" not in bloque.split(":fin")[0], (
            "la red de seguridad vuelve a depender del vigilante"
        )


class TestSigueSiendoUnBotDeWindows:
    def test_conserva_los_finales_de_linea_de_windows(self):
        datos = CMD.read_bytes()
        assert b"\r\n" in datos
        assert datos.replace(b"\r\n", b"").count(b"\n") == 0, "hay saltos sueltos sin CR"

    def test_solo_toca_el_motor_de_produccion(self):
        """Del 04-08: antes mataba también el motor de pruebas del auditor."""
        t = _texto()
        for linea in t.splitlines():
            if "Stop-Process" in linea:
                assert "--port" in linea and "8080" in linea, linea

    def test_no_manda_a_correr_comandos_de_linux(self):
        t = _texto().lower()
        for comando in ("sudo ", "docker compose", "/opt/"):
            assert comando not in t, f"el bot menciona «{comando}»"

    @pytest.mark.parametrize("clave", ["GROQ_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY"])
    def test_no_lleva_claves_escritas(self, clave):
        assert clave not in _texto()
