"""Segunda corrida de los cinco casos (08-09-2026), después de los arreglos.

Los arreglos anteriores funcionaron —paciente honesto, marcador de EPS fuera
del escrito, sello rojo, un solo aviso de soportes— y la corrida destapó
cuatro cosas nuevas:

  1. Caso 2 (SO3401): el verificador encontró un hallazgo de severidad ALTA
     —«afirma lo que dice un documento clínico y no se leyó ningún soporte»—
     y el dictamen salió SIN sello verde… pero tampoco bloqueado. El recuadro
     remataba: «El gestor decide si corrige o ignora — esto es solo
     orientativo». Un defecto que el propio motor llama GRAVE no es un
     consejo.

  2. Caso 1 (TA0701): la glosa objetaba $19.500 y el texto radicable decía
     «POR UN VALOR OBJETADO DE $ 19.». La entidad tiene la factura.

  3. Caso 1: ya no decía «SOAT PLENO», pero invocó el art. 87 del Decreto
     2423 de 1996 —la regla de los servicios SIN tarifa asignada— teniendo el
     recuadro del mismo dictamen un «Tarifa pactada: SOAT -15 %».

  4. La telemetría leía «$ 19.500» como 19,5 y «$ 1.240.000» reventaba: TODA
     glosa de más de un millón se contaba en el cajón «<100K».
"""

from __future__ import annotations

import pytest

from app.services.glosa_service import (
    _bloqueos_para_radicar,
    _cifra_del_escrito_no_es_la_de_la_glosa,
    _contradice_la_ficha_contractual,
)

COOSALUD = {
    "numero": "68001C00060340-24 / 68001S00060339-24",
    "tarifa": "SOAT -15 %",
    "factor": 0.85,
}


# ═══════════════════════════════════════════════════════════════════════
#  1 · Un hallazgo GRAVE bloquea; no es un consejo
# ═══════════════════════════════════════════════════════════════════════


def _citas(*severidades: str) -> dict:
    return {
        "verificado": True,
        "total_citas": 12,
        "issues": [{"severidad": s, "tipo": "AFIRMACION_SIN_SOPORTE"} for s in severidades],
    }


class TestElHallazgoGraveBloquea:
    def test_una_cita_alta_bloquea(self):
        motivos = _bloqueos_para_radicar("TEXTO LIMPIO.", _citas("ALTA"))
        assert motivos and "GRAVE" in motivos[0]

    def test_se_dice_cuantas_son(self):
        motivos = _bloqueos_para_radicar("TEXTO LIMPIO.", _citas("ALTA", "ALTA"))
        assert any("2 hallazgo" in m for m in motivos)

    def test_las_observaciones_menores_no_bloquean(self):
        assert _bloqueos_para_radicar("TEXTO LIMPIO.", _citas("MEDIA", "BAJA")) == []

    def test_sin_hallazgos_no_bloquea(self):
        assert _bloqueos_para_radicar("TEXTO LIMPIO.", _citas()) == []

    @pytest.mark.parametrize("vc", [None, {}, "no es un dict", 0, {"issues": None}])
    def test_una_verificacion_rara_no_rompe(self, vc):
        assert _bloqueos_para_radicar("TEXTO LIMPIO.", vc) == []

    def test_se_suma_a_los_bloqueos_del_texto(self):
        d = "⛔ NO RADICAR TODAVÍA: falta la epicrisis."
        motivos = _bloqueos_para_radicar(d, _citas("ALTA"))
        assert len(motivos) == 2

    def test_no_se_repiten_los_motivos(self):
        d = "⛔ NO RADICAR TODAVÍA … ⛔ NO RADICAR TODAVÍA otra vez"
        assert len(_bloqueos_para_radicar(d)) == 1

    def test_afirmar_soportes_sin_señalarlos_bloquea(self):
        """Caso 2: enumeró los nueve soportes sin un folio y sin un PDF."""
        d = "⚠ AFIRMA SIN PROBAR. El escrito dice que la factura se radicó con todos…"
        assert _bloqueos_para_radicar(d)


# ═══════════════════════════════════════════════════════════════════════
#  2 · La cifra del escrito tiene que ser la de la glosa
# ═══════════════════════════════════════════════════════════════════════


