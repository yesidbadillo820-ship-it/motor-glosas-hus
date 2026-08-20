"""El dictamen no puede certificar qué dice un documento que nadie abrió.

Caso real 20-08-2026. Yesid analizó en el portal una glosa de pertinencia
(CL0801, AXA COLPATRIA) **sin adjuntar un solo soporte**, y el dictamen salió
afirmando:

    «EL SERVICIO DE APOYO DIAGNÓSTICO FACTURADO CUMPLE CON LOS CRITERIOS
     CLÍNICOS DEL MÉDICO TRATANTE, QUIEN DOCUMENTÓ LA INDICACIÓN EN LA
     HISTORIA CLÍNICA INTEGRAL.»

Con medalla verde: «7 citas contra corpus · 0 hallazgos» y el sello «VALIDADO
POR QUALITY GATE». Como no cita ningún folio, el control de folios —que se
había puesto ese mismo día— la dejaba pasar limpia.

Es la misma mentira sin el número. En una glosa de pertinencia, lo que dice la
historia clínica ES el punto en disputa: la EPS la pide, ve que la afirmación
no sale de ahí, y ratifica la glosa completa.

La mitad más importante de estas pruebas es la de los FALSOS POSITIVOS: un
aviso equivocado en cada dictamen enseña al auditor a ignorar los avisos, y
entonces no sirve de nada haberlos puesto.
"""

from __future__ import annotations

from app.services.citation_verifier import verificar_citas
from app.services.extractor_folios import (
    afirmaciones_documentales_sin_respaldo,
    se_leyo_expediente,
)
from app.services.validador_dictamen import detectar_defectos_criticos

# El dictamen tal como salió en el portal.
CASO_YESID = (
    "EL SERVICIO DE APOYO DIAGNÓSTICO FACTURADO CUMPLE CON LOS CRITERIOS "
    "CLÍNICOS DEL MÉDICO TRATANTE, QUIEN DOCUMENTÓ LA INDICACIÓN EN LA "
    "HISTORIA CLÍNICA INTEGRAL."
)


def _issues(dictamen: str, evidencia):
    r = verificar_citas(dictamen, evidencia=evidencia)
    return r.get("issues", []) if isinstance(r, dict) else r


def _tipos(dictamen: str, evidencia):
    return [i["tipo"] for i in _issues(dictamen, evidencia)]


class TestLoQueSeInventa:
    def test_el_caso_de_yesid_queda_marcado(self):
        assert afirmaciones_documentales_sin_respaldo(CASO_YESID, "")

    def test_sin_tildes_tambien(self):
        """Muchos dictámenes salen en mayúsculas y pierden los acentos."""
        sin_tildes = (
            "CUMPLE CON LOS CRITERIOS CLINICOS DEL MEDICO TRATANTE, QUIEN "
            "DOCUMENTO LA INDICACION EN LA HISTORIA CLINICA INTEGRAL."
        )
        assert afirmaciones_documentales_sin_respaldo(sin_tildes, "")

    def test_otras_formas_de_afirmar_contenido(self):
        for frase in (
            "SEGÚN CONSTA EN LA HISTORIA CLÍNICA DEL PACIENTE.",
            "LA HISTORIA CLÍNICA ACREDITA LA PERTINENCIA DEL PROCEDIMIENTO.",
            "LA EPICRISIS REGISTRA LA EVOLUCIÓN FAVORABLE DEL PACIENTE.",
            "LA DESCRIPCIÓN QUIRÚRGICA DESCRIBE EL PROCEDIMIENTO REALIZADO.",
            "SE EVIDENCIA EN LA HOJA DE ADMINISTRACIÓN DE MEDICAMENTOS.",
            "EL REGISTRO DE ENFERMERÍA DEJA CONSTANCIA DEL SUMINISTRO.",
        ):
            assert afirmaciones_documentales_sin_respaldo(frase, ""), f"no marcó: {frase}"

    def test_la_frase_se_devuelve_para_que_el_auditor_la_vea(self):
        """No basta con avisar: hay que mostrar QUÉ frase sobra."""
        hallazgos = afirmaciones_documentales_sin_respaldo(CASO_YESID, "")
        assert "HISTORIA CLÍNICA" in hallazgos[0]


