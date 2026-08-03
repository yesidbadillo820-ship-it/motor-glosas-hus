"""Tests de los 9 fixes de la evaluación de estrés ronda-2 (12-jun-2026).

Cada clase cubre UN fix usando los textos de evidencia REALES de la
evaluación (glosas sintéticas del dueño — sin datos de pacientes):

  1. Sección AU del multi-código asumía "urgencias" en procedimientos
     programados (cláusula anti-rebatimiento contaminada).
  2. Cita literal FALSA marcada ALTA llegaba ENTREGADA al usuario — red
     final "descomillar citas ALTA".
  3. CONTRATO CRUZADO entre EPS (DMBUG citando el contrato de FAMISANAR).
  4. Datos clínicos del enunciado ignorados (NYHA III, FE 25%, 47 días UCI).
  5. Extemporaneidad de RATIFICACIÓN con fechas EN EL TEXTO no detectada.
  6. Placeholders crudos "[ENTIDAD] / [VALOR REAL] / [CODIGO]" en el output.
  7. Números deletreados en palabras → $0.00.
  8. Fecha/factura tomada como CUPS ("CUPS 2026-04", "CUPS HUS0000522871").
  9. gpt-oss-120b (RAZONADOR) agotaba max_tokens=3000 en chain-of-thought →
     content vacío con finish_reason='length' → fallback a qwen innecesario.
     Evidencia: log [GROQ-FALLBACK] de prod 12-jun 19:37 UTC (auto-crítica).
"""

from __future__ import annotations

import logging
import uuid
from unittest.mock import AsyncMock

import pytest

# ════════════════════════════════════════════════════════════════════
# FIX 1 — Sección AU: urgencias solo si consta; electivo → silencio
# administrativo positivo. Evidencia real: glosa multi-código con AU0301
# de procedimiento PROGRAMADO salió con "LA ATENCIÓN DE URGENCIAS, COMO
# LA PRESTADA, NO REQUIERE AUTORIZACIÓN PREVIA".
# ════════════════════════════════════════════════════════════════════

EVIDENCIA_AU_PROGRAMADO = (
    "TA0201, SO0601, AU0301 - SE GLOSA MAYOR VALOR COBRADO, FALTA DE EPICRISIS "
    "Y FALTA DE AUTORIZACION PREVIA PARA PROCEDIMIENTO PROGRAMADO DE "
    "ARTROPLASTIA DE RODILLA. VALOR OBJETADO $4.850.000"
)

_CLAUSULA_URGENCIAS_AU = (
    "LA AUTORIZACIÓN PREVIA NO CONSTITUYE REQUISITO LEGAL EN LA ATENCIÓN DE URGENCIAS"
)


class TestFix1SeccionAUMultiCodigo:
    def test_clausula_au_programado_no_inyecta_urgencias(self):
        """Causa raíz: clausulas_anti_rebatimiento inyectaba SIEMPRE la
        cláusula de urgencias para AU — la IA la copiaba en electivos."""
        from app.services.clausulas_anti_rebatimiento import clausulas_para_codigo

        cls = clausulas_para_codigo("AU0301", 2, texto_glosa=EVIDENCIA_AU_PROGRAMADO)
        assert cls, "AU debe seguir recibiendo cláusulas anti-rebatimiento"
        for c in cls:
            assert "URGENCIA" not in c.upper(), f"cláusula de urgencias en electivo: {c}"
        assert any("SILENCIO ADMINISTRATIVO POSITIVO" in c for c in cls)

    def test_clausula_au_urgencias_reales_si_inyecta(self):
        """Caso A del SYSTEM_AU: urgencias consta → la cláusula clásica vive."""
        from app.services.clausulas_anti_rebatimiento import clausulas_para_codigo

        cls = clausulas_para_codigo(
            "AU0301",
            2,
            texto_glosa="AU0301 ATENCION DE URGENCIAS TRIAGE I SIN AUTORIZACION PREVIA",
        )
        assert any(_CLAUSULA_URGENCIAS_AU in c for c in cls)

    def test_clausula_au_sin_texto_es_conservadora(self):
        """Supuesto desconocido (texto vacío) → PROHIBIDO afirmar urgencias."""
        from app.services.clausulas_anti_rebatimiento import clausulas_para_codigo

        cls = clausulas_para_codigo("AU0301", 2)
        for c in cls:
            assert "URGENCIA" not in c.upper()

    def test_user_prompt_seccion_au_secundaria_bifurcado(self):
        """El prompt de la sección AU secundaria (mismo build que usa
        multi_codigo._generar_seccion_codigo) debe llevar el texto COMPLETO
        de la glosa en el BLOQUE 3 y NO la cláusula de urgencias."""
        from app.services.glosa_ia_prompts import build_user_prompt
        from app.services.multi_codigo import construir_bloque_instruccion_adicional

        user_prompt = build_user_prompt(
            texto_glosa=EVIDENCIA_AU_PROGRAMADO,
            contexto_pdf="",
            codigo="AU0301",
            eps="NUEVA EPS",
            valor_objetado="$4.850.000",
        ) + construir_bloque_instruccion_adicional(
            codigo="AU0301",
            codigo_principal="TA0201",
            todos_los_codigos=["TA0201", "SO0601", "AU0301"],
            valor_objetado="$4.850.000",
        )
        # El texto de la glosa llega completo para evaluar el supuesto
        assert "PROCEDIMIENTO PROGRAMADO" in user_prompt
        # La cláusula contaminante de urgencias NO viaja en el prompt
        assert _CLAUSULA_URGENCIAS_AU not in user_prompt
        assert "SILENCIO ADMINISTRATIVO POSITIVO" in user_prompt

    def test_system_au_secundario_conserva_bifurcacion(self):
        """get_system_prompt (lo que usa multi_codigo) trae la bifurcación
        del PR #103: caso A urgencias-si-consta / caso B electivo."""
        from app.services.glosa_ia_prompts import get_system_prompt

        sp = get_system_prompt(prefijo="AU", eps="NUEVA EPS")
        assert "SI NO CONSTA que fue urgencias" in sp
        assert "SILENCIO" in sp.upper()
        assert "NUNCA describas el servicio como" in sp

    @pytest.mark.asyncio
    async def test_generar_seccion_au_end_to_end(self, monkeypatch):
        """End-to-end de la sección AU secundaria REAL de multi_codigo:
        se stubea el QG para capturar los prompts que recibiría la IA y se
        verifica que llegan bifurcados y sin la cláusula de urgencias."""
        import app.services.multi_codigo as mc

        capturado: dict = {}

        async def fake_qg(**kwargs):
            capturado["system"] = kwargs["system_prompt"]
            capturado["user"] = kwargs["user_prompt"]

            class R:
                estado = "APROBADO"
                dictamen_final = (
                    "ESE HUS NO ACEPTA LA GLOSA POR AUTORIZACIÓN. "
                    "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
                )
                score_final = 90
                modelo_final = "stub"

            return R()

        monkeypatch.setattr(mc, "ejecutar_con_quality_gate", fake_qg)
        seccion = await mc._generar_seccion_codigo(
            servicio=object(),
            codigo="AU0301",
            codigo_principal="TA0201",
            todos_los_codigos=["TA0201", "SO0601", "AU0301"],
            texto_glosa=EVIDENCIA_AU_PROGRAMADO,
            eps="NUEVA EPS",
            valor_objetado="$4.850.000",
            contexto_pdf="",
            numero_factura=None,
            numero_radicado=None,
            dias_habiles=5,
            es_extemporanea=False,
            es_ratificacion=False,
            tono="conciliador",
            proveedores_disponibles={"groq"},
        )
        assert seccion and "AU0301" in seccion
        # SYSTEM bifurcado (PR #103) llega a la sección secundaria
        assert "SI NO CONSTA que fue urgencias" in capturado["system"]
        # El texto de la glosa llega COMPLETO (BLOQUE 3) para evaluar el supuesto
        assert "PROCEDIMIENTO PROGRAMADO" in capturado["user"]
        # La cláusula contaminante de urgencias ya no viaja
        assert _CLAUSULA_URGENCIAS_AU not in capturado["user"]
        assert "SILENCIO ADMINISTRATIVO POSITIVO" in capturado["user"]


