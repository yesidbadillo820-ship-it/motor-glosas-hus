"""El catálogo institucional completo del HUS — TARIFAS_HUS.xlsx (18-08-2026).

Antes el sistema conocía 84 tarifas propias. Estas ~1.900 NO son de FAMISANAR:
son del HUS, y las usan TODOS los contratos que pactan «tarifas propias /
institucionales» — COOSALUD, COMPENSAR, SALUD MÍA, AURORA, PPL, FAMISANAR. Sin
el catálogo completo, el liquidador no podía dar el valor propio de una
colecistectomía ($6.296.900) para ninguna EPS.
"""

from __future__ import annotations

import gzip
import json

import pytest

from app.services import tarifas_oficiales as TO
from app.services.tarifas_oficiales import (
    buscar_tarifa_propia_hus,
    tarifas_propias_hus_completas,
)


@pytest.fixture(autouse=True)
def _limpio():
    TO._CACHE_PROPIAS = None
    yield
    TO._CACHE_PROPIAS = None


class TestCatalogo:
    def test_trae_mas_de_mil_ochocientas(self):
        assert len(tarifas_propias_hus_completas()) >= 1_800

    def test_la_colecistectomia_por_cups(self):
        r = buscar_tarifa_propia_hus("512101")
        assert r is not None
        assert r["valor_pesos_2026"] == 6_296_900
        assert "COLECISTECTOMIA" in r["descripcion"].upper()

    def test_tambien_por_codigo_ips(self):
        """'512101H' (el código que factura el HUS) → mismo valor."""
        assert buscar_tarifa_propia_hus("512101H")["valor_pesos_2026"] == 6_296_900

    @pytest.mark.parametrize(
        "cups,minimo",
        [
            ("423301", 3_000_000),  # paquete gastro
            ("902210", 10_000),  # hemograma ambulatorio
            ("AGMO102T", 2_000_000),  # órtesis alfanumérica
        ],
    )
    def test_las_cuatro_hojas_cargaron(self, cups, minimo):
        r = buscar_tarifa_propia_hus(cups)
        assert r is not None
        assert r["valor_pesos_2026"] >= minimo

    def test_ningun_valor_es_cero_ni_negativo(self):
        malos = [c for c, f in tarifas_propias_hus_completas().items() if int(f["valor"]) <= 0]
        assert malos == [], f"tarifas propias en cero: {malos[:10]}"

    def test_un_codigo_inventado_no_existe(self):
        assert buscar_tarifa_propia_hus("999999") is None
        assert buscar_tarifa_propia_hus("") is None

    def test_meta_del_catalogo(self):
        with gzip.open(TO._RUTA_PROPIAS, "rt", encoding="utf-8") as f:
            meta = json.load(f)["_meta"]
        assert meta["version"] == "2026-TARIFAS-HUS"
        assert meta["codigos"] >= 1_800
        assert set(meta["por_tipo"]) == {"PROPIA", "PAQUETE", "AMBULATORIO", "ORTESIS_PROTESIS"}


class TestSiFaltaElArchivo:
    def test_sin_catalogo_quedan_las_84(self, monkeypatch):
        """Si el .gz no está, el sistema sigue con las 84 transcritas a mano
        y jamás inventa una tarifa."""
        monkeypatch.setattr(TO, "_RUTA_PROPIAS", "/ruta/que/no/existe.json.gz")
        TO._CACHE_PROPIAS = None
        assert tarifas_propias_hus_completas() == {}
        # 372301H está en las 84 transcritas a mano: sigue resolviendo.
        assert buscar_tarifa_propia_hus("372301H") is not None
