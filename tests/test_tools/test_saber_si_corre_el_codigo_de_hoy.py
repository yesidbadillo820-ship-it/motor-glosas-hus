"""«¿Estoy corriendo el código de hoy?» tiene que poder responderse (22-08-2026).

Esa pregunta estuvo horas sin respuesta el 21-08. Todo «se veía bien» —el
portal abierto, el túnel publicando, las tareas en verde— y el PC de cartera
llevaba media tarde con una versión vieja: cuatro correcciones ya publicadas
que nunca llegaron.

Lo que fallaba era el autodespliegue, y fallaba **en silencio**: anotaba una
línea y seguía de largo. Nada en pantalla decía «este PC tiene código viejo».

DOS ARREGLOS, y los dos son de visibilidad:

1. El autodespliegue **encuentra git aunque no esté en el camino de búsqueda**.
   Una tarea programada no hereda el camino del usuario: arranca con un
   entorno mínimo, y ahí `git` puede sencillamente no existir. Si aun así no
   aparece, lo dice con todas las letras en vez de callarse.
2. La pantalla de estado **responde la pregunta**: qué versión hay aquí, cuál
   es la última que se alcanzó a consultar, y qué fue lo último que dijo el
   autodespliegue de sí mismo.
"""

from __future__ import annotations

from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
AUTODEPLOY = TOOLS / "autodeploy_motor_local.cmd"
ESTADO = TOOLS / "estado_motor.ps1"


def _bot() -> str:
    return AUTODEPLOY.read_bytes().decode("utf-8", errors="replace")


def _pantalla() -> str:
    return ESTADO.read_text(encoding="utf-8")


class TestElAutodespliegueEncuentraGit:
    def test_lo_busca_donde_windows_lo_instala(self):
        t = _bot()
        assert "where git" in t, (
            "El bot da por hecho que `git` está en el camino de búsqueda. En "
            "una tarea programada eso no es cierto: arranca con un entorno "
            "mínimo y ahí git puede no existir."
        )
        for sitio in ("%ProgramFiles%", "%LOCALAPPDATA%"):
            assert sitio in t, f"no busca git en {sitio}"

    def test_lo_agrega_al_camino_en_vez_de_guardar_la_ruta(self):
        """Una ruta con espacios —«Program Files»— metida dentro de un
        `for /f` es un sitio clásico de errores en los .cmd de Windows. Con la
        carpeta en el camino, las órdenes quedan igual que siempre."""
        t = _bot()
        assert 'set "PATH=%PATH%;' in t
        assert "%GIT%" not in t, "volvió la ruta guardada en una variable"

    def test_las_ordenes_de_git_siguen_escritas_igual(self):
        t = _bot()
        for orden in (
            "git fetch origin motor-glosas",
            "git rev-parse HEAD",
            "git rev-parse origin/motor-glosas",
            "git reset --hard origin/motor-glosas",
        ):
            assert orden in t, f"se perdió `{orden}`"

    def test_si_no_aparece_lo_dice_en_vez_de_callarse(self):
        t = _bot()
        assert "NO SE ENCUENTRA GIT" in t
        assert "version vieja" in t

    def test_deja_constancia_de_cada_pasada(self):
        """Sin una línea por pasada no se puede saber si la tarea corre. El
        21-08 no se sabía ni eso."""
        assert "revisando si hay codigo nuevo" in _bot()

    def test_el_fallo_de_github_se_nombra_claro(self):
        t = _bot()
        assert "NO SE PUDO CONSULTAR GITHUB" in t
        assert "se queda con la version que tiene" in t


class TestLaPantallaResponde:
    def test_dice_que_version_esta_corriendo(self):
        t = _pantalla()
        assert "EL CODIGO QUE ESTA CORRIENDO" in t
        assert "rev-parse --short HEAD" in t

    def test_y_la_compara_con_la_publicada(self):
        t = _pantalla()
        assert "rev-parse --short origin/motor-glosas" in t
        assert "falta aplicar codigo nuevo" in t

    def test_no_pide_nada_por_internet(self):
        """La pantalla solo mira: no puede quedarse colgada esperando a la red
        del hospital. Compara con lo último que ya se había consultado."""
        t = _pantalla()
        assert "git fetch" not in t, "la pantalla de estado se conecta a internet"

    def test_muestra_lo_ultimo_que_dijo_el_autodespliegue(self):
        assert "ultimo aviso del autodespliegue" in _pantalla()

    def test_traduce_los_dos_fallos_que_dejan_el_PC_atras(self):
        t = _pantalla()
        assert "NO ENCUENTRA GIT" in t or "NO SE ENCUENTRA GIT" in t
        assert "NO SE PUDO CONSULTAR GITHUB" in t
        assert "proxy del hospital" in t

    def test_avisa_si_el_autodespliegue_no_ha_dicho_nada(self):
        """Un registro sin una sola línea suya significa que no está
        corriendo, y eso no se puede ver como normalidad."""
        assert "no ha escrito nada suyo" in _pantalla()

    def test_sigue_en_ascii(self):
        """Windows PowerShell lee este archivo como ANSI: con tildes, los
        mensajes salen rotos en pantalla."""
        for n, linea in enumerate(_pantalla().splitlines(), 1):
            assert all(ord(c) < 128 for c in linea), f"línea {n} tiene tildes"


class TestNoSeRompioLoQueYaFuncionaba:
    def test_el_autodespliegue_sigue_bajando_de_la_rama_del_hospital(self):
        assert "origin/motor-glosas" in _bot()

    def test_y_su_red_de_seguridad_sigue_ahi(self):
        assert "el motor NO volvio solo: se arranca directo" in _bot()

    def test_conserva_los_finales_de_linea_de_windows(self):
        b = AUTODEPLOY.read_bytes()
        assert b.count(b"\n") == b.count(b"\r\n"), "hay saltos de línea sueltos"
