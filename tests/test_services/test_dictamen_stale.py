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
    _matchea_eps,
    _texto_dictamen_normalizado,
    _tokens_significativos,
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
           generado: datetime | None = None,
           codigo_respuesta: str = "",
           codigo_glosa: str = "") -> SimpleNamespace:
    return SimpleNamespace(
        id=1, eps=eps, dictamen=dictamen, dictamen_generado_en=generado,
        codigo_respuesta=codigo_respuesta, codigo_glosa=codigo_glosa,
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


class TestMatcheaEps:
    """Matching permisivo por tokens — caso real DMBUG vs nombre del plan EPS."""

    def test_dispensario_bucaramanga_matchea_dmbug(self):
        # Glosa trae el plan EPS oficial; tarifa cargada con nombre comercial.
        assert _matchea_eps(
            "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG",
            "DISPENSARIO MEDICO DMBUG",
        )

    def test_fomag_matchea_fondo_magisterio(self):
        assert _matchea_eps("FOMAG", "FOMAG")
        assert _matchea_eps(
            "FONDO PRESTACIONES MAGISTERIO FOMAG", "FOMAG MAGISTERIO"
        )

    def test_eps_completamente_distintas_no_matchean(self):
        assert not _matchea_eps("FAMISANAR EPS", "SANITAS EPS")
        assert not _matchea_eps("NUEVA EPS", "COMPENSAR")

    def test_token_unico_no_basta(self):
        # Solo "EPS" en común no debería contar (es stopword)
        assert not _matchea_eps("FAMISANAR EPS", "OTRA COSA EPS")

    def test_sigla_unica_matchea_si_aparece_en_el_otro(self):
        # Tarifa cargada con un solo token significativo (sigla DMBUG)
        # matchea contra eps que contenga esa sigla en cualquier parte
        assert _matchea_eps(
            "DISPENSARIO MEDICO DMBUG BUCARAMANGA", "DMBUG"
        )
        assert _matchea_eps("FOMAG MAGISTERIO", "FOMAG")

    def test_tokens_significativos_filtra_stopwords(self):
        toks = _tokens_significativos("DIRECCION DE SANIDAD EJERCITO")
        assert "EJERCITO" in toks
        assert "DIRECCION" not in toks  # stopword


class TestReIncorrecto:
    """Caso real: glosas TA con RE9602 cuando hay contrato pactado.
    El código correcto sería RE9901 (defensa con subsanación contractual)."""

    def test_RE9602_con_contrato_es_stale(self):
        glosa = _glosa(
            "ESE HUS DEFIENDE LA TARIFA FACTURADA EN $100.000.",
            codigo_respuesta="RE9602",
            codigo_glosa="TA0201",
        )
        db = _StubDB([_tarifa("DISPENSARIO MEDICO DMBUG")])
        msg = motivo_stale(glosa, db)
        assert msg is not None
        assert "RE9602" in msg
        assert "RE9901" in msg

    def test_RE9602_sin_contrato_no_es_stale(self):
        # Sin contrato pactado, RE9602 es correcto.
        glosa = _glosa(
            "ESE HUS DEFIENDE.", codigo_respuesta="RE9602", codigo_glosa="TA0201",
        )
        db = _StubDB([])
        assert motivo_stale(glosa, db) is None

    def test_RE9602_glosa_no_TA_no_aplica(self):
        # El check de RE9602 incorrecto solo aplica para TA*. Otros tipos
        # pueden usar RE9602 legítimamente.
        glosa = _glosa(
            "ESE HUS DEFIENDE.", codigo_respuesta="RE9602", codigo_glosa="FA0203",
        )
        db = _StubDB([_tarifa("DISPENSARIO MEDICO")])
        assert motivo_stale(glosa, db) is None

    def test_RE9901_no_dispara_stale(self):
        # RE9901 es correcto cuando hay contrato, no debe marcarse stale.
        glosa = _glosa(
            "ESE HUS DEFIENDE CON CONTRATO PACTADO.",
            codigo_respuesta="RE9901", codigo_glosa="TA0201",
        )
        db = _StubDB([_tarifa("DISPENSARIO MEDICO")])
        assert motivo_stale(glosa, db) is None


class TestTerceroNombre:
    def test_match_via_tercero_cuando_eps_oficial_no_matchea(self):
        # eps oficial muy formal, tarifa cargada con el tercero comercial
        glosa = _glosa(
            "ESE HUS NO ACEPTA. NO EXISTE CONTRATO PACTADO ENTRE LAS PARTES.",
            eps="U220311 - DIRECCION DE SANIDAD EJERCITO",
        )
        # Ningún token significativo común con la tarifa
        # pero el tercero_nombre sí matchea
        glosa.tercero_nombre = "DISPENSARIO MEDICO BUCARAMANGA"
        db = _StubDB([_tarifa("DISPENSARIO MEDICO DMBUG")])
        assert motivo_stale(glosa, db) is not None
