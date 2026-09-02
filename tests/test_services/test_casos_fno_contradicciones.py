"""Casos F–O (02-09-2026): contradicciones que el modelo no puede razonar solo.

Diez corridas reales en la pantalla en las que el dictamen falló porque el
modelo se dejó llevar por el código inicial, inventó una ley, capturó mal los
números o defendió un imposible. Cada regla vive en `reglas_casos_fno` (la IA
redacta, Python decide) y acá se prueba su comportamiento y —tan importante
como eso— que NO se dispare de más.

  F  código de tarifa, texto que reclama soportes → se responde documental.
  G  ley inventada por la entidad → no se legitima; se argumenta con norma real.
  H  «el 25 % del valor total» → Python calcula 2.500.000, no 10.000.000.
  I  parto en paciente masculino → error de facturación, no autonomía médica.
  J  «se ratifica» / «respuesta a conciliación» en el texto → vía ratificada.
  K  texto basura (&&& /// _ ::: $$$) → se limpia y el código se extrae bien.
  L  alta anterior al ingreso → error de facturación, no «cierre administrativo».
  M  tope SOAT no agotado con matemática correcta → aceptar y cobrar a la aseguradora.
  N  medicamento NO PBS sin MIPRES → se exige el formato, no una devolución genérica.
  O  glosado $0 → informativa, sin defensa jurídica.
"""

from __future__ import annotations

import pytest

from app.services import reglas_casos_fno as R
from app.services.glosa_service import GlosaService


def up(s: str) -> str:
    return s.strip().upper()


@pytest.fixture(scope="module")
def svc() -> GlosaService:
    return GlosaService(groq_api_key="gsk_x")


# ─────────────────────────── Caso K: texto basura ───────────────────────────
CASO_K = "&&&GLOSA///FA0301_FACTURA#HUS0000606666_EPS:NUEVA_EPS***SE_GLOSA_EL_CUPS:::903823_POR_VALOR_DE_$$$450.000==MOTIVO:NO_HAY_ORDEN."


class TestCasoK_TextoBasura:
    def test_el_codigo_se_extrae_pese_al_ruido(self, svc):
        limpio = R.limpiar_ruido_glosa(up(CASO_K))
        assert svc._extraer_codigo_glosa(limpio) == "FA0301"

    def test_el_cups_sobrevive_a_la_limpieza(self):
        assert "903823" in R.limpiar_ruido_glosa(up(CASO_K))

    def test_el_valor_se_extrae_del_texto_basura(self, svc):
        limpio = R.limpiar_ruido_glosa(up(CASO_K))
        assert svc._extraer_valor(limpio) == "$ 450.000"

    def test_el_encabezado_normal_no_se_toca(self):
        normal = (
            "CO0000 | HUS0000600000 | SANITAS. SE GLOSA EL 10% Y/O SOBRECOSTO. FECHA 25/08/2026."
        )
        # Sin caracteres basura, la limpieza no cambia nada (ni el '|', ni el
        # '/' de la fecha, ni el ':' de un rótulo, ni el '%').
        assert R.limpiar_ruido_glosa(normal) == normal

    def test_una_fecha_con_barras_sobrevive(self):
        assert "25/08/2026" in R.limpiar_ruido_glosa("INGRESO 25/08/2026")


# ─────────────────────────── Caso O: glosado $0 ───────────────────────────
CASO_O = "CO0000 | HUS0000600000 | SANITAS. GLOSA INFORMATIVA. EL PACIENTE PRESENTA MULTIPLES AFILIACIONES PERO SE AUTORIZA EL PAGO. GLOSADO $0. ACEPTADO $500.000."


class TestCasoO_GlosaInformativaCero:
    def test_detecta_glosado_cero(self):
        assert R.glosa_es_informativa_cero(up(CASO_O))

    def test_el_valor_objetado_es_cero_no_el_aceptado(self, svc):
        assert svc._extraer_valor(up(CASO_O)) == "$ 0.00"

    def test_una_glosa_con_valor_real_no_es_informativa(self):
        assert not R.glosa_es_informativa_cero(up("TA0301 | HUS1 | NUEVA EPS. GLOSADO $500.000."))

    def test_el_dictamen_forzado_es_informativo_sin_defensa(self):
        d = R.dictamen_forzado_por_contradiccion(up(CASO_O), "CO", "CO0000", "$ 0.00", "SANITAS")
        assert d and d["tipo"] == "INFORMATIVA_CERO"
        assert d["cod"] == "RE9701"
        assert "INFORMATIVO" in d["arg"] and "NO PRESENTA DEFENSA" in d["arg"].upper()


