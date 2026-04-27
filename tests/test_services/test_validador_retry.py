"""Tests del validador post-gen + retry (R-cerebro #1)."""
from __future__ import annotations

from app.services.validador_dictamen import (
    construir_instruccion_retry,
    detectar_defectos_criticos,
    resumen_defectos,
)


def _xml_ok(arg: str) -> str:
    return (
        "<paciente>X</paciente><servicio>S</servicio>"
        "<contrato>C</contrato><tarifa>T</tarifa>"
        "<normas_clave>N1|N2</normas_clave>"
        f"<argumento>{arg}</argumento>"
    )


_BUEN_ARGUMENTO = (
    "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE FACTURACIÓN "
    "SOBRE EL CÓDIGO FA0401, INTERPUESTA POR COOSALUD, RESPECTO DEL "
    "SERVICIO IDENTIFICADO CON CUPS 890301, FACTURADO POR EL VALOR "
    "INDICADO EN EL EXPEDIENTE. DE CONFORMIDAD CON EL ARTÍCULO 177 DE "
    "LA LEY 100 DE 1993, LA ENTIDAD PAGADORA TIENE EL DEBER DE "
    "RECONOCER LOS SERVICIOS PRESTADOS. POR LO ANTERIOR SE SOLICITA "
    "RESPETUOSAMENTE EL LEVANTAMIENTO DE LA GLOSA FA0401 Y EL "
    "RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO. COMUNICACIONES: "
    "CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."
)