# ════════════════════════════════════════════════════════════════════
# FIX 2 — Cita ALTA del verifier: red final "descomillar citas ALTA".
# Evidencia real: caso osteosíntesis ENTREGADO con «El pagador reconocerá
# la factura dentro de los veintidós (22) días hábiles...» marcada
# CITA_LITERAL_FALSA ALTA.
# ════════════════════════════════════════════════════════════════════

CITA_FALSA_OSTEOSINTESIS = (
    "EL PAGADOR RECONOCERÁ LA FACTURA DENTRO DE LOS VEINTIDÓS (22) DÍAS "
    "HÁBILES SIGUIENTES A SU RADICACIÓN"
)

DICTAMEN_OSTEOSINTESIS = (
    "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE FACTURACIÓN SOBRE EL CÓDIGO "
    "FA0801 RESPECTO DEL MATERIAL DE OSTEOSÍNTESIS. EL CONTRATO ESTABLECE "
    f"TEXTUALMENTE: «{CITA_FALSA_OSTEOSINTESIS}». "
    "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
)


class TestFix2DescomillarCitasFalsas:
    def _issue(self, cita: str) -> dict:
        # Mismo formato que produce citation_verifier.verificar_citas
        recortada = cita[:140] + "..." if len(cita) > 140 else cita
        return {
            "tipo": "CITA_LITERAL_FALSA",
            "severidad": "ALTA",
            "cita": f"«{recortada}»",
            "detalle": "no está en el corpus",
        }

    def test_descomilla_la_cita_falsa_evidencia(self):
        from app.services.glosa_service import _descomillar_citas_falsas

        out = _descomillar_citas_falsas(
            DICTAMEN_OSTEOSINTESIS, [self._issue(CITA_FALSA_OSTEOSINTESIS)]
        )
        assert "«" not in out and "»" not in out
        assert f"EN LOS TÉRMINOS DE {CITA_FALSA_OSTEOSINTESIS}" in out
        # El cierre canónico sobrevive
        assert "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA." in out

    def test_cita_truncada_a_140_chars_tambien_matchea(self):
        """El issue trae la cita recortada con '...' — la huella por prefijo
        normalizado debe encontrar el span completo igual."""
        from app.services.glosa_service import _descomillar_citas_falsas

        cita_larga = CITA_FALSA_OSTEOSINTESIS + ", PREVIA VERIFICACIÓN DE LOS SOPORTES " * 4
        dictamen = f"EL CONTRATO DISPONE: «{cita_larga}». SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        out = _descomillar_citas_falsas(dictamen, [self._issue(cita_larga)])
        assert "«" not in out
        assert "EN LOS TÉRMINOS DE" in out

    def test_citas_validas_no_se_tocan(self):
        from app.services.glosa_service import _descomillar_citas_falsas

        valida = "«LA HISTORIA CLÍNICA ES UN DOCUMENTO PRIVADO SOMETIDO A RESERVA QUE ACREDITA LA ATENCIÓN»"
        dictamen = f"CITA VERIFICADA {valida}. {DICTAMEN_OSTEOSINTESIS}"
        out = _descomillar_citas_falsas(dictamen, [self._issue(CITA_FALSA_OSTEOSINTESIS)])
        assert valida in out, "una cita NO marcada por el verifier jamás se altera"
        assert CITA_FALSA_OSTEOSINTESIS in out
        assert f"«{CITA_FALSA_OSTEOSINTESIS}»" not in out

    def test_sin_issues_devuelve_intacto(self):
        from app.services.glosa_service import _descomillar_citas_falsas

        assert _descomillar_citas_falsas(DICTAMEN_OSTEOSINTESIS, []) == DICTAMEN_OSTEOSINTESIS
        assert _descomillar_citas_falsas(DICTAMEN_OSTEOSINTESIS, None) == DICTAMEN_OSTEOSINTESIS

    def test_comillas_dobles_atribuidas_tambien(self):
        from app.services.glosa_service import _descomillar_citas_falsas

        dictamen = (
            'LA CLÁUSULA CUARTA ESTABLECE QUE: "'
            + CITA_FALSA_OSTEOSINTESIS
            + '". SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA.'
        )
        out = _descomillar_citas_falsas(dictamen, [self._issue(CITA_FALSA_OSTEOSINTESIS)])
        assert '"' not in out
        assert "EN LOS TÉRMINOS DE" in out

    def test_round_trip_con_verifier_real(self):
        """Integración con el corpus real: el verifier marca la cita
        inventada → el sanitizer la descomilla → re-verificar ya no
        encuentra CITA_LITERAL_FALSA."""
        from app.services.citation_verifier import verificar_citas
        from app.services.glosa_service import _descomillar_citas_falsas

        rep = verificar_citas(DICTAMEN_OSTEOSINTESIS, eps="NUEVA EPS")
        falsas = [i for i in rep["issues"] if i["tipo"] == "CITA_LITERAL_FALSA"]
        assert falsas, "precondición: el corpus real debe marcar la cita como falsa"

        limpio = _descomillar_citas_falsas(DICTAMEN_OSTEOSINTESIS, rep["issues"])
        rep2 = verificar_citas(limpio, eps="NUEVA EPS")
        assert not any(i["tipo"] == "CITA_LITERAL_FALSA" for i in rep2["issues"])

    @pytest.mark.asyncio
    async def test_analizar_nunca_entrega_cita_falsa_textual(self, monkeypatch):
        """End-to-end del camino legacy (QG OFF — la causa (a) del leak):
        la IA devuelve la cita inventada y el dictamen FINAL sale sin las
        comillas, con la paráfrasis neutra."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        monkeypatch.delenv("TOOL_USE_HABILITADO", raising=False)
        from app.services.glosa_service import GlosaService
        from app.models.schemas import GlosaInput

        servicio = GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")
        respuesta_ia = (
            "<argumento>ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE FACTURACIÓN "
            "SOBRE EL CÓDIGO FA0801 RESPECTO DEL MATERIAL DE OSTEOSÍNTESIS. "
            f"EL CONTRATO ESTABLECE TEXTUALMENTE: «{CITA_FALSA_OSTEOSINTESIS}». "
            "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA.</argumento>"
        )
        monkeypatch.setattr(
            GlosaService,
            "_llamar_ia",
            AsyncMock(return_value=(respuesta_ia, "stub")),
        )
        data = GlosaInput(
            eps="NUEVA EPS",
            etapa="RESPUESTA A GLOSA",
            tabla_excel=(
                "FA0801 - MATERIAL DE OSTEOSÍNTESIS INCLUIDO EN DERECHOS DE SALA. "
                "VALOR OBJETADO $2.480.000"
            ),
            valor_aceptado="0",
        )
        resultado = await servicio.analizar(data, contratos_db={})
        assert f"«{CITA_FALSA_OSTEOSINTESIS}»" not in resultado.dictamen
        # Ronda 17 (26-jun-2026): la frase neutra "en los términos de" se
        # normaliza a sentence case por _normalizar_mayusculas_sostenidas
        # aplicado a arg_ia antes del HTML wrap (Bug L ronda 14 reforzado).
        # Antes el assert pedía "EN LOS TÉRMINOS DE" en MAYÚSCULAS sostenidas;
        # el comportamiento institucional ahora es sentence case para
        # darle pinta profesional al dictamen.
        assert "en los términos de" in resultado.dictamen.lower()
        if resultado.verificacion_citas:
            assert not any(
                i["tipo"] == "CITA_LITERAL_FALSA"
                for i in resultado.verificacion_citas.get("issues", [])
            )


# ════════════════════════════════════════════════════════════════════
# FIX 3 — CONTRATO CRUZADO entre EPS (el más grave: 3 casos).
# Evidencia real: glosa DMBUG citó "CONTRATO S-13-1-03-1-04958" (de
# FAMISANAR); glosa "OTRA / SIN DEFINIR" citó "Cláusula 4.2 del CONTRATO
# S-13-1-03-1-04958"; glosa FOMAG mezcló cláusulas de actas ajenas.
# ════════════════════════════════════════════════════════════════════


class TestFix3ContratoCruzado:
    def test_get_contrato_eps_vacia_no_devuelve_famisanar(self):
        """Causa raíz capa (i): `"" in "FAMISANAR"` era True → eps vacía
        heredaba el PRIMER contrato del catálogo."""
        from app.services.glosa_ia_prompts import get_contrato

        for eps in ("", "  ", "OTRA / SIN DEFINIR", "OTRA", "SIN DEFINIR", "N/A"):
            c = get_contrato(eps)
            assert c["numero"] == "SIN CONTRATO PACTADO", f"eps={eps!r} → {c['numero']}"

    def test_get_contrato_substring_corto_no_matchea(self):
        from app.services.glosa_ia_prompts import get_contrato

        # "EPS" estaba contenido en "NUEVA EPS" y "SA" en "FAMISANAR"
        assert get_contrato("EPS")["numero"] == "SIN CONTRATO PACTADO"
        assert get_contrato("SA")["numero"] == "SIN CONTRATO PACTADO"

    def test_get_contrato_matches_legitimos_siguen(self):
        """Con fecha del hecho FIJA: sin fecha, get_contrato usa "hoy" y la
        prueba se volvía bomba de tiempo — reventó el 01-08-2026 cuando venció
        la vigencia del contrato DMBUG (Dic 2025 – Jul 2026), sin que ningún
        código hubiera cambiado. Lo que se prueba aquí es el MATCH del nombre,
        no la vigencia, así que se ancla a un día en que todos regían."""
        import datetime

        from app.services.glosa_ia_prompts import get_contrato

        dia = datetime.date(2026, 6, 15)
        assert "S-13-1-03-1-04958" in get_contrato("FAMISANAR EPS", fecha_hecho=dia)["numero"]
        assert "DMBUG" in get_contrato("DISPENSARIO MEDICO BUCARAMANGA", fecha_hecho=dia)["numero"]
        assert "12076-359-2025" in get_contrato("FOMAG", fecha_hecho=dia)["numero"]
        assert "IPS-001B-2022" in get_contrato("PPL", fecha_hecho=dia)["numero"]

    def test_catalogo_contrato_eps_duena(self):
        from app.services.glosa_ia_prompts import catalogo_contratos_eps

        cat = catalogo_contratos_eps()
        assert cat["S-13-1-03-1-04958"] == "FAMISANAR"
        assert cat["440-DIGSA/DMBUG-2025"] == "DISPENSARIO MEDICO"
        assert cat["12076-359-2025"] == "FOMAG"

    def test_contratos_ajenos_evidencia_dmbug(self):
        """Evidencia 1: glosa DMBUG citando el contrato de FAMISANAR."""
        from app.services.glosa_ia_prompts import contratos_ajenos_citados

        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA. CONFORME AL CONTRATO S-13-1-03-1-04958 "
            "VIGENTE, LA TARIFA PACTADA ES SOAT -5%."
        )
        ajenos = contratos_ajenos_citados(dictamen, "DISPENSARIO MEDICO BUCARAMANGA")
        assert ajenos == ["S-13-1-03-1-04958"]

    def test_contratos_ajenos_evidencia_otra_sin_definir(self):
        """Evidencia 2: EPS 'OTRA / SIN DEFINIR' citando la Cláusula 4.2
        del contrato de FAMISANAR — sin entidad, TODO contrato es ajeno."""
        from app.services.glosa_ia_prompts import contratos_ajenos_citados

        dictamen = "SEGÚN LA CLÁUSULA 4.2 DEL CONTRATO S-13-1-03-1-04958 LA TARIFA APLICABLE..."
        assert contratos_ajenos_citados(dictamen, "OTRA / SIN DEFINIR") == ["S-13-1-03-1-04958"]

    def test_contrato_propio_no_es_ajeno(self):
        """Evidencia 3 (FOMAG): citar el contrato PROPIO 12076-359-2025 es
        correcto — solo las cláusulas/contratos ajenos disparan."""
        from app.services.glosa_ia_prompts import contratos_ajenos_citados

        dictamen = "EN EJECUCIÓN DEL CONTRATO NO. 12076-359-2025 SUSCRITO CON EL FOMAG"
        assert contratos_ajenos_citados(dictamen, "FOMAG") == []
        # Pero el contrato del DMBUG citado por FOMAG sí es ajeno
        dictamen2 = dictamen + " Y EL CONTRATO No. 440-DIGSA/DMBUG-2025"
        assert contratos_ajenos_citados(dictamen2, "FOMAG") == ["440-DIGSA/DMBUG-2025"]

    def test_check_post_validator_contrato_otra_eps_es_grave(self):
        """Capa (ii): el check nuevo marca ERROR (cuenta para regenerar)."""
        from app.services.quality_gate.post_validator import (
            check_contrato_de_otra_eps,
            post_validar_dictamen,
        )

        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE TARIFAS. " * 6
            + "CONFORME AL CONTRATO S-13-1-03-1-04958 VIGENTE. "
            + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        )
        chk = check_contrato_de_otra_eps(dictamen, "DISPENSARIO MEDICO BUCARAMANGA")
        assert not chk.ok and chk.severidad == "ERROR"

        # En el pipeline completo: NO aprobado → debe_regenerar (el número
        # viene "del input" así que contratos_fabricados NO lo habría cazado)
        r = post_validar_dictamen(
            dictamen,
            eps="DISPENSARIO MEDICO BUCARAMANGA",
            texto_glosa_input="TA0201 MAYOR VALOR COBRADO CONTRATO S-13-1-03-1-04958",
        )
        assert not r.checks["contrato_otra_eps"].ok
        assert not r.aprobado and r.debe_regenerar

    def test_check_contrato_propio_pasa(self):
        from app.services.quality_gate.post_validator import check_contrato_de_otra_eps

        dictamen = "CONFORME AL CONTRATO S-13-1-03-1-04958 VIGENTE CON FAMISANAR"
        assert check_contrato_de_otra_eps(dictamen, "FAMISANAR EPS").ok

    def test_build_user_prompt_otra_sin_definir_instruye_no_citar(self):
        from app.services.glosa_ia_prompts import build_user_prompt

        p = build_user_prompt(
            texto_glosa="TA0201 MAYOR VALOR COBRADO EN CONSULTA",
            contexto_pdf="",
            codigo="TA0201",
            eps="OTRA / SIN DEFINIR",
        )
        assert "NO cites números de contrato" in p
        assert "S-13-1-03-1-04958" not in p

    def test_few_shot_con_contrato_ajeno_se_filtra(self):
        from app.services.few_shot_gold import _contiene_contrato_ajeno

        plantilla = (
            "ESE HUS NO ACEPTA GLOSA. CONFORME AL CONTRATO S-13-1-03-1-04958 "
            "LA TARIFA PACTADA ES SOAT UVB VIGENTE -5%..."
        )
        assert _contiene_contrato_ajeno(plantilla, "DISPENSARIO MEDICO BUCARAMANGA")
        assert not _contiene_contrato_ajeno(plantilla, "FAMISANAR EPS")


# ════════════════════════════════════════════════════════════════════
# FIX 4 — Datos clínicos del enunciado ignorados.
# Evidencia real: "NYHA III, FE 25%, en lista de trasplante" / "47 días
# UCI por TCE severo" / "Kellgren IV" — ningún dictamen los mencionó.
# ════════════════════════════════════════════════════════════════════

EVIDENCIA_NYHA = (
    "CL0301 - SE GLOSA PERTINENCIA DEL CATETERISMO. PACIENTE CON FALLA "
    "CARDIACA NYHA III, FE 25%, EN LISTA DE TRASPLANTE CARDIACO"
)
EVIDENCIA_UCI = "SO0601 - SE OBJETA ESTANCIA PROLONGADA: 47 DIAS UCI POR TCE SEVERO"
EVIDENCIA_KELLGREN = "CL0301 - GONARTROSIS KELLGREN IV, SE GLOSA PERTINENCIA DE ARTROPLASTIA"


class TestFix4DatosClinicos:
    def test_extractor_evidencia_nyha(self):
        from app.services.contexto_contractual_enriquecido import extraer_datos_clinicos

        datos = extraer_datos_clinicos(EVIDENCIA_NYHA)
        assert "NYHA III" in datos
        assert "FE 25%" in datos
        assert "LISTA DE TRASPLANTE" in datos

    def test_extractor_evidencia_uci(self):
        from app.services.contexto_contractual_enriquecido import extraer_datos_clinicos

        datos = extraer_datos_clinicos(EVIDENCIA_UCI)
        assert "47 DIAS UCI" in datos
        assert "TCE SEVERO" in datos

    def test_extractor_evidencia_kellgren(self):
        from app.services.contexto_contractual_enriquecido import extraer_datos_clinicos

        assert extraer_datos_clinicos(EVIDENCIA_KELLGREN) == ["KELLGREN IV"]

    def test_extractor_sin_datos_clinicos(self):
        from app.services.contexto_contractual_enriquecido import extraer_datos_clinicos

        assert extraer_datos_clinicos("TA0201 MAYOR VALOR COBRADO SOAT UVB") == []
        assert extraer_datos_clinicos("") == []

    def test_user_prompt_inyecta_bloque_imperativo(self):
        from app.services.glosa_ia_prompts import build_user_prompt

        p = build_user_prompt(
            texto_glosa=EVIDENCIA_NYHA, contexto_pdf="", codigo="CL0301", eps="NUEVA EPS"
        )
        assert "[DATOS CLÍNICOS DEL CASO — ÚSALOS EN LA ARGUMENTACIÓN]" in p
        assert "NYHA III" in p and "FE 25%" in p

    def test_system_base_tiene_regla_imperativa(self):
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        assert "DATOS CLÍNICOS DEL CASO" in SYSTEM_BASE
        assert "INCORPÓRALOS LITERALMENTE" in SYSTEM_BASE

    def test_post_validator_warn_si_ignora_datos(self):
        """≥2 datos en la glosa y NINGUNO en el dictamen → issue MEDIA
        (WARN): baja score pero NO bloquea sola."""
        from app.services.quality_gate.post_validator import post_validar_dictamen

        dictamen_plantilla = (
            "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE PERTINENCIA CLÍNICA. " * 5
            + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        )
        r = post_validar_dictamen(
            dictamen_plantilla, eps="NUEVA EPS", texto_glosa_input=EVIDENCIA_NYHA
        )
        chk = r.checks["datos_clinicos"]
        assert not chk.ok and chk.severidad == "WARN"
        assert "ignora los datos clínicos" in chk.razon
        assert r.aprobado, "el check es suave: no bloquea por sí solo"
        assert r.score < 100

    def test_post_validator_ok_si_los_usa(self):
        from app.services.quality_gate.post_validator import post_validar_dictamen

        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA: EL PACIENTE CURSA FALLA CARDIACA NYHA III "
            "CON FE 25% Y SE ENCUENTRA EN LISTA DE TRASPLANTE, LO QUE ACREDITA LA "
            "PERTINENCIA DEL CATETERISMO. " * 3 + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        )
        r = post_validar_dictamen(dictamen, eps="NUEVA EPS", texto_glosa_input=EVIDENCIA_NYHA)
        assert r.checks["datos_clinicos"].ok

    def test_post_validator_no_aplica_con_un_solo_dato(self):
        from app.services.quality_gate.post_validator import post_validar_dictamen

        r = post_validar_dictamen(
            "ESE HUS NO ACEPTA LA GLOSA POR PERTINENCIA. " * 6
            + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA.",
            eps="NUEVA EPS",
            texto_glosa_input=EVIDENCIA_KELLGREN,  # 1 solo dato
        )
        assert r.checks["datos_clinicos"].ok


# ════════════════════════════════════════════════════════════════════
# FIX 5 — Extemporaneidad de RATIFICACIÓN con fechas EN EL TEXTO.
# Evidencia real: "Fecha radicación: 2026-03-01. Fecha recepción
# ratificación: 2026-05-30" (≈62 días hábiles) sin mención en el dictamen.
# ════════════════════════════════════════════════════════════════════

EVIDENCIA_RATIFICACION = (
    "SO0601 - LA EPS RATIFICA LA GLOSA POR FALTA DE EPICRISIS. "
    "FECHA RADICACIÓN: 2026-03-01. FECHA RECEPCIÓN RATIFICACIÓN: 2026-05-30. "
    "VALOR OBJETADO $1.350.000"
)


class TestFix5ExtemporaneidadRatificacion:
    def test_detector_fechas_evidencia(self):
        from app.services.glosa_service import detectar_fechas_en_texto

        f = detectar_fechas_en_texto(EVIDENCIA_RATIFICACION)
        assert f["fecha_radicacion"] == "2026-03-01"
        assert f["fecha_ratificacion"] == "2026-05-30"

    def test_detector_formato_colombiano(self):
        from app.services.glosa_service import detectar_fechas_en_texto

        f = detectar_fechas_en_texto(
            "RADICACION DE LA FACTURA: 01/03/2026 — NOTIFICACION DE LA RATIFICACION: 30/05/2026"
        )
        assert f == {"fecha_radicacion": "2026-03-01", "fecha_ratificacion": "2026-05-30"}

    def test_detector_sin_etiquetas_no_dispara(self):
        """Fechas sueltas sin etiqueta radicación/ratificación → nada (el
        detector NO debe adivinar pares de fechas arbitrarios)."""
        from app.services.glosa_service import detectar_fechas_en_texto

        f = detectar_fechas_en_texto("ATENCION DEL 2026-03-01 AL 2026-05-30 EN UCI")
        assert f == {"fecha_radicacion": None, "fecha_ratificacion": None}

    def test_dias_habiles_superan_limite(self):
        from app.services.glosa_service import (
            DIAS_HABILES_LIMITE_RATIFICACION,
            GlosaService,
        )

        svc = GlosaService.__new__(GlosaService)
        dias = svc._calcular_dias_habiles("2026-03-01", "2026-05-30")
        assert dias is not None and dias > DIAS_HABILES_LIMITE_RATIFICACION

    @pytest.mark.asyncio
    async def test_analizar_inyecta_bloque_prioritario_al_prompt(self, monkeypatch):
        """Integración: el user prompt que recibe la IA lleva el bloque
        [EXTEMPORANEIDAD DETECTADA — ARGUMENTO PRIORITARIO] con los días."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        monkeypatch.delenv("TOOL_USE_HABILITADO", raising=False)
        from app.services.glosa_service import GlosaService
        from app.models.schemas import GlosaInput

        servicio = GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")
        prompts_capturados: list[str] = []

        async def fake_llamar_ia(self, system, user, **kwargs):
            prompts_capturados.append(user)
            return (
                "<argumento>ESE HUS NO ACEPTA LA GLOSA RATIFICADA POR SOPORTES. " * 4
                + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA.</argumento>",
                "stub",
            )

        monkeypatch.setattr(GlosaService, "_llamar_ia", fake_llamar_ia)
        data = GlosaInput(
            eps="NUEVA EPS",
            etapa="RESPUESTA A GLOSA",
            tabla_excel=EVIDENCIA_RATIFICACION,
            valor_aceptado="0",
        )
        await servicio.analizar(data, contratos_db={})
        assert prompts_capturados, "la IA debió ser llamada por el camino legacy"
        primer_prompt = prompts_capturados[0]
        # Ronda 7 (16-jun-2026): el bloque se renombró y se prepende al
        # inicio del prompt — basta con que las señales clave aparezcan.
        assert "EXTEMPORANEIDAD DETECTADA" in primer_prompt
        assert "Art. 57 de la Ley 1438 de 2011" in primer_prompt
        assert "2026-03-01" in primer_prompt and "2026-05-30" in primer_prompt

    @pytest.mark.asyncio
    async def test_analizar_sin_fechas_no_inyecta(self, monkeypatch):
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        monkeypatch.delenv("TOOL_USE_HABILITADO", raising=False)
        from app.services.glosa_service import GlosaService
        from app.models.schemas import GlosaInput

        servicio = GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")
        prompts_capturados: list[str] = []

        async def fake_llamar_ia(self, system, user, **kwargs):
            prompts_capturados.append(user)
            return (
                "<argumento>ESE HUS NO ACEPTA LA GLOSA POR SOPORTES. " * 4
                + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA.</argumento>",
                "stub",
            )

        monkeypatch.setattr(GlosaService, "_llamar_ia", fake_llamar_ia)
        data = GlosaInput(
            eps="NUEVA EPS",
            etapa="RESPUESTA A GLOSA",
            tabla_excel="SO0601 - FALTA DE EPICRISIS EN LA FACTURA. VALOR $1.350.000",
            valor_aceptado="0",
        )
        await servicio.analizar(data, contratos_db={})
        assert prompts_capturados
        assert "[EXTEMPORANEIDAD DETECTADA" not in prompts_capturados[0]


