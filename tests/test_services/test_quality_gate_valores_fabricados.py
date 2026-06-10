"""Tests del detector "valores y contratos fabricados" del post-validator.

Regresión del dictamen real del 10-jun-2026: el gestor pegó "Se glosa por
falta de cobertura" sin valor objetado ni número de contrato, y la IA
generó un dictamen con "$ 1.200.000" y "CONTRATO S-13-1-03-1-04958"
inventados — ambos verificables al instante por la EPS.

Los nuevos checks `check_valores_no_fabricados` y `check_contratos_no_fabricados`
exigen que TODA cifra monetaria y TODO número de contrato en el dictamen
aparezcan también en el input del gestor (o en las cláusulas reales
inyectadas al prompt).
"""

from __future__ import annotations

from app.services.quality_gate.post_validator import (
    check_contratos_no_fabricados,
    check_valores_no_fabricados,
    post_validar_dictamen,
)


class TestValoresFabricados:
    def test_valor_inventado_detectado(self):
        # Bug real: input sin valor → IA inventó "$ 1.200.000"
        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA POR UN VALOR DE $1.200.000 CONFORME AL CONTRATO. "
            "SE SOLICITA EL LEVANTAMIENTO."
        )
        r = check_valores_no_fabricados(
            texto_dictamen=dictamen,
            texto_glosa_input="Se glosa por falta de cobertura",
            valor_objetado_input=None,
        )
        assert not r.ok
        assert r.severidad == "ERROR"
        assert "1.200.000" in r.razon or "1200000" in r.razon.replace(".", "")

    def test_valor_presente_en_input_no_se_marca(self):
        # Input dice "$1.500.000" y el dictamen lo reproduce → OK
        dictamen = "ESE HUS NO ACEPTA. POR VALOR DE $1.500.000. SE SOLICITA EL LEVANTAMIENTO."
        r = check_valores_no_fabricados(
            texto_dictamen=dictamen,
            texto_glosa_input="TA0201 mayor valor cobrado por $1.500.000 en factura",
            valor_objetado_input="1500000",
        )
        assert r.ok

    def test_valor_presente_solo_en_valor_objetado(self):
        # El input texto no dice la cifra, pero el formulario sí
        dictamen = "ESE HUS NO ACEPTA. POR VALOR DE $500.000. SE SOLICITA EL LEVANTAMIENTO."
        r = check_valores_no_fabricados(
            texto_dictamen=dictamen,
            texto_glosa_input="TA0201 mayor valor cobrado en consulta",
            valor_objetado_input="500000",
        )
        assert r.ok

    def test_cifras_de_normas_no_se_confunden_con_valores(self):
        # "Art. 168 de la Ley 100" no debe contar como valor monetario inventado
        dictamen = (
            "ESE HUS NO ACEPTA. Conforme al Art. 168 de la Ley 100 de 1993. "
            "SE SOLICITA EL LEVANTAMIENTO."
        )
        r = check_valores_no_fabricados(
            texto_dictamen=dictamen,
            texto_glosa_input="TA0201 mayor valor cobrado en consulta especializada",
        )
        assert r.ok  # no hay $N.NNN, solo "Art. 168"

    def test_input_none_no_se_evalua(self):
        # Si el caller no proveyó input, el check no aplica (silencioso OK)
        dictamen = "ESE HUS NO ACEPTA. POR $9.999.999. SE SOLICITA EL LEVANTAMIENTO."
        r = check_valores_no_fabricados(
            texto_dictamen=dictamen, texto_glosa_input=None, valor_objetado_input=None
        )
        # No hay fuente — todos los valores se ven "fabricados"
        assert not r.ok


class TestContratosFabricados:
    def test_contrato_inventado_detectado(self):
        # Bug real: IA citó "CONTRATO S-13-1-03-1-04958" sin que el gestor lo mencionara
        dictamen = (
            "ESE HUS NO ACEPTA. CONFORME AL CONTRATO S-13-1-03-1-04958 VIGENTE. "
            "SE SOLICITA EL LEVANTAMIENTO."
        )
        r = check_contratos_no_fabricados(
            texto_dictamen=dictamen,
            texto_glosa_input="Se glosa por falta de cobertura",
        )
        assert not r.ok
        assert "S-13-1-03-1-04958" in r.razon

    def test_contrato_en_input_no_se_marca(self):
        dictamen = (
            "ESE HUS NO ACEPTA. SEGÚN CONTRATO 440-DIGSA/DMBUG-2025. SE SOLICITA EL LEVANTAMIENTO."
        )
        r = check_contratos_no_fabricados(
            texto_dictamen=dictamen,
            texto_glosa_input="TA0201 según contrato 440-DIGSA/DMBUG-2025 con dispensario",
        )
        assert r.ok

    def test_contrato_en_clausulas_reales_no_se_marca(self):
        dictamen = (
            "ESE HUS NO ACEPTA. SEGÚN CONTRATO 440-DIGSA/DMBUG-2025. SE SOLICITA EL LEVANTAMIENTO."
        )
        r = check_contratos_no_fabricados(
            texto_dictamen=dictamen,
            texto_glosa_input="TA0201 mayor valor cobrado",
            clausulas_contrato=[
                {
                    "numero_contrato": "440-DIGSA/DMBUG-2025",
                    "texto_literal": "Cláusula primera del 440-DIGSA/DMBUG-2025",
                    "titulo": "OBJETO",
                }
            ],
        )
        assert r.ok

    def test_dictamen_sin_contratos_pasa(self):
        dictamen = "ESE HUS NO ACEPTA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO."
        r = check_contratos_no_fabricados(
            texto_dictamen=dictamen,
            texto_glosa_input="cualquier cosa",
        )
        assert r.ok


class TestPostValidarDictamenIntegracion:
    """Verifica que post_validar_dictamen agregue los 2 checks nuevos
    cuando el caller pasa texto_glosa_input, y los omita cuando no.
    """

    DICTAMEN_LIMPIO = (
        "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE MAYOR VALOR COBRADO. " * 5
        + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO."
    )
    DICTAMEN_CON_VALOR_FABRICADO = (
        "ESE HUS NO ACEPTA POR $9.876.543. " * 3 + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
    )

    def test_legacy_sin_input_no_agrega_checks_nuevos(self):
        r = post_validar_dictamen(self.DICTAMEN_LIMPIO)
        assert "valores_fabricados" not in r.checks
        assert "contratos_fabricados" not in r.checks

    def test_con_input_agrega_los_2_checks(self):
        r = post_validar_dictamen(
            self.DICTAMEN_LIMPIO,
            texto_glosa_input="TA0201 mayor valor cobrado por $500.000 en factura electrónica",
            valor_objetado_input="500000",
        )
        assert "valores_fabricados" in r.checks
        assert "contratos_fabricados" in r.checks
        assert r.checks["valores_fabricados"].ok
        assert r.checks["contratos_fabricados"].ok

    def test_dictamen_con_valor_fabricado_falla_post(self):
        r = post_validar_dictamen(
            self.DICTAMEN_CON_VALOR_FABRICADO,
            texto_glosa_input="TA0201 mayor valor cobrado en consulta",
            valor_objetado_input="500000",
        )
        assert not r.checks["valores_fabricados"].ok
        assert not r.aprobado  # ERROR del check fabricado → no aprobado
