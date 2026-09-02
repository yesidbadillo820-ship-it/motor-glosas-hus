"""GL-149: la IA inventó una cuenta y citó un documento que no existía.

01-09-2026, corrida 6 de la prueba 2. Por fin el motor generó un dictamen
nuevo (GL-149, «1 glosas este mes»), y con él aparecieron dos afirmaciones que
la entidad tumba de un manotazo:

  1. «EL VALOR UNITARIO DEL CLAVO NO SUPERA EL TOPE CONTRACTUAL, YA QUE EL
     CONTRATO VENCIDO ESTABLECÍA UN FACTOR 0.80 Y EL VALOR FACTURADO DE
     $18.940.000, DE ACUERDO CON LA TARIFA SOAT PLENA, ES COMPATIBLE CON LA UVB
     VIGENTE». Nadie hizo esa cuenta: el motor no tiene el tarifario ni la
     fecha del servicio.

  2. «LA HISTORIA CLÍNICA (FOLIO 1) DETALLA QUE…» cuando lo aportado era
     nota_operatoria.pdf y rips_procedimientos.pdf. La historia clínica no
     estaba entre los soportes.

Y de paso el código de la glosa volvió a colarse en el renglón del servicio,
esta vez con guion corto: «OSTEOSÍNTESIS DE FÉMUR - código CL4506».
"""

import pytest

from app.services.glosa_service import (
    _afirmacion_financiera_del_modelo,
    _la_glosa_objeta_plata,
    _limpiar_linea_servicio_objetado,
    _parrafo_tarifario_determinista,
)

GLOSA = (
    "CL4506 | HUS0000601892 | NUEVA E.P.S. S.A. - SUBSIDIADO\n"
    "NO SE JUSTIFICA LA PERTINENCIA DEL MATERIAL DE OSTEOSINTESIS.\n"
    "ADICIONALMENTE EL VALOR UNITARIO DEL CLAVO SUPERA EL TOPE CONTRACTUAL."
)

# La frase textual de GL-149.
FRASE_GL149 = (
    "POR ÚLTIMO, EL VALOR UNITARIO DEL CLAVO NO SUPERA EL TOPE CONTRACTUAL, YA "
    "QUE EL CONTRATO VENCIDO ESTABLECÍA UN FACTOR 0.80 Y EL VALOR FACTURADO DE "
    "$18.940.000, DE ACUERDO CON LA TARIFA SOAT PLENA, ES COMPATIBLE CON LA UVB "
    "VIGENTE; EN CONSECUENCIA, EL DESCUENTO DE $ 7.310.000 RESULTA IMPROCEDENTE."
)


class TestLaCuentaQueNadieHizo:
    def test_detecta_la_frase_de_gl149(self):
        assert _afirmacion_financiera_del_modelo(FRASE_GL149)

    @pytest.mark.parametrize("frag", ["UVB", "FACTOR 0.8", "SOAT PLENA", "ES COMPATIBLE CON LA"])
    def test_nombra_los_pedazos_para_que_el_gestor_los_busque(self, frag: str):
        hallados = [h.upper() for h in _afirmacion_financiera_del_modelo(FRASE_GL149)]
        assert any(frag in h for h in hallados), hallados

    def test_calla_cuando_la_ia_respeta_la_prohibicion(self):
        limpio = (
            "LA NOTA OPERATORIA DEL FOLIO 1 REGISTRA CONMINUCIÓN CON EXTENSIÓN "
            "SUBTROCANTÉRICA, QUE EXIGIÓ EL DOBLE SISTEMA DE FIJACIÓN."
        )
        assert _afirmacion_financiera_del_modelo(limpio) == []

    def test_texto_vacio_no_rompe(self):
        assert _afirmacion_financiera_del_modelo("") == []


