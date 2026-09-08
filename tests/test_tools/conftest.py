"""Herramientas externas que necesitan las pruebas de `tools/`.

La lógica está en `_entorno.py`, que los propios módulos de prueba importan
para sus marcadores. Acá solo se dejan las fixtures equivalentes, para una
prueba suelta que las necesite sin marcar el módulo entero.
"""

from __future__ import annotations

import pytest

from ._entorno import COMO_INSTALAR, exigido, falta_extract_msg, falta_libreoffice


def _exigir_o_saltar(motivo: str, herramienta: str) -> None:
    if not motivo:
        return
    aviso = f"{herramienta}: {motivo}. {COMO_INSTALAR}"
    if exigido():
        pytest.fail(aviso, pytrace=False)
    pytest.skip(aviso)


@pytest.fixture
def exige_libreoffice():
    """Para una prueba que convierte documentos con LibreOffice."""
    _exigir_o_saltar(falta_libreoffice(), "LibreOffice")


@pytest.fixture
def exige_extract_msg():
    """Para una prueba que lee correos .msg."""
    _exigir_o_saltar(falta_extract_msg(), "extract-msg")
