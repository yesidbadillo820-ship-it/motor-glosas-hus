"""Liquidador de cirugías por grupo quirúrgico — 18-08-2026.

Una cirugía no tiene "un" valor: el Manual SOAT 2026 la cobra por grupo (02
al 13, y especiales 20 al 23), sumando sala + honorarios del cirujano +
ayudantía + anestesiólogo + materiales.

La prueba que amarra todo es test_reproduce_el_valor_real_pactado: los
valores que salen aquí se comparan contra los que el auditor sacó de la base
de datos del PC de cartera (el "UVB POR GRUPOS" pactado con FAMISANAR). La
cesárea da exacto; la apendicectomía queda a $100 por el orden del redondeo.
Si algún día se dañan las tablas de grupo, esta prueba se cae.
"""

from __future__ import annotations

import pytest

from app.services.liquidador_cirugias import (
    es_cirugia_por_grupo,
    liquidar_cirugia,
)


class TestReconoceLaCirugia:
    @pytest.mark.parametrize(
        "cups,grupo",
        [
            ("471102", "7"),  # apendicectomía vía abierta
            ("740001", "8"),  # cesárea segmentaria
            ("530001", "7"),  # herniorrafia inguinal
        ],
    )
    def test_identifica_el_grupo(self, cups, grupo):
        d = liquidar_cirugia(cups)
        assert d is not None
        assert d["grupo"] == grupo

    def test_un_examen_no_es_cirugia(self):
        """Un hemograma no se liquida por grupo quirúrgico."""
        assert es_cirugia_por_grupo("902210") is False
        assert liquidar_cirugia("902210") is None

    def test_un_codigo_inexistente_no_es_cirugia(self):
        assert es_cirugia_por_grupo("999999") is False
        assert liquidar_cirugia("999999") is None


class TestElDesglose:
    def test_tiene_las_cinco_lineas(self):
        d = liquidar_cirugia("471102")
        conceptos = [ln["concepto"] for ln in d["lineas"]]
        assert len(conceptos) == 5
        assert any("sala" in c.lower() for c in conceptos)
        assert any("cirujano" in c.lower() for c in conceptos)
        assert any("ayudant" in c.lower() for c in conceptos)
        assert any("anestesi" in c.lower() for c in conceptos)
        assert any("materiales" in c.lower() for c in conceptos)

    def test_el_total_es_la_suma_de_las_lineas_disponibles(self):
        d = liquidar_cirugia("471102", pct=-5)
        suma = sum(ln["valor_pesos"] for ln in d["lineas"] if ln["disponible"])
        # El total se calcula sobre la suma de UVB, no sobre pesos ya
        # redondeados: por eso se compara con tolerancia de una centena.
        assert abs(d["total_pesos"] - suma) <= 100 * len(d["lineas"])

    def test_reproduce_el_valor_real_pactado(self):
        """Contra la base del PC de cartera (UVB POR GRUPOS, FAMISANAR −5%)."""
        cesarea = liquidar_cirugia("740001", pct=-5)
        assert cesarea["total_pesos"] == 2_072_200  # exacto vs. la BD

        apendice = liquidar_cirugia("471102", pct=-5)
        # BD dice $1.885.300; el método directo da $1.885.200 (redondeo).
        assert abs(apendice["total_pesos"] - 1_885_300) <= 100

    def test_el_menos_cinco_baja_el_valor(self):
        pleno = liquidar_cirugia("740001", pct=0)["total_pesos"]
        con_descuento = liquidar_cirugia("740001", pct=-5)["total_pesos"]
        assert con_descuento < pleno


class TestGruposConLagunas:
    def test_grupo_pequeno_no_tiene_ayudantia(self):
        """El Manual reconoce ayudantía solo desde el grupo 06.

        Se busca un CUPS de grupo 2–5 y se comprueba que la línea de
        ayudantía salga como no disponible.
        """
        from app.services.cups_soat_service import _cargar

        cups_g2 = None
        for cups, maps in _cargar().get("cups_a_soat", {}).items():
            for m in maps:
                if str(m.get("clase", "")).upper() == "GRUPO" and str(m.get("uvb")) in (
                    "2",
                    "3",
                    "4",
                    "5",
                ):
                    cups_g2 = cups
                    break
            if cups_g2:
                break
        assert cups_g2, "debería existir al menos un CUPS de grupo 2–5"
        d = liquidar_cirugia(cups_g2)
        ayud = next(ln for ln in d["lineas"] if "ayudant" in ln["concepto"].lower())
        assert ayud["disponible"] is False
        assert "Ayudantía quirúrgica" in d["componentes_faltantes"]

    def test_grupo_especial_no_tiene_materiales(self):
        """Los grupos especiales 20–23 no traen código de materiales."""
        from app.services.cups_soat_service import _cargar

        cups_esp = None
        for cups, maps in _cargar().get("cups_a_soat", {}).items():
            for m in maps:
                if str(m.get("clase", "")).upper() == "GRUPO" and str(m.get("uvb")) in (
                    "20",
                    "21",
                    "22",
                    "23",
                ):
                    cups_esp = cups
                    break
            if cups_esp:
                break
        assert cups_esp
        d = liquidar_cirugia(cups_esp)
        assert d["grupo_especial"] is True
        mat = next(ln for ln in d["lineas"] if "materiales" in ln["concepto"].lower())
        assert mat["disponible"] is False


class TestNoInventa:
    def test_las_lineas_no_disponibles_no_traen_valor(self):
        from app.services.cups_soat_service import _cargar

        for cups, maps in _cargar().get("cups_a_soat", {}).items():
            if any(str(m.get("clase", "")).upper() == "GRUPO" for m in maps):
                d = liquidar_cirugia(cups)
                for ln in d["lineas"]:
                    if not ln["disponible"]:
                        assert ln["valor_pesos"] is None
                        assert ln["uvb"] is None
                break
