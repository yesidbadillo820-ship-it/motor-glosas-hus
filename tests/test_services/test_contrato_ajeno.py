"""El contrato que la entidad invoca y no es el suyo.

PRUEBA 3 DE ESTRÉS (01-09-2026) — glosa AU0201, factura HUS0000602233.
FAMISANAR glosó $2.640.000 «CONFORME A LA CLÁUSULA DÉCIMA SEGUNDA DEL CONTRATO
440-DIGSA».

Dos cosas están mal ahí, y el dictamen GL-154 no dijo ninguna:

  • ese contrato NO es de FAMISANAR — está suscrito con la Dirección de Sanidad
    del Ejército, Dispensario Médico de Bucaramanga;
  • la cláusula décima segunda no existe en él (llega hasta la décima).

El motor sí trajo bien el contrato real de FAMISANAR (S-13-1-03-1-04958) y su
tarifa, pero se limitó a ponerlos en su recuadro. Ignorar el contrato ajeno en
vez de refutarlo deja el fundamento de la glosa en pie: lo que no se refuta se
da por aceptado.

Esto no se le pide a la IA: es comparar dos cadenas contra la malla.
"""

import pytest

from app.services.glosa_ia_prompts import get_contrato
from app.services.glosa_service import (
    _contratos_citados_en_glosa,
    _parrafo_contrato_ajeno,
)
from app.services.malla_contractual import titular_del_contrato

GLOSA = (
    "AU0201 | HUS0000602233 | FAMISANAR EPS\n"
    "SERVICIO PRESTADO SIN AUTORIZACION PREVIA. CONFORME A LA CLAUSULA DECIMA\n"
    "SEGUNDA DEL CONTRATO 440-DIGSA, TODA ATENCION NO URGENTE REQUIERE\n"
    "AUTORIZACION PREVIA EXPEDIDA POR LA EPS. NO SE APORTA DICHA AUTORIZACION.\n"
    "SE GLOSA LA TOTALIDAD DE LA ATENCION.\n"
    "VALOR FACTURADO: $2.640.000  VALOR GLOSADO: $2.640.000"
)


class TestSeSabeDeQuienEsCadaContrato:
    @pytest.mark.parametrize("numero", ["440-DIGSA", "440-DIGSA/DMBUG-2025"])
    def test_el_440_es_del_ejercito(self, numero: str):
        assert "EJÉRCITO" in titular_del_contrato(numero).upper()

    @pytest.mark.parametrize("numero", ["S-13-1-03-1-04958", "S13103104958"])
    def test_reconoce_el_mismo_contrato_con_y_sin_guiones(self, numero: str):
        """En la malla va «S13103104958»; la ficha lo muestra con guiones."""
        assert titular_del_contrato(numero) == "FAMISANAR EPS"

    def test_un_contrato_inventado_no_tiene_titular(self):
        assert titular_del_contrato("INVENTADO-999") == ""

    def test_un_fragmento_corto_no_empareja_con_cualquier_cosa(self):
        assert titular_del_contrato("44") == ""
        assert titular_del_contrato("") == ""


class TestSeDetectaLoQueLaEntidadCita:
    def test_saca_el_contrato_de_la_glosa(self):
        assert _contratos_citados_en_glosa(GLOSA) == ["440-DIGSA"]

    @pytest.mark.parametrize(
        "texto",
        [
            "SEGUN EL CONTRATO No. 02-01-06-00077-2017 LA TARIFA ES OTRA.",
            "conforme al contrato 02-01-06-00077-2017 vigente",
            "CONTRATO N° 02-01-06-00077-2017",
        ],
    )
    def test_aguanta_las_formas_de_citarlo(self, texto: str):
        assert _contratos_citados_en_glosa(texto) == ["02-01-06-00077-2017"]

    def test_no_confunde_prosa_con_un_numero(self):
        """«CONTRATO VIGENTE» no es un número de contrato."""
        assert _contratos_citados_en_glosa("EL CONTRATO VIGENTE ASI LO DISPONE") == []
        assert _contratos_citados_en_glosa("NO EXISTE CONTRATO SUSCRITO") == []

    def test_glosa_vacia_no_rompe(self):
        assert _contratos_citados_en_glosa("") == []


class TestLaRefutacion:
    def _p(self) -> str:
        return _parrafo_contrato_ajeno(GLOSA, get_contrato("FAMISANAR EPS"), "FAMISANAR EPS")

    def test_nombra_el_contrato_que_la_entidad_invoco(self):
        assert "440-DIGSA" in self._p()

    def test_nombra_al_verdadero_titular(self):
        """Es lo que hace la refutación verificable: la entidad lo comprueba."""
        assert "EJÉRCITO" in self._p()

    def test_nombra_el_contrato_que_si_nos_vincula(self):
        p = self._p()
        assert "S-13-1-03-1-04958" in p
        assert "FAMISANAR EPS" in p

    def test_invoca_la_relatividad_de_los_contratos(self):
        p = self._p()
        assert "RELATIVIDAD DE LOS CONTRATOS" in p
        assert "ART. 1602" in p

    def test_pide_la_clausula_del_contrato_correcto(self):
        assert "PRECISAR LA CLÁUSULA" in self._p()

    def test_no_afirma_que_el_contrato_ajeno_no_exista(self):
        """440-DIGSA SÍ existe. Lo que no es, es de FAMISANAR."""
        p = self._p().upper()
        assert "NO EXISTE" not in p
        assert "INEXISTENTE" not in p


class TestCuandoNoHayNadaQueRefutar:
    def test_callada_si_la_entidad_cita_el_contrato_correcto(self):
        g = "GLOSA POR EL CONTRATO S-13-1-03-1-04958 DE FAMISANAR."
        assert _parrafo_contrato_ajeno(g, get_contrato("FAMISANAR EPS"), "FAMISANAR EPS") == ""

    def test_callada_si_lo_cita_sin_guiones(self):
        g = "GLOSA POR EL CONTRATO S13103104958."
        assert _parrafo_contrato_ajeno(g, get_contrato("FAMISANAR EPS"), "FAMISANAR EPS") == ""

    def test_callada_si_la_entidad_no_cita_contrato(self):
        g = "AU0201 SERVICIO SIN AUTORIZACION PREVIA. SE GLOSA LA TOTALIDAD."
        assert _parrafo_contrato_ajeno(g, get_contrato("FAMISANAR EPS"), "FAMISANAR EPS") == ""

    def test_callada_si_el_motor_no_sabe_cual_es_el_nuestro(self):
        """Sin saber cuál es el propio, no se puede afirmar que el otro es ajeno."""
        ficha = {"numero": "SIN CONTRATO PACTADO"}
        assert _parrafo_contrato_ajeno(GLOSA, ficha, "LA PREVISORA") == ""

    def test_ficha_vacia_no_rompe(self):
        assert _parrafo_contrato_ajeno(GLOSA, None, "X") == ""
        assert _parrafo_contrato_ajeno(GLOSA, {}, "X") == ""


class TestVaPrimeroEnElArgumento:
    def test_el_motor_lo_pone_al_inicio(self):
        import io

        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert 'arg_ia = _parr_ctr + " " + arg_ia.lstrip()' in motor, (
            "la refutación dejó de ir primero: si va al final, el auditor de la "
            "entidad lee la defensa de fondo antes de saber que su fundamento cae"
        )

    def test_el_gestor_se_entera(self):
        import io

        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert "fundó su glosa en un contrato que no es el" in motor

    def test_nunca_tumba_el_dictamen(self):
        import io

        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert "[CONTRATO-AJENO] no aplicada" in motor
