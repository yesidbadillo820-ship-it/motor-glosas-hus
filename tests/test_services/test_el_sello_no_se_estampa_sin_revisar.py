"""El sello «VALIDADO POR QUALITY GATE» exige que sí se haya revisado.

19-08-2026. `verificar_citas` devolvía exactamente lo mismo —cero citas, cero
problemas— en dos situaciones que no tienen nada que ver:

  · revisé el dictamen y las citas están bien;
  · **no pude revisar nada** (no cargó el corpus de normas, o el dictamen
    llegó vacío).

La pantalla no podía distinguirlas: le bastaba con que el objeto existiera y no
trajera problemas graves para estampar el sello verde. O sea que un dictamen
que nadie miró salía con sello de calidad — sobre un documento que se radica
ante la EPS.

Es la misma familia de todo lo de hoy: decir que se hizo algo que no se hizo.
"""

from __future__ import annotations

import pytest

from app.services.citation_verifier import verificar_citas

DICTAMEN = (
    "<p>Conforme a la Resolución 2284 de 2023 y a la Ley 1438 de 2011 "
    "artículo 57, procede el levantamiento de la glosa.</p>"
)


class TestCuandoSiSeRevisa:
    def test_lo_dice(self):
        assert verificar_citas(DICTAMEN)["verificado"] is True

    def test_y_cuenta_las_citas(self):
        assert verificar_citas(DICTAMEN)["total_citas"] > 0


class TestCuandoNoSeRevisa:
    def test_el_dictamen_vacio_no_cuenta_como_revisado(self):
        r = verificar_citas("")
        assert r["verificado"] is False
        assert r["motivo_no_verificado"]

    def test_sin_corpus_de_normas_no_cuenta_como_revisado(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "app.services.normativa_completa", None)
        r = verificar_citas(DICTAMEN)
        assert r["verificado"] is False
        assert "NO se revisaron" in r["motivo_no_verificado"]

    def test_el_motivo_le_dice_al_auditor_qué_hacer(self, monkeypatch):
        import sys

        monkeypatch.setitem(sys.modules, "app.services.normativa_completa", None)
        assert "a mano antes de radicar" in verificar_citas(DICTAMEN)["motivo_no_verificado"]

    @pytest.mark.parametrize("entrada", ["", None])
    def test_nunca_dice_que_reviso_lo_que_no_habia(self, entrada):
        assert verificar_citas(entrada)["verificado"] is False


class TestLaPantallaLoRespeta:
    def _index(self) -> str:
        from pathlib import Path

        return (Path(__file__).resolve().parents[2] / "static" / "index.html").read_text(
            encoding="utf-8", errors="ignore"
        )

    def test_el_sello_exige_que_se_haya_revisado(self):
        texto = self._index()
        assert "_vc.verificado !== false" in texto, (
            "el sello vuelve a estamparse solo con que el objeto exista"
        )

    def test_se_le_avisa_al_auditor_en_pantalla(self):
        texto = self._index()
        assert "NO se revisaron" in texto
        assert "motivo_no_verificado" in texto
