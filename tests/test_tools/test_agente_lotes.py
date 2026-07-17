"""Tests del agente local de lotes (tools/agente_lotes.py).

Cubre la lógica compartida entre el CLI y la ventana de escritorio:
armado del comando del bot, configuración persistida y lectura del
CSV --reporte. La parte HTTP se prueba end-to-end en
tests/test_api/test_lotes.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

# El script vive en tools/ (sin __init__.py): lo importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import agente_lotes as ag  # noqa: E402

TAREA = {
    "tarea_id": 7,
    "lote_id": 3,
    "tipo": "RESPONDER_COOSALUD",
    "nombre_archivo": "lote.xlsx",
    "hoja": "BASE",
    "incluir_calidad": False,
    "total_facturas": 2,
}


class TestConstruirComando:
    def test_comando_basico(self, tmp_path):
        bot = _TOOLS / "responder_glosas_coosalud.py"
        comando = ag.construir_comando(bot, TAREA, tmp_path)
        assert comando[0] == sys.executable
        assert comando[1] == str(bot)
        assert comando[comando.index("--excel") + 1] == str(tmp_path / "lote.xlsx")
        assert comando[comando.index("--hoja") + 1] == "BASE"
        assert "--todas" in comando
        assert comando[comando.index("--reporte") + 1] == str(tmp_path / "reporte.csv")
        assert "--incluir-calidad" not in comando
        assert "--indice" not in comando
        assert "--cerrar-residuales" not in comando
        assert "--con-cabeza" not in comando

    def test_flags_opcionales(self, tmp_path):
        tarea = dict(TAREA, incluir_calidad=True)
        comando = ag.construir_comando(
            _TOOLS / "responder_glosas_coosalud.py",
            tarea,
            tmp_path,
            indice=tmp_path / "indice.txt",
            cerrar_residuales=True,
            con_cabeza=True,
        )
        assert "--incluir-calidad" in comando
        assert comando[comando.index("--indice") + 1] == str(tmp_path / "indice.txt")
        assert "--cerrar-residuales" in comando
        assert "--con-cabeza" in comando


class TestConfig:
    def test_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        config = {"url": "http://servidor:8000", "token": "abc", "con_cabeza": True}
        ag.guardar_config(config)
        assert ag.ruta_config().exists()
        assert ag.cargar_config() == config

    def test_sin_config_devuelve_dict_vacio(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path / "no-existe"))
        assert ag.cargar_config() == {}

    def test_config_corrupta_devuelve_dict_vacio(self, tmp_path, monkeypatch):
        monkeypatch.setenv("APPDATA", str(tmp_path))
        ruta = ag.ruta_config()
        ruta.parent.mkdir(parents=True)
        ruta.write_text("{esto no es json", encoding="utf-8")
        assert ag.cargar_config() == {}


class TestApiLotes:
    def test_request_manda_user_agent_y_token(self, monkeypatch):
        # Cloudflare (error 1010) bloquea el UA por defecto de urllib: toda
        # petición debe salir identificada con UA_AGENTE y el token.
        capturado = {}

        class RespuestaFake:
            status = 200

            def read(self):
                return b"{}"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        def urlopen_fake(req, timeout=None):
            capturado["req"] = req
            return RespuestaFake()

        monkeypatch.setattr(ag.urllib.request, "urlopen", urlopen_fake)
        api = ag.ApiLotes("http://servidor:8000/", "tok-123", "pc")
        status, cuerpo = api._request("POST", "/agente/lotes/tareas/reclamar", {"agente": "pc"})
        assert status == 200
        req = capturado["req"]
        assert req.full_url == "http://servidor:8000/agente/lotes/tareas/reclamar"
        assert req.get_header("User-agent") == ag.UA_AGENTE
        assert "Python-urllib" not in req.get_header("User-agent")
        assert req.get_header("X-agente-token") == "tok-123"

    def test_detalle_http_explica_bloqueo_cloudflare(self):
        detalle = ag.detalle_http("reclamar", 403, b"error code: 1010\n")
        assert "Cloudflare" in detalle
        assert "Bot Fight Mode" in detalle

    def test_detalle_http_sin_hint_para_otros_errores(self):
        detalle = ag.detalle_http("reclamar", 401, b'{"detail":"Token invalido"}')
        assert "Cloudflare" not in detalle
        assert "HTTP 401" in detalle


class TestLeerReporte:
    def test_lee_csv_del_bot(self, tmp_path):
        # Mismo formato que escribe responder_glosas_coosalud.py (utf-8-sig).
        ruta = tmp_path / "reporte.csv"
        ruta.write_text(
            "factura,grupos,glosas,estado,detalle\n"
            "HUS100,2,3,OK,\n"
            "HUS200,1,1,RECHAZADA,no en bolsa\n"
            ",,,,\n",
            encoding="utf-8-sig",
        )
        filas = ag.leer_reporte(ruta)
        assert filas == [
            {"factura": "HUS100", "estado": "OK", "detalle": ""},
            {"factura": "HUS200", "estado": "RECHAZADA", "detalle": "no en bolsa"},
        ]

    def test_reporte_inexistente(self, tmp_path):
        assert ag.leer_reporte(tmp_path / "no_existe.csv") == []
