"""Tests del resolver de entidad/EPS (Ronda 36)."""
from __future__ import annotations

from app.services.resolver_entidad import (
    entidad_con_codigo,
    resolver_entidad_mostrar,
)


class TestEpsGenericos:
    def test_otra_sin_definir_usa_tercero(self):
        r = resolver_entidad_mostrar(
            eps="OTRA / SIN DEFINIR",
            tercero_nombre="FAMISANAR EPS SUBSIDIADO",
        )
        assert r == "FAMISANAR EPS SUBSIDIADO"

    def test_sin_nada_devuelve_sin_definir(self):
        assert resolver_entidad_mostrar(None, None, None) == "SIN DEFINIR"
        assert resolver_entidad_mostrar("", "", "") == "SIN DEFINIR"
        assert resolver_entidad_mostrar("OTRA / SIN DEFINIR", None, None) == "SIN DEFINIR"


class TestPrefijosTruncados:
    def test_dispensario_truncado_usa_tercero(self):
        """El Excel del DGH a veces trunca a 'DISPENSARIO MEDICO BUCARAMANG'
        (40 chars). El tercero_nombre trae el nombre completo."""
        r = resolver_entidad_mostrar(
            eps="DISPENSARIO MEDICO",
            tercero_nombre="SANIDAD MILITAR - DISPENSARIO MEDICO BUCARAMANGA",
        )
        assert "BUCARAMANGA" in r

    def test_direccion_sanidad_usa_tercero(self):
        r = resolver_entidad_mostrar(
            eps="DIRECCION DE SANIDAD",
            tercero_nombre="DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA",
        )
        assert "EJERCITO" in r


class TestPrefijoCodigo:
    def test_extrae_prefijo_embedido_en_eps(self):
        """Si eps viene como 'U220181 - FAMISANAR EPS SUBSIDIADO', separar."""
        r = resolver_entidad_mostrar(
            eps="U220181 - FAMISANAR EPS SUBSIDIADO",
            tercero_nombre=None,
        )
        # Debe devolver sin el prefijo
        assert "U220181" not in r
        assert "FAMISANAR EPS SUBSIDIADO" in r

    def test_entidad_con_codigo_reconstruye(self):
        r = entidad_con_codigo(
            eps="U220181 - FAMISANAR EPS SUBSIDIADO",
        )
        assert r == "U220181 - FAMISANAR EPS SUBSIDIADO"

    def test_entidad_con_codigo_arma_desde_partes(self):
        r = entidad_con_codigo(
            eps="OTRA / SIN DEFINIR",
            tercero_nombre="FAMISANAR EPS SUBSIDIADO",
            eps_codigo="U220181",
        )
        assert r == "U220181 - FAMISANAR EPS SUBSIDIADO"


class TestEpsBuenoRespetada:
    def test_eps_institucional_se_mantiene_si_tercero_vacio(self):
        r = resolver_entidad_mostrar(
            eps="FAMISANAR EPS",
            tercero_nombre=None,
        )
        assert r == "FAMISANAR EPS"

    def test_eps_y_tercero_iguales_devuelve_uno(self):
        r = resolver_entidad_mostrar(
            eps="FAMISANAR EPS",
            tercero_nombre="FAMISANAR EPS",
        )
        assert r == "FAMISANAR EPS"

    def test_caso_real_coosalud(self):
        r = resolver_entidad_mostrar(
            eps="COOSALUD ENTIDAD PROMOTORA DE SALUD",
            tercero_nombre="COOSALUD ENTIDAD PROMOTORA DE SALUD S.A.",
        )
        # tercero es más largo → usarlo
        assert r == "COOSALUD ENTIDAD PROMOTORA DE SALUD S.A."


class TestDefensivo:
    def test_none_inputs(self):
        assert resolver_entidad_mostrar(None, None, None) == "SIN DEFINIR"

    def test_espacios_extra(self):
        r = resolver_entidad_mostrar(
            eps="   FAMISANAR EPS   ",
            tercero_nombre="   ",
        )
        assert r == "FAMISANAR EPS"
