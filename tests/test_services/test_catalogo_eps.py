"""El catálogo de entidades reales, más allá de las que tienen contrato.

09-09-2026. SURA, SALUD TOTAL, EMSSANAR, SAVIA y MUTUAL SER tienen bot de
portal propio (`bots_hus.py`) y lógica propia en el motor, pero como nadie
les ha subido un contrato, no aparecían en ningún desplegable de EPS. Este
módulo es la lista fija que arregla eso — sin depender de que alguien haya
escrito antes su nombre en algún lado.
"""

from __future__ import annotations

from app.services.catalogo_eps import EPS_CONOCIDAS, eps_seleccionables


class TestElCatalogoTraeLasEntidadesReales:
    def test_las_que_no_tenian_contrato_estan(self):
        for eps in ("SURA", "SALUD TOTAL", "MUTUAL SER", "EMSSANAR", "SAVIA"):
            assert eps in EPS_CONOCIDAS, f"{eps} tiene bot propio y no estaba"

    def test_las_que_ya_tenian_contrato_siguen(self):
        for eps in ("FAMISANAR", "NUEVA EPS", "COOSALUD", "DISPENSARIO MEDICO"):
            assert eps in EPS_CONOCIDAS

    def test_no_hay_repetidos(self):
        assert len(EPS_CONOCIDAS) == len(set(EPS_CONOCIDAS))

    def test_todo_en_mayuscula_sin_espacios_de_sobra(self):
        for eps in EPS_CONOCIDAS:
            assert eps == eps.upper().strip(), eps

    def test_el_marcador_generico_no_es_parte_del_catalogo(self):
        assert "OTRA" not in EPS_CONOCIDAS
        assert "OTRA / SIN DEFINIR" not in EPS_CONOCIDAS


class TestEpsSeleccionables:
    def test_sin_nada_mas_devuelve_el_catalogo(self):
        assert set(eps_seleccionables()) == set(EPS_CONOCIDAS)

    def test_une_listas_extra_sin_repetir(self):
        salida = eps_seleccionables(["SURA", "COMFAMA"], ["comfama"])
        assert salida.count("COMFAMA") == 1
        assert "SURA" in salida  # ya estaba en el catálogo

    def test_normaliza_mayuscula_y_espacios(self):
        assert "COMFAMA" in eps_seleccionables(["  comfama  "])

    def test_ignora_vacios_y_none(self):
        salida = eps_seleccionables(["", None, "  "])
        assert set(salida) == set(EPS_CONOCIDAS)

    def test_sale_ordenado_alfabeticamente(self):
        salida = eps_seleccionables(["ZZZ INVENTADA", "AAA INVENTADA"])
        assert salida == sorted(salida)

    def test_admite_varias_listas_extra_a_la_vez(self):
        salida = eps_seleccionables(["UNA"], ["OTRA_DE_VERDAD"], [])
        assert "UNA" in salida and "OTRA_DE_VERDAD" in salida