class TestDetectarDefectos:
    def test_dictamen_ok_no_tiene_defectos_criticos(self):
        xml = _xml_ok(_BUEN_ARGUMENTO)
        d = detectar_defectos_criticos(xml, codigo_glosa="FA0401")
        # Puede haber warnings pero no bloqueos críticos
        criticos_clave = {x["regla"] for x in d}
        assert "sin_argumento" not in criticos_clave
        assert "inicio_invalido" not in criticos_clave
        assert "sin_email_contacto" not in criticos_clave

    def test_xml_vacio(self):
        d = detectar_defectos_criticos("", codigo_glosa="FA01")
        assert any(x["regla"] == "vacio" for x in d)

    def test_falta_tag_argumento(self):
        d = detectar_defectos_criticos(
            "<paciente>X</paciente>", codigo_glosa="FA01",
        )
        assert any(x["regla"] == "sin_argumento" for x in d)

    def test_inicio_invalido(self):
        arg = "RESPETUOSAMENTE NO SE ACEPTA " + _BUEN_ARGUMENTO
        d = detectar_defectos_criticos(_xml_ok(arg), codigo_glosa="FA0401")
        assert any(x["regla"] == "inicio_invalido" for x in d)

    def test_sin_email_contacto(self):
        arg = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE FA0401. "
            "DE CONFORMIDAD CON LA LEY 100. SE SOLICITA EL LEVANTAMIENTO."
        )
        d = detectar_defectos_criticos(_xml_ok(arg), codigo_glosa="FA0401")
        assert any(x["regla"] == "sin_email_contacto" for x in d)

    def test_frase_prohibida(self):
        arg = _BUEN_ARGUMENTO + " SE EXIGE EL LEVANTAMIENTO INMEDIATO."
        d = detectar_defectos_criticos(_xml_ok(arg), codigo_glosa="FA0401")
        assert any(
            x["regla"].startswith("frase_prohibida") for x in d
        )

    def test_placeholder_corchete(self):
        arg = _BUEN_ARGUMENTO + " VALOR $[VALOR] PARA [PACIENTE]."
        d = detectar_defectos_criticos(_xml_ok(arg), codigo_glosa="FA0401")
        assert any(x["regla"] == "placeholder_corchete" for x in d)

    def test_codigo_no_mencionado(self):
        # arg con FA0401 pero pedimos TA0801
        d = detectar_defectos_criticos(
            _xml_ok(_BUEN_ARGUMENTO), codigo_glosa="TA0801",
        )
        assert any(x["regla"] == "codigo_glosa_no_mencionado" for x in d)

    def test_valor_no_textual(self):
        # Pedimos $190.964, el dictamen no lo menciona
        d = detectar_defectos_criticos(
            _xml_ok(_BUEN_ARGUMENTO),
            codigo_glosa="FA0401",
            valor_objetado="$190.964",
        )
        assert any(x["regla"] == "valor_no_textual" for x in d)

    def test_cita_incorrecta_1601(self):
        arg = _BUEN_ARGUMENTO + " VER ART. 1601 CC."
        d = detectar_defectos_criticos(_xml_ok(arg), codigo_glosa="FA0401")
        assert any(x["regla"] == "cita_incorrecta" for x in d)

    def test_tarifa_propia_con_contrato_es_critico(self):
        # Caso real del feedback usuario: dictamen menciona "tarifa
        # propia institucional" + "en virtud del contrato" simultáneamente.
        arg = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS "
            "SOBRE EL CÓDIGO TA0201, INTERPUESTA POR DISPENSARIO MEDICO, "
            "RESPECTO DEL SERVICIO IDENTIFICADO CON CUPS 39147B-18, "
            "FACTURADO POR $168.563, DADO QUE LA TARIFA APLICADA "
            "CORRESPONDE A LA TARIFA PROPIA INSTITUCIONAL DE LA ESE HUS "
            "ESTABLECIDA EN LA RESOLUCIÓN 054 DE 2026, LA CUAL RESULTA "
            "PLENAMENTE EXIGIBLE EN VIRTUD DEL CONTRATO No. 440-DIGSA. "
            "COMUNICACIONES: CARTERA@HUS.GOV.CO, "
            "GLOSASYDEVOLUCIONES@HUS.GOV.CO."
        )
        d = detectar_defectos_criticos(
            _xml_ok(arg),
            codigo_glosa="TA0201",
            valor_objetado="$168.563",
            tiene_contrato=True,
        )
        assert any(x["regla"] == "tarifa_propia_con_contrato" for x in d)

    def test_tarifa_propia_pactada_es_contradiccion_interna(self):
        # Caso real de producción 27-abr-2026: el LLM escribió
        # "TARIFA PROPIA INSTITUCIONAL PACTADA DE $231.556" — se lee
        # como contradicción aunque no diga "en virtud del contrato".
        arg = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS "
            "SOBRE EL CÓDIGO TA0201, INTERPUESTA POR DISPENSARIO MEDICO, "
            "RESPECTO DEL SERVICIO IDENTIFICADO CON CUPS 39147B-18, "
            "FACTURADO POR $168.563, DADO QUE EL VALOR COBRADO SE "
            "ENCUENTRA POR DEBAJO DE LA TARIFA PROPIA INSTITUCIONAL "
            "PACTADA DE $231.556. EL DECRETO 1795 DE 2000 RIGE EL "
            "CONTRATO INTERADMINISTRATIVO VIGENTE. "
            "COMUNICACIONES: CARTERA@HUS.GOV.CO, "
            "GLOSASYDEVOLUCIONES@HUS.GOV.CO."
        )
        d = detectar_defectos_criticos(
            _xml_ok(arg),
            codigo_glosa="TA0201",
            valor_objetado="$168.563",
            tiene_contrato=True,
        )
        assert any(x["regla"] == "tarifa_propia_con_contrato" for x in d)

    def test_tarifa_propia_y_contrato_interadministrativo(self):
        # Variante: contrato mencionado solo como "interadministrativo".
        arg = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS "
            "SOBRE EL CÓDIGO TA0201, FACTURADA POR $168.563, RESPECTO DEL "
            "SERVICIO. LA TARIFA PROPIA INSTITUCIONAL DE $231.556 RIGE "
            "EL CONTRATO INTERADMINISTRATIVO. "
            "COMUNICACIONES: CARTERA@HUS.GOV.CO, "
            "GLOSASYDEVOLUCIONES@HUS.GOV.CO."
        )
        d = detectar_defectos_criticos(
            _xml_ok(arg),
            codigo_glosa="TA0201",
            valor_objetado="$168.563",
            tiene_contrato=True,
        )
        assert any(x["regla"] == "tarifa_propia_con_contrato" for x in d)

    def test_tarifa_propia_sin_contrato_no_es_defecto(self):
        # Si NO hay contrato, "tarifa propia institucional" sí aplica.
        arg = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA SOBRE EL CÓDIGO TA0201, "
            "INTERPUESTA POR ASEGURADORA SOAT, RESPECTO DEL SERVICIO "
            "FACTURADO POR $168.563, DADO QUE LA TARIFA APLICADA "
            "CORRESPONDE A LA TARIFA PROPIA INSTITUCIONAL ESTABLECIDA EN "
            "LA RESOLUCIÓN 054 DE 2026 ESE HUS, APLICABLE EN AUSENCIA "
            "DE ACUERDO TARIFARIO PREVIO. "
            "COMUNICACIONES: CARTERA@HUS.GOV.CO, "
            "GLOSASYDEVOLUCIONES@HUS.GOV.CO."
        )
        d = detectar_defectos_criticos(
            _xml_ok(arg),
            codigo_glosa="TA0201",
            valor_objetado="$168.563",
            tiene_contrato=False,
        )
        assert not any(
            x["regla"] == "tarifa_propia_con_contrato" for x in d
        )

    def test_facturado_es_objetado_se_marca(self):
        # Caso real 27-abr-2026: el LLM escribió "FACTURADA POR $168.563"
        # pero $168.563 es el VALOR OBJETADO, no el facturado ($247.663).
        arg = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS "
            "SOBRE EL CÓDIGO TA0201, INTERPUESTA POR DISPENSARIO MEDICO, "
            "RESPECTO DEL SERVICIO IDENTIFICADO CON CUPS 39147B-18, "
            "FACTURADA POR $168.563, DADO QUE EL VALOR COBRADO ESTÁ POR "
            "DEBAJO DE LA TARIFA PACTADA. COMUNICACIONES: "
            "CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."
        )
        d = detectar_defectos_criticos(
            _xml_ok(arg),
            codigo_glosa="TA0201",
            valor_objetado="$168.563",
            valor_facturado="$247.663",
            tiene_contrato=True,
        )
        assert any(x["regla"] == "facturado_es_objetado" for x in d)

    def test_facturado_correcto_no_se_marca(self):
        # Si el dictamen cita el FACTURADO real ($247.663) y luego dice
        # OBJETA $168.563, NO debe marcar.
        arg = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE TARIFAS "
            "SOBRE EL CÓDIGO TA0201, INTERPUESTA POR DISPENSARIO MEDICO, "
            "RESPECTO DEL SERVICIO IDENTIFICADO CON CUPS 39147B-18, "
            "FACTURADO POR $247.663, RESPECTO DEL CUAL LA ENTIDAD "
            "PAGADORA OBJETA $168.563. COMUNICACIONES: "
            "CARTERA@HUS.GOV.CO, GLOSASYDEVOLUCIONES@HUS.GOV.CO."
        )
        d = detectar_defectos_criticos(
            _xml_ok(arg),
            codigo_glosa="TA0201",
            valor_objetado="$168.563",
            valor_facturado="$247.663",
            tiene_contrato=True,
        )
        assert not any(x["regla"] == "facturado_es_objetado" for x in d)

    def test_demasiado_largo_se_marca(self):
        # Argumento con > 340 palabras debe disparar 'demasiado_largo'
        bloque = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE FACTURACIÓN "
            "SOBRE EL CÓDIGO FA0401, INTERPUESTA POR COOSALUD, RESPECTO DEL "
            "SERVICIO FACTURADO. " + ("PALABRA " * 350) +
            "COMUNICACIONES: CARTERA@HUS.GOV.CO, "
            "GLOSASYDEVOLUCIONES@HUS.GOV.CO."
        )
        d = detectar_defectos_criticos(
            _xml_ok(bloque), codigo_glosa="FA0401",
        )
        assert any(x["regla"] == "demasiado_largo" for x in d)

    def test_300_palabras_ya_no_dispara(self):
        # 300 palabras está dentro del nuevo límite (340) — no flag.
        bloque = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE FACTURACIÓN "
            "SOBRE EL CÓDIGO FA0401, INTERPUESTA POR COOSALUD, RESPECTO DEL "
            "SERVICIO FACTURADO. " + ("PALABRA " * 280) +
            "COMUNICACIONES: CARTERA@HUS.GOV.CO, "
            "GLOSASYDEVOLUCIONES@HUS.GOV.CO."
        )
        d = detectar_defectos_criticos(
            _xml_ok(bloque), codigo_glosa="FA0401",
        )
        assert not any(x["regla"] == "demasiado_largo" for x in d)


class TestInstruccionRetry:
    def test_construir_retry_no_vacio_si_hay_defectos(self):
        defectos = [
            {"regla": "frase_prohibida_se_exige",
             "mensaje": "Detectada SE EXIGE", "sugerencia": "Quítalo"},
        ]
        instr = construir_instruccion_retry(defectos)
        assert "DEFECTOS CRÍTICOS" in instr
        assert "SE EXIGE" in instr

    def test_construir_retry_vacio_sin_defectos(self):
        assert construir_instruccion_retry([]) == ""


class TestResumen:
    def test_resumen_lista(self):
        defectos = [
            {"regla": "a", "mensaje": "x"},
            {"regla": "b", "mensaje": "y"},
        ]
        r = resumen_defectos(defectos)
        assert r["total"] == 2
        assert "a" in r["reglas"]
