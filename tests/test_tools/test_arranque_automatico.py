"""El motor tiene que arrancar solo al prender el PC (21-08-2026).

El arranque estaba en la **carpeta Inicio** de Windows, que se dispara al
INICIAR SESIÓN. O sea: si el PC se reinicia de noche y nadie entra, el hospital
amanece sin portal.

Pasó el 21-08 a las 8:57 de la mañana: «Bad gateway · Host Error», y hubo que
sacar el motor a mano por PowerShell.

`tools/ARRANQUE_AUTOMATICO_MOTOR.cmd` crea una tarea de Windows que arranca al
**prender** el equipo, sin que nadie inicie sesión.

LAS DOS DECISIONES QUE ESTAS PRUEBAS CUIDAN:

1. **Corre con la cuenta del usuario, no con la del sistema.** El motor
   necesita entrar a `\\\\Prime\\radicacion_2026` para el índice de soportes, y
   la cuenta del sistema normalmente no tiene ese permiso. Windows pide la
   contraseña y la guarda en su bóveda: NO puede quedar escrita en el
   repositorio.

2. **Espera un minuto tras el arranque.** Al prender el PC la red del hospital
   todavía no está lista.
"""

from __future__ import annotations

import re
from pathlib import Path

RUTA = Path(__file__).resolve().parents[2] / "tools" / "ARRANQUE_AUTOMATICO_MOTOR.cmd"


def _texto() -> str:
    return RUTA.read_bytes().decode("utf-8", errors="replace")


def _linea_schtasks() -> str:
    t = _texto()
    m = re.search(r"^schtasks /Create.*?(?:\n.*?)?$", t, re.M)
    assert m, "no se encontró el comando que crea la tarea"
    i = t.index("schtasks /Create")
    return t[i : i + 300]


class TestLaTareaArrancaAlPrenderElPC:
    def test_existe_el_instalador(self):
        assert RUTA.is_file()

    def test_la_tarea_es_al_arrancar_no_al_iniciar_sesion(self):
        """`ONSTART` = al prender el equipo. `ONLOGON` sería el mismo problema
        que tenemos hoy."""
        linea = _linea_schtasks()
        assert "/SC ONSTART" in linea
        assert "ONLOGON" not in linea

    def test_espera_a_que_la_red_este_lista(self):
        assert "/DELAY 0001:00" in _linea_schtasks()

    def test_se_puede_correr_dos_veces(self):
        """`/F` reemplaza la tarea si ya existe: correrlo de nuevo no duplica
        ni falla."""
        assert "/F" in _linea_schtasks()

    def test_apunta_al_lanzador_de_siempre(self):
        """No inventa una forma nueva de arrancar: usa el mismo lanzador que ya
        usaban la carpeta Inicio y el autodespliegue."""
        assert "arrancar_motor_glosas.cmd" in _texto()


class TestCorreConLaCuentaDelUsuario:
    def test_usa_la_cuenta_de_quien_lo_instala(self):
        assert "/RU" in _linea_schtasks()
        assert "%USERDOMAIN%\\%USERNAME%" in _texto()

    def test_la_contrasena_la_pide_windows(self):
        """`/RP *` hace que la pida por teclado."""
        assert "/RP *" in _linea_schtasks()

    def test_no_hay_ninguna_contrasena_escrita(self):
        """Regla del repositorio: nunca commitear usuarios ni contraseñas."""
        t = _texto().lower()
        for pista in ("password=", "contrasena=", "contraseña=", '/rp "', "/rp '"):
            assert pista not in t, f"parece haber una contraseña escrita: {pista}"

    def test_explica_por_que_pide_la_contrasena(self):
        """Si no se explica, el auditor no sabe si es seguro escribirla."""
        t = _texto()
        assert "Prime" in t and "radicacion_2026" in t
        assert "boveda de Windows" in t or "bóveda de Windows" in t

    def test_no_pide_permisos_de_administrador_que_no_necesita(self):
        assert "/RL HIGHEST" not in _linea_schtasks()


class TestNoRompeNadaDeLoQueYaFunciona:
    def test_avisa_que_lo_demas_sigue_igual(self):
        t = _texto()
        assert "vigilante" in t
        assert "autodespliegue" in t or "autodeploy" in t

    def test_si_falla_lo_dice_y_no_deja_el_motor_peor(self):
        t = _texto()
        assert "pudo crear la tarea" in t
        assert "No se rompio nada" in t or "no se rompio nada" in t.lower()

    def test_comprueba_que_la_tarea_quedo(self):
        """Crear no es lo mismo que quedar: se consulta después."""
        assert "schtasks /Query" in _texto()

    def test_dice_como_comprobarlo_de_verdad(self):
        """Reiniciar el PC y abrir el portal desde otro equipo. Sin eso, uno
        cree que quedó y se entera el día que falle."""
        t = _texto()
        assert "reinicie el PC" in t.lower() or "reinicie el pc" in t.lower()

    def test_avisa_de_la_contrasena_vencida(self):
        """Si cambia la contraseña de Windows, la tarea deja de arrancar EN
        SILENCIO. Es la forma más probable de que esto se rompa dentro de seis
        meses."""
        assert "cambia su contrasena" in _texto() or "cambia su contraseña" in _texto()


class TestElArchivoSirveEnWindows:
    def test_conserva_los_finales_de_linea_de_windows(self):
        """Con finales de Unix la ventana se cierra sin ejecutar nada. Ya se
        sufrió antes en este repositorio."""
        b = RUTA.read_bytes()
        assert b.count(b"\r\n") > 50
        assert b.count(b"\n") == b.count(b"\r\n"), "hay saltos de línea sueltos"

    def test_no_se_cierra_sin_que_el_auditor_lea(self):
        assert _texto().rstrip().endswith("endlocal")
        assert "pause" in _texto()

    def test_avisa_si_el_motor_no_esta_instalado(self):
        t = _texto()
        assert "REVIVIR_EXPRESS_SIN_DOCKER" in t
