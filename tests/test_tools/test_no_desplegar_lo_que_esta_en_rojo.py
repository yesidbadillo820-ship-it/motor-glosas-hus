"""El autodespliegue no le baja al hospital código que la revisión dejó en rojo.

Lo que lo hizo necesario, el 26-08-2026: entraron **tres defectos** al PC de
cartera antes de que nadie supiera que estaban mal. Ninguno pasó desapercibido
—la revisión automática de GitHub los cazó a los tres— pero este bot no la
esperaba: se bajaba el código apenas quedaba fusionado, así que llegaban aquí
primero. Uno dejaba muerta una dirección de la página; otro hacía que una
factura mixta se le cargara al ADRES marcada como administrativa.

LAS CUATRO DECISIONES QUE ESTAS PRUEBAS CUIDAN, y por qué cada una:

1. **En rojo no se baja nada.** Es el punto entero del cambio.
2. **No saber NO es lo mismo que saber que está mal.** Si la consulta falla
   —sin internet, sin llave, GitHub caído— se aplica igual, como hasta hoy.
   Bloquear el despliegue por una consulta fallida sería peor que el problema
   que resuelve.
3. **Una revisión CANCELADA no cuenta como verde.** Fue exactamente una
   cancelada la que dejó pasar el defecto del ADRES: en la pantalla se ve igual
   que una que todavía no termina.
4. **La orden del auditor sigue mandando.** Con `YA` se aplica aunque esté en
   rojo, y queda anotado. Así esto nunca puede dejar el hospital atascado.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
CMD = RAIZ / "tools" / "autodeploy_motor_local.cmd"
PS1 = RAIZ / "tools" / "estado_revision.ps1"


def _texto(ruta: Path) -> str:
    return ruta.read_bytes().decode("utf-8", errors="replace")


@pytest.fixture(scope="module")
def cmd() -> str:
    return _texto(CMD)


@pytest.fixture(scope="module")
def ps1() -> str:
    return _texto(PS1)


@pytest.fixture(scope="module")
def puerta(cmd: str) -> str:
    """El trozo del .cmd que decide si se baja el código."""
    ini = cmd.find("NO BAJAR CODIGO QUE LA REVISION AUTOMATICA")
    assert ini > 0, "se perdió la puerta que consulta la revisión"
    fin = cmd.find("codigo nuevo detectado", ini)
    assert fin > ini, "se perdió el final de la puerta"
    return cmd[ini:fin]


class TestLaPuertaEstaAntesDeBajarElCodigo:
    def test_existe_y_consulta_el_estado(self, puerta: str):
        assert "estado_revision.ps1" in puerta
        assert "%REMOTO%" in puerta, "tiene que preguntar por el commit que se va a bajar"

    def test_pregunta_antes_del_reset(self, cmd: str):
        """Si preguntara después, ya habría bajado el código: no serviría de nada."""
        pregunta = cmd.find("estado_revision.ps1")
        baja = cmd.find("git reset --hard origin/motor-glosas")
        assert 0 < pregunta < baja, "la consulta tiene que ir ANTES de bajarse el código"


class TestEnRojoNoSeBajaNada:
    def test_el_rojo_corta_el_despliegue(self, puerta: str):
        i = puerta.find('if "%REVISION%"=="ROJO"')
        assert i > 0, "no hay rama para el caso rojo"
        bloque = puerta[i : i + 900]
        assert "goto :asegurar" in bloque, "en rojo hay que saltar al final sin bajar el código"

    def test_el_rojo_queda_anotado_con_que_hacer(self, puerta: str):
        i = puerta.find('if "%REVISION%"=="ROJO"')
        bloque = puerta[i : i + 900]
        assert "EN ROJO" in bloque
        assert "YA" in bloque, (
            "el registro tiene que decirle al auditor cómo aplicarlo igual si lo necesita"
        )


class TestNoSaberNoEsLoMismoQueSaberQueEstaMal:
    def test_si_no_se_pudo_preguntar_se_aplica_igual(self, puerta: str):
        i = puerta.find('if "%REVISION%"=="NOSESABE"')
        assert i > 0, "falta el caso de la consulta que no contesta"
        bloque = puerta[i : i + 700]
        assert "goto :asegurar" not in bloque, (
            "sin respuesta se aplica igual, como hasta hoy: dejar el hospital sin "
            "desplegar por una consulta que falla es peor que el problema que resuelve"
        )

    def test_pero_queda_anotado(self, puerta: str):
        i = puerta.find('if "%REVISION%"=="NOSESABE"')
        bloque = puerta[i : i + 700]
        assert "no se pudo preguntar" in bloque
        assert "github_token" in bloque, "hay que decir dónde se arregla"

    def test_el_valor_por_defecto_es_no_saber(self, puerta: str):
        assert 'if not defined REVISION set "REVISION=NOSESABE"' in puerta, (
            "si PowerShell no contesta nada, la variable queda vacía y las "
            "comparaciones de .cmd se comportan raro"
        )


class TestMientrasCorreSeEspera:
    def test_corriendo_no_baja_el_codigo(self, puerta: str):
        i = puerta.find('if "%REVISION%"=="CORRIENDO"')
        assert i > 0
        bloque = puerta[i : i + 800]
        assert "goto :asegurar" in bloque

    def test_dice_cuanto_suele_tardar(self, puerta: str):
        i = puerta.find('if "%REVISION%"=="CORRIENDO"')
        bloque = puerta[i : i + 800]
        assert "9 min" in bloque, "el auditor tiene que saber que no está colgado"


class TestLaOrdenDelAuditorSigueMandando:
    @pytest.mark.parametrize("caso", ["ROJO", "CORRIENDO"])
    def test_ya_se_salta_la_puerta(self, puerta: str, caso: str):
        i = puerta.find(f'if "%REVISION%"=="{caso}"')
        bloque = puerta[i : i + 900]
        assert "if defined FORZADO" in bloque, (
            f"con YA hay que poder aplicar aunque esté {caso}: si no, una revisión "
            "roja por algo ajeno deja el hospital atascado sin salida"
        )

    def test_saltarse_el_rojo_queda_en_mayusculas(self, puerta: str):
        i = puerta.find('if "%REVISION%"=="ROJO"')
        bloque = puerta[i : i + 900]
        assert "SE APLICA IGUAL" in bloque, (
            "saltarse una revisión roja tiene que dejar un rastro que se lea de lejos"
        )


class TestElScriptQueConsulta:
    def test_solo_contesta_una_de_cuatro_palabras(self, ps1: str):
        import re

        respuestas = set(re.findall(r'Responder\s+"([A-Z]+)"', ps1))
        assert respuestas == {"VERDE", "ROJO", "CORRIENDO", "NOSESABE"}, respuestas

    def test_si_la_consulta_falla_dice_nosesabe_y_no_rojo(self, ps1: str):
        i = ps1.find("Invoke-RestMethod")
        bloque = ps1[i : i + 400]
        assert 'Responder "NOSESABE"' in bloque, "una consulta que revienta no es una revisión roja"

    def test_una_sola_en_rojo_basta(self, ps1: str):
        assert '"failure"' in ps1 and '"timed_out"' in ps1
        assert '"startup_failure"' in ps1

    def test_cancelada_no_cuenta_como_verde(self, ps1: str):
        """La lección del PR #507: una corrida cancelada nunca dio veredicto,
        y en la pantalla se ve igual que una que todavía no termina."""
        assert '"cancelled"' not in ps1.split("$buenas")[-1].split("\n")[0], (
            "«cancelled» no puede estar en la lista de conclusiones buenas"
        )
        assert "hayVeredicto" in ps1, (
            "hace falta exigir que alguna revisión haya dado veredicto de verdad"
        )

    def test_sin_revisiones_todavia_no_es_verde(self, ps1: str):
        i = ps1.find("$revisiones.Count -eq 0")
        assert i > 0
        assert 'Responder "CORRIENDO"' in ps1[i : i + 120], (
            "un commit recién llegado aún no tiene revisiones: no es verde ni rojo"
        )

    def test_pone_tls12(self, ps1: str):
        assert "Tls12" in ps1, "los Windows viejos no lo traen puesto y GitHub ya no acepta menos"

    def test_tiene_tiempo_maximo_de_espera(self, ps1: str):
        assert "TimeoutSec" in ps1, (
            "sin tope, una consulta colgada deja el autodespliegue esperando para siempre"
        )


class TestLaLlaveNuncaSeSube:
    def test_la_llave_se_lee_de_fuera_del_repositorio(self, ps1: str):
        assert "GITHUB_TOKEN" in ps1
        assert "github_token.txt" in ps1

    def test_no_hay_ninguna_llave_escrita(self, cmd: str, ps1: str):
        import re

        for nombre, texto in (("el .cmd", cmd), ("el .ps1", ps1)):
            assert not re.search(r"gh[pousr]_[A-Za-z0-9]{20,}", texto), (
                f"hay algo con pinta de llave de GitHub escrito en {nombre}"
            )

    def test_el_archivo_de_la_llave_no_esta_versionado(self):
        assert not (RAIZ / "data" / "github_token.txt").exists()
        ignorados = (RAIZ / ".gitignore").read_text(encoding="utf-8")
        assert "data/*" in ignorados, "la carpeta data no está ignorada"


class TestLosFinalesDeLineaDeWindows:
    """Con finales de línea de Linux la ventana se cierra sin ejecutar nada."""

    @pytest.mark.parametrize("ruta", [CMD, PS1], ids=["autodeploy.cmd", "estado_revision.ps1"])
    def test_conserva_crlf(self, ruta: Path):
        crudo = ruta.read_bytes()
        sueltos = crudo.replace(b"\r\n", b"").count(b"\n")
        assert sueltos == 0, f"{ruta.name} tiene {sueltos} salto(s) de línea sin CR"

    def test_la_regla_del_repositorio_los_cubre(self):
        atributos = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
        assert "*.cmd text eol=crlf" in atributos
        assert "*.ps1 text eol=crlf" in atributos
