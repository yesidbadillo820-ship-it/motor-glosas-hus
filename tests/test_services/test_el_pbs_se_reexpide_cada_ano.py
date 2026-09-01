"""El corpus tenía cuatro listados del PBS vigentes al mismo tiempo.

28-08-2026. Solo puede regir uno: el Ministerio reexpide cada diciembre el
listado de servicios y tecnologías financiados con la UPC para el año
siguiente. El corpus tenía marcadas como vigentes la Res. 5269 de 2017, la
Res. 2481 de 2020 y la Res. 2292 de 2021 —las tres derogadas— además de una
cuarta que sí lo estaba.

Lo que eso permitía: que el motor le dijera al auditor que un servicio está
cubierto invocando un listado que dejó de aplicar hace años. A la entidad le
basta mostrar la derogatoria para ratificar la glosa. Es la misma clase de
defecto que esta semana ya costó dos veces —la Res. 3047 de 2008 y la Res. 4331
de 2012 dadas por vigentes—, ahora en la cobertura, que es donde se decide si
el servicio se paga.

Cadena completa, bajada del normograma de la Superintendencia Nacional de Salud
el 28-08-2026, cada eslabón con la nota de vigencia literal de su página:

    Res. 5269 de 2017 → derogada por el art. 132 de la Res. 5857 de 2018
    Res. 2481 de 2020 → derogada por el art. 116 de la Res. 2292 de 2021
    Res. 2292 de 2021 → derogada por el art. 116 de la Res. 2808 de 2022
    Res. 2808 de 2022 → derogada por el art. 114 de la Res. 2366 de 2023
    Res. 2366 de 2023 → derogada con la expedición de la Res. 2718 de 2024
    Res. 2718 de 2024 → el normograma NO le registra derogatoria

NO se borra ninguna: para un servicio prestado en 2022 el listado aplicable ES
el de la Res. 2808 de 2022, y citar el de 2024 sería el error contrario.
"""

from __future__ import annotations

import pytest

from app.services.citation_verifier import verificar_citas
from app.services.normativa import NORMAS_VIGENTES
from app.services.normativa_completa import _TODAS_LAS_NORMAS

DEROGADAS = {
    "RESOLUCION 5269 DE 2017": "5857",
    "RESOLUCION 2481 DE 2020": "2292",
    "RESOLUCION 2292 DE 2021": "2808",
}


class TestNingunListadoMuertoPasaPorVigente:
    @pytest.mark.parametrize("clave", sorted(DEROGADAS))
    def test_esta_marcada_derogada(self, clave: str):
        assert _TODAS_LAS_NORMAS[clave]["vigente"] is False

    @pytest.mark.parametrize("clave,sucesora", sorted(DEROGADAS.items()))
    def test_dice_quien_la_derogo(self, clave: str, sucesora: str):
        assert sucesora in _TODAS_LAS_NORMAS[clave]["derogada_por"]

    @pytest.mark.parametrize("clave", sorted(DEROGADAS))
    def test_queda_anotada_la_fuente(self, clave: str):
        assert "28-08-2026" in _TODAS_LAS_NORMAS[clave].get("verificada", "")

    @pytest.mark.parametrize("clave", sorted(DEROGADAS))
    def test_el_revisor_de_citas_ya_las_marca(self, clave: str):
        """Marcarlas en el corpus sirve porque el revisor lee ese campo."""
        num, anio = clave.split()[1], clave.split()[-1]
        r = verificar_citas(f"EL SERVICIO ESTÁ CUBIERTO SEGÚN LA RESOLUCIÓN {num} DE {anio}.")
        assert "NORMA_DEROGADA" in [i["tipo"] for i in (r.get("issues") or [])]


class TestElMotorTieneQueCitarAlgo:
    """De nada sirve tumbar cuatro si no queda ninguna que ofrecer."""

    def test_la_2718_de_2024_esta_cargada_y_vigente(self):
        f = _TODAS_LAS_NORMAS["RESOLUCION 2718 DE 2024"]
        assert f["vigente"] is True
        assert "UPC" in f["titulo"]

    def test_el_catalogo_corto_tambien_la_tiene(self):
        assert "RESOLUCION 2718/2024" in NORMAS_VIGENTES
        assert "RESOLUCION 5269/2017" not in NORMAS_VIGENTES

    def test_no_se_afirma_que_sea_la_del_2026(self):
        """El listado se reexpide cada diciembre y el normograma puede ir
        atrasado. Lo comprobado es que no tiene derogatoria anotada — no que
        sea la del año en curso. Sin evidencia no se inventa una posterior."""
        notas = _TODAS_LAS_NORMAS["RESOLUCION 2718 DE 2024"]["notas"].lower()
        assert "verifique si salió uno posterior" in notas

    def test_el_revisor_no_la_marca(self):
        r = verificar_citas("EL SERVICIO ESTÁ CUBIERTO SEGÚN LA RESOLUCIÓN 2718 DE 2024.")
        assert "NORMA_DEROGADA" not in [i["tipo"] for i in (r.get("issues") or [])]


class TestNoSeBorroNinguna:
    """Para un servicio de 2022 el listado aplicable ES el de 2022."""

    @pytest.mark.parametrize("clave", sorted(DEROGADAS))
    def test_la_ficha_sigue_en_el_corpus(self, clave: str):
        assert clave in _TODAS_LAS_NORMAS
        assert _TODAS_LAS_NORMAS[clave].get("titulo")
