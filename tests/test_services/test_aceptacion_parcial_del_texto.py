"""Si la glosa dice que el hospital acepta parte, el motor no puede ignorarlo.

Prueba real del 05-08-2026, glosa de trampa Nº 5:

    "AU0401 SE OBJETA LA TOTALIDAD DE $2.100.000 POR FALTA DE AUTORIZACIÓN.
     LA IPS ACEPTA $340.000 CORRESPONDIENTES A DOS INSUMOS NO SOPORTADOS Y
     CONTROVIERTE EL RESTO."

El motor contestó «GLOSA NO ACEPTADA - SUBSANADA EN SU TOTALIDAD» y el panel
recomendó DEFENDER 100% ($2.100.000). La aceptación parcial existía en el
sistema desde hacía meses, pero solo se encendía si el auditor escribía el
monto en el formulario: nadie leía esa frase del texto pegado.

Lo que se lee es una SEÑAL, no una decisión: el sistema avisa y el auditor
mueve la plata. Igual que con la extemporaneidad inferida del texto.
"""

from __future__ import annotations

from app.utils.parsers_glosa import extraer_aceptacion_ips

GLOSA_REAL = (
    "AU0401 SE OBJETA LA TOTALIDAD DE $2.100.000 POR FALTA DE AUTORIZACIÓN. "
    "LA IPS ACEPTA $340.000 CORRESPONDIENTES A DOS INSUMOS NO SOPORTADOS Y "
    "CONTROVIERTE EL RESTO."
)


class TestLoQueElHospitalDeclaraAceptar:
    def test_lee_la_glosa_que_engano_al_motor(self):
        assert extraer_aceptacion_ips(GLOSA_REAL, 2_100_000) == 340_000

    def test_tambien_con_otras_formas_de_decirlo(self):
        casos = [
            ("SE ACEPTA PARCIALMENTE $500.000 DEL VALOR OBJETADO", 500_000),
            ("LA ESE ACEPTA $1.200.000 Y CONTROVIERTE EL RESTO", 1_200_000),
            ("ACEPTAMOS EL VALOR DE $75.000 POR INSUMO NO SOPORTADO", 75_000),
            ("EL PRESTADOR ACEPTA LA SUMA DE $2.000.000", 2_000_000),
        ]
        for texto, esperado in casos:
            assert extraer_aceptacion_ips(texto, 9_000_000) == esperado, texto

    def test_en_minusculas_tambien(self):
        assert extraer_aceptacion_ips("la ips acepta $340.000 del total", 2_100_000) == 340_000


class TestCuandoNoHayQueInferirNada:
    def test_sin_senal_devuelve_cero(self):
        assert extraer_aceptacion_ips("SO0201 FALTA EPICRISIS. VALOR $890.000", 890_000) == 0.0

    def test_aceptar_todo_no_es_parcial(self):
        """Aceptar la glosa entera es una decisión de plata: no se infiere de
        un texto, la toma el auditor."""
        texto = "LA IPS ACEPTA $2.100.000 DEL VALOR OBJETADO"
        assert extraer_aceptacion_ips(texto, 2_100_000) == 0.0

    def test_un_monto_mayor_al_objetado_se_descarta(self):
        texto = "LA IPS ACEPTA $5.000.000"
        assert extraer_aceptacion_ips(texto, 2_100_000) == 0.0

    def test_lo_que_acepta_la_EPS_no_cuenta(self):
        """«LA EPS RECONOCE» es lo contrario: lo que el pagador admite pagar."""
        texto = "LA EPS RECONOCE $340.000 Y OBJETA EL RESTO"
        assert extraer_aceptacion_ips(texto, 2_100_000) == 0.0

    def test_texto_vacio_no_revienta(self):
        assert extraer_aceptacion_ips("", 100) == 0.0
        assert extraer_aceptacion_ips(None, 100) == 0.0


class TestElBotonQueNoHaciaNada:
    """El botón «Aplicar recomendación» buscaba tres identificadores que no
    existen y aun así cantaba éxito: el auditor creía haber cargado el valor
    aceptado, reanalizaba, y el motor seguía defendiendo el 100%."""

    def _html(self):
        from pathlib import Path

        raiz = Path(__file__).resolve().parent.parent.parent
        return (raiz / "static" / "index.html").read_text(encoding="utf-8", errors="ignore")

    def test_apunta_al_campo_real(self):
        html = self._html()
        assert "getElementById('f-valacp')" in html

    def test_ya_no_busca_identificadores_que_no_existen(self):
        html = self._html()
        assert "getElementById('valor-aceptado')" not in html
        assert "getElementById('valorAceptado')" not in html

    def test_si_no_encuentra_el_campo_lo_dice(self):
        html = self._html()
        i = html.index("function aplicarRecomendacionIA")
        cuerpo = html[i : i + 1600]
        assert "No se pudo aplicar" in cuerpo
        assert "No encuentro el campo" in cuerpo
