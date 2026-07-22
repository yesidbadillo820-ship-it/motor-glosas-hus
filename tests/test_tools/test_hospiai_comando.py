"""Tests del Hospital Command Center (Fase 4 · AG029–AG033).

Verifica los dos criterios de aceptación (`hospiai.py iniciar-dia` y
`hospiai.py preguntar`) y la honestidad del centro de comando: el HOS combina
SOLO los componentes con datos (los demás quedan excluidos con su razón, nunca
un número inventado); el balanceo reparte con aritmética exacta y etiqueta la
ganancia de throughput como estimación; la proyección se niega a proyectar sin
historial; y el copiloto responde con evidencia, confianza y recomendaciones.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # reusar semillas

import hospiai  # noqa: E402
import hospiai_comando as cc  # noqa: E402
import hospiai_db  # noqa: E402
from test_hospiai_conocimiento import _sembrar  # noqa: E402
from test_hospiai_operacion import _indices  # noqa: E402


class TestHOS:
    def test_solo_componentes_con_datos(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        h = cc.hospital_operational_score(db)
        assert 0 <= h["hos"] <= 100
        assert h["nivel"] in ("Excelente", "Bueno", "Aceptable", "Crítico")
        comp = {c["nombre"]: c for c in h["componentes"]}
        # Con datos: calidad (20% listas), productividad (hay carga), aprendizaje
        # (hay 2 corridas). Sin historial: tiempo, devoluciones, recuperación.
        assert comp["calidad_listas"]["disponible"] and comp["calidad_listas"]["score"] == 20.0
        assert comp["productividad"]["disponible"]
        assert not comp["tiempo_radicacion"]["disponible"]
        assert not comp["devoluciones"]["disponible"]
        assert not comp["recuperacion"]["disponible"]
        # Los excluidos NO aportan número: score None y razón textual.
        assert comp["devoluciones"]["score"] is None
        assert "historial" in comp["devoluciones"]["detalle"]
        assert set(h["excluidos"]) == {"tiempo_radicacion", "devoluciones", "recuperacion"}

    def test_reponderacion_no_inventa(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        h = cc.hospital_operational_score(db)
        disp = [c for c in h["componentes"] if c["disponible"]]
        peso = sum(c["peso"] for c in disp)
        esperado = round(sum(c["peso"] * c["score"] for c in disp) / peso)
        assert h["hos"] == esperado  # exactamente la media ponderada de lo disponible

    def test_escala_oficial(self):
        assert cc.nivel_hos(95) == "Excelente"
        assert cc.nivel_hos(85) == "Bueno"
        assert cc.nivel_hos(70) == "Aceptable"
        assert cc.nivel_hos(40) == "Crítico"


class TestSituacion:
    def test_abre_con_decisiones(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        s = cc.situacion_del_dia(db, _indices(tmp_path))
        assert isinstance(s["hos"], int) and s["nivel"]
        assert s["recuperable_hoy"] == 8_400_000  # todos los pendientes con hallazgos
        assert "HEV" in s["prioridad_maxima"] or "Asociar" in s["prioridad_maxima"]
        assert "COOSALUD" in s["riesgo_principal"]
        # KARIN está sobrecargada (3 exp, 2 pendientes) frente a PEPE (2 pend.).
        assert s["accion_inmediata"]


class TestWorkloadBalancer:
    def test_propone_movimiento_exacto(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        b = cc.balancear_carga(db)
        # KARIN: 2 pendientes (528043, 528044); PEPE: 2 (528045, 528047).
        # En esta semilla la carga está pareja → sin movimientos, pero el balance existe.
        assert len(b["cargas"]) == 2
        assert "ESTIMACIÓN" in b["efecto"]

    def test_desequilibrio_genera_traslado(self, tmp_path):
        db = tmp_path / "d.db"
        con = hospiai_db.abrir(db)
        with con:
            con.execute("INSERT INTO corridas(id, iniciada) VALUES(1,'2026-07-21T08:00:00')")
            # KARIN saturada (5 pendientes), LILIANA libre (1 pendiente).
            for i, (resp, dic) in enumerate(
                [("KARIN", "REVISAR_TIPIFICACION")] * 5 + [("LILIANA", "REVISAR_TIPIFICACION")]
            ):
                con.execute(
                    "INSERT INTO expedientes(factura_norm, factura, pagador_nombre, responsable,"
                    " valor_total, dictamen, creado, actualizado) VALUES(?,?,?,?,?,?,?,?)",
                    (f"F{i}", f"HUS{i}", "EPS", resp, 1000, dic, "2026-07-21", "2026-07-21"),
                )
        con.close()
        b = cc.balancear_carga(db)
        assert b["movimientos"], "debe proponer mover expedientes de KARIN a LILIANA"
        mov = b["movimientos"][0]
        assert mov["de"] == "KARIN" and mov["a"] == "LILIANA" and mov["expedientes"] == 2


class TestEarlyWarning:
    def test_riesgo_por_senal_documental(self, tmp_path):
        import hospiai_indexador as idx

        db = _sembrar(tmp_path / "h.db")
        d = _indices(tmp_path)
        # Perfil documental: un DQX SIN firma para la 528043 (riesgo de devolución).
        con = idx._abrir(d / "indice_y.db")
        with con:
            con.execute(
                "INSERT INTO archivos(ruta, nombre, factura, tipo, reconocido, tamano,"
                " ultima_modificacion, visto_primera, visto_ultima, servidor, estado)"
                " VALUES('Y:/DQX_528043.pdf','DQX_528043.pdf','528043','DQX',1,10,0,"
                " '2026-07-21','2026-07-21','y','ACTIVO')"
            )
            con.executescript(
                "CREATE TABLE IF NOT EXISTS document_profile(ruta TEXT PRIMARY KEY,"
                " hash TEXT, paginas INT, autor TEXT, productor TEXT, fecha_creacion_doc TEXT,"
                " fecha_modificacion_doc TEXT, firma INT DEFAULT 0, texto INT DEFAULT 0,"
                " cifrado INT DEFAULT 0, rotacion INT DEFAULT 0, dpi INT, legibilidad REAL,"
                " calidad TEXT, clase TEXT, codigo TEXT, confianza REAL, dup_exacto_de TEXT,"
                " dup_funcional INT, problema TEXT, perfilado_en TEXT);"
            )
            con.execute(
                "INSERT INTO document_profile(ruta, codigo, calidad, firma, texto, problema,"
                " perfilado_en) VALUES('Y:/DQX_528043.pdf','DQX','B',0,1,'','2026-07-21')"
            )
        con.close()
        al = cc.alertas_tempranas(db, d)
        assert al["total"] >= 1
        top = next(a for a in al["alertas"] if a["factura"] == "HUS528043")
        assert "DQX sin firma" in top["motivos"]
        assert top["respaldo_historico"] is None  # sin historial → cualitativo, sin % inventado
        assert "sin historial" in top["base"]

    def test_sin_base_documental_lo_dice(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        al = cc.alertas_tempranas(db, tmp_path / "vacio")
        assert al["total"] == 0 and al["sin_base"]
        assert "Document Intelligence Service" in al["nota"]


class TestForecaster:
    def test_proyecta_con_dos_corridas(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        pr = cc.proyectar_mes(db)
        assert pr["disponible"]
        assert "proyeccion_fin_mes_pct" in pr and "supuesto" in pr["base"]
        assert pr["tendencia"] in ("mejora", "estable", "empeora")
        # Lo que exige historial externo queda declarado, no proyectado.
        assert "glosas" in pr["pendiente_historial"]

    def test_se_niega_sin_historial(self, tmp_path):
        db = tmp_path / "una.db"
        con = hospiai_db.abrir(db)
        with con:
            con.execute("INSERT INTO corridas(id, iniciada) VALUES(1,'2026-07-21T08:00:00')")
            con.execute(
                "INSERT INTO decisiones(codigo, factura_norm, corrida_id, dictamen, fecha)"
                " VALUES('D1','F1',1,'LISTA','2026-07-21')"
            )
        con.close()
        pr = cc.proyectar_mes(db)
        assert not pr["disponible"] and "insuficiente" in pr["nota"]


class TestCopilot:
    def test_dinero_detenido(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        r = cc.preguntar(db, "¿Dónde está detenido el dinero?")
        assert "detenidos" in r["respuesta"]
        assert r["evidencia"] and r["confianza"] == "ALTA"
        assert "HOS" in r["indicadores"]

    def test_eps_a_llamar(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        r = cc.preguntar(db, "¿Qué EPS debo llamar primero?")
        assert "COOSALUD" in r["respuesta"]
        assert r["recomendaciones"]

    def test_funcionario_apoyo(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        r = cc.preguntar(db, "¿Qué funcionario necesita apoyo?")
        assert r["confianza"] == "ALTA"
        assert any("carga" in e.lower() or "pend" in e.lower() for e in r["evidencia"])

    def test_liberar_dinero_hoy(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        r = cc.preguntar(db, "¿Qué debo hacer hoy para liberar la mayor cantidad de dinero?")
        assert "libera" in r["respuesta"].lower() or "impacto" in r["respuesta"].lower()
        assert "Recuperable total" in r["indicadores"]

    def test_respuesta_sin_opinion_tiene_estructura(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        r = cc.preguntar(db, "cualquier cosa rara sin intención clara")
        # Siempre las 4 partes obligatorias: evidencia, indicadores, confianza, recomendaciones.
        for campo in (
            "evidencia",
            "indicadores",
            "confianza",
            "confianza_motivo",
            "recomendaciones",
        ):
            assert campo in r


class TestCriterioAceptacion:
    def test_hospiai_iniciar_dia(self, tmp_path, capsys, monkeypatch):
        import hospiai_indexador as idx

        db = _sembrar(tmp_path / "h.db")
        monkeypatch.setattr(idx, "DIR_INDICES", _indices(tmp_path))
        assert hospiai.main(["--db", str(db), "iniciar-dia"]) == 0
        out = capsys.readouterr().out
        assert "BUENOS DÍAS" in out
        assert "Hospital Operational Score" in out
        assert "Hoy recomendamos:" in out and "OBJETIVO DEL DÍA" in out
        assert "Cuello de botella" in out

    def test_hospiai_preguntar_bateria(self, tmp_path, capsys, monkeypatch):
        import hospiai_indexador as idx

        db = _sembrar(tmp_path / "h.db")
        monkeypatch.setattr(idx, "DIR_INDICES", _indices(tmp_path))
        assert hospiai.main(["--db", str(db), "preguntar"]) == 0
        out = capsys.readouterr().out
        # Las 5 preguntas de aceptación, cada una con evidencia y confianza.
        assert "liberar la mayor cantidad de dinero" in out
        assert "riesgo debo atender primero" in out
        assert "Confianza:" in out and "Recomendaciones:" in out

    def test_hospiai_preguntar_libre(self, tmp_path, capsys):
        db = _sembrar(tmp_path / "h.db")
        assert hospiai.main(["--db", str(db), "preguntar", "¿Dónde está detenido el dinero?"]) == 0
        out = capsys.readouterr().out
        assert "detenido" in out.lower() and "Evidencia:" in out

    def test_api_expone_command_center(self, tmp_path):
        from hospiai_api import Servicios

        db = _sembrar(tmp_path / "h.db")
        s = Servicios(db)
        assert 0 <= s.hos()["hos"] <= 100
        assert s.situacion()["nivel"]
        assert s.iniciar_dia()["saludo"] == "BUENOS DÍAS"
        assert "cargas" in s.carga()
        assert "alertas" in s.alertas()
        assert "disponible" in s.proyeccion()
        assert s.preguntar("¿dónde está detenido el dinero?")["confianza"] == "ALTA"

    def test_panel_abre_con_situacion_y_hos(self, tmp_path):
        from hospiai_api import Servicios
        from hospiai_panel_ejecutivo import render

        db = _sembrar(tmp_path / "h.db")
        html_out = render(Servicios(db))
        assert "SITUACIÓN DEL DÍA" in html_out
        assert "Hospital Operational Score" in html_out

    def test_regla_de_oro_en_fichas_fase4(self):
        registro = json.loads(
            (Path(__file__).resolve().parent.parent.parent / "data" / "agentes.json").read_text(
                encoding="utf-8-sig"
            )
        )
        fichas = {a["id"]: a for a in registro["agentes"]}
        for ag in ("AG029", "AG030", "AG031", "AG032", "AG033"):
            j = fichas[ag].get("justificacion_operativa")
            assert j, f"{ag} sin justificación operativa (regla de oro)"
            for pregunta in ("problema", "dinero", "horas", "indicador", "medicion"):
                assert j.get(pregunta), f"{ag}: falta '{pregunta}'"

    def test_registro_incluye_ag029_a_ag033(self):
        from hospiai_agentes import registro_con_implementaciones

        reg = registro_con_implementaciones()
        for ag_id, capacidad in (
            ("AG029", "INICIAR_DIA"),
            ("AG030", "BALANCEAR_CARGA"),
            ("AG031", "ALERTA_TEMPRANA"),
            ("AG032", "PROYECTAR_KPI"),
            ("AG033", "PREGUNTAR"),
        ):
            assert any(a["id"] == ag_id for a in reg.por_capacidad(capacidad)), capacidad
            assert reg.instanciar(ag_id).id == ag_id
