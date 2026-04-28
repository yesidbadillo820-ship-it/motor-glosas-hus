"""Tests para app.services.dictamen_stale.

La detección por texto del dictamen es la pieza clave: dictámenes generados
antes de cargar contratos/tarifarios no tienen `dictamen_generado_en` y se
quedarían silenciosamente obsoletos sin esta detección.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

# El módulo importa lazy de sqlalchemy/app.models.db; saltamos los tests que
# requieren BD real cuando sqlalchemy no está instalado.
sqlalchemy = pytest.importorskip("sqlalchemy")  # noqa: F841

from app.services.dictamen_stale import (  # noqa: E402
    _texto_dictamen_normalizado,
    motivo_stale,
)


class _StubQuery:
    """Stub mínimo para emular .filter().limit().all() y .filter().filter().limit().all()."""
    def __init__(self, resultado):
        self._res = resultado

    def filter(self, *_a, **_kw):
        return self

    def limit(self, _n):
        return self

    def all(self):
        return self._res


class _StubDB:
    def __init__(self, tarifas):
        self._tarifas = tarifas

    def query(self, _model):
        return _StubQuery(self._tarifas)


def _glosa(dictamen: str, eps: str = "DISPENSARIO MEDICO BUCARAMANGA",
           generado: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=1, eps=eps, dictamen=dictamen, dictamen_generado_en=generado
    )


def _tarifa(eps: str, creado_en: datetime | None = None):
    return SimpleNamespace(
        eps=eps, activa=1,
        creado_en=creado_en or datetime(2026, 4, 28, tzinfo=timezone.utc),
    )


class TestTextoNormalizado:
    def test_quita_html(self):
        assert "PUNCION" in _texto_dictamen_normalizado("<p>Punción</p>")

    def test_colapsa_espacios(self):
        assert _texto_dictamen_normalizado("  hola\n  mundo  ") == "HOLA MUNDO"


class TestDetectaPorTexto:
    """Caso real: glosa #2511 / #2513 con dictamen viejo que dice 'no existe
    contrato' aunque el DMBUG ya está cargado."""

    def test_no_existe_contrato_con_tarifa_existente_es_stale(self):
        glosa = _glosa(
            "ESE HUS NO ACEPTA. NO EXISTE CONTRATO PACTADO ENTRE LAS PARTES.",
            generado=None,  # legado, sin timestamp
        )
        db = _StubDB([_tarifa("DISPENSARIO MEDICO DMBUG")])
        msg = motivo_stale(glosa, db)
        assert msg is not None
        assert "no" in msg.lower() and "contrato" in msg.lower()

    def test_no_existe_contrato_sin_tarifas_no_es_stale(self):
        # Si la EPS realmente no tiene contrato cargado, el dictamen es válido.
        glosa = _glosa("NO EXISTE CONTRATO PACTADO ENTRE LAS PARTES.")
        db = _StubDB([])  # sin tarifas
        assert motivo_stale(glosa, db) is None

    def test_dictamen_correcto_no_es_stale(self):
        glosa = _glosa(
            "ESE HUS DEFIENDE CONFORME A LA TARIFA PACTADA EN EL CONTRATO."
        )
        db = _StubDB([_tarifa("DISPENSARIO MEDICO")])
        assert motivo_stale(glosa, db) is None

    def test_dictamen_vacio_no_es_stale(self):
        glosa = _glosa("", generado=datetime(2020, 1, 1, tzinfo=timezone.utc))
        db = _StubDB([_tarifa("DISPENSARIO MEDICO")])
        assert motivo_stale(glosa, db) is None

    def test_eps_distinta_no_dispara_stale(self):
        glosa = _glosa(
            "NO EXISTE CONTRATO PACTADO.", eps="FAMISANAR EPS",
        )
        # Hay tarifa pero para otra EPS
        db = _StubDB([_tarifa("DISPENSARIO MEDICO")])
        assert motivo_stale(glosa, db) is None
