"""Épica E00 — Cimiento: seguridad, cumplimiento y trazabilidad (28-jul-2026).

Cada prueba fija un hallazgo verificado de la auditoría:

  1. El sistema declaraba `cifrado_fernet: true` con solo tener la variable de
     entorno puesta, mientras `cifrado.py` no tenía un solo importador en
     producción y el nombre del paciente viajaba en texto plano.
  2. `GET /glosas/historial` devolvía el nombre del paciente de TODAS las
     glosas del hospital a cualquier usuario autenticado.
  3. `POST /workflow/{id}/transicionar` escribía las mismas columnas que
     `PATCH /glosas/{id}/workflow` sin comprobar el rol: un VIEWER cerraba
     glosas por la puerta de al lado.
  4. `SECRET_KEY` vacía (docker-compose la inyecta vacía si falta en el .env)
     no abortaba el arranque: los tokens se firmaban con clave nula.
  5. `/sistema/salud/publico` — público y sin límite de tasa — recorría 30 días
     de glosas y corría la detección de anomalías para devolver dos campos.
  6. `/admin/reset-datos` podía borrar el audit_log, la única fuente legal de
     trazabilidad.
  7. `audit_log.ip` existía y estaba siempre en NULL.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import (
    GlosaRecord,
    UsuarioRecord,
    ROL_AUDITOR,
    ROL_COORDINADOR,
    ROL_VIEWER,
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


def _usuario(rol=ROL_AUDITOR, email="ana@hus.com", nombre="Ana Torres"):
    return UsuarioRecord(id=1, email=email, nombre=nombre, rol=rol, activo=1)


@pytest.fixture
def cliente(db_session):
    """TestClient con el usuario inyectable por test."""
    from app.api.deps import get_usuario_actual
    from app.main import app

    estado = {"usuario": _usuario()}
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: estado["usuario"]
    with TestClient(app) as c:
        c.estado = estado  # el test cambia el rol con c.estado["usuario"] = ...
        yield c
    app.dependency_overrides.clear()


def _glosa(db, **kw):
    kw.setdefault("eps", "COOSALUD")
    kw.setdefault("paciente", "Carlos Alberto Ruiz")
    kw.setdefault("factura", "HUS0000224871")
    db.add(GlosaRecord(**kw))
    db.commit()


# ─── 1. El sistema no puede declarar un cifrado que no aplica ──────────────


class TestCifradoHonesto:
    def test_sin_campos_cableados_no_hay_cifrado_aunque_haya_clave(self, monkeypatch):
        from app.services import cifrado

        monkeypatch.setattr(cifrado, "CAMPOS_CIFRADOS", ())
        monkeypatch.setattr(cifrado, "hay_clave", lambda: True)
        assert cifrado.cifrado_activo() is False

    def test_con_campos_y_clave_si_hay_cifrado(self, monkeypatch):
        from app.services import cifrado

        monkeypatch.setattr(cifrado, "CAMPOS_CIFRADOS", ("historial.paciente",))
        monkeypatch.setattr(cifrado, "hay_clave", lambda: True)
        assert cifrado.cifrado_activo() is True

    def test_con_campos_pero_sin_clave_no_hay_cifrado(self, monkeypatch):
        from app.services import cifrado

        monkeypatch.setattr(cifrado, "CAMPOS_CIFRADOS", ("historial.paciente",))
        monkeypatch.setattr(cifrado, "hay_clave", lambda: False)
        assert cifrado.cifrado_activo() is False

    def test_hoy_no_hay_ningun_campo_cifrado(self):
        """Deja constancia del estado real: ninguno. Cuando se cifre el primer
        campo, esta prueba se actualiza junto con el cableado."""
        from app.services.cifrado import CAMPOS_CIFRADOS

        assert CAMPOS_CIFRADOS == ()


# ─── 2. El nombre del paciente no se muestra a quien no le corresponde ─────


class TestPacienteEnHistorial:
    def test_auditor_no_ve_el_paciente_de_glosa_de_otro(self, cliente, db_session):
        _glosa(db_session, auditor_email="otro@hus.com")
        d = cliente.get("/glosas/historial").json()
        assert d[0]["paciente"] == "C. A. R."
        assert "Carlos" not in str(d)

    def test_auditor_si_ve_el_paciente_de_su_propia_glosa(self, cliente, db_session):
        _glosa(db_session, auditor_email="ana@hus.com")
        d = cliente.get("/glosas/historial").json()
        assert d[0]["paciente"] == "Carlos Alberto Ruiz"

    def test_auditor_ve_el_paciente_si_la_glosa_no_tiene_dueno(self, cliente, db_session):
        # Trabajo sin asignar: cualquiera puede tomarlo, ocultarlo lo trabaría.
        _glosa(db_session)
        d = cliente.get("/glosas/historial").json()
        assert d[0]["paciente"] == "Carlos Alberto Ruiz"

    def test_coordinador_ve_todo(self, cliente, db_session):
        _glosa(db_session, auditor_email="otro@hus.com")
        cliente.estado["usuario"] = _usuario(rol=ROL_COORDINADOR)
        d = cliente.get("/glosas/historial").json()
        assert d[0]["paciente"] == "Carlos Alberto Ruiz"

    def test_viewer_nunca_ve_el_paciente(self, cliente, db_session):
        _glosa(db_session)  # sin dueño: aun así el VIEWER no lo ve
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        d = cliente.get("/glosas/historial").json()
        assert d[0]["paciente"] == "C. A. R."

    def test_gestor_por_nombre_tambien_cuenta_como_dueno(self, cliente, db_session):
        _glosa(db_session, gestor_nombre="Ana Torres")
        d = cliente.get("/glosas/historial").json()
        assert d[0]["paciente"] == "Carlos Alberto Ruiz"

    def test_glosa_sin_paciente_no_revienta(self, cliente, db_session):
        _glosa(db_session, paciente=None, auditor_email="otro@hus.com")
        d = cliente.get("/glosas/historial").json()
        assert d[0]["paciente"] is None


# ─── 3. El bypass de autorización del workflow ────────────────────────────


class TestWorkflowSinBypass:
    def test_viewer_no_puede_transicionar(self, cliente, db_session):
        _glosa(db_session, estado="RADICADA", workflow_state="RADICADA")
        gid = db_session.query(GlosaRecord).first().id
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.post(f"/workflow/{gid}/transicionar", json={"hacia": "RESPONDIDA"})
        assert r.status_code == 403

    def test_viewer_no_puede_transicionar_en_lote(self, cliente, db_session):
        _glosa(db_session, estado="RADICADA", workflow_state="RADICADA")
        gid = db_session.query(GlosaRecord).first().id
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.post(
            "/workflow/transicionar-lote", json={"glosa_ids": [gid], "hacia": "RESPONDIDA"}
        )
        assert r.status_code == 403

    def test_auditor_no_toca_glosa_de_otro(self, cliente, db_session):
        _glosa(
            db_session,
            estado="RADICADA",
            workflow_state="RADICADA",
            auditor_email="otro@hus.com",
        )
        gid = db_session.query(GlosaRecord).first().id
        r = cliente.post(f"/workflow/{gid}/transicionar", json={"hacia": "RESPONDIDA"})
        assert r.status_code == 403

    def test_auditor_si_transiciona_la_suya(self, cliente, db_session):
        _glosa(
            db_session,
            estado="RADICADA",
            workflow_state="RADICADA",
            auditor_email="ana@hus.com",
        )
        gid = db_session.query(GlosaRecord).first().id
        r = cliente.post(f"/workflow/{gid}/transicionar", json={"hacia": "RESPONDIDA"})
        assert r.status_code == 200

    def test_lote_salta_las_de_otro_sin_abortar(self, cliente, db_session):
        _glosa(db_session, estado="RADICADA", workflow_state="RADICADA", factura="A")
        _glosa(
            db_session,
            estado="RADICADA",
            workflow_state="RADICADA",
            factura="B",
            auditor_email="otro@hus.com",
        )
        ids = [g.id for g in db_session.query(GlosaRecord).all()]
        r = cliente.post(
            "/workflow/transicionar-lote", json={"glosa_ids": ids, "hacia": "RESPONDIDA"}
        )
        assert r.status_code == 200
        d = r.json()
        assert d["procesadas"] == 1
        assert any("otro auditor" in f.get("error", "") for f in d["fallidas"])


# ─── 4. SECRET_KEY vacía aborta el arranque ───────────────────────────────


class TestSecretKey:
    def test_secret_key_vacia_aborta(self, monkeypatch):
        from app.core import config

        monkeypatch.setenv("SECRET_KEY", "   ")
        config.get_settings.cache_clear()
        with pytest.raises(config.ConfiguracionInsegura):
            config.check_security_config()
        config.get_settings.cache_clear()

    def test_secret_key_valida_no_aborta(self, monkeypatch):
        from app.core import config

        monkeypatch.setenv("SECRET_KEY", "x" * 40)
        monkeypatch.setenv("ADMIN_PASSWORD", "una-clave-larga-y-propia")
        config.get_settings.cache_clear()
        config.check_security_config()  # no debe levantar
        config.get_settings.cache_clear()


# ─── 5. El healthcheck público es barato ──────────────────────────────────


class TestSaludPublica:
    def test_no_corre_deteccion_de_anomalias(self, cliente, monkeypatch):
        import app.services.health_monitor as hm

        def _explota(*a, **k):
            raise AssertionError("el healthcheck público no debe correr esto")

        monkeypatch.setattr(hm, "_check_anomalias", _explota)
        monkeypatch.setattr(hm, "_check_actividad_reciente", _explota)
        r = cliente.get("/sistema/salud/publico")
        assert r.status_code == 200
        assert set(r.json()) == {"estado", "generado_en"}


# ─── 6. El registro de auditoría no se borra ──────────────────────────────


class TestAuditLogIntocable:
    def test_reset_datos_no_borra_el_audit_log(self, cliente, db_session):
        from app.models.db import AuditLogRecord, ROL_SUPER_ADMIN

        db_session.add(
            AuditLogRecord(usuario_email="x@hus.com", usuario_rol="AUDITOR", accion="X", tabla="t")
        )
        db_session.commit()
        cliente.estado["usuario"] = _usuario(rol=ROL_SUPER_ADMIN)
        r = cliente.post(
            "/admin/reset-datos",
            json={"confirmar": "CONFIRMAR-BORRADO-TOTAL", "borrar_audit_log": True},
        )
        assert r.status_code == 200
        assert r.json()["registros_borrados"]["audit_log"] == 0
        assert "audit_log" in r.json()["preservado"]
        assert db_session.query(AuditLogRecord).count() >= 1


# ─── 7. La IP queda registrada ────────────────────────────────────────────


class TestIpEnAuditoria:
    def test_registrar_toma_la_ip_del_request(self, db_session):
        from app.core.logging_utils import client_ip_var
        from app.repositories.audit_repository import AuditRepository

        token = client_ip_var.set("190.85.1.7")
        try:
            log = AuditRepository(db_session).registrar(
                usuario_email="ana@hus.com", usuario_rol="AUDITOR", accion="X", tabla="historial"
            )
        finally:
            client_ip_var.reset(token)
        assert log.ip == "190.85.1.7"

    def test_ip_explicita_gana_sobre_el_contexto(self, db_session):
        from app.core.logging_utils import client_ip_var
        from app.repositories.audit_repository import AuditRepository

        token = client_ip_var.set("190.85.1.7")
        try:
            log = AuditRepository(db_session).registrar(
                usuario_email="ana@hus.com",
                usuario_rol="AUDITOR",
                accion="X",
                tabla="historial",
                ip="10.0.0.1",
            )
        finally:
            client_ip_var.reset(token)
        assert log.ip == "10.0.0.1"

    def test_cloudflare_gana_sobre_forwarded_for(self):
        from app.core.correlation import _ip_del_cliente

        class _Req:
            headers = {"CF-Connecting-IP": "1.2.3.4", "X-Forwarded-For": "9.9.9.9, 8.8.8.8"}
            client = None

        assert _ip_del_cliente(_Req()) == "1.2.3.4"

    def test_forwarded_for_toma_el_primer_salto(self):
        from app.core.correlation import _ip_del_cliente

        class _Req:
            headers = {"X-Forwarded-For": "9.9.9.9, 8.8.8.8"}
            client = None

        assert _ip_del_cliente(_Req()) == "9.9.9.9"
