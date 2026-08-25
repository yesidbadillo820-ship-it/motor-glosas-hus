"""La cita del Art. 168 no se salva por una palabra de menos (GL-198).

QUÉ PASÓ. En la auditoría independiente de nueve dictámenes, el expediente
GL-198 (COMPENSAR) salió impreso con esta frase:

    «EN VIRTUD DE LO DISPUESTO EN EL ARTÍCULO 168 LA LEY 100 DE 1993…»

Nótese que falta el «DE» entre «168» y «LA LEY». La glosa de ese expediente
no era de urgencias, así que el motor tenía una defensa puesta para tumbar
esa cita — y no la tumbó. La razón: el patrón que la buscaba solo aceptaba
«DE LA LEY» o «DE LEY», y esa palabra que la IA se comió bastó para que la
cita inaplicable llegara hasta el papel que firma el auditor.

QUÉ CUIDA ESTA PRUEBA. Que las cuatro maneras de escribir el conector caigan
igual — «DE LA LEY», «DE LEY», «LA LEY» y «LEY» pelada — tanto para el
Art. 168 como para el Art. 177. Si alguien vuelve a angostar el patrón,
estas pruebas se ponen rojas antes de que el error salga a producción.
"""

import pytest

from app.services.glosa_service import (
    _neutralizar_art_168_fuera_de_contexto,
    _neutralizar_art_177_relleno,
)

# Glosa que NO es de urgencias: es un cobro de tarifa por algo programado.
# Con este texto, citar el Art. 168 (atención inicial de urgencias) o el
# Art. 177 (deber de la EPS de movilizar recursos al POS) está fuera de lugar.
GLOSA_DE_TARIFA = (
    "GLOSA POR TARIFA. SE OBJETA EL VALOR COBRADO DEL PROCEDIMIENTO "
    "ELECTIVO PROGRAMADO. NO CORRESPONDE AL MANUAL PACTADO."
)

CONECTORES = [
    "DE LA LEY",  # la forma correcta
    "DE LEY",  # sin el artículo
    "LA LEY",  # ← la de GL-198: sin el «DE»
    "LEY",  # pelada
]


class TestArt168NoSeSalvaPorUnaPalabra:
    @pytest.mark.parametrize("conector", CONECTORES)
    def test_las_cuatro_formas_del_conector_caen(self, conector):
        dictamen = (
            f"EN VIRTUD DE LO DISPUESTO EN EL ARTÍCULO 168 {conector} 100 DE 1993, "
            "LA IPS PRESTÓ EL SERVICIO Y LA EPS DEBE RECONOCERLO."
        )
        resultado = _neutralizar_art_168_fuera_de_contexto(dictamen, GLOSA_DE_TARIFA)
        assert resultado != dictamen, f"la cita se escapó con el conector «{conector}»"
        assert "168" not in resultado

    def test_la_frase_exacta_del_expediente_gl198(self):
        """El renglón tal cual salió impreso, sin retocarle nada."""
        dictamen = (
            "EN VIRTUD DE LO DISPUESTO EN EL ARTÍCULO 168 LA LEY 100 DE 1993, "
            "LA ENTIDAD RESPONSABLE DE PAGO DEBE GARANTIZAR LA ATENCIÓN."
        )
        resultado = _neutralizar_art_168_fuera_de_contexto(dictamen, GLOSA_DE_TARIFA)
        assert "ARTÍCULO 168" not in resultado
        assert "LEY 100" not in resultado

    def test_cuando_si_es_urgencia_la_cita_se_respeta(self):
        """La defensa no puede volverse un borrador ciego: si la glosa sí es
        de urgencias, el Art. 168 es la norma correcta y se queda."""
        glosa_urgencias = (
            "PACIENTE INGRESA POR URGENCIAS EN ESTADO CRÍTICO. SE GLOSA LA "
            "ATENCIÓN INICIAL DE URGENCIAS POR FALTA DE AUTORIZACIÓN."
        )
        dictamen = "EN VIRTUD DEL ARTÍCULO 168 LA LEY 100 DE 1993 SE RESPONDE."
        assert _neutralizar_art_168_fuera_de_contexto(dictamen, glosa_urgencias) == dictamen


class TestArt177NoSeSalvaPorUnaPalabra:
    @pytest.mark.parametrize("conector", CONECTORES)
    def test_las_cuatro_formas_del_conector_caen(self, conector):
        dictamen = f"RIGE EL MANUAL TARIFARIO CONFORME AL ARTÍCULO 177 {conector} 100 DE 1993."
        resultado = _neutralizar_art_177_relleno(dictamen, GLOSA_DE_TARIFA, "TA2902")
        assert resultado != dictamen, f"la cita se escapó con el conector «{conector}»"
        assert "177" not in resultado

    def test_en_debate_de_cobertura_la_cita_se_respeta(self):
        """Si la glosa sí es de cobertura (código CO), el Art. 177 aplica."""
        glosa_cobertura = "GLOSA CO0101 POR SERVICIO NO INCLUIDO EN EL PBS."
        dictamen = "CONFORME AL ARTÍCULO 177 LA LEY 100 DE 1993, LA EPS DEBE PAGAR."
        assert _neutralizar_art_177_relleno(dictamen, glosa_cobertura, "CO0101") == dictamen
