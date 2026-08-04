"""Toda ruta que modifica datos tiene una decisión de permisos, y está escrita.

De dónde viene: el barrido del 28-07 encontró cuatro «puertas de al lado»
—rutas que cambiaban el estado de una glosa sin comprobar el rol— y se
cerraron una por una. Al terminar quedaban 51 rutas que solo pedían estar
autenticado, y nadie sabía cuáles estaban bien así y cuáles eran otro
descuido esperando. Esta prueba convierte esa duda en una lista escrita.

La regla: una ruta que modifica datos (POST/PUT/PATCH/DELETE) tiene que
estar en UNO de estos tres cajones:

  1. Exige un rol en la puerta (`Depends(get_auditor_o_superior)` y
     compañía) — el caso normal.
  2. Es un servicio del propio usuario (su contraseña, su segundo factor,
     sus tareas): basta con estar autenticado. Van en SERVICIO_PROPIO.
  3. Comprueba el rol o la propiedad DENTRO del código, porque la regla
     depende del dato (p. ej. «esta glosa es de otro auditor»). Van en
     CHEQUEO_INTERNO, y la prueba verifica que el chequeo exista.

Una ruta nueva que no esté en ninguno rompe la suite: obliga a decidir
antes de mezclarla, que es justo lo que faltó las cuatro veces anteriores.
"""

from __future__ import annotations

import inspect

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.db import (
    ROL_AUDITOR,
    ROL_COORDINADOR,
    ROL_VIEWER,
    GlosaRecord,
    UsuarioRecord,
)

METODOS_QUE_MUTAN = {"POST", "PUT", "PATCH", "DELETE"}

GUARDIAS_DE_ROL = {
    "get_admin",
    "get_super_admin",
    "get_coordinador_o_admin",
    "get_auditor_o_superior",
    "verificar_token_agente",
}

# Cajón 2 — el usuario actuando sobre lo suyo. Un VIEWER también entra a
# trabajar: cambia su contraseña, activa su segundo factor y anota sus
# tareas. Cerrarle esto sería dejarlo sin poder ni entrar.
SERVICIO_PROPIO = {
    ("POST", "/auth/logout"),
    ("POST", "/auth/refresh"),
    ("POST", "/auth/cambiar-password"),
    ("POST", "/2fa/setup"),
    ("POST", "/2fa/activar"),
    ("POST", "/2fa/desactivar"),
    ("POST", "/usuarios/yo/rustdesk"),
    ("POST", "/usuarios/yo/vacaciones"),
    ("POST", "/usuarios/yo/tareas"),
    ("PATCH", "/usuarios/yo/tareas/{tarea_id}"),
    ("DELETE", "/usuarios/yo/tareas/{tarea_id}"),
    # El buzón de sugerencias: cualquiera del hospital puede proponer algo.
    ("POST", "/sugerencias"),
}

# Cajón 3 — la regla depende del dato, no solo del rol: «la glosa es de
# otro auditor», «el comentario es tuyo», «el lote lo creaste vos». Eso no
# se puede resolver en la puerta.
CHEQUEO_INTERNO = {
    ("PATCH", "/glosas/{glosa_id}/estado"),
    ("PATCH", "/glosas/{glosa_id}/workflow"),
    ("DELETE", "/glosas/{glosa_id}/comentarios/{comentario_id}"),
    ("POST", "/glosas/bulk/exportar-csv"),
    ("POST", "/glosas/importar-masiva/lote/{lote_id}/cancelar"),
    ("POST", "/glosas/importar-masiva/lote/{lote_id}/retry-fila"),
    ("POST", "/workflow/{glosa_id}/transicionar"),
    ("POST", "/workflow/transicionar-lote"),
    ("POST", "/workflow/reabrir-para-corregir"),
}

# Señales de que el handler comprueba rol o propiedad por dentro.
MARCAS_DE_CHEQUEO = (
    "ROL_VIEWER",
    "ROL_AUDITOR",
    "rol not in",
    "rol ==",
    "rol !=",
    "auditor_email",
    "creado_por",
    "403",
)


def _dependencias(ruta) -> set[str]:
    dep = getattr(ruta, "dependant", None)
    nombres: set[str] = set()
    if dep is None:
        return nombres
    pila = list(dep.dependencies)
    while pila:
        d = pila.pop()
        if d.call is not None:
            nombres.add(getattr(d.call, "__name__", ""))
        pila.extend(d.dependencies)
    return nombres


def _rutas_que_mutan():
    for r in app.routes:
        metodos = (getattr(r, "methods", set()) or set()) & METODOS_QUE_MUTAN
        if not metodos:
            continue
        for m in sorted(metodos):
            yield m, r.path, _dependencias(r), r


