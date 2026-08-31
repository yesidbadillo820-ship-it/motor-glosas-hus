"""Contra una glosa quirúrgica manda la nota operatoria, no la Ley 1751.

PRUEBA 2 DE ESTRÉS (31-08-2026), glosa CL4506 · HUS0000601892 · NUEVA EPS.
Palabras del auditor: «escudarse en la autonomía médica sin justificar
clínicamente el uso de doble material (clavo + placa) y omitir por completo la
objeción del tope contractual garantiza que la EPS ratifique la glosa y el
hospital pierda el dinero».

Dos exigencias, y las dos ANTES de redactar (en el prompt), no solo después:

  1. Si la nota operatoria está entre los soportes, la defensa sale de ella
     —con folio y fecha— y la Ley 1751 queda como cierre.
  2. Si la glosa encadena una segunda objeción, va un párrafo propio para
     ella, resuelto con SU fundamento, no con el de la primera.
"""

import pytest

from app.services.glosa_ia_prompts import (
    FUNDAMENTO_POR_FAMILIA,
    build_user_prompt,
    exige_nota_operatoria,
    familias_de_objecion_en,
    objeciones_no_respondidas,
)
from app.services.glosa_service import _nota_operatoria_sin_citar

GLOSA = (
    "CL4506 | HUS0000601892 | NUEVA E.P.S. S.A. - SUBSIDIADO\n"
    "NO SE JUSTIFICA LA PERTINENCIA DEL MATERIAL DE OSTEOSINTESIS UTILIZADO.\n"
    "EL PACIENTE INGRESA CON DIAGNOSTICO S72.0 FRACTURA DEL CUELLO DE FEMUR.\n"
    "SE FACTURA CLAVO CEFALOMEDULAR Y ADICIONALMENTE PLACA DCP 4.5 CON 8 TORNILLOS.\n"
    "NO SE EVIDENCIA JUSTIFICACION DE AMBOS SISTEMAS DE FIJACION EN EL MISMO ACTO.\n"
    "ADICIONALMENTE EL VALOR UNITARIO DEL CLAVO SUPERA EL TOPE CONTRACTUAL.\n"
    "VALOR FACTURADO: $18.940.000  VALOR GLOSADO: $7.310.000"
)

PDF_CON_NOTA = (
    "═══ DOCUMENTO: nota_operatoria.pdf ═══\n"
    "NOTA OPERATORIA — Folio 14 — 22/05/2026 — Dr. J. Ramírez\n"
    "Fractura conminuta con extensión subtrocantérica; tras la fijación con "
    "clavo cefalomedular persiste inestabilidad rotacional del fragmento, por "
    "lo que se complementa con placa DCP 4.5."
)

# Sin nota entre lo aportado no se puede exigir que se cite.
PDF_SIN_NOTA = "═══ DOCUMENTO: epicrisis.pdf ═══\nEPICRISIS DE EGRESO — Folio 3"

DICTAMEN_SOLO_LEY = (
    "ESE HUS NO ACEPTA GLOSA POR PRESUNTA NO PERTINENCIA CLÍNICA. LA PRESCRIPCIÓN "
    "OBEDECIÓ AL CRITERIO DEL MÉDICO TRATANTE EN EJERCICIO DE SU AUTONOMÍA "
    "PROFESIONAL, GARANTIZADA POR EL ARTÍCULO 17 DE LA LEY 1751 DE 2015."
)


def _prompt() -> str:
    return build_user_prompt(
        texto_glosa=GLOSA,
        contexto_pdf=PDF_CON_NOTA,
        codigo="CL4506",
        eps="NUEVA EPS",
        numero_factura="HUS0000601892",
    )


class TestElPromptExigeLaNotaAntesDeRedactar:
    def test_le_prohibe_usar_la_plantilla_juridica_como_argumento_principal(self):
        assert "PROHIBIDO defender esta glosa con la plantilla juridica" in _prompt()

    def test_le_ordena_extraer_la_justificacion_del_cirujano(self):
        p = _prompt()
        assert "JUSTIFICACION CLINICA EXACTA del cirujano" in p
        assert "TRANSCRIBA lo que dice" in p

    def test_le_ordena_citar_folio_y_fecha(self):
        assert "CITE el folio y la fecha exactos" in _prompt()

    def test_la_ley_1751_queda_de_cierre(self):
        assert "Solo el cierre." in _prompt()

    def test_le_prohibe_inventar_el_folio(self):
        p = _prompt()
        assert "NUNCA invente un numero de folio" in p
        assert "Inventar una justificacion clinica es peor" in p

    def test_sin_nota_entre_los_soportes_no_exige_citarla(self):
        """Pedir que se cite lo que nadie entregó es pedir que se invente."""
        p = build_user_prompt(
            texto_glosa=GLOSA,
            contexto_pdf=PDF_SIN_NOTA,
            codigo="CL4506",
            eps="NUEVA EPS",
        )
        assert "PERTINENCIA QUIRURGICA" not in p


