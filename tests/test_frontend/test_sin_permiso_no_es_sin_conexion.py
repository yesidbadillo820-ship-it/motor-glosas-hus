"""«No tiene permiso» no es «revise la conexión».

31-08-2026. Los gestores no podían trabajar las glosas del ADRES y **nadie
sabía por qué**. Al revisarlo apareció que los 28 usuarios ya tenían el rol
AUDITOR, que es el que el motor exige para responder glosas del ADRES y para
usar el Validador FURIPS. O sea que el permiso, en el papel, lo tenían.

El problema no era el permiso: era que **la pantalla no lo decía**.

Cuando el servidor contesta 403, lo que veía el gestor era el aviso genérico
de carga:

    «No se pudo cargar: las glosas de ADRES —
     Lo que ve en pantalla puede estar desactualizado.
     Revise la conexión y vuelva a entrar.»

Le decía que mirara el internet cuando lo que había pasado era que el servidor
le negó el permiso. Así el gestor reintenta, culpa a la red, y el problema
nunca llega con nombre propio hasta quien puede arreglarlo. Es exactamente el
defecto de «ningún estado que mienta»: una pantalla que afirma con seguridad
algo que no es.

De las 317 llamadas que esta pantalla le hace al motor, solo 21 miraban el
403. Arreglarlas una por una no se sostiene: el día que alguien escriba la
318 vuelve el problema. Por eso se envuelve `fetch` **una sola vez** — con eso
queda cubierta toda llamada, la de hoy y la que se escriba mañana.

El servidor ya mandaba el motivo exacto («Se requiere rol COORDINADOR o
superior»). Lo único que faltaba era mostrárselo a quien está sentado
enfrente, junto con el rol que tiene.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PANTALLA = RAIZ / "static" / "index.html"


@pytest.fixture(scope="module")
def html() -> str:
    return PANTALLA.read_text(encoding="utf-8")


def _cuerpo(html: str, nombre: str) -> str:
    """El cuerpo de una función suelta del archivo."""
    m = re.search(r"\nfunction " + re.escape(nombre) + r"\(", html)
    assert m, f"no existe la función {nombre}"
    i = html.index("{", m.end())
    prof, j = 0, i
    while j < len(html):
        if html[j] == "{":
            prof += 1
        elif html[j] == "}":
            prof -= 1
            if prof == 0:
                return html[i : j + 1]
        j += 1
    raise AssertionError(f"no se pudo cerrar la función {nombre}")


class TestElAvisoExisteYCubreTodo:
    def test_fetch_queda_envuelto_una_sola_vez(self, html: str):
        """Una sola envoltura cubre las 317 llamadas y las que vengan."""
        assert "envolverFetchPara403" in html
        assert "window.__fetch403" in html, "hace falta la guarda de no envolver dos veces"

    def test_mira_el_403(self, html: str):
        assert re.search(r"res\.status\s*===\s*403", html)

    def test_no_se_come_la_respuesta(self, html: str):
        """Se lee sobre una copia: el original tiene que llegar intacto a
        quien hizo la llamada, o se rompe media pantalla."""
        assert "res.clone()" in html

    def test_devuelve_la_respuesta_original(self, html: str):
        cuerpo = html[html.index("envolverFetchPara403") :]
        cuerpo = cuerpo[: cuerpo.index("function _avisar403")]
        assert "return res;" in cuerpo


class TestElAvisoDiceLaVerdad:
    def test_dice_que_es_permiso_y_no_conexion(self, html: str):
        cuerpo = _cuerpo(html, "_avisar403")
        assert "No tiene permiso" in cuerpo
        assert "No es un problema de conexión" in cuerpo

    def test_muestra_el_rol_que_tiene_el_usuario(self, html: str):
        """Sin el rol, el gestor no sabe qué pedir ni a quién."""
        cuerpo = _cuerpo(html, "_avisar403")
        assert "USER_ROL" in cuerpo
        assert "rol " in cuerpo

    def test_muestra_el_motivo_que_manda_el_servidor(self, html: str):
        """El motor ya responde «Se requiere rol COORDINADOR o superior»."""
        assert "cuerpo.detail" in html

    def test_dice_a_quien_pedirle_el_permiso(self, html: str):
        assert "quien administra los usuarios" in _cuerpo(html, "_avisar403")


class TestNoSeContradiceConElAvisoViejo:
    def test_el_aviso_generico_se_calla_tras_un_403(self, html: str):
        """Si los dos hablan, el gestor lee «revise la conexión» encima del
        aviso bueno — que es la mentira que este cambio vino a quitar."""
        cuerpo = _cuerpo(html, "avisarNoCargo")
        assert "_ultimo403" in cuerpo

    def test_el_aviso_generico_conserva_lo_suyo(self, html: str):
        """El cambio no puede llevarse por delante lo que ese aviso ya hacía."""
        cuerpo = _cuerpo(html, "avisarNoCargo")
        assert "15000" in cuerpo, "seguía sin repetirse cada segundo"
        assert "puede estar desactualizado" in cuerpo


class TestLoQueElGestorSiPuedeHacer:
    """Se deja escrito lo que se comprobó en el código del motor, porque es
    lo que evita volver a buscar en el sitio equivocado."""

    def test_el_rol_auditor_basta_para_responder_glosas_adres(self):
        ruta = RAIZ / "app" / "api" / "routers" / "glosas_adres.py"
        codigo = ruta.read_text(encoding="utf-8")
        for endpoint in ("/factura/{numero}/estado", "/glosa/{glosa_id}", "/aplicar-sugerencias"):
            i = codigo.index(f'"{endpoint}"')
            bloque = codigo[i : i + 700]
            assert "get_auditor_o_superior" in bloque, endpoint

    def test_el_validador_adres_completo_es_de_auditor(self):
        codigo = (RAIZ / "app" / "api" / "routers" / "validador_adres.py").read_text(
            encoding="utf-8"
        )
        assert "get_coordinador_o_admin" not in codigo
        assert "get_admin" not in codigo

    def test_importar_el_paquete_sigue_siendo_de_coordinador(self):
        """A propósito: reimportar REEMPLAZA el paquete para todos. Si algún
        día se abre, que sea una decisión, no un descuido."""
        codigo = (RAIZ / "app" / "api" / "routers" / "glosas_adres.py").read_text(encoding="utf-8")
        i = codigo.index('"/importar"')
        assert "get_coordinador_o_admin" in codigo[i : i + 900]
