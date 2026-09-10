"""Anthropic fallaba sin decir por qué, y sin reintentar.

10-09-2026. En el PC del hospital, cada llamada a Anthropic salía así:

    IA anthropic falló: . Intentando siguiente proveedor…

Un punto después de los dos puntos: el motivo venía VACÍO. Y fallaba en medio
segundo, o sea que no pasó por los tres reintentos que el código creía tener.

DOS DEFECTOS, LOS DOS CAROS:

1. La lista de «errores de red» nombraba los tipos UNO POR UNO y se dejó por
   fuera `httpx.ConnectError` — justo el que lanza una conexión cortada por el
   host remoto, el «WinError 10054» que el panel de Diagnóstico le venía
   mostrando al auditor. Al no estar en la lista, no se reintentaba.

2. El aviso imprimía `str(e)` a secas, y los cortes de conexión vienen sin
   texto. El auditor veía que algo falló y no tenía ni una palabra que buscar.

Lo que costaba: el motor escala a Claude los casos complejos a propósito
(«Llama 4 Scout alucina en estos casos»). Con este defecto, esos casos caían
a Groq en silencio al primer corte de red. Pasó con una glosa de $55.985.100.
"""

from __future__ import annotations

import httpx
import pytest

from app.services.glosa_service import _motivo_del_fallo


class TestElMotivoNuncaQuedaVacio:
    def test_un_corte_de_conexion_dice_al_menos_el_tipo(self):
        """Estos errores vienen sin texto: `str(e)` es la cadena vacía."""
        assert str(httpx.ConnectError("")) == "", "la prueba dejó de reproducir el caso"
        assert _motivo_del_fallo(httpx.ConnectError("")) == "ConnectError"

    def test_cuando_hay_texto_se_conserva(self):
        assert _motivo_del_fallo(RuntimeError("clave inválida")) == "RuntimeError: clave inválida"

    @pytest.mark.parametrize(
        "error",
        [
            httpx.ConnectError(""),
            httpx.ReadError(""),
            httpx.RemoteProtocolError(""),
            RuntimeError(""),
            Exception(),
        ],
    )
    def test_ningun_fallo_se_queda_sin_motivo(self, error):
        motivo = _motivo_del_fallo(error)
        assert motivo.strip(), "un fallo sin motivo deja al auditor sin nada que buscar"
        assert motivo != "."

    def test_el_codigo_ya_no_imprime_el_error_a_pelo(self):
        """Si alguien vuelve a poner `{e}` suelto, esta prueba avisa."""
        import inspect

        from app.services.glosa_service import GlosaService

        fuente = inspect.getsource(GlosaService._llamar_ia)
        assert "_motivo_del_fallo(e)" in fuente
        assert "falló: {e}." not in fuente


class TestUnCorteDeRedSeReintenta:
    """La lista de errores de red ya no se enumera a mano."""

    @pytest.mark.parametrize(
        "clase,que_es",
        [
            (httpx.ConnectError, "conexión cortada por el host remoto (WinError 10054)"),
            (httpx.ConnectTimeout, "no alcanzó a conectar"),
            (httpx.ReadTimeout, "conectó y no contestó a tiempo"),
            (httpx.ReadError, "se cortó leyendo la respuesta"),
            (httpx.WriteError, "se cortó enviando la petición"),
            (httpx.WriteTimeout, "se demoró enviando"),
            (httpx.PoolTimeout, "sin conexiones libres"),
            (httpx.RemoteProtocolError, "el otro lado habló mal el protocolo"),
        ],
    )
    def test_cuenta_como_error_de_red(self, clase, que_es):
        assert issubclass(clase, httpx.TransportError), (
            f"«{que_es}» no se reintentaría: el motor se rendiría al primer intento"
        )

    def test_el_codigo_usa_la_clase_madre_y_no_una_lista(self):
        """Enumerarlos a mano fue el error: la lista se queda corta en silencio."""
        import inspect

        from app.services.glosa_service import GlosaService

        fuente = inspect.getsource(GlosaService._llamar_anthropic)
        assert "_ERRORES_TRANSITORIOS = (httpx.TransportError,)" in fuente

    def test_un_error_que_no_es_de_red_no_se_reintenta(self):
        """Una clave inválida no se arregla reintentando: hay que avisar."""
        assert not issubclass(ValueError, httpx.TransportError)
        assert not issubclass(RuntimeError, httpx.TransportError)
