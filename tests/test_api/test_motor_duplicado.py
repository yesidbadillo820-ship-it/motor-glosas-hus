"""Dos motores vivos = dos verdades. El sistema tiene que decirlo.

Incidente 04-08-2026 (equipo local, Windows): el auditor cambió la clave de
Groq, reinició y el log de arranque escribió `groq=OK gsk_vn06EE…`. La
pantalla de Diagnóstico —que lee la MISMA variable— mostraba `gsk_5CxaRq…`
y el análisis fallaba con «su clave está inválida o vencida». Dos valores de
una sola variable en un solo proceso es imposible: había dos `uvicorn` vivos
sobre el puerto 8000, y las peticiones caían en cualquiera de los dos. El
viejo respondía con la clave anterior y con el código anterior.

Lo que sellan estas pruebas:
  1. Un motor con `--reload` (dos procesos) NO se cuenta como dos.
  2. Dos motores independientes se detectan y el panel se pone en ROJO.
  3. El aviso de clave rechazada dice CUÁL clave se usó (los 10 primeros
     caracteres), que es el dato que permite compararlo con el log.
  4. La prueba de proveedores avisa si hay más de un motor: si no, el
     auditor ve «verde» y el análisis igual le falla.
  5. Existe el bot de doble clic que cierra los sobrantes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import ROL_SUPER_ADMIN, UsuarioRecord
from app.services import motor_proceso as mp

RAIZ = Path(__file__).resolve().parent.parent.parent


class _Proc:
    """Lo mínimo que `motores_vivos()` le pide a psutil.process_iter."""

    def __init__(self, pid, ppid, cmdline, create_time=1_700_000_000.0):
        self.info = {
            "pid": pid,
            "ppid": ppid,
            "cmdline": cmdline,
            "create_time": create_time,
        }


UVICORN = ["uvicorn", "app.main:app", "--port", "8000"]
UVICORN_RELOAD = ["uvicorn", "app.main:app", "--reload"]
# El motor que sirve la página por internet en el PC del hospital: mismo
# programa, otro puerto, otra instalación. Ver TestDosMotoresNoEsLoMismoQue…
UVICORN_TUNEL = [
    "C:\\motor-glosas\\repo\\venv\\Scripts\\python.exe",
    "-m",
    "uvicorn",
    "app.main:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8080",
]


def _procesos(monkeypatch, lista):
    import psutil

    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: list(lista))


class TestQuienEsUnMotor:
    def test_uvicorn_de_esta_app_lo_es(self):
        assert mp._es_motor(UVICORN) is True

    def test_gunicorn_tambien(self):
        assert mp._es_motor(["gunicorn", "app.main:app", "-k", "uvicorn.workers"]) is True

    def test_pytest_no_es_un_motor(self):
        """Importar la app no es servirla: pytest no atiende el puerto."""
        assert mp._es_motor(["pytest", "tests/test_api"]) is False

    def test_otro_uvicorn_de_otro_proyecto_no_cuenta(self):
        assert mp._es_motor(["uvicorn", "otra_cosa:app"]) is False

    def test_sin_cmdline_no_revienta(self):
        assert mp._es_motor(None) is False
        assert mp._es_motor([]) is False


class TestContarMotores:
    def test_reload_son_dos_procesos_pero_un_solo_motor(self, monkeypatch):
        """`uvicorn --reload` deja el vigilante y el que sirve. Contarlos como
        dos motores sería una falsa alarma en cada arranque."""
        _procesos(
            monkeypatch,
            [_Proc(100, 1, UVICORN_RELOAD), _Proc(101, 100, UVICORN_RELOAD)],
        )
        assert len(mp.motores_vivos()) == 1

    def test_dos_motores_independientes_se_detectan(self, monkeypatch):
        _procesos(
            monkeypatch,
            [
                _Proc(100, 1, UVICORN, create_time=1_700_000_000.0),
                _Proc(200, 1, UVICORN, create_time=1_700_009_999.0),
            ],
        )
        vivos = mp.motores_vivos()
        assert [m["pid"] for m in vivos] == [100, 200]  # el más viejo primero

    def test_un_proceso_que_no_deja_leerse_no_tumba_el_conteo(self, monkeypatch):
        class _Rota:
            @property
            def info(self):
                raise RuntimeError("acceso denegado")

        _procesos(monkeypatch, [_Rota(), _Proc(100, 1, UVICORN)])
        assert len(mp.motores_vivos()) == 1

    def test_sin_psutil_no_revienta(self, monkeypatch):
        import builtins

        real = builtins.__import__

        def _falla(nombre, *a, **k):
            if nombre == "psutil":
                raise ImportError("no está")
            return real(nombre, *a, **k)

        monkeypatch.setattr(builtins, "__import__", _falla)
        assert mp.motores_vivos() == []


class TestElPuertoDeCadaMotor:
    def test_lo_lee_de_la_linea_de_comando(self):
        assert mp.puerto_de(UVICORN_TUNEL) == "8080"
        assert mp.puerto_de(UVICORN) == "8000"

    def test_tambien_con_igual(self):
        assert mp.puerto_de(["uvicorn", "app.main:app", "--port=9000"]) == "9000"

    def test_sin_puerto_es_el_de_siempre(self):
        assert mp.puerto_de(UVICORN_RELOAD) == ""  # el valor por defecto lo pone quien pregunta
        assert mp.motores_vivos.__doc__  # el default (8000) se aplica en motores_vivos

    def test_no_revienta_sin_linea_de_comando(self):
        assert mp.puerto_de(None) == ""
        assert mp.puerto_de(["uvicorn", "app.main:app", "--port"]) == ""


class TestDosMotoresNoEsLoMismoQueUnSobrante:
    """04-08-2026, la lección cara del día.

    El aviso decía «hay 2 motores, cerrá los sobrantes» y el auditor cerró
    el del puerto 8080: el que sirve la página por internet. No sobraba —
    era el OTRO sistema, con su propia copia de las claves, y era el que su
    navegador estaba usando. De ahí venía el enredo entero: el arranque del
    puerto 8000 mostraba la clave nueva y la pantalla, servida por el 8080,
    mostraba la vieja.
    """

    def test_mismo_puerto_es_pelea_de_verdad(self, monkeypatch):
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN), _Proc(200, 1, UVICORN)])
        est = mp.estado_motor()
        assert est["estado"] == "error"
        assert "mismo puerto" in est["mensaje"]
        assert "Cerrá el sobrante" in est["mensaje"]

    def test_puertos_distintos_no_es_error_y_no_manda_a_cerrar_nada(self, monkeypatch):
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN_TUNEL), _Proc(200, 1, UVICORN)])
        est = mp.estado_motor()
        assert est["estado"] == "warning"
        assert "cerrá los sobrantes" not in est["mensaje"].lower()
        assert "reiniciar TODAS" in est["mensaje"]

    def test_avisa_que_el_8080_es_la_pagina_por_internet(self, monkeypatch):
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN_TUNEL), _Proc(200, 1, UVICORN)])
        est = mp.estado_motor()
        assert "8080" in est["mensaje"]
        assert "internet" in est["mensaje"]
        assert "NO lo cierres" in est["mensaje"]

    def test_el_puerto_de_cada_uno_viaja_en_el_aviso(self, monkeypatch):
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN_TUNEL), _Proc(200, 1, UVICORN)])
        est = mp.estado_motor()
        assert "puerto 8080" in est["mensaje"] and "puerto 8000" in est["mensaje"]
        assert {m["puerto"] for m in est["data"]["motores"]} == {"8080", "8000"}


class TestElAmbienteViejoQueTapaLaClaveNueva:
    """La causa de fondo del 04-08-2026, la que nadie podía ver.

    `servidor_motor_local.cmd` volcaba el `.env` al ambiente UNA vez, antes
    de su bucle de vigilancia. Cada vez que revivía el servidor le entregaba
    el ambiente de horas antes; y como las variables de entorno le ganan al
    archivo, el motor de la página por internet siguió respondiendo «su
    clave está inválida» con la clave vieja (gsk_5CxaRq) mientras el archivo
    ya tenía la nueva (gsk_vn06EE). Cada mitad decía la verdad por separado
    y el conjunto mentía.
    """

    def test_detecta_que_el_ambiente_no_coincide_con_el_archivo(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("GROQ_API_KEY=gsk_vn06EEnueva\n", encoding="utf-8")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_5CxaRqvieja")

        d = mp.claves_desajustadas(str(env))
        assert len(d) == 1
        assert d[0]["clave"] == "GROQ_API_KEY"
        assert d[0]["en_uso"] == "gsk_5CxaRq"
        assert d[0]["en_el_archivo"] == "gsk_vn06EE"

    def test_si_coinciden_no_dice_nada(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("GROQ_API_KEY=gsk_igual\n", encoding="utf-8")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_igual")
        assert mp.claves_desajustadas(str(env)) == []

    def test_las_comillas_del_archivo_no_cuentan_como_diferencia(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text('GROQ_API_KEY="gsk_igual"\n', encoding="utf-8")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_igual")
        assert mp.claves_desajustadas(str(env)) == []

    def test_un_comentario_al_final_de_la_linea_no_es_desajuste(self, tmp_path, monkeypatch):
        env = tmp_path / ".env"
        env.write_text("GROQ_API_KEY=gsk_igual # la nueva del 04-08\n", encoding="utf-8")
        monkeypatch.setenv("GROQ_API_KEY", "gsk_igual")
        assert mp.claves_desajustadas(str(env)) == []

    def test_sin_archivo_env_no_inventa_desajustes(self, tmp_path):
        assert mp.claves_desajustadas(str(tmp_path / "no-existe.env")) == []

    def test_lo_que_solo_esta_en_un_lado_no_es_desajuste(self, tmp_path, monkeypatch):
        """Docker y systemd mandan claves que el archivo no tiene: eso es
        normal, no un ambiente viejo."""
        env = tmp_path / ".env"
        env.write_text("GROQ_API_KEY=gsk_solo_archivo\n", encoding="utf-8")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        assert mp.claves_desajustadas(str(env)) == []

    def test_el_diagnostico_lo_pone_en_rojo_antes_que_nada(self, monkeypatch):
        monkeypatch.setattr(
            mp,
            "claves_desajustadas",
            lambda *a: [
                {"clave": "GROQ_API_KEY", "en_uso": "gsk_5CxaRq", "en_el_archivo": "gsk_vn06EE"}
            ],
        )
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN)])
        est = mp.estado_motor()
        assert est["estado"] == "error"
        assert "NO está usando las claves del archivo" in est["mensaje"]
        assert "gsk_5CxaRq" in est["mensaje"] and "gsk_vn06EE" in est["mensaje"]
        assert "MotorGlosasServidor" in est["mensaje"]


class TestElVigilanteReleeLasClaves:
    def test_el_env_se_carga_dentro_del_bucle(self):
        """Si el volcado del .env queda ANTES del bucle, cada reinicio
        automático revive el servidor con las claves de horas antes."""
        cmd = (RAIZ / "tools" / "servidor_motor_local.cmd").read_text(encoding="utf-8")
        assert ":loop" in cmd
        cuerpo = cmd.split(":loop", 1)[1]
        assert ".env" in cuerpo, "el .env ya no se relee en cada vuelta del vigilante"
        assert "usebackq eol=#" in cuerpo

    def test_el_autodeploy_solo_reinicia_el_de_produccion(self):
        """Cerraba cualquier uvicorn de la aplicación cada 5 minutos: le
        mataba el motor de pruebas al auditor sin explicación."""
        cmd = (RAIZ / "tools" / "autodeploy_motor_local.cmd").read_text(encoding="utf-8")
        assert "8080" in cmd.split("Stop-Process")[0].rsplit("powershell", 1)[-1]


class TestEstadoDelMotor:
    def test_uno_solo_es_verde_y_dice_la_clave_en_uso(self, monkeypatch):
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN)])
        monkeypatch.setattr(
            mp,
            "claves_en_uso",
            lambda: {"groq": "gsk_vn06EE", "anthropic": "", "gemini": "", "principal": "groq"},
        )
        est = mp.estado_motor()
        assert est["estado"] == "ok"
        assert "gsk_vn06EE" in est["mensaje"]
        assert "GROQ" in est["mensaje"]

    def test_dos_es_rojo_y_nombra_los_pid(self, monkeypatch):
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN), _Proc(200, 1, UVICORN)])
        est = mp.estado_motor()
        assert est["estado"] == "error"
        assert "PID 100" in est["mensaje"] and "PID 200" in est["mensaje"]
        assert "REINICIAR_MOTOR.cmd" in est["mensaje"]
        assert len(est["data"]["motores"]) == 2

    def test_la_clave_viaja_recortada_nunca_completa(self, monkeypatch):
        from app.core.config import get_settings

        cfg = get_settings()
        monkeypatch.setattr(cfg, "groq_api_key", "gsk_" + "S" * 60, raising=False)
        claves = mp.claves_en_uso()
        assert claves["groq"] == "gsk_SSSSSS"
        assert len(claves["groq"]) == 10


# ─── El panel de Diagnóstico lo muestra primero ───────────────────────────


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def cliente(db_session):
    from app.api.deps import get_usuario_actual
    from app.main import app

    usuario = UsuarioRecord(
        id=1, email="admin@hus.gov.co", nombre="Admin", rol=ROL_SUPER_ADMIN, activo=1
    )
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestDiagnostico:
    def test_la_seccion_motor_va_primero(self, cliente):
        d = cliente.get("/admin/diagnostico").json()
        assert list(d["secciones"])[0] == "motor"

    def test_dos_motores_ponen_el_panel_en_rojo(self, cliente, monkeypatch):
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN), _Proc(200, 1, UVICORN)])
        d = cliente.get("/admin/diagnostico").json()
        assert d["secciones"]["motor"]["estado"] == "error"
        assert d["estado_global"] == "error"

    def test_si_falla_la_inspeccion_el_panel_igual_llega(self, cliente, monkeypatch):
        monkeypatch.setattr(
            mp, "estado_motor", lambda: (_ for _ in ()).throw(RuntimeError("sin permisos"))
        )
        d = cliente.get("/admin/diagnostico").json()
        assert d["secciones"]["motor"]["estado"] == "warning"
        assert "base_de_datos" in d["secciones"]


class TestElAvisoDiceQueClaveUso:
    """«Pero si ya la cambié» — el aviso tiene que permitir comprobarlo."""

    def test_la_causa_de_clave_lleva_el_prefijo(self):
        from app.services.glosa_service import _mensaje_ia_caida

        fallos = [
            ("groq", Exception("Error code: 401 - invalid_api_key"), "gsk_5CxaRq"),
            ("anthropic", Exception("connection reset"), "sk-ant-api"),
        ]
        m = _mensaje_ia_caida(fallos[-1][1], fallos)
        assert "GROQ: su clave está inválida o vencida (la que usó: gsk_5CxaRq…)" in m
        # La causa que no es de clave no se ensucia con el prefijo
        assert "sk-ant-api" not in m

    def test_las_tuplas_de_dos_siguen_sirviendo(self):
        """Compatibilidad con las llamadas anteriores (sin prefijo)."""
        from app.services.glosa_service import _mensaje_ia_caida

        m = _mensaje_ia_caida(Exception("x"), [("groq", Exception("429 rate limit"))])
        assert "GROQ: está en límite de uso" in m

    def test_el_servicio_guarda_el_prefijo_de_cada_clave(self):
        from app.services.glosa_service import GlosaService

        svc = GlosaService(groq_api_key="gsk_ABCDEFGHIJKLM", anthropic_api_key="sk-ant-XYZ")
        assert svc.pref_clave["groq"] == "gsk_ABCDEF"
        assert svc.pref_clave["anthropic"] == "sk-ant-XYZ"[:10]


def _claves_de_prueba(monkeypatch, groq="gsk_PROBADA123456", anthropic="sk-ant-PRUEBA"):
    """Claves de mentira y proveedores que contestan: la prueba no sale a red."""
    from app.core.config import get_settings
    from app.services import glosa_service as gs

    cfg = get_settings()
    monkeypatch.setattr(cfg, "groq_api_key", groq, raising=False)
    monkeypatch.setattr(cfg, "anthropic_api_key", anthropic, raising=False)
    monkeypatch.setattr(cfg, "primary_ai", "groq", raising=False)

    async def _responde(self, system, user, **kw):
        return ("LISTO", "llama-3.3-70b")

    monkeypatch.setattr(gs.GlosaService, "_llamar_groq_con_retry", _responde)
    monkeypatch.setattr(gs.GlosaService, "_llamar_anthropic", _responde)


class TestProbarProveedoresAvisaDelDuplicado:
    def test_con_dos_motores_el_veredicto_avisa(self, cliente, monkeypatch):
        """Sin esto el auditor ve «Todo listo» y el análisis igual le falla:
        la prueba la contestó un motor y el análisis cae en el otro."""
        _claves_de_prueba(monkeypatch)
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN), _Proc(200, 1, UVICORN)])
        d = cliente.get("/gobierno-ia/probar-proveedores").json()
        assert d["motores_vivos"] == 2
        assert "2 motores" in d["veredicto"]

    def test_con_un_solo_motor_el_veredicto_queda_limpio(self, cliente, monkeypatch):
        _claves_de_prueba(monkeypatch)
        _procesos(monkeypatch, [_Proc(100, 1, UVICORN)])
        d = cliente.get("/gobierno-ia/probar-proveedores").json()
        assert d["motores_vivos"] == 1
        assert "motores" not in d["veredicto"]

    def test_cada_proveedor_dice_que_clave_probo(self, cliente, monkeypatch):
        _claves_de_prueba(monkeypatch, anthropic="")
        d = cliente.get("/gobierno-ia/probar-proveedores").json()
        groq = next(p for p in d["proveedores"] if p["proveedor"] == "groq")
        assert groq["clave_probada"] == "gsk_PROBAD"
        anth = next(p for p in d["proveedores"] if p["proveedor"] == "anthropic")
        assert anth["estado"] == "SIN CLAVE"
        assert anth["clave_probada"] == ""


class TestUnaClaveVencidaNoApagaElRazonador:
    """Destapado al escribir estas pruebas.

    Cuando la API rechazaba `reasoning_effort`, el motor lo apagaba para TODO
    el proceso. El detector aceptaba `invalid_request_error` — que es el tipo
    que Groq devuelve también cuando la clave está vencida o el contexto es
    muy largo. Resultado: una sola llamada con la clave mala dejaba a
    gpt-oss-120b sin razonador hasta el próximo reinicio, y los dictámenes
    salían más pobres sin que nada lo dijera.
    """

    def _corre(self, monkeypatch, mensaje_error):
        import asyncio

        from app.services import glosa_service as gs

        monkeypatch.setattr(gs, "_GROQ_SDK_SOPORTA_REASONING_EFFORT", True, raising=False)

        class _Groq:
            def __init__(self):
                self.chat = self
                self.completions = self

            async def create(self, **kw):
                raise RuntimeError(mensaje_error)

        svc = gs.GlosaService(groq_api_key="gsk_x", groq_model="openai/gpt-oss-120b")
        svc.groq = _Groq()
        with pytest.raises(Exception):
            asyncio.run(svc._llamar_groq_con_retry("sys", "user"))
        return gs._GROQ_SDK_SOPORTA_REASONING_EFFORT

    def test_la_clave_vencida_deja_el_razonador_encendido(self, monkeypatch):
        sigue = self._corre(
            monkeypatch,
            "Error code: 401 - {'error': {'type': 'invalid_request_error', "
            "'code': 'invalid_api_key'}}",
        )
        assert sigue is True

    def test_el_rechazo_del_parametro_si_lo_apaga(self, monkeypatch):
        sigue = self._corre(monkeypatch, "400 Unknown parameter: reasoning_effort")
        assert sigue is False


class TestPantalla:
    def test_la_prueba_de_proveedores_muestra_la_clave_y_el_duplicado(self):
        html = (RAIZ / "static" / "index.html").read_text(encoding="utf-8", errors="ignore")
        assert "p.clave_probada" in html
        assert "d.motores_vivos > 1" in html
        # Y NO manda a cerrar nada: el otro motor puede ser el de la página
        # por internet (04-08-2026).
        assert "cerrá los sobrantes" not in html
        assert "su propia copia de las claves" in html

    def test_el_panel_de_diagnostico_nombra_la_tarjeta(self):
        html = (RAIZ / "static" / "index.html").read_text(encoding="utf-8", errors="ignore")
        assert "'motor': 'Motor (quién está atendiendo)'" in html


class TestElBotDeDobleClic:
    def _ps(self):
        return (RAIZ / "tools" / "reiniciar_motor.ps1").read_text(encoding="utf-8")

    def test_existe_y_cierra_antes_de_arrancar(self):
        cmd = (RAIZ / "tools" / "REINICIAR_MOTOR.cmd").read_text(encoding="utf-8")
        assert "reiniciar_motor.ps1" in cmd
        assert "uvicorn app.main:app" in cmd
        # Primero cerrar, después arrancar: al revés no sirve de nada.
        assert cmd.index("reiniciar_motor.ps1") < cmd.index("uvicorn app.main:app")

    def test_si_no_pudo_dejar_libre_el_puerto_no_arranca(self):
        """Arrancar encima de algo vivo es repetir el enredo."""
        cmd = (RAIZ / "tools" / "REINICIAR_MOTOR.cmd").read_text(encoding="utf-8")
        assert "errorlevel 1" in cmd
        assert cmd.index("errorlevel 1") < cmd.index("uvicorn app.main:app")

    def test_solo_cierra_los_motores_de_su_propio_puerto(self):
        """Lo que costó la página pública: el bot no puede cerrar el motor
        del 8080 cuando lo que reinicia es el del 8000."""
        ps = self._ps()
        assert "$suyo -eq $Puerto" in ps
        assert "dejo VIVO el motor" in ps
        assert "sirve la pagina por internet" in ps

    def test_tambien_cierra_al_que_quedo_vivo_sin_escuchar(self):
        """El de --reload que sobrevive sin el puerto: se busca por su línea
        de comando, no solo por quién ocupa el puerto."""
        ps = self._ps()
        assert "Win32_Process" in ps
        assert "Stop-Process" in ps

    def test_comprueba_que_de_verdad_murieron(self):
        """`-ErrorAction SilentlyContinue` se tragaba el «acceso denegado» y
        el bot informaba cerrado algo que seguía vivo."""
        ps = self._ps()
        assert "Get-Process -Id" in ps
        assert "sobrevivientes" in ps
        assert "exit 1" in ps

    def test_el_puerto_se_consulta_sin_depender_del_idioma(self):
        """En un Windows en español netstat dice ESCUCHANDO, no LISTENING:
        el filtro viejo no encontraba nunca nada en el PC del hospital."""
        ps = self._ps()
        assert "Get-NetTCPConnection" in ps
        codigo = "\n".join(ln for ln in ps.splitlines() if not ln.lstrip().startswith("#"))
        assert "LISTENING" not in codigo
        assert "netstat" not in codigo

    def test_no_mata_al_dueno_del_puerto_si_no_es_el_motor(self):
        ps = self._ps()
        assert "NO es el motor de glosas" in ps
        assert "no lo voy a cerrar" in ps

    def test_nunca_se_cierra_a_si_mismo(self):
        ps = self._ps()
        assert "$p.ProcessId -eq $PID" in ps

    def test_avisa_de_los_procesos_que_no_puede_ver(self):
        """Sin permisos, Windows oculta la línea de comando: descartarlos en
        silencio hacía que el bot dijera «no había ninguno» justo cuando sí."""
        ps = self._ps()
        assert "invisibles" in ps
        assert "Ejecutar como administrador" in ps

    def test_arranca_con_el_python_del_proyecto_y_con_las_claves(self):
        cmd = (RAIZ / "tools" / "REINICIAR_MOTOR.cmd").read_text(encoding="utf-8")
        assert "venv\\Scripts\\python.exe" in cmd
        assert ".env" in cmd.split("[3/3]")[0]

    def test_no_manda_a_repetir_a_ciegas(self):
        """El consejo «cierra esta ventana y volvé a dar doble clic» era un
        bucle infinito: el vigilante revive el otro motor cada 5 segundos."""
        cmd = (RAIZ / "tools" / "REINICIAR_MOTOR.cmd").read_text(encoding="utf-8")
        assert "vuelve a dar doble clic" not in cmd
        assert "[MOTORES]" in cmd

    def test_el_bot_avisa_si_falta_el_env(self):
        cmd = (RAIZ / "tools" / "REINICIAR_MOTOR.cmd").read_text(encoding="utf-8")
        assert ".env" in cmd

    def test_el_ayudante_de_powershell_tambien_va_en_crlf(self):
        ga = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
        assert "*.ps1 text eol=crlf" in ga

    def test_queda_en_crlf_como_todos_los_bots(self):
        ga = (RAIZ / ".gitattributes").read_text(encoding="utf-8")
        assert "*.cmd text eol=crlf" in ga