# ─────────────────────────── Caso H: porcentaje ───────────────────────────
CASO_H = "TA0301 | HUS0000603333 | NUEVA EPS. SE AUDITA LA FACTURA POR $10.000.000. SE ENCUENTRA COBRO INDEBIDO EN MATERIALES. SE GLOSA EXACTAMENTE EL 25% DEL VALOR TOTAL DE LA FACTURA. PROCEDA CON LA NOTA CREDITO."


class TestCasoH_CalculoPorPorcentaje:
    def test_calcula_el_25_por_ciento_del_total(self):
        assert R.valor_glosa_por_porcentaje(up(CASO_H)) == 2500000

    def test_el_extractor_del_motor_devuelve_el_calculo_no_el_total(self, svc):
        assert svc._extraer_valor(up(CASO_H)) == "$ 2.500.000"

    def test_sin_porcentaje_no_calcula_nada(self):
        assert R.valor_glosa_por_porcentaje(up("SE GLOSA $500.000 EN MATERIALES")) is None

    def test_un_porcentaje_sin_base_no_inventa(self):
        assert R.valor_glosa_por_porcentaje(up("SE GLOSA EL 25% DE LO COBRADO")) is None

    def test_el_50_por_ciento_de_dos_millones(self):
        t = up("SE GLOSA EL 50% DEL VALOR TOTAL DE LA FACTURA POR $2.000.000.")
        assert R.valor_glosa_por_porcentaje(t) == 1000000


# ─────────────────────────── Caso I: incoherencia biológica ───────────────────────────
CASO_I = "CL0201 | HUS0000604444 | FAMISANAR. PERTINENCIA MEDICA. SE FACTURA ATENCION DEL PARTO (CUPS 735930) EN PACIENTE MASCULINO DE 65 AÑOS. SERVICIO INJUSTIFICADO. GLOSA $1.800.000."


class TestCasoI_ParadojaBiologica:
    def test_detecta_parto_en_hombre(self):
        assert R.incoherencia_biologica(up(CASO_I))

    def test_detecta_prostata_en_mujer(self):
        assert R.incoherencia_biologica(up("PROSTATECTOMIA EN PACIENTE FEMENINO"))

    def test_no_dispara_con_parto_en_mujer(self):
        assert R.incoherencia_biologica(up("ATENCION DEL PARTO EN PACIENTE FEMENINO")) is None

    def test_no_dispara_sin_sexo_declarado(self):
        assert R.incoherencia_biologica(up("ATENCION DEL PARTO CUPS 735930")) is None

    def test_el_dictamen_forzado_acepta_por_error_no_defiende(self):
        d = R.dictamen_forzado_por_contradiccion(
            up(CASO_I), "CL", "CL0201", "$ 1.800.000", "FAMISANAR"
        )
        assert d and d["tipo"] == "ACEPTADA_ERROR_FACTURA" and d["cod"] == "RE9702"
        assert "AUTONOMÍA" in d["arg"].upper()  # la nombra para descartarla
        assert "NOTA CRÉDITO" in d["arg"].upper()


# ─────────────────────────── Caso J: ratificación en el texto ───────────────────────────
class TestCasoJ_RatificacionCamuflada:
    @pytest.mark.parametrize(
        "frase",
        [
            "RESPUESTA A CONCILIACION. LA IPS APORTO LOS SOPORTES.",
            "SE CONVOCA A MESA DE CONCILIACION POR LA GLOSA.",
            "SEGUNDA RESPUESTA A LA GLOSA FA0101.",
            "FA0101 | HUS1 | COOSALUD. RESPUESTA A CONCILIACION. SE RATIFICA LA GLOSA INICIAL.",
        ],
    )
    def test_marcador_de_etapa_dispara(self, frase):
        assert R.texto_es_ratificacion(up(frase))

    @pytest.mark.parametrize(
        "frase",
        [
            # «ratifica» a secas NO basta: es lo que hace la EPS, no la etapa.
            "SE RATIFICA LA GLOSA INICIAL POR $800.000.",
            "LA ENTIDAD RATIFICA LA GLOSA.",
            # SO0601: ratificación EXTEMPORÁNEA — debe ir al motor, no al texto fijo.
            "SO0601 - LA EPS RATIFICA LA GLOSA POR FALTA DE EPICRISIS. FECHA RATIFICACION 2026-05-30.",
            "PRIMERA RESPUESTA A LA GLOSA FA0101 POR SOPORTES.",
        ],
    )
    def test_ratifica_a_secas_no_dispara(self, frase):
        assert not R.texto_es_ratificacion(up(frase))


