"""El respaldo de IA estaba en un modelo viejo Y más caro.

10-09-2026. El motor tenía `claude-sonnet-4-5` fijado como modelo de
Anthropic: generación anterior y 3,00 / 15,00 dólares por millón de palabras,
contra 2,00 / 10,00 del Sonnet 5. Más viejo y más caro a la vez.

**Lo que casi convierte esto en un desastre silencioso.** La generación actual
RECHAZA el parámetro `temperature` con error 400, y el motor se lo manda en
las diez llamadas que le hace a Anthropic. Cambiar solo el nombre del modelo
habría dejado el respaldo muerto, y no se habría notado hasta el día que Groq
fallara — que es el peor día para enterarse.

Por eso la prueba central de este archivo no es «el modelo cambió», es
**«con el modelo nuevo NO se manda temperature, y con el viejo SÍ»**.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.modelos_anthropic import (
    MODELO_POR_DEFECTO,
    acepta_temperature,
    temperatura_si_aplica,
)

RAIZ = Path(__file__).resolve().parents[2]


class TestQueModeloAceptaQue:
    @pytest.mark.parametrize(
        "modelo",
        ["claude-sonnet-5", "claude-opus-5", "claude-opus-4-7", "claude-opus-4-8"],
    )
    def test_la_generacion_actual_rechaza_temperature(self, modelo):
        assert not acepta_temperature(modelo), f"{modelo} devuelve 400 si se le manda"
        assert temperatura_si_aplica(modelo, 0.10) == {}

    @pytest.mark.parametrize(
        "modelo",
        ["claude-sonnet-4-5", "claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5"],
    )
    def test_la_generacion_anterior_si_la_acepta(self, modelo):
        assert acepta_temperature(modelo)
        assert temperatura_si_aplica(modelo, 0.10) == {"temperature": 0.10}

    def test_no_confunde_sonnet_4_5_con_sonnet_5(self):
        """Los nombres se parecen y un `in` en vez de un `startswith` los mezcla.

        Si esta se cae, o el respaldo viejo perdió su temperature (dictámenes
        menos consistentes) o el nuevo la recibe y contesta 400.
        """
        assert acepta_temperature("claude-sonnet-4-5")
        assert not acepta_temperature("claude-sonnet-5")

    def test_un_modelo_desconocido_se_comporta_como_hasta_hoy(self):
        """Ante la duda, mandar temperature: es lo que hace el motor hoy."""
        assert acepta_temperature("un-modelo-que-no-existe")

    def test_aguanta_vacio_y_none(self):
        assert acepta_temperature("") and acepta_temperature(None)
        assert temperatura_si_aplica("claude-sonnet-5", None) == {}


class TestNingunaLlamadaMandaTemperatureAPelo:
    """La prueba que impide que esto vuelva a pasar.

    No comprueba una lista de archivos: recorre TODO el código buscando
    llamadas a Anthropic con `temperature` fija. Si mañana alguien agrega una
    llamada nueva copiando y pegando, esta prueba avisa sola.
    """

    def _fuentes_que_llaman_a_anthropic(self):
        for ruta in (RAIZ / "app").rglob("*.py"):
            texto = ruta.read_text(encoding="utf-8", errors="ignore")
            if "api.anthropic.com" in texto:
                yield ruta, texto

    def test_hay_llamadas_que_revisar(self):
        assert list(self._fuentes_que_llaman_a_anthropic()), "no encontré el código a revisar"

    def test_ninguna_manda_temperature_sin_preguntar(self):
        culpables = []
        for ruta, texto in self._fuentes_que_llaman_a_anthropic():
            for n, linea in enumerate(texto.split("\n"), 1):
                if re.search(r'^\s*"temperature"\s*:', linea):
                    culpables.append(f"{ruta.relative_to(RAIZ)}:{n}")
        assert not culpables, (
            "estas llamadas le mandan temperature a Anthropic a pelo; la "
            f"generación actual contesta 400: {culpables}"
        )

    def test_las_que_quieren_temperature_usan_el_ayudante(self):
        usos = 0
        for _ruta, texto in self._fuentes_que_llaman_a_anthropic():
            usos += texto.count("temperatura_si_aplica(")
        assert usos >= 10, f"esperaba al menos los 10 sitios conocidos, encontré {usos}"


class TestElModeloPorDefecto:
    def test_es_el_de_la_generacion_actual(self):
        assert MODELO_POR_DEFECTO == "claude-sonnet-5"

    def test_ya_no_queda_el_viejo_fijado_en_el_codigo(self):
        """Salvo en la tabla de precios, donde es un dato histórico."""
        culpables = []
        for ruta in (RAIZ / "app").rglob("*.py"):
            if ruta.name == "modelos_anthropic.py":
                continue  # lo nombra en su explicación, a propósito
            for n, linea in enumerate(ruta.read_text(encoding="utf-8").split("\n"), 1):
                if "claude-sonnet-4-5" in linea and "output" not in linea:
                    culpables.append(f"{ruta.relative_to(RAIZ)}:{n}")
        assert not culpables, f"quedó el modelo viejo fijado en: {culpables}"


class TestLosPreciosDelRespaldo:
    def _tarifas(self):
        from app.services.glosa_service import _TARIFAS_ANTHROPIC_USD_POR_MTOK

        return _TARIFAS_ANTHROPIC_USD_POR_MTOK

    def test_el_modelo_nuevo_tiene_precio_propio(self):
        """Sin esto caía al default y se costeaba 50% más caro de lo real."""
        assert self._tarifas()[MODELO_POR_DEFECTO] == {"input": 2.0, "output": 10.0}

    def test_el_nuevo_es_mas_barato_que_el_que_reemplaza(self):
        t = self._tarifas()
        assert t["claude-sonnet-5"]["input"] < t["claude-sonnet-4-5"]["input"]
        assert t["claude-sonnet-5"]["output"] < t["claude-sonnet-4-5"]["output"]

    @pytest.mark.parametrize("modelo", ["claude-opus-4-6", "claude-opus-4-7", "claude-opus-4-8"])
    def test_los_opus_ya_no_estan_al_triple(self, modelo):
        """Estaban a 15,00 / 75,00: el precio de la generación Opus 3."""
        assert self._tarifas()[modelo] == {"input": 5.0, "output": 25.0}

    def test_el_haiku_pelado_tiene_precio(self):
        """`ia_status` usa el nombre sin fecha; caía al default a 3,00."""
        assert self._tarifas()["claude-haiku-4-5"] == {"input": 1.0, "output": 5.0}
