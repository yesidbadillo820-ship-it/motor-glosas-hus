"""Tests del inferidor de código canónico Res. 2284/2023 (Ronda 50 Paso 2).

Cuando el Excel DGH trae código interno Syscafe numérico ('423') y no
el canónico ('TA0201'), lo derivamos del nombre del concepto.
"""
from __future__ import annotations

from app.services.recepcion_service import _inferir_codigo_canonico


class TestInferirCodigo:
    def test_autorizacion(self):
        assert _inferir_codigo_canonico("AUTORIZACION - PROCEDIMIENTO O ACTIVIDAD") == "AU0101"

    def test_autorizacion_con_tilde(self):
        assert _inferir_codigo_canonico("AUTORIZACIÓN PREVIA NO HALLADA") == "AU0101"

    def test_tarifas(self):
        assert _inferir_codigo_canonico("TARIFAS - PROCEDIMIENTO O ACTIVIDAD") == "TA0201"

    def test_tarifa_singular(self):
        assert _inferir_codigo_canonico("Diferencia en TARIFA contratada") == "TA0201"

    def test_soportes(self):
        assert _inferir_codigo_canonico("SOPORTES - HISTORIA CLINICA NO ANEXADA") == "SO0101"

    def test_pertinencia(self):
        assert _inferir_codigo_canonico("PERTINENCIA MEDICA") == "PE0101"

    def test_cobertura(self):
        assert _inferir_codigo_canonico("COBERTURA - NO INCLUIDO EN POS") == "CO0101"

    def test_facturacion(self):
        assert _inferir_codigo_canonico("FACTURACION - SERVICIO NO DOCUMENTADO") == "FA0101"

    def test_calidad(self):
        assert _inferir_codigo_canonico("CALIDAD - PROCESO NO CUMPLIDO") == "CL0101"

    def test_no_reconocido(self):
        assert _inferir_codigo_canonico("TEXTO SIN PALABRA CLAVE") is None

    def test_vacio(self):
        assert _inferir_codigo_canonico("") is None
        assert _inferir_codigo_canonico(None) is None
