"""Con el PC recién prendido y nadie adentro, el motor tiene que subir igual
(21-08-2026, tarde).

QUÉ PASÓ. Se reinició el PC de cartera y el portal contestó «Bad gateway 502».
El túnel subió; el motor no. Y la **red de seguridad** —la parte del
autodespliegue que arranca el motor directo cuando no vuelve solo, la que ha
salvado el portal varias veces— no se enteró de nada.

POR QUÉ NO SE ENTERÓ. La tarea del autodespliegue se creó sin decirle a
Windows con qué cuenta corre. Cuando no se dice, Windows la deja en «solo
cuando el usuario haya iniciado sesión». O sea: la red de seguridad dormía
justo en el único momento para el que se construyó.

LO QUE ESTAS PRUEBAS CUIDAN, y que solo se nota con el PC recién prendido:

1. Que el autodespliegue quede puesto para trabajar **sin sesión iniciada**.
2. Que las esperas de los bots aguanten esa situación. `timeout` necesita una
   consola de verdad; sin ella contesta «Input redirection is not supported» y
   sigue de largo **sin esperar**, con lo que un bucle de reintentos se vuelve
   una tormenta de procesos. `ping` a uno mismo espera igual en todos lados.
3. Que la pantalla de estado lo DIGA. Una tarea que existe pero duerme se ve
   igual de bien que una que trabaja, y esa es exactamente la trampa en la que
   se cayó.
4. Que la contraseña la siga pidiendo Windows y no quede escrita en ningún
   archivo del repositorio.
"""

from __future__ import annotations

import re
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
INSTALADOR = TOOLS / "ARRANQUE_AUTOMATICO_MOTOR.cmd"
ESTADO = TOOLS / "estado_motor.ps1"

# Los bots que ahora corren también sin sesión iniciada.
SIN_SESION = [
    TOOLS / "servidor_motor_local.cmd",
    TOOLS / "tunel_motor_local.cmd",
    TOOLS / "autodeploy_motor_local.cmd",
]


def _texto(ruta: Path) -> str:
    return ruta.read_bytes().decode("utf-8", errors="replace")


class TestLasEsperasAguantanElArranqueDelPC:
    def test_ningun_bot_espera_con_timeout(self):
        for ruta in SIN_SESION:
            assert "timeout /t" not in _texto(ruta), (
                f"{ruta.name} espera con `timeout`. Sin sesión iniciada eso "
                f"puede no esperar nada y el bucle se vuelve una tormenta de "
                f"procesos. Use `ping -n N 127.0.0.1 >nul`."
            )

    def test_todos_esperan_con_ping(self):
        for ruta in SIN_SESION:
            assert re.search(r"ping -n \d+ 127\.0\.0\.1 >nul", _texto(ruta)), (
                f"{ruta.name} se quedó sin ninguna espera: un bucle sin pausa "
                f"consume el equipo entero."
            )

    def test_las_esperas_siguen_durando_mas_o_menos_lo_mismo(self):
        """`ping -n N` manda N paquetes con un segundo entre uno y otro: la
        espera real son N-1 segundos. Cambiar el método no puede cambiar los
        tiempos que ya estaban pensados."""
        esperados = {
            "servidor_motor_local.cmd": [5, 5],
            "tunel_motor_local.cmd": [5],
            "autodeploy_motor_local.cmd": [12, 15],
        }
        for ruta in SIN_SESION:
            n = [int(x) for x in re.findall(r"ping -n (\d+) 127\.0\.0\.1 >nul", _texto(ruta))]
            assert [x - 1 for x in n] == esperados[ruta.name], (
                f"{ruta.name}: las esperas quedaron en {[x - 1 for x in n]} segundos"
            )

    def test_explica_por_que_no_usa_timeout(self):
        """Sin la explicación, el próximo que lea el archivo lo 'arregla' de
        vuelta a `timeout`, que es lo que se lee más natural."""
        for ruta in SIN_SESION:
            t = _texto(ruta)
            assert "timeout" in t and "sesion" in t.lower(), (
                f"{ruta.name} no explica por qué espera con ping"
            )


