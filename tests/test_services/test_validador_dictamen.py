"""Tests del validador de dictamen pre-radicación (R51 P3)."""
from __future__ import annotations

from app.services.validador_dictamen import (
    _contar_palabras,
    _limpiar_html,
    check_apertura,
    check_cups_real,
    check_enumeracion,
    check_extension,
    check_invitacion_conciliacion,
    check_normas_citadas,
    check_placeholders,
    check_sin_cifras_inventadas,
    evaluar_dictamen,
)


class TestHelpers:
    def test_limpiar_html(self):
        r = _limpiar_html("<p>Hola <b>mundo</b></p>")
        assert "<" not in r
        assert "Hola" in r and "mundo" in r

    def test_contar_palabras(self):
        assert _contar_palabras("uno dos tres") == 3
        assert _contar_palabras("") == 0


class TestCheckApertura:
    def test_inicio_correcto_aprueba(self):
        r = check_apertura("ESE HUS NO ACEPTA LA GLOSA aplicada...")
        assert r["aprobado"] is True

    def test_respetuosamente_falla(self):
        """Anti-patrón: nunca empezar con 'respetuosamente'."""
        r = check_apertura("RESPETUOSAMENTE, se solicita revisar...")
        assert r["aprobado"] is False


class TestCheckCupsReal:
    def test_cups_presente_aprueba(self):
        r = check_cups_real("...CUPS 890750 consulta...", "890750")
        assert r["aprobado"] is True

    def test_cups_ausente_falla(self):
        r = check_cups_real("...cualquier texto sin cups...", "890750")
        assert r["aprobado"] is False

    def test_sin_esperado_pasa(self):
        """Si no hay cups esperado, el check no aplica."""
        r = check_cups_real("texto", None)
        assert r["aprobado"] is True


class TestCheckSinCifrasInventadas:
    def test_valor_real_aprueba(self):
        r = check_sin_cifras_inventadas("...por $168.563 según...", "168563")
        assert r["aprobado"] is True

    def test_sin_cifras_aprueba(self):
        """Si no se cita ninguna cifra, el check aprueba."""
        r = check_sin_cifras_inventadas("dictamen sin valores monetarios", "")
        assert r["aprobado"] is True

    def test_cifras_sin_valor_real_falla(self):
        """Sin valor_original pero con cifras → sospecha de inventadas."""
        r = check_sin_cifras_inventadas("...por $50.000 de diferencia...", "")
        assert r["aprobado"] is False


class TestCheckNormas:
    def test_con_normas_aprueba(self):
        t = "según Ley 1438 de 2011 Art. 57 y Resolución 2284 de 2023..."
        r = check_normas_citadas(t, "TA0201")
        assert r["aprobado"] is True

    def test_sin_normas_falla(self):
        r = check_normas_citadas("texto sin citas", "TA0201")
        assert r["aprobado"] is False


class TestCheckExtension:
    def test_extension_adecuada(self):
        """Rango esperado 230-310 palabras (con margen 180-320)."""
        texto = "palabra " * 260
        r = check_extension(texto)
        assert r["aprobado"] is True

    def test_muy_corto(self):
        r = check_extension("solo 3 palabras")
        assert r["aprobado"] is False

    def test_muy_largo(self):
        texto = "palabra " * 2000
        r = check_extension(texto)
        assert r["aprobado"] is False


class TestCheckPlaceholders:
    def test_sin_placeholders_aprueba(self):
        r = check_placeholders("Dictamen legítimo sin placeholders inventados.")
        assert r["aprobado"] is True

    def test_con_corchetes_falla(self):
        r = check_placeholders("El valor es $[INSERTAR_AQUI]")
        assert r["aprobado"] is False

    def test_con_placeholder_simple_falla(self):
        r = check_placeholders("Factura [NUMERO_FACTURA] pagada")
        assert r["aprobado"] is False


class TestEvaluarDictamen:
    def test_dictamen_completo_score_alto(self):
        texto = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS SOBRE "
            "EL CÓDIGO TA0201, INTERPUESTA POR FAMISANAR. "
            "El valor facturado $168.563 corresponde a tarifa pactada según "
            "Contrato S-13-1-03-1-04958. "
            "De conformidad con el Artículo 57 de la Ley 1438 de 2011 y "
            "la Resolución 2284 de 2023 (Manual Único de Glosas), "
            "y el Artículo 871 del Código de Comercio (buena fe contractual), "
            "se solicita respetuosamente el LEVANTAMIENTO de la glosa. "
            "En subsidio, se invita a MESA DE CONCILIACIÓN de auditoría. "
        ) * 5
        r = evaluar_dictamen(
            texto, codigo_glosa="TA0201",
            cups_esperado="890750", valor_original="168563",
            codigo_respuesta="RE9901", eps="FAMISANAR",
        )
        assert "score" in r
        assert "checks" in r
        assert r["total"] > 0
        assert r["aprobados"] > 0

    def test_dictamen_vacio_score_muy_bajo(self):
        r = evaluar_dictamen("", codigo_glosa="TA0201")
        assert r["score"] <= 50
