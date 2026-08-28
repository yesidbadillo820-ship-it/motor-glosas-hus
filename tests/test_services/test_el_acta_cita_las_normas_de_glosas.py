"""El acta que firman el HUS y la EPS invocaba tres normas mal.

28-08-2026. Revisando las normas del corpus que nadie había contrastado contra
su fuente, apareció que la Res. 2175 de 2015 estaba cargada como «procedimiento
de conciliación de glosas médicas». No es eso. Encabezado literal, bajado del
normograma de la Superintendencia Nacional de Salud:

    «RESOLUCIÓN 2175 DE 2015 (junio 18) — Por la cual se establece el anexo
     técnico para el reporte de las atenciones en salud a menores de 18 años,
     gestantes y atenciones de parto y se adopta el mecanismo de transferencia
     de los archivos.»

Es del programa Familias en Acción. Es el mismo error de la Ley 1388 de 2010
—citada para discapacidad auditiva cuando es de cáncer infantil— pero dentro de
nuestro propio tema, y no en un borrador: en el **acta de conciliación**, el
documento que firman un representante del hospital y uno de la EPS. Decía
suscribirse «en cumplimiento de … la Resolución 2175 de 2015». A la EPS le
bastaba abrirla.

Y las otras dos citas de esa misma frase también estaban corridas, ambas al
artículo de al lado:

- **Ley 1438 de 2011, art. 56** → es «Pagos a los prestadores». El trámite de
  glosas es el **57**, que es el que el motor usa en todas partes.
- **Decreto 4747 de 2007, art. 20** → es el del RIPS. El trámite de glosas es
  el **23**. Ya existía una red que corrige justamente esa confusión en los
  dictámenes; el acta no pasa por ella.

Los textos de los cuatro artículos están cargados literales en el corpus, así
que esta prueba los contrasta contra el corpus, no contra la memoria de nadie.
"""

from __future__ import annotations

import pathlib

from app.services.normativa import NORMAS_VIGENTES
from app.services.normativa_completa import _TODAS_LAS_NORMAS

RAIZ = pathlib.Path(__file__).resolve().parents[2]
ACTA = RAIZ / "app" / "api" / "routers" / "conciliacion.py"


def _texto_del_acta() -> str:
    return ACTA.read_text(encoding="utf-8")


class TestElActaNoInvocaLaNormaEquivocada:
    def test_no_nombra_la_2175(self):
        """Es de reporte de atenciones a menores y gestantes, no de glosas."""
        assert "2175" not in _texto_del_acta()

    def test_invoca_el_manual_unico(self):
        acta = _texto_del_acta()
        assert "2284 de 2023" in acta
        assert "Anexo Técnico 3" in acta

    def test_invoca_el_articulo_del_tramite_de_glosas_no_el_de_pagos(self):
        acta = _texto_del_acta()
        assert "artículo 57 de la Ley 1438 de 2011" in acta
        assert "artículo 56 de la Ley 1438 de 2011" not in acta

    def test_invoca_el_articulo_23_del_4747_no_el_del_rips(self):
        acta = _texto_del_acta()
        assert "artículo 23" in acta
        assert "artículo 20" not in acta


class TestLosArticulosSonLosQueDiceElCorpus:
    """Se contrasta contra el texto literal cargado, no contra la memoria."""

    def test_el_57_de_la_1438_es_el_de_glosas(self):
        art = _TODAS_LAS_NORMAS["LEY 1438 DE 2011"]["articulos"]["57"]
        assert "glosa" in (art.get("titulo", "") + art.get("texto", "")).lower()

    def test_el_56_de_la_1438_es_el_de_pagos(self):
        art = _TODAS_LAS_NORMAS["LEY 1438 DE 2011"]["articulos"]["56"]
        assert "pago" in art.get("titulo", "").lower()

    def test_el_23_del_4747_es_el_de_glosas(self):
        art = _TODAS_LAS_NORMAS["DECRETO 4747 DE 2007"]["articulos"]["23"]
        assert "glosa" in art.get("titulo", "").lower()

    def test_el_20_del_4747_es_el_del_rips(self):
        art = _TODAS_LAS_NORMAS["DECRETO 4747 DE 2007"]["articulos"]["20"]
        assert "RIPS" in art.get("titulo", "")


class TestElCorpusYaNoLaOfreceParaGlosas:
    def test_la_ficha_dice_lo_que_de_verdad_dice_la_norma(self):
        f = _TODAS_LAS_NORMAS["RESOLUCION 2175 DE 2015"]
        titulo = f["titulo"].lower()
        assert "gestantes" in titulo or "menores de 18" in titulo
        assert "conciliación de glosas" not in titulo

    def test_no_la_busca_nadie_por_la_palabra_conciliacion(self):
        """Con «conciliación» entre las claves, el buscador del corpus se la
        ofrecía a la IA justo para el tema en el que no sirve."""
        claves = [k.lower() for k in _TODAS_LAS_NORMAS["RESOLUCION 2175 DE 2015"]["keywords"]]
        assert "conciliación" not in claves
        assert "auditoría médica" not in claves

    def test_el_catalogo_corto_tambien_quedo_corregido(self):
        resumen = NORMAS_VIGENTES["RESOLUCION 2175/2015"]["resumen"].lower()
        assert "conciliación de glosas médicas." != resumen
        assert "gestantes" in resumen or "menores de 18" in resumen

    def test_queda_anotada_la_fuente(self):
        f = _TODAS_LAS_NORMAS["RESOLUCION 2175 DE 2015"]
        assert "28-08-2026" in f.get("verificada", "")
