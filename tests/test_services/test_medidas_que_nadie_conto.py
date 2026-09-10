"""El dictamen no puede inventar mililitros, unidades ni números de ítem.

Caso que lo pidió — objeción N° 189801, factura HUS0000541440, causal FA0701
sobre el IOBITRIDOL. La entidad objetó que según la nota operatoria se usaron
40 CC y que la hoja de gastos registra frasco de 100 ML / 50 ML, y que por
eso no reconoce el cobro de 4 unidades. El dictamen salió a defender el cobro
diciendo:

    «EL ÍTEM 13 DE LA FACTURA INDICA LA ADQUISICIÓN DE CINCO UNIDADES DE
     100 ML CADA UNA, TOTALIZANDO 500 ML»

El ítem 13, las cinco unidades y los 500 ML no estaban en ninguna parte de lo
que se le entregó al modelo — el medicamento es de 50 ML, lo dice la propia
descripción del renglón. La entidad abre la factura, ve que el ítem 13 no dice
eso, y el hospital pierde la glosa y la credibilidad de las otras siete.
"""

from app.services.quality_gate.post_validator import (
    check_medidas_no_fabricadas,
    post_validar_dictamen,
)

GLOSA_REAL = (
    "FA0701 - Los cargos por Medicamentos o APME que vienen relacionados en "
    "los soportes de cobro, presentan diferencias con las cantidades que "
    "fueron facturadas - CUPS 224249-2 - IOBITRIDOL 300MG/50ML (XENETIX) "
    "( EQUIVALENTE A 30%P/V DE YODO) - Valor objetado: $ 103.000 - SE OBJETA "
    "MEDIO DE CONTRASTE UTILIZADO SEGUN NOTA OPERATORIA SE UTILIZA 40CC LA "
    "HOJA DE GASTOS REGISTRA FRASCO DE 100 ML 50 ML POR LO TANTO NO SE "
    "RECONOCE COBRO DE 4 UNIDADES."
)

PARRAFO_QUE_SE_RADICO = (
    "EN RELACIÓN CON LA OBJECIÓN DE QUE SE HABÍA UTILIZADO 40 CC DE CONTRASTE "
    "Y QUE LA HOJA DE GASTOS REGISTRA UN FRASCO DE 100 ML, SE DEBE SEÑALAR "
    "QUE EL ÍTEM 13 DE LA FACTURA INDICA LA ADQUISICIÓN DE CINCO UNIDADES DE "
    "100 ML CADA UNA, TOTALIZANDO 500 ML."
)


class TestElCasoReal:
    def test_el_parrafo_que_se_radico_queda_marcado(self):
        r = check_medidas_no_fabricadas(PARRAFO_QUE_SE_RADICO, GLOSA_REAL)
        assert not r.ok
        assert r.severidad == "ERROR"

    def test_dice_exactamente_que_se_invento(self):
        r = check_medidas_no_fabricadas(PARRAFO_QUE_SE_RADICO, GLOSA_REAL)
        assert "500 ML" in r.razon
        assert "ítem 13" in r.razon
        assert "5 unidad(es)" in r.razon

    def test_no_acusa_lo_que_si_estaba_en_la_glosa(self):
        """40 CC, 100 ML, 50 ML y 300 MG los escribió la propia entidad."""
        r = check_medidas_no_fabricadas(PARRAFO_QUE_SE_RADICO, GLOSA_REAL)
        for legitimo in ("40 ML", "100 ML", "50 ML", "300 MG"):
            assert legitimo not in r.razon

    def test_la_respuesta_honesta_pasa(self):
        """Contestar con lo que sí consta: el frasco es de 50 ML."""
        honesta = (
            "EL MEDICAMENTO FACTURADO ES IOBITRIDOL 300MG/50ML; LOS 40 CC QUE "
            "REGISTRA LA NOTA OPERATORIA CORRESPONDEN AL VOLUMEN ADMINISTRADO "
            "AL PACIENTE, CONFORME AL ARTÍCULO 56 DE LA LEY 1438 DE 2011."
        )
        assert check_medidas_no_fabricadas(honesta, GLOSA_REAL).ok


