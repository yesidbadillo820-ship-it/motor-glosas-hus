"""V3 · Pilar 1, fase final — bandeja «En espera de EPS» y los tres radicadores.

Lo que estas pruebas cuidan:

1. LA BANDEJA MUESTRA LO QUE IMPORTA. El radicado y la huella SHA-256 de lo
   que sí quedó; y, separado, lo que está atorado esperando a una persona.
2. RESOLVER NO ES REINTENTAR. Los botones de la bandeja son la ÚNICA salida
   de «no sé si quedó»; y decir «sí quedó» escribe la evidencia.
3. LOS TRES BOTS COMPARTEN UN SOLO PATRÓN. La conversación con el motor vive
   en un módulo común: un arreglo vale para los tres.
4. MUTUAL SER NO FINGE AUTONOMÍA. Ese portal pide reCAPTCHA; sin sesión
   sembrada, la glosa se marca HUMANO_REQUERIDO en vez de fallar a ciegas.
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
    RAD_HUMANO_REQUERIDO,
    RAD_PENDIENTE,
    RAD_RADICADA,
    RAD_VERIFICAR_MANUAL,
    GlosaRecord,
    RadicacionEpsRecord,
)
from app.services import radicacion_eps as svc

RAIZ = Path(__file__).resolve().parents[2]
_TOOLS = RAIZ / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

DICTAMEN = (
    "<div>ESE HUS NO ACEPTA LA GLOSA. El expediente reposa completo en el archivo "
    "institucional y la objeción fue notificada fuera del término legal. Se sostiene "
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
        factura="HUS910001",
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


# ══════════════════════════════════════════════════════════════════════════
#  1) La bandeja
# ══════════════════════════════════════════════════════════════════════════


class TestLaBandejaMuestraLoQueImporta:
    def test_la_cola_devuelve_radicado_y_huella(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        svc.confirmar_radicada(db_session, fila.id, "COO-4455", "/ruta/comp.png", "a" * 64)

        d = cliente.get("/radicacion/cola").json()
        f = next(x for x in d["filas"] if x["id"] == fila.id)
        assert f["radicado_numero"] == "COO-4455"
        assert f["comprobante_sha256"] == "a" * 64
        assert f["estado"] == RAD_RADICADA

    def test_el_resumen_cuenta_por_estado(self, cliente, db_session):
        for i, eps in enumerate(("COOSALUD", "FOMAG", "NUEVA EPS")):
            _glosa(db_session, eps=eps, factura=f"HUS9200{i}")
        cliente.post(
            "/radicacion/encolar",
            json={"glosa_ids": [g.id for g in db_session.query(GlosaRecord).all()]},
        )
        d = cliente.get("/radicacion/cola").json()
        assert d["por_estado"].get(RAD_PENDIENTE) == 1  # solo COOSALUD
        assert d["por_estado"].get(RAD_HUMANO_REQUERIDO) == 2  # captcha/token

    def test_se_puede_filtrar_lo_atorado(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        svc.marcar_en_portal(db_session, fila.id)
        svc.marcar_fallida(db_session, fila.id, "se cortó la red")

        d = cliente.get(f"/radicacion/cola?estado={RAD_VERIFICAR_MANUAL}").json()
        assert d["total"] == 1 and d["filas"][0]["id"] == fila.id


class TestResolverNoEsReintentar:
    def test_decir_que_si_quedo_escribe_la_evidencia(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        svc.marcar_en_portal(db_session, fila.id)
        svc.marcar_fallida(db_session, fila.id, "corte")

        r = cliente.post(
            f"/radicacion/{fila.id}/verificar",
            json={"quedo_radicada": True, "radicado_numero": "COO-9001"},
        )
        assert r.status_code == 200
        db_session.refresh(fila)
        db_session.refresh(g)
        assert fila.estado == RAD_RADICADA and fila.radicado_numero == "COO-9001"
        assert fila.verificado_por == "coord@hus.gov.co"
        assert g.workflow_state == "RADICADA_EN_EPS"

    def test_decir_que_no_quedo_la_devuelve_a_la_cola(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        svc.marcar_en_portal(db_session, fila.id)
        svc.marcar_fallida(db_session, fila.id, "corte")

        cliente.post(f"/radicacion/{fila.id}/verificar", json={"quedo_radicada": False})
        db_session.refresh(fila)
        assert fila.estado == RAD_PENDIENTE

    def test_lo_no_atorado_no_se_puede_resolver(self, cliente, db_session):
        g = _glosa(db_session)
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        r = cliente.post(f"/radicacion/{fila.id}/verificar", json={"quedo_radicada": True})
        assert r.status_code == 409

    def test_una_de_portal_manual_se_puede_dar_por_radicada_a_mano(self, cliente, db_session):
        """FOMAG/DGH/NUEVA EPS los hace una persona; tiene que poder cerrarlos."""
        g = _glosa(db_session, eps="FOMAG", factura="HUS930001")
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = db_session.query(RadicacionEpsRecord).filter_by(glosa_id=g.id).one()
        assert fila.estado == RAD_HUMANO_REQUERIDO
        svc.marcar_fallida(db_session, fila.id, "pendiente de hacer a mano")
        db_session.refresh(fila)
        # No estaba en la duda, así que cae a FALLIDA y se puede reencolar.
        assert fila.estado != RAD_VERIFICAR_MANUAL


# ══════════════════════════════════════════════════════════════════════════
#  2) El contrato de la pantalla
# ══════════════════════════════════════════════════════════════════════════


class TestLaPantallaDeLaBandeja:
    @pytest.fixture(scope="class")
    def js(self):
        return (RAIZ / "static" / "healthtech.js").read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def html(self):
        return (RAIZ / "static" / "index.html").read_text(encoding="utf-8")

    def test_hay_boton_para_abrirla(self, html):
        assert "verBandejaEsperaEPS()" in html
        assert "En espera de EPS" in html

    def test_la_bandeja_lee_el_libro(self, js):
        assert "HT.abrirBandejaEspera" in js
        assert "/radicacion/cola" in js

    def test_muestra_radicado_y_huella(self, js):
        assert "radicado_numero" in js
        assert "comprobante_sha256" in js
        assert "SHA-256" in js

    def test_separa_lo_atorado_de_lo_demas(self, js):
        assert "EN_PORTAL_SIN_CONFIRMAR" in js and "VERIFICAR_MANUAL" in js
        assert "HUMANO_REQUERIDO" in js
        assert "Necesitan que usted mire el portal" in js

    def test_los_botones_resuelven_por_la_via_correcta(self, js):
        assert "HT.resolverRadicacion" in js
        assert "/verificar" in js
        assert "quedo_radicada" in js


# ══════════════════════════════════════════════════════════════════════════
#  3) Los tres bots, un solo patrón
# ══════════════════════════════════════════════════════════════════════════


class TestUnSoloPatronParaLosTres:
    @pytest.mark.parametrize(
        "modulo,portal",
        [
            ("radicar_glosas_coosalud", "COOSALUD"),
            ("radicar_glosas_simed", "SIMED"),
            ("radicar_glosas_mutual_ser", "MUTUAL_SER"),
        ],
    )
    def test_cada_bot_declara_su_portal_y_usa_el_molde_comun(self, modulo, portal):
        import importlib

        m = importlib.import_module(modulo)
        assert m.PORTAL == portal
        # Las tres piezas del patrón, en los tres bots.
        assert callable(m.abrir_sesion) and callable(m.radicar) and callable(m.main)
        assert m.limite_efectivo(1, False) == 1

    @pytest.mark.parametrize(
        "modulo", ["radicar_glosas_coosalud", "radicar_glosas_simed", "radicar_glosas_mutual_ser"]
    )
    def test_el_piloto_es_obligatorio_en_los_tres(self, modulo):
        import importlib

        m = importlib.import_module(modulo)
        with pytest.raises(m.PilotoNoConfirmado):
            m.limite_efectivo(50, piloto_ok=False)
        assert m.limite_efectivo(50, piloto_ok=True) == 50

    def test_la_conversacion_con_el_motor_vive_en_un_solo_sitio(self):
        """Si algún bot vuelve a hablar con el motor por su cuenta, un arreglo
        dejaría de valer para los tres."""
        for nombre in (
            "radicar_glosas_coosalud.py",
            "radicar_glosas_simed.py",
            "radicar_glosas_mutual_ser.py",
        ):
            fuente = (_TOOLS / nombre).read_text(encoding="utf-8")
            assert "radicador_comun" in fuente, f"{nombre} no usa el módulo común"
            assert "/radicacion/reclamar" not in fuente, (
                f"{nombre} volvió a hablar con el motor por su cuenta"
            )

    def test_ninguno_manda_credenciales_al_motor(self):
        comun = (_TOOLS / "radicador_comun.py").read_text(encoding="utf-8")
        assert "Nunca credenciales" in comun
        # Lo que se envía en el reclamo son solo portal y equipo.
        assert '"portal": self.portal' in comun and '"equipo": self.equipo' in comun


class TestElBotRespondeAunqueFaltePlaywright:
    """CI en rojo desde el 04-09 por un guardián que sobraba.

    `abrir_sesion` empezaba llamando a `_exigir_playwright()`, que ante la
    ausencia de la librería mata el proceso con `sys.exit(2)`. Dos problemas:

      · **Era inalcanzable en producción.** `radicador_comun.correr()` importa
        `sync_playwright` y abre su contexto ANTES de llamar a `abrir_sesion`:
        si faltara, el proceso ni llega hasta ahí.
      · **Donde sí se alcanzaba, hacía daño.** Mataba el proceso en vez de
        dejar que la función diera su respuesta honesta —`SesionNoDisponible`—,
        que es la que manda la glosa a manos de una persona con el instructivo
        del `--cdp`. Y en el runner de CI, que no instala playwright, tumbaba
        tres pruebas en toda rama que se abriera.

    Estas pruebas fijan la conducta: la decisión de «no hay sesión» se toma
    mirando el disco, no el navegador.
    """

    @pytest.fixture
    def sin_playwright(self, monkeypatch):
        """Simula un PC (o un runner de CI) sin playwright instalado."""
        import responder_glosas_coosalud
        import responder_glosas_mutual_ser
        import responder_glosas_simed

        for modulo in (
            responder_glosas_mutual_ser,
            responder_glosas_simed,
            responder_glosas_coosalud,
        ):
            monkeypatch.setattr(modulo, "sync_playwright", None, raising=False)

    def test_mutual_ser_avisa_en_vez_de_matar_el_proceso(self, sin_playwright, tmp_path):
        import radicar_glosas_mutual_ser as bot

        args = SimpleNamespace(
            storage_state=str(tmp_path / "no_existe.json"),
            con_cabeza=False,
            lento=False,
            cdp="",
        )
        with pytest.raises(bot.SesionNoDisponible) as e:
            bot.abrir_sesion(None, args)
        assert "--cdp" in str(e.value)

    @pytest.mark.parametrize("modulo", ["radicar_glosas_simed", "radicar_glosas_coosalud"])
    def test_ningun_radicador_conserva_el_guardian_que_sobraba(self, modulo):
        """El mismo guardián estaba copiado en los tres bots. Si vuelve a
        aparecer en cualquiera, esta prueba lo delata."""
        import importlib
        import inspect

        fuente = inspect.getsource(importlib.import_module(modulo).abrir_sesion)
        assert "_exigir_playwright()" not in fuente

    def test_mutual_ser_tampoco_lo_conserva(self):
        import inspect

        import radicar_glosas_mutual_ser as bot

        assert "_exigir_playwright()" not in inspect.getsource(bot.abrir_sesion)


class TestMutualSerNoFingeAutonomia:
    def test_sin_sesion_sembrada_no_intenta_el_captcha(self, tmp_path):
        import radicar_glosas_mutual_ser as bot

        args = SimpleNamespace(
            storage_state=str(tmp_path / "no_existe.json"),
            con_cabeza=False,
            lento=False,
            cdp="",
        )
        with pytest.raises(bot.SesionNoDisponible) as e:
            bot.abrir_sesion(None, args)
        assert "reCAPTCHA" in str(e.value)
        # El consejo tiene que ser el CAMINO FIABLE, no el que el repositorio
        # advierte que falla. Antes decía «--con-cabeza» a secas y eso mandaba
        # al auditor de frente contra el captcha (04-09-2026).
        assert "--cdp" in str(e.value), "no ofrece el camino que de verdad funciona"
        assert "9222" in str(e.value), "no dice cómo abrir su Chrome"

    def test_se_engancha_al_chrome_del_auditor(self, monkeypatch):
        """El camino recomendado: la sesión humana ya validada."""
        import radicador_comun
        import radicar_glosas_mutual_ser as bot

        class _Page:
            url = "https://zonaser.mutualser.org/glosas"

            def set_default_navigation_timeout(self, *_a):
                pass

            def set_default_timeout(self, *_a):
                pass

            def on(self, *_a):
                pass

        class _Ctx:
            pages = [_Page()]

        class _Browser:
            contexts = [_Ctx()]
            cerrado = False

            def close(self):
                _Browser.cerrado = True

        monkeypatch.setattr(radicador_comun, "conectar_cdp", lambda pw, url: _Browser())
        monkeypatch.setattr(bot, "conectar_cdp", lambda pw, url: _Browser())
        monkeypatch.setattr(
            "responder_glosas_mutual_ser._login_ok", lambda page: True, raising=False
        )

        args = SimpleNamespace(
            cdp="http://127.0.0.1:9222", storage_state="x", con_cabeza=False, lento=False
        )
        page, cerrar = bot.abrir_sesion(None, args)
        assert page is not None
        cerrar()
        assert _Browser.cerrado is False, (
            "el radicador cerró el Chrome del auditor: ese navegador no es suyo"
        )

    def test_conectado_pero_sin_sesion_no_pulsa_nada(self, monkeypatch):
        """Enganchado al Chrome pero sin login: NO se toca el portal."""
        import radicar_glosas_mutual_ser as bot

        class _Page:
            url = "about:blank"

            def set_default_navigation_timeout(self, *_a):
                pass

            def set_default_timeout(self, *_a):
                pass

            def on(self, *_a):
                pass

        class _Ctx:
            pages = [_Page()]

        class _Browser:
            contexts = [_Ctx()]

        monkeypatch.setattr(bot, "conectar_cdp", lambda pw, url: _Browser())
        monkeypatch.setattr(
            "responder_glosas_mutual_ser._login_ok", lambda page: False, raising=False
        )
        args = SimpleNamespace(
            cdp="http://127.0.0.1:9222", storage_state="x", con_cabeza=False, lento=False
        )
        with pytest.raises(bot.SesionNoDisponible) as e:
            bot.abrir_sesion(None, args)
        assert "no hay sesión abierta" in str(e.value)

    def test_el_helper_cdp_prueba_ipv4_cuando_localhost_falla(self, monkeypatch):
        """En Windows «localhost» resuelve a IPv6 y Chrome escucha en IPv4."""
        import radicador_comun

        intentos = []

        class _PW:
            class chromium:
                @staticmethod
                def connect_over_cdp(url):
                    intentos.append(url)
                    if "127.0.0.1" not in url:
                        raise RuntimeError("ECONNREFUSED")
                    return "browser"

        assert radicador_comun.conectar_cdp(_PW, "http://localhost:9222") == "browser"
        assert intentos == ["http://localhost:9222", "http://127.0.0.1:9222"]

    def test_si_no_hay_chrome_lo_dice_con_el_comando_exacto(self):
        import radicador_comun

        class _PW:
            class chromium:
                @staticmethod
                def connect_over_cdp(url):
                    raise RuntimeError("no hay nadie ahí")

        with pytest.raises(radicador_comun.SesionNoDisponible) as e:
            radicador_comun.conectar_cdp(_PW, "http://127.0.0.1:9222")
        assert "--remote-debugging-port=9222" in str(e.value)

    def test_el_catalogo_avisa_del_captcha(self):
        from app.services import bots_hus

        b = bots_hus.obtener("mutualser-radicar")
        assert b is not None
        assert "reCAPTCHA" in (b.riesgo or "")
        assert "PILOTO" in (b.riesgo or "").upper()

    def test_los_tres_bots_estan_en_el_catalogo(self):
        from app.services import bots_hus

        for bot_id in ("coosalud-radicar", "simed-radicar", "mutualser-radicar"):
            b = bots_hus.obtener(bot_id)
            assert b is not None, f"falta {bot_id} en el catálogo"
            assert b.donde_corre == "pc_hus"
            assert "PILOTO" in (b.riesgo or "").upper()


class TestLaColaEntregaLoQueElPortalNecesita:
    def test_incluye_el_codigo_de_respuesta(self, cliente, db_session):
        """Mutual Ser pide el código al cerrar. Sin él, el bot lo adivinaría."""
        g = _glosa(db_session, codigo_respuesta="RE9502")
        cliente.post("/radicacion/encolar", json={"glosa_ids": [g.id]})
        fila = svc.reclamar_una(db_session, "COOSALUD", equipo="PC-PRUEBA")
        assert fila is not None
        assert fila["codigo_respuesta"] == "RE9502"
