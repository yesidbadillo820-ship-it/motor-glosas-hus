"""Los tres defectos de la tercera corrida de la prueba 2 (31-08-2026).

Glosa CL4506 · HUS0000601892 · NUEVA EPS, con la caché de IA ya vaciada.

Lo que sí funcionó y no se puede perder: la IA leyó la nota operatoria, sacó
el folio y justificó biomecánicamente el doble material. Eso salvó la objeción
de pertinencia.

Lo que falló:

  1. «PROCEDIMIENTO OSTEOSÍNTESIS DE FÉMUR (código CL4506)». El campo
     <servicio> ya se limpiaba; el CUERPO no. La red del cuerpo
     (`_neutralizar_cups_sin_respaldo`) exige la palabra literal «CUPS» y ahí
     decía «código» a secas, entre paréntesis: nunca hubo coincidencia.
  2. Ante el tope contractual, «EL VALOR FACTURADO SE AJUSTA A LA COMPLEJIDAD
     DEL PROCEDIMIENTO». Palabras del auditor: «eso en auditoría no sirve para
     nada y hace perder el dinero».
  3. El bloque de anexos no salió: se había metido dentro del «si el índice no
     encontró nada», y esta vez el índice sí respondió.
"""

import pytest

from app.services.glosa_ia_prompts import build_user_prompt
from app.services.glosa_service import (
    GlosaService,
    _objecion_de_dinero_con_relleno,
    _quitar_causal_propia_del_cuerpo,
)

GLOSA = (
    "CL4506 | HUS0000601892 | NUEVA E.P.S. S.A. - SUBSIDIADO\n"
    "NO SE JUSTIFICA LA PERTINENCIA DEL MATERIAL DE OSTEOSINTESIS UTILIZADO.\n"
    "SE FACTURA CLAVO CEFALOMEDULAR Y ADICIONALMENTE PLACA DCP 4.5.\n"
    "ADICIONALMENTE EL VALOR UNITARIO DEL CLAVO SUPERA EL TOPE CONTRACTUAL."
)


class TestLaCausalFueraDelCuerpo:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            (
                "EL PROCEDIMIENTO OSTEOSÍNTESIS DE FÉMUR (código CL4506) FUE PERTINENTE.",
                "EL PROCEDIMIENTO OSTEOSÍNTESIS DE FÉMUR FUE PERTINENTE.",
            ),
            (
                "SE FACTURA EL PROCEDIMIENTO, código CL-4506, conforme a la HC.",
                "SE FACTURA EL PROCEDIMIENTO, conforme a la HC.",
            ),
            (
                "EL PROCEDIMIENTO CON CUPS CL 4506 ES PERTINENTE.",
                "EL PROCEDIMIENTO ES PERTINENTE.",
            ),
            ("EL PROCEDIMIENTO (CL4506) ES PERTINENTE.", "EL PROCEDIMIENTO ES PERTINENTE."),
        ],
    )
    def test_lo_borra_venga_como_venga(self, texto: str, esperado: str):
        assert _quitar_causal_propia_del_cuerpo(texto, "CL4506") == esperado

    def test_no_toca_un_cups_de_verdad(self):
        t = "EL HEMOGRAMA (código 902210) ES PERTINENTE."
        assert _quitar_causal_propia_del_cuerpo(t, "CL4506") == t

    def test_no_toca_la_glosa_nombrada_como_glosa(self):
        """Decir «la glosa CL4506» es correcto: ahí sí es la causal."""
        t = "LA GLOSA CL4506 POR $7.310.000 NO PROCEDE."
        assert _quitar_causal_propia_del_cuerpo(t, "CL4506") == t

    def test_no_toca_otra_causal_distinta(self):
        """Solo se borra la de ESTA glosa; las demás las juzga el catálogo."""
        t = "EL PROCEDIMIENTO (código TA0301) FUE PERTINENTE."
        assert _quitar_causal_propia_del_cuerpo(t, "CL4506") == t

    @pytest.mark.parametrize("basura", ["", "   ", "902210", "NO-ES-CODIGO"])
    def test_codigo_raro_no_rompe_nada(self, basura: str):
        t = "EL PROCEDIMIENTO (código CL4506) ES PERTINENTE."
        assert _quitar_causal_propia_del_cuerpo(t, basura) == t

    def test_no_deja_el_texto_vacio(self):
        assert _quitar_causal_propia_del_cuerpo("(código CL4506)", "CL4506") == "(código CL4506)"


