"""Endpoints del Motor de Vencimientos (28-jul-2026).

El tablero funciona SIEMPRE, esté o no configurado el correo — es preferible
que el área vea el listado en pantalla a que nadie se entere. Y el envío
SIMULA por defecto: estrenar la configuración no puede significar mandar
cincuenta correos sin querer.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import GlosaRecord, UsuarioRecord


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def cliente(db_session):
    from app.api.deps import get_usuario_actual
    from app.main import app

    usuario = UsuarioRecord(
        id=1, email="ana@hus.com", nombre="Ana Torres", rol="COORDINADOR", activo=1
    )
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _glosa(db, dias, **kw):
    kw.setdefault("eps", "COOSALUD")
    kw.setdefault("estado", "PENDIENTE")
    kw.setdefault("valor_objetado", 1_000_000)
    kw.setdefault("paciente", "Carlos Alberto Ruiz")
    db.add(GlosaRecord(dias_restantes=dias, **kw))
    db.commit()


@pytest.fixture(autouse=True)
def umbrales_del_area(monkeypatch):
    monkeypatch.setenv("VENCIMIENTOS_DIAS_PREVENTIVO", "10")
    monkeypatch.setenv("VENCIMIENTOS_DIAS_ALTA", "5")
    monkeypatch.setenv("VENCIMIENTOS_DIAS_CRITICA", "2")


class TestTablero:
    def test_clasifica_por_urgencia(self, cliente, db_session):
        _glosa(db_session, -3, factura="A", valor_objetado=20_054_751)
        _glosa(db_session, 1, factura="B")
        _glosa(db_session, 4, factura="C")
        _glosa(db_session, 9, factura="D")
        _glosa(db_session, 40, factura="E")
        d = cliente.get("/alertas/vencimientos").json()
        assert d["conteos"] == {"PREVENTIVO": 1, "ALTA": 1, "CRITICA": 1, "VENCIDA": 1}
        assert d["total_en_riesgo"] == 4

    def test_reporta_el_valor_en_riesgo(self, cliente, db_session):
        _glosa(db_session, -3, factura="A", valor_objetado=20_054_751)
        d = cliente.get("/alertas/vencimientos").json()
        assert d["valor_en_riesgo"] == 20_054_751

    def test_las_cerradas_no_cuentan(self, cliente, db_session):
        _glosa(db_session, -10, factura="A", estado="LEVANTADA")
        d = cliente.get("/alertas/vencimientos").json()
        assert d["total_en_riesgo"] == 0

    def test_funciona_sin_correo_configurado(self, cliente, db_session, monkeypatch):
        for v in ("VENCIMIENTOS_CORREO_ALTA", "VENCIMIENTOS_CORREO_CRITICA"):
            monkeypatch.setenv(v, "")
        monkeypatch.setenv("VENCIMIENTOS_CORREO_GESTOR", "0")
        _glosa(db_session, -1, factura="A")
        d = cliente.get("/alertas/vencimientos").json()
        assert d["total_en_riesgo"] == 1
        assert d["avisos_configurados"] is False

    def test_devuelve_los_umbrales_vigentes(self, cliente):
        d = cliente.get("/alertas/vencimientos").json()
        assert d["umbrales"] == {"preventivo": 10, "alta": 5, "critica": 2}

    def test_no_expone_el_nombre_del_paciente(self, cliente, db_session):
        _glosa(db_session, -1, factura="A")
        d = cliente.get("/alertas/vencimientos").json()
        assert "Carlos" not in str(d)


class TestNotificar:
    def test_simula_por_defecto(self, cliente, db_session, monkeypatch):
        monkeypatch.setenv("VENCIMIENTOS_CORREO_VENCIDA", "direccion@hus.com")
        _glosa(db_session, -5, factura="A", auditor_email="luis@hus.com")
        d = cliente.post("/alertas/vencimientos/notificar").json()
        assert d["simulado"] is True
        assert d["enviados"] == 0
        assert sorted(d["bandejas"]) == ["direccion@hus.com", "luis@hus.com"]

    def test_una_bandeja_por_persona_con_su_conteo(self, cliente, db_session, monkeypatch):
        monkeypatch.setenv("VENCIMIENTOS_CORREO_CRITICA", "cartera@hus.com")
        _glosa(db_session, 1, factura="A", auditor_email="ana@hus.com")
        _glosa(db_session, 1, factura="B", auditor_email="ana@hus.com")
        d = cliente.post("/alertas/vencimientos/notificar").json()
        assert d["bandejas"]["ana@hus.com"]["total"] == 2
        assert d["bandejas"]["cartera@hus.com"]["por_urgencia"]["CRITICA"] == 2

    def test_sin_destinatarios_avisa_que_falta_configurar(self, cliente, db_session, monkeypatch):
        for v in (
            "VENCIMIENTOS_CORREO_ALTA",
            "VENCIMIENTOS_CORREO_CRITICA",
            "VENCIMIENTOS_CORREO_VENCIDA",
        ):
            monkeypatch.setenv(v, "")
        monkeypatch.setenv("VENCIMIENTOS_CORREO_GESTOR", "0")
        _glosa(db_session, -1, factura="A")
        d = cliente.post("/alertas/vencimientos/notificar").json()
        assert d["enviados"] == 0
        assert "VENCIMIENTOS_CORREO_ALTA" in d["detalle"]

    def test_una_vencida_sin_gestor_igual_escala(self, cliente, db_session, monkeypatch):
        """El caso de las 3 facturas de junio: sin dueño y vencidas."""
        monkeypatch.setenv("VENCIMIENTOS_CORREO_VENCIDA", "direccion@hus.com")
        _glosa(db_session, -45, factura="A", auditor_email="")
        d = cliente.post("/alertas/vencimientos/notificar").json()
        assert "direccion@hus.com" in d["bandejas"]

    def test_un_correo_caido_no_tumba_el_resto(self, cliente, db_session, monkeypatch):
        monkeypatch.setenv("VENCIMIENTOS_CORREO_CRITICA", "cartera@hus.com")
        _glosa(db_session, 1, factura="A", auditor_email="ana@hus.com")

        import app.services.alerta_service as als

        def _revienta(self, glosas, dias_limite=5, destinatarios=None):
            if destinatarios and destinatarios[0] == "ana@hus.com":
                raise RuntimeError("buzón lleno")
            return True, "enviado"

        monkeypatch.setattr(als.EmailService, "enviar_alerta_glosas", _revienta)
        d = cliente.post("/alertas/vencimientos/notificar?simular=false").json()
        assert d["enviados"] == 1
        assert d["fallidos"][0]["correo"] == "ana@hus.com"
