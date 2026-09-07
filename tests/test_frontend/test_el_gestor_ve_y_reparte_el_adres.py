"""El gestor no veía las glosas del ADRES, y no podía repartir las compartidas.

31-08-2026, pedido del área. Dos cosas distintas que se veían igual desde
afuera —«no tengo permiso»— y ninguna era lo que parecía.

**1. El botón del menú se les escondía.**
Hay una lista blanca, `AUDITOR_TABS_PERMITIDAS`, que oculta del menú lateral
todo lo que no esté en ella cuando el rol es AUDITOR. `glosas-adres` no
estaba. Como los 28 usuarios del hospital son AUDITOR, **ninguno veía la
pantalla**. Y el permiso del servidor sí lo tenían desde siempre: responder,
cambiar estado y contestar en lote piden AUDITOR o superior.

**2. Repartir el área era solo de SUPER ADMIN.**
Las glosas de causal compartida (hoy la 4506) las trabajan dos áreas:
facturación y las médicas. Hasta hoy solo un super admin podía decir cuál la
toma, así que se quedaban quietas esperando a una sola persona. Se abre a los
gestores.

LO QUE NO CAMBIA, y es lo que hacía prudente la restricción: el material de
osteosíntesis y el de alto costo los revisa el médico auditor, no facturación.
El reparto sigue siendo acotado (solo causales de dos áreas), con testigo
(queda quién y cuándo) y reversible. Y el motor ya trae su sugerencia de área
con el motivo, que es lo que hay que mirar antes de mandarle a facturación
algo que le toca al médico.
"""

from __future__ import annotations

from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
PANTALLA = RAIZ / "static" / "index.html"
RUTAS = RAIZ / "app" / "api" / "routers" / "glosas_adres.py"


@pytest.fixture(scope="module")
def html() -> str:
    return PANTALLA.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def rutas() -> str:
    return RUTAS.read_text(encoding="utf-8")


def _lista_blanca(html: str) -> str:
    i = html.index("var AUDITOR_TABS_PERMITIDAS")
    return html[i : html.index("\n};", i)]


class TestElGestorVeLaPantalla:
    def test_glosas_adres_esta_en_la_lista_blanca(self, html: str):
        """Sin esto el botón se le esconde a los 28 gestores."""
        assert "'glosas-adres': true" in _lista_blanca(html)

    def test_el_validador_adres_sigue_estando(self, html: str):
        """No se puede arreglar uno rompiendo el otro."""
        assert "'validador-adres': true" in _lista_blanca(html)

    def test_el_boton_del_menu_existe_y_apunta_ahi(self, html: str):
        assert "sidebarTab(this,'glosas-adres')" in html

    def test_no_se_le_abrio_lo_que_no_se_pidio(self, html: str):
        """La lista blanca es lo único que separa al gestor de las pantallas
        de coordinación. Que no se cuele nada de paso.

        01-09-2026: 'contratos' sale de esta lista de prohibidas porque Yesid
        lo pidió expresamente para los gestores (ver TestLoQuePidioYesid)."""
        blanca = _lista_blanca(html)
        for prohibida in ("'mando'", "'usuarios'", "'admin-sugerencias'"):
            assert prohibida not in blanca, prohibida


class TestLoQuePidioYesid:
    """01-09-2026, con las capturas en la mano: «que los auditores puedan ver
    esos espacios». Contratos e Importación masiva faltaban en la lista blanca:
    el menú se los escondía a todos los gestores aunque el servidor ya les
    permitiera consultarlos."""

    @pytest.mark.parametrize(
        "tab",
        [
            "'contratos'",
            "'importacion-masiva'",
            # 02-09-2026: el resto de las capturas de Yesid («yo no veo que se
            # vean todos esos botones»). El servidor ya las deja consultar.
            "'mi-dia'",
            "'vencimientos'",
            "'malla'",
            "'automatizacion'",
            "'tarifas'",
            "'soportes'",
        ],
    )
    def test_entran_a_la_lista_blanca(self, html: str, tab):
        assert f"{tab}: true" in _lista_blanca(html), tab

    def test_y_lo_ya_abierto_sigue_abierto(self, html: str):
        blanca = _lista_blanca(html)
        for tab in ("'conciliacion'", "'papelera'", "'glosas-adres'", "'consulta-normativa'"):
            assert f"{tab}: true" in blanca, tab


