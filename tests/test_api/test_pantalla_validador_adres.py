"""La pantalla del validador ADRES dentro del portal.

OT-035 · 13-08-2026. En OT-031 se metieron al portal el validador FURIPS y
el buscador de autorizaciones, pero solo por debajo: las rutas respondían y
no había ni un botón. Yesid preguntó si ya estaba listo lo de los ZIP que
había mandado, y no: lo que él subrayó como fundamental —«el validador app
web que valida cuando se le suben los soportes del ADRES y descarga el
informe en Excel»— no se podía usar desde la página.

Lo que estas pruebas fijan es la costura entre la pantalla y el motor, que
es justo lo que se rompe sin que nadie se entere: el JavaScript llama por
nombre y, si una ruta o un campo cambia, la pantalla no da error — se queda
callada. Fue exactamente lo que pasó con «Salud Total», que estuvo tres
meses devolviendo «Not Found» sin que ninguna prueba lo viera.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"


@pytest.fixture(scope="module")
def html() -> str:
    if not INDEX.exists():  # pragma: no cover - algunos despliegues no lo copian
        pytest.skip("static/index.html no está en este entorno")
    return INDEX.read_text(encoding="utf-8", errors="ignore")


class TestLaPantallaExiste:
    def test_hay_panel(self, html):
        assert 'id="p-validador-adres"' in html

    def test_hay_boton_en_el_menu(self, html):
        assert "sidebarTab(this,'validador-adres')" in html
        assert "Validador ADRES" in html

    def test_el_panel_esta_en_la_lista_de_paneles_verticales(self, html):
        """Sin esta línea de CSS el panel abre con el ancho de otra pantalla."""
        assert ".panel.active#p-validador-adres" in html

    def test_el_auditor_puede_entrar(self, html):
        """Las rutas ya exigen rol AUDITOR o superior; si la pantalla no está
        en la lista de permitidas, al auditor se le esconde el botón."""
        assert "'validador-adres': true" in html

    def test_esta_en_el_buscador_de_comandos(self, html):
        assert 'tab:"validador-adres"' in html


class TestLaPantallaLlamaALasRutasQueExisten:
    """El JavaScript llama por nombre. Si una ruta cambia, la pantalla se
    queda callada en vez de dar error: hay que fijarlo acá."""

    def test_las_cuatro_rutas_del_html_estan_montadas(self, html):
        from app.main import app

        rutas = {getattr(r, "path", "") for r in app.routes}
        llamadas = set(re.findall(r"'(/validador-adres/[^'?]*)", html))
        assert llamadas, "la pantalla no llama a ninguna ruta del validador"
        for llamada in llamadas:
            # El HTML concatena el identificador: '/validador-adres/estado/'+id
            esperada = llamada.rstrip("/")
            candidatas = {esperada, esperada + "/{trabajo_id}"}
            assert candidatas & rutas, f"la pantalla llama a {llamada} y no existe"

    def test_llama_a_las_cuatro(self, html):
        for ruta in (
            "/validador-adres/validar",
            "/validador-adres/estado/",
            "/validador-adres/excel/",
            "/validador-adres/autorizaciones",
        ):
            assert ruta in html, ruta

    def test_manda_el_campo_con_el_nombre_que_espera_el_motor(self, html):
        """El motor recibe `archivos`; si el HTML manda `files`, la subida
        falla con un 422 que en pantalla se ve como «Error» y nada más."""
        bloque = html[html.index("async function validarAdres") :]
        bloque = bloque[: bloque.index("async function _vaGuardarBlob")]
        assert "fd.append('archivos'" in bloque
        assert "fd.append('files'" not in bloque


class TestLoQueSeSubeYLoQueNo:
    def test_de_una_carpeta_solo_viajan_los_json(self, html):
        """Una carpeta de facturación trae PDF y XML que no se necesitan. Si
        se subieran todos, la subida se vuelve eterna y el disco del servidor
        se llena con soportes que nadie pidió."""
        assert "webkitdirectory" in html, "no se puede escoger una carpeta completa"
        assert re.search(r"\\.json\$/i\.test\(", html), "no se filtran los .json de la carpeta"

    def test_la_pantalla_pregunta_por_el_trabajo_en_vez_de_esperar(self, html):
        """Validar un paquete grande tarda minutos: si el navegador espera la
        respuesta, el usuario ve la página congelada y recarga."""
        assert "setInterval(_vaConsultarEstado" in html

    def test_deja_de_preguntar_cuando_termina(self, html):
        """Sin esto queda un temporizador consultando para siempre, aunque el
        auditor se haya ido a otra pantalla."""
        bloque = html[html.index("async function _vaConsultarEstado") :][:3000]
        assert bloque.count("clearInterval(VA_TIMER)") >= 3, (
            "falta apagar el temporizador en alguno de los finales (LISTO, ERROR o trabajo perdido)"
        )


class TestElMotorRespondeLoQueLaPantallaLee:
    """La pantalla lee estas llaves por nombre."""

    def test_estado_devuelve_las_llaves_que_pinta_la_pantalla(self):
        from app.api.routers import validador_adres as router_mod
        from app.services import validador_adres_service as vas

        trabajo_id, _carpeta = vas.crear_trabajo()
        datos = router_mod.estado_validacion(trabajo_id, None)
        for k in ("estado", "mensaje", "progreso", "total", "facturas"):
            assert k in datos, k

    def test_validar_devuelve_el_identificador_del_trabajo(self, html):
        """La pantalla guarda `d.trabajo_id` y con eso pregunta después."""
        assert "d.trabajo_id" in html
        fuente = (RAIZ / "app" / "api" / "routers" / "validador_adres.py").read_text(
            encoding="utf-8"
        )
        assert '"trabajo_id": trabajo_id' in fuente