# ─────────────────────────── Caso L: fechas invertidas ───────────────────────────
CASO_L = "FA0201 | HUS0000607777 | SALUD TOTAL. SE FACTURA ESTANCIA. PACIENTE INGRESO EL 25/08/2026 Y FUE DADO DE ALTA EL 20/08/2026. INCONGRUENCIA EN FECHAS. GLOSA TOTAL $500.000."


class TestCasoL_FechasInvertidas:
    def test_detecta_alta_antes_del_ingreso(self):
        r = R.fechas_ingreso_alta_invertidas(up(CASO_L))
        assert r is not None
        ing, alta = r
        assert alta < ing

    def test_fechas_en_orden_no_disparan(self):
        assert R.fechas_ingreso_alta_invertidas(up("INGRESO 20/08/2026 ALTA 25/08/2026")) is None

    def test_mismo_dia_no_dispara(self):
        assert R.fechas_ingreso_alta_invertidas(up("INGRESO 20/08/2026 ALTA 20/08/2026")) is None

    def test_el_dictamen_forzado_reconoce_el_error(self):
        d = R.dictamen_forzado_por_contradiccion(
            up(CASO_L), "FA", "FA0201", "$ 500.000", "SALUD TOTAL"
        )
        assert d and d["tipo"] == "ACEPTADA_FECHA_INVERTIDA"
        assert "20/08/2026" in d["arg"] and "25/08/2026" in d["arg"]
        assert "CIERRE ADMINISTRATIVO" not in d["arg"].upper()


# ─────────────────────────── Caso M: tope SOAT no agotado ───────────────────────────
CASO_M = "CO4601 | HUS0000608888 | EPS SURA. PACIENTE SOAT. SE COBRAN SERVICIOS A LA EPS POR $15.000.000. EL TOPE SOAT (800 SMDLV) SON $34.600.000. LA IPS SOLO DEMUESTRA GASTOS SOAT POR $10.000.000. FALTAN $24.600.000 PARA AGOTAR TOPE. GLOSA $15.000.000."


class TestCasoM_TopeSoatNoAgotado:
    def test_extrae_la_matematica(self):
        d = R.soat_tope_no_agotado(up(CASO_M))
        assert d == {
            "tope": 34600000.0,
            "demostrado": 10000000.0,
            "faltante": 24600000.0,
            "cobrado_eps": 15000000.0,
        }

    def test_no_dispara_en_caso6_sin_numeros(self):
        # El Caso 6 (CO4601) NO trae la matemática del tope: allí se defiende.
        caso6 = up(
            "CO4601 | HUS1 | COOSALUD. NO ACREDITA EL AGOTAMIENTO DE LA COBERTURA DEL SOAT. GLOSA $2.000.000."
        )
        assert R.soat_tope_no_agotado(caso6) is None

    def test_no_dispara_si_el_tope_ya_se_agoto(self):
        # demostrado >= tope: no hay remanente, no aplica esta regla.
        t = up(
            "TOPE SOAT $10.000.000. LA IPS DEMUESTRA GASTOS SOAT POR $12.000.000. SE COBRA A LA EPS $5.000.000."
        )
        assert R.soat_tope_no_agotado(t) is None

    def test_el_dictamen_forzado_acepta_y_cobra_a_la_aseguradora(self):
        d = R.dictamen_forzado_por_contradiccion(
            up(CASO_M), "CO", "CO4601", "$ 15.000.000", "EPS SURA"
        )
        assert d and d["tipo"] == "ACEPTADA_SOAT_REMANENTE" and d["cod"] == "RE9702"
        arg = d["arg"].upper()
        assert "DECRETO 780 DE 2016" in arg
        assert "ASEGURADORA" in arg
        assert "$24.600.000" in arg  # el remanente calculado


