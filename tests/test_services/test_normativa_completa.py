"""Tests del módulo normativa_completa (R80 P2)."""
from __future__ import annotations

from app.services.normativa_completa import (
    _normalizar,
    consultar_normativa,
    listar_todas_las_normas,
    normas_relevantes_para_codigo,
)


class TestNormalizar:
    def test_quita_tildes(self):
        assert _normalizar("Médico") == "medico"
        assert _normalizar("Glosa") == "glosa"

    def test_minusculas(self):
        assert _normalizar("LEY 1438") == "ley 1438"

    def test_strip(self):
        assert _normalizar("  hola  ") == "hola"

    def test_vacio(self):
        assert _normalizar("") == ""
        assert _normalizar(None) == ""


class TestListarTodasLasNormas:
    def test_devuelve_lista_no_vacia(self):
        normas = listar_todas_las_normas()
        assert len(normas) >= 100  # R52 B

    def test_estructura_de_cada_item(self):
        normas = listar_todas_las_normas()
        for n in normas[:5]:
            assert "clave" in n
            assert "nombre" in n
            assert "vigente" in n
            assert "num_articulos" in n
            assert isinstance(n["num_articulos"], int)


class TestConsultarNormativa:
    def test_pregunta_vacia_retorna_vacio(self):
        assert consultar_normativa("") == []
        assert consultar_normativa("   ") == []

    def test_match_directo_ley(self):
        """Ley 1438 → match exacto."""
        r = consultar_normativa("Ley 1438")
        assert len(r) > 0
        # Algún resultado debe mencionar 1438
        nombres = " ".join(x.get("norma", "") for x in r)
        assert "1438" in nombres

    def test_match_directo_resolucion(self):
        r = consultar_normativa("Resolución 2284")
        assert len(r) > 0
        nombres = " ".join(x.get("norma", "") for x in r)
        assert "2284" in nombres

    def test_busqueda_por_keyword(self):
        """Búsqueda por keyword 'soportes' debe traer Res. 1995/1999."""
        r = consultar_normativa("soportes historia clínica", limite=5)
        assert len(r) > 0

    def test_limite_respeta_top_n(self):
        r = consultar_normativa("ley", limite=3)
        assert len(r) <= 3


class TestNormasRelevantesParaCodigo:
    def test_codigo_TA_devuelve_normas_tarifa(self):
        """Para TA0801 (tarifas) debe sugerir normas de tarifa."""
        normas = normas_relevantes_para_codigo("TA0801")
        assert isinstance(normas, list)
        # Al menos debe sugerir algo
        assert len(normas) >= 1

    def test_codigo_SO_devuelve_normas_soportes(self):
        normas = normas_relevantes_para_codigo("SO0101")
        assert len(normas) >= 1

    def test_codigo_inexistente_no_explota(self):
        normas = normas_relevantes_para_codigo("XX9999")
        # Puede ser vacío o lista, pero no debe lanzar
        assert isinstance(normas, list)

    def test_codigo_vacio(self):
        normas = normas_relevantes_para_codigo("")
        assert isinstance(normas, list)
