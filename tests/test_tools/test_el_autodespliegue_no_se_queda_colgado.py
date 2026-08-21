"""El autodespliegue tiene que TERMINAR, no quedarse colgado (21-08-2026, noche).

QUÉ PASÓ. El portal llevaba horas sin recibir el código nuevo, aunque todo
estaba fusionado. El PC de cartera contó por qué, en tres datos:

- `data\\autodeploy.log` estaba lleno de **líneas de visitas a la página**
  (`GET / HTTP/1.1 200 OK`), no de mensajes del autodespliegue.
- La tarea `MotorGlosas_Autodeploy` terminó con **resultado 255**.
- El repositorio estaba clavado en un commit viejo.

LA CAUSA, que encadena las tres. La red de seguridad —la parte que arranca el
motor cuando no volvió solo— lo hacía con `start /b`. Sin ventana nueva, el
motor **hereda la salida** de la tarea. Windows da una tarea por terminada
solo cuando nadie más tiene esa salida abierta… y el motor no la suelta nunca.

Así que la tarea se quedaba «corriendo» para siempre, Windows terminaba
matándola (255) y, como está puesta en no abrir dos a la vez, **saltaba todas
las pasadas siguientes**. El autodespliegue moría en silencio, y de paso el
registro donde había que mirar quedaba tapado por el tráfico de la página.

Lo peor: nada avisa. Todo «se ve bien» hasta que alguien nota que el código
nuevo no llega.
"""

from __future__ import annotations

import re
from pathlib import Path

RUTA = Path(__file__).resolve().parents[2] / "tools" / "autodeploy_motor_local.cmd"


def _texto() -> str:
    return RUTA.read_bytes().decode("utf-8", errors="replace")


def _linea_del_rescate() -> str:
    for linea in _texto().splitlines():
        if linea.strip().startswith("start ") and "uvicorn" in linea:
            return linea
    raise AssertionError("la red de seguridad ya no arranca el motor")


class TestLaTareaSuletaElProceso:
    def test_el_motor_se_abre_en_su_propia_ventana(self):
        linea = _linea_del_rescate()
        assert "/b" not in linea.split("cmd", 1)[0], (
            "Volvió el `start /b`: el motor hereda la salida de la tarea, la "
            "tarea no termina nunca, Windows la mata con 255 y salta todas las "
            "pasadas siguientes. El autodespliegue deja de bajar código y nada "
            "avisa."
        )

    def test_usa_la_forma_segura_de_pasar_comillas(self):
        """`cmd /s /c` quita la primera y la última comilla y deja el resto tal
        cual. Sin `/s`, una orden con comillas adentro se parte mal y el motor
        no arranca — que es justo lo que esta parte tiene que garantizar."""
        assert "cmd /s /c" in _linea_del_rescate()

    def test_el_motor_sigue_siendo_el_de_produccion(self):
        linea = _linea_del_rescate()
        assert "app.main:app" in linea
        assert "--port 8080" in linea
        assert "127.0.0.1" in linea


class TestCadaRegistroEnSuSitio:
    def test_el_motor_no_escribe_en_el_registro_del_autodespliegue(self):
        linea = _linea_del_rescate()
        assert "autodeploy.log" not in linea, (
            "El motor vuelve a escribir en el registro del autodespliegue. Ese "
            "archivo se llena de las visitas a la página y tapa los mensajes "
            "propios: es justo donde hay que mirar cuando el código no baja."
        )

    def test_escribe_en_el_registro_del_servidor(self):
        assert "servidor.log" in _linea_del_rescate()

    def test_el_registro_del_autodespliegue_no_crece_sin_fin(self):
        """Ya llegó a llenarse con el tráfico de la página. El vigilante ya se
        reiniciaba solo al pasar de ~5 MB; esta tarea no."""
        t = _texto()
        assert "GTR 5000000" in t, "el registro del autodespliegue no se recicla"
        assert "del " in t


class TestNoSeRompioLaRedDeSeguridad:
    def test_sigue_comprobando_antes_de_arrancar_nada(self):
        t = _texto()
        i = t.index("el motor NO volvio solo")
        assert "uvicorn app.main:app" in t[:i], (
            "se perdió la comprobación de si el motor ya estaba arriba"
        )

    def test_sigue_avisando_si_ni_asi_sube(self):
        assert "ALERTA: el motor sigue caido" in _texto()

    def test_sigue_esperando_a_que_arranque_antes_de_juzgar(self):
        """Preguntar de inmediato daría un falso negativo."""
        esperas = [int(x) - 1 for x in re.findall(r"ping -n (\d+) 127\.0\.0\.1", _texto())]
        assert esperas and max(esperas) >= 10

    def test_sigue_bajando_de_la_rama_del_hospital(self):
        assert "origin/motor-glosas" in _texto()

    def test_conserva_los_finales_de_linea_de_windows(self):
        b = RUTA.read_bytes()
        assert b.count(b"\n") == b.count(b"\r\n"), "hay saltos de línea sueltos"
