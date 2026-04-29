"""Tests del liquidador de tarifas SOAT/Propias HUS."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_usuario_actual
from app.models.db import UsuarioRecord


@pytest.fixture
def admin_user():
    return UsuarioRecord(
        id=1, email="admin@hus.com", rol="SUPER_ADMIN", activo=1, nombre="ADMIN",
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
        # 890402 está en DESCRIPCIONES_CUPS_2025 pero NO en TARIFAS_SOAT_2026.
        # Sin embargo está en PROPIAS_HUS como 890402H1 — buscar SOLO SOAT
        # debería devolver 0 con tarifa pero mostrar fallback.
        r = client.get("/tarifa-liquidador/buscar?q=890402&modalidad=SOAT")
        assert r.status_code == 200
        d = r.json()
        # Sin tarifa SOAT pero el CUPS existe en catálogo descriptivo
        assert d["total_resultados"] == 0
        assert d["total_fallback_cups"] >= 1
        # Cada item de fallback marca SIN_TARIFA_LOCAL
        for r in d["resultados"]:
            assert r["modalidad"] == "SIN_TARIFA_LOCAL"
            assert r["valor_pesos"] is None


class TestLiquidarManual:
    def test_soat_pleno(self, client):
        r = client.post("/tarifa-liquidador/liquidar-manual",
                        json={"factor": 5.93, "modalidad": "SOAT", "pct": 0, "anio": 2026})
        assert r.status_code == 200
        d = r.json()
        assert d["valor_pesos"] == 71_800
        assert d["uvb_vigente"] == 12_110

    def test_soat_menos_5(self, client):
        r = client.post("/tarifa-liquidador/liquidar-manual",
                        json={"factor": 5.93, "modalidad": "SOAT", "pct": -5})
        d = r.json()
        # 5.93 × 12110 × 0.95 ≈ 68221.685 → centena = 68200
        assert d["valor_pesos"] == 68_200

    def test_propia_hus(self, client):
        # 3.94 SMDLV × 58375 = 229997.5 → centena = 230000
        r = client.post("/tarifa-liquidador/liquidar-manual",
                        json={"factor": 3.94, "modalidad": "PROPIA"})
        d = r.json()
        assert d["valor_pesos"] == 230_000
        assert d["smdlv_vigente"] == 58_375

    def test_factor_invalido(self, client):
        r = client.post("/tarifa-liquidador/liquidar-manual",
                        json={"factor": 0, "modalidad": "SOAT"})
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