class TestElDineroNoSeContestaConAdjetivos:
    def test_atrapa_la_frase_que_salio(self):
        assert _objecion_de_dinero_con_relleno(
            GLOSA, "EL VALOR FACTURADO SE AJUSTA A LA COMPLEJIDAD DEL PROCEDIMIENTO."
        )

    @pytest.mark.parametrize(
        "frase",
        [
            "EL VALOR ES RAZONABLE.",
            "ACORDE CON LA NATURALEZA DEL SERVICIO.",
            "CORRESPONDE A LOS ESTÁNDARES DEL MERCADO.",
        ],
    )
    def test_atrapa_las_demas_formulas_vacias(self, frase: str):
        assert _objecion_de_dinero_con_relleno(GLOSA, frase)

    def test_calla_si_cita_el_contrato(self):
        assert not _objecion_de_dinero_con_relleno(
            GLOSA,
            "EL VALOR SE AJUSTA A LA COMPLEJIDAD. CONTRATO 02-01-06-00077-2017, "
            "TARIFA NO DETERMINADA.",
        )

    def test_calla_si_exige_la_clausula(self):
        assert not _objecion_de_dinero_con_relleno(
            GLOSA, "SE EXIGE LA CLÁUSULA DEL TOPE INVOCADO; PACTA SUNT SERVANDA."
        )

    def test_no_se_mete_donde_no_hay_objecion_de_plata(self):
        assert not _objecion_de_dinero_con_relleno(
            "SO0102 NO SE ANEXA LA EPICRISIS.",
            "EL VALOR FACTURADO SE AJUSTA A LA COMPLEJIDAD DEL PROCEDIMIENTO.",
        )


class TestElPromptProhibeElRelleno:
    def _p(self) -> str:
        return build_user_prompt(
            texto_glosa=GLOSA, contexto_pdf="", codigo="CL4506", eps="NUEVA EPS"
        )

    def test_prohibe_las_formulas_vacias_por_su_nombre(self):
        p = self._p()
        assert "PROHIBIDAS las formulas vacias" in p
        assert "se ajusta a la complejidad" in p

    def test_exige_las_tres_cosas_concretas(self):
        p = self._p()
        assert "el NUMERO del contrato" in p
        assert "<tarifa>" in p
        assert "CLAUSULA del tope que invoca" in p

    def test_le_dice_que_hacer_si_le_faltan_datos(self):
        assert "pedir el dato es defensa" in self._p()


class TestLosAnexosSeRelacionanSiempre:
    def test_lee_los_nombres_de_la_marca_del_router(self):
        ctx = (
            "═══ DOCUMENTO: nota_operatoria.pdf ═══\ntexto\n"
            "═══ DOCUMENTO: epicrisis.pdf ═══\nmas texto"
        )
        assert GlosaService._documentos_adjuntos(ctx) == [
            "nota_operatoria.pdf",
            "epicrisis.pdf",
        ]

    def test_sin_adjuntos_devuelve_vacio(self):
        assert GlosaService._documentos_adjuntos("") == []
        assert GlosaService._documentos_adjuntos("texto suelto") == []

    def test_no_repite_el_mismo_archivo(self):
        ctx = "═══ DOCUMENTO: a.pdf ═══\nx\n═══ DOCUMENTO: a.pdf ═══\ny"
        assert GlosaService._documentos_adjuntos(ctx) == ["a.pdf"]

    def test_el_bloque_ya_no_vive_dentro_de_la_rama_del_indice(self):
        """Era el bug: el índice respondió y los anexos se perdieron."""
        import io

        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        i_anx = motor.index("_bloque_anexos = (")
        i_rama = motor.index("if not soportes_reales:", motor.index("filas_adj, soportes_reales"))
        assert i_anx < i_rama, "el bloque volvió a quedar dentro del «si el índice no halló nada»"
        assert motor.count("bloque_adjuntos += _bloque_anexos") == 1, (
            "la rama del índice ya no concatena los anexos"
        )

    def test_el_titulo_corta_el_argumento(self):
        """Si no está en la lista de cortes, el bloque se cuela al texto radicable."""
        import io

        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert '"DOCUMENTOS ANEXOS A ESTA RESPUESTA",' in motor