# ════════════════════════════════════════════════════════════════════
# FIX 6 — Placeholders crudos en el output.
# Evidencia real: dictamen entregado con "INTERPUESTA POR [ENTIDAD],
# RESPECTO DE LA PRESCRIPCIÓN Y EJECUCIÓN DEL [SERVICIO] FACTURADO POR
# [VALOR REAL]... LA GLOSA [CODIGO]".
# ════════════════════════════════════════════════════════════════════

EVIDENCIA_PLACEHOLDERS = (
    "INTERPUESTA POR [ENTIDAD], RESPECTO DE LA PRESCRIPCIÓN Y EJECUCIÓN DEL "
    "[SERVICIO] FACTURADO POR [VALOR REAL]. NO ES PROCEDENTE LA GLOSA [CODIGO]."
)


class TestFix6PlaceholdersCrudos:
    def test_sanitizer_rellena_evidencia(self):
        from app.services.glosa_service import _rellenar_placeholders

        out = _rellenar_placeholders(
            EVIDENCIA_PLACEHOLDERS,
            eps="SALUD MIA",
            codigo="ME0801",
            valor="$ 1.250.000",
        )
        assert "[" not in out and "]" not in out
        assert "SALUD MIA" in out
        assert "ME0801" in out
        assert "$ 1.250.000" in out
        assert "SERVICIO FACTURADO" in out
        # Sin artefactos gramaticales del reemplazo
        assert "DEL EL " not in out
        assert "FACTURADO FACTURADO" not in out

    def test_sanitizer_sin_datos_usa_frases_neutras(self):
        from app.services.glosa_service import _rellenar_placeholders

        out = _rellenar_placeholders(EVIDENCIA_PLACEHOLDERS, eps="", codigo="N/A", valor="$ 0.00")
        assert "[" not in out
        assert "LA ENTIDAD PAGADORA" in out
        assert "EL VALOR INDICADO EN EL EXPEDIENTE" in out

    def test_sanitizer_no_toca_sic_minusculas(self):
        from app.services.glosa_service import _rellenar_placeholders

        texto = "LA EPS AFIRMÓ 'no se adjuntó historia clinica [sic]' EN SU GLOSA"
        assert _rellenar_placeholders(texto, eps="X", codigo="SO0601", valor="") == texto

    def test_placeholder_desconocido_queda_y_se_reporta(self):
        from app.services.glosa_service import _PAT_PLACEHOLDER_CRUDO, _rellenar_placeholders

        out = _rellenar_placeholders("VER [ANEXO TECNICO FALTANTE]", eps="X", codigo="", valor="")
        assert _PAT_PLACEHOLDER_CRUDO.search(out), "sin equivalencia → queda para el check GRAVE"

    def test_post_validator_marca_grave(self):
        from app.services.quality_gate.post_validator import (
            check_sin_placeholders_crudos,
            post_validar_dictamen,
        )

        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA. "
            + EVIDENCIA_PLACEHOLDERS
            + " SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA. "
            + "FUNDAMENTO: PACTA SUNT SERVANDA Y BUENA FE CONTRACTUAL OBJETIVA."
        )
        chk = check_sin_placeholders_crudos(dictamen)
        assert not chk.ok and chk.severidad == "ERROR"
        r = post_validar_dictamen(dictamen, eps="SALUD MIA", texto_glosa_input="ME0801 GLOSA")
        assert not r.aprobado and r.debe_regenerar

    def test_post_validator_sic_no_dispara(self):
        from app.services.quality_gate.post_validator import check_sin_placeholders_crudos

        assert check_sin_placeholders_crudos("TEXTO CON [sic] LEGÍTIMO").ok

    @pytest.mark.asyncio
    async def test_analizar_rellena_placeholders_de_la_ia(self, monkeypatch):
        """End-to-end legacy: la IA devuelve placeholders crudos y el
        dictamen final sale con los datos reales del caso."""
        monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
        monkeypatch.delenv("TOOL_USE_HABILITADO", raising=False)
        from app.services.glosa_service import GlosaService
        from app.models.schemas import GlosaInput

        servicio = GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")
        respuesta_ia = (
            "<argumento>ESE HUS NO ACEPTA LA GLOSA "
            + EVIDENCIA_PLACEHOLDERS
            + " SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA.</argumento>"
        )
        monkeypatch.setattr(
            GlosaService, "_llamar_ia", AsyncMock(return_value=(respuesta_ia, "stub"))
        )
        data = GlosaInput(
            eps="SALUD MIA",
            etapa="RESPUESTA A GLOSA",
            tabla_excel="ME0801 - MEDICAMENTO GLOSADO POR VALOR DE $ 1.250.000 SIN MIPRES",
            valor_aceptado="0",
        )
        resultado = await servicio.analizar(data, contratos_db={})
        assert "[ENTIDAD]" not in resultado.dictamen
        assert "[VALOR REAL]" not in resultado.dictamen
        assert "[CODIGO]" not in resultado.dictamen
        assert "[SERVICIO]" not in resultado.dictamen
        assert "SALUD MIA" in resultado.dictamen.upper()
        assert "ME0801" in resultado.dictamen


