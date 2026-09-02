"""Sin evidencia, el dictamen dice que no hay evidencia.

PRUEBA 5 DE ESTRÉS (01-09-2026) — glosa FA0205, factura HUS0000603118,
Dirección de Sanidad del Ejército. Texto completo de la objeción:

    DIFERENCIA EN CANTIDADES FACTURADAS FRENTE A LO REGISTRADO. SE GLOSA.

Sin servicio, sin CUPS, sin cantidades, sin fechas, sin un solo soporte. El
motor produjo una defensa de manual: inventó una consulta médica, una historia
clínica que «muestra que la consulta se realizó una sola vez», unos «informes
de validación de cargos», dos cláusulas y una ley del subsistema militar. Todo
bien redactado. Todo falso. Y pidió el levantamiento.

Un modelo entrenado en plantillas no sabe abstenerse: ante el vacío rellena.
Por eso la abstención se decide ANTES de llamar a la IA, en código, y la
llamada no se hace.
"""

import io

import pytest

from app.services.glosa_service import ARGUMENTO_ABSTENCION, _glosa_sin_elementos

FA0205 = (
    "FA0205 | HUS0000603118 | DIRECCION DE SANIDAD EJERCITO NACIONAL\n"
    "DIFERENCIA EN CANTIDADES FACTURADAS FRENTE A LO REGISTRADO. SE GLOSA.\n"
    "VALOR FACTURADO: $960.000  VALOR GLOSADO: $960.000"
)


class TestElCasoQueLoDestapo:
    def test_fa0205_sin_nada_se_abstiene(self):
        assert _glosa_sin_elementos(FA0205, "", "")

    def test_el_encabezado_y_la_linea_de_valores_no_cuentan_como_elementos(self):
        """Los trae cualquier glosa, hasta la más vacía."""
        solo_marco = "FA0205 | HUS1 | X\nVALOR FACTURADO: $1  VALOR GLOSADO: $1"
        assert _glosa_sin_elementos(solo_marco, "", "")

    def test_texto_vacio_se_abstiene(self):
        assert _glosa_sin_elementos("", "", "")


class TestLasDosCondicionesALaVez:
    """Se abstiene solo cuando faltan LAS DOS cosas: soportes y elementos."""

    def test_con_un_pdf_adjunto_no_se_abstiene(self):
        assert not _glosa_sin_elementos(FA0205, "═══ DOCUMENTO: factura.pdf ═══\nx", "")

    def test_con_cups_verificado_no_se_abstiene(self):
        assert not _glosa_sin_elementos(FA0205, "", "890201")

    @pytest.mark.parametrize(
        "elemento",
        [
            "SE FACTURARON 3 CONSULTAS Y SE REGISTRARON 2.",
            "DIFERENCIA EN EL CUPS 890201.",
            "DIFERENCIA EN EL 890201.",
            "EL MEDICAMENTO SE FACTURO POR 18 DOSIS.",
            "LA CONSULTA DE URGENCIAS NO CORRESPONDE.",
            "ATENCION DEL 04/04/2026 NO REGISTRADA.",
        ],
    )
    def test_con_un_elemento_material_hay_con_que_discutir(self, elemento: str):
        glosa = f"FA0205 | HUS1 | X\n{elemento}\nVALOR FACTURADO: $1  VALOR GLOSADO: $1"
        assert not _glosa_sin_elementos(glosa, "", "")


class TestLosOtrosCuatroCasosNoSeAbstienen:
    """Las pruebas 1 a 4 sí tienen con qué: servicio, CUPS, dosis o fecha."""

    @pytest.mark.parametrize(
        "carpeta",
        [
            "01_TA0301_CUPS_QUE_NO_LO_ES",
            "02_CL4506_PERTINENCIA_VS_TARIFA",
            "03_AU0201_CLAUSULA_QUE_NO_EXISTE",
            "04_SO0102_SOPORTE_QUE_DICE_LO_CONTRARIO",
        ],
    )
    def test_no_se_abstiene(self, carpeta: str):
        txt = io.open(f"PRUEBAS_STRESS_IA/{carpeta}/glosa.txt", encoding="utf-8").read()
        assert not _glosa_sin_elementos(txt, "", ""), carpeta

    def test_y_el_quinto_si(self):
        txt = io.open("PRUEBAS_STRESS_IA/05_FA0205_SIN_NADA/glosa.txt", encoding="utf-8").read()
        assert _glosa_sin_elementos(txt, "", "")


