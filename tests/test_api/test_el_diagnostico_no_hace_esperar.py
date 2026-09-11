"""La pantalla de Diagnóstico no puede hacer esperar por IAs caídas.

11-09-2026, medido con el cronómetro en una hora de trabajo real del HUS:

    GET /admin/diagnostico   19 veces · 2.200 ms de promedio · 15,3 s la peor

La fila más lenta de toda la tabla, de lejos, con picos de 15,3 s, 12,5 s y
8,3 s. La causa estaba a la vista en la misma pantalla: esta ruta le pregunta
«¿estás viva?» a Anthropic y a Gemini, y los dos llevaban rato caídos
—`WinError 10054` y `HTTP 503`—. Las esperas eran de **15 y 10 segundos**,
una detrás de la otra: hasta 25 segundos por una respuesta que no iba a
llegar.

Tres segundos alcanzan: si una IA se demora más de eso en contestar «ok» a
cuatro palabras, lo que la pantalla tiene que decir es justamente que está
degradada.
"""

from __future__ import annotations

import inspect
import re

from app.api.routers import diagnostico


class TestLaEsperaEsCorta:
    def test_el_tope_esta_declarado_y_es_corto(self):
        assert hasattr(diagnostico, "_PING_TIMEOUT_S")
        assert 0 < diagnostico._PING_TIMEOUT_S <= 5.0, (
            "un «¿estás vivo?» que espera más de 5 segundos no da una respuesta "
            "mejor, solo una más tarde"
        )

    def test_los_dos_pings_usan_ese_tope(self):
        fuente = inspect.getsource(diagnostico)
        assert fuente.count("_PING_TIMEOUT_S") >= 3, (
            "el tope tiene que aplicarse a los dos pings, no a uno solo"
        )

    def test_no_quedo_ninguna_espera_larga_suelta(self):
        """Los números sueltos son los que vuelven a crecer sin que nadie mire."""
        fuente = inspect.getsource(diagnostico)
        largos = [
            n for n in re.findall(r"timeout\s*=\s*([0-9]+(?:\.[0-9]+)?)", fuente) if float(n) > 5.0
        ]
        assert not largos, f"esperas largas escritas a mano: {largos}"
        largos_httpx = [
            n
            for n in re.findall(r"httpx\.Timeout\(\s*([0-9]+(?:\.[0-9]+)?)", fuente)
            if float(n) > 5.0
        ]
        assert not largos_httpx, f"httpx.Timeout largo: {largos_httpx}"

    def test_lo_peor_que_puede_pasar_son_pocos_segundos(self):
        """Los dos pings corren uno detrás del otro: el techo es la suma."""
        techo = diagnostico._PING_TIMEOUT_S * 2
        assert techo <= 10.0, (
            f"abrir Diagnóstico podría costar {techo:.0f} s con las dos IAs caídas"
        )


class TestElResultadoSeGuardaUnRato:
    """Si no, cada vez que alguien abre la pantalla se vuelve a esperar."""

    def test_hay_cache_y_dura_minutos(self):
        assert diagnostico._PING_TTL_S >= 60

    def test_un_fallo_tambien_se_guarda(self, monkeypatch):
        """Guardar solo los éxitos dejaría el problema igual: con las IAs
        caídas, cada apertura volvería a pagar la espera completa."""
        diagnostico._PING_CACHE.clear()
        llamadas = {"n": 0}

        def _falla():
            llamadas["n"] += 1
            return ("error", "no contesta", {})

        for _ in range(3):
            diagnostico._ping_cached("prueba-de-fallo", _falla)
        assert llamadas["n"] == 1, "el fallo no se guardó: se vuelve a esperar cada vez"
        diagnostico._PING_CACHE.clear()
