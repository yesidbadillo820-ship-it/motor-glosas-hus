"""Piezas compartidas por las pruebas del sistema ICFES."""

from __future__ import annotations

from datetime import date

import pytest

from icfes.almacen import Almacen, Configuracion
from icfes.banco import cargar_banco
from icfes.dominio import Area

#: Fecha fija para que las pruebas no dependan del día en que se corran.
HOY = date(2026, 8, 20)
EXAMEN = date(2027, 8, 8)


@pytest.fixture(scope="session")
def banco():
    """El banco de preguntas real del repositorio."""
    return cargar_banco()


@pytest.fixture
def almacen(tmp_path):
    """Un almacén vacío en un archivo temporal."""
    with Almacen(tmp_path / "progreso.db") as a:
        yield a


@pytest.fixture
def config():
    """Configuración de ejemplo: examen de agosto de 2027, meta de 400."""
    return Configuracion(
        nombre="estudiante",
        fecha_examen=EXAMEN,
        meta_global=400,
        horas_semana=12,
    )


@pytest.fixture
def diagnostico():
    """Un diagnóstico de partida con desempeño desigual entre áreas."""
    return {
        Area.LECTURA_CRITICA: 62.0,
        Area.MATEMATICAS: 48.0,
        Area.SOCIALES_CIUDADANAS: 55.0,
        Area.CIENCIAS_NATURALES: 50.0,
        Area.INGLES: 40.0,
    }
