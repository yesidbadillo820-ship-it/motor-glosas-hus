"""Tests del Enterprise Knowledge Engine (Fase 2.2).

Con un mini-expediente sintético verifica la regla de arquitectura completa:
todo aprendizaje entra como CANDIDATO a la Memoria Institucional, solo el
Knowledge Curator (AG019) lo promueve a VALIDADO, y únicamente lo VALIDADO se
sirve a los demás agentes. Además: patrones (AG020), recomendaciones con base
declarada (AG021), causa raíz por concentración (AG022), minería de proceso
(AG023), el Motor de Hipótesis (exacto vs. estimación etiquetada) y los
criterios de aceptación `hospiai.py recomendar HUS…` / `hospiai.py simular`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import hospiai  # noqa: E402
import hospiai_conocimiento as kn  # noqa: E402
import hospiai_db  # noqa: E402
from hospiai_sdk import Mision  # noqa: E402


def _sembrar(db: Path) -> Path:
    """Mini-expediente: corridas #1 y #2, cinco facturas, hallazgos vigentes,
    una transición REVISAR→LISTA (528046) y eventos con horas medibles."""
    con = hospiai_db.abrir(db)
    with con:
        con.execute("INSERT INTO corridas(id, iniciada) VALUES(1, '2026-07-20T08:00:00')")
        con.execute("INSERT INTO corridas(id, iniciada) VALUES(2, '2026-07-21T08:00:00')")
        exps = [
            (
                "528043",
                "HUS528043",
                "COOSALUD",
                "KARIN",
                "LOTE1",
                4_000_000,
                "REVISAR_TIPIFICACION",
            ),
            (
                "528044",
                "HUS528044",
                "COOSALUD",
                "KARIN",
                "LOTE1",
                2_000_000,
                "REVISAR_TIPIFICACION",
            ),
            (
                "528045",
                "HUS528045",
                "NUEVA EPS",
                "PEPE",
                "LOTE2",
                1_500_000,
                "REVISAR_TIPIFICACION",
            ),
            ("528046", "HUS528046", "COOSALUD", "KARIN", "LOTE1", 3_000_000, "LISTA"),
            ("528047", "HUS528047", "NUEVA EPS", "PEPE", "LOTE2", 900_000, "REVISAR_TIPIFICACION"),
        ]
        for norm, fac, pag, resp, lote, valor, dic in exps:
            con.execute(
                "INSERT INTO expedientes(factura_norm, factura, pagador_id, pagador_nombre,"
                " responsable, lote, anio, mes, valor_total, dictamen, creado, actualizado,"
                " ultima_corrida) VALUES(?,?,?,?,?,?,2026,6,?,?,"
                " '2026-07-21T08:00:00','2026-07-21T08:00:00',2)",
                (norm, fac, pag, pag, resp, lote, valor, dic),
            )
        # Corrida 2 (vigente): lo que FALTA hoy. 528043/528045 solo esperan HEV;
        # 528044 espera HEV+EPI; 528047 solo EPI; 528046 quedó limpia.
        halls = [
            ("528043", "HEV"),
            ("528044", "HEV"),
            ("528044", "EPI"),
            ("528045", "HEV"),
            ("528047", "EPI"),
        ]
        for norm, cod in halls:
            con.execute(
                "INSERT INTO hallazgos(factura_norm, corrida_id, agente, tipo, codigo,"
                " criticidad, detalle, regla_id, evidencia, fecha) VALUES(?,2,'AG006',"
                " 'FALTA_SOPORTE', ?, 'CRITICO', 'falta', ?, 'inventario', '2026-07-21T08:05:00')",
                (norm, cod, f"R-{cod}"),
            )
        # Corrida 1: 528046 esperaba HEV → hoy LISTA (la transición del AG015).
        con.execute(
            "INSERT INTO hallazgos(factura_norm, corrida_id, agente, tipo, codigo, criticidad,"
            " detalle, regla_id, evidencia, fecha) VALUES('528046',1,'AG006','FALTA_SOPORTE',"
            " 'HEV','CRITICO','falta','R-HEV','inventario','2026-07-20T08:05:00')"
        )
        con.execute(
            "INSERT INTO decisiones(codigo, factura_norm, corrida_id, dictamen, fecha)"
            " VALUES('DEC-000001','528046',1,'REVISAR_TIPIFICACION','2026-07-20T08:05:00')"
        )
        con.execute(
            "INSERT INTO decisiones(codigo, factura_norm, corrida_id, dictamen, fecha)"
            " VALUES('DEC-000002','528046',2,'LISTA','2026-07-21T08:05:00')"
        )
        # Eventos para el ProcessMiner: INDEXACION → AUDITORIA (6 h y 2 h).
        for norm, f1, f2 in (
            ("528043", "2026-07-20T08:00:00", "2026-07-20T14:00:00"),
            ("528044", "2026-07-20T09:00:00", "2026-07-20T11:00:00"),
        ):
            con.execute(
                "INSERT INTO eventos(factura_norm, fecha, agente, tipo)"
                " VALUES(?,?,'AG001','INDEXACION')",
                (norm, f1),
            )
            con.execute(
                "INSERT INTO eventos(factura_norm, fecha, agente, tipo)"
                " VALUES(?,?,'AG006','AUDITORIA')",
                (norm, f2),
            )
    con.close()
    return db


class TestMemoriaInstitucional:
    def test_registrar_deduplica_y_acumula(self, tmp_path):
        db = tmp_path / "h.db"
        hospiai_db.abrir(db).close()
        m = kn.MemoriaInstitucional(db)
        clave1 = m.registrar("LECCION", "Resolver HEV destraba.", {"codigo": "HEV"}, "exp 1")
        clave2 = m.registrar("LECCION", "Resolver HEV destraba.", {"codigo": "HEV"}, "exp 2")
        assert clave1 == clave2  # mismo tipo+contexto → un solo conocimiento
        filas = m.consultar(solo_validado=False)
        assert len(filas) == 1
        k = filas[0]
        assert k["codigo"] == "CON-000001" and k["estado"] == "CANDIDATO"
        assert k["ocurrencias"] == 2 and k["exitos"] == 2
        # Contexto distinto → conocimiento distinto, con su propio código.
        m.registrar("LECCION", "En COOSALUD…", {"codigo": "HEV", "eps": "COOSALUD"}, "exp 3")
        assert len(m.consultar(solo_validado=False)) == 2

    def test_confianza_laplace_no_infla_muestras_chicas(self):
        assert kn._confianza_laplace(1, 1) == 0.667  # 1 caso NO es 100%
        assert kn._confianza_laplace(3, 3) == 0.8
        assert kn._confianza_laplace(0, 1) == 0.333
        assert kn._confianza_laplace(94, 98) == 0.95

    def test_candidato_jamas_se_sirve(self, tmp_path):
        """LA regla de arquitectura: sin pasar por el Curator no hay consumo."""
        db = tmp_path / "h.db"
        hospiai_db.abrir(db).close()
        m = kn.MemoriaInstitucional(db)
        m.registrar("LECCION", "Resolver HEV destraba.", {"codigo": "HEV"}, "exp 1")
        assert m.consultar("LECCION", {"codigo": "HEV"}) == []  # default: solo VALIDADO
        assert len(m.consultar("LECCION", {"codigo": "HEV"}, solo_validado=False)) == 1


class TestKnowledgeCurator:
    def test_promueve_con_muestra_y_evidencia(self, tmp_path):
        db = tmp_path / "h.db"
        hospiai_db.abrir(db).close()
        m = kn.MemoriaInstitucional(db)
        for i in range(3):
            m.registrar("LECCION", "Resolver HEV destraba.", {"codigo": "HEV"}, f"exp {i}")
        m.registrar("LECCION", "Resolver EPI destraba.", {"codigo": "EPI"}, "exp x")  # n=1
        r = kn.AgenteKnowledgeCurator().ejecutar(
            Mision(codigo="M", tipo="CURAR_CONOCIMIENTO"), {"db_path": db}
        )
        assert r.resultado == "OK" and r.salida["curado"]["promovidos"] == 1
        validados = m.consultar("LECCION")
        assert len(validados) == 1  # EPI (n=1) sigue CANDIDATO
        k = validados[0]
        assert json.loads(k["contexto"])["codigo"] == "HEV"
        assert k["confianza"] == 0.8  # Laplace 4/5 con 3/3
        assert k["version"] == 2  # el cambio de estado versiona

    def test_retira_lo_que_pierde_sustento(self, tmp_path):
        db = tmp_path / "h.db"
        hospiai_db.abrir(db).close()
        m = kn.MemoriaInstitucional(db)
        m.registrar("LECCION", "X destraba.", {"codigo": "X"}, "e", exito=False, ocurrencias=6)
        con = hospiai_db.abrir(db)
        with con:  # fue VALIDADO en el pasado; hoy sus números no lo sostienen
            con.execute("UPDATE conocimiento SET estado='VALIDADO'")
        con.close()
        r = kn.AgenteKnowledgeCurator().ejecutar(
            Mision(codigo="M", tipo="CURAR_CONOCIMIENTO"), {"db_path": db}
        )
        assert r.salida["curado"]["retirados"] == 1
        k = m.consultar(solo_validado=False)[0]
        assert k["estado"] == "RETIRADO" and k["confianza"] == kn._confianza_laplace(0, 6)


class TestPatternDiscovery:
    def test_propone_patrones_como_candidatos(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        r = kn.AgentePatternDiscovery().ejecutar(
            Mision(codigo="M", tipo="DESCUBRIR_PATRONES"), {"db_path": db}
        )
        assert r.resultado == "OK" and r.salida["patrones"]
        dims = {p["dimension"] for p in r.salida["patrones"]}
        assert "eps" in dims and "responsable" in dims
        hev_coosalud = [
            p
            for p in r.salida["patrones"]
            if p["dimension"] == "eps" and p["valor"] == "COOSALUD" and p["codigo"] == "HEV"
        ]
        assert hev_coosalud and hev_coosalud[0]["casos"] == 2
        m = kn.MemoriaInstitucional(db)
        assert m.consultar("PATRON") == []  # candidatos: aún nadie puede usarlos
        assert m.consultar("PATRON", solo_validado=False)


class TestRecomendar:
    def test_por_regla_vigente_cuando_es_lo_unico_que_falta(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        r = kn.recomendar_expediente(db, "HUS528043")
        assert r["dictamen"] == "REVISAR_TIPIFICACION" and len(r["acciones"]) == 1
        a = r["acciones"][0]
        assert a["base"] == "POR REGLA VIGENTE" and a["probabilidad"] == 1.0
        assert "HEV" in a["accion"] and a["regla"] == "R-HEV"
        assert a["restantes_despues"] == []

    def test_parcial_cuando_faltan_varios(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        r = kn.recomendar_expediente(db, "HUS528044")
        assert len(r["acciones"]) == 2
        for a in r["acciones"]:
            assert a["base"] == "PARCIAL" and a["probabilidad"] == 0.0
            assert a["restantes_despues"]  # siempre queda otro pendiente

    def test_historia_solo_si_esta_validada(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        m = kn.MemoriaInstitucional(db)
        for i in range(3):  # HEV con muestra suficiente → el Curator la valida
            m.registrar("LECCION", "Resolver HEV destraba.", {"codigo": "HEV"}, f"exp {i}")
        m.registrar("LECCION", "Resolver EPI destraba.", {"codigo": "EPI"}, "exp x")  # n=1
        kn.AgenteKnowledgeCurator().ejecutar(
            Mision(codigo="M", tipo="CURAR_CONOCIMIENTO"), {"db_path": db}
        )
        con_hev = kn.recomendar_expediente(db, "HUS528043")["acciones"][0]
        assert con_hev["historico"]["casos"] == 3
        assert con_hev["historico"]["probabilidad"] == 0.8  # calculada, no inventada
        # EPI quedó CANDIDATO: la recomendación NO puede citarla.
        con_epi = kn.recomendar_expediente(db, "HUS528047")["acciones"][0]
        assert "historico" not in con_epi

    def test_lista_y_desconocida(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        assert "LISTO" in kn.recomendar_expediente(db, "HUS528046")["nota"]
        assert "error" in kn.recomendar_expediente(db, "HUS999999")


class TestRootCause:
    def test_concentracion_con_mapa_curado(self, tmp_path, monkeypatch):
        db = _sembrar(tmp_path / "h.db")
        mapa = tmp_path / "causas.json"
        mapa.write_text(
            json.dumps({"HEV": {"causa": "no se escanea al egreso", "area": "Facturación"}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(kn, "RUTA_CAUSAS", mapa)
        r = kn.AgenteRootCause().ejecutar(Mision(codigo="M", tipo="CAUSA_RAIZ"), {"db_path": db})
        assert r.resultado == "OK" and r.salida["causas"]
        # HEV: 2 de 3 en LOTE1/KARIN/COOSALUD (67% ≥ 60%); EPI solo tiene 2 casos.
        assert {c["hallazgo"] for c in r.salida["causas"]} == {"HEV"}
        c = r.salida["causas"][0]
        assert c["proporcion"] == 0.67 and c["casos"] == 2 and c["total"] == 3
        assert c["causa_probable"] == "no se escanea al egreso"
        assert c["area_responsable"] == "Facturación"

    def test_sin_mapa_no_inventa(self, tmp_path, monkeypatch):
        db = _sembrar(tmp_path / "h.db")
        monkeypatch.setattr(kn, "RUTA_CAUSAS", tmp_path / "no_existe.json")
        r = kn.AgenteRootCause().ejecutar(Mision(codigo="M", tipo="CAUSA_RAIZ"), {"db_path": db})
        for c in r.salida["causas"]:
            assert "por determinar" in c["area_responsable"]

    def test_mapa_semilla_del_repo_es_valido(self):
        mapa = json.loads(kn.RUTA_CAUSAS.read_text(encoding="utf-8-sig"))
        for cod, info in mapa.items():
            if cod.startswith("_"):
                continue
            assert info["causa"] and info["area"], f"entrada incompleta: {cod}"


class TestProcessMiner:
    def test_mide_transiciones_y_cuello(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        r = kn.AgenteProcessMiner().ejecutar(
            Mision(codigo="M", tipo="MINAR_PROCESO"), {"db_path": db}
        )
        assert r.resultado == "OK"
        cuello = r.salida["cuello_de_botella"]
        assert cuello["de"] == "INDEXACION" and cuello["a"] == "AUDITORIA"
        assert cuello["casos"] == 2 and cuello["horas_promedio"] == 4.0  # (6+2)/2


class TestSimular:
    def test_escenarios_exactos_por_reglas(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        s = kn.simular(db)
        por_causa = {e["causa"]: e for e in s["escenarios"]}
        # HEV libera SOLO a quienes únicamente esperan HEV: 528043 y 528045.
        assert por_causa["HEV"]["facturas_liberadas"] == 2
        assert por_causa["HEV"]["valor_liberado"] == 5_500_000
        assert por_causa["EPI"]["facturas_liberadas"] == 1  # 528047
        assert "EXACTO" in por_causa["HEV"]["base"]
        # Las dos causas juntas liberan TODO lo pendiente (4 facturas).
        assert s["combinado_top3"]["facturas_liberadas"] == 4
        assert s["combinado_top3"]["valor_liberado"] == 8_400_000

    def test_redistribucion_es_estimacion_etiquetada(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        s = kn.simular(db)
        rd = s["redistribucion"]
        assert rd is not None and "ESTIMACIÓN" in rd["base"] and "supuesto" in rd["base"]

    def test_simular_un_codigo(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        s = kn.simular(db, codigo="hev")
        assert len(s["escenarios"]) == 1 and s["escenarios"][0]["causa"] == "HEV"


class TestAprendizajeAlimentaMemoria:
    def test_ag015_registra_leccion_como_candidato(self, tmp_path):
        """Integración de la regla: AG015 aprende → Memoria (CANDIDATO) →
        nadie la consume hasta que AG019 la valide."""
        from hospiai_directores import AgenteAprendizaje

        db = _sembrar(tmp_path / "h.db")
        r = AgenteAprendizaje().ejecutar(Mision(codigo="M", tipo="APRENDIZAJE"), {"db_path": db})
        assert r.resultado == "OK" and len(r.salida["aprendizajes"]) == 1
        assert "Memoria Institucional" in r.detalle
        m = kn.MemoriaInstitucional(db)
        candidatas = m.consultar("LECCION", solo_validado=False)
        contextos = [json.loads(k["contexto"]) for k in candidatas]
        assert {"codigo": "HEV"} in contextos  # lección general
        assert {"codigo": "HEV", "eps": "COOSALUD"} in contextos  # lección por EPS
        for k in candidatas:
            assert k["estado"] == "CANDIDATO" and k["fuente_agente"] == "AG015"
        assert m.consultar("LECCION") == []  # sin Curator no se sirve
        # Reejecutar no duplica (idempotencia por evento APRENDIZAJE).
        AgenteAprendizaje().ejecutar(Mision(codigo="M2", tipo="APRENDIZAJE"), {"db_path": db})
        general = m.consultar("LECCION", {"codigo": "HEV"}, solo_validado=False)
        assert general and general[0]["ocurrencias"] == 1


class TestAPIYPanel:
    def test_endpoints_del_knowledge_engine(self, tmp_path):
        from hospiai_api import Servicios

        db = _sembrar(tmp_path / "h.db")
        s = Servicios(db)
        rec = s.recomendaciones("HUS528043")
        assert rec["acciones"][0]["base"] == "POR REGLA VIGENTE"
        sim = s.simulaciones()
        assert sim["escenarios"] and sim["combinado_top3"]["facturas_liberadas"] == 4
        assert s.conocimiento() == []  # nada validado todavía
        m = kn.MemoriaInstitucional(db)
        for i in range(3):
            m.registrar("LECCION", "Resolver HEV destraba.", {"codigo": "HEV"}, f"e{i}")
        kn.AgenteKnowledgeCurator().ejecutar(
            Mision(codigo="M", tipo="CURAR_CONOCIMIENTO"), {"db_path": db}
        )
        assert len(s.conocimiento()) == 1

    def test_panel_gerencial_2_muestra_decisiones(self, tmp_path):
        from hospiai_api import Servicios
        from hospiai_panel_ejecutivo import render

        db = _sembrar(tmp_path / "h.db")
        html_out = render(Servicios(db))
        assert "Qué pasaría si" in html_out
        assert "Corregir HEV en todos los expedientes" in html_out
        assert "EXACTO" in html_out


class TestCriterioAceptacion:
    def test_hospiai_recomendar(self, tmp_path, capsys):
        db = _sembrar(tmp_path / "h.db")
        assert hospiai.main(["--db", str(db), "recomendar", "HUS528043"]) == 0
        out = capsys.readouterr().out
        assert "RECOMENDACIONES · HUS528043" in out
        assert "POR REGLA VIGENTE" in out and "HEV" in out and "100%" in out

    def test_hospiai_simular(self, tmp_path, capsys):
        db = _sembrar(tmp_path / "h.db")
        assert hospiai.main(["--db", str(db), "simular"]) == 0
        out = capsys.readouterr().out
        assert "MOTOR DE HIPÓTESIS" in out and "Corregir HEV" in out
        assert "EXACTO" in out and "ESTIMACIÓN" in out
        assert hospiai.main(["--db", str(db), "simular", "--codigo", "HEV"]) == 0

    def test_cli_conocimiento(self, tmp_path, capsys):
        db = _sembrar(tmp_path / "h.db")
        m = kn.MemoriaInstitucional(db)
        for i in range(3):
            m.registrar("LECCION", "Resolver HEV destraba.", {"codigo": "HEV"}, f"e{i}")
        assert kn.main(["--db", str(db), "curar"]) == 0
        assert "1 promovido" in capsys.readouterr().out
        assert kn.main(["--db", str(db), "memoria"]) == 0
        assert "[VALIDADO ]" in capsys.readouterr().out

    def test_registro_central_incluye_ag019_a_ag023(self):
        from hospiai_agentes import registro_con_implementaciones

        reg = registro_con_implementaciones()
        ids = {a["id"] for a in reg.listar()}
        assert {"AG019", "AG020", "AG021", "AG022", "AG023"} <= ids
        for ag_id, capacidad in (
            ("AG019", "CURAR_CONOCIMIENTO"),
            ("AG020", "DESCUBRIR_PATRONES"),
            ("AG021", "RECOMENDAR"),
            ("AG022", "CAUSA_RAIZ"),
            ("AG023", "MINAR_PROCESO"),
        ):
            assert any(a["id"] == ag_id for a in reg.por_capacidad(capacidad)), capacidad
            assert reg.instanciar(ag_id).id == ag_id
