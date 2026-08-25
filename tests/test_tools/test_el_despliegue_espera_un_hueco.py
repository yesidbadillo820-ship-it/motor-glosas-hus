"""El despliegue espera un hueco en vez de tumbar la página (24-08-2026).

Pedido de Yesid, textual: «necesito que cada vez que hagamos cambios y demás no
se les esté cayendo la página a los gestores a cada rato».

Aplicar código nuevo obliga a apagar el motor y volverlo a levantar: entre 15 y
30 segundos de página caída, y lo que estuviera a medio hacer se pierde. Un
dictamen que la IA estaba redactando se va con el motor, y eso son minutos de
trabajo de una médica auditora.

Ahora el bot pregunta antes. En una oficina de tres personas siempre aparece un
hueco —una llamada, un café, una reunión— y el cambio entra sin que nadie lo
note.

LO QUE ESTAS PRUEBAS CUIDAN, que es donde esto se rompe si se hace mal:

- Que **no baje el código** mientras hay gente. Bajarlo y no reiniciar sería
  peor: el motor viejo quedaría sirviendo las pantallas nuevas, y eso ya
  rompió cosas en este repositorio.
- Que **nunca se quede atascado**. Un cambio que espera para siempre no llega
  nunca, y hoy dependemos de que las correcciones lleguen el mismo día.
- Que si el motor está caído, **se aplique de una**: no hay a quién
  interrumpir, y esperar sería dejar el portal caído más tiempo.
"""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parents[2] / "tools" / "autodeploy_motor_local.cmd"


def _texto() -> str:
    return RUTA.read_bytes().decode("utf-8", errors="replace")


class TestPreguntaAntesDeTocarNada:
    def test_le_pregunta_al_motor_si_hay_gente(self):
        t = _texto()
        assert "/sistema/ocupacion" in t, (
            "El bot apaga el motor sin preguntar si hay alguien trabajando."
        )
        assert "hay_gente_trabajando" in t

    def test_pregunta_ANTES_de_bajar_el_codigo(self):
        """Bajar el código y no reiniciar deja el motor viejo sirviendo las
        pantallas nuevas. Eso ya rompió cosas acá: una pantalla llamando a una
        ruta que el motor todavía no tiene."""
        t = _texto()
        assert t.index("/sistema/ocupacion") < t.index("git reset --hard"), (
            "Se baja el código antes de preguntar: el motor viejo quedaría "
            "sirviendo las pantallas nuevas."
        )

    def test_si_hay_gente_no_toca_nada(self):
        """Se mira el bloque EXACTO, de su paréntesis de apertura al de
        cierre. Una ventana de tantos caracteres alcanzaría a incluir lo que
        viene después y la prueba diría cualquier cosa.

        Desde el 25-08-2026 hay dos bloques que empiezan igual: el de la orden
        forzada («YA») y el del ciclo automático. Este mira el AUTOMÁTICO, que
        es el que tiene que seguir respetando a las gestoras.
        """
        t = _texto()
        i = t.index('if not defined FORZADO if "%OCUPADO%"=="SI" (')
        fin = t.index("\n)", i)
        bloque = t[i:fin]
        assert "goto :asegurar" in bloque, "no se salta el despliegue"
        assert "git reset" not in bloque, "baja el código aunque haya gente"
        assert "Stop-Process" not in bloque, "apaga el motor aunque haya gente"

    def test_deja_dicho_por_que_no_aplico(self):
        """Si se salta en silencio, nadie entiende por qué el cambio no llegó."""
        assert "hay gente trabajando: el cambio espera un hueco" in _texto()

    def test_no_pregunta_si_no_hay_nada_que_aplicar(self):
        """Preguntar en cada pasada, cada 5 minutos, todo el día, para nada."""
        t = _texto()
        assert t.index('if "%LOCAL%"=="%REMOTO%"') < t.index("/sistema/ocupacion")


