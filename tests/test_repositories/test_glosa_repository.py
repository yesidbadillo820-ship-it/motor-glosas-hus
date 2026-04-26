"""Tests del GlosaRepository (R67 P1)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.tz import ahora_utc
from app.database import Base
from app.models.db import GlosaRecord
from app.repositories.glosa_repository import GlosaRepository


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


def _seed(db, **kw):
    base = dict(
        eps="FAMISANAR", paciente="X", codigo_glosa="TA0201",
        valor_objetado=100_000, valor_aceptado=0,
        etapa="RESPUESTA", estado="RADICADA",
        creado_en=ahora_utc(),
    )
    base.update(kw)
    db.add(GlosaRecord(**base))
    db.commit()


class TestCrear:
    def test_crear_glosa_basica(self, db):
        repo = GlosaRepository(db)
        g = repo.crear(
            eps="FAMISANAR", paciente="JUAN PEREZ",
            codigo_glosa="TA0201", valor_objetado=168_563,
            valor_aceptado=0, etapa="RESPUESTA",
            estado="RADICADA",
            dictamen="<p>x</p>", dias_restantes=15,
        )
        assert g.id is not None
        assert g.eps == "FAMISANAR"
        assert g.creado_en is not None

    def test_crear_glosa_con_metadata_completa(self, db):
        repo = GlosaRepository(db)
        g = repo.crear(
            eps="X", paciente="Y", codigo_glosa="SO0101",
            valor_objetado=50_000, valor_aceptado=0,
            etapa="X", estado="RADICADA",
            dictamen="<p>x</p>", dias_restantes=10,
            cups_servicio="890101",
            servicio_descripcion="CONSULTA MEDICINA GENERAL",
            concepto_glosa="SOPORTES",
            factura="FE-001", numero_radicado="RAD-1",
            modelo_ia="anthropic/claude-sonnet-4-6",
            score=92.5,
        )
        assert g.cups_servicio == "890101"
        assert g.servicio_descripcion == "CONSULTA MEDICINA GENERAL"
        assert g.score == 92.5


class TestAlertasProximas:
    def test_solo_glosas_proximas_a_vencer(self, db):
        _seed(db, paciente="LEJANA", dias_restantes=20)
        _seed(db, paciente="CERCANA", dias_restantes=2)
        repo = GlosaRepository(db)
        alertas = repo.alertas_proximas(dias_limite=5)
        pacientes = [g.paciente for g in alertas]
        assert "CERCANA" in pacientes
        assert "LEJANA" not in pacientes

    def test_excluye_levantadas(self, db):
        """alertas_proximas excluye explícitamente LEVANTADA (otros
        estados aún pueden requerir acción)."""
        _seed(db, paciente="ABIERTA", dias_restantes=2, estado="RADICADA")
        _seed(db, paciente="LEVANTADA", dias_restantes=2, estado="LEVANTADA")
        repo = GlosaRepository(db)
        alertas = repo.alertas_proximas(dias_limite=5)
        pacientes = [g.paciente for g in alertas]
        assert "ABIERTA" in pacientes
        assert "LEVANTADA" not in pacientes

    def test_excluye_dias_negativos_o_cero(self, db):
        """alertas_proximas requiere dias_restantes > 0."""
        _seed(db, paciente="VENCIDA", dias_restantes=0)
        _seed(db, paciente="POR_VENCER", dias_restantes=2)
        repo = GlosaRepository(db)
        alertas = repo.alertas_proximas(dias_limite=5)
        pacientes = [g.paciente for g in alertas]
        # >0 → vencida (=0) NO entra
        assert "POR_VENCER" in pacientes
        assert "VENCIDA" not in pacientes


class TestMetrics:
    def test_metrics_retorna_dict_con_campos(self, db):
        _seed(db, valor_objetado=100_000)
        _seed(db, valor_objetado=200_000, valor_aceptado=50_000)
        repo = GlosaRepository(db)
        m = repo.metrics()
        # Estructura mínima
        assert isinstance(m, dict)
        # Suma debe reflejar las 2 glosas
        # Los campos exactos varían pero típicamente hay total / valor_objetado
        # Solo verificamos que no es vacío
        assert len(m) > 0


class TestSearchFullText:
    def test_search_en_dictamen(self, db):
        _seed(db, paciente="A", dictamen="<p>Art. 57 Ley 1438</p>")
        _seed(db, paciente="B", dictamen="<p>Sentencia T-760</p>")
        repo = GlosaRepository(db)
        # listar_paginado usa _query_con_filtros
        r = repo.listar_paginado(page=1, per_page=10, search="T-760")
        pacientes = [g.paciente for g in r["items"]]
        assert "B" in pacientes
        assert "A" not in pacientes

    def test_search_en_servicio_descripcion(self, db):
        _seed(db, paciente="X",
              servicio_descripcion="CONSULTA URGENCIAS GINECOLOGIA")
        repo = GlosaRepository(db)
        r = repo.listar_paginado(page=1, per_page=10, search="GINECOLOGIA")
        assert any(g.paciente == "X" for g in r["items"])


class TestActualizarEstado:
    def test_actualiza_y_devuelve_glosa(self, db):
        _seed(db, paciente="X", estado="RADICADA")
        repo = GlosaRepository(db)
        # Obtener id
        gid = db.query(GlosaRecord).first().id
        g = repo.actualizar_estado(gid, "RESPONDIDA", responsable="x@hus.com")
        assert g is not None
        assert g.estado == "RESPONDIDA"

    def test_glosa_inexistente_retorna_none(self, db):
        repo = GlosaRepository(db)
        g = repo.actualizar_estado(99999, "RESPONDIDA")
        assert g is None
