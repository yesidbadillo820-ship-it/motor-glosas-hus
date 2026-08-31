"""Una hoja suelta del dictamen no decía de qué factura era.

31-08-2026, cuarta idea del repaso de diseño.

En casi todos los programas imprimir es lo último que se cuida. Aquí es al
revés: **el papel es lo que llega a la EPS**. El dictamen se imprime, se anexa
y se radica — y en la mesa de radicación las hojas se separan, se traspapelan
y se vuelven a juntar.

El número de factura aparecía **una sola vez**, en el membrete de la primera
hoja. De la segunda en adelante no había nada que dijera a qué factura
pertenecían.

Ahora hay un pie que se repite en todas las hojas impresas con la entidad, la
factura y la fecha. En pantalla no existe: `position: fixed` dentro de
`@media print` es lo que los navegadores sí respetan para repetir algo en cada
página.

Y se agregó control de viudas y huérfanas al cuerpo del dictamen: un párrafo
jurídico partido dejando una línea sola al final de la hoja se lee como si
faltara texto.

LO QUE ESTA PRUEBA NO REVISA: que el estilo de impresión completo esté bien.
Ya estaba trabajado desde antes —oculta el menú, la cabecera, los botones y
los avisos internos, y deja el sello legible— y no se tocó.
"""

from __future__ import annotations

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
HTML = (RAIZ / "static" / "index.html").read_text(encoding="utf-8")
CSS = (RAIZ / "static" / "sinac-ds.css").read_text(encoding="utf-8")


def _bloque_print() -> str:
    i = CSS.index(".doc-pie-corrido { display: none; }")
    return CSS[i : CSS.index(".sds-kbd {", i)]


class TestCadaHojaDiceDeQueFacturaEs:
    def test_el_pie_existe_en_el_dictamen(self):
        assert "doc-pie-corrido" in HTML

    def test_lleva_la_factura(self):
        i = HTML.index('class="doc-pie-corrido"')
        assert "_facturaImpresa" in HTML[i : i + 400]

    def test_lleva_la_entidad_y_la_fecha(self):
        i = HTML.index('class="doc-pie-corrido"')
        trozo = HTML[i : i + 400]
        assert "ESE HUS" in trozo
        assert "fechaLarga" in trozo

    def test_la_factura_va_escapada(self):
        i = HTML.index('class="doc-pie-corrido"')
        assert "escHtml(_facturaImpresa)" in HTML[i : i + 400]

    def test_na_no_es_un_numero_de_factura(self):
        """«N/A» es falta de dato. Si el motor no la manda se toma la que el
        auditor escribió en el formulario."""
        i = HTML.index("var _facturaImpresa = ''")
        trozo = HTML[i : i + 500]
        assert "'N/A'" in trozo
        assert "f-factura" in trozo

    def test_sin_factura_el_pie_no_inventa_nada(self):
        """Sale con la entidad y la fecha, sin un número falso."""
        i = HTML.index('class="doc-pie-corrido"')
        assert "_facturaImpresa ?" in HTML[i : i + 400]


class TestSoloExisteEnElPapel:
    def test_en_pantalla_no_se_ve(self):
        assert ".doc-pie-corrido { display: none; }" in CSS

    def test_se_repite_en_todas_las_hojas(self):
        """position:fixed dentro de @media print es lo que los navegadores
        respetan para repetir algo en cada página."""
        b = _bloque_print()
        assert "@media print" in b
        i = b.index("@media print")
        assert "position: fixed" in b[i:]


class TestNingunParrafoQuedaPartidoFeo:
    def test_hay_control_de_viudas_y_huerfanas(self):
        """Un párrafo jurídico que deja una línea sola al final de la hoja se
        lee como si faltara texto."""
        b = _bloque_print()
        assert re.search(r"orphans:\s*3", b)
        assert re.search(r"widows:\s*3", b)

    def test_aplica_al_cuerpo_del_dictamen(self):
        b = _bloque_print()
        assert ".res-dictamen-body p" in b


class TestNoSeRompioLoQueYaEstaba:
    def test_el_menu_y_la_cabecera_siguen_ocultos_al_imprimir(self):
        assert re.search(r"header,\.sidebar-nav[^}]*display:none", HTML)

    def test_el_sello_sigue_saliendo_en_el_papel(self):
        assert ".card-doc.qg-ok .qg-seal" in HTML

    def test_el_panel_de_correcciones_sigue_sin_imprimirse(self):
        """Es una nota interna: no puede salir en el escrito que va a la EPS."""
        i = HTML.index("res-correcciones")
        assert "no-print" in HTML[i - 200 : i + 200]
