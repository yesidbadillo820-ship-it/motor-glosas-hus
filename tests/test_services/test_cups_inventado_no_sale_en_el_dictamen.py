"""El dictamen no puede citar un CUPS que nadie le mostro.

Caso real 25-08-2026. El auditor subio el archivo de recepcion del dia y el
motor contesto 117 glosas. El revisor de citas marco 19 dictamenes con un
CUPS que no existe. La prueba de que son inventados no es que falten del
catalogo — es que el MISMO codigo nombra servicios distintos:

    734101 -> "RADIOGRAFIA DE MAXILAR INFERIOR"  (dictamen A)
    734101 -> "RADIOGRAFIA DE PIERNA"            (dictamen B)
    730102 -> "URGENCIAS ADULTOS"                (dictamen C)
    730102 -> "INTERNACION ADULTOS COMPLEJIDAD ALTA" (dictamen D)

Un codigo no puede nombrar dos procedimientos. Y el archivo de recepcion no
trae columna de CUPS: la IA relleno el hueco con un numero de seis cifras.

Un CUPS inventado es de lo primero que la EPS cruza contra su sistema. No
lo encuentra y ratifica la glosa completa, por buena que este la defensa.
"""

from app.services.glosa_service import (
    _cups_en_evidencia,
    _cups_esta_en_catalogo,
    _neutralizar_cups_sin_respaldo,
)


# ── Lo que de verdad salio el 25-08-2026 ────────────────────────────────
class TestElLoteDel25DeAgosto:
    def test_el_maxilar_inferior_pierde_el_codigo_inventado(self):
        texto = "RESPECTO DE RADIOGRAFIA DE MAXILAR INFERIOR CUPS 734101, FACTURADO."
        salida = _neutralizar_cups_sin_respaldo(texto, "GLOSA TA0201 SIN CODIGO")
        assert "734101" not in salida
        assert "RADIOGRAFIA DE MAXILAR INFERIOR" in salida, (
            "se retira el numero inventado, no la descripcion del servicio"
        )

    def test_la_pierna_pierde_el_mismo_codigo(self):
        texto = "RESPECTO DE RADIOGRAFIA DE PIERNA - CUPS 734101, FACTURADO."
        salida = _neutralizar_cups_sin_respaldo(texto, "GLOSA CL0801")
        assert "734101" not in salida
        assert "RADIOGRAFIA DE PIERNA" in salida

    def test_urgencias_adultos_pierde_el_codigo(self):
        texto = "SERVICIO OBJETADO: URGENCIAS ADULTOS - CUPS 730102."
        salida = _neutralizar_cups_sin_respaldo(texto, "SIN SOPORTES")
        assert "730102" not in salida
        assert "URGENCIAS ADULTOS" in salida

    def test_la_referencia_del_insumo_no_se_disfraza_de_cups(self):
        texto = "ESENTA REMOVEDOR SPRAY X 50 ML REF 423289 - CUPS 423289."
        salida = _neutralizar_cups_sin_respaldo(texto, "GLOSA IN0101 SIN DETALLE")
        assert "CUPS 423289" not in salida

    def test_el_sintagma_servicio_prestado_con_cups_queda_legible(self):
        texto = "RESPECTO DEL SERVICIO PRESTADO CON CUPS 733101, FACTURADO POR $ 122.700."
        salida = _neutralizar_cups_sin_respaldo(texto, "FA1606 AU0202 TA0801")
        assert "733101" not in salida
        assert "SERVICIO PRESTADO" in salida
        assert "  " not in salida, "no puede quedar doble espacio donde estaba el codigo"


