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
        """Lo que importa es que arranque el motor de producción, no con qué
        forma exacta de `start`.

        Esta prueba pedía literalmente `start "" /b`, y ese `/b` resultó ser el
        defecto: sin ventana nueva el motor hereda la salida de la tarea,
        Windows nunca da la tarea por terminada, la mata con 255 y salta todas
        las pasadas siguientes. El autodespliegue dejó de bajar código durante
        horas sin avisar (21-08-2026).

        Ahora se comprueba lo que de verdad protege —que arranca el motor
        correcto— y, además, que NO vuelva el `/b` que lo rompía.
        """
        t = _texto()
        assert "se arranca directo" in t
        arranque = re.search(r"^\s*start\s+.*uvicorn app\.main:app.*$", t, re.M)
        assert arranque, "no hay arranque directo del motor"
        linea = arranque.group(0)
        assert "app.main:app" in linea and "--port 8080" in linea
        antes_del_comando = linea.split("cmd", 1)[0]
        assert "/b" not in antes_del_comando, (
            "volvió el `start /b`: la tarea del autodespliegue se queda colgada y deja de correr."
        )

    def test_espera_antes_de_comprobar(self):
        """Preguntar de inmediato daría un falso negativo: el motor tarda en
        subir.

        Esto ya fijó dos veces el mecanismo equivocado. Primero pedía
        `timeout`, que no espera nada sin sesión iniciada. Después pedía una
        espera larga de una sola vez, y el 24-08 se vio que 12 segundos no le
        alcanzan a un motor que carga una base de 133 MB: se daba por muerto
        estando vivo y se le levantaba otro encima.

        Ahora se comprueba lo único que de verdad protege: **cuánto está
        dispuesto a esperar en total** antes de declararlo caído.
        """
        t = _texto()
        pausa = [int(x) - 1 for x in re.findall(r"ping -n (\d+) 127\.0\.0\.1", t)]
        vueltas = [int(x) for x in re.findall(r"%INTENTOS%\s+(?:GEQ|LSS)\s+(\d+)", t)]
        fijas = [int(x) for x in re.findall(r"timeout /t (\d+) /nobreak", t)]
        if vueltas:
            total = min(pausa) * min(vueltas)
        else:
            total = max(pausa + fijas or [0])
        assert total >= 60, (
            f"la red de seguridad solo espera {total} segundos: puede dar el "
            f"motor por caído estando vivo y arrancarle un segundo encima."
        )

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
