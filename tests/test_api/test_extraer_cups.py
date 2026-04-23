"""Tests del extractor de CUPS desde el texto de la glosa.

Casos reales que antes fallaban (reportados por el usuario):
  - CUPS con sufijo H: 372301H, 039001H1
  - CUPS con sufijo alfa-dígito-dígito: 39147B-18
  - Medicamentos CUM: 19914262-04
  - Códigos propios HUS (letras+dígitos): FMQ6296, QX0106
  - NO confundir el código de glosa (TA0801, SO0101) con el CUPS
"""
from app.main import _extraer_cups_servicio


class TestExtraerCups:
    def test_cups_con_sufijo_h(self):
        """CUPS institucional HUS con sufijo H (Res. 124/2026)."""
        cups, _ = _extraer_cups_servicio(
            "CUPS 372301H - ESTUDIO ELECTROFISIOLOGICO CARDIACO"
        )
        assert cups == "372301H"

    def test_cups_con_sufijo_h_numero(self):
        """CUPS tipo 039001H1, 908859H2."""
        cups, _ = _extraer_cups_servicio("CUPS 908859H2 - PANEL BCID2")
        assert cups == "908859H2"

    def test_cups_con_sufijo_letra_guion_digitos(self):
        """CUPS tipo 39147B-18 (consulta genética médica Dispensario)."""
        cups, _ = _extraer_cups_servicio(
            "CUPS 39147B-18 - CONSULTA GENETICA MEDICA"
        )
        assert cups == "39147B-18"

    def test_medicamento_cum(self):
        """Medicamento con CUM tipo 19914262-04."""
        cups, _ = _extraer_cups_servicio("CUPS 19914262-04 - INSULINA GLARGINA")
        assert cups == "19914262-04"

    def test_cups_propio_hus_alfanumerico(self):
        """Códigos propios HUS tipo FMQ6296, QX0106."""
        cups, _ = _extraer_cups_servicio("CUPS FMQ6296 - STEN CORONARIO")
        assert cups == "FMQ6296"

    def test_cups_simple_6_digitos(self):
        cups, _ = _extraer_cups_servicio("CUPS 890750 - CONSULTA URGENCIAS")
        assert cups == "890750"

    def test_no_confunde_codigo_glosa_con_cups(self):
        """BUG REAL: cuando el texto empieza con 'TA0801 - CUPS 873306',
        no debe tomar TA0801 como CUPS."""
        cups, _ = _extraer_cups_servicio(
            "TA0801 - CUPS 873306 - RADIOGRAFIA - $83.800"
        )
        assert cups == "873306"
        assert cups != "TA0801"

    def test_texto_minusculas(self):
        """Caso real con mojibake y minúsculas."""
        cups, _ = _extraer_cups_servicio(
            "ta0801 - cups 873306 - valor facturado $83.800"
        )
        assert cups == "873306"

    def test_so_glosa_con_cups_real(self):
        cups, _ = _extraer_cups_servicio(
            "SO0101 - No se aporta historia clínica - CUPS 890201"
        )
        assert cups == "890201"

    def test_sin_cups_retorna_vacio(self):
        cups, _ = _extraer_cups_servicio("TA0801 - Glosa genérica sin CUPS")
        # Debe devolver vacío (no tomar TA0801 como CUPS)
        assert cups == ""

    def test_texto_vacio(self):
        cups, _ = _extraer_cups_servicio("")
        assert cups == ""