# ════════════════════════════════════════════════════════════════════
# FIX 7 — Números deletreados en palabras.
# Evidencia real: "novecientos cincuenta y dos millones de pesos" → $0.00.
# ════════════════════════════════════════════════════════════════════

EVIDENCIA_LETRAS = (
    "CO0301 - SE GLOSA LA FACTURA POR NOVECIENTOS CINCUENTA Y DOS MILLONES "
    "DE PESOS POR PRESUNTA FALTA DE COBERTURA DEL PLAN"
)


class TestFix7NumerosDeletreados:
    def test_palabras_a_numero_composiciones_estandar(self):
        from app.utils.moneda import palabras_a_numero

        assert palabras_a_numero("novecientos cincuenta y dos millones") == 952_000_000.0
        assert palabras_a_numero("doscientos treinta mil") == 230_000.0
        assert palabras_a_numero("un millón doscientos mil") == 1_200_000.0
        assert palabras_a_numero("UN MILLON DOSCIENTOS MIL") == 1_200_000.0
        assert palabras_a_numero("dos mil millones") == 2_000_000_000.0
        assert palabras_a_numero("veintidós mil") == 22_000.0

    def test_palabras_a_numero_conservador(self):
        """Sin escala (mil/millón) o sin cardinal explícito NO devuelve
        valor — nada de NLP ni adivinanzas. "mil millones" sin número
        delante sigue siendo 0.0 (coherente con el fix P0-2 del 10-jun)."""
        from app.utils.moneda import palabras_a_numero

        assert palabras_a_numero("una glosa por tres conceptos") == 0.0
        assert palabras_a_numero("miles de millones en juego") == 0.0
        assert palabras_a_numero("los millones de pesos del contrato") == 0.0
        assert palabras_a_numero("mil millones") == 0.0
        assert palabras_a_numero("mil") == 0.0
        assert palabras_a_numero("") == 0.0
        assert palabras_a_numero(None) == 0.0

    def test_parse_valor_cop_ultimo_intento(self):
        from app.utils.moneda import parse_valor_cop

        assert parse_valor_cop("novecientos cincuenta y dos millones de pesos") == 952_000_000.0
        # Los formatos numéricos existentes NO cambian
        assert parse_valor_cop("7.700,00") == 7_700.0
        assert parse_valor_cop("850 millones") == 850_000_000.0
        assert parse_valor_cop("1,5 mil millones") == 1_500_000_000.0
        assert parse_valor_cop("texto sin valor") == 0.0

    def test_extraer_valor_evidencia(self):
        from app.services.glosa_service import GlosaService

        svc = GlosaService.__new__(GlosaService)
        assert svc._extraer_valor(EVIDENCIA_LETRAS) == "$ 952.000.000"
        assert svc._extraer_valor("TA0201 POR VALOR DE DOSCIENTOS TREINTA MIL PESOS") == "$ 230.000"
        assert svc._extraer_valor("FA0205 UN MILLÓN DOSCIENTOS MIL PESOS M/CTE") == "$ 1.200.000"

    def test_extraer_valor_digitos_siguen_ganando(self):
        from app.services.glosa_service import GlosaService

        svc = GlosaService.__new__(GlosaService)
        assert svc._extraer_valor("TA0201 $ 168.563 MAYOR VALOR COBRADO") == "$ 168.563"
        assert svc._extraer_valor("GLOSA $850 millones DE LA FACTURA") == "$ 850.000.000"
        assert svc._extraer_valor("SE RADICARON MIL GRACIAS") == "$ 0.00"