class TestElPromptExigeLaSegundaObjecion:
    def test_anuncia_las_dos_objeciones(self):
        p = _prompt()
        assert "ESTA GLOSA OBJETA MAS DE UNA COSA" in p
        assert "el mayor valor o el tope tarifario" in p

    def test_exige_un_parrafo_independiente_por_cada_una(self):
        assert "UN PARRAFO INDEPENDIENTE POR CADA UNA" in _prompt()

    def test_le_da_el_fundamento_propio_de_la_tarifa(self):
        p = _prompt()
        assert "PACTA SUNT SERVANDA" in p
        assert "un tope que no consta en el contrato no existe" in p

    def test_le_prohibe_resolverla_con_las_normas_de_la_primera(self):
        p = _prompt()
        assert "PROHIBIDO resolver la segunda con las normas de la primera" in p
        assert "PROHIBIDO" in p and "omitirla" in p

    def test_toda_familia_tiene_su_fundamento(self):
        for fam in familias_de_objecion_en(GLOSA):
            assert FUNDAMENTO_POR_FAMILIA.get(fam[0]), fam[0]


class TestLaRedAvisaSiAunAsiFalto:
    def test_avisa_cuando_el_dictamen_no_cita_la_nota(self):
        assert _nota_operatoria_sin_citar("CL4506", GLOSA, PDF_CON_NOTA, DICTAMEN_SOLO_LEY)

    def test_calla_cuando_si_la_cita(self):
        bueno = DICTAMEN_SOLO_LEY + (
            " CONFORME A LA NOTA OPERATORIA DEL FOLIO 14 DEL 22/05/2026, LA FRACTURA "
            "PRESENTABA CONMINUCIÓN CON EXTENSIÓN SUBTROCANTÉRICA."
        )
        assert not _nota_operatoria_sin_citar("CL4506", GLOSA, PDF_CON_NOTA, bueno)

    def test_calla_si_la_nota_no_fue_aportada(self):
        assert not _nota_operatoria_sin_citar("CL4506", GLOSA, PDF_SIN_NOTA, DICTAMEN_SOLO_LEY)

    @pytest.mark.parametrize("codigo", ["TA0301", "SO0102", "FA0205"])
    def test_no_se_mete_con_glosas_que_no_son_de_pertinencia(self, codigo: str):
        assert not _nota_operatoria_sin_citar(codigo, GLOSA, PDF_CON_NOTA, DICTAMEN_SOLO_LEY)

    def test_sigue_avisando_del_tope_tarifario(self):
        faltan = objeciones_no_respondidas(GLOSA, DICTAMEN_SOLO_LEY)
        assert any("tope" in f for f in faltan), faltan


class TestUnaSolaFuenteDeVerdad:
    def test_el_motor_no_tiene_su_propia_tabla(self):
        import io

        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert "_FAMILIAS_DE_OBJECION" not in motor, (
            "la tabla volvió a duplicarse: el prompt y la red se van a desincronizar"
        )


class TestNoMolestaDondeNoDebe:
    def test_glosa_de_una_sola_objecion_no_dispara(self):
        p = build_user_prompt(
            texto_glosa="TA0301 SE RECONOCE TARIFA SOAT UVB. VALOR GLOSADO: $1.254.000",
            contexto_pdf="",
            codigo="TA0301",
            eps="LA PREVISORA S.A.",
        )
        assert "ESTA GLOSA OBJETA MAS DE UNA COSA" not in p

    def test_pertinencia_no_quirurgica_no_pide_nota_operatoria(self):
        assert not exige_nota_operatoria(
            "CL0101", "NO SE JUSTIFICA LA PERTINENCIA DEL HEMOGRAMA", PDF_CON_NOTA
        )