# ─────────────────────────── Caso F: objeción documental con código de tarifa ───────────────────────────
CASO_F = "TA0101 | HUS0000601111 | COMPENSAR. GLOSA POR TARIFA. NO SE ADJUNTA LA NOTA QUIRURGICA NI EL RECORD DE ANESTESIA, POR LO TANTO NO SE PUEDE VERIFICAR EL COBRO DEL CIRUJANO. SE GLOSAN $2.500.000."


class TestCasoF_ContradiccionCodigoVsTexto:
    def test_detecta_los_documentos_reclamados(self):
        docs = R.objecion_realmente_documental(up(CASO_F), "TA")
        assert docs == ["la nota operatoria", "el récord de anestesia"]

    def test_una_tarifa_pura_no_se_reclasifica(self):
        assert (
            R.objecion_realmente_documental(up("TA0101 MAYOR VALOR COBRADO SEGUN CONTRATO"), "TA")
            is None
        )

    def test_solo_aplica_a_codigos_de_tarifa(self):
        assert R.objecion_realmente_documental(up(CASO_F), "SO") is None

    def test_el_dictamen_forzado_responde_documental_no_tarifa(self):
        d = R.dictamen_forzado_por_contradiccion(
            up(CASO_F), "TA", "TA0101", "$ 2.500.000", "COMPENSAR"
        )
        assert d and d["tipo"] == "FA_SOPORTES_FORZADO" and d["cod"] == "RE9901"
        arg = d["arg"].upper()
        assert "NOTA OPERATORIA" in arg and "RÉCORD DE ANESTESIA" in arg
        assert "SOAT" not in arg and "UVB" not in arg  # no responde tarifa


# ─────────────────────────── Caso G: ley inventada ───────────────────────────
CASO_G = "CO0302 | HUS0000602222 | SANITAS. SERVICIO NO AUTORIZADO. DE ACUERDO CON EL ARTICULO 99 DE LA RESOLUCION 8888 DE 2025 DEL MINISTERIO, LAS URGENCIAS ODONTOLOGICAS DEBEN SER PREVIAMENTE AUTORIZADAS POR LA EPS. GLOSA $120.000."


class TestCasoG_LeyInventada:
    def test_detecta_la_resolucion_inexistente(self):
        assert "RESOLUCION 8888 DE 2025" in R.normas_inexistentes_citadas(up(CASO_G))

    def test_una_norma_real_no_se_marca(self):
        fuera = R.normas_inexistentes_citadas(
            up("SEGUN LA LEY 100 DE 1993 Y LA RESOLUCION 2284 DE 2023")
        )
        assert fuera == []

    def test_una_norma_del_futuro_se_marca(self):
        assert R.normas_inexistentes_citadas(up("RESOLUCION 12 DE 2099")) == [
            "RESOLUCION 12 DE 2099"
        ]

    def test_el_argumento_pierde_la_discusion_de_la_norma_falsa_y_conserva_la_real(self):
        arg = (
            "SE RECHAZA LA CALIFICACION. LA SUPUESTA EXIGENCIA SE BASA EN EL ARTICULO 99 "
            "DE LA RESOLUCION 8888 DE 2025, EL CUAL NO ES APLICABLE. LAS URGENCIAS NO "
            "REQUIEREN AUTORIZACION PREVIA SEGUN EL ART. 168 DE LA LEY 100 DE 1993."
        )
        limpio, borradas = R.no_legitimar_normas_ajenas(arg, ["RESOLUCION 8888 DE 2025"])
        assert borradas  # se borró la oración que la debatía
        # La oración que la trataba como aplicable ya no está...
        assert "EL CUAL NO ES APLICABLE" not in limpio.upper()
        assert "LA SUPUESTA EXIGENCIA" not in limpio.upper()
        # ...la 8888 solo se nombra para decir que NO existe...
        assert "NO SE ENCUENTRA EN EL ORDENAMIENTO" in limpio.upper()
        # ...y la defensa real (norma vigente) queda intacta.
        assert "LEY 100 DE 1993" in limpio

    def test_sin_normas_falsas_no_toca_nada(self):
        arg = "DEFENSA CON LA LEY 100 DE 1993."
        assert R.no_legitimar_normas_ajenas(arg, []) == (arg, [])


# ─────────────────────────── Caso N: MIPRES obligatorio ───────────────────────────
CASO_N = "FA0102 | HUS0000609999 | ASMET SALUD. SE COBRA RITUXIMAB (CUPS NO POS) POR $4.500.000. NO SE ADJUNTA FORMATO MIPRES GENERADO POR EL MEDICO TRATANTE, SOLO LA FORMULA MANUAL. GLOSA TOTAL."


