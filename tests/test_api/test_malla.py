"""La malla en la pantalla: qué contrato rige y qué ya venció."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import ROL_VIEWER, UsuarioRecord


@pytest.fixture
def cliente():
    from app.api.deps import get_usuario_actual
    from app.main import app

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    estado = {"usuario": UsuarioRecord(id=1, email="ana@hus.com", rol="AUDITOR", activo=1)}
    app.dependency_overrides[get_db] = lambda: iter([s]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: estado["usuario"]
    with TestClient(app) as c:
        c.estado = estado
        yield c
    app.dependency_overrides.clear()
    s.close()
    engine.dispose()


class TestEstadoDeLaMalla:
    def test_devuelve_los_cuatro_grupos(self, cliente):
        d = cliente.get("/malla").json()
        assert {"vencidos", "por_vencer", "vigentes", "indeterminados"} <= set(d)
        assert d["total"] == len(d["vencidos"]) + len(d["por_vencer"]) + len(d["vigentes"]) + len(
            d["indeterminados"]
        )

    def test_dice_de_cuando_es_la_malla(self, cliente):
        """Sin la fecha del documento nadie sabe si está mirando algo viejo."""
        assert cliente.get("/malla").json()["fecha_malla"] == "2026-07-28"

    def test_el_viewer_tambien_la_ve(self, cliente):
        """Saber con qué contrato se factura no es información reservada, y
        esconderla es lo que hace que alguien defienda con un contrato muerto."""
        cliente.estado["usuario"] = UsuarioRecord(id=2, email="v@hus.com", rol=ROL_VIEWER, activo=1)
        assert cliente.get("/malla").status_code == 200


class TestContratoVigenteAUnaFecha:
    def test_famisanar_no_cubre_marzo_de_2026(self, cliente):
        d = cliente.get("/malla/vigente?pagador=FAMISANAR&fecha=2026-03-20").json()
        assert d["hay_contrato"] is False
        assert "2026-03-20" in d["mensaje"]
        # Y dice cuáles sí existen, para que el auditor sepa qué está pasando.
        assert d["otros_contratos"]

    def test_famisanar_si_cubre_mayo_de_2026(self, cliente):
        d = cliente.get("/malla/vigente?pagador=FAMISANAR&fecha=2026-05-20").json()
        assert d["hay_contrato"] is True
        assert d["contrato"]["numero"] == "S13103104958"
        assert d["contrato"]["factor"] == 0.95

    def test_coosalud_devuelve_el_contributivo_despues_de_abril(self, cliente):
        d = cliente.get("/malla/vigente?pagador=COOSALUD&fecha=2026-06-15").json()
        assert d["contrato"]["numero"] == "68001C00060340-24"

    def test_avisa_cuando_el_contrato_ya_vencio(self, cliente):
        d = cliente.get("/malla/vigente?pagador=NUEVA EPS&fecha=2026-01-15").json()
        assert d["hay_contrato"] is True
        d_hoy = cliente.get("/malla/vigente?pagador=NUEVA EPS&fecha=2026-07-29").json()
        assert d_hoy["hay_contrato"] is False

    def test_fecha_mal_escrita(self, cliente):
        r = cliente.get("/malla/vigente?pagador=COOSALUD&fecha=20-06-2026")
        assert r.status_code == 400
        assert "AAAA-MM-DD" in r.json()["detail"]

    def test_pagador_desconocido_lo_dice(self, cliente):
        d = cliente.get("/malla/vigente?pagador=EPS INVENTADA").json()
        assert d["hay_contrato"] is False
        assert "no aparece en la malla" in d["mensaje"]


class TestLaPantallaExiste:
    def _html(self):
        from pathlib import Path

        return (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )

    def test_hay_entrada_y_panel(self):
        html = self._html()
        assert 'id="sn-malla"' in html
        assert 'id="p-malla"' in html

    def test_el_panel_se_carga_al_abrirlo(self):
        assert "if(id==='malla') mallaCargar();" in self._html()

    def test_el_menu_avisa_cuantos_urgen(self):
        """El globo del menú suma vencidos y por vencer: el auditor lo ve sin
        entrar a la pantalla."""
        assert "malla-badge-side" in self._html()
