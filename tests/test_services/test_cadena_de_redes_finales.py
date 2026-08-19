"""Invariantes de la cadena de redes finales del dictamen.

Las redes finales son la última defensa antes de que el documento se radique
ante la entidad: cada una borra o corrige algo que el motor afirmó sin poder
probarlo. A 06-08-2026 son 18, y casi todas nacieron de un dictamen real que
salió mal.

Dos formas de que una red deje de proteger sin que nadie se entere:

  1. **Que se defina y no se conecte.** Queda el código, quedan sus pruebas
     unitarias en verde, y el dictamen sale sin pasar por ella. Es
     exactamente el caso de OT-020: las 26 cláusulas existían desde julio
     con su script, pero nadie lo llamaba.

  2. **Que se conecte sin red de seguridad.** Si una red revienta y la
     excepción sube, se cae el análisis entero y el auditor se queda sin
     dictamen — peor que el defecto que la red iba a corregir.

Estas dos pruebas vigilan lo uno y lo otro para TODA red presente y futura,
sin tener que acordarse de agregarla a una lista.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from app.services import glosa_service as gs
from app.services.glosa_service import GlosaService

_PREFIJOS = ("_neutralizar", "_quitar_signos", "_rechazar", "_reescribir", "_corregir", "_refutar")


def _redes() -> list[str]:
    """Toda función del módulo que corrige el dictamen antes de entregarlo."""
    return sorted(
        n
        for n in dir(gs)
        if n.startswith(_PREFIJOS) and callable(getattr(gs, n)) and not n.endswith("_legacy")
    )


class TestNingunaRedQuedaDesconectada:
    def test_hay_redes_que_vigilar(self):
        """Sanity: si esto baja de golpe, alguien borró media defensa."""
        assert len(_redes()) >= 15

    def test_todas_se_llaman_desde_el_analisis(self):
        src = inspect.getsource(GlosaService.analizar)
        sueltas = [r for r in _redes() if f"{r}(" not in src]
        assert not sueltas, (
            f"redes definidas que NUNCA se llaman al armar el dictamen: {sueltas}. "
            "El código existe, sus pruebas pasan, y el documento se radica sin "
            "pasar por ellas."
        )


class TestNingunaRedPuedeTumbarElDictamen:
    def test_todas_van_dentro_de_un_try(self):
        """Un fallo de una red no puede dejar al auditor sin dictamen.

        Se lee el árbol del código, no líneas alrededor: contar líneas da
        falsos positivos cuando un solo `try` cubre varias redes seguidas.
        """
        arbol = ast.parse(textwrap.dedent(inspect.getsource(GlosaService.analizar)))
        redes = set(_redes())
        protegidas: set[str] = set()
        llamadas: set[str] = set()

        def _recorrer(nodo, dentro_de_try: bool) -> None:
            for hijo in ast.iter_child_nodes(nodo):
                if isinstance(hijo, ast.Call):
                    fn = hijo.func
                    nombre = getattr(fn, "id", None) or getattr(fn, "attr", None)
                    if nombre in redes:
                        llamadas.add(nombre)
                        if dentro_de_try:
                            protegidas.add(nombre)
                if isinstance(hijo, ast.Try):
                    for sub in hijo.body:
                        _recorrer(sub, True)
                    for sub in hijo.handlers + hijo.orelse + hijo.finalbody:
                        _recorrer(sub, dentro_de_try)
                    # El propio nodo Try ya se recorrió por partes.
                    if isinstance(hijo, ast.Try):
                        continue
                _recorrer(hijo, dentro_de_try)

        _recorrer(arbol, False)
        sin_proteccion = sorted(llamadas - protegidas)
        assert not sin_proteccion, (
            f"redes llamadas sin try/except alrededor: {sin_proteccion}. "
            "Si revientan, se cae el análisis completo y el auditor se queda "
            "sin dictamen — peor que el defecto que la red iba a corregir."
        )

    def test_ninguna_devuelve_none_con_texto_valido(self):
        """Una red que devuelva None en vez del texto vaciaría el dictamen.

        Se les pasa un dictamen inocuo: ninguna debe encontrar nada que
        corregir, y todas deben devolver una cadena.
        """
        limpio = (
            "ESE HUS NO ACEPTA LA GLOSA. EL SERVICIO FUE PRESTADO Y FACTURADO "
            "CONFORME A LO PACTADO. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        )
        for nombre in _redes():
            fn = getattr(gs, nombre)
            params = list(inspect.signature(fn).parameters)
            if not params:
                continue
            try:
                salida = fn(limpio) if len(params) == 1 else fn(limpio, "")
            except TypeError:
                continue  # firma que no encaja con la sonda; la cubren sus propias pruebas
            assert isinstance(salida, str), f"{nombre} devolvió {type(salida).__name__}"
            assert salida.strip(), f"{nombre} vació un dictamen que no tenía nada malo"

    def test_ninguna_revienta_con_texto_vacio(self):
        for nombre in _redes():
            fn = getattr(gs, nombre)
            params = list(inspect.signature(fn).parameters)
            if not params:
                continue
            try:
                fn("") if len(params) == 1 else fn("", "")
            except TypeError:
                continue
            except Exception as e:  # noqa: BLE001 - el punto de la prueba
                raise AssertionError(f"{nombre} revienta con texto vacío: {e}") from e
