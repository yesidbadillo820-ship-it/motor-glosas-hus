"""El material del prompt se elegía solo por el prefijo del código.

OT-007 · 05-08-2026. Dos dictámenes seguidos del motor del hospital:

    COMPENSAR AU0401 — "el procedimiento 895201 no corresponde con la
    descripción clínica registrada" → el dictamen contestó que "la atención
    de urgencias no requiere autorización previa".

    COOSALUD AU0203 — "el RIPS no coincide con la evolución médica" → el
    dictamen contestó lo mismo.

Ninguna de las dos preguntaba por autorización. La causa no está en el
prompt: está en cómo se arma el contexto. `normas_relevantes_para_codigo`
mapea TODA glosa AU a Ley 100 + T-1025 + Decreto 4747, y el bloque de texto
literal le pega los artículos 168 y 177 de la Ley 100 — que son justamente
"la atención inicial de urgencias... no requiere contrato ni orden previa".
El modelo cita lo que tiene delante. Misma lección de la corrección de ARL.

El arreglo solo QUITA material fuera de tema. No agrega nada, no toca el
prompt y no cambia ninguna otra familia de códigos.
"""

from __future__ import annotations

from app.services.glosa_ia_prompts import (
    _articulos_fuera_de_tema,
    _sin_normas_de_otro_tema,
    build_user_prompt,
)

NORMAS_AU = ["LEY 100 DE 1993", "SENTENCIA T-1025 DE 2002", "DECRETO 4747 DE 2007"]

GLOSA_COMPENSAR = (
    "AU0401 - Se glosa por cuanto el procedimiento 895201 no corresponde con la "
    "descripción clínica registrada. La historia clínica describe una exploración "
    "simple mientras se facturó una exploración especializada."
)
GLOSA_COOSALUD = (
    "AU0203 - Se rechaza la factura porque el RIPS no coincide con la evolución médica."
)
GLOSA_CON_AUTORIZACION = "AU0101 - Servicio prestado SIN AUTORIZACION previa de la EPS."


class TestSeQuitaLoQueNoVieneAlCaso:
    def test_compensar_pierde_las_normas_de_autorizacion(self):
        assert _sin_normas_de_otro_tema(NORMAS_AU, "AU0401", GLOSA_COMPENSAR) == ["LEY 100 DE 1993"]

    def test_coosalud_igual(self):
        assert _sin_normas_de_otro_tema(NORMAS_AU, "AU0203", GLOSA_COOSALUD) == ["LEY 100 DE 1993"]

    def test_los_articulos_de_urgencias_quedan_fuera(self):
        assert _articulos_fuera_de_tema("AU0401", GLOSA_COMPENSAR) == {"168", "177"}

    def test_el_prompt_ya_no_trae_el_texto_de_urgencias(self):
        for glosa, cod in ((GLOSA_COMPENSAR, "AU0401"), (GLOSA_COOSALUD, "AU0203")):
            p = build_user_prompt(
                texto_glosa=glosa, contexto_pdf="", codigo=cod, eps="COMPENSAR"
            ).upper()
            i = p.find("[NORMATIVA CON TEXTO LITERAL")
            bloque = p[i : i + 1500] if i >= 0 else ""
            assert "NO REQUIERE CONTRATO NI ORDEN PREVIA" not in bloque, cod
            assert "ATENCIÓN INICIAL DE URGENCIAS" not in bloque, cod


class TestLaGlosaQueSiPreguntaPorAutorizacion:
    def test_conserva_todo_su_material(self):
        assert _sin_normas_de_otro_tema(NORMAS_AU, "AU0101", GLOSA_CON_AUTORIZACION) == NORMAS_AU

    def test_no_se_le_quitan_articulos(self):
        assert _articulos_fuera_de_tema("AU0101", GLOSA_CON_AUTORIZACION) == set()

    def test_el_prompt_conserva_el_texto_de_urgencias(self):
        p = build_user_prompt(
            texto_glosa=GLOSA_CON_AUTORIZACION, codigo="AU0101", contexto_pdf="", eps="NUEVA EPS"
        ).upper()
        assert "NO REQUIERE CONTRATO NI ORDEN PREVIA" in p

    def test_otras_formas_de_nombrar_la_autorizacion(self):
        for t in (
            "SERVICIO NO AUTORIZADO POR LA EPS",
            "FALTA NUMERO DE AUTORIZACION EN LA FACTURA",
            "LA EPS NO ALCANZÓ A AUTORIZAR EL PROCEDIMIENTO",
            "SIN PREAUTORIZACION",
        ):
            assert _sin_normas_de_otro_tema(NORMAS_AU, "AU0301", t) == NORMAS_AU, t


class TestNoSeTocaNadaMas:
    def test_las_demas_familias_quedan_igual(self):
        for cod in ("TA0801", "SO0201", "FA0301", "CO0102", "CL0501", "DE1601"):
            assert _sin_normas_de_otro_tema(NORMAS_AU, cod, "cualquier motivo") == NORMAS_AU, cod
            assert _articulos_fuera_de_tema(cod, "cualquier motivo") == set(), cod

    def test_lista_vacia_o_codigo_vacio(self):
        assert _sin_normas_de_otro_tema([], "AU0401", GLOSA_COMPENSAR) == []
        assert _sin_normas_de_otro_tema(NORMAS_AU, "", "x") == NORMAS_AU

    def test_nunca_lo_deja_sin_material(self):
        """Si TODO lo relevante era de autorización, se conserva la lista:
        mejor material de más que un dictamen sin fundamento."""
        solo_autorizacion = ["SENTENCIA T-1025 DE 2002", "DECRETO 4747 DE 2007"]
        assert (
            _sin_normas_de_otro_tema(solo_autorizacion, "AU0401", GLOSA_COMPENSAR)
            == solo_autorizacion
        )