class TestLaCifraDelEscrito:
    def test_el_caso_real(self):
        """«POR UN VALOR OBJETADO DE $ 19.» cuando lo objetado era $19.500."""
        d = "ESE HUS NO ACEPTA GLOSA … POR UN VALOR OBJETADO DE $ 19. EN VIRTUD DE…"
        malas = _cifra_del_escrito_no_es_la_de_la_glosa(d, "$ 19.500")
        assert malas, "una cifra cortada tiene que saltar"
        assert "19.500" in malas[0]

    def test_la_cifra_correcta_no_se_marca(self):
        d = "POR UN VALOR OBJETADO DE $ 19.500. SE SOLICITA EL LEVANTAMIENTO."
        assert _cifra_del_escrito_no_es_la_de_la_glosa(d, "$ 19.500") == []

    def test_el_mismo_valor_escrito_sin_puntos(self):
        d = "POR UN VALOR OBJETADO DE $ 19500."
        assert _cifra_del_escrito_no_es_la_de_la_glosa(d, "$ 19.500") == []

    def test_millones(self):
        d = "VALOR OBJETADO DE $ 1.240.000."
        assert _cifra_del_escrito_no_es_la_de_la_glosa(d, "$ 1.240.000") == []
        d_malo = "VALOR OBJETADO DE $ 1.240."
        assert _cifra_del_escrito_no_es_la_de_la_glosa(d_malo, "$ 1.240.000")

    def test_las_otras_cifras_del_escrito_no_se_tocan(self):
        """Topes, valores de contrato y la UVB tienen sus propias redes."""
        d = (
            "VALOR OBJETADO DE $ 19.500. EL TOPE CONTRACTUAL ES DE $ 900.000 Y LA "
            "UVB 2026 ES $ 12.110."
        )
        assert _cifra_del_escrito_no_es_la_de_la_glosa(d, "$ 19.500") == []

    def test_sin_valor_objetado_no_se_inventa_comparacion(self):
        d = "POR UN VALOR OBJETADO DE $ 19."
        for vacio in ("", None, "0", "$ 0"):
            assert _cifra_del_escrito_no_es_la_de_la_glosa(d, vacio) == []

    def test_un_peso_de_diferencia_no_es_contradiccion(self):
        d = "VALOR OBJETADO DE $ 19.501."
        assert _cifra_del_escrito_no_es_la_de_la_glosa(d, "$ 19.500") == []

    def test_escrito_vacio_no_rompe(self):
        assert _cifra_del_escrito_no_es_la_de_la_glosa("", "$ 19.500") == []
        assert _cifra_del_escrito_no_es_la_de_la_glosa(None, "$ 19.500") == []

    def test_esto_bloquea(self):
        d = "<h4>LA CIFRA DEL ESCRITO NO ES LA DE LA GLOSA</h4>"
        assert _bloqueos_para_radicar(d)


# ═══════════════════════════════════════════════════════════════════════
#  3 · La norma del vacío tarifario, teniendo pacto
# ═══════════════════════════════════════════════════════════════════════


class TestLaNormaDelVacioTarifario:
    def test_el_caso_real(self):
        d = (
            "LA LIQUIDACIÓN CORRECTA SE AJUSTA AL ARTÍCULO 87 DEL DECRETO 2423 DE 1996 "
            "QUE DISPONE QUE CUANDO UN PROCEDIMIENTO NO SE ENCUENTRE DEFINIDO SE "
            "RECONOCERÁ POR LA TARIFA QUE TENGA DEFINIDA LA INSTITUCIÓN."
        )
        h = _contradice_la_ficha_contractual(d, COOSALUD)
        assert h, "invocar la norma del vacío teniendo pacto es contradecirse"
        assert "SOAT -15 %" in " ".join(h)

    def test_tambien_al_reves(self):
        d = "SEGÚN EL DECRETO 2423 DE 1996, ARTÍCULO 87, LA TARIFA INSTITUCIONAL RIGE."
        assert _contradice_la_ficha_contractual(d, COOSALUD)

    def test_la_frase_del_vacio_sin_citar_la_norma(self):
        d = "EL PROCEDIMIENTO NO TENGA ASIGNADA TARIFA EN EL MANUAL."
        assert _contradice_la_ficha_contractual(d, COOSALUD)

    def test_sin_pacto_esa_norma_es_legitima(self):
        """A falta de tarifa pactada, el art. 87 es exactamente lo que aplica."""
        ficha = {"numero": "SIN CONTRATO PACTADO", "tarifa": "SOAT PLENO", "factor": 1.0}
        d = "SE AJUSTA AL ARTÍCULO 87 DEL DECRETO 2423 DE 1996."
        assert _contradice_la_ficha_contractual(d, ficha) == []

    def test_citar_otro_articulo_del_mismo_decreto_no_se_marca(self):
        d = "SEGÚN EL ARTÍCULO 12 DEL DECRETO 2423 DE 1996, LA TARIFA SE INDEXA."
        assert _contradice_la_ficha_contractual(d, COOSALUD) == []


# ═══════════════════════════════════════════════════════════════════════
#  4 · La telemetría contaba mal TODAS las glosas grandes
# ═══════════════════════════════════════════════════════════════════════


class TestElValorParaLaTelemetria:
    """El punto de miles colombiano no es un separador decimal."""

    @pytest.mark.parametrize(
        "crudo,esperado",
        [
            ("$ 19.500", 19_500),
            ("$ 1.240.000", 1_240_000),
            ("$ 8.400.000", 8_400_000),
            ("$ 420.000", 420_000),
            ("19500", 19_500),
        ],
    )
    def test_se_lee_el_valor_de_verdad(self, crudo, esperado):
        from app.utils.moneda import parse_valor_cop

        assert parse_valor_cop(crudo) == esperado

    def test_el_analisis_ya_no_usa_el_parseo_ingenuo(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert 'float(_re.sub(r"[^\\d.]", "", valor_raw or "") or 0)' not in src
        assert "parse_valor_cop as _pvc_tel" in src
