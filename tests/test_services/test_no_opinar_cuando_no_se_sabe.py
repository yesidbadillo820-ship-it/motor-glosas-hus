"""«No sé qué se leyó» no es lo mismo que «no se leyó nada» (21-08-2026).

`verificar_citas(..., evidencia=...)` distingue tres cosas:

    evidencia = "texto de los PDF"  → se leyó ESO; se contrasta contra ello.
    evidencia = ""                  → se analizó SIN adjuntar nada; se marca
                                      cualquier afirmación sobre documentos.
    evidencia = None                → este camino no sabe qué se leyó; no opina.

Una investigación marcó ese tercer caso como «agujero abierto» porque dos
llamadores pasan `None` y ahí la protección nunca corre. **Revisándolo, es una
decisión correcta y hay que dejarla:**

  · `quality_gate/post_validator.check_citas_verificadas` solo recibe el texto
    y la EPS. No tiene el contexto de los PDF.
  · `dictamen_postprocesor` **borra** las frases con citas inválidas. Si ahí se
    marcaran afirmaciones documentales, borraría argumentación clínica
    legítima de dictámenes donde SÍ se adjuntaron soportes.

Pasarles `""` para «cerrar el hueco» convertiría la protección en una máquina
de avisos falsos. Esta prueba existe para que nadie lo «arregle» después sin
saber por qué está así.
"""

from __future__ import annotations

import inspect

from app.services.citation_verifier import verificar_citas

AFIRMA_SIN_SOPORTE = (
    "ESE HUS NO ACEPTA LA GLOSA. EL PROCEDIMIENTO ESTÁ DEBIDAMENTE INDICADO EN LA "
    "HISTORIA CLÍNICA DEL PACIENTE, SEGÚN CONSTA EN EL EXPEDIENTE."
)


def _tipos(reporte: dict) -> set[str]:
    return {i["tipo"] for i in reporte.get("issues", [])}


class TestLosTresCasos:
    def test_sin_adjuntar_nada_si_se_marca(self):
        """Cadena vacía = «se analizó sin soportes». Ahí sí se acusa."""
        assert "AFIRMACION_SIN_SOPORTE" in _tipos(verificar_citas(AFIRMA_SIN_SOPORTE, evidencia=""))

    def test_con_expediente_leido_no_se_marca(self):
        evidencia = "═══ DOCUMENTO: historia_clinica.pdf ═══\nFOLIO 12: se ordena el estudio."
        assert "AFIRMACION_SIN_SOPORTE" not in _tipos(
            verificar_citas(AFIRMA_SIN_SOPORTE, evidencia=evidencia)
        )

    def test_sin_saber_no_se_opina(self):
        """El caso que hay que proteger: sin el dato, no se acusa."""
        assert "AFIRMACION_SIN_SOPORTE" not in _tipos(verificar_citas(AFIRMA_SIN_SOPORTE))


class TestLosDosLlamadoresQueNoDebenPasarlo:
    def test_el_quality_gate_no_tiene_el_contexto(self):
        from app.services.quality_gate.post_validator import check_citas_verificadas

        params = inspect.signature(check_citas_verificadas).parameters
        assert "evidencia" not in params, (
            "Si algún día recibe la evidencia, hay que pasarla a verificar_citas; "
            "mientras no la reciba, NO puede pasar cadena vacía."
        )

    def test_el_postprocesador_borra_frases_y_por_eso_no_opina(self):
        """Es el más peligroso: si marcara afirmaciones documentales, borraría
        argumentación clínica legítima."""
        from app.services import dictamen_postprocesor as mod

        fuente = inspect.getsource(mod)
        assert "verificar_citas(texto, eps=eps)" in fuente
        assert "evidencia=" not in fuente


class TestLaDecisionQuedaExplicada:
    def test_el_codigo_dice_por_que(self):
        """Sin la explicación, el próximo que lo lea lo «arregla» y rompe la
        protección convirtiéndola en avisos falsos.

        Se mira el MÓDULO y no una función: la decisión es del contrato de
        `verificar_citas` —qué significa `evidencia=None`— y aplica igual a la
        revisión de folios y a la de afirmaciones documentales.
        """
        from app.services import citation_verifier as mod

        fuente = inspect.getsource(mod)
        assert "no sabe qué se leyó" in fuente, "se perdió la explicación del None"
        assert "post_validator" in fuente, "no se nombra al llamador que no debe pasarlo"
        assert "dictamen_postprocesor" in fuente, "no se explica por qué el que BORRA no opina"

    def test_los_tres_casos_quedan_escritos(self):
        """El contrato de `evidencia` tiene que estar dicho, no deducido."""
        from app.services import citation_verifier as mod

        fuente = inspect.getsource(mod)
        assert "no se leyó ningún soporte" in fuente
        assert "no se inventa un fallo" in fuente
