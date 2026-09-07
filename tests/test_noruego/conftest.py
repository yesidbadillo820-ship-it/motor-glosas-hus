"""Piezas compartidas por las pruebas del curso de noruego."""

from __future__ import annotations

import pytest

from noruego.lexico import cargar


@pytest.fixture(scope="session")
def lexico():
    """El léxico real del repositorio."""
    return cargar()
