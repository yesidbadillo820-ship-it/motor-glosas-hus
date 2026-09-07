"""La ficha contractual manda sobre lo que escriba el modelo.

PRUEBA 2 DE ESTRÉS (31-08-2026) — glosa CL4506, factura HUS0000601892,
NUEVA E.P.S. S.A. - SUBSIDIADO, sin fecha del servicio en el formulario.

El dictamen salió con estas dos líneas, una encima de la otra:

    Contrato: 02-01-06-00077-2017
    Tarifa pactada: SOAT PLENO

Las dos son falsas a la vez. Ese contrato pactaba SOAT −20 % y su vigencia
terminó el 31/03/2026. Decirle a NUEVA EPS que lo PACTADO es SOAT pleno, en
una glosa que objeta precisamente la tarifa, es firmarle que el hospital
cobró de más.

El arreglo del prompt (e23a886) ya ponía «TARIFA NO DETERMINADA» en la ficha
que entra al modelo. El modelo lo limpió: se quedó con el número bonito y
con «SOAT PLENO» —que el propio esquema le ofrecía como valor válido—. De
ahí estas pruebas: la ficha se impone después, no se le pide permiso.
"""

import io

import pytest

from app.services.glosa_ia_prompts import get_contrato

MOTOR = io.open("app/services/glosa_service.py", encoding="utf-8").read()
PROMPTS = io.open("app/services/glosa_ia_prompts.py", encoding="utf-8").read()


class TestLaFichaDiceLaVerdad:
    """Lo que ya funcionaba y no se puede perder."""

    def test_sin_fecha_la_tarifa_queda_indeterminada(self):
        ficha = get_contrato("NUEVA EPS", None)
        assert ficha.get("_vigencia_vencida") is True
        assert ficha.get("_tarifa_indeterminada") is True
        assert ficha["tarifa"].startswith("TARIFA NO DETERMINADA")

    def test_nombra_el_factor_que_estaba_en_juego(self):
        """Sin el 0.80 a la vista el gestor no sabe qué se está regalando."""
        ficha = get_contrato("NUEVA EPS", None)
        assert "0.80" in ficha["tarifa"]

    def test_el_numero_lleva_la_advertencia_y_no_solo_el_numero(self):
        ficha = get_contrato("NUEVA EPS", None)
        assert "VIGENCIA TERMINADA" in ficha["numero"]
        assert "02-01-06-00077-2017" in ficha["numero"]

    def test_no_dice_que_no_habia_contrato(self):
        """Negar un contrato que sí existió también es mentir."""
        ficha = get_contrato("NUEVA EPS", None)
        assert "SIN CONTRATO PACTADO" not in ficha["numero"].upper()


class TestElMotorNoLeCreeAlModelo:
    def test_existe_la_guarda_que_pisa_el_xml(self):
        assert "_ficha_vig" in MOTOR, "se perdió la guarda de vigencia vencida"
        assert 'if _ficha_vig and _ficha_vig.get("_vigencia_vencida"):' in MOTOR

    def test_la_guarda_pisa_las_dos_casillas(self):
        assert "contrato_ia = _num_ficha" in MOTOR
        assert "tarifa_ia = _tar_ficha" in MOTOR

    def test_solo_pisa_cuando_la_vigencia_vencio(self):
        """Con contrato al día el XML del modelo sigue mandando."""
        assert "_vigencia_vencida" in MOTOR
        assert "contrato_ia = _num_ficha" in MOTOR.split("_vigencia_vencida")[-1]

    def test_el_gestor_se_entera_de_la_correccion(self):
        assert "_correcciones_previas" in MOTOR
        assert 'locals().get("_correcciones_previas") or []' in MOTOR
        assert "TARIFA NO DETERMINADA" in MOTOR

    def test_la_guarda_nunca_tumba_el_dictamen(self):
        assert "[VIGENCIA-VENCIDA] guarda no aplicada" in MOTOR


class TestLaEtiquetaNoSeContradiceConSuValor:
    def test_vigencia_terminada_no_se_llama_pactada(self):
        assert '"VIGENCIA TERMINADA" in _c_up' in MOTOR

    def test_tarifa_no_determinada_no_se_llama_pactada(self):
        assert '"NO DETERMINADA" in _t_up' in MOTOR

    def test_sigue_cubriendo_el_caso_viejo_sin_contrato(self):
        """El arreglo del 25-08 (HUS0000538289) no se puede perder."""
        assert '"SIN CONTRATO" in _c_up' in MOTOR


class TestElEsquemaYaNoOfreceLaMentira:
    def test_el_esquema_admite_la_tarifa_indeterminada(self):
        assert "TARIFA NO DETERMINADA" in PROMPTS

    def test_le_prohibe_cambiarla_por_soat_pleno(self):
        i = PROMPTS.find("<tarifa>Tarifa pactada")
        assert i != -1, "cambió el esquema de salida"
        renglon = PROMPTS[i : PROMPTS.find("\n", i)]
        assert "PROHIBIDO" in renglon
        assert "COPIADO TAL CUAL" in renglon


class TestNoSeRompioLoDeLasAseguradorasSoat:
    """Prueba 1 (TA0301, La Previsora): sin contrato de ninguna clase."""

    @pytest.mark.parametrize("nombre", ["LA PREVISORA S.A. — SOAT", "LA PREVISORA S.A."])
    def test_la_previsora_sigue_sin_contrato_y_a_soat_pleno(self, nombre):
        ficha = get_contrato(nombre, None)
        assert not ficha.get("_vigencia_vencida"), (
            "La Previsora no tiene contrato vencido: no tiene contrato. "
            "Si esto falla volvió a heredar el del magisterio."
        )
        assert "FOMAG" not in str(ficha.get("numero", "")).upper()
