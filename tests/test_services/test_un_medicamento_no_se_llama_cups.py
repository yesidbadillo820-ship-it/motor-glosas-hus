"""Un medicamento se factura con CUM, no con CUPS.

09-09-2026, caso 1 de la prueba del auditor. Una glosa de tarifas sobre
acetaminofén salió con un dictamen que hablaba del «código homologado del
CUPS facturado». El acetaminofén no tiene CUPS: tiene CUM. Son dos tablas
distintas del Ministerio —CUPS son procedimientos, CUM son medicamentos— y
la entidad cruza el CUPS contra la suya, no encuentra el código y ratifica
la glosa completa, por bien argumentado que esté el resto.

DÓNDE ESTABA EL DEFECTO, Y NO ERA DEL MODELO. La regla 4 del prompt de
sistema ya decía «NUNCA escribas CUPS cuando el número viene de un CUM».
Pero la ficha de datos del caso —la parte que el prompt llama AUTORITATIVA—
rotulaba «CUPS» cualquier código, CUM incluido, y encima remataba con «USA
ESTE CUPS». El prompt se contradecía a sí mismo, y entre una regla general y
un dato concreto con una orden al lado, gana el dato.

QUÉ CUIDA ESTA PRUEBA. Que la ficha llame a cada código por su nombre, y que
cuando sea un CUM lo diga explícitamente para que el modelo no arrastre la
palabra «CUPS» desde los ejemplos del resto del prompt.
"""

from __future__ import annotations

import pytest

from app.services.glosa_ia_prompts import _es_codigo_cum, build_user_prompt


class TestReconocerElCum:
    @pytest.mark.parametrize(
        "cum",
        ["20123-1", "19953856-3", "19900272-1", "20047-22", "1234-1"],
    )
    def test_los_cum_se_reconocen(self, cum):
        assert _es_codigo_cum(cum), cum

    @pytest.mark.parametrize(
        "cups",
        [
            "890201",  # consulta
            "882201",
            "890201H",  # con sufijo de letra
            "39147B-18",  # CUPS con anexo: el guion NO lo vuelve un CUM
            "348240",
        ],
    )
    def test_los_cups_no_se_confunden(self, cups):
        assert not _es_codigo_cum(cups), cups

    def test_sin_codigo_no_se_afirma_nada(self):
        assert not _es_codigo_cum("")
        assert not _es_codigo_cum(None)
        assert not _es_codigo_cum("   ")

    def test_ni_una_fecha_ni_una_factura(self):
        """Las dos cosas que históricamente se colaban en la casilla."""
        assert not _es_codigo_cum("2026-04-15")
        assert not _es_codigo_cum("HUS0000522871")


def _ficha(codigo: str) -> str:
    """La línea de la ficha donde va el código del servicio."""
    prompt = build_user_prompt(
        texto_glosa="TA0801 $12.500 VALOR FACTURADO SUPERIOR AL PACTADO",
        contexto_pdf="",
        codigo="TA0801",
        eps="COOSALUD EPS",
        cups_verificado=codigo,
        valor_objetado="$12.500",
    )
    return prompt


class TestLaFichaLoNombraBien:
    def test_un_medicamento_no_se_rotula_cups(self):
        prompt = _ficha("20123-1")
        linea = next(ln for ln in prompt.splitlines() if "20123-1" in ln and "←" in ln)
        assert "CUM" in linea, (
            f"La ficha sigue rotulando el CUM como otra cosa:\n    {linea.strip()}"
        )
        assert not linea.strip().startswith("• CUPS"), (
            "La ficha le dice «CUPS» al código de un medicamento, y esa ficha es "
            "la parte del prompt que se declara AUTORITATIVA."
        )

    def test_y_se_lo_dice_al_modelo_con_todas_las_letras(self):
        """Rotular bien la fila no basta: el resto del prompt está lleno de
        ejemplos con la palabra CUPS y el modelo los copia."""
        prompt = _ficha("20123-1")
        assert "es un CUM (código del MEDICAMENTO), NO un CUPS" in prompt
        assert "código homologado del CUPS" in prompt, (
            "No se le prohíbe la frase exacta que salió en el dictamen del caso 1."
        )

    def test_un_procedimiento_sigue_siendo_cups(self):
        """La corrección no puede voltear el caso normal, que es la mayoría."""
        prompt = _ficha("890201")
        linea = next(ln for ln in prompt.splitlines() if "890201" in ln and "←" in ln)
        assert linea.strip().startswith("• CUPS"), linea
        assert "es un CUM" not in prompt

    def test_el_cups_con_anexo_no_se_vuelve_medicamento(self):
        """«39147B-18» es un CUPS con anexo. Marcarlo como CUM le quitaría al
        hospital el argumento tarifario correcto."""
        prompt = _ficha("39147B-18")
        linea = next(ln for ln in prompt.splitlines() if "39147B-18" in ln and "←" in ln)
        assert linea.strip().startswith("• CUPS"), linea

    def test_sin_codigo_confiable_el_aviso_de_siempre_sigue_saliendo(self):
        """La rama del CUM no puede haberle robado el turno a la que ya
        estaba: sin código, lo que va es «no inventes»."""
        prompt = _ficha("NO IDENTIFICADO")
        assert "NO inventes ni rellenes el CUPS" in prompt
        assert "es un CUM" not in prompt
