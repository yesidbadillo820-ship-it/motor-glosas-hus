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

    # ── La tercera puerta: reabrir para corregir ──────────────────────────
    #
    # `transicionar` y `transicionar-lote` ya cerraban el paso al VIEWER.
    # `reabrir-para-corregir` quedó abierta, y mueve hasta 200 glosas de
    # RESPONDIDA a pendiente en una sola llamada. Que la pantalla no le
    # muestre el botón no es una guarda: la API se puede llamar directo.

    def test_viewer_no_puede_reabrir(self, cliente, db_session):
        _glosa(db_session, estado="RESPONDIDA", workflow_state="RESPONDIDA")
        gid = db_session.query(GlosaRecord).first().id
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.post(
            "/workflow/reabrir-para-corregir",
            json={"glosa_ids": [gid], "motivo": "El dictamen citaba un contrato vencido"},
        )
        assert r.status_code == 403

    def test_auditor_no_reabre_la_glosa_de_otro(self, cliente, db_session):
        _glosa(
            db_session,
            estado="RESPONDIDA",
            workflow_state="RESPONDIDA",
            auditor_email="otro@hus.com",
        )
        gid = db_session.query(GlosaRecord).first().id
        r = cliente.post(
            "/workflow/reabrir-para-corregir",
            json={"glosa_ids": [gid], "motivo": "El dictamen citaba un contrato vencido"},
        )
        assert r.json()["reabiertas"] == 0
        assert r.json()["fallidas"][0]["error"] == "asignada a otro auditor"

    def test_coordinador_si_reabre(self, cliente, db_session):
        _glosa(db_session, estado="RESPONDIDA", workflow_state="RESPONDIDA")
        gid = db_session.query(GlosaRecord).first().id
        cliente.estado["usuario"] = _usuario(rol=ROL_COORDINADOR)
        r = cliente.post(
            "/workflow/reabrir-para-corregir",
            json={"glosa_ids": [gid], "motivo": "El dictamen citaba un contrato vencido"},
        )
        assert r.status_code == 200
        assert r.json()["reabiertas"] == 1


class TestMotivoDeReaperturaQuedaEnAuditoria:
    """Reabrir una glosa ya respondida rehace trabajo cerrado.

    El motivo tenía valor por defecto en el servidor —"Reabrir para corregir
    dictamen"—, así que la pantalla lo pedía pero nada lo exigía: una llamada
    sin motivo dejaba esa frase genérica en el registro de auditoría, y
    después no había forma de saber por qué se reabrió.
    """

    def test_sin_motivo_no_se_reabre(self, cliente, db_session):
        _glosa(db_session, estado="RESPONDIDA", workflow_state="RESPONDIDA")
        gid = db_session.query(GlosaRecord).first().id
        r = cliente.post("/workflow/reabrir-para-corregir", json={"glosa_ids": [gid]})
        assert r.status_code == 422

    def test_un_motivo_de_relleno_tampoco_pasa(self, cliente, db_session):
        _glosa(db_session, estado="RESPONDIDA", workflow_state="RESPONDIDA")
        gid = db_session.query(GlosaRecord).first().id
        r = cliente.post(
            "/workflow/reabrir-para-corregir", json={"glosa_ids": [gid], "motivo": "   x  "}
        )
        assert r.status_code == 422

    def test_el_motivo_real_queda_escrito_en_la_glosa(self, cliente, db_session):
        _glosa(db_session, estado="RESPONDIDA", workflow_state="RESPONDIDA")
        gid = db_session.query(GlosaRecord).first().id
        motivo = "El dictamen citaba la Res. 3047, derogada por la 2284"
        r = cliente.post(
            "/workflow/reabrir-para-corregir", json={"glosa_ids": [gid], "motivo": motivo}
        )
        assert r.status_code == 200
        db_session.expire_all()
        assert db_session.query(GlosaRecord).get(gid).nota_workflow == motivo

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


class TestLaCuartaPuerta:
    """`PATCH /glosas/{id}/estado` era la más ancha de las cuatro.

    Las tres de `workflow.py` ya están cerradas. Esta pone la glosa en
    cualquiera de los once estados —incluidos LEVANTADA (el hospital ganó) y
    ACEPTADA (el hospital desistió)— y bastaba con estar autenticado. Encima
    guardaba `responsable="sistema"`, así que el registro no decía quién fue.
    """

    def test_viewer_no_puede_cambiar_el_estado(self, cliente, db_session):
        _glosa(db_session, estado="RADICADA", workflow_state="RADICADA")
        gid = db_session.query(GlosaRecord).first().id
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.patch(f"/glosas/{gid}/estado?nuevo_estado=LEVANTADA")
        assert r.status_code == 403

    def test_auditor_no_cambia_el_estado_de_otro(self, cliente, db_session):
        _glosa(db_session, estado="RADICADA", auditor_email="otro@hus.com")
        gid = db_session.query(GlosaRecord).first().id
        r = cliente.patch(f"/glosas/{gid}/estado?nuevo_estado=LEVANTADA")
        assert r.status_code == 403

    def test_queda_escrito_quien_lo_hizo_no_el_sistema(self, cliente, db_session):
        _glosa(db_session, estado="RADICADA", auditor_email="ana@hus.com")
        gid = db_session.query(GlosaRecord).first().id
        r = cliente.patch(f"/glosas/{gid}/estado?nuevo_estado=LEVANTADA")
        assert r.status_code == 200
        db_session.expire_all()
        glosa = db_session.query(GlosaRecord).get(gid)
        assert glosa.responsable != "sistema"
        assert glosa.responsable == "ana@hus.com"