class TestNuncaSeQuedaAtascado:
    def test_si_el_motor_no_contesta_se_aplica_de_una(self):
        """Con el portal caído no hay a quién interrumpir, y esperar solo lo
        deja caído más tiempo."""
        t = _texto()
        assert "SINMOTOR" in t
        # Solo se aplaza cuando la respuesta es un SI rotundo.
        assert 'if "%OCUPADO%"=="SI"' in t

    def test_hay_un_techo_de_espera(self):
        t = _texto()
        assert "MINUTOS% GEQ 60" in t, (
            "Sin techo, un cambio urgente puede quedarse fuera todo el día "
            "porque siempre hay alguien conectado."
        )
        assert "se aplica igual" in t

    def test_se_acuerda_de_cuando_empezo_a_esperar(self):
        t = _texto()
        assert "deploy_aplazado.txt" in t

    def test_y_lo_olvida_cuando_ya_aplico(self):
        """Sin borrarlo, la siguiente espera arrancaría con el reloj de la
        anterior y el techo saltaría de inmediato."""
        t = _texto()
        assert 'del "%ESPERA%"' in t

    def test_si_no_se_puede_medir_la_espera_no_revienta(self):
        """`if  GEQ 60` sin número es un error de sintaxis que deja el bot a
        medias sin decir nada."""
        t = _texto()
        assert 'set "MINUTOS=0"' in t


class TestUnaSolaPasadaALaVez:
    """El registro del PC de cartera mostró «codigo nuevo detectado» **dos
    veces con medio segundo de diferencia**: dos pasadas corriendo al tiempo.

    Eso es grave. Cada pasada apaga el motor contando con revivirlo, y entre
    las dos lo dejan caído: una lo levanta y la otra lo vuelve a matar. En ese
    mismo registro, la línea siguiente fue «ALERTA: el motor sigue caido».
    """

    def test_hay_un_candado(self):
        t = _texto()
        assert "autodeploy.lock" in t, (
            "Nada impide que dos pasadas del autodespliegue corran a la vez y se peleen el motor."
        )

    def test_se_toma_antes_de_tocar_el_codigo(self):
        t = _texto()
        assert t.index(":tomar_candado") < t.index("git fetch")

    def test_la_pasada_que_sobra_se_va_sin_hacer_nada(self):
        t = _texto()
        i = t.index('if not exist "%CANDADO%" goto :tomar_candado')
        # Hasta la ETIQUETA, al principio de su renglón: buscar el nombre a
        # secas encontraría el `goto` de esta misma línea y el trozo saldría
        # vacío.
        bloque = t[i : t.index("\n:tomar_candado", i)]
        assert "exit /b 0" in bloque
        assert "otra pasada sigue trabajando" in bloque
        assert "git reset" not in bloque

    def test_se_suelta_al_terminar(self):
        """Sin soltarlo, la primera pasada bloquearía todas las demás."""
        t = _texto()
        i = t.index("\n:fin")
        assert 'del "%CANDADO%"' in t[i : i + 120]

    def test_no_se_cuenta_procesos(self):
        """Contar procesos ya salió mal este mes: la orden que contaba se
        contaba a sí misma y dejó el hospital sin portal tras un reinicio. Un
        archivo no tiene esa trampa."""
        t = _texto()
        i = t.index("CANDADO=")
        assert "Get-CimInstance" not in t[i - 900 : i]

    def test_un_candado_de_una_pasada_muerta_no_bloquea_para_siempre(self):
        """Si una pasada muere sin soltarlo, el autodespliegue no puede
        quedarse esperando a un muerto: dejaría de traer código sin avisar,
        que es exactamente lo que costó una tarde entera."""
        t = _texto()
        assert "%EDAD% GEQ 30" in t
        assert "se ignora" in t

    def test_y_si_no_se_puede_medir_su_edad_no_revienta(self):
        t = _texto()
        assert 'set "EDAD=999"' in t


class TestApagarConBuenosModales:
    def test_pide_que_se_cierre_antes_de_forzar(self):
        t = _texto()
        i = t.index("Name='python.exe'")
        bloque = t[i : i + 700]
        assert "Stop-Process -Id $p.ProcessId -ErrorAction SilentlyContinue }" in bloque, (
            "Se fuerza el cierre de una: lo que el motor estuviera contestando se corta a la mitad."
        )
        assert "Start-Sleep" in bloque

    def test_pero_termina_forzando_si_no_hace_caso(self):
        """Un motor que no cierra dejaría el puerto ocupado y el nuevo no
        podría arrancar: el portal se quedaría caído de verdad."""
        t = _texto()
        i = t.index("Name='python.exe'")
        assert "-Force" in t[i : i + 700]

    def test_sigue_apagando_solo_el_de_produccion(self):
        """El motor de pruebas del auditor, en el 8000, no se toca."""
        t = _texto()
        i = t.index("Name='python.exe'")
        assert "--port\\s+8080" in t[i : i + 700]


