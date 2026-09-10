"""Tests de GET /contratos/eps-seleccionables (09-09-2026).

El desplegable «EPS / Entidad Pagadora» del botón Analizar se llenaba
SOLO con `GET /contratos/`, o sea con las entidades que tienen
`ContratoRecord`. SURA, SALUD TOTAL, EMSSANAR, SAVIA y MUTUAL SER son
entidades reales —con bot de portal propio y lógica propia en el resto
del motor— que nunca tuvieron un PDF de contrato cargado, así que JAMÁS
aparecían: el auditor solo podía elegir «OTRA / SIN DEFINIR» y todos esos
dictámenes salían genéricos.

Esta ruta une tres fuentes: el catálogo fijo de entidades reales, las que
sí tienen contrato, y las que ya aparecen en el historial sin tenerlo.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.tz import ahora_utc
from app.database import Base, get_db
from app.models.db import ContratoRecord, GlosaRecord, UsuarioRecord


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
def usuario():
    return UsuarioRecord(id=1, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _seed_contrato(db, eps):
    db.add(ContratoRecord(eps=eps, detalles="X" * 12))
    db.commit()


def _seed_glosa(db, eps, valor=1000):
    db.add(
        GlosaRecord(
            eps=eps,
            paciente="X",
            codigo_glosa="C",
            valor_objetado=valor,
            etapa="X",
            estado="RADICADA",
            creado_en=ahora_utc(),
        )
    )
    db.commit()


class TestLasEntidadesRealesSalenAunqueNoTenganContrato:
    """El caso que motivó la ruta: base completamente vacía."""

    @pytest.mark.parametrize("eps", ["SURA", "SALUD TOTAL", "MUTUAL SER", "EMSSANAR", "SAVIA"])
    def test_aparece_sin_ningun_dato_en_la_base(self, client, eps):
        r = client.get("/contratos/eps-seleccionables")
        assert r.status_code == 200
        assert eps in r.json(), f"{eps} tiene bot y lógica propia; no puede depender de un contrato"

    def test_no_es_una_lista_vacia_ni_de_un_solo_elemento(self, client):
        assert len(client.get("/contratos/eps-seleccionables").json()) >= 15


class TestSeUnenLasTresFuentes:
    def test_una_eps_con_contrato_pero_fuera_del_catalogo_aparece(self, client, db_session):
        _seed_contrato(db_session, "COMFAMA")  # inventada, solo para la prueba
        eps = client.get("/contratos/eps-seleccionables").json()
        assert "COMFAMA" in eps

    def test_una_eps_del_historial_sin_contrato_y_fuera_del_catalogo_aparece(
        self, client, db_session
    ):
        _seed_glosa(db_session, "COMFAMA")
        eps = client.get("/contratos/eps-seleccionables").json()
        assert "COMFAMA" in eps

    def test_el_marcador_generico_no_es_una_entidad(self, client, db_session):
        """«OTRA / SIN DEFINIR» es el marcador del desplegable, no un pagador."""
        _seed_glosa(db_session, "OTRA / SIN DEFINIR")
        _seed_glosa(db_session, "OTRA")
        eps = client.get("/contratos/eps-seleccionables").json()
        assert "OTRA / SIN DEFINIR" not in eps
        assert "OTRA" not in eps

    def test_sin_repetidos_entre_las_tres_fuentes(self, client, db_session):
        """SURA con contrato Y en el historial: una sola vez en la lista."""
        _seed_contrato(db_session, "SURA")
        _seed_glosa(db_session, "SURA")
        eps = client.get("/contratos/eps-seleccionables").json()
        assert eps.count("SURA") == 1

    def test_viene_ordenada_alfabeticamente(self, client):
        eps = client.get("/contratos/eps-seleccionables").json()
        assert eps == sorted(eps)

    def test_todo_en_mayuscula(self, client, db_session):
        _seed_glosa(db_session, "comfama en minuscula")
        eps = client.get("/contratos/eps-seleccionables").json()
        assert "COMFAMA EN MINUSCULA" in eps
        assert "comfama en minuscula" not in eps


class TestExigeSesion:
    def test_sin_token_no_entra(self):
        from app.main import app

        with TestClient(app) as c:
            assert c.get("/contratos/eps-seleccionables").status_code == 401


class TestNoSaleLaMismaEntidadDosVeces:
    """10-09-2026 — el desplegable real de Yesid traía ocho renglones de más.

    Los nombres repetidos no son un error de la lista fija: son registros
    REALES escritos distinto (unos vienen de un contrato cargado, otros del
    historial) y la unión solo descartaba el texto idéntico.
    """

    def test_salud_total_y_salud_total_eps_son_un_solo_renglon(self, client, db_session):
        """Sobrevive el nombre con glosas detrás, no el del catálogo fijo."""
        _seed_glosa(db_session, "SALUD TOTAL EPS")
        eps = client.get("/contratos/eps-seleccionables").json()
        assert len([e for e in eps if e.startswith("SALUD TOTAL")]) == 1
        assert "SALUD TOTAL EPS" in eps

    def test_sura_y_sura_eps_son_un_solo_renglon(self, client, db_session):
        _seed_glosa(db_session, "SURA EPS")
        eps = client.get("/contratos/eps-seleccionables").json()
        assert len([e for e in eps if e.startswith("SURA")]) == 1

    def test_el_guion_de_adres_no_crea_una_segunda_entidad(self, client, db_session):
        _seed_glosa(db_session, "ADRES ACCIDENTES DE TRANSITO")
        _seed_glosa(db_session, "ADRES-ACCIDENTES DE TRANSITO", valor=2000)
        eps = client.get("/contratos/eps-seleccionables").json()
        assert len([e for e in eps if e.startswith("ADRES")]) == 1

    def test_el_dispensario_sale_con_el_nombre_del_contrato_firmado(self, client, db_session):
        """El dictamen debe citar el nombre con el que está firmado."""
        oficial = "DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA"
        _seed_contrato(db_session, oficial)
        eps = client.get("/contratos/eps-seleccionables").json()
        assert oficial in eps
        assert "DISPENSARIO MEDICO" not in eps
        assert len([e for e in eps if "DISPENSARIO" in e]) == 1

    def test_uvt_y_uvb_son_un_solo_renglon(self, client, db_session):
        """10-09-2026: esta prueba decía lo contrario y estaba equivocada.

        El motor liquida SOLO en UVB (`uvb.py`). No existe ni una tarifa en
        UVT en todo el código, y las bases de la malla son SOAT, SOAT_UVB,
        SOAT_SMLV, PROPIA, PACTADA y MIXTA — no hay SOAT_UVT. El sufijo no
        cambia nada; son el mismo pagador.
        """
        _seed_glosa(db_session, "LA PREVISORA S A COMPANIA DE SEGUROS SOAT - UVT")
        _seed_glosa(db_session, "LA PREVISORA S A COMPANIA DE SEGUROS SOAT UVB", valor=2000)
        eps = client.get("/contratos/eps-seleccionables").json()
        assert len([e for e in eps if e.startswith("LA PREVISORA")]) == 1

    def test_contributivo_y_subsidiado_son_un_solo_renglon(self, client, db_session):
        """PROTEGER no está en la malla contractual: su nombre no elige contrato.

        Donde el régimen SÍ decide —COOSALUD, que tiene dos contratos con
        números distintos— eso lo resuelven los alias de la malla leyendo el
        texto de la glosa, no un renglón del desplegable.
        """
        _seed_glosa(db_session, "PROTEGER EPS S.A.S. CONTRIBUTIVO")
        _seed_glosa(db_session, "PROTEGER EPS S.A.S. SUBSIDIADO", valor=2000)
        eps = client.get("/contratos/eps-seleccionables").json()
        assert len([e for e in eps if e.startswith("PROTEGER")]) == 1

    def test_el_marcador_no_se_cuela_por_un_contrato(self, client, db_session):
        """En la captura de Yesid salía DOS veces: el filtro no cubría los contratos."""
        _seed_contrato(db_session, "OTRA / SIN DEFINIR")
        eps = client.get("/contratos/eps-seleccionables").json()
        assert "OTRA / SIN DEFINIR" not in eps
        assert "OTRA" not in eps

    def test_una_entidad_nueva_de_verdad_sigue_entrando(self, client, db_session):
        """La regla une duplicados; no puede tapar una entidad nueva."""
        _seed_glosa(db_session, "COMFAMA")
        assert "COMFAMA" in client.get("/contratos/eps-seleccionables").json()
