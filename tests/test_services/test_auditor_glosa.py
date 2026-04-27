"""Tests del auditor pre-IA de glosas (R-cerebro #9)."""
from __future__ import annotations

from app.services.auditor_glosa import (
    auditar,
    bloque_auditoria_para_prompt,
    construir_bloque_auditoria,
)


class TestSinContrato:
    def test_eps_dice_sin_contrato_pero_si_hay(self):
        a = auditar(
            "SE GLOSA MVC SIN CONTRATO ENTRE LAS PARTES",
            tiene_contrato=True,
        )
        ids = [h["id"] for h in a["hallazgos"]]
        assert "afirmacion_sin_contrato_falsa" in ids
        assert a["score_evidencia"] >= 30

    def test_eps_dice_sin_contrato_y_efectivamente_no_hay(self):
        a = auditar(
            "SE GLOSA MVC SIN CONTRATO ENTRE LAS PARTES",
            tiene_contrato=False,
        )
        ids = [h["id"] for h in a["hallazgos"]]
        # Si efectivamente no hay contrato, no es mentira — no flag.
        assert "afirmacion_sin_contrato_falsa" not in ids


class TestSoatIndebido:
    def test_aplica_soat_con_contrato_y_tarifa(self):
        a = auditar(
            "SE RECONOCE TARIFA SOAT VIGENTE",
            tiene_contrato=True,
            valor_pactado=33487,
        )
        ids = [h["id"] for h in a["hallazgos"]]
        assert "soat_sustituto_indebido" in ids

    def test_aplica_soat_sin_contrato_no_es_indebido(self):
        a = auditar(
            "SE RECONOCE TARIFA SOAT VIGENTE",
            tiene_contrato=False,
        )
        ids = [h["id"] for h in a["hallazgos"]]
        assert "soat_sustituto_indebido" not in ids


class TestSinTarifa:
    def test_eps_dice_sin_tarifa_pero_si_hay(self):
        a = auditar(
            "NO HAY TARIFA PACTADA NI COTIZACION AVALADA",
            tiene_contrato=True, valor_pactado=33487,
            cups="902210",
        )
        ids = [h["id"] for h in a["hallazgos"]]
        assert "afirmacion_sin_tarifa_falsa" in ids


class TestObjetaMasQueExcedente:
    def test_objeta_mas_que_excedente_real(self):
        # facturado $247.663 - pactado $231.556 = excedente $16.107
        # objetado $168.563 >> $16.107 → flag
        a = auditar(
            "SE GLOSA LA DIFERENCIA",
            valor_facturado=247663, valor_pactado=231556,
            valor_objetado=168563,
        )
        ids = [h["id"] for h in a["hallazgos"]]
        assert "objeta_mas_que_excedente" in ids


class TestGlosaDiferenciaAbstracta:
    def test_glosa_la_diferencia_se_marca(self):
        a = auditar("SE GLOSA LA DIFERENCIA")
        ids = [h["id"] for h in a["hallazgos"]]
        assert "diferencia_sin_referente" in ids


class TestHistoriaAportada:
    def test_eps_dice_sin_historia_pero_pdf_existe(self):
        a = auditar(
            "FALTA HISTORIA CLINICA",
            contexto_pdf="X" * 1000,
        )
        ids = [h["id"] for h in a["hallazgos"]]
        assert "historia_aportada_objetada" in ids


class TestScoreEvidencia:
    def test_caso_completo_alto_score(self):
        # 3 hallazgos ALTA = 90, capeado a 100
        a = auditar(
            "SE GLOSA MVC SIN CONTRATO ENTRE LAS PARTES "
            "SE RECONOCE A SOAT VIGENTE. SE GLOSA LA DIFERENCIA",
            tiene_contrato=True,
            valor_facturado=41151, valor_pactado=33487, valor_objetado=3151,
            cups="902210",
        )
        assert a["score_evidencia"] >= 60
        assert a["accion_sugerida"] in ("DEFENDER", "DEFENDER_FUERTE")
        assert a["n_hallazgos_alta"] >= 2


class TestBloquePrompt:
    def test_sin_hallazgos_devuelve_vacio(self):
        a = auditar("texto neutro sin afirmaciones objetables")
        assert bloque_auditoria_para_prompt(a) == ""

    def test_con_hallazgos_genera_bloque(self):
        a = auditar(
            "SIN CONTRATO ENTRE LAS PARTES",
            tiene_contrato=True,
        )
        b = bloque_auditoria_para_prompt(a)
        assert "AUDITORÍA PREVIA" in b
        assert "INCONSISTENCIAS" in b
        assert "ALTA" in b


class TestConstruirIntegrado:
    def test_un_paso(self):
        b = construir_bloque_auditoria(
            "SIN CONTRATO ENTRE LAS PARTES SE RECONOCE A SOAT",
            tiene_contrato=True,
            valor_pactado=33487,
        )
        assert "AUDITORÍA" in b
        assert "soat" in b.lower() or "SOAT" in b

    def test_un_paso_sin_input_devuelve_vacio(self):
        assert construir_bloque_auditoria("") == ""
