"""Cuando la glosa no es de la factura, no se contesta con la factura.

Segunda auditoria del lote del 25-08-2026. El auditor cruzo, codigo por
codigo, el motivo REAL del pagador contra lo que contesto el motor. De 79
codigos, 74 contestaban el tema — buen resultado. Los 5 que no
($3.564.600) fallaban todos igual:

  FA1606 (3 casos, $2.571.800): el pagador dice "el regimen del afiliado al
    momento de la prestacion (CONTRIBUTIVO) es diferente al registrado en el
    contrato (SUBSIDIADO)" y el motor contesta que la factura electronica es
    valida ante la DIAN.

  FA0703 (2 casos, $992.800): el pagador dice "insumo no facturable"
    nombrando el codigo del item, y el motor contesta lo mismo de la DIAN.

Ninguna de las dos es una glosa de la FORMA de la factura. En auditoria,
lo que no se refuta se descuenta: la entidad puede darlas por no
contestadas y ratificar el valor completo.

La red no reescribe el argumento —de eso se encarga la defensa central que
quedo en el catalogo de codigos—: AVISA, para que el gestor lo devuelva
antes de radicarlo.
"""

from app.services.catalogo_glosas import obtener_concepto
from app.services.glosa_service import _avisar_si_contesta_la_forma

SOLO_DIAN = (
    "ESE HUS NO ACEPTA GLOSA POR PRESUNTOS DEFECTOS FORMALES EN LA FACTURACIÓN. "
    "LA FACTURA FUE VALIDADA POR LA DIAN CON SU RESPECTIVO CUFE Y CUMPLE EL "
    "ARTÍCULO 617 DEL ESTATUTO TRIBUTARIO. SE SOLICITA EL LEVANTAMIENTO."
)


class TestAvisaCuandoContestaLaFactura:
    def test_fa1606_contestado_con_la_dian(self):
        salida = _avisar_si_contesta_la_forma(SOLO_DIAN, "FA1606")
        assert "REVISAR ANTES DE RADICAR" in salida
        assert "responsable de pago" in salida

    def test_fa0703_contestado_con_la_dian(self):
        salida = _avisar_si_contesta_la_forma(SOLO_DIAN, "FA0703")
        assert "REVISAR ANTES DE RADICAR" in salida
        assert "atención agrupada" in salida

    def test_el_aviso_no_borra_el_argumento(self):
        salida = _avisar_si_contesta_la_forma(SOLO_DIAN, "FA1606")
        assert "SE SOLICITA EL LEVANTAMIENTO" in salida


class TestNoAvisaCuandoSiEntroEnElTema:
    def test_fa1606_que_si_habla_del_regimen(self):
        texto = SOLO_DIAN + " LA CONSULTA BDUA A LA FECHA DE ATENCIÓN ACREDITA EL RÉGIMEN."
        assert "REVISAR ANTES" not in _avisar_si_contesta_la_forma(texto, "FA1606")

    def test_fa1606_que_nombra_la_verificacion_de_derechos(self):
        texto = SOLO_DIAN + " LA VERIFICACIÓN DE DERECHOS IDENTIFICA AL RESPONSABLE DEL PAGO."
        assert "REVISAR ANTES" not in _avisar_si_contesta_la_forma(texto, "FA1606")

    def test_fa0703_que_si_habla_del_paquete(self):
        texto = SOLO_DIAN + " EL ÍTEM NO ESTÁ INCLUIDO EN LA ATENCIÓN AGRUPADA SEGÚN EL ANEXO 1."
        assert "REVISAR ANTES" not in _avisar_si_contesta_la_forma(texto, "FA0703")

    def test_una_glosa_que_si_es_de_la_factura_no_se_avisa(self):
        """FA1601 y las demas de forma SI se contestan con la validez de la
        factura: la red no puede molestar ahi."""
        for codigo in ("FA1601", "TA0201", "SO0101", "CL0801"):
            assert "REVISAR ANTES" not in _avisar_si_contesta_la_forma(SOLO_DIAN, codigo), codigo

    def test_un_dictamen_que_ni_menciona_la_dian_no_se_avisa(self):
        texto = "ESE HUS NO ACEPTA GLOSA. EL SERVICIO FUE PRESTADO Y ESTÁ SOPORTADO."
        assert _avisar_si_contesta_la_forma(texto, "FA1606") == texto

    def test_sin_codigo_o_sin_texto_no_rompe(self):
        assert _avisar_si_contesta_la_forma("", "FA1606") == ""
        assert _avisar_si_contesta_la_forma(SOLO_DIAN, "") == SOLO_DIAN
        assert _avisar_si_contesta_la_forma(None, "FA1606") is None


class TestElCatalogoEnsenaLaDefensaCorrecta:
    def test_fa1606_manda_a_la_bdua_y_no_a_la_dian(self):
        d = obtener_concepto("FA1606")
        assert "BDUA" in d
        assert "FECHA DE LA ATENCIÓN" in d.upper()
        assert "DIAN" in d, "la advertencia de NO usar la DIAN debe estar escrita"

    def test_fa1606_se_apoya_en_el_articulo_11_que_es_el_verdadero(self):
        assert "Art. 11 del Decreto 4747 de 2007" in obtener_concepto("FA1606")
        assert "verificación de derechos" in obtener_concepto("FA1606")

    def test_fa1606_prohibe_afirmar_el_regimen_sin_soporte(self):
        assert "NO se afirma el régimen" in obtener_concepto("FA1606")

    def test_fa0703_manda_al_anexo_del_paquete(self):
        d = obtener_concepto("FA0703")
        assert "anexo del contrato" in d
        assert "no es medicamento ni APME" in d