class TestElParrafoYaNoDependeDeLaIA:
    """Antes bastaba que la IA escribiera «tarifa» para desactivar la inyección."""

    def test_la_glosa_de_tope_siempre_pide_el_parrafo(self):
        assert _la_glosa_objeta_plata(GLOSA)

    def test_la_glosa_sin_plata_no_lo_pide(self):
        assert not _la_glosa_objeta_plata("SO0102 NO SE ANEXA LA EPICRISIS.")

    def test_el_parrafo_del_motor_no_afirma_lo_que_no_puede_probar(self):
        """El motor tampoco tiene el tarifario: pide la cláusula, no promete."""
        p = _parrafo_tarifario_determinista(
            GLOSA,
            {
                "numero": "CONTRATO CON VIGENCIA TERMINADA: 02-01-06-00077-2017",
                "_vigencia_vencida": True,
            },
            "$ 7.310.000",
        ).upper()
        assert "NO IDENTIFICA LA CLÁUSULA" in p
        for prometido in (
            "NO SUPERA EL TOPE",
            "ES COMPATIBLE CON LA UVB",
            "SE AJUSTA A LA COMPLEJIDAD",
        ):
            assert prometido not in p, prometido


class TestElRenglonDelServicio:
    @pytest.mark.parametrize(
        "sufijo",
        [
            "- código CL4506",
            "código CL4506",
            "(CL4506)",
            "[CL4506]",
            "ref. CL4506",
            "– código CL4506",
        ],
    )
    def test_lo_borra_venga_como_venga(self, sufijo: str):
        t = f"<div><b>Servicio objetado:</b> OSTEOSÍNTESIS DE FÉMUR {sufijo}</div>"
        assert _limpiar_linea_servicio_objetado(t, "CL4506") == (
            "<div><b>Servicio objetado:</b> OSTEOSÍNTESIS DE FÉMUR</div>"
        )

    def test_no_toca_un_cups_real(self):
        t = "<div><b>Servicio objetado:</b> HEMOGRAMA IV código 902210</div>"
        assert _limpiar_linea_servicio_objetado(t, "CL4506") == t

    def test_no_toca_otros_renglones(self):
        """Un barrido amplio ya se llevó los títulos multi-código una vez."""
        t = (
            "<div>═══ RESPUESTA AL CÓDIGO CL4506 — PERTINENCIA ═══</div>"
            "<div><b>Servicio objetado:</b> OSTEOSÍNTESIS DE FÉMUR código CL4506</div>"
        )
        r = _limpiar_linea_servicio_objetado(t, "CL4506")
        assert "RESPUESTA AL CÓDIGO CL4506 — PERTINENCIA" in r
        assert "Servicio objetado:</b> OSTEOSÍNTESIS DE FÉMUR</div>" in r

    def test_no_deja_el_renglon_sin_servicio(self):
        """Un rótulo huérfano confunde más que el código de más."""
        t = "<div><b>Servicio objetado:</b> CL4506</div>"
        assert _limpiar_linea_servicio_objetado(t, "CL4506") == t

    def test_codigo_vacio_o_raro_no_rompe(self):
        t = "<div><b>Servicio objetado:</b> OSTEOSÍNTESIS código CL4506</div>"
        for basura in ("", "   ", "902210", "N/A"):
            assert _limpiar_linea_servicio_objetado(t, basura) == t


class TestLasDosProhibicionesEstanEnElSystem:
    def _base(self) -> str:
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        return SYSTEM_BASE

    def test_prohibe_las_cifras_antes_de_la_mision(self):
        b = self._base()
        assert b.index("PROHIBICIÓN ABSOLUTA — DINERO") < b.index("MISIÓN: Redactar")

    def test_nombra_lo_que_no_puede_escribir(self):
        b = self._base()
        for palabra in ("UVB", "FACTOR", "TOPE CONTRACTUAL", "PORCENTAJE DE DESCUENTO"):
            assert palabra in b, palabra

    def test_le_dice_que_otra_capa_lo_hace(self):
        assert "La defensa económica la arma OTRA CAPA del sistema" in self._base()

    def test_prohibe_citar_documentos_no_aportados(self):
        b = self._base()
        assert "PROHIBICIÓN ABSOLUTA — DOCUMENTOS" in b
        assert "JAMÁS escribas «historia clínica»" in b

    def test_le_da_la_salida_correcta(self):
        """Una prohibición sin salida deja a la IA sin qué escribir."""
        b = self._base()
        assert "decí «la objeción tarifaria» y seguí" in b
        assert "decí «la nota operatoria»" in b
