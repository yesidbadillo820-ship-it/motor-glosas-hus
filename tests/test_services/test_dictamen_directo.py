"""Tests del generador de dictamen directo sin LLM (R-cerebro #10)."""
from __future__ import annotations

import re

from app.services.auditor_glosa import auditar
from app.services.dictamen_directo import (
    generar_dictamen_directo,
    puede_emitir_directo,
)


def _aud_caso_real():
    """Auditoría del caso real TA0801 con score 75 + 2 ALTA."""
    texto = (
        "TA0801 - CUPS 902210 - Valor objetado: $3.151 - SE GLOSA MVC "
        "SIN CONTRATO ENTRE LAS PARTES SE RECONOCE A SOAT VIGENTE."
    )
    return auditar(
        texto, tiene_contrato=True, valor_pactado=33487,
        cups="902210", contexto_pdf="X" * 1000,
    )


class TestPuedeEmitirDirecto:
    def test_caso_unívoco_devuelve_true(self):
        a = _aud_caso_real()
        ok = puede_emitir_directo(
            a, codigo="TA0801", eps="DISPENSARIO MEDICO",
            cups="902210", valor_objetado=3151,
            valor_facturado=33487, valor_pactado=33487,
            tiene_contrato=True,
            numero_contrato="440-DIGSA",
        )
        assert ok is True

    def test_score_bajo_devuelve_false(self):
        # score < 70 → no
        a = {"score_evidencia": 50, "accion_sugerida": "DEFENDER",
             "n_hallazgos_alta": 1, "hallazgos": [
                 {"id": "afirmacion_sin_contrato_falsa", "severidad": "ALTA",
                  "afirmacion_eps": "x", "realidad_sistema": "y",
                  "refutacion_sugerida": "z"}]}
        ok = puede_emitir_directo(
            a, codigo="TA0801", eps="X", cups="902210",
            valor_objetado=1000, valor_facturado=1000,
            valor_pactado=1000, tiene_contrato=True,
            numero_contrato="X",
        )
        assert ok is False

    def test_caso_excedente_devuelve_false(self):
        # Si hay excedente facturado > pactado, NO emitir directo
        # (el LLM redacta mejor respuestas mixtas).
        a = _aud_caso_real()
        ok = puede_emitir_directo(
            a, codigo="TA0801", eps="DISPENSARIO MEDICO",
            cups="902210", valor_objetado=3151,
            valor_facturado=41151, valor_pactado=33487,  # excedente
            tiene_contrato=True, numero_contrato="440-DIGSA",
        )
        assert ok is False

    def test_aceptar_excedente_explicito_devuelve_false(self):
        a = _aud_caso_real()
        ok = puede_emitir_directo(
            a, codigo="TA0801", eps="X", cups="902210",
            valor_objetado=3151, valor_facturado=33487,
            valor_pactado=33487, tiene_contrato=True,
            numero_contrato="X", accion_excedente="ACEPTAR_TOTAL",
        )
        assert ok is False

    def test_sin_contrato_devuelve_false(self):
        a = _aud_caso_real()
        ok = puede_emitir_directo(
            a, codigo="TA0801", eps="X", cups="902210",
            valor_objetado=3151, valor_facturado=33487,
            valor_pactado=33487, tiene_contrato=False,
            numero_contrato=None,
        )
        assert ok is False

    def test_valor_objetado_cero_devuelve_false(self):
        a = _aud_caso_real()
        ok = puede_emitir_directo(
            a, codigo="TA0801", eps="X", cups="902210",
            valor_objetado=0, valor_facturado=0,
            valor_pactado=33487, tiene_contrato=True,
            numero_contrato="X",
        )
        assert ok is False

    def test_codigo_prefijo_desconocido_devuelve_false(self):
        a = _aud_caso_real()
        ok = puede_emitir_directo(
            a, codigo="ZZ0001", eps="X", cups="902210",
            valor_objetado=1000, valor_facturado=1000,
            valor_pactado=1000, tiene_contrato=True,
            numero_contrato="X",
        )
        assert ok is False


