"""Un solo vocabulario de color en todo el motor.

Idea #12, decidida por el área el 26-08-2026.

Lo que había: dos paletas distintas conviviendo. La corporativa del rebrand
de junio (`--sinac-*`, la que usa toda la página) y la de `sinac-ds.css`, de
mayo, con sus propios azules y verdes. **No eran dos nombres para el mismo
color: eran colores distintos.** Y ese archivo no estaba muerto —sus reglas
pintan la pantalla de Analizar—, así que el mismo «verificado» salía de un
verde en el dictamen (#16a34a) y de otro verde en el resto del motor
(#2E7D32).

Cómo quedó: los nombres `--sds-*` son los que se escriben (como pide
CLAUDE.md) pero el color que devuelven es el corporativo.

Estas pruebas cuidan las dos mitades del arreglo: que ningún color del
sistema de diseño vuelva a declararse por su cuenta, y que ninguno se quede
sin color de respaldo —que es lo que dejaría un elemento transparente en las
cuatro páginas que no definen la paleta corporativa—.
"""

from __future__ import annotations

import pathlib
import re

import pytest

# Los tokens de COLOR del sistema de diseño. El espaciado, los radios, las
# sombras y las transiciones son otra cosa y no entran aquí.
_FAMILIAS_DE_COLOR = ("blue", "gray", "success", "amber", "rose")


@pytest.fixture(scope="module")
def ds() -> str:
    return pathlib.Path("static/sinac-ds.css").read_text(encoding="utf-8")


def _definiciones_de_color(css: str) -> dict[str, str]:
    """Cada `--sds-<color>…: <valor>;` declarado en el archivo."""
    salida = {}
    for nombre, valor in re.findall(r"(--sds-[a-z0-9-]+)\s*:\s*([^;]+);", css):
        familia = nombre[len("--sds-") :].split("-")[0]
        if familia in _FAMILIAS_DE_COLOR:
            salida[nombre] = valor.strip()
    return salida


class TestNingunColorSeDeclaraPorSuCuenta:
    def test_hay_colores_que_revisar(self, ds: str):
        """Si el conteo se cae a cero, la prueba pasaría por estar vacía."""
        assert len(_definiciones_de_color(ds)) >= 10

    def test_todos_apuntan_a_la_paleta_corporativa(self, ds: str):
        sueltos = {
            n: v for n, v in _definiciones_de_color(ds).items() if not v.startswith("var(")
        }
        assert not sueltos, (
            "Estos colores del sistema de diseño se declaran por su cuenta en vez "
            "de apuntar a la paleta corporativa, así que vuelven a ser un segundo "
            "vocabulario:\n"
            + "\n".join(f"  {n}: {v}" for n, v in sorted(sueltos.items()))
        )

    def test_apuntan_a_un_token_de_la_casa(self, ds: str):
        for nombre, valor in _definiciones_de_color(ds).items():
            assert re.match(r"var\(--(sinac|c)-", valor), (
                f"{nombre} apunta a «{valor}», que no es un token de la paleta de la casa"
            )


class TestNingunoSeQuedaSinRespaldo:
    """Cuatro de las seis páginas que cargan este archivo NO definen la paleta
    corporativa. Sin color de respaldo el token queda vacío y el elemento se
    pinta transparente — así quedó invisible el botón del lote ADRES."""

    def test_todos_traen_su_color_de_respaldo(self, ds: str):
        sin_respaldo = {
            n: v for n, v in _definiciones_de_color(ds).items() if "," not in v
        }
        assert not sin_respaldo, (
            "Estos colores no traen respaldo: en preauditoría, importar masiva, "
            "presentación IA y terapia física quedarían vacíos:\n"
            + "\n".join(f"  {n}: {v}" for n, v in sorted(sin_respaldo.items()))
        )

    def test_el_respaldo_es_un_color_de_verdad(self, ds: str):
        for nombre, valor in _definiciones_de_color(ds).items():
            respaldo = valor.split(",", 1)[1].rstrip(") ").strip()
            assert re.fullmatch(r"#[0-9A-Fa-f]{6}", respaldo), (
                f"{nombre} tiene «{respaldo}» de respaldo, que no es un color"
            )

    def test_el_respaldo_es_el_corporativo_no_el_viejo(self, ds: str):
        """Si el respaldo fuera el color viejo, las cuatro páginas sueltas
        seguirían con la paleta de mayo y no se habría unificado nada."""
        viejos = {"#eff6ff", "#3b82f6", "#2563eb", "#1d4ed8", "#1e3a8a",
                  "#f8fafc", "#f1f5f9", "#e2e8f0", "#94a3b8", "#475569",
                  "#0f172a", "#16a34a", "#f0fdf4", "#d97706", "#fffbeb", "#e11d48"}
        for nombre, valor in _definiciones_de_color(ds).items():
            respaldo = valor.split(",", 1)[1].rstrip(") ").strip().lower()
            assert respaldo not in viejos, (
                f"{nombre} se quedó con el color viejo ({respaldo}) de respaldo"
            )


class TestLaPaginaSigueMandando:
    def test_index_no_perdio_su_paleta(self):
        html = pathlib.Path("static/index.html").read_text(encoding="utf-8")
        for token in ("--sinac-blue-700:", "--sinac-green-700:", "--c-amber:", "--c-red:"):
            assert token in html, f"desapareció {token} de la paleta corporativa"

    def test_las_paginas_sueltas_no_definen_la_paleta(self):
        """Deja constancia de por qué hace falta el respaldo. Si algún día
        estas páginas sí definen la paleta, se puede revisar la regla."""
        sueltas = [
            "static/preauditoria.html",
            "static/importar-masiva.html",
            "static/presentacion-ia.html",
        ]
        for ruta in sueltas:
            texto = pathlib.Path(ruta).read_text(encoding="utf-8")
            if "sinac-ds.css" not in texto:
                continue
            assert "--sinac-blue-700:" not in texto, (
                f"{ruta} ahora sí define la paleta — se puede revisar si el "
                "respaldo sigue haciendo falta"
            )
