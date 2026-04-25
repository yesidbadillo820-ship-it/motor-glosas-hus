"""Tests del helper TZ-aware (R52 C)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.tz import a_utc, ahora_utc


class TestAhoraUtc:
    def test_devuelve_tz_aware(self):
        ahora = ahora_utc()
        assert ahora.tzinfo is not None
        assert ahora.tzinfo == timezone.utc

    def test_resta_funciona_con_columna_tz_aware(self):
        """REGRESIÓN: ahora_utc() - tz_aware no debe lanzar TypeError.

        Antes con datetime.utcnow() (naive) restando contra un valor
        de columna DateTime(timezone=True) (tz-aware) Python lanzaba:
        'can't subtract offset-naive and offset-aware datetimes'.
        """
        col_tz_aware = datetime.now(timezone.utc) - timedelta(days=2)
        delta = ahora_utc() - col_tz_aware
        assert delta.days == 2

    def test_comparacion_funciona_con_columna_tz_aware(self):
        col_tz_aware = datetime.now(timezone.utc) - timedelta(days=2)
        assert col_tz_aware < ahora_utc()


class TestAUtc:
    def test_naive_se_convierte_a_utc(self):
        naive = datetime(2026, 4, 25, 10, 0)
        out = a_utc(naive)
        assert out.tzinfo is not None
        assert out.tzinfo == timezone.utc
        # Mismo "wall clock", solo agrega tz
        assert out.hour == 10

    def test_tz_aware_no_modifica(self):
        aware = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)
        out = a_utc(aware)
        assert out == aware
        assert out.tzinfo == timezone.utc

    def test_none_retorna_none(self):
        assert a_utc(None) is None

    def test_resta_funciona_tras_normalizar(self):
        """Caso típico: campo de BD que pudo quedar naive (legacy) — se
        normaliza con a_utc() antes de comparar contra ahora_utc()."""
        legado_naive = datetime(2026, 4, 25, 10, 0)
        delta = ahora_utc() - a_utc(legado_naive)
        # No explota — esa era la prueba clave
        assert delta is not None
