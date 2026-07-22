"""Tests de HOSPIAI Fase 2 · Sprint 1 — AG010 Supervisor.

Cubre las seis piezas por separado (Scheduler con dependencias y backoff,
Dispatcher solo-por-Registro, RetryManager con backoff y Decision Record,
PolicyEngine desde data/politicas.json, MissionLogger con cada transición) y
el ciclo completo end-to-end drenando una cola real con agentes reales.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import hospiai_db as hdb  # noqa: E402
import hospiai_sdk as sdk  # noqa: E402
import hospiai_supervisor as sup  # noqa: E402
from hospiai_rpa import IRadicador, adaptador  # noqa: E402

import pytest  # noqa: E402


def _politicas(tmp_path, extra=None) -> sup.PolicyEngine:
    data = {
        "max_procesos_por_tipo": {"OCR": 1},
        "horario_laboral": {"aplica_a_tipos": ["OCR"], "desde": "05:00", "hasta": "21:00"},
        "requiere_aprobacion_humana": ["RPA", "RADICAR"],
        "backoff_segundos": [5, 60],
        "cadenas": {},
    }
    data.update(extra or {})
    f = tmp_path / "politicas.json"
    f.write_text(json.dumps(data), encoding="utf-8")
    return sup.PolicyEngine(f)


class TestPolicyEngine:
    def test_aprobacion_humana_bloquea(self, tmp_path):
        pe = _politicas(tmp_path)
        m = sdk.Mision(codigo="MISION-000001", tipo="RPA")
        ok, motivo = pe.permitida(m, {})
        assert not ok and "aprobación humana" in motivo

    def test_tope_de_concurrencia(self, tmp_path):
        pe = _politicas(tmp_path)
        pe._ahora = lambda: datetime(2026, 7, 22, 10, 0)  # dentro del horario laboral
        m = sdk.Mision(codigo="MISION-000002", tipo="OCR")
        assert pe.permitida(m, {"OCR": 0})[0] is True
        ok, motivo = pe.permitida(m, {"OCR": 1})
        assert not ok and "tope" in motivo

    def test_horario_laboral(self, tmp_path):
        pe = _politicas(tmp_path)
        pe._ahora = lambda: datetime(2026, 7, 22, 23, 30)  # fuera de 05:00–21:00
        ok, motivo = pe.permitida(sdk.Mision(codigo="M", tipo="OCR"), {})
        assert not ok and "horario" in motivo
        pe._ahora = lambda: datetime(2026, 7, 22, 10, 0)
        assert pe.permitida(sdk.Mision(codigo="M", tipo="OCR"), {})[0] is True

    def test_backoff_escalonado(self, tmp_path):
        pe = _politicas(tmp_path)
        assert pe.backoff(1) == 5 and pe.backoff(2) == 60 and pe.backoff(9) == 60


class TestScheduler:
    def test_respeta_dependencias(self, tmp_path):
        db = tmp_path / "h.db"
        cola = sdk.ColaMisiones(db)
        primera = cola.crear("ECO", datos={"mensaje": "a"})
        segunda = cola.crear("ECO", datos={"mensaje": "b", "depende_de": [primera.codigo]})
        sch = sup.Scheduler(cola)
        # Solo la primera es elegible mientras su dependencia no esté OK.
        assert [m.codigo for m in sch.elegibles()] == [primera.codigo]
        tomada = cola.tomar(["ECO"], "X")
        cola.completar(tomada, sdk.ResultadoAgente(agente="X", version="1"))
        assert [m.codigo for m in sch.elegibles()] == [segunda.codigo]

    def test_respeta_backoff_no_antes(self, tmp_path):
        db = tmp_path / "h.db"
        cola = sdk.ColaMisiones(db)
        m = cola.crear("ECO", datos={})
        cola.reprogramar(m, 3600)  # no elegible por una hora
        assert sup.Scheduler(cola).elegibles() == []


class TestDispatcherYRetry:
    def test_dispatcher_usa_solo_el_registro(self, tmp_path):
        s = sup.Supervisor(tmp_path / "h.db")
        m = sdk.Mision(codigo="M", tipo="EXPLICAR_CONCEPTO")
        assert s.dispatcher.candidato(m) == "AG011"
        assert s.dispatcher.candidato(sdk.Mision(codigo="M", tipo="NO_EXISTE")) is None
        assert s.dispatcher.existe_capacidad("OCR") is True  # AG004 PLANEADO la declara
        assert s.dispatcher.existe_capacidad("NO_EXISTE") is False

    def test_error_reintenta_con_backoff_y_luego_decision(self, tmp_path, monkeypatch):
        import hospiai_agentes as hag

        class AgenteFalla(sdk.Agente):
            id = "AG996"
            nombre = "FallaSiempre"
            version = "1.0"
            capacidades = ["FALLAR_SIEMPRE"]

            def _trabajar(self, mision, contexto, res):
                raise RuntimeError("boom")

        original = hag.registro_con_implementaciones

        def registro(ruta=None):
            reg = original(ruta)
            reg._agentes["AG996"] = {
                "id": "AG996", "nombre": "FallaSiempre", "estado": "ACTIVO",
                "version": "1.0", "capacidades": ["FALLAR_SIEMPRE"], "requiere_sdk": "1.0",
            }  # fmt: skip
            reg.registrar_clase(AgenteFalla)
            return reg

        db = tmp_path / "h.db"
        s = sup.Supervisor(db, registro=registro(), politicas=_politicas(tmp_path))
        s.cola.crear("FALLAR_SIEMPRE", expediente="1", datos={}, max_intentos=2)

        r1 = s.paso()
        assert r1["resultado"] == "REINTENTO"
        # Quedó reprogramada con backoff: no elegible ya mismo.
        assert s.paso() is None
        # Vence el backoff → segundo intento → error definitivo + Decision Record.
        con = hdb.abrir(db)
        with con:
            con.execute("UPDATE misiones SET no_antes=''")
        con.close()
        r2 = s.paso()
        assert r2["resultado"] == "ERROR"
        con = hdb.abrir(db)
        dec = con.execute("SELECT * FROM decisiones WHERE dictamen='ERROR_OPERATIVO'").fetchone()
        con.close()
        assert dec is not None and "boom" in dec["motivo"]

    def test_capacidad_inexistente_no_bloquea_la_cola(self, tmp_path):
        db = tmp_path / "h.db"
        s = sup.Supervisor(db, politicas=_politicas(tmp_path))
        s.cola.crear("CAPACIDAD_FANTASMA", datos={})
        r = s.paso()
        assert r["resultado"] == "ERROR"  # error definitivo inmediato, nada bloqueado
        assert s.cola.estado() == {"ERROR": 1}


class TestSupervisorEndToEnd:
    def test_drena_cola_real_con_agentes_reales(self, tmp_path):
        db = tmp_path / "h.db"
        s = sup.Supervisor(db, politicas=_politicas(tmp_path))
        ruta = (
            r"Y:\7. JULIO 2026 - SOPORTES RADICACION\ASMET SALUD\LILIANA"
            r"\ENV-230314-OKDGH\HUS528043\EPI.pdf"
        )
        s.cola.crear("ANALIZAR_RUTA", expediente="528043", datos={"ruta": ruta}, prioridad="ALTA")
        s.cola.crear("CLASIFICAR_DOCUMENTO", expediente="528043", datos={"nombre": "HEV_x.pdf"})
        s.cola.crear("EXPLICAR_CONCEPTO", datos={"codigo": "DQX"})

        conteo = s.correr()
        assert conteo == {"OK": 3}
        assert s.cola.estado() == {"OK": 3}

        con = hdb.abrir(db)
        try:
            # Mission Logger: transición completa por misión.
            log = con.execute(
                "SELECT a_estado FROM mision_log WHERE mision_codigo='MISION-000001' ORDER BY id"
            ).fetchall()
            assert [f["a_estado"] for f in log] == ["ASIGNADA", "EJECUTANDO", "FINALIZADA"]
            # Los resultados quedaron persistidos con el agente que los produjo.
            res = con.execute(
                "SELECT resultado FROM misiones WHERE codigo='MISION-000001'"
            ).fetchone()
            datos = json.loads(res["resultado"])
            assert datos["agente"] == "AG002"
            assert datos["salida"]["responsable"] == "LILIANA"
            # Y los eventos del Expediente registran la ejecución.
            n_ev = con.execute("SELECT COUNT(*) FROM eventos").fetchone()[0]
            assert n_ev >= 2  # AG002 y AG003 registran (AG011 sin expediente usa '-')
        finally:
            con.close()

    def test_aprobacion_humana_deja_pendiente(self, tmp_path):
        db = tmp_path / "h.db"
        s = sup.Supervisor(db, politicas=_politicas(tmp_path))
        s.cola.crear("RPA", expediente="1", datos={})
        assert s.correr() == {}  # nada procesado: la política la retiene
        assert s.cola.estado() == {"PENDIENTE": 1}
        con = hdb.abrir(db)
        log = con.execute("SELECT detalle FROM mision_log ORDER BY id DESC LIMIT 1").fetchone()
        con.close()
        assert "aprobación humana" in log["detalle"]

    def test_cadenas_generan_siguiente_mision(self, tmp_path):
        pe = _politicas(
            tmp_path,
            {"cadenas": {"ANALIZAR_RUTA": [{"tipo": "EXPLICAR_CONCEPTO", "prioridad": "BAJA"}]}},
        )
        db = tmp_path / "h.db"
        s = sup.Supervisor(db, politicas=pe)
        s.cola.crear("ANALIZAR_RUTA", datos={"ruta": "X:\\HUS1", "codigo": "DQX"})
        conteo = s.correr()
        # La cadena creó EXPLICAR_CONCEPTO y también se procesó.
        assert conteo["OK"] == 2
        con = hdb.abrir(db)
        tipos = [f["tipo"] for f in con.execute("SELECT tipo FROM misiones ORDER BY id")]
        con.close()
        assert tipos == ["ANALIZAR_RUTA", "EXPLICAR_CONCEPTO"]


class TestInterfazRPA:
    def test_interfaz_definida_sin_adaptadores(self):
        # El contrato existe (Fase 5 lista para adaptadores)…
        assert {"login", "subir", "confirmar", "descargar_comprobante", "cerrar"} <= set(
            vars(IRadicador)
        )
        # …pero NO hay ningún adaptador real: radicar automático sigue vedado.
        with pytest.raises(KeyError) as e:
            adaptador("ASMET")
        assert "autorización" in str(e.value)
