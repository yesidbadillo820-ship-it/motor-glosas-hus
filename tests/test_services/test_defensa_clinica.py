"""Tests del banco de defensas clínicas (mejora #4).

Inyecta literatura clínica nivel 1A concreta (FDA/NICE/Cochrane/AHA) para
tecnología de alto costo, en vez de dejar a la IA en "autonomía médica"
genérica que la EPS desestima.
"""

from app.services.defensa_clinica import (
    auditar_literatura_citada,
    bloque_defensa_clinica_para_prompt,
    detectar_defensa_clinica,
)


class TestDeteccion:
    def test_tms(self):
        d = detectar_defensa_clinica("terapia de Estimulación Magnética Transcraneal (TMS)")
        assert d is not None
        assert "TMS" in d["titulo"]

    def test_da_vinci(self):
        d = detectar_defensa_clinica("prostatectomía radical asistida por robot da Vinci Xi")
        assert d is not None
        assert "robótica" in d["titulo"].lower()

    def test_cart_t(self):
        d = detectar_defensa_clinica("Tisagenlecleucel en linfoma B refractario")
        assert d is not None
        assert "CAR-T" in d["titulo"]

    def test_implante_coclear(self):
        d = detectar_defensa_clinica("implante coclear bilateral pediátrico")
        assert d is not None
        assert "coclear" in d["titulo"].lower()

    def test_epicel(self):
        d = detectar_defensa_clinica("aplicación de Epicel en quemado grave SCQ 45%")
        assert d is not None
        assert "Epicel" in d["titulo"]

    def test_norwood(self):
        d = detectar_defensa_clinica("cirugía de Norwood para HLHS")
        assert d is not None
        assert "Norwood" in d["titulo"]

    def test_hemofilia(self):
        d = detectar_defensa_clinica("hemofilia con inhibidores ≥ 5 BU, eptacog alfa")
        assert d is not None
        assert "Hemofilia" in d["titulo"]

    def test_iris_vih(self):
        d = detectar_defensa_clinica("síndrome de reconstitución inmune IRIS post-TARV")
        assert d is not None
        assert "IRIS" in d["titulo"]

    def test_caso_sin_tecnologia_cara(self):
        assert detectar_defensa_clinica("tarifa SOAT no pactada en contrato") is None
        assert detectar_defensa_clinica("") is None
        assert detectar_defensa_clinica(None) is None


class TestBloquePrompt:
    def test_bloque_incluye_evidencia_1a(self):
        bloque = bloque_defensa_clinica_para_prompt("paciente con da Vinci")
        assert "EVIDENCIA NIVEL 1A" in bloque
        assert "Cochrane" in bloque
        assert "autonomía médica" in bloque.lower()  # advertencia de no quedarse ahí

    def test_bloque_tms_cita_fda_nice(self):
        bloque = bloque_defensa_clinica_para_prompt("TMS en esquizofrenia refractaria")
        assert "FDA" in bloque
        assert "NICE" in bloque
        assert "Ley 1616/2013" in bloque

    def test_bloque_vacio_sin_tecnologia(self):
        assert bloque_defensa_clinica_para_prompt("consulta de control simple") == ""


class TestAuditorLiteratura:
    def test_solo_autonomia_falla(self):
        ok, msg = auditar_literatura_citada(
            "ESE HUS defiende por autonomía médica Ley 23/1981",
            "paciente con da Vinci robótico",
        )
        assert ok is False
        assert "literatura" in msg.lower()

    def test_con_literatura_pasa(self):
        ok, msg = auditar_literatura_citada(
            "conforme a Cochrane Review 2017 y EAU Guidelines, la vía robótica preserva continencia",
            "paciente con da Vinci robótico",
        )
        assert ok is True

    def test_caso_sin_tecnologia_no_aplica(self):
        ok, msg = auditar_literatura_citada(
            "ESE HUS no acepta la glosa de tarifa",
            "tarifa SOAT no pactada",
        )
        assert ok is True  # no es tecnología cara → no se exige literatura

    def test_dictamen_vacio_con_tecnologia_falla(self):
        ok, msg = auditar_literatura_citada("", "implante coclear bilateral")
        assert ok is False


class TestSinInvencion:
    """Cada defensa debe citar literatura real y conocida, no inventada."""

    def test_todas_las_defensas_tienen_evidencia_y_normas(self):
        from app.services.defensa_clinica import _BANCO_DEFENSAS

        for d in _BANCO_DEFENSAS:
            assert d["evidencia"], f"{d['key']} sin evidencia"
            assert d["argumento"], f"{d['key']} sin argumento"
            assert d["normas"], f"{d['key']} sin normas"
            assert d["titulo"], f"{d['key']} sin título"
