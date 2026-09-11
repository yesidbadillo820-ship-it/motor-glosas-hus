"""El dictamen no puede negar QUÉ ES una cosa cuando el papel lo dice.

Caso real (10-09-2026, objeción 189801, causal FA0701). Para defender el
cobro del IOBITRIDOL, el dictamen escribió:

    «…Y QUE EL MEDICAMENTO IOBITRIDOL NO ES UN MEDIO DE CONTRASTE, SINO UN
     SOLUCIÓN ANTISEPTICA»

El iobitridol es un medio de contraste yodado: lo dice la propia factura
(«EQUIVALENTE A 30%P/V DE YODO») y la entidad lo objetó llamándolo así («SE
OBJETA MEDIO DE CONTRASTE UTILIZADO»). Del otro lado eso lo lee un médico
auditor, y una sola frase así desacredita la respuesta entera — incluidos los
siete renglones de millones que iban bien argumentados.

Lo que el check NO hace: opinar de medicina. Solo mira si el dictamen niega,
con esas mismas palabras, una naturaleza que el papel afirma. Negarle a la
entidad sus afirmaciones jurídicas —que la glosa es extemporánea, que no hubo
autorización— es el trabajo del dictamen y no se toca.
"""

import json
from pathlib import Path

from app.services.quality_gate.post_validator import (
    check_no_contradice_la_naturaleza_del_servicio,
    post_validar_dictamen,
)

GLOSA_REAL = (
    "FA0701 - Los cargos por Medicamentos o APME presentan diferencias con las "
    "cantidades facturadas - CUPS 224249-2 - IOBITRIDOL 300MG/50ML (XENETIX) "
    "( EQUIVALENTE A 30%P/V DE YODO) - SE OBJETA MEDIO DE CONTRASTE UTILIZADO "
    "SEGUN NOTA OPERATORIA SE UTILIZA 40CC."
)

FRASE_QUE_SE_RADICO = (
    "Y QUE EL MEDICAMENTO IOBITRIDOL NO ES UN MEDIO DE CONTRASTE, SINO UN "
    "SOLUCIÓN ANTISEPTICA. POR LO TANTO, NO EXISTE DISCREPANCIA."
)


class TestElCasoReal:
    def test_la_frase_que_se_radico_queda_marcada(self):
        r = check_no_contradice_la_naturaleza_del_servicio(FRASE_QUE_SE_RADICO, GLOSA_REAL)
        assert not r.ok
        assert r.severidad == "ERROR"
        assert "medio de contraste" in r.razon

    def test_la_respuesta_correcta_pasa(self):
        buena = (
            "EL IOBITRIDOL ES EL MEDIO DE CONTRASTE YODADO EMPLEADO EN LA "
            "ANGIOGRAFÍA, CONFORME A LA NOTA OPERATORIA Y A LA DESCRIPCIÓN DE "
            "LA FACTURA."
        )
        assert check_no_contradice_la_naturaleza_del_servicio(buena, GLOSA_REAL).ok

    def test_corre_dentro_del_quality_gate(self):
        r = post_validar_dictamen(FRASE_QUE_SE_RADICO, texto_glosa_input=GLOSA_REAL)
        assert "naturaleza_contradicha" in r.checks
        assert not r.checks["naturaleza_contradicha"].ok
        assert not r.aprobado


class TestNoLeQuitaAlDictamenSuTrabajo:
    """Negarle a la entidad sus afirmaciones jurídicas ES el dictamen."""

    def test_negar_la_extemporaneidad_no_es_contradecir_el_papel(self):
        d = (
            "LA GLOSA NO ES EXTEMPORÁNEA, NO PROCEDE LA OBJECIÓN Y NO SE "
            "CONFIGURA EL SUPUESTO DE HECHO DE LA CAUSAL INVOCADA."
        )
        assert check_no_contradice_la_naturaleza_del_servicio(d, GLOSA_REAL).ok

    def test_negar_algo_que_el_papel_no_dice_no_salta(self):
        d = "EL COIL NO ES UN ANTIBIÓTICO NI REQUIERE CADENA DE FRÍO."
        assert check_no_contradice_la_naturaleza_del_servicio(d, GLOSA_REAL).ok

    def test_afirmar_no_es_negar(self):
        d = "SE TRATA DE UN MEDIO DE CONTRASTE Y DE UN DISPOSITIVO MÉDICO."
        assert check_no_contradice_la_naturaleza_del_servicio(d, GLOSA_REAL).ok

    def test_sin_input_no_se_acusa_a_nadie(self):
        assert check_no_contradice_la_naturaleza_del_servicio(FRASE_QUE_SE_RADICO, None).ok
        assert check_no_contradice_la_naturaleza_del_servicio(FRASE_QUE_SE_RADICO, "  ").ok

    def test_dictamen_vacio(self):
        assert check_no_contradice_la_naturaleza_del_servicio("", GLOSA_REAL).ok

    def test_los_dictamenes_reales_de_produccion_pasan(self):
        ruta = Path(__file__).resolve().parents[1] / "benchmark" / "casos.json"
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        casos = datos if isinstance(datos, list) else datos.get("casos", [])
        assert casos
        for caso in casos:
            entrada = json.dumps(
                [caso.get("glosa"), caso.get("conceptos"), caso.get("contrato")],
                ensure_ascii=False,
            )
            dictamen = caso.get("dictamen_produccion") or ""
            if isinstance(dictamen, dict):
                dictamen = json.dumps(dictamen, ensure_ascii=False)
            r = check_no_contradice_la_naturaleza_del_servicio(dictamen, entrada)
            assert r.ok, f"{caso.get('id')}: {r.razon}"


class TestLasOtrasFormasDeDecirLoMismo:
    def test_no_se_trata_de(self):
        d = "EL PRODUCTO NO SE TRATA DE UN MEDIO DE CONTRASTE."
        assert not check_no_contradice_la_naturaleza_del_servicio(d, GLOSA_REAL).ok

    def test_no_corresponde_a(self):
        d = "LO FACTURADO NO CORRESPONDE A UN MEDICAMENTO."
        glosa = "se objeta el MEDICAMENTO facturado en el renglón 3"
        assert not check_no_contradice_la_naturaleza_del_servicio(d, glosa).ok

    def test_acentos_y_mayusculas_dan_igual(self):
        glosa = "se objeta el uso de un antiséptico no pactado"
        assert not check_no_contradice_la_naturaleza_del_servicio(
            "no es un ANTISEPTICO, es otra cosa", glosa
        ).ok

    def test_lo_que_la_ia_vio_en_los_soportes_tambien_cuenta(self):
        d = "EL PRODUCTO NO ES UN MEDIO DE CONTRASTE."
        assert check_no_contradice_la_naturaleza_del_servicio(d, "glosa sin descripción").ok
        assert not check_no_contradice_la_naturaleza_del_servicio(
            d,
            "glosa sin descripción",
            fuentes_adicionales=["…se administró el medio de contraste yodado…"],
        ).ok
