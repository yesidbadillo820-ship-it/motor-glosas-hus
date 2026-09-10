"""Una ratificación no puede decir que mantiene una respuesta que no existe.

09-09-2026, caso 4 de la prueba del auditor. La respuesta a una glosa
RATIFICADA no la escribe la IA: el motor devuelve el texto fijo que definió
el área, y ese texto arranca así:

    «ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN
     TRÁMITE DE LA GLOSA INICIAL…»

Salió tal cual sobre una factura que en el historial no tenía ninguna
respuesta anterior. El escrito afirma mantener algo que no consta en ningún
lado, y a la entidad le basta pedir esa primera respuesta para tumbar la
ratificación entera — que era, además, el único argumento del escrito.

LA REGLA DE SIEMPRE: el motor no afirma lo que no puede probar. Y con dos
mitades:

  · si el historial dice que NO hay respuesta previa → se avisa y NO se
    radica (un hallazgo grave bloquea, no aconseja);
  · si no se puede saber —la factura no está en el historial, o la base no
    responde— NO se acusa a nadie. «No se sabe» no es «no existe»: una
    factura respondida antes de que el motor existiera, o respondida por
    fuera, tampoco aparece.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import GlosaRecord
from app.services.glosa_service import (
    _bloqueos_para_radicar,
    _hay_respuesta_inicial_registrada,
)


@pytest.fixture
def base_en_memoria(monkeypatch):
    """Una base vacía, y el helper apuntando a ella."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Sesion = sessionmaker(bind=engine)
    monkeypatch.setattr("app.database.SessionLocal", Sesion, raising=False)
    s = Sesion()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _guardar(db, factura, etapa, dictamen):
    db.add(
        GlosaRecord(
            eps="COOSALUD EPS",
            factura=factura,
            etapa=etapa,
            estado="RADICADA",
            codigo_glosa="TA0201",
            dictamen=dictamen,
        )
    )
    db.commit()


class TestCuandoSiHayRespuestaAnterior:
    def test_una_respuesta_inicial_guardada_cuenta(self, base_en_memoria):
        _guardar(base_en_memoria, "FE-900", "INICIAL", "ESE HUS NO ACEPTA LA GLOSA…")
        assert _hay_respuesta_inicial_registrada("FE-900") is True

    def test_no_importa_como_se_llame_la_etapa_mientras_no_sea_ratificacion(self, base_en_memoria):
        """El Excel de recepción guarda «RESPUESTA A GLOSA»; el formulario,
        «RESPUESTA». Las dos son la respuesta que se mantiene."""
        _guardar(base_en_memoria, "FE-901", "RESPUESTA A GLOSA", "TEXTO DE LA RESPUESTA")
        assert _hay_respuesta_inicial_registrada("FE-901") is True

    def test_los_espacios_alrededor_del_numero_no_lo_esconden(self, base_en_memoria):
        _guardar(base_en_memoria, "FE-902", "INICIAL", "TEXTO")
        assert _hay_respuesta_inicial_registrada("  FE-902  ") is True


class TestCuandoNoHayRespuestaAnterior:
    def test_la_factura_esta_pero_sin_ningun_dictamen(self, base_en_memoria):
        """El caso 4: la factura se registró y nunca se respondió."""
        _guardar(base_en_memoria, "FE-910", "INICIAL", None)
        assert _hay_respuesta_inicial_registrada("FE-910") is False

    def test_un_dictamen_en_blanco_tampoco_es_una_respuesta(self, base_en_memoria):
        _guardar(base_en_memoria, "FE-911", "INICIAL", "   \n  ")
        assert _hay_respuesta_inicial_registrada("FE-911") is False

    def test_la_propia_ratificacion_no_se_cuenta_a_si_misma(self, base_en_memoria):
        """Sería circular: la ratificación no puede ser «la respuesta que
        se mantiene» de sí misma."""
        _guardar(base_en_memoria, "FE-912", "RATIFICACION", "TEXTO DE LA RATIFICADA")
        assert _hay_respuesta_inicial_registrada("FE-912") is False

    def test_tampoco_la_hoja_RATIFICADA_del_excel(self, base_en_memoria):
        _guardar(base_en_memoria, "FE-913", "RATIFICADA", "TEXTO")
        assert _hay_respuesta_inicial_registrada("FE-913") is False


