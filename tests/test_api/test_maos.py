"""Material de osteosíntesis: el precio oficial y la norma que lo respalda.

LA GLOSA QUE ESTO CONTESTA. La EPS objeta el valor del material diciendo que
«no está pactado». La respuesta está en el Anexo 09 de la Resolución 194 de
2025 —1.216 códigos FMO con su precio de venta— y hasta ahora el auditor
tenía que buscar la fila a ojo en un PDF de 18 páginas.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord
from app.services import maos


@pytest.fixture
def cliente():
    from app.api.deps import get_usuario_actual
    from app.main import app

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    app.dependency_overrides[get_db] = lambda: iter([s]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: UsuarioRecord(
        id=1, email="ana@hus.com", rol="AUDITOR", activo=1
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    s.close()
    engine.dispose()


class TestCatalogo:
    def test_el_anexo_09_esta_cargado(self):
        r = maos.resumen()
        assert r["total_codigos"] > 1000, "el catálogo quedó incompleto"
        assert r["grupos"]

    def test_los_precios_son_razonables(self):
        """Un precio de $6 o de $600 millones delata un error de extracción
        del PDF, que es de donde salieron estos 1.216 números."""
        for cod, f in maos._catalogo().items():
            assert 1_000 <= f["precio"] <= 60_000_000, f"{cod}: ${f['precio']:,}"

    def test_el_tornillo_cortical_vale_lo_que_dice_el_anexo(self):
        ficha = maos.buscar("FMO00482")
        assert ficha["precio"] == 89_800
        assert "TORNILLO CORTICAL" in ficha["descripcion"]

    def test_los_precios_partidos_del_pdf_quedaron_bien(self):
        """El PDF trae algunos precios cortados: '$ 6 .611.500'. Sin reparar
        esa unión, un set de artroscopia de $6,6 millones se leía como
        $611.500 — una décima parte."""
        assert maos.buscar("FMO01700")["precio"] == 6_611_500
        assert maos.buscar("FMO01701")["precio"] == 5_850_800


class TestComoLoEscribeLaEps:
    """La EPS y el ERP escriben el código de formas distintas."""

    @pytest.mark.parametrize("escrito", ["FMO00482", "FMO482", "fmo 482", "FMO-00482", "fmo-482"])
    def test_reconoce_las_variantes(self, escrito):
        assert maos.normalizar_codigo(escrito) == "FMO00482"
        assert maos.buscar(escrito)["precio"] == 89_800

    def test_saca_los_codigos_de_un_texto_de_glosa(self):
        texto = "Se objeta el material FMO-482 y fmo 1724 por tarifa no pactada"
        assert maos.codigos_en(texto) == ["FMO00482", "FMO01724"]


class TestBuscarPorDescripcion:
    def test_encuentra_sin_saber_el_codigo(self):
        """Es lo normal: la glosa dice 'tornillo cortical 3.5', no FMO00482."""
        res = maos.buscar_por_texto("tornillo cortical")
        assert res
        assert all("TORNILLO CORTICAL" in x["descripcion"] for x in res)

    def test_sin_coincidencias_no_revienta(self):
        assert maos.buscar_por_texto("prótesis de unicornio") == []


class TestLaDefensaQueSePega:
    def test_trae_el_precio_y_la_norma(self):
        d = maos.defensa_para("FMO00482")
        assert "$89.800" in d
        assert "RESOLUCIÓN NO. 194 DE 2025" in d
        assert "ANEXO No. 9" in d

    def test_cita_el_sustento_legal(self):
        """Sin los decretos, la EPS responde que es una cotización unilateral."""
        d = maos.defensa_para("FMO00482")
        assert "DECRETO 2423 DE 1996" in d
        assert "DECRETO 887 DE 2001" in d

    def test_dice_que_no_es_una_cotizacion(self):
        assert "NO ES UNA COTIZACIÓN" in maos.defensa_para("FMO00482")

    def test_el_separador_de_miles_no_daña_el_texto(self):
        """El formato de pesos usa punto; aplicarlo a todo el párrafo
        convertía en punto las comas de la redacción."""
        d = maos.defensa_para("FMO00482")
        assert "LONGITUDES, CUYO PRECIO" in d

    def test_un_codigo_que_no_existe_devuelve_none(self):
        assert maos.defensa_para("FMO99999") is None


class TestEndpoints:
    def test_busca_por_codigo_y_trae_la_defensa(self, cliente):
        d = cliente.get("/maos/buscar?q=FMO00482").json()
        assert d["encontrado"] is True
        assert d["por"] == "codigo"
        assert d["defensa"]

    def test_busca_por_descripcion(self, cliente):
        d = cliente.get("/maos/buscar?q=tornillo cortical").json()
        assert d["encontrado"] is True
        assert d["por"] == "descripcion"
        assert len(d["resultados"]) > 1

    def test_sin_resultados_explica_que_hacer(self, cliente):
        d = cliente.get("/maos/buscar?q=zzzz inexistente").json()
        assert d["encontrado"] is False
        assert "código FMO" in d["mensaje"]

    def test_la_defensa_de_un_codigo_inexistente_explica(self, cliente):
        r = cliente.get("/maos/defensa/FMO99999")
        assert r.status_code == 404
        assert "no está en el Anexo 09" in r.json()["detail"]

    def test_el_resumen_trae_la_resolucion_y_su_sustento(self, cliente):
        d = cliente.get("/maos").json()
        assert d["resolucion"]["numero"] == "Resolución No. 194 de 2025"
        assert len(d["sustento"]) == 2


class TestLaPantalla:
    def _html(self):
        from pathlib import Path

        return (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )

    def test_el_buscador_esta_donde_el_auditor_lo_necesita(self):
        """Dentro de Contratos: es la pantalla donde está cuando pelea una
        glosa de tarifa."""
        html = self._html()
        assert 'id="maos-q"' in html
        assert 'id="p-malla"' in html

    def test_llama_a_los_endpoints(self):
        html = self._html()
        assert "'/maos/buscar?q='" in html
        assert "'/maos/defensa/'" in html

    def test_se_puede_copiar_la_defensa(self):
        assert "maosCopiar" in self._html()