# ════════════════════════════════════════════════════════════════════
# FIX 8 — Fecha/factura tomada como CUPS.
# Evidencia real: "CUPS 2026-04" (era la fecha 2026-04-15) y "CUPS
# HUS0000522871" (era el número de factura).
# ════════════════════════════════════════════════════════════════════

EVIDENCIA_FECHA_CUPS = (
    "AU0301 - SE GLOSA POR FALTA DE AUTORIZACION LA ATENCION DEL 2026-04-15 "
    "FACTURA HUS0000522871. VALOR OBJETADO $890.000"
)


class TestFix8FechaFacturaComoCups:
    def test_extractor_principal_no_toma_fecha_ni_factura(self):
        from app.utils.parsers_glosa import _extraer_cups_servicio

        cups, _ = _extraer_cups_servicio(EVIDENCIA_FECHA_CUPS)
        assert cups == "", f"extrajo {cups!r} de una glosa SIN CUPS real"

    def test_extractor_principal_cups_legitimo_convive_con_fecha(self):
        from app.utils.parsers_glosa import _extraer_cups_servicio

        cups, _ = _extraer_cups_servicio(
            "TA0201 - 890602 - CONSULTA ESPECIALIZADA - FACTURA HUS0000522871 DEL 2026-04-15"
        )
        assert cups == "890602"

    def test_extractor_conserva_codigos_institucionales(self):
        from app.utils.parsers_glosa import _extraer_cups_servicio

        assert (
            _extraer_cups_servicio("FA0801 - 39147B-18 - MATERIAL OSTEOSINTESIS")[0] == "39147B-18"
        )
        assert _extraer_cups_servicio("ME0801 FMQ6296 MEDICAMENTO GLOSADO")[0] == "FMQ6296"

    def test_es_cups_descartable(self):
        from app.services.contexto_contractual_enriquecido import es_cups_descartable

        assert es_cups_descartable("2026-04")  # (a) fecha parcial
        assert es_cups_descartable("2026-04-15")  # (a) fecha completa
        assert es_cups_descartable("HUS0000522871")  # (b) prefijo factura
        assert es_cups_descartable("FE12345678")  # (b) factura electrónica
        assert es_cups_descartable("2026")  # (c) año
        assert es_cups_descartable("2026-04", "ATENCION DEL 2026-04-15")  # (d)
        assert not es_cups_descartable("890201")
        assert not es_cups_descartable("FMQ6296")
        assert not es_cups_descartable("39143A-4")

    def test_contexto_enriquecido_filtra_candidatos(self):
        from app.services.contexto_contractual_enriquecido import _extraer_cups_del_texto

        cups = _extraer_cups_del_texto("CUPS 890201 FACTURA HUS0000522871 FECHA 2026-04-15")
        assert cups == ["890201"]

    def test_prompt_instruye_omitir_cups_no_confiable(self):
        from app.services.glosa_ia_prompts import build_user_prompt

        p = build_user_prompt(
            texto_glosa=EVIDENCIA_FECHA_CUPS, contexto_pdf="", codigo="AU0301", eps="NUEVA EPS"
        )
        assert "NO inventes ni rellenes el CUPS" in p
        assert "omite la referencia al CUPS" in p

    def test_prompt_con_cups_confiable_no_lleva_la_advertencia(self):
        from app.services.glosa_ia_prompts import build_user_prompt

        p = build_user_prompt(
            texto_glosa="TA0201 - 890602 - CONSULTA ESPECIALIZADA MAYOR VALOR",
            contexto_pdf="",
            codigo="TA0201",
            eps="NUEVA EPS",
            cups_verificado="890602",
        )
        assert "NO inventes ni rellenes el CUPS" not in p