class TestContratosNoLosBorraCualquiera:
    """El contrato es la base de todo dictamen de esa EPS.

    Borrarlo —o borrar sus cláusulas— deja a la IA sin nada literal que citar.
    Bastaba con estar autenticado, así que un VIEWER podía hacerlo.
    """

    def test_viewer_no_borra_un_contrato(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        assert cliente.delete("/contratos/COOSALUD").status_code == 403

    def test_auditor_tampoco_borra(self, cliente):
        """Subir el contrato sí es su trabajo; borrarlo no."""
        assert cliente.delete("/contratos/COOSALUD").status_code == 403

    def test_viewer_no_sube_un_contrato(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.post("/contratos/upsert", json={"eps": "COOSALUD", "contenido": "x"})
        assert r.status_code == 403


class TestPreauditoriaNoLaEscribeUnViewer:
    """Las siete rutas que escriben en Pre-auditoría son del flujo del auditor.

    La más delicada es la última: el oficio de devolución es un documento que
    **sale del hospital** con un consecutivo. Bastaba con estar autenticado.
    Leer el consolidado sigue abierto: leer no cambia nada.
    """

    def test_viewer_no_registra_un_oficio(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.post("/preauditoria/oficios", json={"numero": "FHUS-1"})
        assert r.status_code == 403

    def test_viewer_no_audita_una_factura(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.patch("/preauditoria/facturas/1/auditar", json={"resultado": "RADICADA"})
        assert r.status_code == 403

    def test_viewer_no_emite_oficio_de_devolucion(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.post("/preauditoria/oficios/1/oficio-devolucion", json={})
        assert r.status_code == 403

    def test_el_auditor_conserva_su_trabajo(self, cliente):
        """No se cierra de más: registrar el oficio es su tarea diaria."""
        r = cliente.post("/preauditoria/oficios", json={"numero": "FHUS-1"})
        assert r.status_code != 403


class TestPlantillasYNotasCredito:
    """Tercer lote del barrido: lo compartido y lo que mueve plata.

    Las plantillas son de todo el equipo: la que escribe un gestor la usan
    todos al responder, y desactivarla se la quita a todos. La nota crédito es
    plata que el hospital devuelve.
    """

    def test_viewer_no_crea_plantillas(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.post("/plantillas/", json={"nombre": "x", "contenido": "y"})
        assert r.status_code == 403

    def test_auditor_si_crea_plantillas(self, cliente):
        """Escribir una plantilla es su trabajo; no se cierra de más."""
        r = cliente.post("/plantillas/", json={"nombre": "x", "contenido": "y"})
        assert r.status_code != 403

    def test_auditor_no_borra_una_plantilla_del_equipo(self, cliente):
        assert cliente.delete("/plantillas/1").status_code == 403

    def test_coordinador_si_la_borra(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_COORDINADOR)
        assert cliente.delete("/plantillas/1").status_code != 403

    def test_viewer_no_escribe_una_nota_credito(self, cliente, db_session):
        _glosa(db_session, estado="ACEPTADA", valor_aceptado=100000)
        gid = db_session.query(GlosaRecord).first().id
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.patch(f"/glosas/{gid}/nota-credito", json={"numero_nota": "NC-1"})
        assert r.status_code == 403

    def test_la_nota_credito_esta_implementada_una_sola_vez(self):
        """Estaba dos veces: en `glosas.py` y en `nota_credito.py`.

        Las dos se montaban en la misma ruta, así que servía la primera —la de
        `glosas.py`, que además registra en auditoría— y la otra era código
        muerto que nadie ejecutaba nunca. Nadie lo sabía: el arreglo de
        permisos que se le hizo a la copia muerta no habría tenido efecto.
        """
        from app.main import app

        rutas = [r for r in app.routes if getattr(r, "path", "").endswith("/nota-credito")]
        por_metodo = {}
        for r in rutas:
            for m in getattr(r, "methods", set()) - {"HEAD", "OPTIONS"}:
                por_metodo.setdefault(m, []).append(r.path)
        duplicadas = {m: p for m, p in por_metodo.items() if len(p) > 1}
        assert not duplicadas, f"La nota crédito volvió a estar duplicada: {duplicadas}"
