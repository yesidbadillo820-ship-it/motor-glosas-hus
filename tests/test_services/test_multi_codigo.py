"""Tests: un dictamen por código para glosas multi-código (jun-2026).

Caso real de producción: la EPS agrupa varios códigos en una misma fila
("SO0601 + TA0201 + TA0701"). Antes el motor respondía SOLO el primero y
el dictamen mezclaba familias sin declararlas. Contrato nuevo:

  - Flag MULTI_CODIGO_DICTAMENES ON (default): encabezado que declara
    TODOS los códigos + sección del principal (flujo intacto) + una
    sección por código adicional, cada una vía Quality Gate.
  - Cap: máximo 3 códigos (principal + 2); excedentes se declaran como
    "requieren respuesta separada".
  - Fallo en un código adicional NUNCA rompe el dictamen principal —
    queda nota visible de respuesta manual.
  - Flag OFF: comportamiento viejo (solo el primero + warning).
  - Single-código: cero cambios.

Patrón de stubs de _llamar_ia tomado de test_glosa_service_qg_wire.py.
"""

from __future__ import annotations

import logging

import pytest

from app.services import multi_codigo as mc

TEXTO_3_CODIGOS = (
    "SO0601 + TA0201 + TA0701 - AUSENCIA DE SOPORTES Y DIFERENCIA DE TARIFAS "
    "EN LA FACTURA FE12345 POR VALOR DE $1.500.000 SEGUN LO PACTADO"
)

TEXTO_4_CODIGOS = (
    "SO0601 + TA0201 + TA0701 + FA0801 - AUSENCIA DE SOPORTES, DIFERENCIA DE "
    "TARIFAS Y ERROR DE FACTURACION EN LA FACTURA FE12345 POR VALOR DE $1.500.000"
)

TEXTO_1_CODIGO = "FA0101 $ 7.700,00 FALTA SOPORTE DE ENTREGA DE LA FACTURA AL PACIENTE"


def _respuesta_stub(codigo: str) -> str:
    """Respuesta IA sintética que APRUEBA el post-validator del QG:
    >= 200 chars, cierre canónico, sin cifras ajenas al input, sin citas
    normativas (nada que el verificador pueda marcar), sin coda procesal."""
    cuerpo = (
        f"LA ESE HUS NO ACEPTA LA GLOSA EN LO RELATIVO AL CODIGO {codigo}. "
        "LA ENTIDAD PAGADORA OBJETA SIN APORTAR EVIDENCIA QUE DESVIRTUE LO FACTURADO. "
        "LOS SERVICIOS FUERON PRESTADOS, SOPORTADOS Y FACTURADOS CONFORME A LO PACTADO, "
        "Y EL EXPEDIENTE CONTIENE LOS DOCUMENTOS QUE ACREDITAN LA ATENCION BRINDADA. "
        "EN CONSECUENCIA, SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO INTEGRO "
        "DEL VALOR FACTURADO."
    )
    return f"<paciente>NO IDENTIFICADO</paciente><argumento>{cuerpo}</argumento>"


