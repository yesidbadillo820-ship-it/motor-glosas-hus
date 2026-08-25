"""Tests del citation_verifier — patrones y mapeo al corpus.

Regresión de los huecos hallados en auditoría:
  - Acuerdo NNN/YYYY y Circular NN/YYYY no se reconocían (no había patrón).
  - Decreto/Ley en forma compacta "NNN/YYYY" no se reconocía.
  - "Decreto 4747 de 2007" devolvía NORMA_INEXISTENTE porque la clave del
    corpus era 'DECRETO 4747 DE 2007' (upper-words) y el lookup solo
    probaba snake_case 'decreto_4747_2007'.
  - El fallback antiguo matcheaba spuriamente por substring numérico
    ("138" caía en 'LEY 1438 DE 2011').
"""

from __future__ import annotations

from app.services.citation_verifier import _buscar_clave_norma, verificar_citas
from app.services.normativa_completa import _TODAS_LAS_NORMAS as CORPUS


class TestNormasReales:
    """Citas que SÍ están en el corpus → 0 issues."""

    def _verificar_sin_issues(self, texto: str):
        r = verificar_citas(texto)
        assert not r["issues"], f"esperaba 0 issues, obtuve: {r['issues']}"

    def test_decreto_4747_de_2007(self):
        self._verificar_sin_issues("Decreto 4747 de 2007")

    def test_ley_100_de_1993(self):
        self._verificar_sin_issues("Ley 100 de 1993")

    def test_ley_1438_de_2011(self):
        self._verificar_sin_issues("Ley 1438 de 2011")

    def test_acuerdo_002_de_2001(self):
        # Clave real: 'ACUERDO 002 DE 2001 CSSFFMM' (con sufijo)
        self._verificar_sin_issues("Acuerdo 002 de 2001")

    def test_acuerdo_002_compacto(self):
        # Forma compacta NNN/YYYY usada en lista FUNDAMENTO
        self._verificar_sin_issues("Acuerdo 002/2001")


class TestNormasInventadas:
    """Citas que NO están en el corpus → marcadas como inexistentes."""

    def test_ley_inventada(self):
        r = verificar_citas("Ley 9999 de 9999")
        assert any(i["tipo"] == "NORMA_INEXISTENTE" for i in r["issues"])

    def test_decreto_inventado(self):
        r = verificar_citas("Decreto 9999 de 2099")
        assert any(i["tipo"] == "NORMA_INEXISTENTE" for i in r["issues"])

    def test_acuerdo_inventado(self):
        r = verificar_citas("Acuerdo 777 de 2099")
        assert any(i["tipo"] == "NORMA_INEXISTENTE" for i in r["issues"])


class TestFalsosPositivosPorBordeDePalabra:
    """Regresión 10-jun-2026: PAT_SENTENCIA no exigía \\b antes de (T|C|SU)
    y la C final de "DEC." matcheaba como sentencia. El dictamen real decía
    "MESA DE CONCILIACIÓN DE AUDITORÍA (ART. 20 DEC. 4747/2007)" y el
    verifier reportaba la sentencia fantasma "C-4747/2007" → el gestor veía
    un problema de citas sobre una cita perfectamente válida (Decreto
    4747 de 2007, que SÍ está en el corpus).
    """

    def test_dec_abreviado_no_es_sentencia(self):
        r = verificar_citas(
            "SE INVITA A MESA DE CONCILIACIÓN DE AUDITORÍA (ART. 20 DEC. 4747/2007)."
        )
        sentencias = [i for i in r["issues"] if "Sentencia" in i.get("cita", "")]
        assert not sentencias, f"falso positivo de sentencia: {sentencias}"

    def test_dec_abreviado_se_verifica_como_decreto(self):
        # Bonus del fix: "DEC. 4747/2007" ahora se reconoce como Decreto y
        # se valida contra el corpus (antes ni se contaba como cita).
        r = verificar_citas("DEC. 4747/2007")
        assert r["total_citas"] >= 1
        assert not r["issues"], f"Decreto 4747/2007 existe en corpus: {r['issues']}"

    def test_sentencia_real_sigue_detectandose(self):
        # El \b no debe romper la detección de sentencias genuinas.
        r = verificar_citas("Sentencia C-9999/2099 dice algo")
        assert any("C-9999" in i.get("cita", "") for i in r["issues"])

    def test_tres_seguido_de_numeros_no_es_resolucion(self):
        # "...TRES 500/2024" — la cola "RES" de una palabra no debe
        # dispararse como "Resolución 500 de 2024".
        r = verificar_citas("SE PAGARON TRES 500/2024 CUOTAS")
        resoluciones = [i for i in r["issues"] if "Resolución" in i.get("cita", "")]
        assert not resoluciones, f"falso positivo de resolución: {resoluciones}"


