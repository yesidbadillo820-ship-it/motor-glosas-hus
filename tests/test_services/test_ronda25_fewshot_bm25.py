"""Ronda 25 / Fase 3 RAG-banco (jul-2026) — few-shots por SIMILITUD.

El match exacto (eps+código) de obtener_ejemplos_gold tenía recall bajo:
si no había histórico del par exacto, no había ejemplo relevante. Ahora,
cuando faltan ejemplos, se completa con precedentes GANADOS rankeados por
BM25 al texto de la glosa (RAGService, sobre cualquier eps/código).

Se prueba con una BD en memoria vacía (pasos 1-3 no devuelven nada) y el
RAGService mockeado, para aislar el paso BM25 nuevo.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base


@pytest.fixture
def db_vacia():
    """SQLite en memoria con el esquema creado pero SIN filas — fuerza que
    obtener_ejemplos_gold caiga al paso 4 (BM25)."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


_PRECEDENTES_FAKE = [
    {
        "extracto_dictamen": (
            "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE TARIFA. "
            "El valor facturado corresponde a la tarifa pactada y el servicio "
            "está debidamente soportado conforme a la normatividad vigente. " * 3
        ),
        "eps": "COMPENSAR",
        "codigo_glosa": "TA0201",
        "id": 101,
        "score_similitud": 9.4,
    },
]


def _mock_rag(monkeypatch, precedentes):
    import app.services.rag_service as rag

    def _fake(self, **kwargs):
        return precedentes

    monkeypatch.setattr(rag.RAGService, "buscar_casos_similares", _fake)


def test_bm25_completa_cuando_no_hay_match_exacto(monkeypatch, db_vacia):
    monkeypatch.delenv("GLOSA_FEWSHOT_BM25", raising=False)
    _mock_rag(monkeypatch, _PRECEDENTES_FAKE)
    from app.services.few_shot_gold import obtener_ejemplos_gold

    ejemplos = obtener_ejemplos_gold(
        db_vacia, "COMPENSAR", "TA0201", texto_glosa="LA EPS OBJETA LA TARIFA APLICADA"
    )
    assert any(e["fuente"] == "SIMILAR_BM25" for e in ejemplos)


def test_bm25_apagable_por_env(monkeypatch, db_vacia):
    monkeypatch.setenv("GLOSA_FEWSHOT_BM25", "0")
    _mock_rag(monkeypatch, _PRECEDENTES_FAKE)
    from app.services.few_shot_gold import obtener_ejemplos_gold

    ejemplos = obtener_ejemplos_gold(
        db_vacia, "COMPENSAR", "TA0201", texto_glosa="LA EPS OBJETA LA TARIFA"
    )
    assert not any(e["fuente"] == "SIMILAR_BM25" for e in ejemplos)


def test_bm25_no_corre_sin_texto_glosa(monkeypatch, db_vacia):
    """Sin texto_glosa no se puede rankear por similitud → no BM25."""
    monkeypatch.delenv("GLOSA_FEWSHOT_BM25", raising=False)
    _mock_rag(monkeypatch, _PRECEDENTES_FAKE)
    from app.services.few_shot_gold import obtener_ejemplos_gold

    ejemplos = obtener_ejemplos_gold(db_vacia, "COMPENSAR", "TA0201", texto_glosa="")
    assert not any(e["fuente"] == "SIMILAR_BM25" for e in ejemplos)


def test_bm25_filtra_precedente_con_contrato_ajeno(monkeypatch, db_vacia):
    """Un precedente que cita el contrato de OTRA EPS no se inyecta (la IA
    lo arrastraría al dictamen — contrato cruzado)."""
    monkeypatch.delenv("GLOSA_FEWSHOT_BM25", raising=False)
    ajeno = [
        {
            "extracto_dictamen": (
                "ESE HUS NO ACEPTA LA GLOSA. Conforme al CONTRATO "
                "S-13-1-03-1-04958 suscrito con FAMISANAR, la tarifa aplicable "
                "corresponde a lo pactado y el servicio está soportado. " * 3
            ),
            "eps": "FAMISANAR",
            "codigo_glosa": "TA0201",
            "id": 202,
            "score_similitud": 8.1,
        }
    ]
    _mock_rag(monkeypatch, ajeno)
    from app.services.few_shot_gold import obtener_ejemplos_gold

    # La glosa es de COMPENSAR: el precedente cita el contrato de FAMISANAR.
    ejemplos = obtener_ejemplos_gold(
        db_vacia, "COMPENSAR", "TA0201", texto_glosa="LA EPS OBJETA LA TARIFA"
    )
    assert not any(e.get("id") == 202 for e in ejemplos)


def test_bloque_similar_prohibe_copiar_datos_del_ejemplo():
    """El bloque de ejemplos por similitud debe prohibir copiar folios,
    fechas, contratos y valores del ejemplo (son de otro caso)."""
    from app.services.few_shot_gold import bloque_few_shot_para_prompt

    bloque = bloque_few_shot_para_prompt(
        [{"argumento": "X" * 300, "fuente": "SIMILAR_BM25", "id": 1}]
    )
    assert "PROHIBIDO copiar del ejemplo" in bloque
    assert "otro" in bloque.lower()