def _instalar_stub_ia(monkeypatch, registro: list, fallar_codigos=frozenset()):
    """Reemplaza GlosaService._llamar_ia por un stub determinista que
    registra el `codigo` de cada llamada (el flujo principal pasa el
    principal; el adapter QG pasa el código adicional)."""
    from app.services.glosa_service import GlosaService

    async def fake_llamar_ia(
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
        if codigo in fallar_codigos:
            raise RuntimeError(f"proveedor caido simulado para {codigo}")
        return (_respuesta_stub(codigo), "stub-test")

    monkeypatch.setattr(GlosaService, "_llamar_ia", fake_llamar_ia)


def _preparar_entorno(monkeypatch):
    """Entorno determinista: QG global OFF (el de las secciones adicionales
    NO depende del flag), sin tool-use ni multi-agent, sin retries del
    R-CEREBRO y sin dictamen directo (forzamos el path LLM para poder
    contar llamadas IA)."""
    monkeypatch.delenv("QUALITY_GATE_ENABLED", raising=False)
    monkeypatch.delenv("QUALITY_GATE_ROLLOUT_PCT", raising=False)
    monkeypatch.delenv("TOOL_USE_HABILITADO", raising=False)
    monkeypatch.delenv("MULTI_AGENT_HABILITADO", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MULTI_CODIGO_DICTAMENES", raising=False)

    import app.services.dictamen_directo as dd
    import app.services.validador_dictamen as vd

    monkeypatch.setattr(vd, "detectar_defectos_criticos", lambda *a, **k: [])
    monkeypatch.setattr(dd, "puede_emitir_directo", lambda *a, **k: False)


def _servicio():
    from app.services.glosa_service import GlosaService

    return GlosaService(groq_api_key=None, anthropic_api_key=None, primary_ai="groq")


def _data(texto: str):
    from app.models.schemas import GlosaInput

    return GlosaInput(
        eps="FAMISANAR EPS",
        etapa="RESPUESTA A GLOSA",
        tabla_excel=texto,
        valor_aceptado="0",
    )


_CONTRATOS = {"FAMISANAR EPS": "CONTRATO 2026"}


class TestMultiCodigoGeneraSecciones:
    """(a) Multi-código genera N secciones + encabezado con todos los códigos."""

    @pytest.mark.asyncio
    async def test_tres_codigos_encabezado_y_dos_secciones(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        registro: list = []
        _instalar_stub_ia(monkeypatch, registro)

        resultado = await _servicio().analizar(_data(TEXTO_3_CODIGOS), contratos_db=_CONTRATOS)
        d = resultado.dictamen

        # Encabezado declara TODOS los códigos
        assert "CÓDIGOS GLOSA: SO0601, TA0201, TA0701" in d
        # Sección del principal (flujo existente) sigue presente
        assert "ARGUMENTACIÓN JURÍDICA" in d
        # Una sección titulada por cada código adicional, con su familia
        assert "RESPUESTA AL CÓDIGO TA0201 — TARIFAS" in d
        assert "RESPUESTA AL CÓDIGO TA0701 — TARIFAS" in d
        # El argumento de cada sección es el del código correcto
        assert "AL CODIGO TA0201" in d
        assert "AL CODIGO TA0701" in d
        # Sin nota de fallidos: todos los bloques salieron
        assert "no pudieron procesarse" not in d
        # El campo codigo de la glosa sigue siendo el principal (BD intacta)
        assert resultado.codigo_glosa == "SO0601"
        # 1 llamada IA del principal + 1 por cada adicional (QG aprueba al 1er intento)
        assert registro == ["SO0601", "TA0201", "TA0701"]

    @pytest.mark.asyncio
    async def test_secciones_sobreviven_a_texto_plano_excel(self, monkeypatch):
        """Flujo descendente Excel-respuesta: dictamen_a_texto_plano debe
        conservar el encabezado y los títulos de sección legibles."""
        _preparar_entorno(monkeypatch)
        _instalar_stub_ia(monkeypatch, [])

        resultado = await _servicio().analizar(_data(TEXTO_3_CODIGOS), contratos_db=_CONTRATOS)

        from app.utils.html_a_texto import dictamen_a_texto_plano

        plano = dictamen_a_texto_plano(resultado.dictamen)
        assert "CÓDIGOS GLOSA: SO0601, TA0201, TA0701" in plano
        assert "═══ RESPUESTA AL CÓDIGO TA0201 — TARIFAS ═══" in plano
        assert "═══ RESPUESTA AL CÓDIGO TA0701 — TARIFAS ═══" in plano
        assert "<div" not in plano and "style=" not in plano

    @pytest.mark.asyncio
    async def test_pdf_radicable_renderiza_secciones(self, monkeypatch):
        """Flujo descendente PDF: el dictamen multi-código produce un PDF
        válido y las secciones aparecen como texto."""
        _preparar_entorno(monkeypatch)
        _instalar_stub_ia(monkeypatch, [])

        resultado = await _servicio().analizar(_data(TEXTO_3_CODIGOS), contratos_db=_CONTRATOS)

        import io
        from types import SimpleNamespace

        import pdfplumber

        from app.services.dictamen_pdf import generar_pdf_dictamen

        glosa = SimpleNamespace(
            id=99,
            factura="FE12345",
            eps="FAMISANAR EPS",
            tercero_nombre=None,
            eps_codigo=None,
            codigo_glosa=resultado.codigo_glosa,
            valor_objetado=1_500_000.0,
            codigo_respuesta="RE9901",
            paciente=None,
            numero_radicado=None,
            dictamen=resultado.dictamen,
        )
        pdf = generar_pdf_dictamen(glosa)
        assert pdf.startswith(b"%PDF")
        with pdfplumber.open(io.BytesIO(pdf)) as doc:
            txt = "\n".join(p.extract_text() or "" for p in doc.pages)
        assert "RESPUESTA AL CÓDIGO TA0201" in txt
        assert "RESPUESTA AL CÓDIGO TA0701" in txt
        assert "CÓDIGOS GLOSA: SO0601, TA0201, TA0701" in txt


class TestFalloAdicionalNoRompePrincipal:
    """(b) Un código adicional que falla no tumba el dictamen principal."""

    @pytest.mark.asyncio
    async def test_fallo_de_un_codigo_deja_nota_manual(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        registro: list = []
        # TA0701 revienta en TODOS los intentos del QG → bloque fallido
        _instalar_stub_ia(monkeypatch, registro, fallar_codigos={"TA0701"})

        resultado = await _servicio().analizar(_data(TEXTO_3_CODIGOS), contratos_db=_CONTRATOS)
        d = resultado.dictamen

        # Principal intacto + sección del código sano presente
        assert "ARGUMENTACIÓN JURÍDICA" in d
        assert resultado.codigo_glosa == "SO0601"
        assert "RESPUESTA AL CÓDIGO TA0201 — TARIFAS" in d
        # El código caído NO tiene sección, pero SÍ nota de respuesta manual
        assert "RESPUESTA AL CÓDIGO TA0701" not in d
        assert "TA0701 no pudieron procesarse automáticamente" in d
        assert "responder manualmente" in d

    @pytest.mark.asyncio
    async def test_excepcion_total_del_modulo_conserva_principal(self, monkeypatch):
        """Si generar_secciones_adicionales explota entero (no por código),
        el dictamen principal se entrega con la nota de pendientes."""
        _preparar_entorno(monkeypatch)
        _instalar_stub_ia(monkeypatch, [])

        async def kaboom(**kwargs):
            raise RuntimeError("crash simulado del módulo multi-código")

        monkeypatch.setattr(mc, "generar_secciones_adicionales", kaboom)

        resultado = await _servicio().analizar(_data(TEXTO_3_CODIGOS), contratos_db=_CONTRATOS)
        d = resultado.dictamen
        assert "ARGUMENTACIÓN JURÍDICA" in d  # principal vivo
        assert resultado.codigo_glosa == "SO0601"
        assert "TA0201, TA0701 no pudieron procesarse automáticamente" in d

    @pytest.mark.asyncio
    async def test_qg_escalar_humano_incluye_mejor_intento_con_banner(self, monkeypatch):
        """Si el QG escala a humano en un bloque adicional, se incluye el
        mejor intento con la nota visible de revisión y el score."""
        _preparar_entorno(monkeypatch)
        _instalar_stub_ia(monkeypatch, [])

        from app.services.quality_gate import QualityGateResult

        async def fake_qg(**kwargs):
            return QualityGateResult(
                estado="ESCALAR_HUMANO",
                dictamen_final=(
                    "BORRADOR PARA REVISION DEL CODIGO " + kwargs["codigo_glosa"] + ". " * 10
                ),
                modelo_final="stub",
                score_final=55,
            )

        monkeypatch.setattr(mc, "ejecutar_con_quality_gate", fake_qg)

        resultado = await _servicio().analizar(_data(TEXTO_3_CODIGOS), contratos_db=_CONTRATOS)
        d = resultado.dictamen
        assert "REVISAR ESTE BLOQUE — escalado por Quality Gate (score=55)" in d
        assert "BORRADOR PARA REVISION DEL CODIGO TA0201" in d


class TestFlagOffComportamientoViejo:
    """(c) MULTI_CODIGO_DICTAMENES=0 → solo el primero + warning."""

    @pytest.mark.asyncio
    async def test_flag_off_sin_secciones_y_con_warning(self, monkeypatch, caplog):
        _preparar_entorno(monkeypatch)
        monkeypatch.setenv("MULTI_CODIGO_DICTAMENES", "0")
        registro: list = []
        _instalar_stub_ia(monkeypatch, registro)

        with caplog.at_level(logging.WARNING):
            resultado = await _servicio().analizar(_data(TEXTO_3_CODIGOS), contratos_db=_CONTRATOS)

        d = resultado.dictamen
        assert "CÓDIGOS GLOSA:" not in d
        assert "RESPUESTA AL CÓDIGO" not in d
        assert "no pudieron procesarse" not in d
        # Una sola llamada IA: la del código principal
        assert registro == ["SO0601"]
        assert resultado.codigo_glosa == "SO0601"
        # El warning de pérdida sigue informando al operador
        assert any("Se procesa solo el primero" in r.message for r in caplog.records)

    @pytest.mark.asyncio
    async def test_flag_on_loguea_info_no_warning(self, monkeypatch, caplog):
        """Con el flag ON el log evoluciona a INFO (ya no hay pérdida)."""
        _preparar_entorno(monkeypatch)
        _instalar_stub_ia(monkeypatch, [])

        with caplog.at_level(logging.INFO):
            await _servicio().analizar(_data(TEXTO_3_CODIGOS), contratos_db=_CONTRATOS)

        msgs_multi = [r for r in caplog.records if "Multi-código detectado" in r.message]
        assert msgs_multi, "debe seguir logueando la detección multi-código"
        assert all(r.levelno == logging.INFO for r in msgs_multi)
        assert any("Se procesarán todos" in r.message for r in msgs_multi)


class TestSingleCodigoSinCambios:
    """(d) Una glosa de UN código no cambia en nada."""

    @pytest.mark.asyncio
    async def test_single_codigo_no_invoca_multi_codigo(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        registro: list = []
        _instalar_stub_ia(monkeypatch, registro)

        qg_calls = {"n": 0}

        async def spy_qg(**kwargs):
            qg_calls["n"] += 1
            raise AssertionError("el QG de secciones adicionales no debe ejecutarse")

        monkeypatch.setattr(mc, "ejecutar_con_quality_gate", spy_qg)

        resultado = await _servicio().analizar(_data(TEXTO_1_CODIGO), contratos_db=_CONTRATOS)
        d = resultado.dictamen

        assert resultado.codigo_glosa == "FA0101"
        assert "CÓDIGOS GLOSA:" not in d
        assert "RESPUESTA AL CÓDIGO" not in d
        assert "no pudieron procesarse" not in d
        assert registro == ["FA0101"]
        assert qg_calls["n"] == 0

    @pytest.mark.asyncio
    async def test_single_codigo_dictamen_identico_flag_on_vs_off(self, monkeypatch):
        """Bit-for-bit: para single-código el dictamen es idéntico con el
        flag ON (default) y OFF — la feature no toca ese camino."""
        _preparar_entorno(monkeypatch)
        _instalar_stub_ia(monkeypatch, [])

        res_on = await _servicio().analizar(_data(TEXTO_1_CODIGO), contratos_db=_CONTRATOS)

        monkeypatch.setenv("MULTI_CODIGO_DICTAMENES", "0")
        res_off = await _servicio().analizar(_data(TEXTO_1_CODIGO), contratos_db=_CONTRATOS)

        assert res_on.dictamen == res_off.dictamen
        assert res_on.codigo_glosa == res_off.codigo_glosa


class TestCapTresCodigos:
    """(e) El cap de 3 códigos (principal + 2 adicionales) se respeta."""

    @pytest.mark.asyncio
    async def test_cuarto_codigo_no_se_procesa_pero_se_declara(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        registro: list = []
        _instalar_stub_ia(monkeypatch, registro)

        resultado = await _servicio().analizar(_data(TEXTO_4_CODIGOS), contratos_db=_CONTRATOS)
        d = resultado.dictamen

        # El encabezado declara los 4, incluido el excedente
        assert "CÓDIGOS GLOSA: SO0601, TA0201, TA0701, FA0801" in d
        # Solo 2 secciones adicionales (cap = 3 códigos en total)
        assert "RESPUESTA AL CÓDIGO TA0201" in d
        assert "RESPUESTA AL CÓDIGO TA0701" in d
        assert "RESPUESTA AL CÓDIGO FA0801" not in d
        # El excedente queda anunciado como respuesta separada
        assert "FA0801 exceden el límite de procesamiento automático" in d
        assert "requieren respuesta separada" in d
        # FA0801 jamás llegó a la IA
        assert registro == ["SO0601", "TA0201", "TA0701"]


class TestHelpersUnitarios:
    """Unidades puras del módulo multi_codigo (sin IA ni analizar())."""

    def test_flag_default_on(self, monkeypatch):
        monkeypatch.delenv("MULTI_CODIGO_DICTAMENES", raising=False)
        assert mc.multi_codigo_habilitado() is True

    @pytest.mark.parametrize("valor", ["0", "false", "no", "off", " 0 "])
    def test_flag_off_variantes(self, monkeypatch, valor):
        monkeypatch.setenv("MULTI_CODIGO_DICTAMENES", valor)
        assert mc.multi_codigo_habilitado() is False

    @pytest.mark.parametrize("valor", ["1", "true", "on", "yes", ""])
    def test_flag_on_variantes(self, monkeypatch, valor):
        # "" (seteado vacío) también queda ON: solo el OFF explícito apaga
        monkeypatch.setenv("MULTI_CODIGO_DICTAMENES", valor)
        assert mc.multi_codigo_habilitado() is True

    def test_encabezado_declara_todos_los_codigos(self):
        html = mc.construir_encabezado_html(["SO0601", "TA0201", "TA0701"])
        assert "CÓDIGOS GLOSA: SO0601, TA0201, TA0701" in html
        assert "respuesta separada" not in html

    def test_encabezado_declara_excedentes(self):
        html = mc.construir_encabezado_html(
            ["SO0601", "TA0201", "TA0701", "FA0801"], no_procesados=["FA0801"]
        )
        assert "FA0801 exceden el límite" in html
        assert "requieren respuesta separada" in html

    def test_nota_fallidos_vacia_sin_codigos(self):
        assert mc.construir_nota_fallidos_html([]) == ""

    def test_nota_fallidos_lista_codigos(self):
        html = mc.construir_nota_fallidos_html(["TA0201", "TA0701"])
        assert "TA0201, TA0701 no pudieron procesarse automáticamente" in html
        assert "responder manualmente" in html

    def test_instruccion_adicional_contiene_reglas_clave(self):
        bloque = mc.construir_bloque_instruccion_adicional(
            codigo="TA0201",
            codigo_principal="SO0601",
            todos_los_codigos=["SO0601", "TA0201", "TA0701"],
            valor_objetado="$ 1.500.000",
        )
        assert "Genera SOLO la argumentación para el código TA0201" in bloque
        assert "familia TA — TARIFAS" in bloque
        assert "NO repitas la argumentación de los otros códigos" in bloque
        assert "SO0601" in bloque and "TA0701" in bloque
        assert "GLOSA COMPLETA" in bloque
        assert "valor total objetado" in bloque
        assert "NUNCA lo atribuyas solo a este código" in bloque

    def test_instruccion_adicional_sin_valor_prohibe_cifras(self):
        bloque = mc.construir_bloque_instruccion_adicional(
            codigo="TA0201",
            codigo_principal="SO0601",
            todos_los_codigos=["SO0601", "TA0201"],
            valor_objetado="$ 0.00",
        )
        assert "NO menciones cifras" in bloque
        assert "valor total objetado" not in bloque
