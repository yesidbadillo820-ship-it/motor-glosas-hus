"""Tests del tablero de calidad (scorer de dictámenes).

Protegen el scorer mismo: que corra sobre los 4 casos, que detecte los
defectos que Yesid marcó en su auditoría experta del 30-jun-2026, y que la
línea base (producción) NO apruebe todavía (para que cuando los fixes la
suban, el cambio sea visible y medible).
"""

from __future__ import annotations

import json
import os

from tests.benchmark.scorer import UMBRAL_BUENO, puntuar_dictamen

_CASOS = os.path.join(os.path.dirname(__file__), "benchmark", "casos.json")


def _casos():
    with open(_CASOS, encoding="utf-8") as f:
        return {c["id"]: c for c in json.load(f)["casos"]}


def test_scorer_corre_los_cuatro_casos():
    casos = _casos()
    assert len(casos) == 4
    for caso in casos.values():
        r = puntuar_dictamen(caso["dictamen_produccion"], caso)
        assert 0.0 <= r["score"] <= 10.0
        assert "defectos" in r


def test_medimas_detecta_negacion_de_contrato():
    casos = _casos()
    r = puntuar_dictamen(casos["medimas_davinci"]["dictamen_produccion"], casos["medimas_davinci"])
    criterios = {d["criterio"] for d in r["defectos"]}
    assert "niega_contrato_citado" in criterios
    assert "tarifa_incoherente" in criterios


def test_ecoopsos_detecta_norma_alucinada_y_silencio():
    casos = _casos()
    r = puntuar_dictamen(
        casos["ecoopsos_coclear"]["dictamen_produccion"], casos["ecoopsos_coclear"]
    )
    criterios = {d["criterio"] for d in r["defectos"]}
    assert "norma_alucinada" in criterios  # Ley 1388/2010 (cáncer) en caso auditivo
    assert "falso_silencio_positivo" in criterios


def test_hemofilia_detecta_clausula_inventada_y_placeholder():
    casos = _casos()
    r = puntuar_dictamen(
        casos["hemofilia_sancion"]["dictamen_produccion"], casos["hemofilia_sancion"]
    )
    criterios = {d["criterio"] for d in r["defectos"]}
    assert "clausula_inventada" in criterios
    assert "placeholder_sin_llenar" in criterios


def test_saludtotal_detecta_pacta_sunt_servanda_en_sancion():
    """El defecto que Yesid llamó 'tiro por la culata': invocar Pacta Sunt
    Servanda ante una cláusula sancionatoria concede que aplica."""
    casos = _casos()
    r = puntuar_dictamen(casos["saludtotal_tms"]["dictamen_produccion"], casos["saludtotal_tms"])
    criterios = {d["criterio"] for d in r["defectos"]}
    assert "sancion_pacta_sunt_servanda" in criterios
    assert "tono_hostil" in criterios


def test_linea_base_no_aprueba_todavia():
    """La producción del 30-jun saca < 7 en todos (baseline a superar)."""
    casos = _casos()
    aprobados = 0
    for caso in casos.values():
        r = puntuar_dictamen(caso["dictamen_produccion"], caso)
        if r["score"] >= UMBRAL_BUENO:
            aprobados += 1
    assert aprobados == 0, "Si la baseline empezó a aprobar, actualizá este test (¡buena noticia!)"


def test_dictamen_perfecto_aprueba():
    """Sanity: un dictamen que responde todo y no comete defectos saca >= 7."""
    caso = {
        "id": "perfecto",
        "contrato": "CTR-2024-X-HUS",
        "tiene_sancion": True,
        "es_tecnologia_cara": True,
        "conceptos": [
            {"id": "c1", "keywords": ["pertinencia"]},
            {"id": "c2", "keywords": ["dosis"]},
        ],
    }
    dictamen = (
        "Respecto de la pertinencia, conforme a EAU Guidelines y evidencia nivel 1A. "
        "Respecto de la dosis, corresponde al peso del paciente. La sanción se rechaza "
        "por vicio de competencia: las EPS carecen de facultad sancionatoria (Ley 1438 "
        "Art. 126). Se defiende dentro del contrato CTR-2024-X-HUS. Se solicita el "
        "levantamiento de la glosa."
    )
    r = puntuar_dictamen(dictamen, caso)
    assert r["score"] >= UMBRAL_BUENO, r["defectos"]
    assert r["aprobado"]
