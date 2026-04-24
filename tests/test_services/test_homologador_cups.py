"""Tests del homologador Res. 2641/2025 (Ronda 45)."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import TarifaContratadaRecord
from app.services.homologador_cups import (
    HOMOLOGACIONES_EXPLICITAS,
    agregar_homologacion,
    cita_res_2641,
    homologar_cups,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try:
        yield s
    finally:
        s.close()


class TestCupsYaOficial:
    def test_cups_de_6_digitos_pasa_directo(self):
        r = homologar_cups("890348")
        assert r is not None
        assert r["cups_oficial"] == "890348"
        assert r["confianza"] == "alta"

    def test_codigo_vacio_devuelve_none(self):
        assert homologar_cups("") is None
        assert homologar_cups(None) is None


class TestTablaExplicita:
    def test_codigo_HUS_con_guion_se_homologa(self):
        """Caso reportado: '39147B-18' (código interno HUS viejo)
        debe homologarse al CUPS oficial 890348."""
        r = homologar_cups("39147B-18")
        assert r is not None
        assert r["cups_oficial"] == "890348"
        assert "2641" in r["fuente"]
        assert r["confianza"] == "alta"

    def test_mayusculas_y_espacios(self):
        r = homologar_cups("  39147b-18  ")
        assert r is not None
        assert r["cups_oficial"] == "890348"

    def test_codigo_sin_guion_tambien_se_reconoce(self):
        r = homologar_cups("39147B18")
        assert r is not None
        assert r["cups_oficial"] == "890348"


class TestNormalizacionHeuristica:
    def test_sufijo_H_se_quita_para_match_heuristico(self):
        """Si el CUPS viene como '890348H' y el base '890348' matchea
        en CUPS oficial, debe devolverlo con confianza MEDIA."""
        r = homologar_cups("890348H")
        assert r is not None
        assert r["cups_oficial"] == "890348"
        # Puede ser alta (si está en tabla) o media (heurística)
        assert r["confianza"] in ("alta", "media")


class TestBDLookup:
    def test_busca_en_tarifa_contratada_por_codigo_ips(self, db):
        """Si se cargó una tarifa con codigo_ips='39999X-99' y
        codigo_cups='890999', homologar_cups('39999X-99', db) debe
        encontrarla en BD aunque no esté en la tabla explícita."""
        db.add(TarifaContratadaRecord(
            eps="TEST EPS", codigo_cups="890999", codigo_ips="39999X-99",
            valor_pactado=100_000, activa=1,
        ))
        db.commit()
        r = homologar_cups("39999X-99", db=db)
        assert r is not None
        assert r["cups_oficial"] == "890999"
        assert "contrato" in r["fuente"].lower() or "excel" in r["fuente"].lower()

    def test_respeta_eps_si_se_pasa(self, db):
        db.add(TarifaContratadaRecord(
            eps="EPS A", codigo_cups="890111", codigo_ips="CODIGO-X",
            valor_pactado=10_000, activa=1,
        ))
        db.add(TarifaContratadaRecord(
            eps="EPS B", codigo_cups="890222", codigo_ips="CODIGO-X",
            valor_pactado=20_000, activa=1,
        ))
        db.commit()
        rA = homologar_cups("CODIGO-X", db=db, eps="EPS A")
        rB = homologar_cups("CODIGO-X", db=db, eps="EPS B")
        assert rA["cups_oficial"] == "890111"
        assert rB["cups_oficial"] == "890222"


class TestAgregarHomologacion:
    def test_agregar_y_consultar(self):
        agregar_homologacion("TEST-CODIGO-UNICO", "999999", "Descripción test")
        r = homologar_cups("TEST-CODIGO-UNICO")
        assert r is not None
        assert r["cups_oficial"] == "999999"

    def test_agregar_vacio_es_noop(self):
        # No debería crashear
        agregar_homologacion("", "999999")
        agregar_homologacion("X", "")


class TestCita2641:
    def test_cita_incluye_numero_y_codigo(self):
        c = cita_res_2641("39147B-18", "890348")
        assert "2641" in c
        assert "39147B-18" in c
        assert "890348" in c
        assert "CUPS" in c.upper()

    def test_cita_es_formal(self):
        c = cita_res_2641("X", "Y")
        assert "Ministerio" in c or "MinSalud" in c or "Ministro" in c


class TestCasoReal:
    def test_caso_usuario_DMBUG_genetica(self):
        """Test del caso exacto reportado por el usuario."""
        r = homologar_cups("39147B-18")
        assert r is not None
        assert r["cups_oficial"] == "890348"
        assert "GENÉTICA" in r["descripcion"].upper()


class TestIntegridad:
    def test_tabla_tiene_caso_DMBUG(self):
        """Garantiza que el caso reportado por el usuario esté cubierto."""
        assert "39147B-18" in HOMOLOGACIONES_EXPLICITAS