class TestRegresionTextoFijoDMBUG:
    """Regresión 11-jun-2026: el texto fijo curado para DMBUG citaba
    "DECRETO-LEY 1795 DE 2000" y "Decreto 111 de 1996" (Estatuto Orgánico
    del Presupuesto, art. 71 — defensa contra "agotamiento presupuestal").
    El verifier los marcaba NORMA_INEXISTENTE ALTA:
      - "Decreto-Ley 1795/2000" → PAT_LEY extraía "Ley 1795 de 2000" y
        no la encontraba (la norma real es DECRETO-LEY, no LEY).
      - "Decreto 111/1996" no estaba cargado en el corpus.
    Resultado: EVIDENCIA C y CONFIANZA 31% en un dictamen jurídicamente
    correcto. Ambos resueltos.
    """

    def test_decreto_ley_1795_no_se_lee_como_ley(self):
        texto = "DECRETO-LEY 1795 DE 2000 (RÉGIMEN DEL SUBSISTEMA DE SALUD DE LAS FF.MM.)"
        r = verificar_citas(texto)
        leyes = [i for i in r["issues"] if "Ley 1795" in i.get("cita", "")]
        assert not leyes, f"Decreto-Ley extraído como Ley: {leyes}"

    def test_decreto_ley_con_espacio_tampoco(self):
        # Algunos textos escriben "Decreto Ley 1795 de 2000" sin guión.
        r = verificar_citas("Decreto Ley 1795 de 2000")
        leyes = [i for i in r["issues"] if "Ley 1795" in i.get("cita", "")]
        assert not leyes

    def test_ley_real_sigue_detectandose(self):
        # No debe cazar Decreto-Ley pero sí leyes normales.
        r = verificar_citas("Ley 9999 de 9999")
        assert any(i["tipo"] == "NORMA_INEXISTENTE" for i in r["issues"])

    def test_decreto_111_de_1996_esta_en_corpus(self):
        # Estatuto Orgánico del Presupuesto, cargado el 11-jun-2026 para
        # eliminar el falso positivo en dictámenes DMBUG por agotamiento.
        r = verificar_citas("Decreto 111 de 1996")
        assert not r["issues"], f"esperaba 0 issues: {r['issues']}"

    def test_articulo_71_decreto_111(self):
        # El texto fijo cita "ART. 71 DEL DECRETO 111/1996" — debe pasar.
        r = verificar_citas("art. 71 del Decreto 111 de 1996")
        assert not any(i["tipo"] == "ARTICULO_FUERA_DE_NORMA" for i in r["issues"])


class TestFallbackEstricto:
    """El fallback antiguo matcheaba por substring numérico: '138' caía
    spuriamente dentro de 'LEY 1438 DE 2011'. El fallback nuevo exige
    token exacto entre delimitadores.
    """

    def test_ley_138_no_se_confunde_con_ley_1438(self):
        # Asumiendo que 'LEY 138 DE 2011' NO existe en el corpus pero
        # 'LEY 1438 DE 2011' sí: el verificador debe reportar inexistente
        # (no debe casar spuriamente con la 1438).
        if "LEY 138 DE 2011" in CORPUS:
            return  # caso ya cubierto, skip
        clave = _buscar_clave_norma("ley", "138", "2011", CORPUS)
        assert clave != "LEY 1438 DE 2011"
