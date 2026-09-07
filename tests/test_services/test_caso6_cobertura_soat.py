"""Caso 6 (CO4601, COOSALUD): quién paga primero, y quién lo prueba.

02-09-2026. Accidente de tránsito; la entidad glosa toda la factura porque el
hospital «no acredita el agotamiento de la cobertura del SOAT». Sin un solo
PDF, el dictamen:

  1. inventó que «la responsabilidad de demostrar el agotamiento corresponde a
     la entidad pagadora por carga dinámica de la prueba» — al revés: la IPS
     factura al SOAT y la IPS aporta el certificado de la aseguradora;
  2. inventó que la Resolución 2284/2023 «confirma que los servicios facturados
     sin agotar topes deben ser reconocidos» — es el manual de códigos, no una
     regla de pago;
  3. omitió el Decreto 780 de 2016, que es la norma del orden de cobertura;
  4. y el número de la póliza «7745120-3» terminó pegado al nombre del
     servicio («RADIOGRAFÍA DE TÓRAX-3»).

Lo primero venía del propio prompt, que enseñaba la carga dinámica como arma
general y encima con la norma equivocada (Art. 57 Ley 1438, que es el trámite
de glosas). Lo demás se decide ahora en código.
"""

from __future__ import annotations

import io

import pytest

from app.services.glosa_ia_prompts import (
    SYSTEM_BASE,
    SYSTEM_CO,
    build_user_prompt,
    es_glosa_cobertura_soat,
    hay_certificado_agotamiento,
)
from app.services.glosa_service import (
    _afirmaciones_soat_sin_respaldo,
    _desenmascarar,
    _enmascarar_identificadores,
    _familias_afirmadas_sin_respaldo,
    _neutralizar_cups_sin_respaldo,
    _parrafo_cobertura_soat,
)

PROMPTS = io.open("app/services/glosa_ia_prompts.py", encoding="utf-8").read()

GLOSA = (
    "CO4601 | HUS0000603552 | COOSALUD EPS CONTRIBUTIVO\n"
    "SERVICIOS FACTURADOS A LA EPS SIN AGOTAR TOPES DE SOAT/ADRES. EL PACIENTE\n"
    "INGRESO POR ACCIDENTE DE TRANSITO. LA CONSULTA DE URGENCIAS POR\n"
    "ESPECIALISTA (CUPS 890702) Y LA RADIOGRAFIA DE TORAX (CUPS 871121) DEBEN\n"
    "COBRARSE PRIMERO A LA POLIZA SOAT No. 7745120-3 Y AL ADRES. LA IPS NO\n"
    "ACREDITA EL AGOTAMIENTO DE LA COBERTURA DEL SOAT. SE GLOSA LA TOTALIDAD.\n"
    "VALOR FACTURADO: $1.462.000  VALOR GLOSADO: $1.462.000"
)
SOLO_HC = "═══ DOCUMENTO: historia_clinica.pdf ═══\nINGRESO POR URGENCIAS 04/04/2026."
CON_CERT_NOMBRE = "═══ DOCUMENTO: certificado_agotamiento_soat.pdf ═══\nla aseguradora certifica"
CON_CERT_TEXTO = (
    "═══ DOCUMENTO: carta_aseguradora.pdf ═══\nSE CERTIFICA EL AGOTAMIENTO DE LA COBERTURA "
    "DE LA POLIZA 7745120-3 POR PAGOS EFECTUADOS."
)

# Lo que salió en producción, en sus dos órdenes de palabras.
FRASES_INVENTADAS = [
    "LA RESPONSABILIDAD DE DEMOSTRAR EL AGOTAMIENTO DE LA COBERTURA CORRESPONDE A LA ENTIDAD PAGADORA POR CARGA DINAMICA DE LA PRUEBA.",
    "CORRESPONDE A LA ENTIDAD PAGADORA DEMOSTRAR EL AGOTAMIENTO DE LA COBERTURA.",
    "POR CARGA DINAMICA DE LA PRUEBA ES LA EPS QUIEN DEBE ACREDITARLO.",
    "LA RESOLUCION 2284/2023 CONFIRMA QUE LOS SERVICIOS FACTURADOS SIN AGOTAR TOPES DEBEN SER RECONOCIDOS.",
    "SE AGOTO LA COBERTURA DE LA POLIZA.",
    "EL TOPE DEL SOAT SE ENCUENTRA AGOTADO.",
    "EL CERTIFICADO DE AGOTAMIENTO SE APORTO CON LA FACTURA.",
]