class TestLosFalsosPositivos:
    """La mitad que de verdad importa."""

    def test_ofrecer_un_documento_no_es_afirmar_su_contenido(self):
        for frase in (
            "SE ANEXA LA HISTORIA CLÍNICA COMPLETA DEL PACIENTE.",
            "LA HISTORIA CLÍNICA ESTÁ A DISPOSICIÓN DE LA EPS.",
            "SE REMITE LA EPICRISIS JUNTO CON LA PRESENTE RESPUESTA.",
            "OBRA EN EL EXPEDIENTE LA DESCRIPCIÓN QUIRÚRGICA.",
        ):
            assert not afirmaciones_documentales_sin_respaldo(frase, ""), f"marcó de más: {frase}"

    def test_hablar_de_la_norma_no_es_afirmar_contenido(self):
        frase = (
            "LA HISTORIA CLÍNICA ES EL SOPORTE EXIGIDO POR LA RESOLUCIÓN 2284 "
            "DE 2023 Y LA RESOLUCIÓN 1995 DE 1999."
        )
        assert not afirmaciones_documentales_sin_respaldo(frase, "")

    def test_reprochar_a_la_eps_no_es_afirmar_contenido(self):
        frase = "LA EPS NO PRECISÓ QUÉ SOPORTE ECHA DE MENOS NI EN QUÉ DOCUMENTO."
        assert not afirmaciones_documentales_sin_respaldo(frase, "")

    def test_el_documento_como_sustantivo_no_es_un_verbo(self):
        """«EL DOCUMENTO DE LA HISTORIA CLÍNICA» no afirma nada."""
        frase = "SE APORTA EL DOCUMENTO DE LA HISTORIA CLÍNICA Y LA FACTURA."
        assert not afirmaciones_documentales_sin_respaldo(frase, "")

    def test_con_soportes_leidos_la_verificacion_se_abstiene(self):
        """Con expediente a la vista haría falta leerlo de verdad para saber
        si la frase es fiel. Marcar por las dudas es peor que no marcar."""
        evidencia = "HISTORIA CLÍNICA folio 12: paciente con dolor torácico, se ordena TAC."
        assert not afirmaciones_documentales_sin_respaldo(CASO_YESID, evidencia)

    def test_se_reconoce_un_expediente_leido(self):
        assert se_leyo_expediente("HISTORIA CLÍNICA del paciente, folio 3")
        assert se_leyo_expediente("═══ SOPORTE AUTO: epicrisis.pdf ═══")
        assert not se_leyo_expediente("")
        assert not se_leyo_expediente("   ")


class TestLoQueVeElAuditorEnPantalla:
    def test_sale_como_hallazgo_grave(self):
        issues = _issues(CASO_YESID, "")
        propios = [i for i in issues if i["tipo"] == "AFIRMACION_SIN_SOPORTE"]
        assert propios, "no salió el aviso en pantalla"
        assert propios[0]["severidad"] == "ALTA"

    def test_el_aviso_se_explica_en_español_claro(self):
        issue = [i for i in _issues(CASO_YESID, "") if i["tipo"] == "AFIRMACION_SIN_SOPORTE"][0]
        assert "no se leyó ningún soporte" in issue["detalle"].lower()
        assert issue["sugerencia"]

    def test_con_soportes_no_sale_el_aviso(self):
        evidencia = "HISTORIA CLÍNICA folio 12: paciente con dolor torácico, se ordena TAC."
        assert "AFIRMACION_SIN_SOPORTE" not in _tipos(CASO_YESID, evidencia)

    def test_sin_evidencia_declarada_no_se_inventa_un_fallo(self):
        """`None` significa que el llamador no aportó el dato: no se revisa."""
        assert "AFIRMACION_SIN_SOPORTE" not in _tipos(CASO_YESID, None)


class TestLaIaSeCorrigeSola:
    """Antes de que el auditor lo vea, se le devuelve a la IA."""

    def _dictamen(self, cuerpo: str) -> str:
        return (
            "<argumento>ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE "
            "PERTINENCIA CLÍNICA DEL APOYO DIAGNÓSTICO FACTURADO EN LA ATENCIÓN "
            f"DEL USUARIO. {cuerpo} POR LO ANTERIOR SE SOLICITA EL LEVANTAMIENTO "
            "DE LA GLOSA Y EL PAGO ÍNTEGRO DE LO FACTURADO.</argumento>"
        )

    def test_entra_como_defecto_critico_y_dispara_reintento(self):
        defectos = detectar_defectos_criticos(
            self._dictamen(CASO_YESID),
            codigo_glosa="CL0801",
            evidencia="",
        )
        assert any(d["regla"] == "afirmacion_sin_soporte" for d in defectos)

    def test_con_soportes_no_hay_reintento_por_esto(self):
        defectos = detectar_defectos_criticos(
            self._dictamen(CASO_YESID),
            codigo_glosa="CL0801",
            evidencia="HISTORIA CLÍNICA folio 12: dolor torácico, se ordena TAC.",
        )
        assert not any(d["regla"] == "afirmacion_sin_soporte" for d in defectos)

    def test_el_consejo_no_manda_a_inventar_otra_cosa(self):
        """El consejo del folio decía «escribe LA HISTORIA CLÍNICA ACREDITA…».
        Sin soportes leídos eso es cambiar una invención por otra."""
        defectos = detectar_defectos_criticos(
            self._dictamen("SEGÚN CONSTA EN EL FOLIO 25 DE LA HISTORIA CLÍNICA."),
            codigo_glosa="CL0801",
            evidencia="",
        )
        folio = [d for d in defectos if d["regla"] == "folio_inventado"]
        assert folio, "el control de folios dejó de operar"
        assert "ACREDITA" not in folio[0]["sugerencia"].upper(), (
            "sin soportes leídos, el consejo no puede mandar a afirmar qué dice la historia clínica"
        )

    def test_con_soportes_el_consejo_del_folio_sigue_siendo_el_util(self):
        defectos = detectar_defectos_criticos(
            self._dictamen("SEGÚN CONSTA EN EL FOLIO 25 DE LA HISTORIA CLÍNICA."),
            codigo_glosa="CL0801",
            evidencia="HISTORIA CLÍNICA folio 12: dolor torácico.",
        )
        folio = [d for d in defectos if d["regla"] == "folio_inventado"]
        assert folio and "ACREDITA" in folio[0]["sugerencia"].upper()
