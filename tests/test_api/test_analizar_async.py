"""El túnel ya no decide si un dictamen llega a la pantalla.

02-09-2026 — PRUEBA 2 (CL4506). El túnel corta toda respuesta a los 100 s y
una glosa pesada tarda más. El motor terminaba y guardaba en el historial,
pero la respuesta nunca llegaba: «Error de conexión». Para el auditor eso ES
una caída.

Ahora `POST /analizar/async` devuelve el trace_id enseguida, el análisis corre
aparte con su propia sesión y su propio servicio —resueltos como lo haría
FastAPI, overrides incluidos—, y `GET /analizar/resultado/{trace_id}` entrega
el dictamen con una petición corta. La ruta bloqueante `/analizar` sigue
intacta para el agente de lotes y las herramientas.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.models.db import UsuarioRecord
from app.models.schemas import GlosaResult
from app.services import resultados_analisis as res


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


def _resultado_mock() -> GlosaResult:
    return GlosaResult(
        tipo="RESPUESTA RE9901",
        resumen="Defensa técnica generada",
        dictamen="<div>Dictamen mock del camino asíncrono</div>",
        codigo_glosa="TA0201",
        valor_objetado="$ 168,563",
        paciente="N/A",
        mensaje_tiempo="EN TÉRMINOS",
        color_tiempo="green",
        score=85.0,
        dias_restantes=10,
        modelo_ia="mock/test",
    )


@pytest.fixture
def service_mock():
    svc = MagicMock()
    svc.analizar = AsyncMock(return_value=_resultado_mock())
    return svc


@pytest.fixture
def client(db_session, usuario_fake, service_mock):
    from app.api.deps import get_usuario_actual
    from app.api.routers.analizar import get_glosa_service
    from app.main import app

    res._vaciar_para_pruebas()
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario_fake
    app.dependency_overrides[get_glosa_service] = lambda: service_mock
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
    res._vaciar_para_pruebas()


DATOS = {
    "eps": "FAMISANAR",
    "etapa": "RESPUESTA",
    "valor_aceptado": "0",
    "tabla_excel": "TA0201 — Diferencia tarifa CUPS 890750 valor objetado $168.563 según contrato vigente.",
}


def _esperar(client: TestClient, tid: str, segundos: float = 8.0) -> dict:
    """Consulta corta, repetida — igual que hace la pantalla."""
    fin = time.time() + segundos
    ultimo: dict = {}
    while time.time() < fin:
        r = client.get(f"/analizar/resultado/{tid}")
        assert r.status_code == 200, r.text
        ultimo = r.json()
        if ultimo.get("estado") != "en_curso":
            return ultimo
        time.sleep(0.1)
    return ultimo


class TestElPostRespondeEnseguida:
    def test_devuelve_202_con_trace_id(self, client):
        r = client.post("/analizar/async", data=DATOS)
        assert r.status_code == 202, r.text
        cuerpo = r.json()
        assert cuerpo["estado"] == "en_curso"
        assert cuerpo["trace_id"]

    def test_respeta_el_trace_id_que_manda_la_pantalla(self, client):
        r = client.post("/analizar/async", data={**DATOS, "trace_id": "abc-123"})
        assert r.json()["trace_id"] == "abc-123"


class TestElResultadoLlegaPorPeticionCorta:
    def test_el_dictamen_se_recoge_listo(self, client, service_mock):
        tid = client.post("/analizar/async", data=DATOS).json()["trace_id"]
        e = _esperar(client, tid)
        assert e["estado"] == "listo", e
        assert "Dictamen mock del camino asíncrono" in e["resultado"]["dictamen"]
        assert e["resultado"]["codigo_glosa"] == "TA0201"
        service_mock.analizar.assert_awaited()

    def test_el_analisis_se_persiste_en_la_sesion_de_la_app(self, client, db_session):
        """El corredor usa la sesión que la app resuelve, no una propia a ciegas."""
        from app.models.db import GlosaRecord

        tid = client.post("/analizar/async", data=DATOS).json()["trace_id"]
        assert _esperar(client, tid)["estado"] == "listo"
        assert db_session.query(GlosaRecord).count() == 1

    def test_un_trace_id_desconocido_es_404(self, client):
        assert client.get("/analizar/resultado/no-existe").status_code == 404

    def test_el_resultado_sobrevive_a_varias_consultas(self, client):
        """La pantalla puede preguntar más de una vez; el resultado no se consume."""
        tid = client.post("/analizar/async", data=DATOS).json()["trace_id"]
        assert _esperar(client, tid)["estado"] == "listo"
        assert client.get(f"/analizar/resultado/{tid}").json()["estado"] == "listo"


class TestUnAnalisisCaidoNoSePierdeEnSilencio:
    def test_el_error_llega_con_su_causa(self, client, service_mock):
        service_mock.analizar = AsyncMock(side_effect=RuntimeError("la IA se cayó"))
        tid = client.post("/analizar/async", data=DATOS).json()["trace_id"]
        e = _esperar(client, tid)
        assert e["estado"] == "error", e
        assert "la IA se cayó" in (e.get("detail") or "")
        assert e.get("status") == 500


class TestElCaminoDeSiempreSigueIntacto:
    def test_post_analizar_sigue_respondiendo_el_dictamen(self, client):
        r = client.post("/analizar", data=DATOS)
        assert r.status_code == 200, r.text
        assert "dictamen" in r.json()


class TestElAlmacenDeResultados:
    def test_ciclo_completo(self):
        res._vaciar_para_pruebas()
        res.abrir("t1")
        assert res.consultar("t1")["estado"] == "en_curso"
        res.cerrar_ok("t1", {"dictamen": "x"}, glosa_id=7)
        e = res.consultar("t1")
        assert e["estado"] == "listo" and e["glosa_id"] == 7 and e["resultado"] == {"dictamen": "x"}

    def test_error_guarda_causa_y_status(self):
        res._vaciar_para_pruebas()
        res.abrir("t2")
        res.cerrar_error("t2", "se cayó", 503)
        e = res.consultar("t2")
        assert e["estado"] == "error" and e["detail"] == "se cayó" and e["status"] == 503

    def test_lo_que_nunca_existio_es_none(self):
        res._vaciar_para_pruebas()
        assert res.consultar("nunca") is None

    def test_consultar_devuelve_copia(self):
        res._vaciar_para_pruebas()
        res.abrir("t3")
        res.consultar("t3")["estado"] = "manipulado"
        assert res.consultar("t3")["estado"] == "en_curso"

    def test_la_purga_no_se_come_lo_reciente(self, monkeypatch):
        res._vaciar_para_pruebas()
        res.abrir("viejo")
        reloj_real = time.time  # res.time es el propio módulo time: sin esto, recursión
        monkeypatch.setattr(res.time, "time", lambda: reloj_real() + res._TTL_SEGUNDOS + 5)
        res.abrir("nuevo")
        assert res.consultar("viejo") is None
        assert res.consultar("nuevo") is not None


class TestLaPantallaLanzaYRecoge:
    def test_el_front_usa_el_camino_asincrono(self):
        import io

        html = io.open("static/index.html", encoding="utf-8").read()
        assert "fetch('/analizar/async'" in html
        assert "async function esperarResultadoAnalisis(traceId)" in html
        assert "'/analizar/resultado/'+encodeURIComponent(traceId)" in html

    def test_analizar_ya_no_espera_la_respuesta_larga(self):
        import io

        html = io.open("static/index.html", encoding="utf-8").read()
        i = html.index("async function analizar(modoOverride){")
        j = html.index("function renderAccionIA(", i)
        cuerpo = html[i:j]
        assert "fetch('/analizar',{method:'POST'" not in cuerpo

    def test_si_se_agota_la_espera_manda_al_historial_sin_perder_el_dictamen(self):
        import io

        html = io.open("static/index.html", encoding="utf-8").read()
        assert "Revíselo en Historial en un momento: el dictamen se guarda al terminar" in html


class TestLaNarracionNoSeApagaEnSilencio:
    """02-09-2026. El auditor: «si el websocket se desconecta en silencio,
    rechazo la PR». Si el túnel corta el stream de /eventos/analizar, la
    pantalla lo dice, reintenta una vez con el mismo trace_id, y si tampoco
    vuelve, lo dice también. El dictamen llega igual por la consulta corta."""

    def _narrador(self) -> str:
        import io

        html = io.open("static/index.html", encoding="utf-8").read()
        i = html.index("function iniciarNarracion(traceId)")
        j = html.index("return { cerrar: cerrar };", i)
        return html[i:j]

    def test_el_bucle_tiene_nombre_para_poder_reintentar(self):
        assert "async function leer()" in self._narrador()

    def test_un_corte_deja_una_linea_visible_y_reintenta_una_vez(self):
        n = self._narrador()
        assert "agregar('reconectando', {})" in n
        assert "setTimeout(function(){ if(!cerrado) leer(); }, 1500)" in n
        assert "reintentado = true" in n

    def test_si_tampoco_vuelve_lo_dice(self):
        assert "agregar('sin_narracion', {})" in self._narrador()

    def test_un_final_legitimo_no_dispara_reintento(self):
        n = self._narrador()
        assert "terminado = true; cerrar();" in n
        assert "if(cerrado || terminado){ cerrar(); return; }" in n

    def test_ya_no_hay_cierre_silencioso(self):
        assert "cierre silencioso" not in self._narrador()

    def test_los_dos_avisos_tienen_texto_para_el_gestor(self):
        import io

        html = io.open("static/index.html", encoding="utf-8").read()
        assert "Se cortó la narración en vivo; reconectando" in html
        assert "La narración en vivo no volvió" in html
