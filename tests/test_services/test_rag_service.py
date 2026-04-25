"""Tests del RAG service (precedentes internos del HUS) — R51 P4."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.db import GlosaRecord
from app.services.rag_service import (
    RAGService,
    _normalizar,
    _palabras_clave,
    _similitud,
)


class TestHelpers:
    def test_normalizar_minusculas_y_puntuacion(self):
        assert _normalizar("Hola, MUNDO!!!") == "hola mundo"

    def test_normalizar_vacio(self):
        assert _normalizar("") == ""
        assert _normalizar(None) == ""

    def test_similitud_identica_es_1(self):
        assert _similitud("mismo texto", "mismo texto") == 1.0

    def test_similitud_diferentes(self):
        assert 0.0 <= _similitud("hola", "adios") < 1.0

    def test_similitud_vacia_es_0(self):
        assert _similitud("", "algo") == 0.0
        assert _similitud("algo", "") == 0.0

    def test_palabras_clave_filtra_stopwords_y_cortas(self):
        kw = _palabras_clave("tarifa contrato segun valor glosa sobre")
        # 'segun', 'valor', 'glosa', 'sobre' son stopwords
        assert "tarifa" in kw
        assert "contrato" in kw
        assert "segun" not in kw
        assert "glosa" not in kw

    def test_palabras_clave_longitud_minima(self):
        # Solo palabras con >= 5 chars
        kw = _palabras_clave("hoy voy a casa")
        assert all(len(p) >= 5 for p in kw)


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    S = sessionmaker(bind=engine)
    s = S()
    # Seed precedentes exitosos del HUS
    s.add(GlosaRecord(
        eps="FAMISANAR", codigo_glosa="TA0201",
        dictamen="Dictamen sobre tarifa contrato consulta urgencias...",
        decision_eps="LEVANTADA", etapa="respuesta",
        valor_objetado=100000, creado_en=datetime.now(timezone.utc),
    ))
    s.add(GlosaRecord(
        eps="FAMISANAR", codigo_glosa="TA0202",
        dictamen="Otra tarifa pactada contrato consulta especialista...",
        decision_eps="LEVANTADA", etapa="respuesta",
        valor_objetado=200000, creado_en=datetime.now(timezone.utc),
    ))
    s.add(GlosaRecord(
        eps="SALUD TOTAL", codigo_glosa="SO0101",
        dictamen="Soporte historia clínica completa institucional...",
        decision_eps="RATIFICADA", etapa="respuesta",
        valor_objetado=50000, creado_en=datetime.now(timezone.utc),
    ))
    s.commit()
    try:
        yield s
    finally:
        s.close()


class TestBuscarCasosSimilares:
    def test_filtra_por_solo_exitosos(self, db):
        """Por defecto solo trae LEVANTADAS."""
        r = RAGService().buscar_casos_similares(
            "tarifa contrato consulta", "FAMISANAR", "TA0201", db,
            top_k=5, solo_exitosos=True,
        )
        # Los dos TA (levantados) pueden aparecer; el SO (ratificado) no
        for c in r:
            assert c["decision_eps"] == "LEVANTADA"

    def test_bonus_eps_y_codigo_mejora_ranking(self, db):
        """Un caso con la misma EPS y prefijo de código debe rankear alto."""
        r = RAGService().buscar_casos_similares(
            "tarifa contrato pactada", "FAMISANAR", "TA0299", db,
            top_k=3, solo_exitosos=True,
        )
        assert len(r) > 0
        # Los códigos TA* de FAMISANAR deben aparecer
        assert any(c["codigo_glosa"].startswith("TA") for c in r)

    def test_db_vacia_retorna_lista_vacia(self, db):
        # Crear db limpia
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        S = sessionmaker(bind=engine)
        empty = S()
        try:
            r = RAGService().buscar_casos_similares(
                "cualquier texto", "FAMISANAR", "TA0201", empty, top_k=3,
            )
            assert r == []
        finally:
            empty.close()


class TestConstruirContextoRag:
    def test_sin_casos_retorna_vacio(self):
        assert RAGService().construir_contexto_rag([]) == ""

    def test_con_casos_construye_bloque_precedentes(self):
        casos = [{
            "codigo_glosa": "TA0201", "eps": "FAMISANAR",
            "etapa": "respuesta", "decision_eps": "LEVANTADA",
            "score_similitud": 0.75,
            "extracto_dictamen": "Extracto del precedente...",
            "id": 1,
        }]
        ctx = RAGService().construir_contexto_rag(casos)
        assert "PRECEDENTES EXITOSOS" in ctx
        assert "TA0201" in ctx
        assert "FAMISANAR" in ctx
