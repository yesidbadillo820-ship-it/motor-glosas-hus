"""Las ratificaciones de aseguradora ya no salen con la plantilla.

DECISION DEL AREA, 25-08-2026. La segunda auditoria del lote midio que de los
44 codigos de las 21 respuestas a glosas ratificadas, **ninguno** entraba en el
motivo concreto por el que la entidad ratifico: todas usaban el mismo texto
institucional. El caso: HUS0000512271, de la Compania de Seguros de Vida
Aurora — «se ratifica glosa por Estancia no autorizada» contestado con la
plantilla generica.

Yesid decidio: «en el caso de las ratificadas, cuando son de aseguradoras
estas no van con esa respuesta, sino que toca hacerle su respectivo analisis».

Las demas —EPS, Dispensario, Policia, Magisterio, PPL— siguen con la plantilla
institucional, que es la que el area pidio en abril y no se toca.
"""

from app.services.glosa_ia_prompts import build_user_prompt
from app.services.glosa_service import _ratificada_va_al_analisis


class TestQuienVaAlAnalisis:
    def test_las_companias_de_seguros(self):
        for eps in (
            "C250121 - COMPAÑIA DE SEGUROS DE VIDA AURORA",
            "LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB",
            "ASEGURADORA SOLIDARIA DE COLOMBIA",
            "COMPAÑIA MUNDIAL DE SEGUROS S.A. SOAT UVB",
            "SEGUROS DEL ESTADO S.A.",
        ):
            assert _ratificada_va_al_analisis(eps), eps

    def test_las_arl(self):
        assert _ratificada_va_al_analisis("POSITIVA COMPAÑIA DE SEGUROS S.A.")
        assert _ratificada_va_al_analisis("SEGUROS DE VIDA SURAMERICANA ARL")


class TestQuienSigueConLaPlantilla:
    def test_las_eps(self):
        for eps in (
            "C220018 - NUEVA E.P.S. S.A. - SUBSIDIADO",
            "FAMISANAR EPS",
            "COOSALUD EPS",
            "SALUD TOTAL",
        ):
            assert not _ratificada_va_al_analisis(eps), eps

    def test_el_dispensario_y_sanidad_militar(self):
        """Tienen contrato y su propio texto: NO son aseguradoras para esto,
        aunque el otro clasificador del motor (_es_aseguradora_soat, que sirve
        para reforzar el prompt de tarifas) sí los meta en su lista."""
        for eps in (
            "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA",
            "DIRECCIÓN DE SANIDAD NAVAL",
            "REGIONAL DE ASEGURAMIENTO EN SALUD N°5 POLICIA NACIONAL",
        ):
            assert not _ratificada_va_al_analisis(eps), eps

    def test_el_magisterio_aunque_lo_pague_fiduprevisora(self):
        """FOMAG lo administra Fiduprevisora, que lleva «previsora» en el
        nombre. No es una aseguradora ratificando: es el fondo del magisterio."""
        assert not _ratificada_va_al_analisis("FOMAG - FIDUPREVISORA")
        assert not _ratificada_va_al_analisis("FIDUPREVISORA S.A. MAGISTERIO")

    def test_sin_pagador_no_cambia_nada(self):
        assert not _ratificada_va_al_analisis("")
        assert not _ratificada_va_al_analisis(None)


class TestLoQueSeLeDiceAlMotor:
    """Cuando la ratificación va al análisis, el motor tiene que saber que NO
    debe repetir la respuesta inicial."""

    def _prompt(self, **kw):
        base = dict(
            texto_glosa="SE RATIFICA LA GLOSA POR ESTANCIA NO AUTORIZADA",
            contexto_pdf="",
            codigo="CL0101",
            eps="COMPAÑIA DE SEGUROS DE VIDA AURORA",
        )
        base.update(kw)
        return build_user_prompt(**base)

    def test_le_dice_que_refute_el_motivo_de_la_ratificacion(self):
        p = self._prompt(es_ratificacion=True)
        assert "ESTA ES UNA RATIFICACIÓN" in p
        assert "NO REPITAS LA RESPUESTA INICIAL" in p

    def test_le_da_el_argumento_de_la_causal_nueva(self):
        """El Art. 23 prohíbe glosar de nuevo la misma factura salvo por
        hechos nuevos: si la entidad ratifica estrenando causal, es rebatible."""
        p = self._prompt(es_ratificacion=True)
        assert "Art. 23 del Decreto 4747 de 2007" in p
        assert "hechos nuevos" in p

    def test_conserva_el_cierre_que_corresponde(self):
        p = self._prompt(es_ratificacion=True)
        assert "Superintendencia Nacional de Salud" in p
        assert "Art. 126 Ley 1438/2011" in p

    def test_le_prohibe_amenazar_y_el_falso_silencio_positivo(self):
        p = self._prompt(es_ratificacion=True)
        assert "nunca amenazante" in p
        assert "silencio de la entidad equivale a aceptación" in p

    def test_una_glosa_inicial_no_lleva_ese_bloque(self):
        p = self._prompt(codigo="TA0201", eps="NUEVA EPS")
        assert "ESTA ES UNA RATIFICACIÓN" not in p
