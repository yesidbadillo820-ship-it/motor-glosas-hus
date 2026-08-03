"""Todos los bots del hospital administrados desde la plataforma.

El ciclo de vida completo de un trabajo: encolar → reclamar (agente del
PC) → progreso → finalizar; cancelar y reintentar desde la pantalla; el
tablero con estado vivo, estadísticas y último error; y el agente que no
conoce ningún bot por nombre — el comando viaja desde el catálogo.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models.db import AuditLogRecord, UsuarioRecord
from app.services import bots_hus

TOKEN = "token-de-prueba-bots"


@pytest.fixture
def db_session():
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


@pytest.fixture
def cliente(db_session, monkeypatch):
    from app.api.deps import get_usuario_actual
    from app.core.config import get_settings
    from app.main import app

    monkeypatch.setattr(get_settings(), "agente_lotes_token", TOKEN, raising=False)
    u = UsuarioRecord(id=1, email="auditor@hus.gov.co", nombre="A", rol="AUDITOR", activo=1)
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: u
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _agente(cliente, ruta, cuerpo):
    return cliente.post(ruta, json=cuerpo, headers={"X-Agente-Token": TOKEN})


class TestCatalogo:
    def test_todos_los_bots_del_hospital_estan(self):
        ids = {b.id for b in bots_hus.CATALOGO_BOTS}
        # Los que el área nombró con nombre propio, todos presentes:
        for esperado in (
            "coosalud-responder",
            "simed-responder",
            "fomag-responder",
            "mutual-responder",
            "dgh-responder",
            "adres-furips",
            "nueva-eps-de4401",
            "savia-erp",
            "vco-erp",
            "emssanar-erp",
            "xml-facturas",
            "excel-csv",
            "unir-pdfs",
            "radicador",
        ):
            assert esperado in ids, f"falta {esperado} en el catálogo"
        assert len(ids) >= 30

    def test_cada_bot_de_cola_tiene_comando_y_archivo_real(self):
        for b in bots_hus.CATALOGO_BOTS:
            if b.disparo == "cola":
                assert b.comando_pc, f"{b.id} sin comando para el agente"
                assert Path(b.archivo).exists(), f"{b.id}: no existe {b.archivo}"


class TestCicloCompleto:
    def test_encolar_reclamar_progreso_finalizar(self, cliente, db_session):
        r = cliente.post("/bots/fomag-responder/ejecutar", json={"parametros": {"piloto": "1"}})
        assert r.status_code == 200, r.text
        tid = r.json()["trabajo_id"]

        # El tablero lo muestra EN COLA
        tablero = cliente.get("/bots").json()
        fomag = next(
            b for g in tablero["grupos"] for b in g["bots"] if b["id"] == "fomag-responder"
        )
        assert fomag["estado"] == "EN COLA" and fomag["pendientes"] == 1

        # El agente reclama: recibe el comando del catálogo, no un if/else
        rec = _agente(cliente, "/bots/trabajos/reclamar", {"equipo": "PC-CARTERA-03"})
        assert rec.status_code == 200
        assert rec.json()["trabajo_id"] == tid
        assert rec.json()["comando"] == "py tools/responder_glosas_fomag.py"
        assert rec.json()["parametros"] == {"piloto": "1"}

        # Progreso visible en vivo
        assert (
            _agente(
                cliente, f"/bots/trabajos/{tid}/progreso", {"mensaje": "factura 3 de 12"}
            ).status_code
            == 200
        )
        assert cliente.get(f"/bots/trabajos/{tid}").json()["progreso"] == "factura 3 de 12"

        tablero = cliente.get("/bots").json()
        fomag = next(
            b for g in tablero["grupos"] for b in g["bots"] if b["id"] == "fomag-responder"
        )
        assert fomag["estado"] == "CORRIENDO"
        assert fomag["trabajo_corriendo"]["equipo"] == "PC-CARTERA-03"

        # Finaliza bien y todo queda: estado, registro, auditoría, historial
        fin = _agente(
            cliente,
            f"/bots/trabajos/{tid}/finalizar",
            {"exito": True, "registro": "12 facturas cargadas"},
        )
        assert fin.status_code == 200 and fin.json()["estado"] == "TERMINADO"

        detalle = cliente.get("/bots/fomag-responder").json()
        assert detalle["estado"] == "DISPONIBLE"
        assert detalle["ultima_ejecucion"]["registro"].startswith("12 facturas")
        assert detalle["ejecutadas_hoy"] == 1
        assert detalle["historial"][0]["id"] == tid
        assert (
            db_session.query(AuditLogRecord)
            .filter(AuditLogRecord.accion == "BOT_TERMINADO")
            .count()
            == 1
        )

    def test_error_cancelar_y_reintentar(self, cliente, db_session):
        tid = cliente.post("/bots/dgh-responder/ejecutar", json={}).json()["trabajo_id"]
        _agente(cliente, "/bots/trabajos/reclamar", {"equipo": "PC-01"})
        _agente(
            cliente,
            f"/bots/trabajos/{tid}/finalizar",
            {"exito": False, "error": "El portal cerró la sesión"},
        )
        d = cliente.get("/bots/dgh-responder").json()
        assert d["estado"] == "ERROR"
        assert "portal" in d["ultimo_error"]["error"]

        # Reintentar re-encola con los mismos parámetros
        r2 = cliente.post("/bots/dgh-responder/reintentar")
        assert r2.status_code == 200 and r2.json()["reintenta_a"] == tid

        # Cancelar limpia lo abierto
        rc = cliente.post("/bots/dgh-responder/cancelar")
        assert rc.status_code == 200 and rc.json()["cancelados"] == 1
        assert cliente.get("/bots/dgh-responder").json()["pendientes"] == 0
        assert (
            db_session.query(AuditLogRecord)
            .filter(AuditLogRecord.accion.in_(("BOT_CANCELADO", "BOT_REINTENTADO")))
            .count()
            == 2
        )

    def test_cola_global_y_sin_trabajo_204(self, cliente):
        cliente.post("/bots/radicador/ejecutar", json={})
        cola = cliente.get("/bots/trabajos").json()
        assert len(cola["abiertos"]) == 1
        _agente(cliente, "/bots/trabajos/reclamar", {"equipo": "PC-9"})
        tid = cola["abiertos"][0]["id"]
        _agente(cliente, f"/bots/trabajos/{tid}/finalizar", {"exito": True})
        assert _agente(cliente, "/bots/trabajos/reclamar", {"equipo": "PC-9"}).status_code == 204


class TestLosQueNoVanPorCola:
    def test_nube_remite_a_su_conversor(self, cliente):
        d = cliente.post("/bots/savia-erp/ejecutar", json={}).json()
        assert d["encolado"] is False and d["automatizacion_id"] == "objeciones-savia"

    def test_lotes_remite_a_lotes(self, cliente):
        d = cliente.post("/bots/coosalud-responder/ejecutar", json={}).json()
        assert d["encolado"] is False and d["motivo"] == "lotes"


class TestSeguridad:
    def test_agente_sin_token_no_entra(self, cliente):
        r = cliente.post("/bots/trabajos/reclamar", json={"equipo": "PC-X"})
        assert r.status_code == 401

    def test_viewer_no_ejecuta(self, db_session, monkeypatch):
        from app.api.deps import get_usuario_actual
        from app.main import app

        u = UsuarioRecord(id=2, email="v@hus.gov.co", nombre="V", rol="VIEWER", activo=1)
        app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: u
        with TestClient(app) as c:
            assert c.post("/bots/fomag-responder/ejecutar", json={}).status_code == 403
            assert c.get("/bots").status_code == 200  # ver sí puede
        app.dependency_overrides.clear()


class TestAgenteDelPC:
    def test_corre_cualquier_comando_sin_conocer_pagadores(self, tmp_path):
        import sys

        sys.path.insert(0, "tools")
        try:
            import agente_bots_hus as ag
        finally:
            sys.path.remove("tools")
        exito, registro, error = ag._correr_bot(
            f'{sys.executable} -c "print(chr(111)+chr(107))"', {"factura": "HUS001"}
        )
        assert exito is True and "ok" in registro and error == ""

        exito2, _, error2 = ag._correr_bot(f'{sys.executable} -c "raise SystemExit(3)"', {})
        assert exito2 is False and "código 3" in error2


class TestPantalla:
    def test_el_tablero_esta_en_la_pantalla(self):
        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert 'id="bots-tablero"' in html
        assert "Bots del hospital" in html
        for fn in (
            "botsCargar",
            "botEjecutar",
            "botCancelar",
            "botReintentar",
            "botHistorial",
            "botRegistros",
            "botConfigurar",
        ):
            assert fn in html, f"falta {fn} en la pantalla"


class TestLotesEnLaTarjeta:
    """Los bots de COOSALUD/SIMED muestran SU cola real de Lotes."""

    def _lote(self, db, pagador, estado, tarea_estado=None, agente=None, error=None):
        from app.models.db import LoteRecord, TareaLoteRecord

        lote = LoteRecord(
            creado_por="ana@hus.gov.co",
            pagador=pagador,
            nombre_archivo=f"LOTE_{pagador}.xlsx",
            estado=estado,
            total_facturas=45,
            total_glosas=120,
            excel_archivo=b"xlsx",
        )
        db.add(lote)
        db.commit()
        if tarea_estado:
            db.add(
                TareaLoteRecord(lote_id=lote.id, estado=tarea_estado, agente=agente, error=error)
            )
            db.commit()
        return lote

    def test_lote_en_proceso_pone_la_tarjeta_corriendo(self, cliente, db_session):
        self._lote(
            db_session, "COOSALUD", "EN_PROCESO", tarea_estado="RECLAMADA", agente="PC-CARTERA-02"
        )
        d = cliente.get("/bots").json()
        coo = next(b for g in d["grupos"] for b in g["bots"] if b["id"] == "coosalud-responder")
        assert coo["estado"] == "CORRIENDO"
        assert coo["lotes"][0]["archivo"] == "LOTE_COOSALUD.xlsx"
        assert coo["lotes"][0]["total_facturas"] == 45
        assert coo["lotes"][0]["equipo"] == "PC-CARTERA-02"
        assert coo["lotes"][0]["creado_por"] == "ana@hus.gov.co"

    def test_lote_con_error_pone_la_tarjeta_en_error(self, cliente, db_session):
        self._lote(
            db_session,
            "SIMED",
            "ERROR",
            tarea_estado="ERROR",
            agente="PC-01",
            error="SIMED rechazó el usuario",
        )
        d = cliente.get("/bots/simed-responder").json()
        assert d["estado"] == "ERROR"
        assert "SIMED rechazó" in d["lotes"][0]["tarea_error"]

    def test_sin_lotes_la_tarjeta_queda_disponible(self, cliente):
        d = cliente.get("/bots/simed-responder").json()
        assert d["estado"] == "DISPONIBLE" and d["lotes"] == []


class TestHallazgosDeLaRevision:
    """Los cuatro defectos que encontró la revisión adversarial, sellados."""

    def test_completado_con_pendientes_no_es_tarjeta_verde(self, cliente, db_session):
        from app.models.db import LoteRecord, TareaLoteRecord

        lote = LoteRecord(
            creado_por="ana@hus.gov.co",
            pagador="COOSALUD",
            nombre_archivo="LOTE.xlsx",
            estado="COMPLETADO_CON_PENDIENTES",
            total_facturas=45,
            excel_archivo=b"x",
        )
        db_session.add(lote)
        db_session.commit()
        db_session.add(TareaLoteRecord(lote_id=lote.id, estado="COMPLETADA", agente="PC-1"))
        db_session.commit()

        d = cliente.get("/bots/coosalud-responder").json()
        assert d["estado"] == "CON PENDIENTES"  # ámbar, no DISPONIBLE verde

    def test_lote_en_cola_no_infla_pendientes_de_la_cola_universal(self, cliente, db_session):
        from app.models.db import LoteRecord

        db_session.add(
            LoteRecord(
                creado_por="a@hus.gov.co",
                pagador="COOSALUD",
                nombre_archivo="L.xlsx",
                estado="EN_COLA",
                excel_archivo=b"x",
            )
        )
        db_session.commit()
        d = cliente.get("/bots/coosalud-responder").json()
        assert d["estado"] == "EN COLA"
        assert d["pendientes"] == 0  # sin botón Cancelar fantasma

    def test_los_botones_de_cola_no_aplican_a_bots_de_lotes(self):
        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert html.count("b.disparo !== 'lotes' && (b.pendientes || corr)") == 1
        assert html.count("b.disparo !== 'lotes' && (b.estado === 'ERROR'") == 1

    def test_la_consulta_de_lotes_no_arrastra_el_excel_binario(self):
        """Ronda 31: el defer del BLOB debe estar también acá."""
        import inspect

        from app.api.routers import bots

        fuente = inspect.getsource(bots._enriquecer_con_lotes)
        assert "defer(LoteRecord.excel_archivo)" in fuente
