"""Interfaz Health-Tech (03-09-2026): pantalla dividida, Kanban de
borradores, semáforo de vencimientos y modo oscuro por defecto.

Dos frentes:
  1. Los ENDPOINTS que la pantalla nueva consume (bandeja enriquecida con
     confianza/modelo/días, devolución a revisión manual, visor de
     soportes servido SOLO desde el índice — jamás rutas del cliente).
  2. El CONTRATO de los archivos estáticos: que el JavaScript y el CSS
     tengan las piezas de las que depende la pantalla (la lección «Salud
     Total»: un backend vivo con un frontend que llama a lo borrado).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.database import Base, get_db
from app.main import app
from app.models.db import AutoPilotBitacoraRecord, GlosaRecord

RAIZ = Path(__file__).resolve().parents[2]


@pytest.fixture
def db_session():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


@pytest.fixture
def cliente(db_session):
    coordinador = SimpleNamespace(
        email="coordinador@hus.gov.co", rol="COORDINADOR", nombre="Coord", activo=1
    )
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[deps.get_usuario_actual] = lambda: coordinador
    app.dependency_overrides[deps.get_auditor_o_superior] = lambda: coordinador
    app.dependency_overrides[deps.get_coordinador_o_admin] = lambda: coordinador
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(deps.get_usuario_actual, None)
        app.dependency_overrides.pop(deps.get_auditor_o_superior, None)
        app.dependency_overrides.pop(deps.get_coordinador_o_admin, None)


def _glosa_en_cuarentena(db, **kw):
    base = dict(
        eps="COOSALUD",
        factura="HUS777001",
        codigo_glosa="SO0101",
        valor_objetado=180000.0,
        estado="PENDIENTE",
        workflow_state="PENDIENTE_APROBACION_HUMANA",
        dictamen="<div>ESE HUS NO ACEPTA LA GLOSA…</div>",
        modelo_ia="texto_fijo_extemporanea",
    )
    base.update(kw)
    g = GlosaRecord(**base)
    db.add(g)
    db.commit()
    return g


class TestBandejaEnriquecida:
    def test_borradores_traen_confianza_modelo_y_dias(self, cliente, db_session):
        g = _glosa_en_cuarentena(db_session)
        db_session.add(
            AutoPilotBitacoraRecord(
                glosa_id=g.id,
                decision="CANDIDATA",
                regla_aplicada="Confianza 95% · valor bajo · riesgo BAJO",
                confianza=0.95,
                riesgo="BAJO",
                soportes_analizados="[]",
                actor="auto-pilot",
                modelo_utilizado="texto_fijo_extemporanea",
            )
        )
        db_session.commit()

        r = cliente.get("/autopilot/borradores")
        assert r.status_code == 200
        fila = next(b for b in r.json()["borradores"] if b["glosa_id"] == g.id)
        assert fila["confianza"] == 0.95
        assert fila["riesgo"] == "BAJO"
        assert fila["modelo_utilizado"] == "texto_fijo_extemporanea"
        assert "Confianza 95%" in fila["regla_aplicada"]
        assert "dias_restantes" in fila  # None sin fecha base: el JS pinta «sin fecha»

    def test_sin_bitacora_no_se_inventa_confianza(self, cliente, db_session):
        g = _glosa_en_cuarentena(db_session, factura="HUS777002")
        r = cliente.get("/autopilot/borradores")
        fila = next(b for b in r.json()["borradores"] if b["glosa_id"] == g.id)
        assert fila["confianza"] is None
        assert fila["modelo_utilizado"] == "texto_fijo_extemporanea"  # cae al modelo_ia real


class TestDevolverBorrador:
    def test_devolver_saca_de_cuarentena_y_queda_en_bitacora(self, cliente, db_session):
        g = _glosa_en_cuarentena(db_session)
        r = cliente.post(f"/autopilot/devolver/{g.id}?motivo=Requiere revisar la epicrisis")
        assert r.status_code == 200
        assert r.json()["estado"] == "devuelta"
        db_session.refresh(g)
        assert g.workflow_state == "RADICADA"
        assert "Requiere revisar la epicrisis" in (g.nota_workflow or "")
        fila = (
            db_session.query(AutoPilotBitacoraRecord)
            .filter(AutoPilotBitacoraRecord.decision == "DEVUELTA_POR_HUMANO")
            .one()
        )
        assert fila.glosa_id == g.id
        assert fila.actor == "coordinador@hus.gov.co"
        assert fila.modelo_utilizado == "texto_fijo_extemporanea"

    def test_no_se_devuelve_lo_que_no_esta_en_borradores(self, cliente, db_session):
        g = _glosa_en_cuarentena(db_session, workflow_state="RESPONDIDA")
        r = cliente.post(f"/autopilot/devolver/{g.id}")
        assert r.status_code == 409

    def test_devolver_inexistente_es_404(self, cliente):
        assert cliente.post("/autopilot/devolver/999999").status_code == 404


class TestVisorDeSoportes:
    """/soportes-auto/archivo — la ruta del disco JAMÁS viene del cliente."""

    def _stub_indexador(self, monkeypatch, tmp_path):
        pdf = tmp_path / "historia_clinica.pdf"
        pdf.write_bytes(b"%PDF-1.4 contenido de prueba")
        import app.api.routers.soportes as mod

        class _Idx:
            def lookup(self, factura, auto_rebuild=True):
                if "495050" in str(factura):
                    return [
                        {
                            "tipo_codigo": "HEV",
                            "nombre_archivo": "historia_clinica.pdf",
                            "ruta": str(pdf),
                        }
                    ]
                return []

            def stats(self):
                return {"construyendo": False}

        monkeypatch.setattr(mod, "get_indexer", lambda: _Idx())
        return pdf

    def test_sirve_un_archivo_que_el_indice_conoce(self, cliente, monkeypatch, tmp_path):
        self._stub_indexador(monkeypatch, tmp_path)
        r = cliente.get(
            "/soportes-auto/archivo",
            params={"factura": "HUS495050", "nombre": "historia_clinica.pdf"},
        )
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("application/pdf")
        assert r.content.startswith(b"%PDF")

    def test_nombre_no_indexado_es_404(self, cliente, monkeypatch, tmp_path):
        self._stub_indexador(monkeypatch, tmp_path)
        r = cliente.get(
            "/soportes-auto/archivo", params={"factura": "HUS495050", "nombre": "otro.pdf"}
        )
        assert r.status_code == 404

    def test_rutas_y_saltos_de_carpeta_se_rechazan(self, cliente, monkeypatch, tmp_path):
        self._stub_indexador(monkeypatch, tmp_path)
        for malicioso in ("../../etc/passwd", "..\\secreto.txt", "carpeta/archivo.pdf"):
            r = cliente.get(
                "/soportes-auto/archivo", params={"factura": "HUS495050", "nombre": malicioso}
            )
            assert r.status_code == 400, malicioso


class TestContratoDeLaPantalla:
    """El HTML/JS/CSS deben tener las piezas de las que depende la UI."""

    @pytest.fixture(scope="class")
    def html(self):
        return (RAIZ / "static" / "index.html").read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def js(self):
        return (RAIZ / "static" / "healthtech.js").read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def css(self):
        return (RAIZ / "static" / "healthtech.css").read_text(encoding="utf-8")

    def test_index_carga_el_modulo_health_tech(self, html):
        assert "/static/healthtech.css" in html
        assert "/static/healthtech.js" in html

    def test_modo_oscuro_es_el_predeterminado_respetando_la_eleccion(self, html):
        assert "localStorage.getItem('dark')!=='0'" in html
        assert "localStorage.getItem('dark')==='1'" not in html

    def test_los_listados_usan_la_barra_de_vencimiento(self, html):
        assert html.count("HT.barraVencimiento") >= 2  # alertas + tablero

    def test_split_view_con_paneles_independientes(self, js):
        assert "abrirSplitView" in js
        assert "Promise.allSettled" in js  # el panel no muere si la bitácora falla
        assert "ht-panel-scroll" in js and "ht-visor-lienzo" in js  # esqueletos propios
        assert "_cargarPanel(glosaId)" in js  # el panel arranca sin esperar al visor

    def test_el_ancho_de_la_barra_siempre_queda_entre_0_y_100(self, js):
        assert "Math.max(0, Math.min(100, pct))" in js

    def test_el_relleno_de_la_barra_es_block(self, css):
        # Cazado por el arnés de estrés (03-09-2026): el relleno es un <span>
        # y sin display:block el ancho se ignora — la barra pintaba vacía.
        import re

        fill = re.search(r"\.ht-venc-fill\s*\{[^}]+\}", css)
        assert fill and "display: block" in fill.group(0)

    def test_cero_saltos_de_ventana(self, js, html):
        assert "window.verGlosa = function" in js
        assert "window.verBorradoresAutoPilot = function" in js
        assert "window.open" not in js

    def test_kanban_con_badges_de_confianza_y_modelo(self, js, css):
        assert "ht-badge-confianza" in js and "ht-badge-modelo" in js
        assert "text-overflow: ellipsis" in css
        assert "tabular-nums" in css

    def test_acentos_solo_esmeralda_y_carmesi(self, css, js):
        assert ".ht-btn-esmeralda" in css and ".ht-btn-carmesi" in css
        assert "ht-btn-esmeralda" in js  # liberar
        assert "ht-btn-carmesi" in js  # devolver

    def test_visor_con_zoom_integrado(self, js):
        assert "HT.zoom" in js and "ht-zoomwrap" in js