class TestElTextoFijo:
    def test_dice_que_no_hay_evidencia(self):
        assert "NO EXISTE EVIDENCIA SUFICIENTE" in ARGUMENTO_ABSTENCION

    def test_le_pide_al_pagador_que_precise(self):
        assert "PRECISAR LOS ELEMENTOS MATERIALES" in ARGUMENTO_ABSTENCION

    def test_nunca_pide_el_levantamiento(self):
        """Pedir el levantamiento es una defensa de fondo. Aquí no hay fondo."""
        assert "LEVANTAMIENTO" not in ARGUMENTO_ABSTENCION.upper()

    def test_no_afirma_nada_del_expediente(self):
        for prohibido in ("HISTORIA CL", "CUPS", "CLÁUSULA", "FOLIO", "CONSULTA SE REALIZ"):
            assert prohibido not in ARGUMENTO_ABSTENCION.upper(), prohibido

    def test_no_calcula_extemporaneidad(self):
        """Sin fechas no puede decir ni a tiempo ni tarde."""
        for prohibido in ("EXTEMPORÁNEA", "DENTRO DEL TÉRMINO DE 15", "FUERA DEL TÉRMINO"):
            assert prohibido not in ARGUMENTO_ABSTENCION.upper(), prohibido
        assert "CÁLCULO DE EXTEMPORANEIDAD" in ARGUMENTO_ABSTENCION


class TestElMotorNoLlamaALaIA:
    MOTOR = io.open("app/services/glosa_service.py", encoding="utf-8").read()

    def test_la_rama_existe_antes_de_la_plantilla_y_del_llm(self):
        i_abs = self.MOTOR.index("elif _abstenerse:")
        i_pla = self.MOTOR.index("elif usa_plantilla:")
        assert i_abs < i_pla, "la abstención tiene que decidirse antes de la plantilla y del LLM"

    def test_el_modelo_usado_lo_dice(self):
        assert 'modelo_usado = "abstencion"' in self.MOTOR

    def test_el_codigo_es_oficial_y_el_rotulo_es_honesto(self):
        """No existe en el Manual Único un código de «pídame precisión»."""
        assert "OBJECIÓN IMPRECISA" in self.MOTOR
        assert '"RE9901",\n                "GLOSA NO ACEPTADA - OBJECIÓN IMPRECISA' in self.MOTOR


class TestLoQueAtrapoLaSuite:
    """La primera versión se abstenía de glosas llenas de elementos.

    Tres pruebas de extremo a extremo cayeron al meter la abstención. Causa:
    el predicado descartaba la LÍNEA ENTERA si decía «VALOR FACTURADO», y una
    glosa escrita en un solo renglón —«…SANCIÓN DEL 10 % AL VALOR FACTURADO
    conforme a la Cláusula 18 del contrato…»— se borraba completa y quedaba
    «vacía». Además ignoraba el formulario: con fechas la extemporaneidad SÍ se
    calcula, y una tabla de Excel del expediente también es evidencia.
    """

    GLOSA_UN_RENGLON = (
        "SALUD TOTAL: Se objeta integralmente la atención: (1) la terapia TMS "
        "NO está en el PBS; (2) la hospitalización de 22 días excede lo "
        "pertinente; (3) no hubo autorización previa. SE APLICA SANCIÓN DEL 10% "
        "AL VALOR FACTURADO conforme a la Cláusula 18 del contrato "
        "CTR-2024-SALUDTOTAL-HUS."
    )

    def test_una_glosa_de_un_solo_renglon_con_elementos_no_se_abstiene(self):
        assert not _glosa_sin_elementos(self.GLOSA_UN_RENGLON, "", "")

    def test_se_quita_la_cifra_no_la_linea(self):
        """Lo único que no cuenta es el número de plata; el resto sí."""
        glosa = (
            "SE GLOSA POR MAYOR VALOR COBRADO. VALOR FACTURADO: $500.000 VALOR GLOSADO: $500.000"
        )
        assert not _glosa_sin_elementos(glosa, "", "")

    def test_una_causal_reconocible_es_un_elemento(self):
        """«Mayor valor cobrado» no nombra servicio, pero sí dice qué objeta."""
        assert not _glosa_sin_elementos("TA0201 | HUS1 | X\nMAYOR VALOR COBRADO.", "", "")

    def test_fa0205_sigue_abstenido_despues_del_arreglo(self):
        assert _glosa_sin_elementos(FA0205, "", "")


class TestElFormularioTambienEsEvidencia:
    MOTOR = io.open("app/services/glosa_service.py", encoding="utf-8").read()

    def test_con_fechas_no_se_abstiene(self):
        """Con fechas, «sin fechas que permitan calcular extemporaneidad» sería falso."""
        i = self.MOTOR.index("_hay_algo_mas = bool(")
        bloque = self.MOTOR[i : i + 500]
        for campo in (
            "fecha_radicacion",
            "fecha_recepcion",
            "tabla_excel",
            "es_ratificacion",
            "es_extemporanea",
            "modo_resp",
        ):
            assert campo in bloque, campo

    def test_la_abstencion_exige_las_dos_cosas(self):
        assert "(not _hay_algo_mas) and _glosa_sin_elementos(" in self.MOTOR
