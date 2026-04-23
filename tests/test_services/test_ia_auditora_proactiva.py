"""Tests de la IA auditora proactiva (scheduler + pre-análisis)."""
from __future__ import annotations

from datetime import datetime, time
from unittest.mock import MagicMock, patch

import pytest


def test_segundos_hasta_6am_dentro_de_24h():
    from app.services.ia_auditora_proactiva import _segundos_hasta_proximas_6am
    s = _segundos_hasta_proximas_6am()
    assert 0 < s <= 86400, "debe ser positivo y menor o igual a 24h"


def test_obtener_estado_initial():
    from app.services.ia_auditora_proactiva import obtener_estado
    est = obtener_estado()
    assert "scheduler_activo" in est
    assert "ejecucion_en_curso" in est
    assert "ultima_ejecucion" in est


@pytest.mark.asyncio
async def test_ejecutar_pre_analisis_sin_glosas_pendientes():
    """Si no hay glosas pendientes, retorna procesadas=0 sin error."""
    from app.services import ia_auditora_proactiva as iap
    # Forzar flag off
    iap._EJECUCION_EN_CURSO = False

    fake_db = MagicMock()
    # query().filter().filter().filter().order_by().limit().all() → []
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    fake_db.query.return_value = q

    with patch("app.services.ia_auditora_proactiva.SessionLocal", return_value=fake_db):
        stats = await iap.ejecutar_pre_analisis_background(limite=5)
    assert stats.get("procesadas") == 0
    assert "mensaje" in stats


@pytest.mark.asyncio
async def test_ejecucion_concurrente_se_bloquea():
    """Si ya hay una ejecución corriendo, la segunda retorna skip."""
    from app.services import ia_auditora_proactiva as iap
    iap._EJECUCION_EN_CURSO = True
    try:
        r = await iap.ejecutar_pre_analisis_background(limite=5)
        assert "skip" in r
    finally:
        iap._EJECUCION_EN_CURSO = False
