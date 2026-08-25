"""El mismo contrato leído de dos maneras distintas.

QUÉ PASÓ. La primera auditoría independiente encontró que, dentro del MISMO
lote de dictámenes, el contrato 0525 de 2017 de POSITIVA y el CUPS 010101 se
leyeron de dos maneras que no pueden ser las dos ciertas:

  · GL-188 dijo «tarifa pactada $915.051», modalidad SOAT (pleno).
  · GL-190 y GL-192 dijeron, del mismo contrato y el mismo CUPS, «SOAT −15 %».

El 85 % de $915.051 es $777.793. O el valor guardado ya trae el descuento, o
no lo trae: no puede ser las dos cosas. El auditor lo dijo así: «el control de
calidad no lo detecta porque audita cada caso por separado; una contradicción
entre expedientes solo se ve mirándolos juntos».

LA CAUSA. El número y las palabras salían de columnas distintas del Excel y
nadie las cruzaba. La columna del valor por un lado, la de la modalidad por
otro, y el catálogo estático de la EPS por un tercero.

QUÉ SE HIZO, en dos frentes.

EN EL ORIGEN: cuando el valor se toma de una columna cuyo encabezado YA dice el
descuento («SOAT -15%»), ese encabezado pasa a ser la modalidad. Número y
palabras salen de la misma celda y dejan de poder contradecirse. Esto arregla
las cargas nuevas.

EN LO YA CARGADO: si la modalidad de una fila anuncia un descuento y la fila lo
declara en cero, no se puede saber si el valor ya lo trae aplicado. Ahí NO se
corrige el número —recalcularlo sería inventar una tarifa, y eso está
prohibido— pero tampoco se afirma la modalidad como si constara: se avisa, y la
plantilla que va derecho al documento radicado cambia «BAJO LA MODALIDAD X» por
una frase que no afirma nada que no conste.

El aviso es estrecho a propósito: solo mira la contradicción DENTRO de la fila.
Una regla más ancha marcaría casi toda glosa de tarifa, y un aviso que sale
siempre es un aviso que el auditor aprende a ignorar.
"""

from app.services.glosa_service import generar_texto_tarifa_match


def _info(modalidad: str, verificada) -> dict:
    return {
        "tarifa": {
            "eps": "POSITIVA",
            "codigo_cups": "010101",
            "descripcion": "Puncion cisternal",
            "contrato_numero": "OT3-0525-2017",
            "modalidad": modalidad,
            "fuente_archivo": "TARIFAS ESE HUS 2025- POSITIVA.xlsx",
        },
        "valor_pactado_calc": 915051.0,
        "valor_facturado": 915051.0,
        "tarifa_verificada": verificada,
    }


class TestElDictamenNoAfirmaLoQueNoConsta:
    def test_con_la_fila_contradictoria_no_dice_la_modalidad(self):
        texto = generar_texto_tarifa_match("TA5401", 77793.0, _info("SOAT -15%", False))
        assert "BAJO LA MODALIDAD" not in texto
        assert "SEGÚN EL VALOR REGISTRADO EN EL CATÁLOGO" in texto

    def test_el_valor_se_sigue_usando(self):
        """No se corrige el número: recalcularlo sería inventar una tarifa."""
        texto = generar_texto_tarifa_match("TA5401", 77793.0, _info("SOAT -15%", False))
        assert "915.051" in texto

    def test_cuando_la_fila_concuerda_si_dice_la_modalidad(self):
        texto = generar_texto_tarifa_match("TA5401", 77793.0, _info("SOAT -15%", True))
        assert "BAJO LA MODALIDAD SOAT -15%" in texto

    def test_sin_la_marca_se_comporta_como_siempre(self):
        """Compatibilidad: las llamadas viejas no cambian de comportamiento."""
        info = _info("SOAT PLENO", None)
        del info["tarifa_verificada"]
        assert "BAJO LA MODALIDAD SOAT PLENO" in generar_texto_tarifa_match("TA5401", 1.0, info)


class TestLaModalidadSaleDeLaMismaCeldaQueElNumero:
    """Se prueba por la puerta de verdad: un Excel como los que llegan."""

    def _parsear(self, encabezado_valor: str, modalidad_suelta: str):
        import io as _io

        import openpyxl

        from app.services.tarifas_excel_parser import parsear_excel_tarifas

        wb = openpyxl.Workbook()
        wb.remove(wb.active)
        ws = wb.create_sheet("SOAT")
        ws.append(["CUPS", "DESCRIPCIÓN CUPS", " VALOR 2025 ", encabezado_valor, "MODALIDAD"])
        ws.append([10101, "PUNCION CISTERNAL, VIA LATERAL", 915051, 777793, modalidad_suelta])
        buf = _io.BytesIO()
        wb.save(buf)
        return parsear_excel_tarifas(buf.getvalue())

    def test_el_encabezado_del_descuento_le_gana_a_la_columna_suelta(self):
        """Si la columna del valor dice «SOAT -15%», esa es la modalidad.

        Y de paso se comprueba lo que ya cuidaba otra prueba: que el valor
        cargado sea el del descuento ($777.793) y no el pleno ($915.051).
        """
        r = self._parsear("SOAT -15%", "SOAT")
        filas = r["filas"]
        assert filas, f"no se leyó ninguna fila: {r}"
        assert filas[0]["valor_pactado"] == 777793.0
        assert "15" in filas[0]["modalidad"], filas[0]["modalidad"]

    def test_sin_columna_de_descuento_se_respeta_la_modalidad_suelta(self):
        r = self._parsear("VALOR NEGOCIADO", "SOAT PLENO")
        filas = r["filas"]
        assert filas
        assert "PLENO" in filas[0]["modalidad"].upper()
