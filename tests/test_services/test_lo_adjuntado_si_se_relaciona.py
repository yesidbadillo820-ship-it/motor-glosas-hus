"""Los PDF que el gestor adjunta también son soportes aportados.

PRUEBA 2 DE ESTRÉS (31-08-2026), segunda corrida. El auditor adjuntó dos PDF,
la confianza subió de 47 % a 61 % «por tener soportes»… y el dictamen que se
radica no relacionó ninguno.

La relación de soportes solo sabía leer el índice del servidor de radicación,
por número de factura. Lo que se acaba de adjuntar no lo miraba nadie — y en
esa corrida el N° Factura iba vacío, así que el bloque desapareció entero.
"""

from app.services.glosa_service import GlosaService

# El armador exige un cuerpo con sustancia: un argumento corto aborta.
ARGUMENTO = (
    "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE PRESUNTA NO PERTINENCIA "
    "CLINICA DEL SERVICIO PRESTADO, DADO QUE LA PRESCRIPCION OBEDECIO AL "
    "CRITERIO DEL MEDICO TRATANTE EN EJERCICIO DE SU AUTONOMIA PROFESIONAL, "
    "GARANTIZADA POR EL ARTICULO 17 DE LA LEY ESTATUTARIA 1751 DE 2015. SE "
    "SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO INTEGRO DE LO FACTURADO."
)

CONTEXTO = (
    "═══ DOCUMENTO: nota_operatoria_HUS0000601892.pdf ═══\n\n"
    "DESCRIPCIÓN QUIRÚRGICA. FRACTURA CUELLO DE FÉMUR...\n\n"
    "═══ DOCUMENTO: epicrisis.pdf ═══\n\n"
    "PACIENTE DE 78 AÑOS...\n"
)


class TestSacaLosNombresDeLoAdjuntado:
    def test_los_encuentra_en_orden(self):
        assert GlosaService._documentos_adjuntos(CONTEXTO) == [
            "nota_operatoria_HUS0000601892.pdf",
            "epicrisis.pdf",
        ]

    def test_no_repite_si_el_documento_aparece_dos_veces(self):
        doble = CONTEXTO + "═══ DOCUMENTO: epicrisis.pdf ═══\n\nsigue...\n"
        assert GlosaService._documentos_adjuntos(doble).count("epicrisis.pdf") == 1

    def test_sin_contexto_no_inventa_nada(self):
        assert GlosaService._documentos_adjuntos("") == []
        assert GlosaService._documentos_adjuntos(None) == []

    def test_texto_sin_marcas_no_devuelve_nada(self):
        assert GlosaService._documentos_adjuntos("HISTORIA CLINICA DEL PACIENTE") == []

    def test_no_pasa_de_diez(self):
        muchos = "".join(f"═══ DOCUMENTO: s{i}.pdf ═══\ntexto\n" for i in range(20))
        assert len(GlosaService._documentos_adjuntos(muchos)) == 10


class TestElDictamenLosRelaciona:
    def _html(self, **kw):
        svc = GlosaService.__new__(GlosaService)
        return svc._generar_dictamen_html(
            "CL4506",
            "$ 7.310.000",
            "RE9901",
            "GLOSA NO ACEPTADA",
            ARGUMENTO,
            "NUEVA EPS",
            "CL",
            **kw,
        )

    def test_aparecen_los_nombres_de_los_pdf(self):
        html = self._html(adjuntos=["nota_operatoria.pdf", "epicrisis.pdf"])
        assert "DOCUMENTOS ANEXOS A ESTA RESPUESTA" in html
        assert "nota_operatoria.pdf" in html
        assert "epicrisis.pdf" in html

    def test_no_afirma_que_obren_en_el_expediente(self):
        """Eso lo verifica el índice, y en este camino no se verificó.

        31-08-2026: el texto de la nota cambió al sacar el bloque de la rama
        del índice. Lo que la prueba vigila NO cambió —que el escrito no
        afirme que lo adjuntado obra en el expediente institucional— así que
        se ancla en la afirmación, no en la redacción exacta.
        """
        html = self._html(adjuntos=["nota_operatoria.pdf"])
        assert "RELACIÓN DE SOPORTES APORTADOS" not in html
        assert "obran en el expediente" not in html.lower()
        assert "índice del servidor de radicación" in html

    def test_sin_adjuntos_no_pinta_la_tabla(self):
        html = self._html(adjuntos=[])
        assert "DOCUMENTOS ANEXOS A ESTA RESPUESTA" not in html

    def test_sin_adjuntos_ni_expediente_sigue_el_aviso_de_siempre(self):
        html = self._html(numero_factura="HUS0000601892", adjuntos=None)
        assert "RELACIÓN DE SOPORTES — POR VERIFICAR" in html


class TestEstaCableado:
    def test_el_flujo_le_pasa_los_adjuntos_al_recuadro(self):
        import io

        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert "adjuntos=self._documentos_adjuntos(contexto_pdf)" in motor, (
            "el recuadro dejó de recibir lo que el gestor adjuntó"
        )
