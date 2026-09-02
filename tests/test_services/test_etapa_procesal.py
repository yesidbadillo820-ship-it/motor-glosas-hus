"""Ciclo de vida de la glosa: el motor ya no responde una segunda instancia
como si fuera el día uno (Caso J, refactor del 02-09-2026).

El auditor pasó una glosa que decía «RESPUESTA A CONCILIACION. SE RATIFICA LA
GLOSA INICIAL» y el dictamen salió pidiendo el «levantamiento» como el primer
día. Si eso se radica en segunda instancia, la EPS cierra el caso por forma.

Requisitos que se prueban:
  1. Un clasificador de etapa lee marcadores avanzados (ratifica, mantiene
     glosa, respuesta a conciliación, segunda instancia, acta) y tipifica la
     glosa como RATIFICACION o CONCILIACION, no como INICIAL.
  2. En segunda instancia el modelo tiene PROHIBIDO redactar como respuesta
     inicial: el prompt le ordena sostener la defensa y exigir la mesa de
     conciliación / escalar a Supersalud (Ley 1438 de 2011).
  3. La pantalla muestra un badge «⚠️ ETAPA: RATIFICACIÓN DETECTADA».

Y una NO-regresión clave: una ratificación EXTEMPORÁNEA (SO0601) sigue yendo al
motor con su defensa de tiempo — el badge la marca, pero no se la lleva el
texto fijo.
"""

from __future__ import annotations

import pytest

from app.services import reglas_casos_fno as R
from app.services.glosa_service import GlosaService


def up(s: str) -> str:
    return s.strip().upper()


# ─────────────────────────── clasificador ───────────────────────────
class TestClasificadorDeEtapa:
    @pytest.mark.parametrize(
        "frase,esperado",
        [
            ("LA EPS RATIFICA LA GLOSA POR FALTA DE EPICRISIS", "RATIFICACION"),
            ("SE RATIFICA LA GLOSA INICIAL POR $800.000", "RATIFICACION"),
            ("LA ENTIDAD MANTIENE LA GLOSA", "RATIFICACION"),
            ("GLOSA EN SEGUNDA INSTANCIA", "RATIFICACION"),
            ("LA EPS INSISTE EN LA GLOSA", "RATIFICACION"),
            ("LA EPS REITERA LA GLOSA", "RATIFICACION"),
            ("RESPUESTA A CONCILIACION. LA IPS APORTO SOPORTES", "CONCILIACION"),
            ("SE CONVOCA A MESA DE CONCILIACION", "CONCILIACION"),
            ("ACTA DE CONCILIACION DE AUDITORIA MEDICA", "CONCILIACION"),
            ("TA0301 | HUS1 | NUEVA EPS. MAYOR VALOR COBRADO. GLOSADO $500.000", "INICIAL"),
            ("SO0102 | HUS1 | DIFERENCIA EN CANTIDADES. GLOSA $1.000.000", "INICIAL"),
        ],
    )
    def test_clasifica(self, frase, esperado):
        assert R.clasificar_etapa_procesal(up(frase)) == esperado

    def test_conciliacion_manda_sobre_ratificacion(self):
        # Aparecen las dos: conciliación es la etapa posterior.
        t = up("SE RATIFICA LA GLOSA Y SE CONVOCA A MESA DE CONCILIACION")
        assert R.clasificar_etapa_procesal(t) == "CONCILIACION"

    def test_el_campo_etapa_del_formulario_cuenta(self):
        assert R.clasificar_etapa_procesal("texto sin marcadores", "RATIFICACION") == "RATIFICACION"
        assert R.clasificar_etapa_procesal("texto sin marcadores", "CONCILIACION") == "CONCILIACION"

    def test_el_ruteo_al_texto_fijo_no_cambia(self):
        """`texto_es_ratificacion` (más estricto) sigue decidiendo el texto
        fijo: «ratifica» a secas NO lo dispara (para que SO0601 vaya al motor);
        el marcador de conciliación sí."""
        assert not R.texto_es_ratificacion(up("LA EPS RATIFICA LA GLOSA"))
        assert R.texto_es_ratificacion(up("RESPUESTA A CONCILIACION"))


# ─────────────────────────── integración end-to-end ───────────────────────────
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


def _stub_ia(monkeypatch, prompts: list):
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
        prompts.append(user)
        cuerpo = (
            "ESE HUS SOSTIENE LA DEFENSA TECNICO-JURIDICA YA PRESENTADA Y NO ACEPTA LA "
            "GLOSA RATIFICADA POR FALTA DE EPICRISIS. "
            * 4
            + "SE SOLICITA LA PROGRAMACION DE LA MESA DE CONCILIACION DE AUDITORIA MEDICA."
        )
        return (
            f"<paciente>NO IDENTIFICADO</paciente><argumento>{cuerpo}</argumento>",
            "stub-test",
        )

    monkeypatch.setattr(GlosaService, "_llamar_ia", fake)


