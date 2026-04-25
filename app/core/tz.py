"""Helpers de fecha y hora TZ-aware (R52 C).

Razón de existir:

  En Postgres muchas columnas son `Column(DateTime(timezone=True))` —
  TIMESTAMPTZ — y devuelven datetimes TZ-aware al consultarlas. Si el
  código Python compara o resta esos valores contra `datetime.utcnow()`
  (que es naive), Python lanza:

      TypeError: can't subtract offset-naive and offset-aware datetimes

  En SQLite (los tests) eso no se nota porque el driver no impone TZ
  awareness; el bug solo aparece en producción. Eso fue el 500 reportado
  en la papelera el 2026-04-25.

  Adicionalmente, `datetime.utcnow()` está deprecado a partir de Python
  3.12 — la recomendación oficial es `datetime.now(timezone.utc)`.

Uso recomendado en todo el proyecto:

    from app.core.tz import ahora_utc

    ahora = ahora_utc()                       # TZ-aware UTC
    desde = ahora - timedelta(days=30)        # TZ-aware
    glosa.fecha_decision_eps = ahora_utc()    # safe contra TIMESTAMPTZ

Y para defenderse de datos legacy que quedaron naive:

    from app.core.tz import a_utc
    eliminado_en = a_utc(r.eliminado_en)      # convierte naive→UTC, deja
                                              # TZ-aware igual.
"""
from __future__ import annotations

from datetime import datetime, timezone


def ahora_utc() -> datetime:
    """Datetime actual TZ-aware en UTC. Reemplazo de datetime.utcnow()."""
    return datetime.now(timezone.utc)


def a_utc(dt: datetime | None) -> datetime | None:
    """Asegura que un datetime sea TZ-aware (lo asume UTC si es naive).

    - None         → None
    - naive        → mismo valor con tzinfo=UTC
    - TZ-aware     → sin modificar
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