class TestCuandoNoSePuedeSaber:
    """«No se sabe» no es «no existe». Con la duda, no se acusa a nadie."""

    def test_una_factura_que_no_esta_en_el_historial(self, base_en_memoria):
        assert _hay_respuesta_inicial_registrada("FE-QUE-NO-EXISTE") is None

    def test_sin_numero_de_factura(self, base_en_memoria):
        assert _hay_respuesta_inicial_registrada(None) is None
        assert _hay_respuesta_inicial_registrada("") is None
        assert _hay_respuesta_inicial_registrada("   ") is None

    def test_si_la_base_no_responde_no_se_acusa(self, monkeypatch):
        def _revienta():
            raise RuntimeError("base caída")

        monkeypatch.setattr("app.database.SessionLocal", _revienta, raising=False)
        assert _hay_respuesta_inicial_registrada("FE-999") is None


class TestElAvisoImpideRadicar:
    """Un hallazgo grave bloquea; no aconseja. Es la doctrina del motor."""

    def test_el_dictamen_con_el_aviso_queda_bloqueado(self):
        dictamen = (
            "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN "
            "TRÁMITE DE LA GLOSA INICIAL…\n\n"
            "⛔ NO RADICAR TODAVÍA: NO HAY RESPUESTA INICIAL REGISTRADA. Este escrito "
            "dice que se mantiene la respuesta dada a la glosa inicial, y en el "
            "historial de esta factura no aparece ninguna respuesta anterior."
        )
        motivos = _bloqueos_para_radicar(dictamen)
        assert motivos, "El aviso salió pero el dictamen se podía radicar igual."
        assert "Dice que mantiene una respuesta anterior que no aparece" in motivos

    def test_una_ratificacion_normal_no_se_bloquea(self):
        from app.services.glosa_service import TEXTO_RATIFICADA

        assert _bloqueos_para_radicar(TEXTO_RATIFICADA) == []


class TestElMotorCompletoLoAplica:
    """Los helpers sueltos pueden estar bien y el cableado mal.

    Esto corre el motor entero sobre una glosa RATIFICADA —el camino del
    texto fijo, donde la IA no se llama— y comprueba que el aviso llega
    hasta el dictamen y hasta el sello de «no radicable» que ve la pantalla.
    """

    @staticmethod
    def _entorno(monkeypatch):
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

    @staticmethod
    def _glosa(factura):
        from app.models.schemas import GlosaInput

        return GlosaInput(
            eps="COOSALUD EPS",
            etapa="RATIFICACION",
            numero_factura=factura,
            tabla_excel="TA0201 $1.500.000 SE RATIFICA GLOSA POR TARIFAS",
            valor_aceptado="0",
        )

    @pytest.mark.asyncio
    async def test_sin_respuesta_previa_el_dictamen_sale_bloqueado(
        self, base_en_memoria, monkeypatch
    ):
        from app.services.glosa_service import GlosaService

        self._entorno(monkeypatch)
        _guardar(base_en_memoria, "FE-920", "INICIAL", None)  # nunca se respondió

        r = await GlosaService(groq_api_key=None).analizar(self._glosa("FE-920"), contratos_db={})

        assert "NO HAY RESPUESTA INICIAL REGISTRADA" in r.dictamen, (
            "El aviso no llegó al dictamen: el helper acierta pero el cableado no "
            "lo aplica en el camino del texto fijo, que es justo el de las "
            "ratificaciones."
        )
        assert r.bloqueado_para_radicar is True, (
            "El aviso sale pero el dictamen se puede radicar igual. Un hallazgo "
            "grave bloquea, no aconseja."
        )
        assert any("no aparece" in m for m in (r.motivos_bloqueo or [])), r.motivos_bloqueo

    @pytest.mark.asyncio
    async def test_con_respuesta_previa_el_dictamen_sale_limpio(self, base_en_memoria, monkeypatch):
        from app.services.glosa_service import GlosaService

        self._entorno(monkeypatch)
        _guardar(base_en_memoria, "FE-921", "INICIAL", "ESE HUS NO ACEPTA LA GLOSA…")

        r = await GlosaService(groq_api_key=None).analizar(self._glosa("FE-921"), contratos_db={})

        assert "NO HAY RESPUESTA INICIAL REGISTRADA" not in r.dictamen, (
            "Avisa de una respuesta que SÍ existe: el aviso perdería toda su "
            "fuerza saliendo en ratificaciones normales."
        )

    @pytest.mark.asyncio
    async def test_si_no_se_sabe_no_se_avisa(self, base_en_memoria, monkeypatch):
        """La factura no está en el historial. Puede haberse respondido antes
        de que el motor existiera: eso no se puede llamar invención."""
        from app.services.glosa_service import GlosaService

        self._entorno(monkeypatch)

        r = await GlosaService(groq_api_key=None).analizar(
            self._glosa("FE-QUE-NO-ESTA"), contratos_db={}
        )

        assert "NO HAY RESPUESTA INICIAL REGISTRADA" not in r.dictamen
