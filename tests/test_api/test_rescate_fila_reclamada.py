"""Rescate de filas RECLAMADAS (hotfix 04-09-2026).

**La fuga.** `reclamar_una` marca la fila RECLAMADA y se la entrega al bot.
Si el bot se moría en el paso siguiente —playwright sin instalar, el
navegador que no arranca, el portal que no abre— esa fila se quedaba
RECLAMADA **para siempre**:

  · los demás equipos no la veían, porque solo toman las PENDIENTE;
  · las personas tampoco, porque la bandeja muestra las atoradas;
  · y la glosa desaparecía sin que nadie se enterara.

**El rescate.** El bot atrapa su propia caída y devuelve la fila a PENDIENTE
para que otro equipo sano la tome. A los 3 intentos deja de rebotar y pasa a
HUMANO_REQUERIDO: si un PC falló tres veces en el mismo sitio no es mala
suerte, es que le falta algo, y ninguna cuarta pasada lo va a arreglar.

**Lo que el rescate NO puede hacer nunca.** Traer de vuelta una fila que ya
salió de RECLAMADA. En particular una EN_PORTAL_SIN_CONFIRMAR: ahí ya se
pulsó «radicar» y no se leyó el comprobante. Devolverla a la cola sería
invitar a radicar dos veces la misma glosa ante la EPS.
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

from app.core.config import get_settings
from app.database import Base, get_db
from app.models.db import (
    RAD_EN_PORTAL_SIN_CONFIRMAR,
    RAD_FALLIDA,
    RAD_HUMANO_REQUERIDO,
    RAD_PENDIENTE,
    RAD_RADICADA,
    RAD_RECLAMADA,
    GlosaRecord,
    RadicacionEpsRecord,
)
from app.services import radicacion_eps as svc

RAIZ = Path(__file__).resolve().parents[2]
_TOOLS = RAIZ / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

TOKEN_AGENTE = "token-del-agente-para-pruebas-0123456789"

DICTAMEN = (
    "<div>ESE HUS NO ACEPTA LA GLOSA. El expediente reposa completo en el archivo "
    "institucional y la objeción fue notificada fuera del término legal. Se sostiene "
    "la defensa técnica en su integridad conforme a la normativa vigente.</div>"
)


@pytest.fixture
def db():
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


def _glosa(db, **kw) -> GlosaRecord:
    base = dict(
        eps="COOSALUD EPS-S",
        factura="HUS940001",
        codigo_glosa="SO0101",
        codigo_respuesta="RE9901",
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


def _fila_reclamada(db) -> RadicacionEpsRecord:
    """Una fila tal como queda cuando el bot acaba de reclamarla."""
    g = _glosa(db)
    svc.encolar(db, [g.id])
    tomada = svc.reclamar_una(db, "COOSALUD", "PC-CARTERA-01")
    assert tomada is not None
    fila = db.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
    assert fila.estado == RAD_RECLAMADA
    return fila


# ══════════════════════════════════════════════════════════════════════════
#  1) Lo que pidió el auditor: la fila vuelve a PENDIENTE
# ══════════════════════════════════════════════════════════════════════════


class TestLaFilaVuelveALaCola:
    def test_el_worker_se_cae_con_la_fila_en_la_mano_y_ella_vuelve_a_pendiente(self, db):
        fila = _fila_reclamada(db)

        r = svc.rescatar_reclamada(db, fila.id, "ModuleNotFoundError: No module named 'playwright'")

        db.refresh(fila)
        assert r["estado"] == RAD_PENDIENTE
        assert fila.estado == RAD_PENDIENTE
        assert r["agotada"] is False

    def test_queda_escrito_de_que_se_murio(self, db):
        fila = _fila_reclamada(db)
        svc.rescatar_reclamada(db, fila.id, "a este PC le falta playwright: ImportError")
        db.refresh(fila)
        assert "playwright" in fila.ultimo_error

    def test_el_diagnostico_largo_no_revienta_la_columna(self, db):
        fila = _fila_reclamada(db)
        svc.rescatar_reclamada(db, fila.id, "x" * 9000)
        db.refresh(fila)
        assert len(fila.ultimo_error) == 4000

    def test_se_le_quita_el_sello_del_pc_que_la_tenia(self, db):
        """Una fila pendiente con el nombre de un equipo encima confunde a
        quien mira la bandeja: parece que alguien la está trabajando."""
        fila = _fila_reclamada(db)
        assert "PC-CARTERA-01" in fila.actor
        svc.rescatar_reclamada(db, fila.id, "se cayó")
        db.refresh(fila)
        assert "PC-CARTERA-01" not in (fila.actor or "")
        assert fila.actor == svc.ACTOR_BOT

    def test_otro_equipo_sano_puede_tomarla_de_verdad(self, db):
        """La prueba de que el rescate sirve para algo: no basta con cambiar
        el estado, tiene que volver a ser reclamable."""
        fila = _fila_reclamada(db)
        assert svc.reclamar_una(db, "COOSALUD", "PC-CARTERA-02") is None  # estaba tomada

        svc.rescatar_reclamada(db, fila.id, "el primer PC se cayó")

        segunda = svc.reclamar_una(db, "COOSALUD", "PC-CARTERA-02")
        assert segunda is not None
        assert segunda["radicacion_id"] == fila.id
        db.refresh(fila)
        assert "PC-CARTERA-02" in fila.actor


# ══════════════════════════════════════════════════════════════════════════
#  2) El contador y el cortacircuito
# ══════════════════════════════════════════════════════════════════════════


class TestElContadorYElCortacircuito:
    def test_el_intento_lo_cuenta_el_reclamo_y_no_se_cuenta_dos_veces(self, db):
        """`reclamar_una` ya suma al entregar la fila. Si el rescate volviera
        a sumar, el cortacircuito saltaría a las dos vueltas, no a las tres."""
        fila = _fila_reclamada(db)
        assert fila.intentos == 1

        r = svc.rescatar_reclamada(db, fila.id, "se cayó")

        db.refresh(fila)
        assert fila.intentos == 1, "el rescate contó el intento por segunda vez"
        assert r["intentos"] == 1

    def test_a_la_tercera_deja_de_rebotar(self, db):
        """El ciclo completo, tal como pasaría en el hospital: tres equipos
        (o el mismo tres veces) intentan y se caen."""
        g = _glosa(db)
        svc.encolar(db, [g.id])
        fila = db.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()

        for vuelta in (1, 2):
            tomada = svc.reclamar_una(db, "COOSALUD", f"PC-0{vuelta}")
            assert tomada is not None, f"la vuelta {vuelta} no pudo tomarla"
            r = svc.rescatar_reclamada(db, fila.id, f"caída {vuelta}")
            assert r["estado"] == RAD_PENDIENTE, f"la vuelta {vuelta} no la devolvió"

        # Tercera y última.
        assert svc.reclamar_una(db, "COOSALUD", "PC-03") is not None
        r = svc.rescatar_reclamada(db, fila.id, "caída 3")

        db.refresh(fila)
        assert r["estado"] == RAD_HUMANO_REQUERIDO
        assert r["agotada"] is True
        assert fila.estado == RAD_HUMANO_REQUERIDO
        assert fila.intentos == 3
        assert "caída 3" in fila.ultimo_error

    def test_agotada_ya_no_la_toma_ningun_bot(self, db):
        """Que deje de rebotar es justamente esto: no vuelve a la rueda."""
        g = _glosa(db)
        svc.encolar(db, [g.id])
        fila = db.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        for vuelta in (1, 2, 3):
            svc.reclamar_una(db, "COOSALUD", f"PC-0{vuelta}")
            svc.rescatar_reclamada(db, fila.id, f"caída {vuelta}")

        assert svc.reclamar_una(db, "COOSALUD", "PC-04") is None

    def test_el_tope_es_tres_y_esta_escrito_en_un_solo_sitio(self):
        assert svc.MAX_INTENTOS_RESCATE == 3

    def test_el_tope_se_puede_ajustar_sin_tocar_el_codigo(self, db):
        fila = _fila_reclamada(db)
        r = svc.rescatar_reclamada(db, fila.id, "se cayó", max_intentos=1)
        assert r["estado"] == RAD_HUMANO_REQUERIDO


# ══════════════════════════════════════════════════════════════════════════
#  3) Dónde el rescate NO se mete
# ══════════════════════════════════════════════════════════════════════════


class TestElRescateNoSeMeteDondeNoDebe:
    def test_jamas_trae_de_vuelta_una_que_ya_se_pulso_en_el_portal(self, db):
        """La regla más importante del módulo: desde «no sé si quedó» NO se
        reintenta. Radicar dos veces la misma glosa le hace daño real al
        hospital ante la EPS."""
        fila = _fila_reclamada(db)
        svc.marcar_en_portal(db, fila.id)

        r = svc.rescatar_reclamada(db, fila.id, "se cayó justo después de pulsar")

        db.refresh(fila)
        assert r["estado"] == "no_rescatable"
        assert r["actual"] == RAD_EN_PORTAL_SIN_CONFIRMAR
        assert fila.estado == RAD_EN_PORTAL_SIN_CONFIRMAR

    @pytest.mark.parametrize(
        "preparar,esperado",
        [
            (lambda d, f: svc.confirmar_radicada(d, f.id, "COO-1"), RAD_RADICADA),
            (lambda d, f: svc.marcar_fallida(d, f.id, "x"), RAD_FALLIDA),
            (lambda d, f: svc.marcar_humano_requerido(d, f.id, "x"), RAD_HUMANO_REQUERIDO),
        ],
    )
    def test_una_fila_que_ya_llego_a_su_sitio_no_se_toca(self, db, preparar, esperado):
        fila = _fila_reclamada(db)
        preparar(db, fila)

        r = svc.rescatar_reclamada(db, fila.id, "aviso tardío del bot")

        db.refresh(fila)
        assert r["estado"] == "no_rescatable"
        assert fila.estado == esperado

    def test_una_pendiente_no_se_rescata_dos_veces(self, db):
        """Carrera normal: el bot avisa dos veces de la misma caída."""
        fila = _fila_reclamada(db)
        svc.rescatar_reclamada(db, fila.id, "se cayó")
        r = svc.rescatar_reclamada(db, fila.id, "se cayó (aviso repetido)")
        assert r["estado"] == "no_rescatable"
        db.refresh(fila)
        assert fila.estado == RAD_PENDIENTE

    def test_una_radicacion_que_no_existe(self, db):
        assert svc.rescatar_reclamada(db, 999999, "x")["estado"] == "no_existe"


# ══════════════════════════════════════════════════════════════════════════
#  4) La caída del worker, simulada de punta a punta
# ══════════════════════════════════════════════════════════════════════════


class _ColaFalsa:
    """Reemplaza a `ColaMotor` sin red: apunta qué le pidieron al motor."""

    entregada = {"radicacion_id": 77, "factura": "HUS940001", "glosa_id": 5}

    def __init__(self, *a, **kw):
        self.llamadas: list[tuple] = []
        self.reclamos = 0

    def reclamar(self):
        self.reclamos += 1
        return dict(self.entregada) if self.reclamos == 1 else None

    def rescatar(self, rid, error):
        self.llamadas.append(("rescatar", rid, error))

    def humano_requerido(self, rid, motivo):
        self.llamadas.append(("humano_requerido", rid, motivo))

    def fallida(self, rid, error):
        self.llamadas.append(("fallida", rid, error))

    def en_portal(self, rid):
        self.llamadas.append(("en_portal", rid))

    def radicada(self, rid, radicado, ruta="", sha=""):
        self.llamadas.append(("radicada", rid, radicado))
        return {}

    def cerrar(self):
        pass


@pytest.fixture
def bot(monkeypatch):
    """`radicador_comun` con la cola falsa y el token puesto."""
    import radicador_comun

    monkeypatch.setenv("AGENTE_LOTES_TOKEN", TOKEN_AGENTE)
    cola = _ColaFalsa()
    monkeypatch.setattr(radicador_comun, "ColaMotor", lambda *a, **kw: cola)
    return radicador_comun, cola


ARGS = SimpleNamespace(
    limite=1, piloto_ok=False, motor="http://127.0.0.1:8080", con_cabeza=False, lento=False
)


class TestElWorkerSeCaeConLaFilaEnLaMano:
    def test_sin_playwright_instalado_la_fila_vuelve_a_la_cola(self, bot, monkeypatch):
        """El caso exacto que abrió el boquete: el PC del auditor no tiene
        playwright, el import revienta y la glosa se quedaba en el limbo."""
        mod, cola = bot

        # Se esconde playwright del import, como en un PC sin instalar.
        monkeypatch.setitem(sys.modules, "playwright.sync_api", None)

        codigo = mod.correr(
            "COOSALUD",
            ARGS,
            abrir_sesion=lambda pw, a: (_ for _ in ()).throw(AssertionError("no debió llegar acá")),
            radicar=lambda p, f: ("", ""),
        )

        assert codigo == 2
        assert [c[0] for c in cola.llamadas] == ["rescatar"]
        assert cola.llamadas[0][1] == 77
        assert "playwright" in cola.llamadas[0][2]

    def test_si_el_navegador_no_arranca_tambien_vuelve(self, bot, monkeypatch):
        mod, cola = bot

        class _GestorRoto:
            def __enter__(self):
                raise RuntimeError("Executable doesn't exist: chromium")

            def __exit__(self, *a):
                return False

        monkeypatch.setitem(
            sys.modules,
            "playwright.sync_api",
            SimpleNamespace(sync_playwright=lambda: _GestorRoto()),
        )

        codigo = mod.correr("COOSALUD", ARGS, lambda pw, a: (None, lambda: None), lambda p, f: "")

        assert codigo == 2
        assert cola.llamadas[0][0] == "rescatar"
        assert "chromium" in cola.llamadas[0][2]

    def test_si_el_portal_no_abre_por_otra_razon_tambien_vuelve(self, bot, monkeypatch):
        mod, cola = bot
        _falso_playwright(monkeypatch)

        def se_cae(pw, a):
            raise RuntimeError("Timeout 30000ms exceeded")

        codigo = mod.correr("COOSALUD", ARGS, se_cae, lambda p, f: "")

        assert codigo == 2
        assert cola.llamadas[0][0] == "rescatar"
        assert "Timeout" in cola.llamadas[0][2]

    def test_el_captcha_sigue_yendo_a_humano_no_a_la_cola(self, bot, monkeypatch):
        """Regresión: un portal que exige una persona NO es una caída del
        equipo. Esa fila no debe volver a rebotar entre PCs."""
        mod, cola = bot
        _falso_playwright(monkeypatch)

        def pide_persona(pw, a):
            raise mod.SesionNoDisponible("MUTUAL SER pide reCAPTCHA: use --cdp")

        codigo = mod.correr("COOSALUD", ARGS, pide_persona, lambda p, f: "")

        assert codigo == 3
        assert [c[0] for c in cola.llamadas] == ["humano_requerido"]

    def test_cuando_el_bucle_ya_manda_el_rescate_no_se_entromete(self, bot, monkeypatch):
        """Adentro del bucle cada fila llega sola a su estado: si acá se
        rescatara, se estaría devolviendo algo ya pulsado en el portal."""
        mod, cola = bot
        _falso_playwright(monkeypatch)

        def revienta_radicando(page, fila):
            raise RuntimeError("el portal cambió de pantalla")

        mod.correr("COOSALUD", ARGS, lambda pw, a: (object(), lambda: None), revienta_radicando)

        acciones = [c[0] for c in cola.llamadas]
        assert "rescatar" not in acciones
        assert acciones == ["en_portal", "fallida"]

    def test_si_no_hay_nada_pendiente_no_se_rescata_nada(self, bot, monkeypatch):
        mod, cola = bot
        monkeypatch.setattr(cola, "reclamar", lambda: None)
        assert mod.correr("COOSALUD", ARGS, lambda pw, a: None, lambda p, f: "") == 0
        assert cola.llamadas == []

    def test_avisar_de_la_caida_no_puede_tapar_la_caida(self, monkeypatch):
        """Si el motor también está caído, el auditor tiene que ver el motivo
        real, no una traza de red encima."""
        import radicador_comun

        class _ClienteRoto:
            def post(self, *a, **kw):
                raise ConnectionError("el motor no responde")

        cola = radicador_comun.ColaMotor.__new__(radicador_comun.ColaMotor)
        cola.base = "http://127.0.0.1:8080"
        cola._c = _ClienteRoto()
        cola.rescatar(1, "se cayó")  # no levanta: eso es todo lo que se pide


def _falso_playwright(monkeypatch):
    """Un playwright de mentira que entra y sale sin abrir nada."""

    class _Gestor:
        def __enter__(self):
            return SimpleNamespace()

        def __exit__(self, *a):
            return False

    monkeypatch.setitem(
        sys.modules, "playwright.sync_api", SimpleNamespace(sync_playwright=lambda: _Gestor())
    )


# ══════════════════════════════════════════════════════════════════════════
#  5) La puerta del agente
# ══════════════════════════════════════════════════════════════════════════


@pytest.fixture
def cliente(db, monkeypatch):
    from app.main import app

    monkeypatch.setenv("AGENTE_LOTES_TOKEN", TOKEN_AGENTE)
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


class TestLaPuertaDelAgente:
    def test_el_bot_devuelve_la_fila_por_http(self, cliente, db):
        fila = _fila_reclamada(db)
        r = cliente.post(
            f"/radicacion/{fila.id}/rescatar",
            json={"error": "a este PC le falta playwright"},
            headers={"X-Agente-Token": TOKEN_AGENTE},
        )
        assert r.status_code == 200
        assert r.json()["estado"] == RAD_PENDIENTE
        db.refresh(fila)
        assert fila.estado == RAD_PENDIENTE

    def test_sin_token_no_entra(self, cliente, db):
        fila = _fila_reclamada(db)
        r = cliente.post(f"/radicacion/{fila.id}/rescatar", json={"error": "x"})
        assert r.status_code == 401
        db.refresh(fila)
        assert fila.estado == RAD_RECLAMADA

    def test_una_radicacion_inexistente_da_404(self, cliente):
        r = cliente.post(
            "/radicacion/999999/rescatar",
            json={"error": "x"},
            headers={"X-Agente-Token": TOKEN_AGENTE},
        )
        assert r.status_code == 404

    def test_hace_falta_decir_de_que_se_murio(self, cliente, db):
        fila = _fila_reclamada(db)
        r = cliente.post(
            f"/radicacion/{fila.id}/rescatar",
            json={"error": ""},
            headers={"X-Agente-Token": TOKEN_AGENTE},
        )
        assert r.status_code == 422
