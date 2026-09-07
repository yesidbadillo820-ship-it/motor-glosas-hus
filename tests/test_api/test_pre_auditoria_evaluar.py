"""POST /pre-auditoria/evaluar — el trato con el HIS (V3, Pilar 2 — 04-09-2026).

Del otro lado de esta ruta hay un programa, no una persona: el HIS del
hospital la llama antes de timbrar cada factura y el facturador está mirando
la pantalla mientras tanto. Lo que estas pruebas protegen:

  · **La forma no cambia nunca.** `status`, `alertas`, `valor_en_riesgo` y
    `recomendacion_accion` salen siempre, pase lo que pase.
  · **El reloj se respeta.** Techo duro de 10 s; si la IA se cuelga, se corta
    y se responde igual.
  · **Una IA caída no paraliza el hospital.** Es la lección del candado 423
    que hubo que quitar el 04-09: una medida de seguridad que detiene la
    operación no es seguridad, es un paro.
  · **Queda constancia.** Una fila en `pre_auditoria_eventos` por evaluación.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routers.pre_auditoria import quien_pregunta
from app.core.config import get_settings
from app.database import Base, get_db
from app.models.db import PreAuditoriaEventoRecord, UsuarioRecord

TOKEN_HIS = "token-del-his-para-pruebas-0123456789"

FACTURA_SANA = {
    "factura": "HUS500123",
    "eps": "COOSALUD",
    "paciente": {"documento": "CC1098765", "sexo": "F", "edad_anios": 34},
    "atencion": {
        "tipo": "HOSPITALIZACION",
        "fecha_ingreso": "2026-09-01",
        "fecha_egreso": "2026-09-03",
        "dias_estancia": 2,
    },
    "items": [
        {
            "cups": "890201",
            "descripcion": "CONSULTA DE PRIMERA VEZ",
            "tipo": "CONSULTA",
            "cantidad": 1,
            "valor_unitario": 60000,
            "valor_total": 60000,
            "fecha": "2026-09-01",
        }
    ],
    "valor_total": 60000,
    "epicrisis": "Paciente valorada, egresa estable.",
}

FACTURA_ROTA = {
    "factura": "HUS500999",
    "eps": "COOSALUD",
    "paciente": {"sexo": "M", "edad_anios": 41},
    "atencion": {"fecha_ingreso": "2026-09-01", "fecha_egreso": "2026-09-03"},
    "items": [
        {
            "cups": "740101",
            "descripcion": "PARTO VAGINAL ESPONTÁNEO",
            "tipo": "QUIRURGICO",
            "cantidad": 1,
            "valor_unitario": 800000,
            "valor_total": 800000,
        }
    ],
    "valor_total": 800000,
    "epicrisis": "Atención de urgencias.",
}


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    sesion = sessionmaker(bind=eng)()
    try:
        yield sesion
    finally:
        sesion.close()
        eng.dispose()


@pytest.fixture
def cliente(db, monkeypatch):
    """Cliente con la puerta del HIS abierta y SIN IA configurada.

    Sin `GROQ_API_KEY` el cruce clínico se salta limpiamente: así estas
    pruebas miden el contrato y las reglas duras, no la red.
    """
    from app.main import app

    monkeypatch.setenv("AGENTE_LOTES_TOKEN", TOKEN_HIS)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    get_settings.cache_clear()
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        get_settings.cache_clear()


def evaluar(cliente, payload, **kw):
    headers = kw.pop("headers", {"X-Agente-Token": TOKEN_HIS})
    return cliente.post("/pre-auditoria/evaluar", json=payload, headers=headers)


# ═══════════════════════════════════════════════════════════════════════
class TestLaTablaExiste:
    def test_create_all_crea_pre_auditoria_eventos(self):
        """La tabla es nueva: `Base.metadata.create_all()` la levanta sola,
        sin ALTER TABLE. Si alguien quita el modelo del metadata, esto lo
        delata antes de que el HIS reciba un 500."""
        eng = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(eng)
        columnas = {c["name"] for c in inspect(eng).get_columns("pre_auditoria_eventos")}
        assert {
            "factura",
            "eps",
            "estado",
            "recomendacion_accion",
            "valor_en_riesgo",
            "payload_base",
            "alertas",
            "cruce_clinico_estado",
            "duracion_ms",
        } <= columnas
        eng.dispose()


# ═══════════════════════════════════════════════════════════════════════
class TestElContratoDeSalida:
    def test_los_cuatro_campos_salen_siempre(self, cliente):
        cuerpo = evaluar(cliente, FACTURA_SANA).json()
        assert {"status", "alertas", "valor_en_riesgo", "recomendacion_accion"} <= set(cuerpo)

    def test_una_factura_sana_se_aprueba_y_se_manda_a_timbrar(self, cliente):
        cuerpo = evaluar(cliente, FACTURA_SANA).json()
        assert cuerpo["status"] == "APROBADO", cuerpo["alertas"]
        assert cuerpo["alertas"] == []
        assert cuerpo["valor_en_riesgo"] == 0.0
        assert cuerpo["recomendacion_accion"] == "TIMBRAR"

    def test_una_factura_imposible_se_bloquea(self, cliente):
        cuerpo = evaluar(cliente, FACTURA_ROTA).json()
        assert cuerpo["status"] == "BLOQUEO"
        assert cuerpo["recomendacion_accion"] == "CORREGIR_ANTES_DE_TIMBRAR"
        assert cuerpo["valor_en_riesgo"] == 800000
        assert any(a["regla"] == "cruce_genero" for a in cuerpo["alertas"])

    def test_un_reparo_menor_solo_advierte(self, cliente):
        payload = json.loads(json.dumps(FACTURA_SANA))
        payload["items"][0]["fecha"] = "2026-12-25"  # fuera del episodio
        cuerpo = evaluar(cliente, payload).json()
        assert cuerpo["status"] == "ADVERTENCIA"
        assert cuerpo["recomendacion_accion"] == "REVISAR_ANTES_DE_TIMBRAR"

    def test_cada_alerta_trae_lo_que_el_facturador_necesita(self, cliente):
        alerta = evaluar(cliente, FACTURA_ROTA).json()["alertas"][0]
        assert set(alerta) == {
            "codigo_glosa",
            "titulo",
            "detalle",
            "severidad",
            "origen",
            "regla",
            "item",
            "valor_en_riesgo",
        }
        assert alerta["titulo"] and alerta["detalle"]

    def test_la_respuesta_dice_como_le_fue_al_cruce_clinico(self, cliente):
        cuerpo = evaluar(cliente, FACTURA_SANA).json()
        assert cuerpo["cruce_clinico"]["estado"] == "OMITIDO_SIN_IA"

    def test_sin_ia_configurada_no_se_ensucia_cada_factura_con_una_advertencia(self, cliente):
        """Un servidor sin IA es un estado del despliegue, no un riesgo de
        esta cuenta. Si avisáramos en todas, nadie leería los avisos."""
        cuerpo = evaluar(cliente, FACTURA_SANA).json()
        assert cuerpo["status"] == "APROBADO"
        assert not any(a["regla"] == "cruce_clinico_incompleto" for a in cuerpo["alertas"])

    def test_una_factura_ilegible_se_rechaza_con_422(self, cliente):
        assert evaluar(cliente, {"items": []}).status_code == 422  # falta la EPS


# ═══════════════════════════════════════════════════════════════════════
class TestLasDosPuertas:
    def test_el_his_entra_con_su_token(self, cliente):
        assert evaluar(cliente, FACTURA_SANA).status_code == 200

    def test_sin_credencial_ninguna_no_entra(self, cliente):
        assert evaluar(cliente, FACTURA_SANA, headers={}).status_code == 401

    def test_con_token_equivocado_no_entra(self, cliente):
        r = evaluar(cliente, FACTURA_SANA, headers={"X-Agente-Token": "otro"})
        assert r.status_code == 401

    def test_sin_token_configurado_la_puerta_del_his_no_existe(self, cliente, monkeypatch):
        """Un despliegue sin configurar no expone la pre-auditoría."""
        monkeypatch.delenv("AGENTE_LOTES_TOKEN", raising=False)
        monkeypatch.setattr(get_settings(), "agente_lotes_token", "", raising=False)
        r = evaluar(cliente, FACTURA_SANA, headers={"X-Agente-Token": "lo-que-sea"})
        assert r.status_code == 503

    def test_una_persona_entra_con_su_sesion(self, db, monkeypatch):
        from app.api import deps
        from app.main import app

        monkeypatch.setenv("AGENTE_LOTES_TOKEN", TOKEN_HIS)
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        get_settings.cache_clear()
        usuario = UsuarioRecord(id=1, email="auditor@hus.gov.co", rol="AUDITOR", activo=1)
        monkeypatch.setattr(deps, "get_usuario_actual", lambda token, db: usuario)
        app.dependency_overrides[get_db] = lambda: db
        try:
            c = TestClient(app)
            r = c.post(
                "/pre-auditoria/evaluar",
                json=FACTURA_SANA,
                headers={"Authorization": "Bearer jwt-de-mentira"},
            )
            assert r.status_code == 200
            fila = db.query(PreAuditoriaEventoRecord).first()
            assert fila.actor == "auditor@hus.gov.co"
        finally:
            app.dependency_overrides.clear()
            get_settings.cache_clear()


# ═══════════════════════════════════════════════════════════════════════
class TestQuedaConstancia:
    def test_cada_evaluacion_deja_su_fila(self, cliente, db):
        cuerpo = evaluar(cliente, FACTURA_ROTA).json()
        fila = db.get(PreAuditoriaEventoRecord, cuerpo["evento_id"])
        assert fila is not None
        assert fila.factura == "HUS500999"
        assert fila.eps == "COOSALUD"
        assert fila.estado == "BLOQUEO"
        assert fila.valor_en_riesgo == 800000
        assert fila.total_alertas == len(cuerpo["alertas"])
        assert fila.actor == "his"
        assert fila.duracion_ms >= 0

    def test_se_guarda_el_payload_tal_como_llego(self, cliente, db):
        """Para poder repetir la evaluación el día que una regla se corrija."""
        cuerpo = evaluar(cliente, FACTURA_ROTA).json()
        fila = db.get(PreAuditoriaEventoRecord, cuerpo["evento_id"])
        guardado = json.loads(fila.payload_base)
        assert guardado["items"][0]["cups"] == "740101"
        assert json.loads(fila.alertas)[0]["regla"]

    def test_la_misma_factura_dos_veces_da_la_misma_huella(self, cliente, db):
        evaluar(cliente, FACTURA_ROTA)
        evaluar(cliente, FACTURA_ROTA)
        huellas = {f.huella_payload for f in db.query(PreAuditoriaEventoRecord).all()}
        assert len(huellas) == 1, "el HIS reintentó lo mismo y no se nota"

    def test_si_la_base_falla_la_respuesta_sale_igual(self, cliente, monkeypatch):
        """El facturador no puede quedarse esperando por un problema nuestro."""
        import app.services.preauditoria_concurrente as mod

        monkeypatch.setattr(mod, "_guardar_evento", lambda *a, **kw: None)
        cuerpo = evaluar(cliente, FACTURA_ROTA).json()
        assert cuerpo["status"] == "BLOQUEO"
        assert cuerpo["evento_id"] is None


# ═══════════════════════════════════════════════════════════════════════
class TestElLibroSeConsulta:
    def test_el_auditor_ve_lo_pre_auditado(self, cliente, db, monkeypatch):
        from app.api import deps
        from app.main import app

        evaluar(cliente, FACTURA_ROTA)
        usuario = UsuarioRecord(id=1, email="auditor@hus.gov.co", rol="AUDITOR", activo=1)
        app.dependency_overrides[deps.get_auditor_o_superior] = lambda: usuario

        filas = cliente.get("/pre-auditoria/eventos").json()
        assert len(filas) == 1 and filas[0]["estado"] == "BLOQUEO"

        detalle = cliente.get(f"/pre-auditoria/eventos/{filas[0]['id']}").json()
        assert detalle["alertas"] and detalle["alertas"][0]["titulo"]

        assert cliente.get("/pre-auditoria/eventos/999999").status_code == 404

    def test_el_libro_no_esta_abierto_a_cualquiera(self, cliente):
        assert cliente.get("/pre-auditoria/eventos").status_code == 401


# ═══════════════════════════════════════════════════════════════════════
class TestElRelojManda:
    def test_el_presupuesto_no_puede_pasar_de_diez_segundos(self):
        """La cuenta, escrita: reglas + IA + escritura ≤ 10 s."""
        from app.services import preauditoria_concurrente as motor
        from app.services import preauditoria_cruce_clinico as cruce

        assert motor.PRESUPUESTO_TOTAL_S == 10.0
        assert cruce.TOPE_IA_S <= 6.0
        # Peor caso: la IA consume su tope entero y aún queda la reserva.
        assert cruce.TOPE_IA_S + motor.RESERVA_ESCRITURA_S < motor.PRESUPUESTO_TOTAL_S

    def test_si_no_queda_tiempo_la_ia_ni_se_intenta(self):
        from app.services.preauditoria_cruce_clinico import MINIMO_IA_S, presupuesto_util

        assert presupuesto_util(0.4) == 0.0
        assert presupuesto_util(MINIMO_IA_S) == MINIMO_IA_S
        assert presupuesto_util(600.0) <= 6.0

    def test_una_ia_colgada_se_corta_y_la_factura_se_dictamina_igual(self, cliente, monkeypatch):
        import app.services.preauditoria_cruce_clinico as cruce

        async def se_cuelga(*a, **kw):
            await asyncio.sleep(60)

        monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
        # Se acorta el reloj para no dormir 6 s en cada corrida: lo que se
        # prueba es que el corte EXISTA y que la respuesta salga igual.
        monkeypatch.setattr(cruce, "MINIMO_IA_S", 0.2)
        monkeypatch.setattr(cruce, "TOPE_IA_S", 0.5)
        monkeypatch.setattr(cruce, "_llamar_groq", se_cuelga)

        cuerpo = evaluar(cliente, FACTURA_ROTA).json()
        assert cuerpo["cruce_clinico"]["estado"] == "TIMEOUT"
        assert cuerpo["duracion_ms"] < 10_000, "se pasó del techo prometido al HIS"
        # Las reglas duras hicieron su trabajo pese a la IA caída:
        assert cuerpo["status"] == "BLOQUEO"
        assert any(a["regla"] == "cruce_genero" for a in cuerpo["alertas"])

    def test_cuando_la_ia_falla_esta_factura_lo_dice(self, cliente, monkeypatch):
        """Distinto de «no encontramos nada»: esta cuenta recibió menos
        revisión que las demás y el facturador tiene que saberlo."""
        import app.services.preauditoria_cruce_clinico as cruce

        async def revienta(*a, **kw):
            raise RuntimeError("Groq 500")

        monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
        monkeypatch.setattr(cruce, "_llamar_groq", revienta)

        cuerpo = evaluar(cliente, FACTURA_SANA).json()
        assert cuerpo["cruce_clinico"]["estado"] == "ERROR"
        assert cuerpo["status"] == "ADVERTENCIA"
        avisos = [a for a in cuerpo["alertas"] if a["regla"] == "cruce_clinico_incompleto"]
        assert len(avisos) == 1
        assert avisos[0]["valor_en_riesgo"] == 0.0  # no infla la cifra


# ═══════════════════════════════════════════════════════════════════════
class TestElHisMandaLoQuePuede:
    """Rígidos en la salida, tolerantes en la entrada: el HIS es un sistema
    viejo y no vamos a rechazar una factura por el formato de una fecha."""

    @pytest.mark.parametrize(
        "fecha", ["2026-09-01", "01/09/2026", "2026-09-01T08:30:00", "2026-09-01 08:30"]
    )
    def test_acepta_las_fechas_como_vengan(self, cliente, fecha):
        payload = json.loads(json.dumps(FACTURA_SANA))
        payload["atencion"]["fecha_ingreso"] = fecha
        assert evaluar(cliente, payload).status_code == 200

    def test_una_fecha_ilegible_no_tumba_la_evaluacion(self, cliente):
        payload = json.loads(json.dumps(FACTURA_SANA))
        payload["atencion"]["fecha_ingreso"] = "no es una fecha"
        assert evaluar(cliente, payload).status_code == 200

    @pytest.mark.parametrize("sexo", ["M", "MASCULINO", "Hombre", "1"])
    def test_entiende_el_sexo_como_lo_escriba_el_his(self, cliente, sexo):
        payload = json.loads(json.dumps(FACTURA_ROTA))
        payload["paciente"]["sexo"] = sexo
        cuerpo = evaluar(cliente, payload).json()
        assert any(a["regla"] == "cruce_genero" for a in cuerpo["alertas"])

    def test_los_campos_que_no_conocemos_se_ignoran(self, cliente):
        payload = json.loads(json.dumps(FACTURA_SANA))
        payload["campo_raro_del_his"] = {"lo": "que sea"}
        payload["items"][0]["otro_campo"] = 123
        assert evaluar(cliente, payload).status_code == 200

    def test_una_factura_sin_epicrisis_se_evalua_igual(self, cliente):
        payload = json.loads(json.dumps(FACTURA_SANA))
        payload.pop("epicrisis")
        assert evaluar(cliente, payload).json()["status"] == "APROBADO"

    def test_si_no_mandan_el_total_se_suman_las_lineas(self, cliente):
        payload = json.loads(json.dumps(FACTURA_SANA))
        payload.pop("valor_total")
        assert evaluar(cliente, payload).json()["valor_factura"] == 60000


# ═══════════════════════════════════════════════════════════════════════
class TestLaIaNuncaBloquea:
    """Doctrina del proyecto: la IA opina, Python decide."""

    def _con_respuesta(self, monkeypatch, contenido: str):
        import app.services.preauditoria_cruce_clinico as cruce

        async def responde(*a, **kw):
            return contenido

        monkeypatch.setenv("GROQ_API_KEY", "clave-de-prueba")
        monkeypatch.setattr(cruce, "_llamar_groq", responde)

    def test_un_hallazgo_de_la_ia_es_advertencia_no_bloqueo(self, cliente, monkeypatch):
        self._con_respuesta(
            monkeypatch,
            '{"hallazgos":[{"item":"890201","motivo":"la epicrisis no menciona la consulta"}]}',
        )
        cuerpo = evaluar(cliente, FACTURA_SANA).json()
        assert cuerpo["status"] == "ADVERTENCIA"
        ia = [a for a in cuerpo["alertas"] if a["origen"] == "IA"]
        assert len(ia) == 1
        assert ia[0]["severidad"] == "ADVERTENCIA"
        assert ia[0]["codigo_glosa"] == "CL0201"
        assert ia[0]["valor_en_riesgo"] == 60000

    def test_un_hallazgo_sobre_un_item_que_no_existe_se_descarta(self, cliente, monkeypatch):
        """Alucinación clásica: el modelo inventa un CUPS que no está en la
        factura. Se tira sin contemplaciones."""
        self._con_respuesta(monkeypatch, '{"hallazgos":[{"item":"999999","motivo":"inventado"}]}')
        cuerpo = evaluar(cliente, FACTURA_SANA).json()
        assert cuerpo["status"] == "APROBADO"
        assert cuerpo["cruce_clinico"]["estado"] == "OK"

    def test_una_respuesta_que_no_es_json_no_rompe_nada(self, cliente, monkeypatch):
        self._con_respuesta(monkeypatch, "Claro, con gusto reviso la factura...")
        cuerpo = evaluar(cliente, FACTURA_SANA).json()
        assert cuerpo["status"] == "APROBADO"
        assert cuerpo["cruce_clinico"]["estado"] == "OK"

    def test_el_json_envuelto_en_markdown_igual_se_lee(self, cliente, monkeypatch):
        self._con_respuesta(
            monkeypatch,
            '```json\n{"hallazgos":[{"item":"890201","motivo":"sin respaldo"}]}\n```',
        )
        assert evaluar(cliente, FACTURA_SANA).json()["status"] == "ADVERTENCIA"

    def test_el_modelo_usado_queda_registrado(self, cliente, db, monkeypatch):
        self._con_respuesta(monkeypatch, '{"hallazgos":[]}')
        cuerpo = evaluar(cliente, FACTURA_SANA).json()
        fila = db.get(PreAuditoriaEventoRecord, cuerpo["evento_id"])
        assert fila.modelo_utilizado
        assert fila.cruce_clinico_estado == "OK"

    def test_el_cruce_clinico_no_usa_un_modelo_razonador(self):
        """Un razonador gasta el presupuesto de tiempo pensando en voz alta.
        Acá se responde con el facturador esperando."""
        assert not get_settings().preauditoria_modelo.startswith("openai/gpt-oss")


# ═══════════════════════════════════════════════════════════════════════
class TestLaPuertaDelHisPorDentro:
    def test_sin_token_de_agente_configurado_responde_503(self, monkeypatch):
        from fastapi import HTTPException

        monkeypatch.setattr(get_settings(), "agente_lotes_token", "", raising=False)
        with pytest.raises(HTTPException) as e:
            quien_pregunta(x_agente_token="algo", token=None, db=None)
        assert e.value.status_code == 503

    def test_el_token_se_compara_sin_filtrar_el_tiempo(self):
        """`secrets.compare_digest`, no `==`: comparar cadenas con `==` deja
        adivinar el token carácter por carácter midiendo lo que tarda."""
        import inspect

        from app.api.routers import pre_auditoria as mod

        fuente = inspect.getsource(mod.quien_pregunta)
        assert "compare_digest" in fuente
