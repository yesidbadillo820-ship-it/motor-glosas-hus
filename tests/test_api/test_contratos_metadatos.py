"""Tests del editor de metadatos enriquecidos del contrato.

Endpoints bajo prueba (cierran el hueco del PR #106 — columnas creadas
pero sin editor, auditoría 10-jun-2026):
  - GET  /contratos/{eps}/metadatos        (AUDITOR+ lee)
  - PUT  /contratos/{eps}/metadatos        (COORDINADOR/SUPER_ADMIN escribe)
  - GET  /contratos/{eps}/anexos/sugeridos (plantillas para el panel)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import AuditLogRecord, ContratoRecord, UsuarioRecord

# Payload realista — el contrato DIGSA/DMBUG que la "otra IA" citaba y
# el sistema HUS no podía (datos del caso de la auditoría 10-jun-2026).
PAYLOAD_COMPLETO = {
    "numero_contrato": "440-DIGSA/DMBUG-2025",
    "nit_eps": "901.541.137-1",
    "nit_ips": "900.006.037-4",
    "razon_social_eps": "DIRECCIÓN GENERAL DE SANIDAD MILITAR",
    "razon_social_ips": "ESE HOSPITAL UNIVERSITARIO DE SANTANDER",
    "numero_proceso_secop": "CD477",
    "secop_url": "https://community.secop.gov.co/Public/Tendering/OpportunityDetail/Index?noticeUID=CD477",
    "fecha_suscripcion": "2025-07-30",
    "fecha_inicio": "2025-07-31",
    "fecha_fin": "2026-07-30",
    "objeto_contractual": "Prestación de servicios integrales de salud a los usuarios del Subsistema de Salud de las Fuerzas Militares adscritos al DMBUG.",
    "anexos_descripcion": [
        {"nombre": "Anexo 1", "descripcion": "Tarifas y servicios pactados"},
        {"nombre": "Anexo 05", "descripcion": "Dispositivos médicos"},
    ],
    "modalidades_tarifarias": ["TARIFA PROPIA ESE", "SOAT UVB"],
}


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
def usuario_actual():
    """Usuario mutable: los tests cambian .rol para probar los gates."""
    return UsuarioRecord(
        id=1,
        email="meta-tester@hus.gov.co",
        nombre="Meta Tester",
        rol="SUPER_ADMIN",
        activo=1,
        password_hash="x",
    )


@pytest.fixture
def client(db_session, usuario_actual):
    from app.api.deps import get_usuario_actual
    from app.main import app

    def _db_override():
        yield db_session

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_actual
    # SIN context manager: no disparar el lifespan pesado (ver conftest).
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def client_sin_auth(db_session):
    """Cliente sin override de usuario — para probar el 401 real."""
    from app.main import app

    def _db_override():
        yield db_session

    app.dependency_overrides[get_db] = _db_override
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


def _sembrar_contrato_completo(db_session) -> ContratoRecord:
    contrato = ContratoRecord(
        eps="DIGSA SANTANDER",
        detalles="Contrato vigente DMBUG",
        numero_contrato="440-DIGSA/DMBUG-2025",
        nit_eps="901.541.137-1",
        nit_ips="900.006.037-4",
        razon_social_eps="DIRECCIÓN GENERAL DE SANIDAD MILITAR",
        razon_social_ips="ESE HOSPITAL UNIVERSITARIO DE SANTANDER",
        numero_proceso_secop="CD477",
        secop_url="https://community.secop.gov.co/Public/CD477",
        fecha_suscripcion=datetime(2025, 7, 30, tzinfo=timezone.utc),
        fecha_inicio=datetime(2025, 7, 31, tzinfo=timezone.utc),
        fecha_fin=datetime(2026, 7, 30, tzinfo=timezone.utc),
        objeto_contractual="Prestación de servicios de salud al personal DMBUG.",
        anexos_descripcion=json.dumps(
            [{"nombre": "Anexo 1", "descripcion": "Tarifas y servicios pactados"}],
            ensure_ascii=False,
        ),
        modalidades_tarifarias=json.dumps(["TARIFA PROPIA ESE", "SOAT UVB"]),
    )
    db_session.add(contrato)
    db_session.commit()
    return contrato


# ─── GET /contratos/{eps}/metadatos ──────────────────────────────────────────


class TestObtenerMetadatos:
    def test_404_si_eps_sin_contrato(self, client):
        r = client.get("/contratos/EPS_FANTASMA/metadatos")
        assert r.status_code == 404
        assert "EPS_FANTASMA" in r.json()["detail"]

    def test_devuelve_todos_los_campos(self, client, db_session):
        _sembrar_contrato_completo(db_session)
        r = client.get("/contratos/DIGSA SANTANDER/metadatos")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["eps"] == "DIGSA SANTANDER"
        assert d["detalles"] == "Contrato vigente DMBUG"
        assert d["numero_contrato"] == "440-DIGSA/DMBUG-2025"
        assert d["nit_eps"] == "901.541.137-1"
        assert d["nit_ips"] == "900.006.037-4"
        assert d["razon_social_ips"] == "ESE HOSPITAL UNIVERSITARIO DE SANTANDER"
        assert d["numero_proceso_secop"] == "CD477"
        assert d["secop_url"].startswith("https://")
        # Fechas como ISO YYYY-MM-DD
        assert d["fecha_suscripcion"] == "2025-07-30"
        assert d["fecha_inicio"] == "2025-07-31"
        assert d["fecha_fin"] == "2026-07-30"
        # Listas parseadas del Text JSON
        assert d["anexos_descripcion"] == [
            {"nombre": "Anexo 1", "descripcion": "Tarifas y servicios pactados"}
        ]
        assert d["modalidades_tarifarias"] == ["TARIFA PROPIA ESE", "SOAT UVB"]
        # Existentes pre-PR#106 también presentes
        assert "pdf_path" in d and "pdf_subido_en" in d

    def test_listas_vacias_y_fechas_null_cuando_no_hay_datos(self, client, db_session):
        db_session.add(ContratoRecord(eps="SANITAS", detalles="contrato base"))
        db_session.commit()
        r = client.get("/contratos/SANITAS/metadatos")
        assert r.status_code == 200
        d = r.json()
        assert d["anexos_descripcion"] == []
        assert d["modalidades_tarifarias"] == []
        assert d["fecha_inicio"] is None
        assert d["numero_contrato"] is None

    def test_json_corrupto_en_bd_no_rompe_el_get(self, client, db_session):
        # Defensivo: si una migración/import dejó JSON inválido, el GET
        # degrada a [] en vez de 500.
        db_session.add(ContratoRecord(eps="SURA", detalles="x", anexos_descripcion="{{{no-json"))
        db_session.commit()
        r = client.get("/contratos/SURA/metadatos")
        assert r.status_code == 200
        assert r.json()["anexos_descripcion"] == []

    def test_auditor_puede_leer(self, client, usuario_actual, db_session):
        _sembrar_contrato_completo(db_session)
        usuario_actual.rol = "AUDITOR"
        r = client.get("/contratos/DIGSA SANTANDER/metadatos")
        assert r.status_code == 200

    def test_busca_con_eps_normalizada(self, client, db_session):
        _sembrar_contrato_completo(db_session)
        # El registro está en mayúsculas; consulta en minúsculas resuelve
        r = client.get("/contratos/digsa santander/metadatos")
        assert r.status_code == 200
        assert r.json()["eps"] == "DIGSA SANTANDER"


# ─── PUT /contratos/{eps}/metadatos ──────────────────────────────────────────


class TestActualizarMetadatos:
    def test_put_crea_cuando_no_existe(self, client, db_session):
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=PAYLOAD_COMPLETO)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["eps"] == "DIGSA SANTANDER"
        assert d["numero_contrato"] == "440-DIGSA/DMBUG-2025"
        assert d["modalidades_tarifarias"] == ["TARIFA PROPIA ESE", "SOAT UVB"]
        # Fila creada en BD con eps normalizada
        c = db_session.query(ContratoRecord).filter_by(eps="DIGSA SANTANDER").one()
        assert c.numero_proceso_secop == "CD477"
        assert c.fecha_fin is not None

    def test_put_actualiza_idempotente(self, client, db_session):
        r1 = client.put("/contratos/DIGSA SANTANDER/metadatos", json=PAYLOAD_COMPLETO)
        r2 = client.put("/contratos/DIGSA SANTANDER/metadatos", json=PAYLOAD_COMPLETO)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.json() == r2.json()
        n = db_session.query(ContratoRecord).filter_by(eps="DIGSA SANTANDER").count()
        assert n == 1

    def test_put_no_pisa_detalles_ni_pdf(self, client, db_session):
        _sembrar_contrato_completo(db_session)
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=PAYLOAD_COMPLETO)
        assert r.status_code == 200
        c = db_session.query(ContratoRecord).filter_by(eps="DIGSA SANTANDER").one()
        assert c.detalles == "Contrato vigente DMBUG"

    def test_fecha_inicio_mayor_que_fin_400(self, client):
        payload = dict(PAYLOAD_COMPLETO, fecha_inicio="2026-08-01", fecha_fin="2025-07-30")
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 400
        assert "fecha_inicio" in r.json()["detail"]
        assert "fecha_fin" in r.json()["detail"]

    def test_fecha_invalida_400(self, client):
        payload = dict(PAYLOAD_COMPLETO, fecha_inicio="31/07/2025")
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 400
        assert "YYYY-MM-DD" in r.json()["detail"]

    def test_fechas_vacias_quedan_null(self, client, db_session):
        payload = dict(PAYLOAD_COMPLETO, fecha_suscripcion="", fecha_inicio="", fecha_fin="")
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 200
        d = r.json()
        assert d["fecha_suscripcion"] is None
        assert d["fecha_inicio"] is None
        assert d["fecha_fin"] is None

    def test_secop_url_ftp_400(self, client):
        payload = dict(PAYLOAD_COMPLETO, secop_url="ftp://secop.gov.co/CD477")
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 400
        assert "https" in r.json()["detail"]

    def test_secop_url_javascript_400(self, client):
        payload = dict(PAYLOAD_COMPLETO, secop_url="javascript:alert(1)")
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 400

    def test_secop_url_vacia_es_valida(self, client):
        payload = dict(PAYLOAD_COMPLETO, secop_url="")
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 200
        assert r.json()["secop_url"] is None

    def test_nit_normaliza_quitando_espacios(self, client):
        payload = dict(PAYLOAD_COMPLETO, nit_eps="901 541 137-1")
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 200
        assert r.json()["nit_eps"] == "901541137-1"

    def test_nit_caracteres_invalidos_400(self, client):
        payload = dict(PAYLOAD_COMPLETO, nit_ips="NIT-ABC-900")
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 400
        assert "nit_ips" in r.json()["detail"]

    def test_objeto_contractual_max_5000_400(self, client):
        payload = dict(PAYLOAD_COMPLETO, objeto_contractual="x" * 5001)
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 400
        assert "5000" in r.json()["detail"]

    def test_roundtrip_anexos(self, client):
        anexos = [
            {"nombre": "Anexo 1", "descripcion": "Tarifas y servicios pactados"},
            {"nombre": "Anexo 05", "descripcion": "Dispositivos médicos"},
            {"nombre": "Anexo técnico 5", "descripcion": "Soportes Res. 3047/2008"},
        ]
        payload = dict(PAYLOAD_COMPLETO, anexos_descripcion=anexos)
        r_put = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r_put.status_code == 200
        r_get = client.get("/contratos/DIGSA SANTANDER/metadatos")
        assert r_get.status_code == 200
        assert r_get.json()["anexos_descripcion"] == anexos

    def test_anexos_vacios_quedan_lista_vacia(self, client):
        payload = dict(PAYLOAD_COMPLETO, anexos_descripcion=[], modalidades_tarifarias=[])
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=payload)
        assert r.status_code == 200
        d = r.json()
        assert d["anexos_descripcion"] == []
        assert d["modalidades_tarifarias"] == []

    def test_auditor_no_puede_put(self, client, usuario_actual):
        usuario_actual.rol = "AUDITOR"
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=PAYLOAD_COMPLETO)
        assert r.status_code == 403

    def test_coordinador_si_puede_put(self, client, usuario_actual):
        usuario_actual.rol = "COORDINADOR"
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=PAYLOAD_COMPLETO)
        assert r.status_code == 200

    def test_audit_log_tras_put(self, client, db_session):
        r = client.put("/contratos/DIGSA SANTANDER/metadatos", json=PAYLOAD_COMPLETO)
        assert r.status_code == 200
        log = db_session.query(AuditLogRecord).filter_by(accion="UPDATE_CONTRATO_METADATOS").one()
        assert log.usuario_email == "meta-tester@hus.gov.co"
        assert log.tabla == "contratos"
        assert log.campo == "contratos.metadatos"
        assert "440-DIGSA/DMBUG-2025" in (log.valor_nuevo or "")


# ─── Permisos: sin autenticar ────────────────────────────────────────────────


class TestSinAutenticar:
    def test_get_sin_token_401(self, client_sin_auth):
        r = client_sin_auth.get("/contratos/DIGSA SANTANDER/metadatos")
        assert r.status_code == 401

    def test_put_sin_token_401(self, client_sin_auth):
        r = client_sin_auth.put("/contratos/DIGSA SANTANDER/metadatos", json=PAYLOAD_COMPLETO)
        assert r.status_code == 401

    def test_sugeridos_sin_token_401(self, client_sin_auth):
        r = client_sin_auth.get("/contratos/DIGSA SANTANDER/anexos/sugeridos")
        assert r.status_code == 401


# ─── GET /contratos/{eps}/anexos/sugeridos ───────────────────────────────────


class TestAnexosSugeridos:
    def test_devuelve_sugerencias_estandar(self, client):
        r = client.get("/contratos/CUALQUIERA/anexos/sugeridos")
        assert r.status_code == 200
        d = r.json()
        assert d["eps"] == "CUALQUIERA"
        sugeridos = d["sugeridos"]
        assert len(sugeridos) >= 2
        assert all("nombre" in a and "descripcion" in a for a in sugeridos)
        nombres = [a["nombre"] for a in sugeridos]
        assert "Anexo 1" in nombres
        assert "Anexo 05" in nombres

    def test_auditor_tambien_lee_sugerencias(self, client, usuario_actual):
        usuario_actual.rol = "AUDITOR"
        r = client.get("/contratos/CUALQUIERA/anexos/sugeridos")
        assert r.status_code == 200
