"""El programa no puede imprimir huecos donde va una dirección.

La lección viene del curso de noruego: dos veces el auditor copió en el
navegador el texto de relleno («LA-IP-DE-ARRIBA», «ese-numero») porque el bot
lo imprimió como si fuera la dirección. Aquí se vigila lo mismo: si algún día
alguien vuelve a poner un `<...>` donde va un enlace, estas pruebas se ponen
rojas antes de que salga del repositorio.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from mercados.cli import main
from mercados.enlace import (
    CARPETA_PUBLICADA,
    POR_DEFECTO,
    direccion_del_motor,
    enlace_celular,
    ruta_publicada,
)

#: Cualquier `<algo>` en una línea que hable de direcciones o enlaces.
HUECO = re.compile(r"<[^>]+>")

CSV = (
    "Fecha,Apertura,Máximo,Mínimo,Cierre\n"
    + "\n".join(f"2026-01-{d:02d},1.1000,1.1100,1.0900,1.10{d:02d}" for d in range(1, 29))
    + "\n"
)


@pytest.fixture
def historico(tmp_path: Path) -> Path:
    ruta = tmp_path / "historico.csv"
    ruta.write_text(CSV, encoding="utf-8")
    return ruta


def test_el_enlace_del_celular_sale_completo_y_copiable():
    enlace = enlace_celular(Path("static/mercados"))
    assert enlace is not None
    assert enlace.startswith("http")
    assert enlace.endswith("/static/mercados/index.html")
    assert not HUECO.search(enlace)


def test_la_direccion_sale_de_la_variable_del_motor(monkeypatch):
    monkeypatch.setenv("APP_BASE_URL", "https://otra-direccion.example/")
    # La barra final se quita: si no, el enlace saldría con dos seguidas.
    assert direccion_del_motor() == "https://otra-direccion.example"


def test_la_direccion_tambien_sale_del_env_del_repositorio(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("MOTOR_GLOSAS_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        '# un comentario\nSECRET_KEY=no-es-esta\nAPP_BASE_URL="https://del-env.example"\n',
        encoding="utf-8",
    )
    assert direccion_del_motor(tmp_path) == "https://del-env.example"


def test_sin_variable_ni_env_queda_la_misma_que_usa_el_motor(tmp_path, monkeypatch):
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("MOTOR_GLOSAS_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    assert direccion_del_motor(tmp_path) == POR_DEFECTO


def test_el_defecto_es_el_mismo_que_declara_el_motor():
    """Si el motor cambia de dominio, esta prueba avisa que hay dos verdades."""
    config = Path("app/core/config.py").read_text(encoding="utf-8")
    assert f'app_base_url: str = "{POR_DEFECTO}"' in config


def test_una_carpeta_fuera_de_static_no_recibe_enlace_inventado(tmp_path):
    assert ruta_publicada(tmp_path) is None
    assert enlace_celular(tmp_path) is None


def test_exportar_fuera_de_static_avisa_en_vez_de_inventar_enlace(historico, tmp_path):
    lineas: list[str] = []
    assert main(["exportar", str(historico), "--salida", str(tmp_path / "app")], lineas.append) == 0
    assert "no publica" in "\n".join(lineas)
    assert not any(HUECO.search(línea) for línea in lineas)


def test_exportar_dentro_de_static_imprime_el_enlace_entero(historico):
    # Una carpeta propia: la aplicación de verdad vive en `static/mercados/` y
    # una prueba no tiene por qué pisarla.
    destino = Path(CARPETA_PUBLICADA) / "mercados-prueba-enlace"
    lineas: list[str] = []
    try:
        assert main(["exportar", str(historico), "--salida", str(destino)], lineas.append) == 0
        esperado = enlace_celular(destino)
        assert esperado is not None
        assert esperado in "\n".join(lineas)
        assert not any(HUECO.search(línea) for línea in lineas)
    finally:
        shutil.rmtree(destino, ignore_errors=True)


def test_la_guia_no_deja_ningun_hueco_donde_va_el_enlace():
    guia = Path("docs/GUIA_ANALISIS_VELAS.md").read_text(encoding="utf-8")
    for línea in guia.splitlines():
        if "/static/mercados/index.html" in línea:
            assert not HUECO.search(línea), f"hueco en la guía: {línea!r}"
