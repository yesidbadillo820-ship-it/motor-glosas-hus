"""Tests del predictor ML de ratificación (Ronda 12)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services.ml_ratificacion import predecir_ratificacion, _sigmoide


def test_sigmoide_limites():
    assert _sigmoide(500) == 1.0
    assert _sigmoide(-500) == 0.0
    assert abs(_sigmoide(0) - 0.5) < 0.0001


def _mock_db(total=0, ratif=0, previas=0):
    db = MagicMock()
    q = MagicMock()
    q.filter.return_value = q
    # Los scalar() retornarán alternativamente según el orden del código
    # (queremos total → ratif → previas).
    scalars = [total, ratif, previas]
    call = {"i": 0}
    def _sc():
        v = scalars[min(call["i"], len(scalars) - 1)]
        call["i"] += 1
        return v
    q.scalar.side_effect = _sc
    db.query.return_value = q
    return db


def test_match_perfecto_baja_riesgo():
    db = _mock_db()
    g = SimpleNamespace(
        id=1, codigo_glosa="TA0201", eps="FAMISANAR EPS",
        valor_objetado=50_000,
        dictamen="ESE HUS NO ACEPTA... " * 50,  # ~1000 chars
        modelo_ia="texto_fijo",
        estado="TARIFA_MATCH_PERFECTO",
        decision_eps=None,
    )
    r = predecir_ratificacion(db, g)
    assert r["nivel"] in ("MUY_BAJO", "BAJO")
    # Debe aparecer el factor positivo del match
    joined = " ".join(r["factores_positivos"])
    assert "MATCH" in joined.upper() or "match" in joined.lower()


def test_eps_alta_ratificacion_sube_riesgo():
    db = _mock_db(total=10, ratif=5, previas=3)  # 50% ratif histórico + 3 previas
    g = SimpleNamespace(
        id=2, codigo_glosa="TA0201", eps="NUEVA EPS",
        valor_objetado=2_000_000,
        dictamen="Defensa corta sin citas.",
        modelo_ia="groq/llama",
        estado="RADICADA",
        decision_eps=None,
    )
    r = predecir_ratificacion(db, g)
    assert r["nivel"] in ("ALTO", "MUY_ALTO", "MEDIO")
    assert len(r["factores_negativos"]) >= 2
    assert len(r["acciones_sugeridas"]) >= 1


def test_aseguradora_soat_tendencia_levantar():
    db = _mock_db()
    g = SimpleNamespace(
        id=3, codigo_glosa="TA0301", eps="COMPAÑIA MUNDIAL DE SEGUROS",
        valor_objetado=50_000,
        dictamen="Texto de defensa con citas. " * 60,
        modelo_ia="texto_fijo",
        estado="INICIAL",
        decision_eps=None,
    )
    r = predecir_ratificacion(db, g)
    joined = " ".join(r["factores_positivos"])
    assert "Aseguradora" in joined or "aseguradora" in joined.lower()


def test_pocas_citas_sugiere_agregar():
    db = _mock_db()
    g = SimpleNamespace(
        id=4, codigo_glosa="SO0101", eps="COOSALUD",
        valor_objetado=80_000,
        dictamen="Defensa sin mencionar normas específicas.",
        modelo_ia="groq/llama",
        estado="RADICADA",
        decision_eps=None,
    )
    r = predecir_ratificacion(db, g)
    joined = " ".join(r["acciones_sugeridas"])
    # Debe sugerir agregar citas
    assert "normas" in joined.lower() or "cita" in joined.lower()


def test_estructura_respuesta():
    db = _mock_db()
    g = SimpleNamespace(
        id=5, codigo_glosa="FA0801", eps="COMPENSAR",
        valor_objetado=100_000,
        dictamen="Texto con Ley 1438 y Res. 2284/2023 y Art. 871. " * 10,
        modelo_ia="groq/llama",
        estado="RADICADA",
        decision_eps=None,
    )
    r = predecir_ratificacion(db, g)
    assert set(r.keys()) >= {
        "probabilidad_ratificacion", "nivel",
        "factores_positivos", "factores_negativos",
        "acciones_sugeridas", "score_logit",
    }
    assert 0 <= r["probabilidad_ratificacion"] <= 1