class TestLaMatrizEstaCompleta:
    def test_ninguna_ruta_que_muta_queda_sin_decision(self):
        huerfanas = []
        for metodo, path, deps, _ in _rutas_que_mutan():
            if deps & GUARDIAS_DE_ROL:
                continue
            if (metodo, path) in SERVICIO_PROPIO or (metodo, path) in CHEQUEO_INTERNO:
                continue
            if "get_usuario_actual" not in deps:
                continue  # pública: la vigila test_e00_seguridad
            huerfanas.append(f"{metodo} {path}")
        assert not huerfanas, (
            "Estas rutas modifican datos y solo piden estar autenticado, sin "
            "que nadie haya decidido quién puede usarlas:\n  "
            + "\n  ".join(sorted(huerfanas))
            + "\n\nAgregá el Depends del rol que corresponda, o metela en "
            "SERVICIO_PROPIO / CHEQUEO_INTERNO de esta prueba explicando por qué."
        )

    def test_las_listas_no_guardan_rutas_muertas(self):
        """Una lista con rutas que ya no existen deja de ser una decisión y
        pasa a ser un permiso olvidado."""
        vivas = {(m, p) for m, p, _, _ in _rutas_que_mutan()}
        fantasmas = (SERVICIO_PROPIO | CHEQUEO_INTERNO) - vivas
        assert not fantasmas, f"Rutas listadas que ya no existen: {sorted(fantasmas)}"

    def test_el_chequeo_interno_existe_de_verdad(self):
        """El cajón 3 no puede ser la puerta de atrás: si una ruta dice que
        comprueba por dentro, tiene que verse en el código."""
        sin_marca = []
        for metodo, path, _, ruta in _rutas_que_mutan():
            if (metodo, path) not in CHEQUEO_INTERNO:
                continue
            try:
                src = inspect.getsource(ruta.endpoint)
            except (OSError, TypeError):
                continue
            if not any(marca in src for marca in MARCAS_DE_CHEQUEO):
                sin_marca.append(f"{metodo} {path}")
        assert not sin_marca, (
            f"Dicen comprobar el rol por dentro pero no se ve el chequeo: {sin_marca}"
        )

    def test_el_barrido_dejo_la_mayoria_cerrada_en_la_puerta(self):
        """Constancia del estado: si alguien afloja permisos en masa, se ve."""
        total = con_rol = 0
        for _, _, deps, _ in _rutas_que_mutan():
            total += 1
            if deps & GUARDIAS_DE_ROL:
                con_rol += 1
        assert total >= 160
        assert con_rol / total >= 0.85, (
            f"Solo {con_rol} de {total} rutas que mutan exigen rol en la puerta"
        )


# ─── Y que además funcione: el VIEWER se topa con la puerta ───────────────


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

    estado = {
        "usuario": UsuarioRecord(id=1, email="v@hus.gov.co", nombre="V", rol=ROL_VIEWER, activo=1)
    }
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: estado["usuario"]
    with TestClient(app) as c:
        c.estado = estado
        yield c
    app.dependency_overrides.clear()


def _rol(cliente, rol):
    cliente.estado["usuario"] = UsuarioRecord(
        id=1, email="u@hus.gov.co", nombre="U", rol=rol, activo=1
    )


class TestElViewerYaNoTrabaja:
    """El VIEWER mira. Estas eran las puertas por las que igual escribía."""

    def test_no_analiza_una_glosa(self, cliente):
        r = cliente.post("/analizar", json={"eps": "COOSALUD", "texto_glosa": "x" * 40})
        assert r.status_code == 403

    def test_no_comenta_en_el_expediente(self, cliente, db_session):
        db_session.add(GlosaRecord(eps="COOSALUD", factura="F1"))
        db_session.commit()
        gid = db_session.query(GlosaRecord).first().id
        r = cliente.post(f"/glosas/{gid}/comentarios/", json={"texto": "hola"})
        assert r.status_code == 403

    def test_no_importa_glosas_en_masa(self, cliente):
        r = cliente.post("/glosas/importar-recepcion", json={"filas": []})
        assert r.status_code == 403

    def test_no_crea_plantillas_del_equipo(self, cliente):
        r = cliente.post("/plantillas-gold/", json={"codigo_glosa": "TA0601", "texto": "x"})
        assert r.status_code == 403

    def test_no_le_pregunta_a_la_ia(self, cliente):
        """Cada pregunta al asistente cuesta plata de la cuenta del hospital."""
        r = cliente.post("/asistente/chat", json={"mensaje": "hola"})
        assert r.status_code == 403

    def test_no_restaura_una_version_del_dictamen(self, cliente):
        r = cliente.post("/glosas/1/versiones/1/restaurar")
        assert r.status_code == 403

    def test_no_decide_una_glosa_adres(self, cliente):
        r = cliente.post("/glosas-adres/glosa/1", json={"decision": "ACEPTAR"})
        assert r.status_code == 403

    def test_sigue_pudiendo_cambiar_su_propia_clave(self, cliente):
        """No se cerró de más: lo suyo lo sigue manejando."""
        r = cliente.post(
            "/auth/cambiar-password",
            json={"password_actual": "vieja", "password_nueva": "una-nueva-larga"},
        )
        assert r.status_code != 403


class TestElAuditorConservaSuTrabajo:
    def test_el_auditor_si_comenta(self, cliente, db_session):
        db_session.add(GlosaRecord(eps="COOSALUD", factura="F1"))
        db_session.commit()
        gid = db_session.query(GlosaRecord).first().id
        _rol(cliente, ROL_AUDITOR)
        r = cliente.post(f"/glosas/{gid}/comentarios/", json={"texto": "hola"})
        assert r.status_code != 403

    def test_el_auditor_si_analiza(self, cliente):
        _rol(cliente, ROL_AUDITOR)
        r = cliente.post("/analizar", json={"eps": "COOSALUD", "texto_glosa": "x" * 40})
        assert r.status_code != 403


class TestLoQueEsDeCoordinacion:
    def test_el_auditor_no_manda_alertas_a_todo_el_equipo(self, cliente):
        _rol(cliente, ROL_AUDITOR)
        assert cliente.post("/alertas/enviar", json={}).status_code == 403

    def test_el_auditor_no_sube_el_pdf_del_contrato(self, cliente):
        _rol(cliente, ROL_AUDITOR)
        r = cliente.post(
            "/contratos/COOSALUD/pdf", files={"archivo": ("c.pdf", b"%PDF-", "application/pdf")}
        )
        assert r.status_code == 403

    def test_coordinacion_si_manda_alertas(self, cliente):
        _rol(cliente, ROL_COORDINADOR)
        assert cliente.post("/alertas/enviar", json={}).status_code != 403
