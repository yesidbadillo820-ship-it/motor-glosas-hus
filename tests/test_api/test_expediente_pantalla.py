"""El Expediente como pantalla y fuente única: todo lo de una glosa, junto.

La épica es que un auditor (o la IA) abra UN solo lugar y encuentre: la
ficha, el contrato que rige con su veredicto, la línea de tiempo completa,
las conciliaciones y los soportes. Estas pruebas recorren el círculo
entero: analizar una glosa → el expediente la consolida → la búsqueda la
encuentra → la IA la consulta → la pantalla existe y el popup viejo no.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models.db import UsuarioRecord
from app.models.schemas import GlosaResult


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
def usuario_fake():
    return UsuarioRecord(
        id=1, email="auditor@hus.gov.co", nombre="Auditor Test", rol="AUDITOR", activo=1
    )


@pytest.fixture
def service_mock():
    svc = MagicMock()
    svc.analizar = AsyncMock(
        return_value=GlosaResult(
            tipo="RESPUESTA RE9901",
            resumen="Defensa técnica generada",
            dictamen="<div>Dictamen mock</div>",
            codigo_glosa="TA0201",
            valor_objetado="$ 168,563",
            paciente="N/A",
            mensaje_tiempo="EN TÉRMINOS",
            color_tiempo="green",
            score=85.0,
            dias_restantes=10,
            modelo_ia="mock/test",
        )
    )
    return svc


@pytest.fixture
def client(db_session, usuario_fake, service_mock):
    from app.api.deps import get_usuario_actual
    from app.api.routers.analizar import get_glosa_service
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_fake
    app.dependency_overrides[get_glosa_service] = lambda: service_mock

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def _analizar(client, factura: str = "HUS0000446262") -> int:
    resp = client.post(
        "/analizar",
        data={
            "eps": "COMPENSAR",
            "etapa": "RESPUESTA",
            "fecha_radicacion": "2025-09-15",
            "valor_aceptado": "0",
            "numero_factura": factura,
            "tabla_excel": "TA0201 — Diferencia tarifa CUPS 890750 valor objetado $168.563.",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["glosa_id"]


class TestExpedienteConsolidado:
    def test_todo_en_una_sola_llamada(self, client):
        """Analizada la glosa, el expediente trae ficha + constancia
        contractual + línea de tiempo, sin abrir nada más."""
        glosa_id = _analizar(client)

        r = client.get(f"/glosas/{glosa_id}/expediente")
        assert r.status_code == 200, r.text
        d = r.json()

        assert d["ficha"]["eps"] == "COMPENSAR"
        assert d["ficha"]["factura"] == "HUS0000446262"
        assert d["ficha"]["estado"]
        assert d["ficha"]["tiene_dictamen"] is True

        # La constancia de la verificación contractual quedó y se consolida
        assert d["constancia_contractual"]["veredicto"] == "VIGENTE"
        assert d["constancia_contractual"]["contrato"]["numero"] == "CSS009-2024"

        # La línea de tiempo trae el análisis y la verificación
        tipos = {e["tipo"] for e in d["timeline"]}
        assert "AUDIT_VERIFICACION_CONTRACTUAL" in tipos
        assert d["total_eventos"] >= 1
        assert d["versiones_dictamen"] >= 0
        assert isinstance(d["conciliaciones"], list)
        assert isinstance(d["soportes"], list)

    def test_glosa_inexistente_da_404(self, client):
        assert client.get("/glosas/999999/expediente").status_code == 404


class TestBusqueda:
    def test_encuentra_por_factura_y_por_id(self, client):
        glosa_id = _analizar(client, factura="HUS0000512345")

        r = client.get("/glosas/expediente/buscar", params={"q": "HUS0000512345"})
        assert r.status_code == 200
        ids = [x["glosa_id"] for x in r.json()["resultados"]]
        assert glosa_id in ids

        r2 = client.get("/glosas/expediente/buscar", params={"q": str(glosa_id)})
        assert [x["glosa_id"] for x in r2.json()["resultados"]] == [glosa_id]

    def test_sin_resultados_no_revienta(self, client):
        r = client.get("/glosas/expediente/buscar", params={"q": "NOEXISTE999"})
        assert r.status_code == 200
        assert r.json()["resultados"] == []


class TestIAConsultaExpediente:
    async def test_la_tool_devuelve_el_expediente(self, client, db_session, usuario_fake):
        """La IA usa la MISMA consolidación que la pantalla: le pasan una
        factura y responde con ficha, veredicto contractual y eventos."""
        from app.services import asistente_maestro as am

        _analizar(client, factura="HUS0000777777")

        crudo = await am.execute_tool_asistente(
            "consultar_expediente",
            {"factura": "HUS0000777777"},
            db=db_session,
            current_user=usuario_fake,
        )
        d = json.loads(crudo)
        assert d["ficha"]["factura"] == "HUS0000777777"
        assert d["constancia_contractual"]["veredicto"] == "VIGENTE"
        assert len(d["timeline"]) <= 15  # al chat va lo último, no la novela

    async def test_sin_datos_pide_el_id(self, db_session, usuario_fake):
        from app.services import asistente_maestro as am

        d = json.loads(
            await am.execute_tool_asistente(
                "consultar_expediente", {}, db=db_session, current_user=usuario_fake
            )
        )
        assert "error" in d

    def test_la_tool_esta_declarada(self):
        from app.services import asistente_maestro as am

        nombres = [t["name"] for t in am.TOOLS_ASISTENTE]
        assert "consultar_expediente" in nombres


class TestPantalla:
    def test_la_pantalla_existe_y_el_popup_se_fue(self):
        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        # La pantalla nueva, con búsqueda y filtros
        assert 'id="p-expediente"' in html
        assert 'id="sn-expediente"' in html
        assert "function expBuscar" in html
        assert "function expAbrir" in html
        assert "expFiltrar" in html
        # El botón Timeline ahora entra acá (no a un popup con document.write)
        assert "function verTimelineGlosa" in html
        assert "width=860,height=720" not in html, "el popup viejo sigue vivo"
        # Y el área scrollea (la .panel es overflow:hidden por diseño)
        import re

        area = re.search(r"\.exp-area\{[^}]*\}", html).group(0)
        assert "overflow-y:auto" in area


class TestExpedientePorFactura:
    """Una factura con varias glosas es UN caso, no varias búsquedas."""

    def test_consolida_todas_las_glosas_con_totales(self, client, db_session):
        from app.models.db import GlosaRecord

        _analizar(client, factura="HUS0000600100")
        # Segunda glosa de la MISMA factura con otro código (el anti-dup
        # actualiza si coinciden factura+código+etapa, y acá queremos dos).
        db_session.add(
            GlosaRecord(
                eps="COMPENSAR",
                factura="HUS0000600100",
                codigo_glosa="SO3401",
                etapa="RESPUESTA",
                estado="RADICADA",
                valor_objetado=90_000,
            )
        )
        db_session.commit()

        r = client.get("/glosas/expediente/factura", params={"numero": "HUS0000600100"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["factura"] == "HUS0000600100"
        assert d["totales"]["glosas"] == 2
        assert d["totales"]["valor_objetado"] > 0
        assert len(d["glosas"]) == 2
        assert all("cerrada" in g for g in d["glosas"])

    def test_factura_sin_glosas_da_404(self, client):
        assert (
            client.get(
                "/glosas/expediente/factura", params={"numero": "HUS999NOEXISTE"}
            ).status_code
            == 404
        )

    def test_la_pantalla_consolida_y_accede(self):
        html = (Path(__file__).resolve().parent.parent.parent / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )
        assert "function expFactura" in html
        assert "/glosas/expediente/factura" in html
        assert "Abrir en Analizar" in html  # del expediente al trabajo, un clic
        assert "Ver toda la factura" in html
