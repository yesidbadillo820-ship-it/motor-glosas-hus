"""Importación masiva probada con un pegado real de Excel (20-08-2026).

Se probó el botón como lo usa el auditor: seleccionar el rango en Excel
—arrastrando desde la primera fila, que es lo normal— y pegarlo. Salieron dos
defectos, los dos en TODAS las importaciones:

  1. la fila de TÍTULOS entraba como una glosa más;
  2. el valor glosado se leía como si fuera el código CUPS del procedimiento,
     y le ganaba incluso al CUPS de verdad que venía en su propia columna.
"""

from __future__ import annotations

from app.api.routers.glosas import _es_fila_de_encabezado, _parsear_filas_excel
from app.utils.parsers_glosa import _detectar_servicio_desde_texto

# Un pegado tal cual sale de Excel: tabs, encabezado y pesos con punto de miles.
PEGADO_REAL = (
    "ENTIDAD\tFACTURA\tVALOR\tCODIGO\tCONCEPTO GLOSA\tCUPS\tSERVICIO\tMOTIVO\n"
    "COOSALUD\tHUS0000468334\t168.563\tSO0201\tFALTA SOPORTE\t890201\t"
    "CONSULTA URGENCIAS\tno anexan hoja de atencion\n"
    "FAMISANAR EPS\tHUS0000468335\t1.250.000\tTA0601\tMAYOR VALOR\t886301\t"
    "CURACION LESION PIEL\tse glosa mayor valor cobrado\n"
)


def _texto_glosa(fila: dict) -> str:
    """Reproduce el texto que el importador le arma a la IA por cada fila."""
    return (
        f"{fila['codigo']} VALOR GLOSADO {fila['valor']} "
        f"{fila['descripcion']} {fila['cups']} {fila['motivo']}"
    )


class TestLaFilaDeTitulosNoEsUnaGlosa:
    """Entraba con eps «ENTIDAD», factura «FACTURA», valor «VALOR» y código
    «CODIGO». Se le gastaba una llamada a la IA, quedaba guardada y le salía
    al auditor en la lista y en los totales del lote. El filtro que había
    —«el código mide 2 o más caracteres»— la dejaba pasar: «CODIGO» mide seis.
    """

    def test_el_pegado_real_deja_solo_las_dos_glosas(self):
        filas = _parsear_filas_excel(PEGADO_REAL)
        assert len(filas) == 2

    def test_y_no_queda_ninguna_entidad_fantasma(self):
        filas = _parsear_filas_excel(PEGADO_REAL)
        assert [f["eps"] for f in filas] == ["COOSALUD", "FAMISANAR EPS"]
        assert all(f["codigo"] != "CODIGO" for f in filas)

    def test_con_tildes_y_en_español(self):
        texto = (
            "Entidad\tFactura\tValor\tCódigo\tConcepto Glosa\tCUPS\tServicio\tMotivo\n"
            "COOSALUD\tHUS468334\t168.563\tSO0201\tX\t890201\tY\tZ"
        )
        assert len(_parsear_filas_excel(texto)) == 1

    def test_con_separador_de_barras(self):
        texto = (
            "EPS | FACTURA | VALOR GLOSADO | CODIGO GLOSA | DESCRIPCION\n"
            "SURA | HUS1 | 5.000 | CO4601 | omeprazol no cubierto"
        )
        assert len(_parsear_filas_excel(texto)) == 1


class TestPeroNoSeComeUnaGlosaDeVerdad:
    """La mitad que importa: descartar de más es peor que no descartar."""

    def test_una_glosa_cuyo_motivo_habla_de_valor_y_factura(self):
        texto = (
            "COOSALUD\tHUS468334\t168.563\tSO0201\tFALTA SOPORTE\t890201\t"
            "CONSULTA\tel valor de la factura no coincide con el servicio"
        )
        assert len(_parsear_filas_excel(texto)) == 1

    def test_una_glosa_con_pocas_celdas_llenas(self):
        assert len(_parsear_filas_excel("SURA\tHUS9\t100\tCO4601\tNO PBS\t\t\tmotivo")) == 1

    def test_dos_glosas_seguidas_sin_encabezado(self):
        texto = "COOSALUD\tHUS1\t100\tSO0201\tA\t890201\tB\tC\nSURA\tHUS2\t200\tCO4601\tD\t\tE\tF"
        assert len(_parsear_filas_excel(texto)) == 2

    def test_hace_falta_que_MANDEN_las_etiquetas(self):
        """Una etiqueta suelta no convierte una glosa en encabezado."""
        assert not _es_fila_de_encabezado(["COOSALUD", "HUS1", "100", "SO0201", "valor"])
        assert _es_fila_de_encabezado(["ENTIDAD", "FACTURA", "VALOR", "CODIGO"])

    def test_una_fila_casi_vacia_no_se_toma_por_encabezado(self):
        assert not _es_fila_de_encabezado(["VALOR", ""])


class TestElValorGlosadoNoEsUnCups:
    """El defecto que llegaba al documento que se radica.

    El texto que el importador le arma a la IA ponía el valor suelto entre el
    código y la descripción («SO0201 125000 FALTA SOPORTE 890201 …»), y el
    lector de CUPS tomaba los pesos como el código del procedimiento. Le
    ganaba al CUPS de verdad porque el valor aparece primero. En una
    importación de 90 glosas, 90 dictámenes citando un CUPS inexistente — y la
    EPS cruza los CUPS contra su sistema.
    """

    def test_gana_el_cups_de_verdad_y_no_el_valor(self):
        fila = _parsear_filas_excel(PEGADO_REAL)[0]
        detectado = _detectar_servicio_desde_texto(_texto_glosa(fila), "") or ""
        assert "890201" in detectado
        assert "168" not in detectado

    def test_sin_columna_cups_no_se_inventa_ninguno(self):
        texto = "SO0201 VALOR GLOSADO 125000 FALTA SOPORTE  no anexan hoja"
        assert _detectar_servicio_desde_texto(texto, "") is None

    def test_un_valor_de_cinco_digitos_tampoco(self):
        texto = "TA0601 VALOR GLOSADO 96800 MAYOR VALOR  se glosa mayor valor"
        assert _detectar_servicio_desde_texto(texto, "") is None

    def test_el_importador_sigue_etiquetando_el_valor(self):
        """Si alguien quita la etiqueta, el valor vuelve a leerse como CUPS."""
        import inspect

        from app.api.routers import glosas as mod

        fuente = inspect.getsource(mod._procesar_fila_en_background)
        assert "VALOR GLOSADO" in fuente, (
            "El importador dejó de etiquetar el valor en el texto de la glosa. "
            "Sin la etiqueta, los pesos glosados vuelven a leerse como el CUPS "
            "del procedimiento y le ganan al CUPS de verdad."
        )

    def test_la_segunda_fila_del_pegado_real_tambien(self):
        fila = _parsear_filas_excel(PEGADO_REAL)[1]
        detectado = _detectar_servicio_desde_texto(_texto_glosa(fila), "") or ""
        assert "886301" in detectado
        assert "250" not in detectado
