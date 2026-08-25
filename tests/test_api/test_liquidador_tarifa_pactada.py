"""El liquidador muestra la tarifa REALMENTE pactada del contrato — 18-08-2026.

Cierra Consulta Normativa. Los catálogos SOAT/Propias dicen lo que el Manual
dice que vale un código; pero lo que el hospital cobra es lo que quedó pactado
en el contrato, y eso vive en la base de datos (las 6.655 tarifas de FAMISANAR,
etc.). El liquidador nunca la miraba.

El caso que lo demuestra: la colecistectomía. El cálculo por grupo da
$3.157.500, pero el contrato la pactó por TARIFA PROPIA a $6.296.900 — más del
doble. Sin leer la BD, esa cifra no aparecía.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_usuario_actual
from app.database import Base, get_db
from app.models.db import TarifaContratadaRecord, UsuarioRecord


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add_all(
        [
            TarifaContratadaRecord(
                eps="FAMISANAR EPS",
                contrato_numero="S-13-1-03-1-04958",
                codigo_cups="512101",
                descripcion="COLECISTECTOMIA VIA ABIERTA",
                valor_pactado=6_296_900,
                modalidad="TARIFA PROPIA",
                tipo_tarifa="VALOR_FIJO",
                activa=1,
            ),
            TarifaContratadaRecord(
                eps="FAMISANAR EPS",
                contrato_numero="S-13-1-03-1-04958",
                codigo_cups="471102",
                descripcion="APENDICECTOMIA VIA ABIERTA",
                valor_pactado=1_885_300,
                modalidad="UVB POR GRUPOS",
                tipo_tarifa="VALOR_FIJO",
                activa=1,
            ),
            # Una tarifa inactiva no debe aparecer.
            TarifaContratadaRecord(
                eps="SANITAS",
                contrato_numero="VIEJO",
                codigo_cups="512101",
                descripcion="COLECISTECTOMIA (contrato vencido)",
                valor_pactado=9_999_999,
                modalidad="X",
                tipo_tarifa="VALOR_FIJO",
                activa=0,
            ),
        ]
    )
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def client(db_session):
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: UsuarioRecord(
        id=1, email="a@b.c", rol="SUPER_ADMIN", activo=1, nombre="X"
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestLaTarifaPactada:
    def test_la_colecistectomia_muestra_su_tarifa_propia(self, client):
        """$6.296.900 pactado, NO los $3.157.500 del cálculo por grupo."""
        d = client.get("/tarifa-liquidador/buscar?q=512101&modalidad=SOAT&pct=-5").json()
        assert d["total_pactadas"] == 1
        pact = d["resultados"][0]
        assert pact["catalogo"] == "PACTADO"
        assert pact["valor_pesos"] == 6_296_900
        assert pact["eps"] == "FAMISANAR EPS"
        assert pact["tipo_tarifa"] == "VALOR_FIJO"

    def test_lo_pactado_va_de_primero(self, client):
        """El valor autoritativo se ve antes que la referencia SOAT."""
        d = client.get("/tarifa-liquidador/buscar?q=471102&modalidad=SOAT").json()
        assert d["resultados"][0]["catalogo"] == "PACTADO"

    def test_convive_con_la_referencia_soat(self, client):
        """Se muestran los dos: lo pactado y el cálculo del Manual."""
        d = client.get("/tarifa-liquidador/buscar?q=512101&modalidad=SOAT").json()
        catalogos = {r["catalogo"] for r in d["resultados"]}
        assert "PACTADO" in catalogos
        assert "CIRUGIA_POR_GRUPO" in catalogos

    def test_no_muestra_la_tarifa_inactiva(self, client):
        """El contrato vencido de SANITAS no aparece."""
        d = client.get("/tarifa-liquidador/buscar?q=512101&modalidad=SOAT").json()
        for r in d["resultados"]:
            if r["catalogo"] == "PACTADO":
                assert r["valor_pesos"] != 9_999_999

    def test_filtra_por_eps(self, client):
        d = client.get("/tarifa-liquidador/buscar?q=512101&modalidad=SOAT&eps=FAMISANAR").json()
        assert d["total_pactadas"] == 1
        vacio = client.get("/tarifa-liquidador/buscar?q=512101&modalidad=SOAT&eps=COOSALUD").json()
        assert vacio["total_pactadas"] == 0

    def test_un_codigo_sin_contrato_no_trae_pactado(self, client):
        d = client.get("/tarifa-liquidador/buscar?q=19001&modalidad=SOAT").json()
        assert d["total_pactadas"] == 0

    def test_el_pactado_no_rompe_el_calculo_soat(self, client):
        """La referencia SOAT sigue igual que sin BD."""
        d = client.get("/tarifa-liquidador/buscar?q=471102&modalidad=SOAT&pct=-5").json()
        cir = next(r for r in d["resultados"] if r["catalogo"] == "CIRUGIA_POR_GRUPO")
        assert cir["valor_pesos"] == 1_885_200