class TestElGestorPuedeRepartirElArea:
    def test_asignar_area_ya_no_pide_super_admin(self, rutas: str):
        i = rutas.index('"/glosa/{glosa_id}/area"')
        bloque = rutas[i : i + 1400]
        assert "get_auditor_o_superior" in bloque
        assert "get_admin" not in bloque

    def test_queda_escrito_quien_asigno_y_cuando(self):
        """El testigo es lo que hace aceptable abrir el permiso."""
        svc = (RAIZ / "app" / "services" / "preauditoria_adres.py").read_text(encoding="utf-8")
        i = svc.index("def asignar_area")
        bloque = svc[i : i + 1600]
        assert "area_asignada_por" in bloque
        assert "area_asignada_en" in bloque

    def test_solo_se_reparte_en_causales_de_dos_areas(self):
        """En cualquier otra causal el motor responde con error. Es lo que
        impide que abrir el permiso se convierta en repartir lo que sea."""
        svc = (RAIZ / "app" / "services" / "preauditoria_adres.py").read_text(encoding="utf-8")
        i = svc.index("def asignar_area")
        bloque = svc[i : i + 1600]
        assert "CAUSALES_DE_DOS_AREAS" in bloque
        assert "raise ValueError" in bloque

    def test_la_razon_clinica_sigue_escrita(self, rutas: str):
        """Si mañana alguien la borra, que sea a sabiendas: el material de
        osteosíntesis y el de alto costo los ve el médico auditor."""
        i = rutas.index('"/glosa/{glosa_id}/area"')
        bloque = rutas[i : i + 1400]
        assert "osteosíntesis" in bloque
        assert "médico auditor" in bloque


class TestNoSeAbrioLoQueNoSePidio:
    def test_importar_el_paquete_sigue_siendo_de_coordinador(self, rutas: str):
        """Reimportar REEMPLAZA el paquete para todos. Eso no se tocó."""
        i = rutas.index('"/importar"')
        assert "get_coordinador_o_admin" in rutas[i : i + 900]

    def test_importar_bitacora_tambien(self, rutas: str):
        i = rutas.index('"/importar-bitacora"')
        assert "get_coordinador_o_admin" in rutas[i : i + 900]

    @pytest.mark.parametrize(
        "endpoint", ["/factura/{numero}/estado", "/glosa/{glosa_id}", "/aplicar-sugerencias"]
    )
    def test_lo_que_el_gestor_ya_podia_sigue_igual(self, rutas: str, endpoint: str):
        i = rutas.index(f'"{endpoint}"')
        assert "get_auditor_o_superior" in rutas[i : i + 700], endpoint


class TestSePuedeReasignarElArea:
    """04-09-2026 (Yesid): «si por error coloco PERTINENCIA y eran FACTURACIÓN
    ya no puedo volver a reasignar». La celda «Clasificación» mostraba solo
    texto plano una vez asignada, y no había forma de corregir el área. Ahora el
    selector queda SIEMPRE en las causales de doble área — el backend siempre
    permitió reasignar (es reversible), solo faltaba la pantalla."""

    def _celda(self, html: str) -> str:
        i = html.index("function gaCeldaArea(")
        return html[i : html.index("\n}\n", i)]

    def test_la_celda_ya_no_se_congela_al_asignar(self, html: str):
        celda = self._celda(html)
        # Antes: `if(!g.requiere_asignacion) return escHtml(...)` congelaba la
        # celda. Ahora decide por si la causal es de doble área.
        assert "if(!(g.areas_posibles||[]).length)" in celda
        assert "!g.requiere_asignacion) return escHtml" not in celda

    def test_el_selector_aparece_tambien_cuando_ya_esta_asignada(self, html: str):
        """El selector se pinta si el usuario puede repartir, sin condicionarlo
        a que la glosa siga «POR ASIGNAR»."""
        celda = self._celda(html)
        assert "gaAsignarArea(" in celda
        # `yaAsignada` se usa para preseleccionar el área actual, no para ocultar.
        assert "yaAsignada" in celda

    def test_el_permiso_de_la_pantalla_es_el_mismo_del_backend(self, html: str):
        """El backend abrió el reparto a auditor o superior el 31-08-2026; la
        pantalla se había quedado pidiendo SUPER_ADMIN. Ahora coinciden."""
        i = html.index("function gaPuedeRepartirArea(")
        bloque = html[i : i + 300]
        for rol in ("'AUDITOR'", "'COORDINADOR'", "'SUPER_ADMIN'"):
            assert rol in bloque, rol

    def test_hay_boton_para_dejarlas_todas_en_facturacion(self, html: str):
        """«TODO SALGA COMO FACTURACIÓN» — el pedido literal de Yesid.

        En el HTML las comillas del onclick van escapadas porque están dentro de
        una cadena JS: `gaTodasArea(\\'FACTURACION\\')`."""
        assert r"gaTodasArea(\'FACTURACION\')" in html
        assert "Todas a FACTURACIÓN" in html

    def test_dejar_todas_en_un_area_es_reversible_y_acotado(self, html: str):
        i = html.index("async function gaTodasArea(")
        bloque = html[i : html.index("\n}\n", i)]
        # Manda al mismo endpoint reversible, una glosa a la vez.
        assert "/glosas-adres/glosa/" in bloque and "/area" in bloque
        # Solo toca las de doble área, y salta las que ya están en ese área.
        assert "areas_posibles" in bloque
        assert "g.clasificacion !== area" in bloque

    def test_el_aviso_recuerda_que_lo_clinico_lo_ve_el_medico(self, html: str):
        """El botón masivo no puede tapar la razón clínica: osteosíntesis y alto
        costo los revisa el médico auditor."""
        i = html.index("async function gaTodasArea(")
        bloque = html[i : html.index("\n}\n", i)]
        assert "osteosíntesis" in bloque
        assert "médico auditor" in bloque
