"""Golden set de CALIDAD — corre en CI en cada cambio.

Evalúa el pipeline determinista del motor (detectores + sanitizers, SIN
LLM) sobre casos reales auditados. Si un cambio rompe la detección de EPS,
sub-conceptos, complejidad, sanciones, contratos, o reintroduce un bug de
placeholders ya corregido, este test FALLA — atrapando la regresión de
calidad antes de producción.

Cada criterio es un test parametrizado individual para que el reporte de
CI muestre EXACTAMENTE qué criterio falló y en qué caso.
"""

from __future__ import annotations

import pytest

from tests.golden.evaluador import cargar_casos, evaluar_todo

_REPORTE = evaluar_todo()


def test_golden_set_sin_fallos():
    """El golden set completo debe pasar al 100%."""
    fallos = _REPORTE["fallidos"]
    detalle = "\n".join(
        f"  [{f['caso']}] {f['criterio']}: {f['detalle']}" for f in _REPORTE["fallos"]
    )
    assert fallos == 0, (
        f"{fallos}/{_REPORTE['total_criterios']} criterios de calidad fallaron:\n{detalle}"
    )


def test_golden_set_cobertura_minima():
    """Sanity: el golden set debe evaluar una cantidad mínima de criterios
    (si baja mucho, alguien borró casos sin querer)."""
    assert _REPORTE["total_criterios"] >= 30


def _ids_criterios():
    """Genera (caso_id, indice, criterio_nombre) para parametrizar."""
    ids = []
    for caso_id, criterios in _REPORTE["detalle_por_caso"].items():
        for i, c in enumerate(criterios):
            ids.append(pytest.param(caso_id, i, id=f"{caso_id}::{c['criterio']}"))
    return ids


@pytest.mark.parametrize("caso_id,indice", _ids_criterios())
def test_criterio_individual(caso_id: str, indice: int):
    """Un test por criterio — el nombre del test dice qué validó."""
    criterio = _REPORTE["detalle_por_caso"][caso_id][indice]
    assert criterio["ok"], f"{caso_id} → {criterio['criterio']}: {criterio['detalle']}"


def test_dataset_bien_formado():
    """El JSON del dataset debe tener la estructura esperada."""
    data = cargar_casos()
    assert "casos_glosa" in data
    assert "dictamenes_con_bugs" in data
    assert len(data["casos_glosa"]) >= 5
    for caso in data["casos_glosa"]:
        assert "id" in caso and "glosa" in caso and "criterios" in caso
    for caso in data["dictamenes_con_bugs"]:
        assert "id" in caso and "dictamen_sucio" in caso and "aplicar" in caso
