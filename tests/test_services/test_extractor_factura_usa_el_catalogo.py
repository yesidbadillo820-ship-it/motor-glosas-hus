"""Una sola lista de EPS conocidas, no dos copias que se desincronizan.

09-09-2026. `extractor_factura.py` tenía su propia copia literal de la
lista de EPS conocidas, y se quedó atrás: le faltaban MUTUAL SER,
EMSSANAR y SAVIA, que sí están en `catalogo_eps.py`. Ahora importa de ahí.
"""

from __future__ import annotations

from app.services import extractor_factura
from app.services.catalogo_eps import EPS_CONOCIDAS


def test_extractor_factura_usa_el_mismo_catalogo():
    assert tuple(extractor_factura._EPS_CONOCIDAS) == EPS_CONOCIDAS


def test_las_entidades_nuevas_ya_se_detectan_en_el_texto():
    """Si el catálogo se queda atrás, esto se rompe: es la prueba que
    habría atrapado el defecto original."""
    for eps in ("MUTUAL SER", "EMSSANAR", "SAVIA"):
        assert eps in extractor_factura._EPS_CONOCIDAS
