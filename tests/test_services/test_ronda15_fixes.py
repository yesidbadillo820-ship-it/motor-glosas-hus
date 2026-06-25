"""Tests de regresión ronda 15 (25-jun-2026) — 7 bugs detectados tras ronda 14.

Yesid pegó 3 dictámenes más (Cart-T $5.847M, Hemofilia $234M, DPP $98M).
Algunos fixes de ronda 14 funcionaron (Bug L en caso 1, K UVB, I v2 header)
pero los nuevos casos expusieron:

  A v4 — CUM con sufijo "-X" sigue confundiéndose con CUPS.
  B v4 — placeholders rotos vuelven en minúsculas y con "/a" suelto.
  L v2 — el umbral 55% no se dispara en casos 2 y 3.
  O v2 — la IA ignora instrucciones explícitas del usuario.
  Q — IA INVENTA citas textuales entre comillas (peor alucinación).
  R — Dropdown EPS errado gana al texto.
  P v2 — más normas faltantes en corpus.
"""

from app.services.glosa_service import (
    _neutralizar_alucinaciones_prompt,
    _normalizar_mayusculas_sostenidas,
)
from app.services.normativa_completa import _TODAS_LAS_NORMAS


class TestBugAv4CumSufijo:
    def test_cum_8_digitos_mas_sufijo_se_neutraliza(self):
        # Caso 1 real: "CUPS 20235847-2" — era CUM Tisagenlecleucel
        texto = "EL CUPS 20235847-2 DEL TISAGENLECLEUCEL"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "20235847-2" not in resultado
        assert "medicamento facturado" in resultado.lower()

    def test_cum_norepinefrina_con_sufijo_se_neutraliza(self):
        texto = "USO DE CUPS 20002174-1 PARA SOPORTE HEMODINAMICO"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "20002174-1" not in resultado

    def test_cups_real_alfanumerico_intacto(self):
        # FMQ0113 sigue siendo CUPS real, no se toca
        texto = "kit FMQ0113 (CATÉTER)"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "FMQ0113" in resultado


class TestBugBv4Placeholders:
    def test_codigo_la_glosa_aplicada_minuscula(self):
        # Caso 1 real (lower después de Bug L)
        texto = "sobre el código la glosa aplicada/a, aplicada por SANITAS"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "/a, aplicada" not in resultado
        assert "/a," not in resultado

    def test_codigo_la_glosa_aplicada_mayuscula(self):
        # Caso 3 real (UPPER)
        texto = "SOBRE EL CÓDIGO LA GLOSA APLICADA/A APLICADA POR COMPENSAR"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "/A APLICADA" not in resultado

    def test_paciente_identificado_suelto_se_remueve(self):
        # Caso 3: "el paciente identificado en el expediente CUMPLIÓ..."
        texto = "la el paciente identificado en el expediente CUMPLIÓ con los requisitos"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "el paciente identificado en el expediente CUMPLIÓ" not in resultado


class TestBugLv2UmbralMasBajo:
    def test_umbral_45_pct_se_dispara(self):
        # Texto con ~50% mayúsculas — antes ronda 14 no se disparaba
        dictamen = "ESE HUS NO ACEPTA LA GLOSA. La EPS objeta el procedimiento."
        resultado = _normalizar_mayusculas_sostenidas(dictamen)
        assert resultado != dictamen
        assert "HUS" in resultado
        assert "EPS" in resultado

    def test_texto_50_pct_mayusculas_se_normaliza(self):
        # Test del nuevo umbral 45% — caso real del Cart-T donde solo
        # algunas oraciones estaban en MAYÚSCULAS
        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR SANITAS. "
            "ES OBJETO DE ESTE DICTAMEN EL VALOR FACTURADO."
        )
        resultado = _normalizar_mayusculas_sostenidas(dictamen)
        # El umbral de 45% sí se debería disparar
        assert "ESE HUS" in resultado
        # Siglas conocidas conservadas
        assert "SANITAS" in resultado
        # Y el texto debe haber cambiado (no quedó IDÉNTICO)
        assert resultado != dictamen


class TestBugQCitasInventadas:
    def test_clausula_textual_inventada_se_neutraliza(self):
        # Caso 2 real: la IA inventó "Cláusula 5 del contrato: '...'"
        dictamen = (
            "se cita textualmente la Cláusula 5 del contrato: "
            '"La EPS se compromete a pagar los servicios prestados".'
        )
        resultado = _neutralizar_alucinaciones_prompt(dictamen)
        assert "Cláusula 5 del contrato:" not in resultado
        assert "cláusulas contractuales" in resultado.lower()

    def test_resolucion_inventada_se_neutraliza(self):
        # IA inventa texto entre comillas de resolución
        dictamen = (
            "la Resolución 2284 de 2023 establece en su artículo 2: "
            '"Los servicios de salud prestados en cumplimiento '
            'deberán ser reconocidos en los términos establecidos".'
        )
        resultado = _neutralizar_alucinaciones_prompt(dictamen)
        assert "establecidos" not in resultado.lower() or '"' not in resultado


class TestBugPv2CorpusExpandido:
    def test_ley_1388_2010_cancer_infantil(self):
        assert "LEY 1388 DE 2010" in _TODAS_LAS_NORMAS

    def test_ley_1392_2010_huerfanas(self):
        assert "LEY 1392 DE 2010" in _TODAS_LAS_NORMAS

    def test_ley_1616_2013_salud_mental(self):
        assert "LEY 1616 DE 2013" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["LEY 1616 DE 2013"]
        assert "consentimiento" in str(norma).lower()

    def test_resolucion_1652_2021_hemofilia(self):
        assert "RESOLUCION 1652 DE 2021" in _TODAS_LAS_NORMAS

    def test_resolucion_2292_2021_pbs(self):
        assert "RESOLUCION 2292 DE 2021" in _TODAS_LAS_NORMAS

    def test_resolucion_2335_2023_cancer_infantil(self):
        assert "RESOLUCION 2335 DE 2023" in _TODAS_LAS_NORMAS

    def test_resolucion_4886_2018_salud_mental(self):
        assert "RESOLUCION 4886 DE 2018" in _TODAS_LAS_NORMAS

    def test_resolucion_2358_1998_crisis_psiquiatricas(self):
        assert "RESOLUCION 2358 DE 1998" in _TODAS_LAS_NORMAS

    def test_sentencia_t553_2024_cart_t(self):
        assert "SENTENCIA T-553 DE 2024" in _TODAS_LAS_NORMAS
        norma = _TODAS_LAS_NORMAS["SENTENCIA T-553 DE 2024"]
        assert "CAR-T" in str(norma) or "Cart-T" in str(norma) or "CART-T" in str(norma)

    def test_sentencia_t027_2020_cancer_infantil(self):
        assert "SENTENCIA T-027 DE 2020" in _TODAS_LAS_NORMAS

    def test_sentencia_t705_2017_migrantes(self):
        assert "SENTENCIA T-705 DE 2017" in _TODAS_LAS_NORMAS

    def test_sentencia_t401_1994_dignidad_psiquiatrica(self):
        assert "SENTENCIA T-401 DE 1994" in _TODAS_LAS_NORMAS


class TestRegresion:
    def test_ronda12_cups_1011_sigue_neutralizado(self):
        texto = "PROCEDIMIENTO BAJO EL CUPS 1011"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1011" not in resultado

    def test_ronda14_codigo_uvb_intacto(self):
        from app.services.glosa_service import _DIGITOS_CONSTANTES_LEGITIMOS

        assert "12110" in _DIGITOS_CONSTANTES_LEGITIMOS
