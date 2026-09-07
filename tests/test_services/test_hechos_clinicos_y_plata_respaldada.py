"""Lo que dejaron las corridas del 02-09 en la pantalla real (pruebas 1 y 3).

Prueba 1 (TA0301, La Previsora). El dictamen salió por texto_fijo —la plantilla
determinista para tarifa sin contrato— y la red de «plata inventada» marcó
«SOAT PLENA» y «UVB» como si la IA los hubiera inventado. La ficha de La
Previsora dice literalmente «SOAT PLENO — UVB 2026 = $12.110»: la red acusaba
al motor de lo que el motor mismo puso. Falso positivo.

Prueba 3 (AU0201, FAMISANAR). El auditor leyó «TRIAGE II Y DOLOR TORÁCICO» y
lo tomó por invención. No lo era: el PDF adjunto dice «TRIAGE II — atención
prioritaria» y «dolor torácico opresivo». Pero su regla es correcta —si no hay
historia leída, no hay cuadro clínico que contar— y hoy nada la hacía cumplir.
Se vigilan los datos que se pueden cotejar exactos: triage, CIE-10 y fechas.
"""

import io

import pytest

from app.services.glosa_service import (
    _afirmacion_financiera_del_modelo,
    _hechos_clinicos_sin_respaldo,
)

FICHA_PREVISORA = (
    "SOAT PLENO — Manual Tarifario SOAT 2026 (Circular 047/2025 MinSalud + UVB 2026 = $12.110)"
)
PLANTILLA_SIN_CONTRATO = (
    "NO EXISTE CONTRATO PACTADO, POR LO QUE LA FACTURACIÓN SE REALIZÓ BAJO TARIFA "
    "SOAT PLENA. MANUAL TARIFARIO SOAT 2026 INDEXADO A UVB — VALOR UVB 2026: $12.110."
)
PDF_URGENCIAS = (
    "HISTORIA CLÍNICA — SERVICIO DE URGENCIAS\nFecha y hora de ingreso: 04/04/2026 · 02:14 horas\n"
    "Motivo de consulta: dolor torácico opresivo de dos horas de evolución.\n"
    "Clasificación en triage: TRIAGE II — atención prioritaria."
)


class TestLaRedDePlataYaNoAcusaAlMotor:
    def test_prueba_1_con_la_ficha_de_respaldo_no_marca_nada(self):
        assert _afirmacion_financiera_del_modelo(PLANTILLA_SIN_CONTRATO, FICHA_PREVISORA) == []

    def test_sin_respaldo_si_marca(self):
        """Sin ficha que lo sostenga, «SOAT PLENA» sigue siendo sospechoso."""
        assert _afirmacion_financiera_del_modelo(PLANTILLA_SIN_CONTRATO, "")

    def test_el_invento_de_gl149_sigue_cayendo(self):
        hallados = _afirmacion_financiera_del_modelo(
            "EL VALOR FACTURADO ES COMPATIBLE CON LA UVB VIGENTE Y EL FACTOR 0.80 PACTADO",
            "TARIFA NO DETERMINADA — sin la fecha del servicio no se puede afirmar cuál rige.",
        )
        assert any("COMPATIBLE" in h.upper() for h in hallados)
        assert any("FACTOR" in h.upper() for h in hallados)

    def test_plena_y_pleno_son_lo_mismo(self):
        assert _afirmacion_financiera_del_modelo("TARIFA SOAT PLENA", "SOAT PLENO") == []

    def test_la_plantilla_fija_ni_se_revisa(self):
        """Si el argumento no lo escribió la IA, no hay modelo que vigilar."""
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        i = motor.index("_es_de_la_ia = ")
        bloque = motor[i : i + 400]
        for m in ('"texto_fijo"', '"abstencion"', '"plantilla"'):
            assert m in bloque, m

    def test_el_respaldo_incluye_la_ficha_y_el_parrafo_del_motor(self):
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        i = motor.index("_respaldo_plata = ")
        bloque = motor[i : i + 300]
        assert '"tarifa"' in bloque and "_parr_tar" in bloque


class TestHechosClinicosConRespaldo:
    def test_prueba_3_el_triage_si_estaba_en_el_pdf(self):
        arg = "SE PRESTÓ EN VÍA DE URGENCIA VITAL CON TRIAGE II Y DOLOR TORÁCICO, EL 04/04/2026."
        assert _hechos_clinicos_sin_respaldo(arg, PDF_URGENCIAS) == []

    @pytest.mark.parametrize("nivel", ["2", "II", "NIVEL II", "nivel 2"])
    def test_romano_y_arabigo_son_el_mismo_triage(self, nivel: str):
        assert _hechos_clinicos_sin_respaldo(f"PACIENTE TRIAGE {nivel}", PDF_URGENCIAS) == []

    @pytest.mark.parametrize("fecha", ["04/04/2026", "4/4/2026"])
    def test_la_fecha_se_reconoce_con_y_sin_cero(self, fecha: str):
        assert _hechos_clinicos_sin_respaldo(f"INGRESO EL {fecha}", PDF_URGENCIAS) == []


class TestHechosClinicosSinRespaldo:
    def test_un_triage_que_no_esta_se_nombra(self):
        assert "TRIAGE III" in _hechos_clinicos_sin_respaldo("PACIENTE TRIAGE III", PDF_URGENCIAS)

    def test_una_fecha_que_no_esta_se_nombra(self):
        r = _hechos_clinicos_sin_respaldo("INGRESO EL 07/07/2026", PDF_URGENCIAS)
        assert "fecha 07/07/2026" in r

    def test_un_cie10_que_no_esta_se_nombra(self):
        assert "CIE-10 I20.0" in _hechos_clinicos_sin_respaldo("DIAGNÓSTICO I20.0", PDF_URGENCIAS)

    def test_sin_pdf_todo_dato_clinico_queda_sin_respaldo(self):
        """Es el caso que preocupa al auditor: sin historia leída, no hay triage."""
        r = _hechos_clinicos_sin_respaldo("TRIAGE II Y DOLOR TORÁCICO, INGRESO 04/04/2026", "")
        assert "TRIAGE II" in r and "fecha 04/04/2026" in r

    def test_argumento_vacio_no_rompe(self):
        assert _hechos_clinicos_sin_respaldo("", PDF_URGENCIAS) == []

    def test_no_se_repite_el_mismo_dato(self):
        r = _hechos_clinicos_sin_respaldo("TRIAGE III. REPITO: TRIAGE III.", PDF_URGENCIAS)
        assert r.count("TRIAGE III") == 1

    def test_avisa_pero_no_borra(self):
        """Quitar una oración clínica a ciegas deja la defensa sin sentido."""
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        i = motor.index("[CLINICO-SIN-RESPALDO]")
        assert "_correcciones.append" in motor[i - 900 : i]
        assert "dictamen = " not in motor[i - 600 : i]


class TestElPromptLoProhibe:
    def test_la_directriz_esta_al_arranque(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "PROHIBICIÓN ABSOLUTA — HECHOS CLÍNICOS Y CIFRAS" in SYSTEM_BASE
        assert SYSTEM_BASE.index("HECHOS CLÍNICOS Y CIFRAS") < SYSTEM_BASE.index("MISIÓN: Redactar")

    def test_sin_historia_el_argumento_es_normativo(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "NETAMENTE NORMATIVO" in SYSTEM_BASE
        assert "«TRIAGE II» solo si el PDF dice TRIAGE II" in SYSTEM_BASE