class TestElAutodespliegueTrabajaSinSesionIniciada:
    def _linea(self) -> str:
        t = _texto(INSTALADOR)
        m = re.search(r"^schtasks /Create[^\n]*MotorGlosas_Autodeploy.*?\n[^\n]*\n", t, re.M)
        assert m, "el instalador ya no vuelve a crear la tarea del autodespliegue"
        return m.group(0)

    def test_se_vuelve_a_crear_con_una_cuenta(self):
        assert "/RU " in self._linea(), (
            "Sin /RU, Windows deja la tarea en «solo con sesión iniciada» y la "
            "red de seguridad duerme cuando más hace falta."
        )

    def test_con_la_misma_cuenta_del_arranque(self):
        assert "%CUENTA%" in self._linea()

    def test_sigue_corriendo_cada_cinco_minutos(self):
        linea = self._linea()
        assert "/SC MINUTE" in linea and "/MO 5" in linea

    def test_sigue_apuntando_al_mismo_bot(self):
        assert "autodeploy_motor_local.cmd" in self._linea()

    def test_la_contrasena_la_pide_windows(self):
        assert "/RP *" in self._linea()

    def test_si_falla_lo_dice_y_no_deja_el_motor_peor(self):
        """Que el autodespliegue no se pueda cambiar NO puede hacer creer que
        el arranque tampoco quedó: son dos cosas distintas."""
        t = _texto(INSTALADOR)
        i = t.index("MotorGlosas_Autodeploy")
        despues = t[i : i + 900]
        assert "No se rompio nada" in despues or "no se rompio nada" in despues.lower()
        assert "SI quedo puesto" in despues or "arranque" in despues.lower()


class TestNingunaContrasenaEnElRepositorio:
    def test_ni_una_sola_contrasena_escrita(self):
        t = _texto(INSTALADOR)
        # /RP seguido de algo que no sea el asterisco sería una clave escrita.
        for m in re.finditer(r"/RP\s+(\S+)", t):
            assert m.group(1) == "*", f"hay una contraseña escrita: {m.group(0)}"

    def test_dice_que_la_guarda_windows_y_no_el_repositorio(self):
        t = _texto(INSTALADOR).lower()
        assert "boveda de windows" in t
        assert "repositorio" in t


class TestLaPantallaDeEstadoLoDelata:
    """Una tarea que existe pero duerme se ve igual de bien que una que
    trabaja. Esa fue la trampa; la pantalla tiene que distinguirlas."""

    def test_mira_tambien_la_tarea_de_arranque(self):
        assert "MotorGlosas_Arranque" in _texto(ESTADO), (
            "La pantalla de estado no revisa la tarea que arranca el motor al "
            "prender el PC: el auditor no tiene cómo saber si quedó puesta."
        )

    def test_distingue_la_que_duerme_de_la_que_trabaja(self):
        t = _texto(ESTADO)
        assert "LogonType" in t
        assert "S4U" in t and "Password" in t

    def test_lo_dice_en_cristiano(self):
        t = _texto(ESTADO)
        assert "SOLO con sesion iniciada" in t
        assert "aunque nadie inicie sesion" in t

    def test_avisa_como_arreglarlo(self):
        assert "ARRANQUE_AUTOMATICO_MOTOR.cmd" in _texto(ESTADO)

    def test_cuenta_como_le_fue_la_ultima_vez(self):
        """Una tarea puesta que termina en error todos los días es peor que no
        tenerla: da tranquilidad falsa."""
        t = _texto(ESTADO)
        assert "LastTaskResult" in t
        assert "TERMINO CON ERROR" in t

    def test_no_confunde_estar_corriendo_con_haber_fallado(self):
        """267009 es «va corriendo ahora mismo», no un error. El
        autodespliegue arranca cada 5 minutos: verlo así es lo normal."""
        assert "267009" in _texto(ESTADO)

    def test_sigue_en_ascii(self):
        """Windows PowerShell lee este archivo como ANSI: con tildes, los
        mensajes salen rotos en pantalla."""
        for n, linea in enumerate(_texto(ESTADO).splitlines(), 1):
            assert all(ord(c) < 128 for c in linea), f"línea {n} tiene tildes"


class TestNoSeRompioLoQueYaFuncionaba:
    def test_los_cmd_conservan_los_finales_de_linea_de_windows(self):
        for ruta in SIN_SESION + [INSTALADOR]:
            b = ruta.read_bytes()
            assert b.count(b"\n") == b.count(b"\r\n"), f"{ruta.name}: saltos sueltos"

    def test_el_arranque_al_prender_el_pc_sigue_puesto(self):
        t = _texto(INSTALADOR)
        assert "/SC ONSTART" in t
        assert "/DELAY 0001:00" in t

    def test_la_red_de_seguridad_del_autodespliegue_sigue_ahi(self):
        t = _texto(TOOLS / "autodeploy_motor_local.cmd")
        assert "el motor NO volvio solo: se arranca directo" in t
        assert "-m uvicorn app.main:app" in t
