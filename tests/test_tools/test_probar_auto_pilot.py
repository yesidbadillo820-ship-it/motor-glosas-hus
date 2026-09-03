"""tools/probar_auto_pilot.py — la prueba en vivo del Auto-Pilot.

Verifica, sobre una base sembrada con el MOTOR REAL (sin stubs del
evaluador), que el informe trae las tres evidencias que pidió el auditor:
el ciclo corrió, las candidatas quedaron SOLO en cuarentena, y la bitácora
registró confianza, riesgo y `modelo_utilizado`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import GlosaRecord

_TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(_TOOLS))

import probar_auto_pilot as PA  # noqa: E402

DICTAMEN_LARGO = (
    "<div>ESE HUS NO ACEPTA LA GLOSA. La objeción fue notificada fuera del "
    "término legal de la Ley 1438 de 2011 y la Resolución 3047 de 2008, "
    "configurándose el silencio administrativo positivo conforme al "
    "Artículo 57. ═══ DOCUMENTO: historia_clinica.pdf ═══ El expediente "
    "completo reposa radicado con la factura, incluida la epicrisis y los "
    "RIPS del servicio prestado, conforme al Decreto 441 de 2022 y la "
    "Circular 030. Se sostiene la defensa técnica en su integridad.</div>"
)


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


def _sembrar(db):
    filas = [
        # Candidata legítima: texto fijo extemporáneo (confianza real 0.95),
        # valor bajo, soporte referenciado → riesgo BAJO.
        dict(
            eps="COOSALUD",
            factura="HUS495001",
            codigo_glosa="SO0101",
            valor_objetado=180000.0,
            estado="PENDIENTE",
            workflow_state="RADICADA",
            dictamen=DICTAMEN_LARGO,
            modelo_ia="texto_fijo_extemporanea",
            texto_glosa_original="SO0101 | Falta epicrisis ═══ DOCUMENTO: historia_clinica.pdf ═══",
        ),
        # Mismo texto fijo pero valor alto → el tope de $500.000 la rechaza.
        dict(
            eps="COOSALUD",
            factura="HUS495002",
            codigo_glosa="SO0101",
            valor_objetado=2300000.0,
            estado="PENDIENTE",
            workflow_state="RADICADA",
            dictamen=DICTAMEN_LARGO,
            modelo_ia="texto_fijo_extemporanea",
        ),
        # Abstención: el caso «sin nada» jamás se auto-envía.
        dict(
            eps="NUEVA EPS",
            factura="HUS495003",
            codigo_glosa="FA1601",
            valor_objetado=90000.0,
            estado="PENDIENTE",
            workflow_state="RADICADA",
            dictamen="<div>No existe evidencia suficiente…</div>",
            modelo_ia="abstencion-deterministica",
        ),
        # Dictamen IA normal (Groq): confianza real ≤ 92 % → rechazada,
        # y la bitácora debe registrar el nombre del modelo del fallback.
        dict(
            eps="FAMISANAR",
            factura="HUS495004",
            codigo_glosa="TA0201",
            valor_objetado=120000.0,
            estado="PENDIENTE",
            workflow_state="RADICADA",
            dictamen=DICTAMEN_LARGO,
            modelo_ia="llama-3.3-70b-versatile",
        ),
    ]
    for f in filas:
        db.add(GlosaRecord(**f))
    db.commit()


def _stub_indexador_quieto(monkeypatch):
    import app.services.soportes_autodiscovery_service as sas

    class _Idx:
        def stats(self):
            return {"construyendo": False}

    monkeypatch.setattr(sas, "get_indexer", lambda: _Idx())


def test_flag_apagado_no_toca_nada(db, monkeypatch):
    monkeypatch.setenv("AUTO_PILOT_ENABLED", "0")
    _sembrar(db)
    informe = PA.correr_prueba(db, limite=25)
    assert informe["parte"]["estado"] == "deshabilitado"
    assert informe["borradores"] == []
    assert informe["bitacora"] == []


def test_informe_trae_las_tres_evidencias(db, monkeypatch):
    monkeypatch.setenv("AUTO_PILOT_ENABLED", "1")
    _stub_indexador_quieto(monkeypatch)
    _sembrar(db)

    informe = PA.correr_prueba(db, limite=25)

    # 1) El ciclo corrió y contó su trabajo.
    parte = informe["parte"]
    assert parte["estado"] == "ok"
    assert parte["evaluadas"] == 4
    assert parte["en_cuarentena"] == 1
    assert parte["rechazadas"] == 3

    # 2) La candidata quedó SOLO en cuarentena — jamás RESPONDIDA.
    assert len(informe["borradores"]) == 1
    assert informe["borradores"][0]["factura"] == "HUS495001"
    assert informe["borradores"][0]["workflow_state"] == "PENDIENTE_APROBACION_HUMANA"
    estados = {g.workflow_state for g in db.query(GlosaRecord).all()}
    assert "RESPONDIDA" not in estados and "ENVIADA" not in estados

    # 3) La bitácora registró confianza, riesgo y modelo_utilizado.
    bitacora = {f["glosa_id"]: f for f in informe["bitacora"]}
    assert len(bitacora) == 4
    candidata = next(f for f in informe["bitacora"] if f["decision"] == "CANDIDATA")
    assert candidata["confianza"] is not None and candidata["confianza"] > 0.92
    assert candidata["riesgo"] == "BAJO"
    assert candidata["modelo_utilizado"] == "texto_fijo_extemporanea"
    assert any(s.startswith("documento:") for s in candidata["soportes_analizados"])
    groq = next(
        f for f in informe["bitacora"] if f["modelo_utilizado"] == "llama-3.3-70b-versatile"
    )
    assert groq["decision"] == "RECHAZADA"


def test_precedencia_del_interruptor(monkeypatch, tmp_path):
    # consola > .env > valor por defecto del repo (encendido)
    monkeypatch.delenv("AUTO_PILOT_ENABLED", raising=False)
    monkeypatch.setattr(PA, "RAIZ", tmp_path)
    (tmp_path / ".env").write_text("AUTO_PILOT_ENABLED=0\n", encoding="utf-8")
    PA._cargar_env_como_el_arranque()
    assert PA.os.environ["AUTO_PILOT_ENABLED"] == "0"

    monkeypatch.setenv("AUTO_PILOT_ENABLED", "true")
    PA._cargar_env_como_el_arranque()
    assert PA.os.environ["AUTO_PILOT_ENABLED"] == "true"

    monkeypatch.delenv("AUTO_PILOT_ENABLED", raising=False)
    (tmp_path / ".env").write_text("# sin flag\n", encoding="utf-8")
    PA._cargar_env_como_el_arranque()
    assert PA.os.environ["AUTO_PILOT_ENABLED"] == "true"
