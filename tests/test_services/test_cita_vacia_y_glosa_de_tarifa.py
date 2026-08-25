"""Dos defectos que salieron de un dictamen real — 18-08-2026.

Yesid analizó una glosa de NUEVA EPS: «se glosa servicio por mayor valor
cobradp segun contracto rx de rodilla por valor de 12.000». El dictamen que
salió traía dos cosas mal.

1. UNA CITA NORMATIVA VACÍA. Decía, textual:

       EN VIRTUD DE ART. 168 LA LEY 100 DE 1993, QUE DISPONE «.», Y …

   La IA abrió comillas para citar el artículo y escribió un punto. Y abajo,
   el sello: «7 citas verificadas · 0 hallazgos». El verificador no la vio
   porque su patrón exigía 15 caracteres dentro de las comillas.

   En un documento que se radica, una cita normativa que no dice nada le
   entrega a la entidad el argumento de que el prestador no sustentó su
   defensa.

2. LA GLOSA SE CLASIFICÓ COMO FACTURACIÓN, NO COMO TARIFA. «Mayor valor
   cobrado según contrato» es la familia TA de la Res. 2284/2023. Al caer en
   FA, la defensa se arma como un problema de facturación y nunca se invoca
   la tarifa pactada, la homologación CUPS→SOAT ni el Manual Tarifario —que
   es justamente lo que tumba este tipo de glosa.
"""

from __future__ import annotations

import pytest

from app.services.citation_verifier import verificar_citas
from app.services.glosa_service import GlosaService, _neutralizar_alucinaciones_prompt

_DICTAMEN_REAL = (
    "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE FACTURACIÓN. "
    "EN VIRTUD DE ART. 168 LA LEY 100 DE 1993, QUE DISPONE «.», Y ART. 177 "
    "LA MISMA LEY, SE RECUERDA QUE LA FACTURACIÓN SE REALIZÓ CON BASE EN LA "
    "TARIFA SOAT PLENO."
)


class TestLaCitaVaciaSeVe:
    def test_el_verificador_la_marca_como_grave(self):
        r = verificar_citas(_DICTAMEN_REAL)
        vacias = [i for i in r["issues"] if i["tipo"] == "CITA_VACIA"]
        assert vacias, "la comilla vacía «.» tiene que aparecer como hallazgo"
        assert vacias[0]["severidad"] == "ALTA"
        assert r["tiene_problemas_graves"] is True

    def test_ya_no_sale_el_sello_de_cero_hallazgos(self):
        """Lo que veía el auditor: «7 citas verificadas · 0 hallazgos»."""
        r = verificar_citas(_DICTAMEN_REAL)
        assert len(r["issues"]) >= 1
        assert r["ok"] < r["total_citas"]

    def test_tambien_con_comillas_rectas(self):
        r = verificar_citas('EL ART. 57 DE LA LEY 1438 DE 2011 DISPONE: "".')
        assert any(i["tipo"] == "CITA_VACIA" for i in r["issues"])

    @pytest.mark.parametrize(
        "texto",
        [
            "SE APLICA EL PRINCIPIO «PACTA SUNT SERVANDA» AL CONTRATO.",
            "LA TARIFA ES «SOAT» PLENO.",
            "EL CÓDIGO DE RESPUESTA ES «RE9901».",
        ],
    )
    def test_una_cita_corta_de_verdad_no_se_marca(self, texto):
        """Una cita corta con contenido no es una cita vacía."""
        r = verificar_citas(texto)
        assert not [i for i in r["issues"] if i["tipo"] == "CITA_VACIA"]

    def test_sin_comillas_no_hay_nada_que_marcar(self):
        r = verificar_citas("EL ART. 57 DE LA LEY 1438 DE 2011 REGULA LOS PLAZOS.")
        assert not [i for i in r["issues"] if i["tipo"] == "CITA_VACIA"]


class TestLaCitaVaciaSeBorraDelDictamen:
    def test_desaparece_la_comilla_vacia(self):
        limpio = _neutralizar_alucinaciones_prompt(_DICTAMEN_REAL)
        assert "«.»" not in limpio
        assert "QUE DISPONE «" not in limpio

    def test_la_norma_citada_sobrevive(self):
        """Se borra la comilla vacía, no la referencia a la norma."""
        limpio = _neutralizar_alucinaciones_prompt(_DICTAMEN_REAL)
        assert "LEY 100 DE 1993" in limpio
        assert "ART. 177" in limpio

    def test_una_cita_de_verdad_no_se_toca(self):
        texto = (
            "EL ART. 1602 DEL CÓDIGO CIVIL DISPONE «TODO CONTRATO LEGALMENTE "
            "CELEBRADO ES UNA LEY PARA LOS CONTRATANTES»."
        )
        assert _neutralizar_alucinaciones_prompt(texto) == texto

    def test_es_idempotente(self):
        una = _neutralizar_alucinaciones_prompt(_DICTAMEN_REAL)
        assert _neutralizar_alucinaciones_prompt(una) == una


class TestMayorValorCobradoEsTarifa:
    @pytest.mark.parametrize(
        "texto",
        [
            "se glosa servicio por mayor valor cobradp segun contracto rx de rodilla",
            "MAYOR VALOR COBRADO SEGÚN CONTRATO",
            "se cobra por encima de lo pactado",
            "valor superior al contratado",
            "el valor facturado es superior al pactado",
            "no corresponde al valor pactado en el contrato",
        ],
    )
    def test_se_clasifica_como_tarifa(self, texto):
        assert GlosaService._determinar_tipo_glosa(None, "", texto) == "TA_TARIFA"

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("falta epicrisis y ordenes medicas", "SO_SOPORTES"),
            ("servicio no autorizado, sin orden previa", "AU_AUTORIZACION"),
            ("no incluido en el plan de beneficios", "CO_COBERTURA"),
            ("glosa extemporanea", "EXT_EXTEMPORANEA"),
        ],
    )
    def test_las_demas_familias_no_se_movieron(self, texto, esperado):
        assert GlosaService._determinar_tipo_glosa(None, "", texto) == esperado

    def test_el_prefijo_explicito_sigue_mandando(self):
        """Si la EPS ya mandó el código TA/SO, ese manda sobre el texto."""
        assert GlosaService._determinar_tipo_glosa(None, "SO", "mayor valor cobrado") == (
            "SO_SOPORTES"
        )
