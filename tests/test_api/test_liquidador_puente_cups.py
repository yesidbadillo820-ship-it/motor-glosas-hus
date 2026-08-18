"""El liquidador de tarifas entiende el código que sale en la factura.

Auditoría del botón «Consulta Normativa» — 18-08-2026.

Lo que estaba pasando: la pantalla solo sabía buscar por código SOAT (21102,
19001…). El auditor no tiene ese código; tiene el CUPS que sale en la factura
(873420) o el nombre del procedimiento («radiografía de rodilla»). Escribiendo
cualquiera de los dos, la pantalla devolvía CERO resultados — justo lo que uno
escribe cuando la EPS objeta la tarifa.

La tabla de homologación (10.024 CUPS) ya estaba cargada. Solo faltaba que la
búsqueda la usara.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord


@pytest.fixture
def client():
    from app.main import app

    usuario = UsuarioRecord(
        id=1, email="auditor@hus.com", rol="SUPER_ADMIN", activo=1, nombre="AUDITOR"
    )
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _buscar(client, q, **extra):
    params = {"q": q, "modalidad": "SOAT", **extra}
    cadena = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/tarifa-liquidador/buscar?{cadena}")
    assert r.status_code == 200
    return r.json()


class TestElCupsDeLaFacturaYaSirve:
    def test_la_rx_de_rodilla_por_su_cups(self, client):
        """CUPS 873420 → SOAT 21102 → 8,25 UVB × $12.110 = $99.900."""
        d = _buscar(client, "873420")
        assert d["total_resultados"] >= 1
        fila = d["resultados"][0]
        assert fila["codigo"] == "21102"
        assert fila["codigo_cups"] == "873420"
        assert "RODILLA" in fila["descripcion_cups"].upper()
        assert fila["valor_pesos"] == 99_900
        assert fila["catalogo"] == "CUPS_HOMOLOGADO_SOAT"

    def test_tambien_por_el_nombre_del_procedimiento(self, client):
        d = _buscar(client, "radiografia de rodilla")
        assert d["total_resultados"] >= 1
        assert any(r.get("codigo_cups") == "873420" for r in d["resultados"])

    def test_el_hemograma_por_su_cups(self, client):
        d = _buscar(client, "902210")
        assert d["total_resultados"] >= 1
        assert d["resultados"][0]["codigo_cups"] == "902210"
        assert d["resultados"][0]["valor_pesos"] > 0

    def test_el_menos_cinco_se_aplica_igual_por_el_camino_del_cups(self, client):
        """8,25 UVB × $12.110 × 0,95 = $94.911,7 → $94.900."""
        d = _buscar(client, "873420", pct=-5)
        assert d["resultados"][0]["valor_pesos"] == 94_900

    def test_el_codigo_soat_directo_sigue_funcionando(self, client):
        """No se rompió el camino viejo: quien sepa el SOAT lo sigue usando."""
        d = _buscar(client, "21102")
        assert d["resultados"][0]["codigo"] == "21102"
        assert d["resultados"][0]["valor_pesos"] == 99_900

    def test_no_se_duplica_cuando_se_llega_por_los_dos_caminos(self, client):
        d = _buscar(client, "21102")
        codigos = [r["codigo"] for r in d["resultados"]]
        assert len(codigos) == len(set(codigos))


class TestCuandoElManualNoLoTarifa:
    def test_se_informa_el_hecho_y_no_se_inventa_tarifa(self, client):
        """013205 está en la tabla y el Manual SOAT NO le asigna código.

        Eso favorece al hospital: la EPS no puede objetar la tarifa citando
        un código SOAT que para ese procedimiento no existe.
        """
        d = _buscar(client, "013205")
        fila = next(r for r in d["resultados"] if r["codigo_cups"] == "013205")
        assert fila["modalidad"] == "SIN_HOMOLOGACION_SOAT"
        assert fila["valor_pesos"] is None
        assert fila["factor_uvb"] is None
        assert "no" in fila["formula"].lower()

    def test_un_codigo_que_no_existe_no_devuelve_nada(self, client):
        d = _buscar(client, "999999")
        assert d["total_resultados"] == 0


class TestElAnioSinUvbAvisa:
    def test_2026_no_lleva_advertencia(self, client):
        assert _buscar(client, "873420", anio=2026)["advertencia"] is None

    @pytest.mark.parametrize("anio", [2023, 2024, 2025])
    def test_un_anio_sin_unidad_propia_avisa(self, client, anio):
        """Liquidar una factura vieja con la UVB de hoy da una cifra que no
        se puede radicar. Antes se hacía en silencio."""
        aviso = _buscar(client, "873420", anio=anio)["advertencia"]
        assert aviso is not None
        assert str(anio) in aviso
        assert "$12.110" in aviso

    def test_los_pesos_del_aviso_van_a_la_colombiana(self, client):
        aviso = _buscar(client, "873420", anio=2024)["advertencia"]
        assert "12,110" not in aviso
        assert "58,375" not in aviso


class TestCirugiasEnElLiquidador:
    """El liquidador ya desglosa las cirugías por grupo — 18-08-2026."""

    def test_una_cirugia_sale_con_desglose(self, client):
        d = _buscar(client, "471102", pct=-5)
        cir = next(r for r in d["resultados"] if r["catalogo"] == "CIRUGIA_POR_GRUPO")
        assert cir["codigo_cups"] == "471102"
        assert cir["grupo"] == "7"
        assert len(cir["desglose"]) == 5
        assert cir["valor_pesos"] == 1_885_200  # método directo; BD = 1.885.300

    def test_el_paquete_integral_se_distingue_del_grupo(self, client):
        """La cesárea aparece de dos formas y NO se confunden:
        por grupo ($2.072.200) y como paquete integral ($4.298.200)."""
        d = _buscar(client, "cesarea segmentaria", pct=-5)
        grupo = [r for r in d["resultados"] if r["catalogo"] == "CIRUGIA_POR_GRUPO"]
        integral = [r for r in d["resultados"] if r.get("atencion_integral")]
        assert grupo and integral
        assert grupo[0]["valor_pesos"] == 2_072_200
        assert integral[0]["valor_pesos"] != grupo[0]["valor_pesos"]

    def test_un_examen_no_trae_desglose_de_cirugia(self, client):
        d = _buscar(client, "902210")
        for r in d["resultados"]:
            assert r["catalogo"] != "CIRUGIA_POR_GRUPO"


class TestTarifasPropiasParaTodaEps:
    """El catálogo propio del HUS en el liquidador — no solo FAMISANAR."""

    def test_la_colecistectomia_muestra_la_tarifa_propia(self, client):
        d = _buscar(client, "512101", modalidad="AMBOS", pct=-5)
        propia = next(r for r in d["resultados"] if r["catalogo"] == "PROPIA_HUS")
        assert propia["valor_pesos"] == 6_296_900

    def test_a_la_propia_no_se_le_aplica_el_porcentaje(self, client):
        """Es valor fijo: con −5% o con 0% da lo mismo."""
        con = _buscar(client, "512101", modalidad="AMBOS", pct=-5)
        sin = _buscar(client, "512101", modalidad="AMBOS", pct=0)

        def propia(d):
            return next(r for r in d["resultados"] if r["catalogo"] == "PROPIA_HUS")

        assert propia(con)["valor_pesos"] == propia(sin)["valor_pesos"] == 6_296_900
        assert propia(con)["porcentaje_aplicado"] == 0

    def test_un_examen_ambulatorio_propio(self, client):
        d = _buscar(client, "902210", modalidad="AMBOS")
        assert any(
            r["catalogo"] == "PROPIA_HUS" and r["valor_pesos"] == 19_700 for r in d["resultados"]
        )

    def test_una_ortesis_alfanumerica(self, client):
        d = _buscar(client, "AGMO102T", modalidad="PROPIA")
        assert d["resultados"][0]["catalogo"] == "PROPIA_HUS"
        assert d["resultados"][0]["valor_pesos"] == 2_786_700

    def test_solo_soat_no_trae_propias(self, client):
        """Si el auditor pide Solo SOAT, no se mezclan las propias."""
        d = _buscar(client, "512101", modalidad="SOAT")
        assert not any(r["catalogo"] == "PROPIA_HUS" for r in d["resultados"])
