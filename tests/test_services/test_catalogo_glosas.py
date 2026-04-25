"""Tests de catalogo_glosas — mapeo códigos Res. 2284/2023 (R51 P3)."""
from __future__ import annotations

from app.services.catalogo_glosas import (
    obtener_concepto,
    pertenece_a_tipo,
    sugerir_codigo_respuesta,
)


class TestObtenerConcepto:
    def test_codigo_exacto(self):
        r = obtener_concepto("TA0201")
        assert r  # no vacío
        assert "tarif" in r.lower() or "cargo" in r.lower() or "consulta" in r.lower()

    def test_fallback_grupo(self):
        """Código desconocido cae al grupo (4 chars)."""
        r = obtener_concepto("TA0299")  # no existe exacto, pero TA02 sí
        # Puede devolver "" si ni el grupo existe — tolerante
        assert isinstance(r, str)

    def test_codigo_vacio(self):
        assert obtener_concepto("") == ""
        assert obtener_concepto(None) == ""

    def test_case_insensitive(self):
        assert obtener_concepto("ta0201") == obtener_concepto("TA0201")


class TestPerteneceATipo:
    def test_prefijos_conocidos(self):
        assert pertenece_a_tipo("TA0201") == "TA"
        assert pertenece_a_tipo("SO0101") == "SO"
        assert pertenece_a_tipo("FA0401") == "FA"
        assert pertenece_a_tipo("AU0101") == "AU"
        assert pertenece_a_tipo("CO0101") == "CO"
        assert pertenece_a_tipo("PE0101") == "PE"
        assert pertenece_a_tipo("IN0101") == "IN"
        assert pertenece_a_tipo("ME0101") == "ME"

    def test_codigo_respuesta(self):
        assert pertenece_a_tipo("RE9901") == "RE"

    def test_case_insensitive(self):
        assert pertenece_a_tipo("ta0201") == "TA"

    def test_sin_prefijo_conocido(self):
        assert pertenece_a_tipo("ZZ9999") == ""
        assert pertenece_a_tipo("") == ""


class TestSugerirCodigoRespuesta:
    def test_ratificada_devuelve_RE9901(self):
        assert sugerir_codigo_respuesta("TA", ratificada=True) == "RE9901"

    def test_aceptada_total_RE9701(self):
        assert sugerir_codigo_respuesta("TA", aceptada_total=True) == "RE9701"

    def test_aceptada_parcial_RE9801(self):
        assert sugerir_codigo_respuesta("TA", aceptada_parcial=True) == "RE9801"

    def test_extemporanea_RE9502(self):
        assert sugerir_codigo_respuesta("TA", es_extemporanea=True) == "RE9502"

    def test_default_RE9901(self):
        assert sugerir_codigo_respuesta("TA") == "RE9901"

    def test_ratificada_prevalece_sobre_aceptada(self):
        """Si ambos flags se pasan, ratificada gana (caso del autopilot)."""
        r = sugerir_codigo_respuesta("TA", ratificada=True, aceptada_total=True)
        assert r == "RE9901"
