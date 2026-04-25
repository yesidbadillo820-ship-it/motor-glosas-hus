"""Tests del scheduler diario de mantenimiento (R57 P2)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from app.services.mantenimiento_scheduler import (
    _segundos_hasta_proxima_ejecucion,
    detener_scheduler,
    iniciar_scheduler,
)


class TestProximaEjecucion:
    def test_si_son_las_2am_falta_1h(self):
        """A las 2 AM faltan ~3600s para las 3 AM."""
        with patch("app.services.mantenimiento_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 25, 2, 0, 0)
            mock_dt.replace = datetime.replace
            espera = _segundos_hasta_proxima_ejecucion()
            # Esperamos ~3600s (1h)
            assert 3500 <= espera <= 3700

    def test_si_son_las_4am_falta_23h(self):
        """A las 4 AM ya pasó la ejecución de hoy → faltan ~23h hasta las 3 AM
        del próximo día."""
        with patch("app.services.mantenimiento_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 25, 4, 0, 0)
            mock_dt.replace = datetime.replace
            espera = _segundos_hasta_proxima_ejecucion()
            # ~23h
            assert 80_000 <= espera <= 84_000

    def test_a_las_3am_exacto_va_al_dia_siguiente(self):
        """A las 3:00:00 exactas, no debería volver a ejecutar HOY."""
        with patch("app.services.mantenimiento_scheduler.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 4, 25, 3, 0, 0)
            mock_dt.replace = datetime.replace
            espera = _segundos_hasta_proxima_ejecucion()
            # Como objetivo == ahora, agrega 1 día
            assert 86_000 <= espera <= 86_500


class TestSchedulerLifecycle:
    def test_detener_idempotente_sin_iniciar(self):
        """Llamar detener sin haber iniciado no debe romper."""
        detener_scheduler()  # no debe lanzar
        detener_scheduler()  # idempotente

    def test_iniciar_sin_event_loop_no_explota(self):
        """En contexto sync (tests pytest sin asyncio mode), iniciar
        debe ser noop con warning, no exception."""
        # No hay event loop activo en este test sync
        iniciar_scheduler()  # no debe lanzar
        detener_scheduler()