class TestCasoN_AltoCostoSinMipres:
    def test_detecta_el_requerimiento_de_mipres(self):
        assert R.glosa_exige_mipres(up(CASO_N))

    def test_reconoce_la_evasion_por_devolucion(self):
        assert R.es_evasion_devolucion(
            "DEVOLUCION ADMINISTRATIVA. NO IDENTIFICA EL SERVICIO OBJETADO."
        )
        assert R.es_evasion_devolucion("NO EXISTE EVIDENCIA SUFICIENTE PARA PRONUNCIARSE DE FONDO.")

    def test_una_defensa_normal_no_es_evasion(self):
        assert not R.es_evasion_devolucion("SE APORTA EL FORMATO MIPRES Y LA HISTORIA CLINICA.")

    def test_sin_mipres_el_parrafo_lo_anuncia_como_obligatorio(self):
        p = R.parrafo_mipres(False).upper()
        assert "MIPRES" in p and "OBLIGATORIO" in p and "NO CONSTITUYE DEVOLUCIÓN" in p

    def test_con_mipres_el_parrafo_lo_da_por_aportado(self):
        assert "OBRA ENTRE LOS SOPORTES" in R.parrafo_mipres(True).upper()

    def test_detecta_mipres_en_soportes(self):
        assert R.hay_mipres_en_soportes("═══ DOCUMENTO: mipres_123.pdf ═══")
        assert not R.hay_mipres_en_soportes("═══ DOCUMENTO: factura.pdf ═══")


# ─────────────────────────── el orquestador respeta la prioridad ───────────────────────────
class TestOrquestadorPrioridad:
    def test_una_glosa_normal_no_fuerza_nada(self):
        normal = up(
            "TA0301 | HUS1 | NUEVA EPS. MAYOR VALOR COBRADO SEGUN CONTRATO. GLOSADO $500.000."
        )
        assert (
            R.dictamen_forzado_por_contradiccion(normal, "TA", "TA0301", "$ 500.000", "NUEVA EPS")
            is None
        )

    def test_informativa_gana_sobre_lo_demas(self):
        # $0 glosado manda: aunque haya otras señales, es informativa.
        d = R.dictamen_forzado_por_contradiccion(up(CASO_O), "CO", "CO0000", "$ 0.00", "SANITAS")
        assert d["tipo"] == "INFORMATIVA_CERO"


# ─────────────────────────── integración: el motor completo enruta bien ───────────────────────────
def _preparar_entorno(monkeypatch):
    for v in (
        "QUALITY_GATE_ENABLED",
        "QUALITY_GATE_ROLLOUT_PCT",
        "TOOL_USE_HABILITADO",
        "MULTI_AGENT_HABILITADO",
        "ANTHROPIC_API_KEY",
        "MULTI_CODIGO_DICTAMENES",
    ):
        monkeypatch.delenv(v, raising=False)
    import app.services.dictamen_directo as dd
    import app.services.validador_dictamen as vd

    monkeypatch.setattr(vd, "detectar_defectos_criticos", lambda *a, **k: [])
    monkeypatch.setattr(dd, "puede_emitir_directo", lambda *a, **k: False)


def _stub_ia(monkeypatch, registro: list, argumento: str):
    async def fake(
        self,
        system,
        user,
        eps="",
        codigo="",
        modelo_override=None,
        temperature_override=None,
        bypass_cache=False,
    ):
        registro.append(codigo)
        return (
            f"<paciente>NO IDENTIFICADO</paciente><argumento>{argumento}</argumento>",
            "stub-test",
        )

    monkeypatch.setattr(GlosaService, "_llamar_ia", fake)


def _data(texto: str, eps: str):
    from app.models.schemas import GlosaInput

    return GlosaInput(eps=eps, etapa="RESPUESTA A GLOSA", tabla_excel=texto, valor_aceptado="0")


