"""Tests del homologador CUPS → SOAT (Manual Único Res. 2775 → SOAT).

Integra el Excel oficial de 11.756 filas (10.024 CUPS únicos, 2.919 SOAT,
1.168 multi-mapeo) convertido a app/data/cups_soat_homologacion.json.gz.

DISTINTO del homologador_cups.py (CUPS viejo → CUPS nuevo Res. 2641/2025).
Este mapea CUPS → código(s) SOAT para fundamentar tarifas en glosas TA.
"""

from app.services.cups_soat_service import (
    bloque_homologacion_para_prompt,
    descripcion_cups,
    homologar_cups_a_soat,
    resumen_homologacion,
    validar_soat_para_cups,
)


class TestCargaYResumen:
    def test_tabla_cargada(self):
        meta = resumen_homologacion()
        assert meta.get("cargado") is True
        assert meta.get("cups_unicos", 0) >= 10000

    def test_soat_unicos(self):
        meta = resumen_homologacion()
        assert meta.get("soat_unicos", 0) >= 2900


class TestHomologacionBasica:
    def test_cups_conocido_devuelve_soat(self):
        # 012403 es un CUPS real con multi-mapeo (1101, 1102, 1103)
        mapeos = homologar_cups_a_soat("012403")
        assert len(mapeos) >= 3
        soats = {m["soat"] for m in mapeos}
        assert "1101" in soats
        assert "1102" in soats

    def test_cada_mapeo_tiene_descripciones(self):
        mapeos = homologar_cups_a_soat("012403")
        for m in mapeos:
            assert m["soat"]
            assert m["desc_soat"]
            assert m["desc_cups"]

    def test_cups_inexistente_devuelve_vacio(self):
        assert homologar_cups_a_soat("999999") == []

    def test_cups_none_o_vacio(self):
        assert homologar_cups_a_soat(None) == []
        assert homologar_cups_a_soat("") == []


class TestNormalizacionCups:
    def test_cups_sin_cero_inicial(self):
        # "12403" debe encontrar "012403"
        assert len(homologar_cups_a_soat("12403")) >= 1

    def test_cups_con_sufijo_institucional_H(self):
        # "012403H" debe encontrar "012403"
        assert len(homologar_cups_a_soat("012403H")) >= 1

    def test_cups_con_sufijo_version_guion(self):
        # "012403-18" debe encontrar "012403"
        assert len(homologar_cups_a_soat("012403-18")) >= 1

    def test_cups_con_espacios(self):
        assert len(homologar_cups_a_soat("  012403  ")) >= 1


class TestValidacionSoat:
    def test_soat_valido_para_cups(self):
        assert validar_soat_para_cups("012403", "1101") is True

    def test_soat_valido_normaliza_ceros(self):
        # "01101" debe validar igual que "1101"
        assert validar_soat_para_cups("012403", "01101") is True

    def test_soat_invalido_para_cups(self):
        # 9999 NO corresponde a 012403 → modificación tarifaria unilateral
        assert validar_soat_para_cups("012403", "9999") is False

    def test_validacion_con_nulos(self):
        assert validar_soat_para_cups(None, "1101") is False
        assert validar_soat_para_cups("012403", None) is False


class TestDescripcionCups:
    def test_descripcion_cups_conocido(self):
        desc = descripcion_cups("012403")
        assert desc  # no vacío
        assert "CRANEOTOMIA" in desc.upper()

    def test_descripcion_cups_inexistente(self):
        assert descripcion_cups("999999") == ""


class TestBloquePrompt:
    def test_bloque_para_cups_conocido(self):
        bloque = bloque_homologacion_para_prompt("012403")
        assert "HOMOLOGACIÓN OFICIAL CUPS → SOAT" in bloque
        assert "SOAT 1101" in bloque
        assert "modificación" in bloque.lower()  # advertencia anti-unilateral

    def test_bloque_vacio_para_cups_inexistente(self):
        # NO inventa nada si el CUPS no está
        assert bloque_homologacion_para_prompt("999999") == ""

    def test_bloque_respeta_max_soat(self):
        # Con max_soat=2, un CUPS de 3 SOAT debe mostrar "… más"
        bloque = bloque_homologacion_para_prompt("012403", max_soat=2)
        assert "más" in bloque.lower()
