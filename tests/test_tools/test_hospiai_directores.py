"""Tests de HOSPIAI Fase 2 · Sprint 2A — Los Directores (AG012–AG015).

Arma un lote sintético con responsables, pagadores, valores y causas
conocidas, lo persiste como corrida real, y verifica que cada director
produzca números correctos: informe ejecutivo, tareas del día, respuestas de
caja, aprendizaje entre corridas, y el panel ejecutivo alimentado SOLO por la
capa de servicios de la API.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import hospiai_db as hdb  # noqa: E402
import hospiai_directores as dirs  # noqa: E402
from hospiai_api import Servicios  # noqa: E402
from hospiai_sdk import Mision  # noqa: E402
import radicar_facturacion as rad  # noqa: E402


def _res(
    fac,
    entidad_id,
    entidad,
    valor,
    responsable,
    estado,
    esperados=(),
    presentes=("FEV", "RIP", "CUV"),
):
    r = rad.ResultadoFactura()
    r.factura = fac
    r.factura_norm = rad.normalizar_factura(fac)
    r.entidad_id = entidad_id
    r.entidad_nombre = entidad
    r.valor_total = valor
    r.responsable = responsable
    r.estado = estado
    r.soportes_presentes = list(presentes)
    r.soportes_esperados_faltantes = list(esperados)
    r.carpeta = f"X:\\FE\\{fac}"
    return r


def _lote_base():
    """6 expedientes: 3 LISTAS ($600), 2 REVISAR por HEV ($900), 1 por CUV ($100).
    LILIANA rinde (2/3 listas), VANESSA sufre (1/3 listas)."""
    return [
        _res("HUS1", "ASMET", "ASMET SALUD", 100, "LILIANA", "LISTA"),
        _res("HUS2", "ASMET", "ASMET SALUD", 200, "LILIANA", "LISTA"),
        _res("HUS3", "ASMET", "ASMET SALUD", 500, "LILIANA", "REVISAR_TIPIFICACION", ["HEV"]),
        _res("HUS4", "NUEVAEPS", "NUEVA EPS", 300, "VANESSA", "LISTA"),
        _res("HUS5", "NUEVAEPS", "NUEVA EPS", 400, "VANESSA", "REVISAR_TIPIFICACION", ["HEV"]),
        _res("HUS6", "NUEVAEPS", "NUEVA EPS", 100, "VANESSA", "SIN_CUV"),
    ]


def _persistir(db, resultados):
    cfg = rad.cargar_perfiles(None)
    rad.cargar_reglas(None, cfg)
    return hdb.persistir_corrida(
        db,
        resultados,
        {},
        version_reglas=cfg.version_reglas,
        version_motor=rad.VERSION_MOTOR,
        regla_id_por_codigo=cfg.regla_id_por_codigo,
        reglas_registro=cfg.reglas_registro,
        clasificar=lambda n: rad.clasificar_soporte(n)[0],
    )


class TestDirectorAuditoria:
    def test_informe_ejecutivo_numeros(self, tmp_path):
        db = tmp_path / "h.db"
        _persistir(db, _lote_base())
        a = dirs.analizar_corrida(db)
        r = a["resumen"]
        assert r["facturas"] == 6 and r["valor_total"] == 1600
        assert r["listas"] == 3 and round(r["listas_pct"], 1) == 50.0
        assert r["valor_listas"] == 600
        # Riesgo financiero: detenido = 1000, explicado por causa.
        assert a["riesgo_financiero"]["detenido"] == 1000
        causas = {c["dictamen"]: c["v"] for c in a["riesgo_financiero"]["por_causa"]}
        assert causas == {"REVISAR_TIPIFICACION": 900, "SIN_CUV": 100}
        # Ranking por responsable.
        por_resp = {x["responsable"]: x for x in a["responsables"]}
        assert round(por_resp["LILIANA"]["pct_listas"]) == 67
        assert round(por_resp["VANESSA"]["pct_listas"]) == 33
        # Riesgo por entidad con causa principal.
        ents = {e["pagador_nombre"]: e for e in a["entidades"]}
        assert ents["ASMET SALUD"]["pendientes"] == 1
        assert ents["ASMET SALUD"]["causa_principal"] == "HEV"
        assert ents["NUEVA EPS"]["pendientes"] == 2
        # Hallazgos valorizados con norma.
        hall = {h["causa"]: h for h in a["hallazgos"]}
        assert hall["HEV"]["facturas"] == 2 and hall["HEV"]["valor"] == 900
        assert "2284" in (hall["HEV"]["norma"] or "")
        # Predicción: HEV es lo único que les falta a HUS3 y HUS5 → suben 2 ($900).
        pred = {p["causa"]: p for p in a["prediccion"]}
        assert pred["HEV"]["facturas"] == 2 and pred["HEV"]["valor"] == 900
        # Recomendaciones priorizadas por impacto (HEV primero).
        assert a["recomendaciones"][0]["accion"] == "Corregir HEV"
        assert a["recomendaciones"][0]["impacto"] == 900

    def test_agente_escribe_informe_a_disco(self, tmp_path, monkeypatch):
        db = tmp_path / "h.db"
        _persistir(db, _lote_base())
        monkeypatch.setattr(dirs, "DIR_INFORMES", tmp_path / "informes")
        res = dirs.AgenteDirectorAuditoria().ejecutar(
            Mision(codigo="M", tipo="INFORME_AUDITORIA"), {"db_path": db}
        )
        assert res.resultado == "OK"
        ruta = Path(res.salida["ruta_informe"])
        assert ruta.is_file()
        assert json.loads(ruta.read_text(encoding="utf-8"))["resumen"]["facturas"] == 6


class TestDirectorOperativo:
    def test_genera_tareas_del_dia_retenidas(self, tmp_path):
        db = tmp_path / "h.db"
        _persistir(db, _lote_base())
        res = dirs.AgenteDirectorOperativo().ejecutar(
            Mision(codigo="M", tipo="PLAN_OPERATIVO"), {"db_path": db}
        )
        assert res.resultado == "OK"
        tareas = res.salida["tareas"]
        # VANESSA primero (más valor detenido: 500 vs 500... LILIANA 500, VANESSA 500)
        assert {t["responsable"] for t in tareas} == {"LILIANA", "VANESSA"}
        assert all("HEV" in t["accion"] for t in tareas)  # empezar por la causa top
        # Quedaron como misiones TAREA_HUMANA pendientes (retenidas por política).
        s = Servicios(db)
        pendientes = s.tareas()
        assert len(pendientes) == 2


class TestDirectorGerencial:
    def test_respuestas_de_caja(self, tmp_path):
        db = tmp_path / "h.db"
        _persistir(db, _lote_base())
        res = dirs.AgenteDirectorGerencial().ejecutar(
            Mision(codigo="M", tipo="RESPUESTAS_CAJA"), {"db_path": db}
        )
        assert res.resultado == "OK"
        r = {x["pregunta"]: x for x in res.salida["respuestas"]}
        assert r["¿Cuánto dinero puedo radicar hoy?"]["cifra"] == 600
        assert r["¿Cuánto dinero está detenido?"]["cifra"] == 1000
        assert r["¿Cuánto recupero si soluciono la causa principal?"]["cifra"] == 900
        assert "HEV" in r["¿Cuánto recupero si soluciono la causa principal?"]["respuesta"]
        assert "VANESSA" not in r["¿Cuál funcionario genera mayor retorno?"]["respuesta"]
        assert "NUEVA EPS" in r["¿Cuál EPS está frenando caja?"]["respuesta"]


class TestAprendizaje:
    def test_registra_transicion_revisar_a_lista(self, tmp_path):
        db = tmp_path / "h.db"
        _persistir(db, _lote_base())
        # Segunda corrida: HUS3 consiguió su HEV → pasó a LISTA.
        lote2 = _lote_base()
        lote2[2] = _res("HUS3", "ASMET", "ASMET SALUD", 500, "LILIANA", "LISTA")
        _persistir(db, lote2)

        res = dirs.AgenteAprendizaje().ejecutar(
            Mision(codigo="M", tipo="APRENDIZAJE"), {"db_path": db}
        )
        assert res.resultado == "OK"
        lecciones = res.salida["aprendizajes"]
        assert len(lecciones) == 1
        lec = lecciones[0]
        assert lec["expediente"] == "3"  # HUS3 normalizada
        assert lec["cambio"] == "REVISAR_TIPIFICACION → LISTA"
        assert lec["que_cambio"] == ["HEV"]
        # Idempotente: correr de nuevo no duplica la lección.
        res2 = dirs.AgenteAprendizaje().ejecutar(
            Mision(codigo="M2", tipo="APRENDIZAJE"), {"db_path": db}
        )
        assert res2.salida["aprendizajes"] == []


class TestPanelEjecutivo:
    def test_seis_vistas_desde_la_api(self, tmp_path):
        import hospiai_panel_ejecutivo as panel

        db = tmp_path / "h.db"
        _persistir(db, _lote_base())
        dirs.AgenteDirectorOperativo().ejecutar(
            Mision(codigo="M", tipo="PLAN_OPERATIVO"), {"db_path": db}
        )
        contenido = panel.render(Servicios(db))
        for vista in (
            "Vista 1 · Estado General",
            "Vista 2 · Riesgo Financiero",
            "Vista 3 · Responsables",
            "Vista 4 · EPS",
            "Vista 5 · Hallazgos",
            "Vista 6 · Predicción",
        ):
            assert vista in contenido
        # Las 6 preguntas de aceptación están respondidas de frente.
        assert "¿Cuánto dinero puedo radicar hoy?" in contenido
        assert "¿3 acciones de mayor impacto" in contenido
        assert "LILIANA" in contenido and "ASMET" in contenido and "HEV" in contenido
        # El módulo del panel no toca SQLite: consume solo la capa de servicios.
        fuente = (Path(_TOOLS) / "hospiai_panel_ejecutivo.py").read_text(encoding="utf-8")
        assert "sqlite3" not in fuente and "hospiai_db" not in fuente
