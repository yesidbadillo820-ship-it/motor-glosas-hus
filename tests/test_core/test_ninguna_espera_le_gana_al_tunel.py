"""Ninguna espera del motor puede durar más que el corte del túnel.

19-08-2026. El portal se sirve por un túnel que corta la petición alrededor de
los 100 segundos. Cualquier espera más larga es una carrera perdida de
antemano: el túnel contesta primero con un «Error 502» pelado, y el auditor no
se entera de qué pasó ni de que perdió su trabajo.

Un barrido del despliegue real encontró **ocho** esperas entre 120 y 240
segundos. La peor es la de Groq —120 s— porque es el camino de TODOS los
dictámenes y el único proveedor que la red del hospital deja salir: cualquier
glosa que se demore un poco termina en 502 mudo, con los tokens ya gastados.

Se arregla de raíz: `espera_maxima()` decide el techo en un solo sitio y
ninguna llamada lo pasa.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.core.config import _corte_del_tunel, espera_maxima

RAIZ = Path(__file__).resolve().parents[2]


class TestElTecho:
    @pytest.mark.parametrize("pedido", [120.0, 180.0, 240.0, 360.0])
    def test_recorta_lo_que_no_alcanza(self, pedido):
        assert espera_maxima(pedido) < _corte_del_tunel()

    def test_deja_margen_para_contestar(self):
        """El motor tiene que alcanzar a armar y mandar SU respuesta."""
        assert _corte_del_tunel() - espera_maxima(240.0) >= 10

    @pytest.mark.parametrize("pedido", [30.0, 75.0])
    def test_respeta_lo_que_si_alcanza(self, pedido):
        assert espera_maxima(pedido) == pedido

    def test_nunca_deja_una_espera_absurda(self):
        """Ni con un túnel mal configurado se puede quedar en cero."""
        assert espera_maxima(240.0, margen=999) >= 10

    def test_se_puede_ajustar_si_el_tunel_cambia(self, monkeypatch):
        monkeypatch.setenv("TUNEL_CORTA_EN_SEGUNDOS", "60")
        assert espera_maxima(240.0) < 60

    def test_un_valor_invalido_no_lo_tumba(self, monkeypatch):
        monkeypatch.setenv("TUNEL_CORTA_EN_SEGUNDOS", "por ahí")
        assert espera_maxima(240.0) > 0


class TestNadieSeSaltaElTecho:
    """La regresión concreta: alguien vuelve a escribir un número largo."""

    ARCHIVOS = [
        "app/services/glosa_service.py",
        "app/services/auditor_forense.py",
        "app/services/extractor_clausulas_contrato.py",
        "app/services/multi_agent.py",
        "app/services/asistente_maestro.py",
    ]

    @pytest.mark.parametrize("ruta", ARCHIVOS)
    def test_ninguna_espera_de_lectura_pasa_del_corte(self, ruta):
        # Se mira el CÓDIGO, no los comentarios: explicar que «era read=180»
        # no puede hacer fallar la prueba de que ya no lo es.
        fuente = "\n".join(
            ln
            for ln in (RAIZ / ruta).read_text(encoding="utf-8").splitlines()
            if not ln.strip().startswith("#")
        )
        largas = [
            m.group(0)
            for m in re.finditer(r"read=(\d+(?:\.\d+)?)", fuente)
            if float(m.group(1)) >= 100
        ]
        assert not largas, f"{ruta} vuelve a perder contra el túnel: {largas}"

    @pytest.mark.parametrize("ruta", ARCHIVOS)
    def test_ningun_timeout_suelto_pasa_del_corte(self, ruta):
        """`timeout=120.0` a pelo, sin httpx.Timeout, cuenta igual."""
        arbol = ast.parse((RAIZ / ruta).read_text(encoding="utf-8"))
        malos = []
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            for kw in nodo.keywords:
                if kw.arg != "timeout":
                    continue
                if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, (int, float)):
                    if kw.value.value >= 100:
                        malos.append(f"linea {kw.value.lineno}: timeout={kw.value.value}")
        assert not malos, f"{ruta}: {malos}"


class TestLaDeGroqQueEsLaQueMasDuele:
    def test_el_camino_de_todos_los_dictamenes_pasa_por_el_techo(self):
        """Groq es el ÚNICO proveedor que la red del hospital deja salir."""
        fuente = (RAIZ / "app" / "services" / "glosa_service.py").read_text(encoding="utf-8")
        assert "timeout=espera_maxima(120.0)" in fuente
