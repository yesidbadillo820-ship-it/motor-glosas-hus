"""Lo que no se contesta se ratifica.

PRUEBA 2 DE ESTRÉS (31-08-2026) — glosa CL4506, factura HUS0000601892,
NUEVA E.P.S. S.A. - SUBSIDIADO. El texto objetaba dos cosas:

  1. la pertinencia del doble sistema de fijación, y
  2. «ADICIONALMENTE EL VALOR UNITARIO DEL CLAVO SUPERA EL TOPE CONTRACTUAL».

El dictamen contestó la primera con tres párrafos de autonomía médica y de la
segunda no dijo una palabra. Esa parte de los $7.310.000 se pierde sin que
nadie la haya discutido.

La red no escribe el argumento que falta —inventarlo sería peor—: detecta que
la objeción quedó sin tocar y se la nombra al gestor.
"""

from app.services.glosa_service import _objeciones_sin_contestar

GLOSA_CL4506 = (
    "CL4506 | HUS0000601892 | NUEVA E.P.S. S.A. - SUBSIDIADO\n"
    "NO SE JUSTIFICA LA PERTINENCIA DEL MATERIAL DE OSTEOSINTESIS UTILIZADO.\n"
    "EL PACIENTE INGRESA CON DIAGNOSTICO S72.0 FRACTURA DEL CUELLO DE FEMUR.\n"
    "SE FACTURA CLAVO CEFALOMEDULAR Y ADICIONALMENTE PLACA DCP 4.5 CON 8 TORNILLOS.\n"
    "NO SE EVIDENCIA JUSTIFICACION DE AMBOS SISTEMAS DE FIJACION EN EL MISMO ACTO.\n"
    "ADICIONALMENTE EL VALOR UNITARIO DEL CLAVO SUPERA EL TOPE CONTRACTUAL.\n"
    "VALOR FACTURADO: $18.940.000  VALOR GLOSADO: $7.310.000"
)

# El dictamen tal como salió: pura autonomía médica.
DICTAMEN_SOLO_PERTINENCIA = (
    "ESE HUS NO ACEPTA GLOSA POR CONCEPTO DE PRESUNTA NO PERTINENCIA CLÍNICA "
    "DEL SERVICIO PRESTADO, DADO QUE LA PRESCRIPCIÓN Y EJECUCIÓN DEL SERVICIO "
    "OBEDECIÓ AL CRITERIO DEL MÉDICO TRATANTE EN EJERCICIO DE SU AUTONOMÍA "
    "PROFESIONAL, GARANTIZADA POR EL ARTÍCULO 17 DE LA LEY ESTATUTARIA 1751 "
    "DE 2015. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
)


class TestElCasoQueLoDestapo:
    def test_avisa_que_falto_la_objecion_de_tarifa(self):
        faltan = _objeciones_sin_contestar(GLOSA_CL4506, DICTAMEN_SOLO_PERTINENCIA)
        assert any("tope" in f or "mayor valor" in f for f in faltan), faltan

    def test_no_reclama_la_pertinencia_que_si_contesto(self):
        faltan = _objeciones_sin_contestar(GLOSA_CL4506, DICTAMEN_SOLO_PERTINENCIA)
        assert not any("pertinencia" in f for f in faltan), faltan

    def test_callada_cuando_el_dictamen_contesta_las_dos(self):
        completo = DICTAMEN_SOLO_PERTINENCIA + (
            " EN CUANTO AL MAYOR VALOR UNITARIO ALEGADO, LA TARIFA APLICADA "
            "CORRESPONDE AL TOPE PACTADO Y NO PROCEDE MODIFICARLA "
            "UNILATERALMENTE EN VÍA DE GLOSA."
        )
        assert _objeciones_sin_contestar(GLOSA_CL4506, completo) == []


class TestNoMolestaCuandoHayUnaSolaObjecion:
    def test_glosa_de_una_sola_cosa_no_dispara(self):
        glosa = "TA0301 SE RECONOCE TARIFA SOAT UVB. VALOR GLOSADO: $1.254.000"
        dictamen = "LA TARIFA PACTADA NO SE MODIFICA UNILATERALMENTE."
        assert _objeciones_sin_contestar(glosa, dictamen) == []

    def test_sin_conector_no_se_cuentan_dos(self):
        """Nombrar la historia clínica de paso no es una segunda objeción."""
        glosa = (
            "SE OBJETA EL VALOR UNITARIO QUE SUPERA EL TOPE CONTRACTUAL "
            "SEGUN LA HISTORIA CLINICA APORTADA."
        )
        assert _objeciones_sin_contestar(glosa, "TARIFA PACTADA.") == []

    def test_texto_vacio_no_rompe(self):
        assert _objeciones_sin_contestar("", "algo") == []
        assert _objeciones_sin_contestar("algo", "") == []
        assert _objeciones_sin_contestar("", "") == []


class TestOtrasCombinacionesReales:
    def test_soportes_mas_autorizacion(self):
        glosa = (
            "SO0102 NO SE EVIDENCIA LA EPICRISIS DEL EGRESO. ADEMAS EL "
            "PROCEDIMIENTO CARECE DE AUTORIZACION PREVIA."
        )
        dictamen = "SE ANEXA LA HISTORIA CLINICA Y LOS SOPORTES DEL FOLIO 12."
        faltan = _objeciones_sin_contestar(glosa, dictamen)
        assert any("autoriza" in f for f in faltan), faltan

    def test_cuando_el_dictamen_toca_las_dos_no_avisa_nada(self):
        glosa = (
            "SO0102 NO SE EVIDENCIA LA EPICRISIS DEL EGRESO. ADEMAS EL "
            "PROCEDIMIENTO CARECE DE AUTORIZACION PREVIA."
        )
        dictamen = (
            "SE ANEXA LA EPICRISIS DEL FOLIO 12. LA ATENCION FUE POR URGENCIA "
            "VITAL, EVENTO EXCEPTUADO DE AUTORIZACION PREVIA (ART. 67 LEY 715)."
        )
        assert _objeciones_sin_contestar(glosa, dictamen) == []


class TestLaReglaLlegoAlPrompt:
    def test_el_prompt_ordena_contestar_todas(self):
        import io

        prompts = io.open("app/services/glosa_ia_prompts.py", encoding="utf-8").read()
        assert "8.octodecies" in prompts
        assert "UNA GLOSA PUEDE TRAER DOS OBJECIONES" in prompts
        assert "UN PÁRRAFO PROPIO PARA CADA OBJECIÓN" in prompts