@pytest.mark.asyncio
class TestEnrutamientoEndToEnd:
    """El camino forzado se arma en el motor completo SIN llamar a la IA, y con
    el código de respuesta correcto. Es lo que prueba que el cableado funciona,
    no solo los helpers sueltos."""

    async def test_O_informativa_no_llama_ia(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        reg = []
        _stub_ia(monkeypatch, reg, "NO DEBERIA USARSE")
        r = await GlosaService(groq_api_key=None).analizar(
            _data(CASO_O, "SANITAS"), contratos_db={}
        )
        assert reg == []  # no se llamó a la IA
        assert "RE9701" in r.tipo
        assert "INFORMATIV" in r.dictamen.upper() and "$0" in r.dictamen

    async def test_I_incoherencia_acepta_sin_ia(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        reg = []
        _stub_ia(monkeypatch, reg, "NO DEBERIA USARSE")
        r = await GlosaService(groq_api_key=None).analizar(
            _data(CASO_I, "FAMISANAR EPS"), contratos_db={}
        )
        assert reg == []
        assert "RE9702" in r.tipo
        assert "ERROR" in r.dictamen.upper() and "NOTA" in r.dictamen.upper()

    async def test_L_fechas_invertidas_reconoce_sin_ia(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        reg = []
        _stub_ia(monkeypatch, reg, "NO DEBERIA USARSE")
        r = await GlosaService(groq_api_key=None).analizar(
            _data(CASO_L, "SALUD TOTAL"), contratos_db={}
        )
        assert reg == []
        assert "RE9702" in r.tipo
        assert "20/08/2026" in r.dictamen and "25/08/2026" in r.dictamen
        assert "CIERRE ADMINISTRATIVO" not in r.dictamen.upper()

    async def test_M_tope_soat_acepta_y_cobra_a_aseguradora_sin_ia(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        reg = []
        _stub_ia(monkeypatch, reg, "NO DEBERIA USARSE")
        r = await GlosaService(groq_api_key=None).analizar(
            _data(CASO_M, "EPS SURA"), contratos_db={}
        )
        assert reg == []
        assert "RE9702" in r.tipo
        assert "DECRETO 780 DE 2016" in r.dictamen.upper() and "ASEGURADORA" in r.dictamen.upper()

    async def test_F_documental_pese_a_codigo_tarifa_sin_ia(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        reg = []
        _stub_ia(monkeypatch, reg, "NO DEBERIA USARSE")
        r = await GlosaService(groq_api_key=None).analizar(
            _data(CASO_F, "COMPENSAR"), contratos_db={}
        )
        assert reg == []
        assert "RE9901" in r.tipo
        # Responde por los soportes, no por tarifa (SOAT/UVB).
        assert "NOTA OPERATORIA" in r.dictamen.upper()
        assert "UVB" not in r.dictamen.upper()

    async def test_H_el_motor_objeta_el_25_por_ciento_no_el_total(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        reg = []
        _stub_ia(monkeypatch, reg, "DEFENSA CUALQUIERA.")
        r = await GlosaService(groq_api_key=None).analizar(
            _data(CASO_H, "NUEVA EPS"), contratos_db={}
        )
        assert r.valor_objetado == "$ 2.500.000"

    async def test_J_ratificacion_en_texto_va_por_conciliacion_sin_ia(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        reg = []
        _stub_ia(monkeypatch, reg, "NO DEBERIA USARSE")
        caso_j = "FA0101 | HUS0000605555 | COOSALUD. RESPUESTA A CONCILIACION. LA IPS APORTO LOS SOPORTES PERO SIGUEN ILEGIBLES. SE RATIFICA LA GLOSA INICIAL POR $800.000."
        r = await GlosaService(groq_api_key=None).analizar(
            _data(up(caso_j), "COOSALUD"), contratos_db={}
        )
        assert reg == []
        assert "CONCILIA" in r.dictamen.upper() or "RATIFICA" in r.dictamen.upper()

    async def test_N_mipres_reemplaza_la_evasion_por_devolucion(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        reg = []
        _stub_ia(
            monkeypatch,
            reg,
            "DEVOLUCION ADMINISTRATIVA. NO EXISTE EVIDENCIA SUFICIENTE PARA PRONUNCIARSE DE FONDO. LA GLOSA NO IDENTIFICA EL SERVICIO OBJETADO.",
        )
        r = await GlosaService(groq_api_key=None).analizar(
            _data(CASO_N, "ASMET SALUD"), contratos_db={}
        )
        assert reg  # la IA sí se llamó (camino LLM)
        assert "MIPRES" in r.dictamen.upper()
        assert "NO EXISTE EVIDENCIA SUFICIENTE" not in r.dictamen.upper()