# ── Lo que NUNCA se puede borrar ────────────────────────────────────────
class TestNoBorraLoQueSiTieneRespaldo:
    def test_un_cups_que_esta_en_la_glosa_se_respeta(self):
        texto = "EL PROCEDIMIENTO FACTURADO CON CUPS 999888 CORRESPONDE AL SERVICIO."
        evidencia = "LA EPS OBJETA EL CODIGO 999888 POR TARIFA"
        salida = _neutralizar_cups_sin_respaldo(texto, evidencia)
        assert "999888" in salida, "estaba en el expediente: la IA lo leyo, no lo invento"

    def test_un_cups_real_del_catalogo_se_respeta_aunque_no_este_en_la_glosa(self):
        assert _cups_esta_en_catalogo("012403"), "codigo de control: existe en el catalogo"
        texto = "EL PROCEDIMIENTO FACTURADO CON CUPS 012403 SE PRESTO EL 12 DE MAYO."
        salida = _neutralizar_cups_sin_respaldo(texto, "GLOSA SIN CODIGOS")
        assert "012403" in salida, (
            "un codigo verificable NUNCA se borra — leccion de la Res. 2641 de 2024"
        )

    def test_el_codigo_con_ceros_a_la_izquierda_se_reconoce(self):
        assert _cups_en_evidencia("012403", "SE FACTURO EL 12403 SEGUN LA TABLA")
        assert _cups_en_evidencia("12403", "SE FACTURO EL 012403 SEGUN LA TABLA")

    def test_el_codigo_institucional_con_sufijo_se_reconoce(self):
        assert _cups_en_evidencia("898015H", "CITOLOGIA 898015 EN LA FACTURA")

    def test_no_confunde_un_codigo_con_otro_mas_largo(self):
        assert not _cups_en_evidencia("734101", "EL NUMERO 7341010 NO ES EL MISMO")
        assert not _cups_en_evidencia("734101", "LA FACTURA 1734101 TAMPOCO")

    def test_texto_sin_cups_sale_identico(self):
        texto = "ESE HUS NO ACEPTA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO."
        assert _neutralizar_cups_sin_respaldo(texto, "") == texto

    def test_texto_vacio_no_rompe(self):
        assert _neutralizar_cups_sin_respaldo("", "algo") == ""
        assert _neutralizar_cups_sin_respaldo(None, "algo") is None


# ── Que el texto siga siendo presentable ────────────────────────────────
class TestElTextoQuedaLimpio:
    def test_no_quedan_parentesis_vacios(self):
        texto = "RADIOGRAFIA DE ANTEBRAZO (CUPS 734101) Y EXTRACCION DE DISPOSITIVO."
        salida = _neutralizar_cups_sin_respaldo(texto, "SIN DATOS")
        assert "()" not in salida
        assert "( )" not in salida
        assert "734101" not in salida

    def test_no_queda_una_coma_pegada_al_espacio(self):
        texto = "EL SERVICIO CON CUPS 730101 , FACTURADO."
        salida = _neutralizar_cups_sin_respaldo(texto, "SIN DATOS")
        assert " ," not in salida

    def test_no_se_come_la_e_de_nueva_eps(self):
        """Bug propio, atrapado el 25-08-2026 al correr la red sobre el lote real.

        La limpieza de conectores borraba toda letra suelta pegada a un punto
        y dejaba "NUEVA .P.S. S.A." en 21 dictamenes. El nombre de la entidad
        pagadora mal escrito es motivo de devolucion por si solo.
        """
        texto = (
            "GLOSA INTERPUESTA POR NUEVA E.P.S. S.A. - SUBSIDIADO, RESPECTO "
            "DEL SERVICIO PRESTADO CON CUPS 733101, POR $ 122.700."
        )
        salida = _neutralizar_cups_sin_respaldo(texto, "SIN DATOS")
        assert "733101" not in salida
        assert "NUEVA E.P.S. S.A." in salida

    def test_no_toca_las_siglas_con_punto(self):
        texto = "LA E.S.E. HUS Y LA E.P.S. DISCUTEN EL SERVICIO CON CUPS 730101."
        salida = _neutralizar_cups_sin_respaldo(texto, "SIN DATOS")
        assert "E.S.E." in salida and "E.P.S." in salida

    def test_no_queda_un_conector_huerfano_antes_del_punto(self):
        texto = "SE OBJETA EL SERVICIO CON CUPS 731101. SE SOLICITA EL LEVANTAMIENTO."
        salida = _neutralizar_cups_sin_respaldo(texto, "SIN DATOS")
        assert "731101" not in salida
        assert " CON." not in salida.upper()
        assert " DE." not in salida.upper()
