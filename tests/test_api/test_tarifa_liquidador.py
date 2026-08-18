"""Tests del liquidador de tarifas SOAT/Propias HUS."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord


@pytest.fixture
def admin_user():
    return UsuarioRecord(
        id=1,
        email="admin@hus.com",
        rol="SUPER_ADMIN",
        activo=1,
        nombre="ADMIN",
    )


@pytest.fixture
def client(admin_user):
    from app.main import app

    app.dependency_overrides[get_usuario_actual] = lambda: admin_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestBuscar:
    def test_busca_por_codigo_propio_hus(self, client):
        r = client.get("/tarifa-liquidador/buscar?q=890402H1&modalidad=PROPIA")
        assert r.status_code == 200
        d = r.json()
        assert d["total_resultados"] >= 1
        primer = d["resultados"][0]
        assert primer["codigo"] == "890402H1"
        assert primer["modalidad"] == "PROPIA_HUS"
        # 1.86 SMDLV × 58375 = 108577.5 → centena = 108600
        # (la tabla oficial dice 109.000 por redondeos internos del HUS)
        assert 108_000 <= primer["valor_pesos"] <= 110_000

    def test_busca_por_descripcion(self, client):
        r = client.get("/tarifa-liquidador/buscar?q=ecocardiograma&modalidad=PROPIA")
        d = r.json()
        assert d["total_resultados"] >= 1
        # Todos los resultados contienen "ecocardiograma" en la descripción
        for it in d["resultados"]:
            assert "ECOCARDIO" in it["descripcion"].upper()

    def test_busca_soat_con_pct_negativo(self, client):
        # SOAT -5%: 5.93 UVB × 12.110 × 0.95 ≈ 68.220 → centena = 68.200
        r = client.get("/tarifa-liquidador/buscar?q=19001&modalidad=SOAT&pct=-5")
        d = r.json()
        assert d["total_resultados"] == 1
        assert d["resultados"][0]["porcentaje_aplicado"] == -5
        # Verificar que el valor con -5% sea menor que el pleno (71.800)
        assert d["resultados"][0]["valor_pesos"] < 71_800

    def test_busca_soat_pleno(self, client):
        r = client.get("/tarifa-liquidador/buscar?q=19001&modalidad=SOAT&pct=0")
        d = r.json()
        assert d["resultados"][0]["valor_pesos"] == 71_800  # 5.93 × 12110 = 71812.3 → 71800

    def test_query_vacio_devuelve_422(self, client):
        r = client.get("/tarifa-liquidador/buscar")
        assert r.status_code == 422  # q es requerido

    def test_fallback_cups_cuando_no_hay_tarifa_local(self, client):
        """Queda fallback solo para lo que NO tiene tarifa por ningún camino.

        18-08-2026: este caso usaba el CUPS 890402 y comprobaba que
        devolviera CERO. Desde que el liquidador cruza la tabla de
        homologación, 890402 sí resuelve (→ SOAT 39140), así que el ejemplo
        dejó de servir: comprobaba el defecto, no la función. Se cambió por
        un CUPS que está en el catálogo descriptivo y que ni el Manual SOAT
        ni las tarifas propias tarifan — ahí el fallback sigue siendo la
        respuesta honesta.
        """
        r = client.get("/tarifa-liquidador/buscar?q=901040&modalidad=SOAT")
        assert r.status_code == 200
        d = r.json()
        assert d["total_resultados"] == 0
        assert d["total_fallback_cups"] >= 1
        for fila in d["resultados"]:
            assert fila["modalidad"] == "SIN_TARIFA_LOCAL"
            assert fila["valor_pesos"] is None

    def test_el_cups_de_consulta_ya_no_cae_al_fallback(self, client):
        """890402 antes devolvía «sin tarifa local»; ahora liquida."""
        d = client.get("/tarifa-liquidador/buscar?q=890402&modalidad=SOAT").json()
        assert d["total_resultados"] >= 1
        assert d["resultados"][0]["codigo_cups"] == "890402"
        assert d["resultados"][0]["valor_pesos"] > 0


class TestLiquidarManual:
    def test_soat_pleno(self, client):
        r = client.post(
            "/tarifa-liquidador/liquidar-manual",
            json={"factor": 5.93, "modalidad": "SOAT", "pct": 0, "anio": 2026},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["valor_pesos"] == 71_800
        assert d["uvb_vigente"] == 12_110

    def test_soat_menos_5(self, client):
        r = client.post(
            "/tarifa-liquidador/liquidar-manual",
            json={"factor": 5.93, "modalidad": "SOAT", "pct": -5},
        )
        d = r.json()
        # 5.93 × 12110 × 0.95 ≈ 68221.685 → centena = 68200
        assert d["valor_pesos"] == 68_200

    def test_propia_hus(self, client):
        # 3.94 SMDLV × 58375 = 229997.5 → centena = 230000
        r = client.post(
            "/tarifa-liquidador/liquidar-manual", json={"factor": 3.94, "modalidad": "PROPIA"}
        )
        d = r.json()
        assert d["valor_pesos"] == 230_000
        assert d["smdlv_vigente"] == 58_375

    def test_factor_invalido(self, client):
        r = client.post(
            "/tarifa-liquidador/liquidar-manual", json={"factor": 0, "modalidad": "SOAT"}
        )
        assert r.status_code == 422


class TestInfoUnidades:
    def test_devuelve_uvb_smdlv(self, client):
        r = client.get("/tarifa-liquidador/info-unidades?anio=2026")
        assert r.status_code == 200
        d = r.json()
        assert d["uvb"] == 12_110
        assert d["smdlv"] == 58_375
        assert d["total_codigos_propios"] > 0
        assert d["total_codigos_soat"] > 0


class TestManualSoatCompleto:
    """El liquidador dejó de conocer solo 4 tarifas SOAT.

    Antes traía cuatro códigos «de ejemplo» y para todo lo demás contestaba
    «sin tarifa local». Ahora lee la tabla completa de la Circular Externa
    047 de 2025 — 1.507 códigos. Esto importa en los contratos pactados
    contra el SOAT: FAMISANAR («SOAT UVB vigente −5%») y Policía Nacional
    («UVB −8%»).
    """

    def test_el_catalogo_ya_no_son_cuatro_codigos(self, client):
        r = client.get("/tarifa-liquidador/info-unidades")
        assert r.status_code == 200
        assert r.json()["total_codigos_soat"] >= 1_500

    def test_una_cirugia_grande_ya_tiene_tarifa(self, client):
        """513014 — reemplazo de cadera: 1.223,71 UVB × $12.110 = $14.819.100."""
        r = client.get("/tarifa-liquidador/buscar?q=513014&modalidad=SOAT")
        d = r.json()
        assert d["total_resultados"] == 1
        fila = d["resultados"][0]
        assert fila["factor_uvb"] == 1223.71
        assert fila["valor_pesos"] == 14_819_100
        assert fila["norma"] == "CIRCULAR_047_2025"

    def test_el_menos_cinco_de_famisanar_sobre_una_cirugia(self, client):
        """SOAT −5%: 1.223,71 × $12.110 × 0,95 = $14.078.171,7 → $14.078.200.

        El porcentaje se aplica sobre el producto exacto, no sobre el valor
        ya redondeado: por eso no da $14.078.100."""
        r = client.get("/tarifa-liquidador/buscar?q=513014&modalidad=SOAT&pct=-5")
        fila = r.json()["resultados"][0]
        assert fila["valor_pesos"] == 14_078_200
        assert fila["porcentaje_aplicado"] == -5

    def test_busca_por_descripcion_aunque_se_escriba_sin_tildes(self, client):
        """El auditor escribe 'osteosintesis'; la Circular dice
        'Osteosíntesis'. Tienen que encontrarse igual."""
        con = client.get("/tarifa-liquidador/buscar?q=osteosíntesis&modalidad=SOAT").json()
        sin = client.get("/tarifa-liquidador/buscar?q=osteosintesis&modalidad=SOAT").json()
        assert sin["total_resultados"] >= 20
        assert sin["total_resultados"] == con["total_resultados"]

    def test_un_codigo_que_no_existe_sigue_sin_tarifa(self, client):
        """No inventar: lo que no está en la Circular no tiene tarifa."""
        r = client.get("/tarifa-liquidador/buscar?q=999999&modalidad=SOAT")
        d = r.json()
        assert d["total_resultados"] == 0
