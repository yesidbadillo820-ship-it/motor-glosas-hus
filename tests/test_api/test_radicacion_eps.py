"""V3 · Pilar 1 — el circuito de radicación autónoma en portales.

Lo que estas pruebas cuidan, en orden de gravedad:

1. NO RADICAR DOS VECES. Es el daño real ante la EPS. Se cuida por tres
   lados: el índice único, el reclamo atómico y —el importante— la regla de
   que desde «no sé si quedó» está PROHIBIDO reintentar solo.
2. LOS 12 ESCUDOS DE LA V2 SIGUEN EN PIE. Nada llega al portal sin que un
   humano lo haya aprobado; la cuarentena del Auto-Pilot jamás se radica.
3. EL RELOJ. Al radicar, la glosa sale del semáforo de urgencia.
4. EL PILOTO DE 1 FACTURA. El bot no deja hacer un masivo sin confirmarlo.

Arquitectura: docs/ARQUITECTURA_V3_PILAR1_RPA.md
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.database import Base, get_db
from app.main import app
from app.models.db import (
    RAD_EN_PORTAL_SIN_CONFIRMAR,
    RAD_HUMANO_REQUERIDO,
    RAD_PENDIENTE,
    RAD_RADICADA,
    RAD_VERIFICAR_MANUAL,
    AutoPilotBitacoraRecord,
    GlosaRecord,
    RadicacionEpsRecord,
)
from app.services import radicacion_eps as svc

_TOOLS = Path(__file__).resolve().parents[2] / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

DICTAMEN = (
    "<div>ESE HUS NO ACEPTA LA GLOSA. La objeción fue notificada fuera del término "
    "legal y el expediente reposa completo en el archivo institucional. Se sostiene "
    "la defensa técnica en su integridad conforme a la normativa vigente.</div>"
)


@pytest.fixture
def db_session():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


@pytest.fixture
def cliente(db_session):
    coord = SimpleNamespace(email="coord@hus.gov.co", rol="COORDINADOR", activo=1)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[deps.get_usuario_actual] = lambda: coord
    app.dependency_overrides[deps.get_auditor_o_superior] = lambda: coord
    app.dependency_overrides[deps.get_coordinador_o_admin] = lambda: coord
    try:
        yield TestClient(app)
    finally:
        for d in (
            get_db,
            deps.get_usuario_actual,
            deps.get_auditor_o_superior,
            deps.get_coordinador_o_admin,
        ):
            app.dependency_overrides.pop(d, None)


def _glosa(db, **kw):
    base = dict(
        eps="COOSALUD EPS-S",
        factura="HUS900001",
        codigo_glosa="SO0101",
        etapa="OBJECION",
        valor_objetado=180000.0,
        estado="PENDIENTE",
        workflow_state="RESPONDIDA",
        dictamen=DICTAMEN,
        modelo_ia="texto_fijo_extemporanea",
    )
    base.update(kw)
    g = GlosaRecord(**base)
    db.add(g)
    db.commit()
    return g


# ══════════════════════════════════════════════════════════════════════════
#  1) Los escudos de la V2 siguen cerrados
# ══════════════════════════════════════════════════════════════════════════


class TestLosEscudosNoSeTocan:
    def test_la_cuarentena_del_auto_pilot_jamas_se_radica(self, db_session):
        g = _glosa(db_session, workflow_state="PENDIENTE_APROBACION_HUMANA")
        motivo = svc.motivo_no_radicable(db_session, g)
        assert motivo and "borradores del Auto-Pilot" in motivo

    def test_solo_se_radica_lo_que_esta_respondida(self, db_session):
        for estado in ("RADICADA", "BORRADOR", "EN_REVISION", "RATIFICADA"):
            g = _glosa(db_session, factura=f"HUS-{estado}", workflow_state=estado)
            assert svc.motivo_no_radicable(db_session, g), f"{estado} no debería radicarse"

    def test_sin_dictamen_no_hay_nada_que_radicar(self, db_session):
        g = _glosa(db_session, dictamen=None)
        assert "no hay nada que radicar" in (svc.motivo_no_radicable(db_session, g) or "")

    def test_lo_que_propuso_la_maquina_exige_liberacion_humana(self, db_session):
        g = _glosa(db_session)
        db_session.add(
            AutoPilotBitacoraRecord(
                glosa_id=g.id, decision="CANDIDATA", confianza=0.95, actor="auto-pilot"
            )
        )
        db_session.commit()
        motivo = svc.motivo_no_radicable(db_session, g)
        assert motivo and "liberación humana" in motivo

        # Con el clic humano en la bitácora, ya pasa.
        db_session.add(
            AutoPilotBitacoraRecord(
                glosa_id=g.id, decision="LIBERADA_POR_HUMANO", actor="gestor@hus.gov.co"
            )
        )
        db_session.commit()
        assert svc.motivo_no_radicable(db_session, g) is None


# ══════════════════════════════════════════════════════════════════════════
#  2) La matriz de portales del auditor
# ══════════════════════════════════════════════════════════════════════════


class TestMatrizDePortales:
    @pytest.mark.parametrize(
        "eps,portal",
        [
            ("COOSALUD EPS-S REGIMEN SUBSIDIADO", "COOSALUD"),
            ("MUTUAL SER EPS", "MUTUAL_SER"),
            ("DISPENSARIO MEDICO", "SIMED"),
            ("FOMAG", "FOMAG"),
            ("NUEVA EPS", "NUEVA_EPS"),
            ("DINAMICA GERENCIAL", "DGH"),
        ],
    )
    def test_reconoce_el_portal(self, eps, portal):
        assert svc.portal_de(eps) == portal

    def test_una_eps_desconocida_no_se_radica_sola(self, cliente, db_session):
        g = _glosa(db_session, eps="EPS QUE NADIE CONOCE", factura="HUS-RARA")
        r = cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        assert r.status_code == 200
        assert r.json()["humano_requerido"] == 1
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        assert fila.estado == RAD_HUMANO_REQUERIDO

    @pytest.mark.parametrize("eps", ["FOMAG", "NUEVA EPS", "DINAMICA GERENCIAL"])
    def test_los_portales_con_captcha_nacen_en_humano_requerido(self, cliente, db_session, eps):
        g = _glosa(db_session, eps=eps, factura=f"HUS-{eps[:6]}")
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        assert fila.estado == RAD_HUMANO_REQUERIDO

    def test_los_automatizables_entran_a_la_cola(self, cliente, db_session):
        g = _glosa(db_session)
        r = cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        assert r.json()["encoladas"] == 1
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        assert fila.estado == RAD_PENDIENTE and fila.portal == "COOSALUD"


# ══════════════════════════════════════════════════════════════════════════
#  3) No radicar dos veces — lo más importante
# ══════════════════════════════════════════════════════════════════════════


class TestNoRadicarDosVeces:
    def test_encolar_dos_veces_no_crea_dos_filas(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        r2 = cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        assert r2.json()["ya_estaban"] == 1
        assert db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).count() == 1

    def test_la_clave_de_idempotencia_no_depende_del_id(self, db_session):
        g1 = _glosa(db_session)
        g2 = _glosa(db_session, factura="HUS900001")  # misma factura/código/etapa
        assert svc.clave_idempotencia(g1) == svc.clave_idempotencia(g2)

    def test_desde_la_duda_esta_prohibido_reintentar(self, cliente, db_session):
        """El corazón del diseño: si se pulsó y no se confirmó, NO vuelve a
        la cola — va a que una persona mire el portal."""
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()

        svc.marcar_en_portal(db_session, fila.id)
        db_session.refresh(fila)
        assert fila.estado == RAD_EN_PORTAL_SIN_CONFIRMAR

        # El bot reporta el fallo… y NO cae a FALLIDA (que sería reintentable).
        svc.marcar_fallida(db_session, fila.id, "se cortó la red al enviar")
        db_session.refresh(fila)
        assert fila.estado == RAD_VERIFICAR_MANUAL, (
            "una radicación dudosa volvió a la cola: eso es radicar dos veces"
        )

    def test_solo_una_persona_saca_la_fila_de_la_duda(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        svc.marcar_en_portal(db_session, fila.id)
        svc.marcar_fallida(db_session, fila.id, "corte")

        r = cliente.post(
            f"/radicacion/{fila.id}/verificar",
            json={"quedo_radicada": True, "radicado_numero": "COO-777"},
        )
        assert r.status_code == 200
        db_session.refresh(fila)
        assert fila.estado == RAD_RADICADA
        assert fila.verificado_por == "coord@hus.gov.co"

    def test_confirmar_dos_veces_es_idempotente(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        svc.confirmar_radicada(db_session, fila.id, "COO-1")
        r = svc.confirmar_radicada(db_session, fila.id, "COO-2")
        assert r.get("repetida") is True
        db_session.refresh(fila)
        assert fila.radicado_numero == "COO-1", "la evidencia se reescribió"

    def test_un_comprobante_sin_numero_no_es_evidencia(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        assert svc.confirmar_radicada(db_session, fila.id, "  ")["estado"] == "sin_radicado"
        db_session.refresh(fila)
        assert fila.estado != RAD_RADICADA


# ══════════════════════════════════════════════════════════════════════════
#  4) El reloj se detiene
# ══════════════════════════════════════════════════════════════════════════


class TestElRelojSeDetiene:
    def test_al_radicar_la_glosa_sale_del_semaforo_de_urgencia(self, cliente, db_session):
        from app.services.motor_vencimientos import ESTADOS_CERRADOS, esta_en_juego

        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        svc.confirmar_radicada(db_session, fila.id, "COO-123")

        db_session.refresh(g)
        assert g.workflow_state == "RADICADA_EN_EPS"
        assert "RADICADA_EN_EPS" in ESTADOS_CERRADOS
        assert esta_en_juego(g) is False, "la glosa sigue compitiendo contra el reloj del hospital"

    def test_la_transicion_existe_en_el_workflow(self):
        from app.services.workflow_service import WorkflowService

        destinos = {t.hacia for t in WorkflowService.obtener_transiciones_validas("RESPONDIDA")}
        assert "RADICADA_EN_EPS" in destinos
        siguientes = {
            t.hacia for t in WorkflowService.obtener_transiciones_validas("RADICADA_EN_EPS")
        }
        assert {"RATIFICADA", "LEVANTADA", "CONCILIADA"} <= siguientes


# ══════════════════════════════════════════════════════════════════════════
#  5) El piloto de 1 factura
# ══════════════════════════════════════════════════════════════════════════


class TestElPilotoEsObligatorio:
    def test_por_defecto_radica_una_sola(self):
        import radicar_glosas_coosalud as bot

        assert bot.limite_efectivo(1, piloto_ok=False) == 1

    def test_un_masivo_sin_piloto_se_rechaza(self):
        import radicar_glosas_coosalud as bot

        with pytest.raises(bot.PilotoNoConfirmado) as e:
            bot.limite_efectivo(50, piloto_ok=False)
        assert "piloto" in str(e.value).lower()

    def test_con_el_piloto_confirmado_deja_pasar(self):
        import radicar_glosas_coosalud as bot

        assert bot.limite_efectivo(50, piloto_ok=True) == 50

    def test_el_catalogo_avisa_del_piloto(self):
        from app.services import bots_hus

        b = bots_hus.obtener("coosalud-radicar")
        assert b is not None
        assert "PILOTO" in (b.riesgo or "").upper()
        assert b.donde_corre == "pc_hus"


# ══════════════════════════════════════════════════════════════════════════
#  6) La frontera de las credenciales
# ══════════════════════════════════════════════════════════════════════════


class TestLaColaNoTransportaClaves:
    def test_lo_que_recibe_el_bot_no_trae_credenciales(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = svc.reclamar_una(db_session, "COOSALUD", equipo="PC-PRUEBA")
        assert fila is not None
        prohibidas = {"usuario", "user", "password", "clave", "contrasena", "token"}
        assert not (prohibidas & set(fila.keys())), "la cola está transportando credenciales"

    def test_el_bot_lee_las_claves_del_entorno_del_pc(self):
        fuente = (_TOOLS / "radicar_glosas_coosalud.py").read_text(encoding="utf-8")
        assert "cargar_credenciales" in fuente
        assert "El motor nunca las ve" in fuente
