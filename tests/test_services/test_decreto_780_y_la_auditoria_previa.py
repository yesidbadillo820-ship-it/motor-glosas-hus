"""El Decreto 780 tenia otro articulo inventado, y la norma buena era otra.

25-08-2026, siguiendo el repaso que pidio el area despues de lo del Decreto
4747. El corpus tenia cargado esto:

    Decreto 780 de 2016, art. 2.5.3.4.1.1 — "Prohibicion de auditoria previa
    como barrera": «No podra establecerse la auditoria previa como barrera
    para la radicacion de facturas...»

Verificado contra el Decreto 441 de 2022, que es la norma que agrego ese
capitulo al Decreto 780: **el 2.5.3.4.1.1 es el "Objeto" del capitulo** y no
dice nada de auditoria previa. El texto estaba inventado.

Pero la prohibicion SI existe — y es un argumento fuerte para el hospital.
Vive en el **articulo 5 de la Resolucion 2284 de 2023**, que ademas llama a
esa practica por su nombre: «actuaciones que se consideran practicas
dilatorias no autorizadas».

O sea que el motor tenia el argumento correcto colgado de la norma
equivocada. Si la entidad iba a verificar la cita, no la encontraba.
"""

from app.services.normativa_completa import _TODAS_LAS_NORMAS as NORMAS

D780 = NORMAS["DECRETO 780 DE 2016"]["articulos"]
R2284 = NORMAS["RESOLUCION 2284 DE 2023"]["articulos"]


class TestElArticuloDelDecreto780:
    def test_el_2_5_3_4_1_1_es_el_objeto_del_capitulo(self):
        assert D780["2.5.3.4.1.1"]["titulo"] == "Objeto"
        assert "acuerdos de voluntades" in D780["2.5.3.4.1.1"]["texto"]

    def test_ya_no_dice_que_prohibe_la_auditoria_previa(self):
        art = D780["2.5.3.4.1.1"]
        assert "auditoría previa" not in art["texto"].lower()
        assert "Prohibición de auditoría previa" not in art["titulo"]

    def test_manda_a_la_norma_correcta(self):
        assert "Resolución 2284 de 2023" in D780["2.5.3.4.1.1"]["aplicacion"]

    def test_se_cargo_el_articulo_de_auditoria_de_cuentas(self):
        art = D780["2.5.3.4.3.3"]
        assert art["titulo"] == "Auditoría de cuentas médicas"
        assert "Manual Único de Devoluciones" in art["texto"]
        assert "artículo 57 de la Ley 1438 de 2011" in art["texto"]

    def test_queda_constancia_de_contra_que_se_verifico(self):
        assert "Decreto 441 de 2022" in NORMAS["DECRETO 780 DE 2016"]["verificada"]


class TestLaProhibicionDeAuditoriaPrevia:
    """El argumento que el hospital sí puede usar, ahora colgado de su norma."""

    def test_esta_en_el_articulo_5_de_la_2284(self):
        assert "5" in R2284
        assert R2284["5"]["titulo"] == "Auditoría de cuentas médicas"

    def test_trae_la_prohibicion_con_sus_palabras(self):
        texto = R2284["5"]["texto"]
        assert "no podrán exigir" in texto
        assert "mallas validadoras propias" in texto
        assert "prácticas dilatorias no autorizadas" in texto

    def test_dice_a_quien_le_toca_auditar(self):
        assert "Corresponde a las entidades responsables de pago" in R2284["5"]["texto"]

    def test_avisa_como_se_debe_citar(self):
        aplic = R2284["5"]["aplicacion"]
        assert "Res. 2284 de 2023" in aplic
        assert "no como artículo del Decreto 780" in aplic

    def test_queda_constancia_de_la_verificacion(self):
        assert NORMAS["RESOLUCION 2284 DE 2023"]["verificada"]


class TestLey1438ArticulosCorregidos:
    """Del mismo repaso salieron tres articulos mal en la Ley 1438.

    Verificados contra el texto oficial del normograma de la SuperSalud:

        Art.  56 decia "Tramite de pagos"                     -> "Pagos a los
                 prestadores de servicios de salud" (y el texto guardado
                 hablaba de pagar "el monto total dentro de los treinta dias",
                 que no esta en la ley)
        Art. 105 decia "Prohibicion de intromision en el acto medico" ->
                 "Autonomia profesional" (texto tambien inventado)
        Art. 126 decia "Supervision, inspeccion y vigilancia" -> "Funcion
                 jurisdiccional de la Superintendencia Nacional de Salud"

    Y el 56 traia un argumento que el motor no estaba usando: la prohibicion
    de exigir auditoria previa para RECIBIR la factura. Es de rango de ley —
    mas fuerte que la resolucion a la que se venia acudiendo.
    """

    L1438 = NORMAS["LEY 1438 DE 2011"]["articulos"]

    def test_el_56_se_llama_como_se_llama(self):
        assert self.L1438["56"]["titulo"] == "Pagos a los prestadores de servicios de salud"

    def test_el_56_trae_la_prohibicion_de_auditoria_previa(self):
        texto = self.L1438["56"]["texto"]
        assert (
            "Se prohíbe el establecimiento de la obligatoriedad de procesos de auditoría previa"
            in texto
        )
        assert "cualquier práctica tendiente a impedir la recepción" in texto

    def test_el_56_ya_no_afirma_un_plazo_de_treinta_dias(self):
        """El artículo remite los plazos al Gobierno Nacional y a la Ley 1122;
        no dice treinta días. Afirmarlo era darle a la entidad una cita fácil
        de desmentir."""
        assert "treinta (30)" not in self.L1438["56"]["texto"]
        assert "NO afirmar «treinta días»" in self.L1438["56"]["aplicacion"]

    def test_el_105_es_autonomia_profesional(self):
        art = self.L1438["105"]
        assert art["titulo"] == "Autonomía profesional"
        assert "emitir con toda libertad su opinión profesional" in art["texto"]

    def test_el_105_ya_no_le_atribuye_a_la_ley_lo_que_no_dice(self):
        art = self.L1438["105"]
        assert "no podrán interferir" not in art["texto"]
        assert "no está en el artículo" in art["aplicacion"]

    def test_el_126_es_la_funcion_jurisdiccional(self):
        assert self.L1438["126"]["titulo"] == (
            "Función jurisdiccional de la Superintendencia Nacional de Salud"
        )
