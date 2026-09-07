"""El programa de consola, probado sin escribir en el teclado."""

from __future__ import annotations

import pytest

from noruego.cli import main


class Consola:
    def __init__(self):
        self.lineas: list[str] = []

    def __call__(self, texto=""):
        self.lineas.append(str(texto))

    @property
    def texto(self):
        return "\n".join(self.lineas)


@pytest.fixture
def consola():
    return Consola()


def test_revisar_no_encuentra_problemas(consola):
    assert main(["revisar"], salida=consola) == 0
    assert "AVISOS DEL LÉXICO: ninguno." in consola.texto
    assert "lecciones" in consola.texto


def test_curso_lista_los_modulos(consola):
    assert main(["curso"], salida=consola) == 0
    assert "Primer contacto" in consola.texto
    assert "ejercicios" in consola.texto


def test_leccion_muestra_los_ejercicios(consola):
    assert main(["leccion", "n1"], salida=consola) == 0
    assert "en, ei, et" in consola.texto
    assert "✓" in consola.texto


def test_leccion_inexistente_es_error(consola):
    with pytest.raises(SystemExit, match="No existe la lección"):
        main(["leccion", "no-existe"], salida=consola)


def test_exportar_crea_la_aplicacion(consola, tmp_path):
    destino = tmp_path / "app"
    assert main(["exportar", "--salida", str(destino)], salida=consola) == 0
    assert (destino / "index.html").is_file()
    assert "pantalla de inicio" in consola.texto
    assert "http://" in consola.texto