def _data(texto: str, eps: str, etapa: str = "RESPUESTA A GLOSA"):
    from app.models.schemas import GlosaInput

    return GlosaInput(eps=eps, etapa=etapa, tabla_excel=texto, valor_aceptado="0")


CASO_J = "FA0101 | HUS0000605555 | COOSALUD. RESPUESTA A CONCILIACION. LA IPS APORTO LOS SOPORTES PERO SIGUEN ILEGIBLES. SE RATIFICA LA GLOSA INICIAL POR $800.000."
RATIFICA_SOLA = "SO0701 | HUS0000607000 | NUEVA EPS. LA EPS RATIFICA LA GLOSA POR FALTA DE EPICRISIS. VALOR OBJETADO $500.000."
SO0601 = "SO0601 | HUS0000606000 | NUEVA EPS. LA EPS RATIFICA LA GLOSA POR FALTA DE EPICRISIS. FECHA RADICACION: 2026-03-01. FECHA RECEPCION RATIFICACION: 2026-05-30. VALOR OBJETADO $1.350.000."


@pytest.mark.asyncio
class TestEnrutamientoEtapa:
    async def test_conciliacion_va_por_texto_fijo_con_supersalud_sin_ia(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        prompts = []
        _stub_ia(monkeypatch, prompts)
        r = await GlosaService(groq_api_key=None).analizar(
            _data(CASO_J, "COOSALUD"), contratos_db={}
        )
        assert prompts == []  # texto fijo, no IA
        assert r.etapa_procesal == "CONCILIACION"
        d = r.dictamen.upper()
        assert "CONCILIACIÓN" in d
        assert "SUPERINTENDENCIA NACIONAL DE SALUD" in d
        # No responde como día uno: mantiene la respuesta inicial.
        assert "MANTIENE" in d

    async def test_ratifica_sola_va_al_motor_con_bloque_de_etapa(self, monkeypatch):
        _preparar_entorno(monkeypatch)
        prompts = []
        _stub_ia(monkeypatch, prompts)
        r = await GlosaService(groq_api_key=None).analizar(
            _data(RATIFICA_SOLA, "NUEVA EPS"), contratos_db={}
        )
        assert prompts, "una ratificación sin marcador de conciliación va al motor"
        assert r.etapa_procesal == "RATIFICACION"
        # El prompt le prohíbe redactar como respuesta inicial.
        assert "NO ES UNA GLOSA INICIAL" in prompts[0]
        assert "MESA DE CONCILIACIÓN" in prompts[0]
        assert "SUPERINTENDENCIA NACIONAL DE SALUD" in prompts[0]

    async def test_ratificacion_extemporanea_conserva_su_defensa_de_tiempo(self, monkeypatch):
        """SO0601: ratificación tardía. El badge la marca, pero NO se la lleva
        el texto fijo: va al motor, y el prompt trae el bloque de
        extemporaneidad ADEMÁS del de etapa."""
        _preparar_entorno(monkeypatch)
        prompts = []
        _stub_ia(monkeypatch, prompts)
        r = await GlosaService(groq_api_key=None).analizar(
            _data(SO0601, "NUEVA EPS"), contratos_db={}
        )
        assert prompts, "la ratificación extemporánea va al motor, no al texto fijo"
        assert r.etapa_procesal == "RATIFICACION"
        assert "EXTEMPORANEIDAD DETECTADA" in prompts[0]
        assert "NO ES UNA GLOSA INICIAL" in prompts[0]


# ─────────────────────────── UI ───────────────────────────
class TestElBadgeEnLaPantalla:
    def _html(self) -> str:
        import io

        return io.open("static/index.html", encoding="utf-8").read()

    def test_la_pantalla_pinta_el_badge_de_etapa(self):
        html = self._html()
        assert "d.etapa_procesal" in html
        assert "ETAPA: " in html and "DETECTADA" in html
        assert "pill-etapa" in html

    def test_el_badge_solo_sale_cuando_no_es_inicial(self):
        html = self._html()
        assert "d.etapa_procesal!=='INICIAL'" in html


# ─────────────────────────── esquema ───────────────────────────
class TestElResultadoLlevaLaEtapa:
    def test_glosa_result_acepta_etapa_procesal(self):
        from app.models.schemas import GlosaResult

        r = GlosaResult(
            tipo="RESPUESTA RE9901",
            resumen="x",
            dictamen="x",
            codigo_glosa="FA0101",
            valor_objetado="$ 800.000",
            paciente="N/A",
            mensaje_tiempo="EN TÉRMINOS",
            color_tiempo="green",
            etapa_procesal="CONCILIACION",
        )
        assert r.etapa_procesal == "CONCILIACION"

    def test_por_defecto_es_inicial(self):
        from app.models.schemas import GlosaResult

        r = GlosaResult(
            tipo="x",
            resumen="x",
            dictamen="x",
            codigo_glosa="TA0301",
            valor_objetado="$ 0.00",
            paciente="N/A",
            mensaje_tiempo="x",
            color_tiempo="x",
        )
        assert r.etapa_procesal == "INICIAL"