class TestGenerarDictamen:
    def test_genera_xml_completo(self):
        a = _aud_caso_real()
        xml = generar_dictamen_directo(
            a, codigo="TA0801", eps="DISPENSARIO MEDICO BUCARAMANGA",
            cups="902210", servicio="HEMOGRAMA IV AUTOMATIZADO",
            valor_objetado=3151, valor_facturado=33487,
            valor_pactado=33487, numero_contrato="440-DIGSA/DMBUG-2025",
        )
        assert xml is not None
        # Estructura XML
        for tag in ("paciente", "servicio", "contrato", "tarifa",
                    "accion", "valor_aceptar", "valor_defender",
                    "normas_clave", "argumento"):
            assert f"<{tag}>" in xml
            assert f"</{tag}>" in xml
        # Apertura obligatoria
        arg = re.search(r"<argumento>(.*?)</argumento>", xml, re.DOTALL).group(1)
        assert arg.lstrip().startswith("ESE HUS NO ACEPTA")
        # Email institucional
        assert "CARTERA@HUS.GOV.CO" in arg
        assert "GLOSASYDEVOLUCIONES@HUS.GOV.CO" in arg
        # Cita literal Art. 1602
        assert "ARTÍCULO 1602" in arg
        assert "«TODO CONTRATO LEGALMENTE CELEBRADO" in arg
        # Régimen Sanidad Militar (DISPENSARIO MEDICO)
        assert "DECRETO 1795" in arg
        # Acción correcta
        assert "<accion>DEFENDER_TOTAL</accion>" in xml
        assert "<valor_aceptar>0</valor_aceptar>" in xml
        assert "<valor_defender>3151</valor_defender>" in xml
        # Longitud razonable (no demasiado corto ni largo)
        n = len(arg.split())
        assert 130 <= n <= 340

    def test_refuta_punto_a_punto(self):
        # Verifica que el dictamen incluye refutaciones específicas
        # de los hallazgos del auditor (no genérico).
        a = _aud_caso_real()
        xml = generar_dictamen_directo(
            a, codigo="TA0801", eps="DISPENSARIO MEDICO",
            cups="902210", servicio="HEMOGRAMA IV",
            valor_objetado=3151, valor_facturado=33487,
            valor_pactado=33487, numero_contrato="440-DIGSA",
        )
        arg = re.search(r"<argumento>(.*?)</argumento>", xml, re.DOTALL).group(1)
        # Debe atacar la mentira de "sin contrato"
        assert "NO EXISTE CONTRATO" in arg or "REALIDAD DOCUMENTAL" in arg
        # Debe atacar el SOAT como sustituto indebido
        assert "SOAT" in arg
        # Debe usar enumeración técnica
        assert "EN PRIMER LUGAR" in arg

    def test_sin_hallazgos_devuelve_none(self):
        # Auditoría sin hallazgos mapeables → no se puede generar
        a = {"hallazgos": [
            {"id": "id_no_mapeada", "severidad": "ALTA",
             "afirmacion_eps": "x", "realidad_sistema": "y",
             "refutacion_sugerida": "z"}
        ], "score_evidencia": 70, "accion_sugerida": "DEFENDER_FUERTE"}
        xml = generar_dictamen_directo(
            a, codigo="TA0801", eps="X", cups="902210",
            servicio="X", valor_objetado=1000, valor_facturado=1000,
            valor_pactado=1000, numero_contrato="X",
        )
        assert xml is None

    def test_eps_no_militar_omite_decreto_1795(self):
        a = _aud_caso_real()
        xml = generar_dictamen_directo(
            a, codigo="TA0801", eps="COOSALUD",
            cups="902210", servicio="HEMOGRAMA",
            valor_objetado=3151, valor_facturado=33487,
            valor_pactado=33487, numero_contrato="X",
        )
        if xml:
            arg = re.search(r"<argumento>(.*?)</argumento>",
                            xml, re.DOTALL).group(1)
            assert "DECRETO 1795" not in arg
