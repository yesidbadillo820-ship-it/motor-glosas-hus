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


class TestLeDiceCualEsLaCuentaBuena:
    """El auditor le dio Enter a la cuenta que mostraba la ventana —la de
    administrador— y la tarea quedó con la cuenta equivocada. Preguntar no
    bastó: hay que **decirle cuál es la buena**.

    Y el propio PC ya lo sabe: es la cuenta con la que corre el
    autodespliegue, que lleva meses funcionando y sí entra a la carpeta de
    soportes del servidor.
    """

    def test_lee_la_cuenta_que_ya_usa_el_motor(self):
        t = _texto()
        assert "MotorGlosas_Autodeploy" in t and "Principal.UserId" in t, (
            "El instalador no averigua con qué cuenta trabaja hoy el motor, y "
            "el auditor se queda adivinando."
        )

    def test_se_la_muestra_antes_de_preguntar(self):
        """Mostrarla después de que ya escribió no sirve de nada."""
        t = _texto()
        assert t.index("SUGERIDA") < t.index("set /p")

    def test_le_dice_que_escriba_esa_si_no_coincide(self):
        assert "escriba ESTA" in _texto()

    def test_si_no_se_puede_averiguar_no_estorba(self):
        """En un PC sin esa tarea la variable queda vacía y el aviso no sale:
        el instalador tiene que seguir funcionando igual."""
        t = _texto()
        assert 'set "SUGERIDA="' in t
        assert "if defined SUGERIDA" in t


class TestNoCantarVictoriaAMedias:
    """Lo que pasó: la segunda contraseña se escribió mal, el autodespliegue
    NO quedó cambiado… y el mensaje final decía igual «El autodespliegue sigue
    bajando el codigo nuevo cada 5 min», como si todo hubiera salido bien.

    Un instalador que dice que quedó lo que no quedó es peor que uno que
    falla: el auditor se va tranquilo con la mitad del trabajo sin hacer.
    """

    def test_se_acuerda_de_si_el_autodespliegue_quedo(self):
        assert "AUTODEPLOY_OK" in _texto()

    def test_el_mensaje_final_depende_de_como_fue(self):
        t = _texto()
        i = t.index("Lo que NO cambio")
        despues = t[i:]
        assert "if defined AUTODEPLOY_OK" in despues, (
            "El mensaje final dice lo mismo salga bien o salga mal."
        )

    def test_si_no_quedo_lo_dice_con_todas_las_letras(self):
        t = _texto()
        assert "el autodespliegue NO quedo cambiado" in t
        assert "SOLO si alguien inicio sesion" in t

    def test_y_dice_como_terminarlo(self):
        assert "Vuelva a correr este archivo para terminar de dejarlo" in _texto()

    def test_si_quedo_tambien_lo_dice(self):
        assert "ahora tambien con el PC recien prendido" in _texto()


class TestNoDejarElPcPeorDeComoEstaba:
    """Lo que pasó de verdad el 21-08, en tres actos:

    1. Por la mañana la tarea de arranque quedó creada.
    2. Por la tarde, un intento sin permisos contestó «Acceso denegado».
    3. Por la noche ya no había tarea de arranque.

    La causa: crear la tarea usa `/F`, que primero borra la que hubiera. Si
    después falla, se queda **sin ninguna**. El intento dejó el PC peor de como
    estaba, y de eso nadie se entera hasta el próximo reinicio — que es
    exactamente cuando ya no se puede hacer nada.
    """

    def test_pregunta_por_los_permisos_antes_de_tocar_nada(self):
        t = _texto()
        assert "net session" in t, (
            "No se comprueba si hay permisos de administrador. Sin eso, un "
            "intento fallido borra la tarea que ya funcionaba."
        )

    def test_y_lo_pregunta_ANTES_de_crear_la_tarea(self):
        """Comprobarlo después no sirve de nada: el daño ya está hecho."""
        t = _texto()
        assert t.index("net session") < t.index("schtasks /Create"), (
            "La comprobación de permisos quedó DESPUÉS de crear la tarea."
        )

    def test_si_no_hay_permisos_se_va_sin_hacer_nada(self):
        t = _texto()
        i = t.index("net session")
        despues = t[i : i + 1200]
        assert "exit /b 1" in despues
        assert "No se toco nada" in despues

    def test_y_explica_como_abrirlo_bien(self):
        t = _texto()
        i = t.index("net session")
        despues = t[i : i + 1200]
        assert "Ejecutar como administrador" in despues

    def test_avisa_de_la_otra_cuenta_desde_ese_mismo_aviso(self):
        """Es el momento en que el auditor va a elevar la ventana: avisarle
        después sería tarde."""
        t = _texto()
        i = t.index("net session")
        despues = t[i : i + 1200]
        assert "NO la de administrador" in despues

    def test_si_aun_asi_falla_avisa_que_puede_no_quedar_ninguna(self):
        """El caso que quedó sin contar: falló, y la que había ya no está."""
        t = _texto()
        assert "AHORA NO HAY NINGUNA" in t
        assert "ESTADO_MOTOR.cmd" in t


class TestLaTrampaDeEjecutarComoAdministrador:
    """Crear una tarea con contraseña guardada exige permisos de
    administrador: sin ellos, `schtasks` contesta «Acceso denegado». Pero al
    abrir la ventana como administrador, si Windows pide OTRA cuenta, la
    ventana pasa a correr con ESA otra y `%USERNAME%` ya no es la del auditor.

    Así fue como la tarea del 21-08 quedó puesta con `cpimiento` cuando la
    cuenta del motor es `cartera`. Y no da error: la tarea queda, el motor
    arranca, y si esa cuenta no entra a la carpeta de soportes del servidor,
    el índice amanece vacío sin que nadie entienda por qué.
    """

    def test_pregunta_con_que_cuenta_en_vez_de_suponer(self):
        t = _texto()
        assert "set /p" in t and "OTRA" in t, (
            "El instalador vuelve a suponer que la cuenta correcta es la de "
            "la ventana. Con «Ejecutar como administrador» eso es falso."
        )

    def test_lo_que_escriba_el_auditor_manda(self):
        t = _texto()
        assert 'if not "%OTRA%"=="" set "CUENTA=%OTRA%"' in t

    def test_avisa_de_la_trampa_antes_de_preguntar(self):
        """Preguntar sin explicar por qué no sirve de nada: el auditor daría
        Enter sin pensarlo."""
        t = _texto().lower()
        assert "administrador" in t and "otra cuenta" in t

    def test_explica_para_que_sirve_esa_cuenta(self):
        """La razón concreta: es la que entra a la carpeta de soportes."""
        assert "soportes" in _texto().lower()

    def test_dice_al_final_con_que_cuenta_quedo(self):
        """Sin esto, el auditor no tiene cómo enterarse de que quedó puesta
        con la cuenta equivocada."""
        t = _texto()
        assert "Corre con la cuenta:  %CUENTA%" in t

    def test_el_mensaje_de_error_nombra_el_acceso_denegado(self):
        """Es el texto exacto que sale en pantalla. Si el mensaje de ayuda no
        lo nombra, el auditor no sabe cuál de las causas es la suya."""
        t = _texto()
        assert "Acceso denegado" in t

    def test_y_avisa_de_no_poner_la_cuenta_de_administrador(self):
        t = _texto().lower()
        assert "no la de administrador" in t


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
