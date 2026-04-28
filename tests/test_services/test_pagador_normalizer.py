"""Tests para app.services.pagador_normalizer."""
from app.services.pagador_normalizer import (
    codigo,
    nombre_corto,
    nombre_largo,
    son_equivalentes,
)


class TestCodigo:
    def test_extrae_codigo_eps(self):
        assert codigo("U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO") == "U220311"

    def test_lowercase_se_normaliza(self):
        assert codigo("u220311 - dispensario") == "U220311"

    def test_sin_codigo_devuelve_vacio(self):
        assert codigo("DISPENSARIO MEDICO BUCARAMANGA") == ""

    def test_vacio(self):
        assert codigo("") == ""
        assert codigo(None) == ""


class TestNombreCorto:
    def test_quita_codigo_y_prefijo_direccion(self):
        entrada = "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG"
        assert nombre_corto(entrada) == "DISPENSARIO MEDICO BUCARAMANGA"

    def test_repara_truncamiento_bucaramang(self):
        assert nombre_corto("DISPENSARIO MEDICO BUCARAMANG") == "DISPENSARIO MEDICO BUCARAMANGA"

    def test_idempotente(self):
        once = nombre_corto("U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG")
        twice = nombre_corto(once)
        assert once == twice

    def test_sanidad_armada(self):
        assert nombre_corto("DIRECCION DE SANIDAD ARMADA - HOSPITAL NAVAL") == "HOSPITAL NAVAL"

    def test_sin_prefijos_pasa_intacto(self):
        assert nombre_corto("FAMISANAR EPS") == "FAMISANAR EPS"

    def test_colapsa_espacios(self):
        assert nombre_corto("  FAMISANAR    EPS  ") == "FAMISANAR EPS"

    def test_vacio(self):
        assert nombre_corto("") == ""
        assert nombre_corto(None) == ""


class TestNombreLargo:
    def test_con_codigo(self):
        entrada = "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG"
        assert nombre_largo(entrada) == "U220311 · DISPENSARIO MEDICO BUCARAMANGA"

    def test_sin_codigo(self):
        assert nombre_largo("FAMISANAR EPS") == "FAMISANAR EPS"


class TestSonEquivalentes:
    def test_mismo_pagador_distintas_grafias(self):
        plan = "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANG"
        corto = "DISPENSARIO MEDICO BUCARAMANGA"
        assert son_equivalentes(plan, corto)

    def test_distintos(self):
        assert not son_equivalentes("FAMISANAR EPS", "SANITAS EPS")

    def test_vacios(self):
        assert not son_equivalentes("", "FAMISANAR")
        assert not son_equivalentes("FAMISANAR", "")