# ════════════════════════════════════════════════════════════════════
# FIX 9 — gpt-oss-120b razonador: presupuesto de tokens + retry-length.
# Evidencia real (prod 12-jun 19:37 UTC): "[GROQ-FALLBACK]
# model=openai/gpt-oss-120b agotado (Groq/openai/gpt-oss-120b devolvió
# content vacío/None (finish_reason='length')); probando siguiente
# modelo Groq: qwen/qwen3-32b". El chain-of-thought consumía TODO el
# max_tokens=3000 (calibrado para Llama) y se perdía calidad + latencia
# saltando a qwen. Fix: max_tokens>=8000 para gpt-oss, reasoning_effort
# 'medium'/'low', y retry del MISMO modelo con max_tokens duplicado
# antes de ceder la cadena.
# ════════════════════════════════════════════════════════════════════

GPT_OSS = "openai/gpt-oss-120b"
QWEN = "qwen/qwen3-32b"
LLAMA = "llama-3.3-70b-versatile"
DICTAMEN_OK = "<paciente>JUAN PEREZ</paciente><argumento>NO SE ACEPTA LA GLOSA</argumento>"
# Acción que simula la respuesta de prod: content vacío, razonamiento
# agotó el presupuesto (finish_reason='length').
VACIO_POR_LENGTH = ("", "length")


