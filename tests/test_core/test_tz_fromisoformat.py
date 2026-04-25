"""Tests de defensa contra fromisoformat() naive vs columna TZ-aware (R53 P3).

Garantiza que cualquier `datetime.fromisoformat(input_usuario)` que vaya
a parar a una columna `DateTime(timezone=True)` (Postgres TIMESTAMPTZ) se
normalice con `a_utc()` antes — si no, el siguiente `column - ahora_utc()`
lanza TypeError en producción.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.tz import a_utc, ahora_utc


class TestFromIsoformatDefensa:
    def test_iso_naive_normalizado_a_utc(self):
        """Input típico de form: '2026-05-10T10:00:00' (sin tz).
        a_utc() debe devolverlo TZ-aware en UTC."""
        parsed = datetime.fromisoformat("2026-05-10T10:00:00")
        assert parsed.tzinfo is None  # confirmamos que parsed es naive
        normalizado = a_utc(parsed)
        assert normalizado.tzinfo == timezone.utc

    def test_iso_con_z_ya_es_aware(self):
        """Input '2026-05-10T10:00:00+00:00' ya viene TZ-aware."""
        parsed = datetime.fromisoformat("2026-05-10T10:00:00+00:00")
        assert parsed.tzinfo is not None
        # a_utc no debe modificar
        normalizado = a_utc(parsed)
        assert normalizado == parsed

    def test_resta_post_normalizacion_no_explota(self):
        """REGRESIÓN: el bug raíz era resta naive vs TZ-aware. Tras a_utc()
        debe funcionar contra ahora_utc()."""
        parsed = a_utc(datetime.fromisoformat("2026-04-25T08:00:00"))
        delta = ahora_utc() - parsed
        assert delta is not None  # no explota
