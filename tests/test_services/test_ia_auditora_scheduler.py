"""Tests del scheduler ia_auditora_proactiva (R70 P3).

Garantizan: cálculo correcto del delay hasta las 6 AM, idempotencia
de iniciar/detener, no romper en absence de event loop.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from app.services.ia_auditora_proactiva import (
    _segundos_hasta_proximas_6am,
    detener_scheduler,
    iniciar_scheduler,
    obtener_estado,
)


class TestProxima6Am:
    def test_a_las_5am_falta_1h(self):
        with patch("app.services.ia_auditora_proactiva.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 25, 5, 0, 0)
            mock_dt.replace = datetime.replace
            espera = _segundos_hasta_proximas_6am()
            # ~1h
            assert 3500 <= espera <= 3700

    def test_a_las_7am_falta_23h(self):
        with patch("app.services.ia_auditora_proactiva.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 25, 7, 0, 0)
            mock_dt.replace = datetime.replace
            espera = _segundos_hasta_proximas_6am()
            # ~23h = 82800s
            assert 82_000 <= espera <= 84_000

    def test_a_las_6am_exacto_va_al_dia_siguiente(self):
        """A las 6:00:00 exactas, va al siguiente día (no se ejecuta hoy)."""
        with patch("app.services.ia_auditora_proactiva.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 25, 6, 0, 0)
            mock_dt.replace = datetime.replace
            espera = _segundos_hasta_proximas_6am()
            # ~24h
            assert 86_000 <= espera <= 86_500


class TestSchedulerLifecycle:
    def test_detener_idempotente_sin_iniciar(self):
        """Llamar detener sin iniciar no debe romper."""
        detener_scheduler()
        detener_scheduler()  # idempotente

    def test_obtener_estado_devuelve_dict(self):
        estado = obtener_estado()
        assert isinstance(estado, dict)


class TestIniciarSinEventLoop:
    def test_iniciar_sin_event_loop_no_explota(self):
        """En contexto sync (tests pytest sin asyncio mode), iniciar
        debe ser noop con warning, no exception."""
        iniciar_scheduler()  # no debe lanzar
        detener_scheduler()