class TestElPromptDejaDeEnsenarLaMentira:
    def test_ya_no_atribuye_la_carga_dinamica_al_art_57(self):
        assert "Art. 57 (carga din" not in PROMPTS
        assert "Ley 1438/2011 Art. 57 (carga dinámica)" not in PROMPTS

    def test_la_fuente_correcta_es_el_art_167_cgp(self):
        assert "Art. 167 del Código General del Proceso" in PROMPTS
        assert PROMPTS.count("Art. 167 CGP") >= 2

    def test_la_carga_dinamica_nunca_para_lo_propio_de_la_ips(self):
        assert "NUNCA para lo que la IPS debe probar por ser suya la carga" in PROMPTS
        assert "AGOTAMIENTO de la cobertura del SOAT" in PROMPTS

    def test_res_2284_es_solo_el_manual_de_codigos(self):
        assert "PROHIBICIÓN ABSOLUTA — LO QUE UNA NORMA NO DICE" in SYSTEM_BASE
        assert "NO establece reglas de pago" in SYSTEM_BASE
        assert "confirma que los servicios facturados sin agotar topes" in SYSTEM_BASE

    def test_el_modulo_co_trae_el_orden_de_cobertura(self):
        assert "TOPES SOAT/ADRES (CO4601" in SYSTEM_CO
        assert "Decreto 780 de 2016" in SYSTEM_CO
        assert "QUIÉN LO PRUEBA: la IPS" in SYSTEM_CO
        assert "PROHIBIDO" in SYSTEM_CO and "carga dinámica" in SYSTEM_CO


class TestLosDetectores:
    def test_reconoce_la_glosa_de_cobertura_soat(self):
        assert es_glosa_cobertura_soat(GLOSA)

    @pytest.mark.parametrize(
        "texto",
        [
            "SE GLOSA POR ACCIDENTE DE TRANSITO",
            "AGOTAR TOPES DE ADRES",
            "POLIZA SOAT VIGENTE",
            "CO4601",
        ],
    )
    def test_cualquier_senal_basta(self, texto: str):
        assert es_glosa_cobertura_soat(texto)

    def test_una_glosa_de_tarifa_no_es_de_cobertura_soat(self):
        assert not es_glosa_cobertura_soat("TA0301 MAYOR VALOR COBRADO EN CONSULTA")

    def test_sin_certificado_con_solo_historia(self):
        assert not hay_certificado_agotamiento(SOLO_HC)
        assert not hay_certificado_agotamiento("")

    def test_certificado_por_nombre_de_archivo(self):
        assert hay_certificado_agotamiento(CON_CERT_NOMBRE)

    def test_certificado_por_su_texto(self):
        assert hay_certificado_agotamiento(CON_CERT_TEXTO)


class TestLoQueNoSePuedeDecirSinCertificado:
    @pytest.mark.parametrize("frase", FRASES_INVENTADAS)
    def test_cae_en_cualquier_orden_de_palabras(self, frase: str):
        limpio, borradas = _afirmaciones_soat_sin_respaldo(
            "LA ATENCION FUE POR URGENCIAS. " + frase + " SE SOLICITA EL LEVANTAMIENTO.", False
        )
        assert borradas, frase
        assert "LA ATENCION FUE POR URGENCIAS." in limpio
        assert "SE SOLICITA EL LEVANTAMIENTO." in limpio

    def test_negar_es_legitimo(self):
        arg = "ESTA IPS NO AFIRMA QUE EL TOPE ESTE AGOTADO. SIN CERTIFICADO NO SE ACREDITA EL AGOTAMIENTO."
        assert _afirmaciones_soat_sin_respaldo(arg, False) == (arg, [])

    def test_con_certificado_no_se_toca_nada(self):
        arg = "SE AGOTO LA COBERTURA DE LA POLIZA, COMO CONSTA EN EL CERTIFICADO APORTADO."
        assert _afirmaciones_soat_sin_respaldo(arg, True) == (arg, [])

    def test_texto_vacio_no_rompe(self):
        assert _afirmaciones_soat_sin_respaldo("", False) == ("", [])


class TestElParrafoLoArmaElMotor:
    def test_sin_certificado_no_afirma_el_agotamiento(self):
        p = _parrafo_cobertura_soat("COOSALUD", con_certificado=False).upper()
        assert "NO AFIRMA EN ESTE ESCRITO QUE EL TOPE SE ENCUENTRE AGOTADO" in p
        assert "APORTARÁ" in p
        assert "PRECISAR EL TOPE Y EL VALOR" in p

    def test_con_certificado_lo_dice_y_lo_senala(self):
        p = _parrafo_cobertura_soat("COOSALUD", con_certificado=True).upper()
        assert "CERTIFICADO DE LA ASEGURADORA QUE OBRA ENTRE LOS SOPORTES" in p

    def test_cita_el_decreto_780_y_nunca_la_2284(self):
        for cert in (True, False):
            p = _parrafo_cobertura_soat("COOSALUD", cert)
            assert "DECRETO 780 DE 2016" in p
            assert "2284" not in p
            assert "CARGA DIN" not in p.upper()

    def test_el_orden_es_soat_adres_eps(self):
        p = _parrafo_cobertura_soat("COOSALUD", False).upper()
        assert (
            p.index("PÓLIZA SOAT RESPONDE EN PRIMER LUGAR")
            < p.index("RESPONDE EL ADRES")
            < p.index("ENTIDAD PROMOTORA DE SALUD")
        )


