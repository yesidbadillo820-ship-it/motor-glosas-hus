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
