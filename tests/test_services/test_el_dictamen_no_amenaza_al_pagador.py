"""El dictamen argumenta; no amenaza.

Casos GL-118 y GL-119 (lote de prueba de agosto): la respuesta al pagador
cerraba advirtiendo responsabilidad penal y anunciando acciones legales. Dos
problemas a la vez:

  · el hospital NO tiene facultad sancionatoria sobre el pagador, asi que la
    amenaza es hueca y el auditor de la EPS lo sabe;
  · pone a la contraparte a la defensiva y escala un caso que se ganaba con
    el argumento normativo.

La regla 8.decies del prompt ya lo prohibia — pero era solo una instruccion y
la IA amenazo igual. Esta es la red que si lo impide.

Lo que SI debe seguir saliendo, porque es legitimo y esta en la norma:
elevar el conflicto a la Superintendencia (Art. 126 Ley 1438 de 2011), pedir
el levantamiento por falta de respuesta (Art. 57), negarle a la EPS la
facultad sancionatoria sobre el prestador y atribuirle su responsabilidad
presupuestal.
"""

from app.services.glosa_service import (
    TEXTO_RATIFICADA,
    _neutralizar_frases_absurdas,
)


class TestSeQuitanLasAmenazas:
    def test_advertencia_de_responsabilidad_penal(self):
        texto = (
            "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA. SE ADVIERTE QUE EL NO PAGO "
            "GENERARÁ RESPONSABILIDAD PENAL DE LOS FUNCIONARIOS. FIN."
        )
        salida = _neutralizar_frases_absurdas(texto)
        assert "RESPONSABILIDAD PENAL" not in salida.upper()
        assert "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA." in salida

    def test_anuncio_de_acciones_legales(self):
        texto = "DE NO PAGARSE, SE TOMARÁN LAS ACCIONES LEGALES CORRESPONDIENTES."
        salida = _neutralizar_frases_absurdas(texto)
        assert "ACCIONES LEGALES" not in salida.upper()

    def test_acciones_judiciales_y_penales(self):
        for verbo in ("SE EMPRENDERÁN", "SE INICIARÁN", "SE ADELANTARÁN"):
            texto = f"{verbo} LAS ACCIONES JUDICIALES A QUE HAYA LUGAR."
            assert "ACCIONES JUDICIALES" not in _neutralizar_frases_absurdas(texto).upper()

    def test_responsabilidad_disciplinaria_y_fiscal(self):
        texto = "EL RECHAZO INJUSTIFICADO ACARREARÁ RESPONSABILIDAD DISCIPLINARIA Y FISCAL."
        salida = _neutralizar_frases_absurdas(texto)
        assert "RESPONSABILIDAD DISCIPLINARIA" not in salida.upper()

    def test_bajo_apercibimiento(self):
        texto = "SE REQUIERE EL PAGO BAJO APERCIBIMIENTO DE INICIAR EL COBRO COACTIVO."
        salida = _neutralizar_frases_absurdas(texto)
        assert "APERCIBIMIENTO" not in salida.upper()

    def test_compulsar_copias(self):
        texto = "SE COMPULSARÁN COPIAS A LA PROCURADURÍA GENERAL DE LA NACIÓN."
        salida = _neutralizar_frases_absurdas(texto)
        assert "COMPULSAR" not in salida.upper()

    def test_denuncia_penal(self):
        texto = "LA CONDUCTA SERÁ OBJETO DE DENUNCIA PENAL ANTE LA FISCALÍA."
        salida = _neutralizar_frases_absurdas(texto)
        assert "DENUNCIA PENAL" not in salida.upper()


class TestNoSeLlevaLoLegitimo:
    def test_la_superintendencia_sigue_en_pie(self):
        salida = _neutralizar_frases_absurdas(TEXTO_RATIFICADA)
        assert "SUPERINTENDENCIA NACIONAL DE SALUD" in salida
        assert "ART. 126 DE LA LEY 1438/2011" in salida

    def test_el_levantamiento_por_falta_de_respuesta_sigue_en_pie(self):
        salida = _neutralizar_frases_absurdas(TEXTO_RATIFICADA)
        assert "SE DARÁ POR LEVANTADA LA RESPECTIVA OBJECIÓN" in salida

    def test_el_texto_de_ratificacion_no_se_toca(self):
        assert _neutralizar_frases_absurdas(TEXTO_RATIFICADA) == TEXTO_RATIFICADA

    def test_negarle_a_la_eps_la_facultad_sancionatoria_sigue_en_pie(self):
        texto = (
            "LA FACULTAD SANCIONATORIA SOBRE EL PRESTADOR ESTÁ RESERVADA A LA "
            "SUPERINTENDENCIA NACIONAL DE SALUD; LA ENTIDAD PAGADORA CARECE DE ELLA."
        )
        assert _neutralizar_frases_absurdas(texto) == texto

    def test_la_responsabilidad_presupuestal_del_pagador_sigue_en_pie(self):
        texto = (
            "EL EVENTUAL AGOTAMIENTO PRESUPUESTAL ES RESPONSABILIDAD DEL DMBUG "
            "(ART. 71 DEL DECRETO 111/1996) Y NO PUEDE TRASLADARSE AL PRESTADOR."
        )
        assert _neutralizar_frases_absurdas(texto) == texto

    def test_un_dictamen_normal_sale_identico(self):
        texto = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA BAJO EL CÓDIGO TA0201. EL VALOR "
            "FACTURADO CORRESPONDE A LA TARIFA PACTADA. SE SOLICITA EL "
            "LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO DE LO FACTURADO."
        )
        assert _neutralizar_frases_absurdas(texto) == texto