class TestElPromptRecibeLaOrdenAntesDeRedactar:
    def test_sin_certificado_el_bloque_va(self):
        p = build_user_prompt(
            texto_glosa=GLOSA, contexto_pdf=SOLO_HC, codigo="CO4601", eps="COOSALUD"
        )
        assert "NO HAY CERTIFICADO DE AGOTAMIENTO ENTRE LOS SOPORTES" in p
        assert "nada de «carga" in p
        assert "Decreto 780 de 2016" in p

    def test_con_certificado_el_bloque_no_va(self):
        p = build_user_prompt(
            texto_glosa=GLOSA, contexto_pdf=CON_CERT_NOMBRE, codigo="CO4601", eps="COOSALUD"
        )
        assert "NO HAY CERTIFICADO DE AGOTAMIENTO" not in p

    def test_una_glosa_de_otra_familia_no_lo_recibe(self):
        p = build_user_prompt(
            texto_glosa="TA0301 MAYOR VALOR COBRADO EN CONSULTA",
            contexto_pdf="",
            codigo="TA0301",
            eps="COOSALUD",
        )
        assert "NO HAY CERTIFICADO DE AGOTAMIENTO" not in p


class TestElCertificadoEsUnDocumentoVigilado:
    def test_afirmar_lo_que_dice_sin_tenerlo_se_detecta(self):
        d = "SEGUN EL CERTIFICADO DE AGOTAMIENTO EXPEDIDO POR LA ASEGURADORA, EL TOPE SE ENCUENTRA AGOTADO."
        assert "certificado de agotamiento del SOAT" in _familias_afirmadas_sin_respaldo(d, SOLO_HC)

    def test_con_el_certificado_entre_lo_aportado_no_se_reclama(self):
        d = "SEGUN EL CERTIFICADO DE AGOTAMIENTO EXPEDIDO POR LA ASEGURADORA, EL TOPE SE ENCUENTRA AGOTADO."
        assert "certificado de agotamiento del SOAT" not in _familias_afirmadas_sin_respaldo(
            d, CON_CERT_TEXTO
        )


class TestLaPolizaNoEsUnCups:
    def test_enmascara_y_restaura_exacto(self):
        t = "POLIZA SOAT No. 7745120-3 Y AUTORIZACION No. 20260455 Y RADICADO 2026-08-991."
        m, mapa = _enmascarar_identificadores(t)
        assert "7745120-3" not in m and "20260455" not in m and "2026-08-991" not in m
        assert len(mapa) == 3
        assert _desenmascarar(m, mapa) == t

    def test_la_marca_no_tiene_digitos(self):
        m, mapa = _enmascarar_identificadores("POLIZA SOAT No. 7745120-3")
        for clave in mapa:
            assert not any(ch.isdigit() for ch in clave.rstrip("X")[:8]), clave

    def test_un_rotulo_sin_numero_se_deja_quieto(self):
        t = "LA ORDEN MEDICA Y EL LOTE VENCIDO."
        assert _enmascarar_identificadores(t) == (t, {})

    def test_el_cups_real_no_se_enmascara(self):
        t = "RADIOGRAFIA DE TORAX (CUPS 871121) Y POLIZA SOAT No. 7745120-3."
        m, _ = _enmascarar_identificadores(t)
        assert "871121" in m

    def test_un_token_con_sufijo_no_es_cups_y_se_retira_entero(self):
        r = _neutralizar_cups_sin_respaldo(
            "EL SERVICIO CON CUPS 7745120-3 SE PRESTO.", "", "CO4601"
        )
        assert "7745120" not in r and "-3" not in r
        assert "código" not in r.lower()

    def test_siete_digitos_tampoco_son_cups(self):
        r = _neutralizar_cups_sin_respaldo("EL SERVICIO CON CUPS 7745120 SE PRESTO.", "", "CO4601")
        assert "7745120" not in r

    def test_el_cups_real_de_seis_digitos_sigue_intacto(self):
        t = "RADIOGRAFIA DE TORAX (CUPS 871121)."
        assert _neutralizar_cups_sin_respaldo(t, "", "CO4601") == t

    def test_el_motor_enmascara_antes_y_restaura_despues(self):
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        i_mask = motor.index("dictamen, _mapa_ids = _enmascarar_identificadores(dictamen)")
        i_falsos = motor.index("_dictamen_sin_cups_falso = _neutralizar_cups_falsos(dictamen)")
        i_unmask = motor.index("dictamen = _desenmascarar(dictamen, _mapa_ids)")
        i_sinresp = motor.index("_dictamen_cups_respaldado = _neutralizar_cups_sin_respaldo(")
        assert i_mask < i_falsos < i_sinresp < i_unmask
