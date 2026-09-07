"""Que un código esté en el expediente no lo vuelve un CUPS.

27-08-2026. Defecto propio, del día anterior. El 26-08 se conectó la búsqueda
del CUPS en DGH —idea #4— para que el dictamen volviera a nombrar el servicio
con su código en vez de quedarse sin él. La función devolvía tal cual lo que
estuviera en la columna de DGH.

Lo destapó un dictamen real que mandó el auditor, GL-134 (factura
HUS0000498954): decía «CONSULTA DE PRIMERA VEZ POR OTRAS ESPECIALIDADES
MÉDICAS CUPS 380125», y **380125 no existe en el catálogo**. Los de consulta
de primera vez son la familia 8902xx / 8903xx.

Ya había precedente el 21-08: «CUPS FMQ0952» no es un CUPS. En DGH caben
códigos que no lo son.

POR QUÉ IMPORTA TANTO, con las palabras del propio motor: «la EPS cruza los
CUPS contra su sistema: un código inventado tumba la defensa completa, así el
argumento jurídico esté bien».

DOS AGUJEROS, NO UNO:

  1. `_cups_desde_dgh` entregaba cualquier cosa que DGH tuviera guardada.
  2. La red que quita códigos inventados **perdonaba el código si aparecía en
     la evidencia** — y uno que viene de DGH aparece. Estar en el expediente
     no es prueba de ser un CUPS.

Lo que NO se hace: borrar el código a secas. Puede ser el que usa la entidad y
el auditor lo reconoce. Se le quita el rótulo de «CUPS», que es lo que hace el
daño, y se avisa.
"""

from __future__ import annotations

from app.services.glosa_service import (
    _cups_desde_dgh,
    _cups_esta_en_catalogo,
    _neutralizar_cups_sin_respaldo,
)

EN_EVIDENCIA = "DGH registra 380125 para la factura HUS0000498954"


class TestElCasoRealDelAuditor:
    def test_380125_no_existe_y_890201_si(self):
        """Los de consulta de primera vez son 8902xx / 8903xx."""
        assert not _cups_esta_en_catalogo("380125")
        assert _cups_esta_en_catalogo("890201")

    def test_el_codigo_del_expediente_deja_de_llamarse_cups(self):
        d = "SERVICIO OBJETADO: CONSULTA DE PRIMERA VEZ CUPS 380125"
        r = _neutralizar_cups_sin_respaldo(d, EN_EVIDENCIA)
        assert "código 380125" in r, "el número se conserva: puede ser el que usa la entidad"
        assert "CUPS 380125" not in r, "pero deja de presentarse como un CUPS"

    def test_y_se_le_avisa_al_gestor_con_que_resolverlo(self):
        d = "SERVICIO OBJETADO: CONSULTA CUPS 380125"
        r = _neutralizar_cups_sin_respaldo(d, EN_EVIDENCIA)
        assert "REVISE EL CÓDIGO ANTES DE RADICAR" in r
        assert "Consulta Normativa" in r, "hay que decirle dónde buscar el bueno"


class TestLoQueYaFuncionabaSigueIgual:
    def test_un_cups_de_verdad_no_se_toca(self):
        d = "SERVICIO OBJETADO: CONSULTA CUPS 890201"
        assert _neutralizar_cups_sin_respaldo(d, "") == d

    def test_un_cups_de_verdad_tampoco_se_toca_estando_en_la_evidencia(self):
        d = "SERVICIO OBJETADO: CONSULTA CUPS 890201"
        assert _neutralizar_cups_sin_respaldo(d, "el expediente trae 890201") == d

    def test_el_inventado_sin_respaldo_se_sigue_borrando(self):
        d = "SERVICIO OBJETADO: CONSULTA CUPS 999999 DEL PACIENTE"
        r = _neutralizar_cups_sin_respaldo(d, "")
        assert "999999" not in r
        assert "CONSULTA" in r, "se conserva el nombre del servicio; lo que sale es el número"

    def test_un_texto_vacio_no_rompe(self):
        assert _neutralizar_cups_sin_respaldo("", "algo") == ""


class TestDghNoEntregaLoQueNoEsUnCups:
    def test_sin_factura_sigue_devolviendo_vacio(self):
        assert _cups_desde_dgh(None) == ("", "")
        assert _cups_desde_dgh("") == ("", "")

    def test_una_factura_que_no_esta_no_inventa_un_codigo(self):
        assert _cups_desde_dgh("HUS0000000000") == ("", "")

    def test_la_funcion_comprueba_el_catalogo_antes_de_entregar(self):
        """El cableado: sin esta comprobación, DGH vuelve a colar un no-CUPS."""
        import inspect

        fuente = inspect.getsource(_cups_desde_dgh)
        assert "_cups_esta_en_catalogo" in fuente, (
            "la función tiene que contrastar contra el catálogo antes de entregar "
            "el código como CUPS"
        )
        assert 'return "", descripcion' in fuente, (
            "cuando el código no es un CUPS se devuelve la descripción sin el número: "
            "es mejor quedarse sin código que poner uno que no lo es"
        )