class TestQueNoSeVuelvaLoco:
    """Un ERROR falso cuesta una regeneración de IA y una escalada a humano."""

    def test_los_numerales_de_una_norma_no_son_medidas(self):
        texto = (
            "CONFORME AL ANEXO 3 G DE LA RESOLUCIÓN 2284 DE 2023, AL NUMERAL "
            "5 L DEL DECRETO 780 DE 2016 Y AL ARTÍCULO 4 MG NO EXISTENTE."
        )
        assert check_medidas_no_fabricadas(texto, "glosa cualquiera").ok

    def test_un_frasco_es_articulo_no_una_cuenta(self):
        texto = "SE ADMINISTRÓ UN FRASCO Y UNA AMPOLLA SEGÚN LA PRESCRIPCIÓN."
        assert check_medidas_no_fabricadas(texto, "glosa cualquiera").ok

    def test_centimetro_cubico_y_mililitro_son_lo_mismo(self):
        """La glosa dice 40CC; el dictamen dice 40 ML. No es invento."""
        assert check_medidas_no_fabricadas("SE APLICARON 40 ML", "SE UTILIZA 40CC").ok

    def test_gramo_escrito_de_varias_formas(self):
        assert check_medidas_no_fabricadas("DOSIS DE 1 G", "CEFAZOLINA VIAL X 1 GR").ok

    def test_ceros_y_decimales_no_cambian_la_cifra(self):
        assert check_medidas_no_fabricadas("50 ML", "50,0 ML").ok

    def test_sin_input_no_se_acusa_a_nadie(self):
        assert check_medidas_no_fabricadas("500 ML", None).ok
        assert check_medidas_no_fabricadas("500 ML", "   ").ok

    def test_dictamen_vacio(self):
        assert check_medidas_no_fabricadas("", GLOSA_REAL).ok

    def test_los_cuatro_dictamenes_de_produccion_del_banco_pasan(self):
        """Los casos reales de tests/benchmark/casos.json no se marcan."""
        import json
        from pathlib import Path

        ruta = Path(__file__).resolve().parents[1] / "benchmark" / "casos.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        casos = datos if isinstance(datos, list) else datos.get("casos", [])
        assert casos, "el banco de casos reales no puede estar vacío"
        for caso in casos:
            entrada = json.dumps(
                [caso.get("glosa"), caso.get("conceptos"), caso.get("contrato")],
                ensure_ascii=False,
            )
            dictamen = caso.get("dictamen_produccion") or ""
            if isinstance(dictamen, dict):
                dictamen = json.dumps(dictamen, ensure_ascii=False)
            resultado = check_medidas_no_fabricadas(dictamen, entrada)
            assert resultado.ok, f"{caso.get('id')}: {resultado.razon}"


class TestLoQueLaIaSiVio:
    """Si la cantidad venía en un soporte leído, es legítima."""

    def test_una_medida_del_soporte_no_se_acusa(self):
        dictamen = "LA HOJA DE ADMINISTRACIÓN REGISTRA 250 ML."
        assert not check_medidas_no_fabricadas(dictamen, "glosa sin cifras").ok
        assert check_medidas_no_fabricadas(
            dictamen,
            "glosa sin cifras",
            fuentes_adicionales=["… se infundieron 250 ML de solución …"],
        ).ok

    def test_fuentes_vacias_no_estorban(self):
        assert not check_medidas_no_fabricadas(
            "500 ML", GLOSA_REAL, fuentes_adicionales=[None, ""]
        ).ok


class TestEngranadoEnElQualityGate:
    def test_el_check_corre_dentro_del_post_validador(self):
        r = post_validar_dictamen(
            PARRAFO_QUE_SE_RADICO,
            texto_glosa_input=GLOSA_REAL,
        )
        assert "medidas_fabricadas" in r.checks
        assert not r.checks["medidas_fabricadas"].ok

    def test_baja_el_puntaje_y_no_aprueba(self):
        r = post_validar_dictamen(PARRAFO_QUE_SE_RADICO, texto_glosa_input=GLOSA_REAL)
        assert not r.aprobado
        assert any("medidas_fabricadas" in razon for razon in r.razones_rechazo)

    def test_el_orchestrator_pasa_las_fuentes(self):
        """Que nadie corte el hilo entre el prompt real y el check."""
        import inspect

        from app.services.quality_gate import orchestrator

        fuente = inspect.getsource(orchestrator.ejecutar_quality_gate)
        assert fuente.count("fuentes_adicionales=fuentes_adicionales") == 2, (
            "los dos llamados a post_validar_dictamen deben pasar las fuentes"
        )

    def test_el_adaptador_entrega_el_prompt_que_vio_la_ia(self):
        import inspect

        from app.services import quality_gate_adapter

        fuente = inspect.getsource(quality_gate_adapter)
        assert "fuentes_adicionales=[user_prompt]" in fuente