class _MsgF9:
    def __init__(self, content):
        self.content = content


class _ChoiceF9:
    def __init__(self, content, finish_reason):
        self.message = _MsgF9(content)
        self.finish_reason = finish_reason


class _RespF9:
    def __init__(self, content, finish_reason="stop"):
        self.choices = [_ChoiceF9(content, finish_reason)]


class _CompletionsF9:
    """create() falso que REGISTRA los kwargs completos de cada llamada
    (para asertar max_tokens / reasoning_effort) y consume acciones por
    modelo: str → respuesta OK; tuple (content, finish_reason) → respuesta
    cruda; Exception → raise; list → se consume en orden."""

    def __init__(self, por_modelo: dict):
        self.por_modelo = por_modelo
        self.kwargs_llamadas: list[dict] = []

    async def create(self, **kwargs):
        self.kwargs_llamadas.append(kwargs)
        accion = self.por_modelo[kwargs["model"]]
        if isinstance(accion, list):
            accion = accion.pop(0)
        if isinstance(accion, Exception):
            raise accion
        if isinstance(accion, tuple):
            return _RespF9(*accion)
        return _RespF9(accion)


class _ChatF9:
    def __init__(self, completions):
        self.completions = completions


class _GroqF9:
    def __init__(self, por_modelo: dict):
        self.chat = _ChatF9(_CompletionsF9(por_modelo))

    @property
    def kwargs_llamadas(self) -> list[dict]:
        return self.chat.completions.kwargs_llamadas

    @property
    def modelos_llamados(self) -> list[str]:
        return [k["model"] for k in self.kwargs_llamadas]


