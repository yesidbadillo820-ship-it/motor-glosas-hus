"""El motor no puede abstenerse de una glosa que sí identifica el servicio.

09-09-2026, hallazgo del análisis de código del auditor — y ninguno de los
dos análisis lo marcó como crítico, siendo el único de toda la lista que
afecta el papel que se radica.

CÓMO ERA. `_glosa_sin_elementos` corta en seco cuando hay un CUPS
verificado (línea 5298): un servicio identificado ES un elemento, y con él
no hay nada de qué abstenerse. Pero el CUPS se extraía **270 líneas más
abajo**, DENTRO de la rama de la IA —o sea, después de que la decisión de
abstenerse ya estaba tomada— y en el sitio de la decisión se leía con
`locals().get("cups_verificado")`, que devolvía `None` **siempre**.

O sea que ese atajo, escrito a propósito, nunca se activó ni una vez.

QUÉ COSTABA. El motor podía negarse a responder una glosa que traía el
servicio perfectamente identificado, y entregar el texto de abstención
—«no hay elementos para pronunciarse»— en lugar de una defensa. Una glosa
sin contestar se ratifica.

QUÉ CUIDA ESTA PRUEBA. Que la guarda reciba el CUPS de verdad, y que la
abstención siga funcionando cuando de verdad no hay nada — porque apagarla
sería el error contrario: la abstención existe por un caso real (PRUEBA 5,
FA0205: sin evidencia no se llama a la IA).
"""

from __future__ import annotations

import inspect

import pytest

from app.services import glosa_service
from app.services.glosa_service import _glosa_sin_elementos


class TestLaGuardaHaceLoQueDice:
    def test_con_un_cups_verificado_NO_se_abstiene(self):
        """Es la línea 5298, la que nunca se ejecutaba."""
        assert _glosa_sin_elementos("TA0201 GLOSA SIN MAS DETALLE", "", "890201") is False, (
            "Con el servicio identificado no hay nada de qué abstenerse."
        )

    def test_sin_cups_y_sin_nada_mas_SI_se_abstiene(self):
        """La abstención tiene que seguir funcionando: existe por un caso
        real y apagarla sería peor que el defecto."""
        assert _glosa_sin_elementos("FA0205 | HUS123 | ", "", "") is True

    def test_un_cups_vacio_no_cuenta_como_elemento(self):
        assert _glosa_sin_elementos("FA0205 | HUS123 | ", "", "   ") is True


class TestElCupsLlegaAntesDeDecidir:
    """El defecto no estaba en la guarda sino en QUIÉN la llama: le pasaba
    una variable que en ese punto del método no existe."""

    @staticmethod
    def _cuerpo_del_analisis() -> str:
        """El CÓDIGO de `analizar`, sin comentarios.

        Hace falta quitarlos: los comentarios que explican este mismo arreglo
        citan las formas viejas («locals().get(...)») para dejar dicho qué se
        cambió y por qué. Buscándolas sobre el texto completo, la prueba se
        encontraría a sí misma y fallaría por su propia documentación.
        """
        fuente = inspect.getsource(glosa_service.GlosaService.analizar)
        return "\n".join(ln for ln in fuente.splitlines() if not ln.lstrip().startswith("#"))

    def test_ya_no_se_lee_con_locals(self):
        cuerpo = self._cuerpo_del_analisis()
        assert 'locals().get("cups_verificado") or ""' not in cuerpo, (
            "Sigue leyendo el CUPS con locals() en el sitio donde todavía no "
            "existe: la guarda seguiría recibiendo cadena vacía siempre."
        )

    def test_se_extrae_ANTES_de_decidir_la_abstencion(self):
        """El orden es el arreglo: si se extrae después, da igual cómo se lea."""
        cuerpo = self._cuerpo_del_analisis()
        i_extrae = cuerpo.index('cups_verificado = _c_pre or ""')
        i_decide = cuerpo.index("_abstenerse = (not _hay_algo_mas)")
        assert i_extrae < i_decide, "El CUPS se sigue extrayendo después de decidir la abstención."

    def test_la_guarda_recibe_la_variable_de_verdad(self):
        cuerpo = self._cuerpo_del_analisis()
        i = cuerpo.index("_abstenerse = (not _hay_algo_mas)")
        assert 'contexto_pdf or "", cups_verificado' in cuerpo[i : i + 250]

    def test_la_rama_de_la_ia_no_lo_recalcula_al_pedo(self):
        """Se reutiliza lo ya extraído; solo se reintenta si quedó vacío."""
        cuerpo = self._cuerpo_del_analisis()
        assert "if not cups_verificado:" in cuerpo


class TestElCodigoMuertoQueSeRetiro:
    """`locals().get("tabla_excel")` tampoco existía — pero ese NO se arregla
    conectándolo: `data.tabla_excel` es obligatorio (min_length=3), así que
    `_hay_algo_mas` daría True siempre y la abstención no volvería a
    activarse. Se retiró."""

    @staticmethod
    def _codigo() -> str:
        """Sin comentarios, por lo mismo que arriba."""
        fuente = inspect.getsource(glosa_service.GlosaService.analizar)
        return "\n".join(ln for ln in fuente.splitlines() if not ln.lstrip().startswith("#"))

    def test_ya_no_esta(self):
        assert 'locals().get("tabla_excel")' not in self._codigo()

    def test_y_la_abstencion_sigue_pudiendo_activarse(self):
        """La prueba de que no se apagó de rebote."""
        assert "_abstenerse = (not _hay_algo_mas)" in self._codigo()


class TestLaCondicionImposible:
    """`if ... and not m:` con un `if not m: return` tres renglones arriba:
    `m` siempre tiene valor ahí, así que la guarda de tarifas neutras nunca
    se aplicaba."""

    @pytest.mark.parametrize("neutra_en_el_texto", [True, False])
    def test_la_guarda_de_tarifas_neutras_ya_se_evalua(self, neutra_en_el_texto):
        fuente = "\n".join(
            ln
            for ln in inspect.getsource(glosa_service).splitlines()
            if not ln.lstrip().startswith("#")
        )
        i = fuente.index("_TARIFAS_NEUTRAS)")
        alrededor = fuente[i - 200 : i + 120]
        assert "and not m" not in alrededor, (
            "La condición imposible sigue ahí: la guarda no se aplica nunca."
        )
