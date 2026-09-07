"""Dos defectos que se vieron corriendo el motor del hospital, no en pruebas.

28-08-2026, dictamen GL-134 de la factura HUS0000498954, corrido por el
auditor en la PC de cartera con el código ya desplegado.

**1. La causal seguía saliendo como nombre del servicio.**
El recuadro decía «Servicio objetado: CONSULTA DE PRIMERA VEZ POR OTRAS
ESPECIALIDADES MÉDICAS, **código SO0102**». Ayer se puso la red que borra las
causales del CUERPO del dictamen — y funcionó ahí. Pero este campo **no pasa
por ella**: la IA lo entrega aparte, en su etiqueta `<servicio>`, y el recuadro
se arma después. Escribir la regla no era el trabajo; el trabajo era comprobar
que llegara a los dos sitios.

**2. El sello describía un documento que ya no existía.**
La red ya le había quitado el rótulo de CUPS al 380125 —en el escrito quedó
como «código», con su aviso— y aun así el sello seguía mostrando
«CUPS_INEXISTENTE · CUPS 380125» en severidad ALTA. El revisor de citas corre
ANTES que las redes. El gestor lee un hallazgo grave sobre algo que ya no está,
y de ahí a no creerle al sello hay un paso — que es justo lo que esta semana
costó tanto arreglar.
"""

from __future__ import annotations

import ast
import pathlib

from app.services.glosa_service import _quitar_causal_del_servicio


class TestLaCausalNoEsElNombreDelServicio:
    def test_el_caso_real_del_gl_134(self):
        s = "CONSULTA DE PRIMERA VEZ POR OTRAS ESPECIALIDADES MÉDICAS, código SO0102"
        r = _quitar_causal_del_servicio(s)
        assert "SO0102" not in r
        assert r == "CONSULTA DE PRIMERA VEZ POR OTRAS ESPECIALIDADES MÉDICAS"

    def test_tambien_cuando_la_llama_cups(self):
        assert _quitar_causal_del_servicio("ESTANCIA GENERAL, CUPS TA0201") == "ESTANCIA GENERAL"

    def test_un_cups_de_verdad_no_se_toca(self):
        s = "RADIOGRAFIA DE TORAX CUPS 871121"
        assert _quitar_causal_del_servicio(s) == s

    def test_un_servicio_limpio_queda_igual(self):
        s = "CONSULTA DE PRIMERA VEZ"
        assert _quitar_causal_del_servicio(s) == s

    def test_no_deja_el_campo_vacio(self):
        """Si al quitar la causal no quedara nada, se conserva lo que había:
        un recuadro sin servicio es peor que uno con el texto original."""
        assert _quitar_causal_del_servicio("SO0102") == "SO0102"

    def test_vacio_no_rompe(self):
        assert _quitar_causal_del_servicio("") == ""
        assert _quitar_causal_del_servicio(None) is None

    def test_esta_cableado_donde_se_arma_el_recuadro(self):
        fuente = pathlib.Path("app/services/glosa_service.py").read_text(encoding="utf-8")
        assert "servicio_ia = _quitar_causal_del_servicio(servicio_ia" in fuente, (
            "el campo <servicio> de la IA tiene que pasar por la limpieza: es el "
            "que alimenta el recuadro, y no pasa por la red del cuerpo"
        )
        # 31-08-2026: la limpieza recibe además el código de ESTA glosa, para
        # poder borrarlo aunque no figure en el catálogo de causales (CL4506).
        assert "_cod_de_esta_glosa" in fuente, (
            "la limpieza dejó de recibir el código de la glosa que se contesta"
        )


class TestElSelloSeRecalculaTrasLimpiarElTexto:
    def _analizar(self):
        fuente = pathlib.Path("app/services/glosa_service.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        return next(
            n
            for n in ast.walk(arbol)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "analizar"
        )

    def test_se_vuelve_a_revisar_despues_de_quitar_los_cups(self):
        fuente = pathlib.Path("app/services/glosa_service.py").read_text(encoding="utf-8")
        i = fuente.find("_dictamen_cups_respaldado = _neutralizar_cups_sin_respaldo")
        assert i > 0
        bloque = fuente[i : i + 1600]
        assert "verif_citas = _vc(" in bloque, (
            "sin re-revisar, el sello sigue mostrando un hallazgo sobre un texto "
            "que la red ya limpió"
        )

    def test_todas_las_revisiones_llevan_la_evidencia(self):
        """La prueba que atajó el error del 26-08 sigue mandando: revisar sin
        evidencia deja pasar un folio inventado."""
        llamadas = [
            n
            for n in ast.walk(self._analizar())
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "_vc"
        ]
        assert len(llamadas) >= 3
        for c in llamadas:
            assert "evidencia" in {k.arg for k in c.keywords}
