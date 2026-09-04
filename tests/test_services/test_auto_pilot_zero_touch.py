"""Auto-Pilot Zero-Touch: las cuatro salvaguardas del auditor (V2, Pilar 2).

03-09-2026. La máquina puede proponer, pero no radicar: (1) todo gobernado por
AUTO_PILOT_ENABLED, apagado por defecto y con aborto en la primera línea;
(2) la IA tiene PROHIBIDO escribir RESPONDIDA/ENVIADA — solo el estado de
cuarentena PENDIENTE_APROBACION_HUMANA, y libera una persona con un clic;
(3) bitácora inmutable: cada decisión es una fila nueva con regla, confianza,
riesgo y soportes analizados; (4) la primera validación NO es con casos
felices: se corre contra PRUEBAS_STRESS_IA (03 falla controlado, 04 resuelve
la contradicción documental y aún así pasa por humano, 05 se rechaza).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import AutoPilotBitacoraRecord, GlosaRecord
from app.services import auto_pilot_worker as W

CASOS = Path("PRUEBAS_STRESS_IA")


def _caso(nombre: str) -> tuple[dict, str]:
    datos = json.loads((CASOS / nombre / "datos.json").read_text(encoding="utf-8"))
    glosa_txt = (CASOS / nombre / "glosa.txt").read_text(encoding="utf-8")
    return datos, glosa_txt


@pytest.fixture(autouse=True)
def _indexador_quieto(monkeypatch):
    """El indexador de soportes, quieto, para TODAS las pruebas de este archivo.

    Por qué hace falta (04-09-2026). Estas pruebas se escribieron ANTES de que
    `procesar()` tuviera su escudo del indexador. Desde que existe, un ciclo
    aborta si el índice está reconstruyéndose — y durante la suite completa hay
    un scheduler de reindexación corriendo de fondo que puede ponerlo en
    «construyendo» en cualquier momento. Resultado: fallas intermitentes que no
    dicen nada del Auto-Pilot.

    El escudo NO se deja sin probar: tiene sus pruebas dedicadas en
    `test_autopilot_resiliencia.py`, que lo fuerzan a propósito. Aquí solo se
    quita de en medio una dependencia del entorno que no es lo que se mide.
    """
    import app.services.soportes_autodiscovery_service as sas

    class _IndiceQuieto:
        def stats(self):
            return {"construyendo": False, "facturas_indexadas": 0}

        def lookup(self, factura, auto_rebuild=True):
            return []

    monkeypatch.setattr(sas, "get_indexer", lambda: _IndiceQuieto())


@pytest.fixture
def db():
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


def _glosa(db, **kw):
    base = dict(
        eps="NUEVA EPS",
        factura="HUS1",
        codigo_glosa="TA0201",
        valor_objetado=100000.0,
        estado="PENDIENTE",
        workflow_state="RADICADA",
        dictamen="<div>ESE HUS NO ACEPTA LA GLOSA…</div>",
        modelo_ia="groq/llm",
    )
    base.update(kw)
    g = GlosaRecord(**base)
    db.add(g)
    db.commit()
    return g


def _stub_evaluador(monkeypatch, confianza=0.95, estado="LISTA_ENVIAR"):
    import app.services.autopilot_service as aps
    import app.services.riesgo_ratificacion as rr

    monkeypatch.setattr(
        aps,
        "evaluar_glosa_autopilot",
        lambda db, g: SimpleNamespace(
            estado=estado,
            confianza=confianza,
            razones_a_favor=[],
            razones_en_contra=["señal en contra"],
            detalle={"plantillas_gold": 2, "calidad_dictamen": {"ok": True}},
        ),
    )
    monkeypatch.setattr(
        rr, "calcular_riesgo", lambda **kw: {"nivel": "BAJO", "score": 10, "factores": []}
    )


class TestSalvaguarda1_FeatureFlag:
    def test_apagado_por_defecto(self, monkeypatch):
        monkeypatch.delenv("AUTO_PILOT_ENABLED", raising=False)
        assert W.habilitado() is False

    def test_con_flag_apagado_aborta_en_la_primera_linea(self, monkeypatch):
        monkeypatch.delenv("AUTO_PILOT_ENABLED", raising=False)

        class DBQueNoSePuedeTocar:
            def __getattr__(self, nombre):  # cualquier acceso = falló el aborto
                raise AssertionError(f"el worker tocó la base ({nombre}) con el flag apagado")

        parte = W.procesar(DBQueNoSePuedeTocar())
        assert parte["estado"] == "deshabilitado"

    def test_el_flag_enciende_solo_con_valor_afirmativo(self, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "0")
        assert W.habilitado() is False
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "true")
        assert W.habilitado() is True


class TestSalvaguarda2_Cuarentena:
    def test_la_ia_solo_escribe_el_estado_de_cuarentena(self, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        g = _glosa(db)
        parte = W.procesar(db)
        db.refresh(g)
        assert parte["en_cuarentena"] == 1
        assert g.workflow_state == "PENDIENTE_APROBACION_HUMANA"

    def test_los_estados_prohibidos_estan_por_escrito(self):
        assert "RESPONDIDA" in W.ESTADOS_PROHIBIDOS_PARA_IA
        assert "ENVIADA" in W.ESTADOS_PROHIBIDOS_PARA_IA
        assert W.ESTADO_CUARENTENA == "PENDIENTE_APROBACION_HUMANA"
        assert W.ESTADO_CUARENTENA not in W.ESTADOS_PROHIBIDOS_PARA_IA

    def test_lo_ya_respondido_no_se_toca(self, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        g = _glosa(db, workflow_state="RESPONDIDA")
        parte = W.procesar(db)
        db.refresh(g)
        assert parte["evaluadas"] == 0
        assert g.workflow_state == "RESPONDIDA"

    def test_la_liberacion_es_humana_y_queda_a_su_nombre(self, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        g = _glosa(db)
        W.procesar(db)
        r = W.liberar(db, g.id, "gestor@hus.gov.co")
        db.refresh(g)
        assert r["estado"] == "liberada"
        assert g.workflow_state == "RESPONDIDA"  # acción humana: sí puede
        fila = (
            db.query(AutoPilotBitacoraRecord)
            .filter(AutoPilotBitacoraRecord.decision == "LIBERADA_POR_HUMANO")
            .one()
        )
        assert fila.actor == "gestor@hus.gov.co"

    def test_no_se_libera_lo_que_no_esta_en_borradores(self, db):
        g = _glosa(db, workflow_state="RADICADA")
        assert W.liberar(db, g.id, "gestor@hus.gov.co")["estado"] == "no_esta_en_borradores"
        assert W.liberar(db, 999999, "gestor@hus.gov.co")["estado"] == "no_existe"


class TestSalvaguarda3_BitacoraInmutable:
    def test_cada_decision_guarda_regla_confianza_riesgo_y_soportes(self, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        g = _glosa(db, dictamen="═══ DOCUMENTO: epicrisis_hus.pdf ═══ ESE HUS NO ACEPTA…")
        W.procesar(db)
        fila = db.query(AutoPilotBitacoraRecord).one()
        assert fila.glosa_id == g.id
        assert fila.decision == "CANDIDATA"
        assert "Confianza" in fila.regla_aplicada and "riesgo BAJO" in fila.regla_aplicada
        assert fila.confianza == 0.95
        assert fila.riesgo == "BAJO"
        soportes = json.loads(fila.soportes_analizados)
        assert "documento:epicrisis_hus.pdf" in soportes
        assert fila.actor == "auto-pilot"

    def test_la_liberacion_es_fila_nueva_no_edicion(self, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        g = _glosa(db)
        W.procesar(db)
        original = db.query(AutoPilotBitacoraRecord).one()
        regla_original = original.regla_aplicada
        W.liberar(db, g.id, "gestor@hus.gov.co")
        filas = db.query(AutoPilotBitacoraRecord).order_by(AutoPilotBitacoraRecord.id).all()
        assert len(filas) == 2, "liberar inserta una fila nueva"
        assert filas[0].regla_aplicada == regla_original, "la fila de la máquina no se editó"
        assert filas[0].actor == "auto-pilot" and filas[1].actor == "gestor@hus.gov.co"


class TestSalvaguarda4_PruebasDeEstres:
    """La primera validación no es con casos felices: PRUEBAS_STRESS_IA."""

    def test_05_fa0205_sin_nada_se_rechaza(self, db):
        datos, glosa_txt = _caso("05_FA0205_SIN_NADA")
        from app.services.glosa_service import ARGUMENTO_ABSTENCION

        g = _glosa(
            db,
            eps=datos["eps"],
            factura=datos["numero_factura"],
            codigo_glosa=datos["codigo_glosa"],
            valor_objetado=float(datos["valor_glosado"]),
            texto_glosa_original=glosa_txt,
            dictamen=ARGUMENTO_ABSTENCION,
            modelo_ia="abstencion",
        )
        decision = W.evaluar_candidata(db, g)
        assert decision["decision"] == "RECHAZADA"
        assert "ABSTENCIÓN" in decision["regla_aplicada"].upper()

    def test_03_au0201_clausula_inexistente_falla_controlado(self, db, monkeypatch):
        datos, glosa_txt = _caso("03_AU0201_CLAUSULA_QUE_NO_EXISTE")
        _stub_evaluador(monkeypatch, confianza=0.99)  # aunque el evaluador jure confianza
        g = _glosa(
            db,
            eps=datos["eps"],
            factura=datos["numero_factura"],
            codigo_glosa=datos["codigo_glosa"],
            valor_objetado=float(datos["valor_glosado"]),  # $2.640.000
            texto_glosa_original=glosa_txt,
        )
        decision = W.evaluar_candidata(db, g)  # no lanza: rechazo con su porqué
        assert decision["decision"] == "RECHAZADA"
        assert "fuera del rango auto-enviable" in decision["regla_aplicada"]

    def test_03_si_el_evaluador_revienta_el_worker_no_alucina(self, db, monkeypatch):
        """Fallo controlado de verdad: el evaluador explota y el worker registra
        el rechazo con la causa, sin dejar la glosa en cuarentena."""
        import app.services.autopilot_service as aps

        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")

        def _revienta(db, g):
            raise RuntimeError("cláusula décima segunda no existe en el contrato")

        monkeypatch.setattr(aps, "evaluar_glosa_autopilot", _revienta)
        datos, glosa_txt = _caso("03_AU0201_CLAUSULA_QUE_NO_EXISTE")
        g = _glosa(
            db,
            eps=datos["eps"],
            factura=datos["numero_factura"],
            codigo_glosa=datos["codigo_glosa"],
            valor_objetado=float(datos["valor_glosado"]),
            texto_glosa_original=glosa_txt,
        )
        parte = W.procesar(db)
        db.refresh(g)
        assert parte["rechazadas"] == 1 and parte["en_cuarentena"] == 0
        assert g.workflow_state == "RADICADA"
        fila = db.query(AutoPilotBitacoraRecord).one()
        assert "Evaluación cayó" in fila.regla_aplicada
        assert "humano" in fila.regla_aplicada

    def test_04_so0102_la_contradiccion_se_resuelve_y_aun_asi_pasa_por_humano(self, db):
        """El motor resuelve la contradicción documental (18 facturadas vs 15
        registradas → partición exacta), y el Auto-Pilot NO auto-envía una
        parcial: repartir plata la aprueba una persona."""
        datos, glosa_txt = _caso("04_SO0102_SOPORTE_QUE_DICE_LO_CONTRARIO")
        from app.services.glosa_service import _particion_por_dosis

        argumento = (
            "EL KARDEX DE ENFERMERÍA REGISTRA QUINCE (15) DOSIS ADMINISTRADAS Y "
            "REGISTRADAS DEL MEROPENEM."
        )
        parte = _particion_por_dosis(glosa_txt.upper(), argumento, float(datos["valor_glosado"]))
        assert parte, "la contradicción documental debe resolverse con la partición"
        assert parte["facturadas"] == 18 and parte["soportadas"] == 15
        assert parte["valor_aceptar"] + parte["valor_defender"] == float(datos["valor_glosado"])

        g = _glosa(
            db,
            eps=datos["eps"],
            factura=datos["numero_factura"],
            codigo_glosa=datos["codigo_glosa"],
            valor_objetado=float(datos["valor_glosado"]),
            texto_glosa_original=glosa_txt,
            codigo_respuesta="RE9801",
        )
        decision = W.evaluar_candidata(db, g)
        assert decision["decision"] == "RECHAZADA"
        assert "PARCIAL" in decision["regla_aplicada"].upper()


class TestEndpoints:
    @pytest.fixture
    def client(self, db):
        from fastapi.testclient import TestClient

        from app.api.deps import get_auditor_o_superior, get_coordinador_o_admin, get_usuario_actual
        from app.database import get_db
        from app.main import app
        from app.models.db import UsuarioRecord

        usuario = UsuarioRecord(
            id=1, email="coord@hus.gov.co", nombre="C", rol="COORDINADOR", activo=1
        )
        app.dependency_overrides[get_db] = lambda: iter([db]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: usuario
        app.dependency_overrides[get_coordinador_o_admin] = lambda: usuario
        app.dependency_overrides[get_auditor_o_superior] = lambda: usuario
        with TestClient(app) as c:
            yield c
        app.dependency_overrides.clear()

    def test_procesar_respeta_el_flag(self, client, monkeypatch):
        monkeypatch.delenv("AUTO_PILOT_ENABLED", raising=False)
        r = client.post("/autopilot/procesar")
        assert r.status_code == 200
        assert r.json()["estado"] == "deshabilitado"

    def test_bandeja_lista_los_borradores_y_liberar_funciona(self, client, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        g = _glosa(db)
        client.post("/autopilot/procesar")
        d = client.get("/autopilot/borradores").json()
        assert d["total"] == 1 and d["borradores"][0]["glosa_id"] == g.id
        assert client.post(f"/autopilot/liberar/{g.id}").json()["estado"] == "liberada"
        assert client.get("/autopilot/borradores").json()["total"] == 0
        assert client.post(f"/autopilot/liberar/{g.id}").status_code == 409
        assert client.post("/autopilot/liberar/999999").status_code == 404

    def test_bitacora_expone_las_decisiones(self, client, db, monkeypatch):
        monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
        _stub_evaluador(monkeypatch)
        _glosa(db)
        client.post("/autopilot/procesar")
        d = client.get("/autopilot/bitacora").json()
        assert d["total"] == 1
        assert d["decisiones"][0]["decision"] == "CANDIDATA"
        assert d["decisiones"][0]["actor"] == "auto-pilot"


class TestLaPantallaTieneLaBandeja:
    def test_boton_y_liberacion_con_clic(self):
        import io

        html = io.open("static/index.html", encoding="utf-8").read()
        assert "verBorradoresAutoPilot" in html
        assert "liberarBorradorAutoPilot" in html
        assert "PENDIENTE_APROBACION_HUMANA" in html
        assert "Borradores Auto-Pilot" in html