class TestNoSeRompioLoQueYaFuncionaba:
    def test_sigue_bajando_de_la_rama_del_hospital(self):
        assert "origin/motor-glosas" in _texto()

    def test_la_red_de_seguridad_sigue_ahi(self):
        assert "el motor NO volvio solo: se arranca directo" in _texto()

    def test_sigue_encontrando_git(self):
        assert "where git" in _texto()

    def test_conserva_los_finales_de_linea_de_windows(self):
        b = RUTA.read_bytes()
        assert b.count(b"\n") == b.count(b"\r\n"), "hay saltos de línea sueltos"

    def test_la_subrutina_queda_despues_del_final(self):
        """Si la subrutina quedara antes del `exit /b 0`, el bot se metería en
        ella al terminar y contestaría cualquier cosa.

        Se buscan las ETIQUETAS —al principio de su renglón— y no la primera
        vez que sale el nombre: `call :aplazar_o_seguir` aparece mucho antes,
        arriba, y compararía los sitios equivocados."""
        t = _texto()
        etiqueta_fin = t.index("\n:fin\r\n")
        etiqueta_sub = t.index("\n:aplazar_o_seguir\r\n")
        assert etiqueta_fin < etiqueta_sub
        assert "exit /b 0" in t[etiqueta_fin:etiqueta_sub]


class TestLaOrdenDelAuditorLeGanaALaEspera:
    """Con «YA» se aplica de una, sin esperar el hueco (25-08-2026).

    Apareció corriendo esto. El motor del hospital se quedó con el código de la
    víspera porque el auditor estaba usando el sistema, y al correr el bot a
    mano para forzarlo **se aplazó igual**: el guardia no distinguía entre el
    ciclo automático de cada 5 minutos y una orden expresa de una persona. La
    única salida era esperar la hora, y adentro iba una corrección urgente —el
    motor estaba sacando dictámenes con citas de sentencias que no existen—.

    El log de esa mañana lo dejó escrito:

        [8:14:06] hay gente trabajando: el cambio espera un hueco (0 min)
        [8:19:06] hay gente trabajando: el cambio espera un hueco (5 min)
        [8:24:06] hay gente trabajando: el cambio espera un hueco (10 min)

    La espera automática no cambió: quien la salta es una persona, que sabe lo
    que hace y puede avisarle a las gestoras antes de tumbar la página.
    """

    def test_reconoce_la_orden_de_forzar(self):
        t = _texto()
        assert '"%~1"=="YA"' in t.replace(" ", ""), (
            "el bot ya no entiende «autodeploy_motor_local.cmd YA», que es como "
            "el auditor fuerza un despliegue urgente"
        )

    def test_acepta_las_formas_en_que_uno_lo_escribe(self):
        """Nadie se acuerda de si era YA, /YA o --YA."""
        t = _texto().replace(" ", "")
        for forma in ('"%~1"=="YA"', '"%~1"=="/YA"', '"%~1"=="--YA"', '"%~1"=="FORZAR"'):
            assert forma in t, f"no reconoce la forma {forma}"

    def test_forzado_se_salta_la_espera(self):
        t = _texto()
        assert 'if defined FORZADO if "%OCUPADO%"=="SI"' in t, (
            "cuando se fuerza, ya no se salta la espera de hueco"
        )
        assert 'if not defined FORZADO if "%OCUPADO%"=="SI"' in t, (
            "la espera de hueco debe seguir aplicándose cuando NO se fuerza"
        )

    def test_queda_escrito_en_el_registro_que_se_forzo(self):
        """Si se tumbó la página a propósito, tiene que quedar constancia."""
        t = _texto()
        assert "se pidio YA: se aplica igual" in t

    def test_sin_forzar_la_espera_sigue_intacta(self):
        """La defensa que pidió Yesid no se debilitó."""
        t = _texto()
        assert "call :aplazar_o_seguir" in t
        assert "goto :asegurar" in t

    def test_la_cabecera_le_dice_al_auditor_como_se_usa(self):
        t = _texto()
        assert "autodeploy_motor_local.cmd YA" in t, (
            "el bot debe explicar arriba cómo se fuerza; nadie lee el código"
        )
