"""Tests del endpoint GET /admin/backup-db.json (R62 P2)."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import (
    AuditLogRecord, ContratoRecord, GlosaRecord,
    PlantillaGoldRecord, UsuarioRecord,
)


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
def usuario_super(db_session):
    u = UsuarioRecord(
        id=1, email="root@hus.gov.co", rol="SUPER_ADMIN",
        activo=1, password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario_super):
    from app.api.deps import get_admin
    from app.main import app
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_admin] = lambda: usuario_super
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class TestBackupDbJson:
    def test_backup_estructura_basica(self, client):
        r = client.get("/admin/backup-db.json")
        assert r.status_code == 200
        # Content-Disposition para descarga
        assert "attachment" in r.headers.get("content-disposition", "")
        assert ".json" in r.headers.get("content-disposition", "")
        # Contenido JSON parseable
        d = json.loads(r.text)
        assert "metadata" in d
        assert "glosas" in d
        assert "usuarios" in d
        assert "audit_log_90d" in d
        # Metadata mínima
        assert d["metadata"]["exportado_por"] == "root@hus.gov.co"

    def test_backup_excluye_password_hash(self, client, db_session):
        """SECURITY: el password_hash NUNCA debe estar en el backup."""
        u2 = UsuarioRecord(
            email="extra@hus.com", rol="AUDITOR", activo=1,
            password_hash=get_password_hash("secret123"),
        )
        db_session.add(u2)
        db_session.commit()
        r = client.get("/admin/backup-db.json")
        d = json.loads(r.text)
        for u in d["usuarios"]:
            assert "password_hash" not in u, (
                "REGRESIÓN crítica: backup expuso password_hash"
            )
            assert "totp_secret" not in u

    def test_backup_incluye_glosas(self, client, db_session):
        g = GlosaRecord(
            eps="FAMISANAR", paciente="X", codigo_glosa="TA0201",
            valor_objetado=100_000, etapa="RESPUESTA", estado="RADICADA",
            creado_en=ahora_utc(),
        )
        db_session.add(g)
        db_session.commit()
        r = client.get("/admin/backup-db.json")
        d = json.loads(r.text)
        assert len(d["glosas"]) == 1
        assert d["glosas"][0]["eps"] == "FAMISANAR"
        assert d["glosas"][0]["valor_objetado"] == 100_000

    def test_backup_incluye_contratos(self, client, db_session):
        c = ContratoRecord(
            eps="FAMISANAR-PRUEBA", detalles="contrato vigente con tarifas pactadas",
        )
        db_session.add(c)
        db_session.commit()
        r = client.get("/admin/backup-db.json")
        d = json.loads(r.text)
        assert len(d["contratos"]) == 1
        assert d["contratos"][0]["eps"] == "FAMISANAR-PRUEBA"

    def test_backup_audit_solo_90_dias(self, client, db_session):
        """audit_log_90d debe filtrar registros más viejos que 90 días."""
        # 1 reciente + 1 viejo
        db_session.add(AuditLogRecord(
            usuario_email="X@hus.com", accion="VIEJO",
            timestamp=ahora_utc() - timedelta(days=120),
        ))
        db_session.add(AuditLogRecord(
            usuario_email="Y@hus.com", accion="RECIENTE",
            timestamp=ahora_utc() - timedelta(days=30),
        ))
        db_session.commit()
        r = client.get("/admin/backup-db.json")
        d = json.loads(r.text)
        acciones = [x["accion"] for x in d["audit_log_90d"]]
        assert "RECIENTE" in acciones
        assert "VIEJO" not in acciones

    def test_backup_plantillas_gold_solo_activas(self, client, db_session):
        """Solo plantillas con activa=1 deben backupearse."""
        db_session.add(PlantillaGoldRecord(
            eps="FAMISANAR", codigo_glosa="TA0201",
            tipo="TA", titulo="Activa",
            argumento="texto…", activa=1,
            creado_en=ahora_utc(),
        ))
        db_session.add(PlantillaGoldRecord(
            eps="FAMISANAR", codigo_glosa="TA0202",
            tipo="TA", titulo="Desactivada",
            argumento="texto…", activa=0,
            creado_en=ahora_utc(),
        ))
        db_session.commit()
        r = client.get("/admin/backup-db.json")
        d = json.loads(r.text)
        titulos = [p["titulo"] for p in d["plantillas_gold"]]
        assert "Activa" in titulos
        assert "Desactivada" not in titulos

    def test_backup_metadata_lista_tablas(self, client):
        r = client.get("/admin/backup-db.json")
        d = json.loads(r.text)
        tablas = d["metadata"]["incluye_tablas"]
        assert "glosas" in tablas
        assert "usuarios" in tablas
        assert "audit_log_90d" in tablas
        assert "plantillas_gold" in tablas
        # NO debe estar ai_cache ni ai_calls (se regeneran)
        assert "ai_cache" not in tablas
        assert "ai_calls" not in tablas
