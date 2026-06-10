"""Tests de app/utils/html_a_texto — conversión de dictamen HTML a
texto plano legible para Excel-respuesta, export de historial y PDF.

El bug original: la columna RESPUESTA IA del Excel-respuesta traía
`<table border="1" style=...>` literal. El helper debe convertir la
tabla de cabecera a líneas legibles, quitar el resto de tags y ser
idempotente (texto ya plano pasa sin romperse).
"""

from app.utils.html_a_texto import (
    dictamen_a_texto_plano,
    extraer_tabla_cabecera,
    tabla_a_filas,
)

# Réplica fiel de la tabla de cabecera que genera _generar_dictamen_html
DICTAMEN_HTML = """
<table border="1" style="width:100%;border-collapse:collapse;font-size:11px;margin-bottom:15px;background:white;">
    <tr style="background-color:#1e40af;color:white;">
        <th style="padding:10px;text-align:center;">CÓDIGO GLOSA</th>
        <th style="padding:10px;text-align:center;">VALOR OBJETADO</th>
        <th style="padding:10px;text-align:center;">CÓDIGO RESPUESTA</th>
    </tr>
    <tr>
        <td style="padding:10px;text-align:center;font-weight:bold;">TA0801</td>
        <td style="padding:10px;text-align:center;font-weight:bold;color:#1e40af;">$36.402</td>
        <td style="padding:10px;text-align:center;"><b>RE9901</b><br><span style="font-size:10px">Glosa no aceptada</span></td>
    </tr>
    <tr>
        <td colspan="3" style="padding:6px 10px;font-size:10px;color:#64748b;">
            N&deg; Factura: <b>HUS123456</b>
        </td>
    </tr>
</table>

<div style="background:#f8fafc;border-radius:12px;padding:20px;">
    <h4 style="color:#0f172a;">ARGUMENTACIÓN JURÍDICA</h4>
    <div style="font-size:12px;">Primer p&aacute;rrafo del argumento.<br/>Segunda l&iacute;nea.</div>
</div>

<div style="margin-top:15px;">
    <b>Nota:</b> Generado con asistencia de IA. Verificar antes de radicar ante la EPS.
</div>
"""


class TestDictamenATextoPlano:
    def test_tabla_cabecera_a_linea_legible(self):
        txt = dictamen_a_texto_plano(DICTAMEN_HTML)
        assert "CÓDIGO GLOSA: TA0801" in txt
        assert "VALOR OBJETADO: $36.402" in txt
        assert "CÓDIGO RESPUESTA: RE9901 Glosa no aceptada" in txt
        # Las tres van en la MISMA línea separadas por pipes
        linea = next(line for line in txt.splitlines() if "CÓDIGO GLOSA" in line)
        assert linea.count("|") == 2

    def test_sin_tags_html_en_salida(self):
        txt = dictamen_a_texto_plano(DICTAMEN_HTML)
        assert "<table" not in txt
        assert "<div" not in txt
        assert "<b>" not in txt
        assert "style=" not in txt

    def test_fila_trazabilidad_colspan(self):
        txt = dictamen_a_texto_plano(DICTAMEN_HTML)
        assert "N° Factura: HUS123456" in txt

    def test_entities_decodificadas_y_parrafos(self):
        txt = dictamen_a_texto_plano(DICTAMEN_HTML)
        assert "Primer párrafo del argumento." in txt
        assert "Segunda línea." in txt
        # <br/> dentro del argumento → salto de línea real
        assert "Primer párrafo del argumento.\nSegunda línea." in txt

    def test_idempotente_texto_plano(self):
        plano = "CÓDIGO GLOSA: TA0801 | VALOR OBJETADO: $36.402\n\nArgumento simple."
        assert dictamen_a_texto_plano(plano) == plano

    def test_idempotente_doble_pasada(self):
        una = dictamen_a_texto_plano(DICTAMEN_HTML)
        dos = dictamen_a_texto_plano(una)
        assert dos == una

    def test_vacio_y_none(self):
        assert dictamen_a_texto_plano("") == ""
        assert dictamen_a_texto_plano(None) == ""

    def test_listas_a_vinetas(self):
        html = "<ul><li>Historia clínica</li><li>RIPS radicados</li></ul>"
        txt = dictamen_a_texto_plano(html)
        assert "• Historia clínica" in txt
        assert "• RIPS radicados" in txt

    def test_menor_que_sin_cierre_no_destruye_texto(self):
        # "<" suelto (sin ">") no debe tragarse el resto del texto
        plano = "El valor facturado es < 100.000 COP"
        assert dictamen_a_texto_plano(plano) == plano

    def test_sin_saltos_excesivos(self):
        txt = dictamen_a_texto_plano(DICTAMEN_HTML)
        assert "\n\n\n" not in txt


class TestTablaAFilas:
    def test_extrae_matriz(self):
        filas = tabla_a_filas(
            "<table><tr><th>A</th><th>B</th></tr><tr><td>1</td><td>2</td></tr></table>"
        )
        assert filas == [["A", "B"], ["1", "2"]]

    def test_ignora_filas_vacias(self):
        filas = tabla_a_filas("<table><tr><td> </td></tr><tr><td>x</td></tr></table>")
        assert filas == [["x"]]


class TestExtraerTablaCabecera:
    def test_separa_cabecera_del_resto(self):
        filas, resto = extraer_tabla_cabecera(DICTAMEN_HTML)
        assert filas is not None
        assert filas[0] == ["CÓDIGO GLOSA", "VALOR OBJETADO", "CÓDIGO RESPUESTA"]
        assert filas[1][0] == "TA0801"
        assert "<table" not in resto
        assert "ARGUMENTACIÓN JURÍDICA" in resto

    def test_sin_tabla_devuelve_html_intacto(self):
        filas, resto = extraer_tabla_cabecera("<div>solo texto</div>")
        assert filas is None
        assert resto == "<div>solo texto</div>"

    def test_tabla_que_no_es_cabecera_no_se_extrae(self):
        html = "<table><tr><td>otra cosa</td></tr></table><p>argumento</p>"
        filas, resto = extraer_tabla_cabecera(html)
        assert filas is None
        assert resto == html