@pytest.fixture
def svc_groq_f9(monkeypatch):
    """GlosaService primary groq, sin keys del entorno ni BD de caché."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr("app.services.glosa_service._buscar_cache_ia_db", lambda clave: None)
    monkeypatch.setattr("app.services.glosa_service._guardar_cache_ia_db", lambda *a, **k: None)

    def _crear(por_modelo: dict, **kwargs):
        from app.services.glosa_service import GlosaService

        defaults = {"groq_api_key": "gsk_test", "anthropic_api_key": None, "primary_ai": "groq"}
        defaults.update(kwargs)
        svc = GlosaService(**defaults)
        svc.groq = _GroqF9(por_modelo)
        return svc

    return _crear


class TestFix9GptOssRazonadorPresupuesto:
    """max_tokens y reasoning_effort por familia de modelo."""

    @pytest.mark.asyncio
    async def test_gpt_oss_max_tokens_minimo_8000_y_reasoning_medium(self, svc_groq_f9):
        """Causa raíz: 3000 tokens calibrados para Llama; en gpt-oss el
        razonamiento se descuenta del MISMO presupuesto y lo agotaba."""
        svc = svc_groq_f9({GPT_OSS: DICTAMEN_OK}, groq_model=GPT_OSS)

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert content == DICTAMEN_OK
        assert modelo == f"groq/{GPT_OSS}"
        (kwargs,) = svc.groq.kwargs_llamadas
        assert kwargs["max_tokens"] >= 8000
        assert kwargs["reasoning_effort"] == "medium"

    @pytest.mark.asyncio
    async def test_llamada_corta_usa_reasoning_low(self, svc_groq_f9):
        """Auto-crítica/refinamiento: salida breve → no quemar razonamiento."""
        svc = svc_groq_f9({GPT_OSS: DICTAMEN_OK}, groq_model=GPT_OSS)

        await svc._llamar_groq_con_retry("sys", "user", llamada_corta=True)

        (kwargs,) = svc.groq.kwargs_llamadas
        assert kwargs["reasoning_effort"] == "low"
        assert kwargs["max_tokens"] >= 8000  # el presupuesto NO baja en cortas

    @pytest.mark.asyncio
    async def test_modelos_no_gpt_oss_conservan_max_tokens_sin_reasoning(self, svc_groq_f9):
        """Para llama/qwen el max_tokens sigue siendo el base (_GROQ_MAX_TOKENS,
        subido a 5000 en ronda 12) y reasoning_effort NI SIQUIERA viaja (el SDK
        documenta otro set de valores para qwen3 y ninguno para llama → riesgo
        de 400)."""
        from app.services.glosa_service import _GROQ_MAX_TOKENS

        svc = svc_groq_f9({LLAMA: DICTAMEN_OK}, groq_model=LLAMA, groq_model_fallback_1=QWEN)

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert modelo == f"groq/{LLAMA}"
        (kwargs,) = svc.groq.kwargs_llamadas
        assert kwargs["max_tokens"] == _GROQ_MAX_TOKENS
        assert "reasoning_effort" not in kwargs

    @pytest.mark.asyncio
    async def test_llamar_ia_propaga_llamada_corta_a_groq(self, svc_groq_f9):
        """El threading completo: _llamar_ia(llamada_corta=True) → gpt-oss
        recibe reasoning_effort='low' (path de auto-crítica/refinamiento)."""
        svc = svc_groq_f9({GPT_OSS: DICTAMEN_OK}, groq_model=GPT_OSS)

        await svc._llamar_ia("sys", f"glosa {uuid.uuid4()}", llamada_corta=True)

        assert svc.groq.kwargs_llamadas[0]["reasoning_effort"] == "low"


class TestFix9RetryLength:
    """content vacío + finish_reason='length' → retry con max_tokens x2."""

    @pytest.mark.asyncio
    async def test_length_vacio_reintenta_mismo_modelo_con_doble_presupuesto(
        self, svc_groq_f9, caplog
    ):
        """El escenario EXACTO del log de prod: gpt-oss agota el presupuesto
        razonando. Antes: salto directo a qwen. Ahora: una segunda
        oportunidad al mismo modelo con max_tokens duplicado."""
        caplog.set_level(logging.WARNING, logger="motor_glosas")
        svc = svc_groq_f9({GPT_OSS: [VACIO_POR_LENGTH, DICTAMEN_OK]}, groq_model=GPT_OSS)

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert content == DICTAMEN_OK
        assert modelo == f"groq/{GPT_OSS}"  # NO cayó a qwen
        assert svc.groq.modelos_llamados == [GPT_OSS, GPT_OSS]
        primera, segunda = svc.groq.kwargs_llamadas
        assert segunda["max_tokens"] == primera["max_tokens"] * 2
        mensajes = " | ".join(r.getMessage() for r in caplog.records)
        assert (
            f"[GROQ-RETRY-LENGTH] model={GPT_OSS} "
            f"max_tokens={primera['max_tokens']}→{segunda['max_tokens']}" in mensajes
        )

    @pytest.mark.asyncio
    async def test_length_vacio_persistente_recien_ahi_cae_a_qwen(self, svc_groq_f9):
        """El salto a qwen queda como SEGUNDA línea: solo tras el retry con
        presupuesto duplicado. Y qwen conserva su max_tokens de siempre."""
        svc = svc_groq_f9(
            {GPT_OSS: [VACIO_POR_LENGTH, VACIO_POR_LENGTH], QWEN: DICTAMEN_OK}, groq_model=GPT_OSS
        )

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        from app.services.glosa_service import _GROQ_MAX_TOKENS

        assert content == DICTAMEN_OK
        assert modelo == f"groq/{QWEN}"
        assert svc.groq.modelos_llamados == [GPT_OSS, GPT_OSS, QWEN]
        kwargs_qwen = svc.groq.kwargs_llamadas[2]
        # Base _GROQ_MAX_TOKENS sin cambios para no-gpt-oss (5000 desde ronda 12)
        assert kwargs_qwen["max_tokens"] == _GROQ_MAX_TOKENS
        assert "reasoning_effort" not in kwargs_qwen

    @pytest.mark.asyncio
    async def test_vacio_sin_length_no_gasta_retry(self, svc_groq_f9):
        """content vacío con finish_reason normal ('stop') NO es el caso del
        razonador: conserva el comportamiento previo (siguiente modelo ya)."""
        svc = svc_groq_f9({GPT_OSS: ("", "stop"), QWEN: DICTAMEN_OK}, groq_model=GPT_OSS)

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        assert modelo == f"groq/{QWEN}"
        assert svc.groq.modelos_llamados == [GPT_OSS, QWEN]

    @pytest.mark.asyncio
    async def test_length_vacio_en_no_gpt_oss_no_reintenta(self, svc_groq_f9):
        """El retry-por-length es EXCLUSIVO de gpt-oss: un length vacío en
        llama (no razonador) significa otra cosa y pasa de modelo directo."""
        svc = svc_groq_f9(
            {LLAMA: VACIO_POR_LENGTH, QWEN: DICTAMEN_OK},
            groq_model=LLAMA,
            groq_model_fallback_1=QWEN,
        )

        content, modelo = await svc._llamar_groq_con_retry("sys", "user")

        from app.services.glosa_service import _GROQ_MAX_TOKENS

        assert modelo == f"groq/{QWEN}"
        assert svc.groq.modelos_llamados == [LLAMA, QWEN]
        # Base sin cambios para no-gpt-oss: el retry-por-length-vacío es
        # EXCLUSIVO de gpt-oss. Llama con content vacío pasa de modelo directo.
        # (En ronda 12 se sumó retry-por-truncamiento que dispara con content
        # PARCIAL en cualquier modelo, pero acá el content viene vacío.)
        assert svc.groq.kwargs_llamadas[0]["max_tokens"] == _GROQ_MAX_TOKENS
