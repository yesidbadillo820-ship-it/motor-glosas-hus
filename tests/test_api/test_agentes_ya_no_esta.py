"""Se quitó el Constructor de Agentes — 19-08-2026.

Yesid preguntó qué hacía ese panel y cuánto se había usado. La respuesta salió
de su propia base de datos:

    Agentes creados: 0

Nunca se usó. Y al probarlo, los dos agentes que creó devolvieron **Error 502**.
La causa no era el panel: `chat_con_asistente` habla ÚNICAMENTE con Anthropic,
y la red del hospital tumba la conexión con `api.anthropic.com` — el
Diagnóstico ya lo marcaba en ámbar («WinError 10054»).

Yesid: «solo funciona con Anthropic — quitarlo, porque si no, entonces
créditos, no hace nada, entonces para qué tenerlo».

Se borró de los dos lados a la vez, que es la lección de «Salud Total»: aquella
pantalla estuvo tres meses dando «Not Found» porque se borró el router y el
JavaScript siguió llamándolo.

OJO: `/agente/lotes/...` NO es esto. Es la cola de trabajos de los bots del PC
del hospital y sigue viva.
"""

from __future__ import annotations

from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]


def _index() -> str:
    return (RAIZ / "static" / "index.html").read_text(encoding="utf-8", errors="ignore")


class TestNoQuedaNadaEnLaPantalla:
    def test_no_queda_el_boton_del_menu(self):
        assert "sidebarTab(this,'agentes')" not in _index()

    def test_no_queda_el_panel(self):
        assert 'id="p-agentes"' not in _index()

    def test_no_quedan_funciones_llamando_a_una_pantalla_que_ya_no_existe(self):
        texto = _index()
        for fn in ("agCargar", "agPintar", "agCrear", "agCorrer", "agRetirar", "agPlantilla"):
            assert fn not in texto, f"{fn} quedó suelta"

    def test_no_queda_el_enganche_de_pestana(self):
        assert "if(id==='agentes')" not in _index()


class TestNoQuedaNadaEnElMotor:
    def test_no_queda_el_router(self):
        assert not (RAIZ / "app" / "api" / "routers" / "agentes.py").exists()

    def test_main_ya_no_lo_monta(self):
        fuente = (RAIZ / "app" / "main.py").read_text(encoding="utf-8")
        assert "agentes_router" not in fuente

    def test_no_queda_el_modelo(self):
        fuente = (RAIZ / "app" / "models" / "db.py").read_text(encoding="utf-8")
        assert "AgenteRecord" not in fuente

    def test_la_aplicacion_arranca_sin_ello(self):
        """La prueba de fondo: importar la app entera no puede reventar."""
        from app.main import app

        rutas = {getattr(r, "path", "") for r in app.routes}
        assert not [r for r in rutas if r.startswith("/agentes")], rutas

    def test_la_cola_de_trabajos_de_los_bots_sigue_viva(self):
        """`/agente/lotes/...` es otra cosa y NO se puede llevar por delante."""
        from app.main import app

        rutas = {getattr(r, "path", "") for r in app.routes}
        assert [r for r in rutas if r.startswith("/agente/lotes")], (
            "se borró de más: la cola de trabajos de los bots desapareció"
        )


class TestElAsistenteExplicaElBloqueoDeRed:
    """Lo que sí se conserva del hallazgo: el 502 mudo.

    El mismo `chat_con_asistente` lo usa el botón 🤖 de la barra de arriba. El
    portal se sirve por un túnel que corta a los ~100 s, y el motor esperaba
    hasta 180 s: SIEMPRE perdía esa carrera, así que el auditor recibía un
    «Error 502» del túnel en vez del motivo real.
    """

    def test_el_motor_contesta_antes_que_el_tunel(self):
        fuente = (RAIZ / "app" / "services" / "asistente_maestro.py").read_text(encoding="utf-8")
        assert "read=180.0" not in fuente, "vuelve a perder la carrera contra el túnel"
        assert "read=75.0" in fuente

    def test_traduce_el_winerror_a_castellano(self):
        from app.services.asistente_maestro import _explicar_fallo_de_red

        msg = _explicar_fallo_de_red(Exception("[WinError 10054] conexión forzada"))
        assert "bloqueo de red" in msg
        assert "api.anthropic.com" in msg

    def test_dice_que_los_dictamenes_siguen_saliendo(self):
        """Para que el auditor no crea que se le cayó el motor entero."""
        from app.services.asistente_maestro import _explicar_fallo_de_red

        assert "Groq" in _explicar_fallo_de_red(Exception("ConnectError"))

    def test_una_demora_no_se_confunde_con_un_bloqueo(self):
        from app.services.asistente_maestro import _explicar_fallo_de_red

        assert "se demoró" in _explicar_fallo_de_red(Exception("ReadTimeout"))
