"""Tests de Operational Intelligence (Fase 3 · AG024–AG028).

Verifica los dos criterios de aceptación (`hospiai.py plan HUS…` y
`hospiai.py oportunidades`) y la honestidad de cada pieza: tiempos solo del
mapa curado (jamás inventados), ASOCIAR solo si el soporte existe de verdad en
el índice, dinero EXACTO por reglas, indicadores sin datos en None con razón,
y la regla de oro (justificación operativa) presente en las fichas nuevas.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # para reusar la semilla

import hospiai  # noqa: E402
import hospiai_db  # noqa: E402
import hospiai_operacion as op  # noqa: E402
from hospiai_sdk import Mision  # noqa: E402
from test_hospiai_conocimiento import _sembrar  # noqa: E402


def _indices(tmp_path: Path) -> Path:
    """Índice permanente sintético: HEV de 528043 YA existe en el servidor
    'y'; el resto no está indexado. 528045 tiene un archivo sin tipificar."""
    import hospiai_indexador as idx

    d = tmp_path / "indices"
    if (d / "indice_y.db").exists():
        return d
    con = idx._abrir(d / "indice_y.db")
    with con:
        con.execute(
            "INSERT INTO archivos(ruta, nombre, factura, tipo, reconocido, tamano,"
            " ultima_modificacion, visto_primera, visto_ultima, servidor, estado)"
            " VALUES('Y:/EPS/HUS528043/HEV_900006037_HUS528043.pdf',"
            " 'HEV_900006037_HUS528043.pdf', '528043', 'HEV', 1, 10, 0,"
            " '2026-07-21', '2026-07-21', 'y', 'ACTIVO')"
        )
        con.execute(
            "INSERT INTO archivos(ruta, nombre, factura, tipo, reconocido, tamano,"
            " ultima_modificacion, visto_primera, visto_ultima, servidor, estado)"
            " VALUES('Y:/EPS/HUS528045/escaneo_raro.pdf', 'escaneo_raro.pdf',"
            " '528045', 'ADM', 0, 10, 0, '2026-07-21', '2026-07-21', 'y', 'ACTIVO')"
        )
    con.close()
    return d


class TestIndiceGlobal:
    def test_lee_reconocidos_y_sin_tipificar(self, tmp_path):
        d = _indices(tmp_path)
        tiene, sin_tip = op.indice_global(d)
        assert tiene["528043"]["HEV"] == "y"
        assert sin_tip == {"528045": 1}

    def test_equivalencias_del_motor(self, tmp_path):
        # Un HEV presente satisface EPI/HAU (regla del área en el motor).
        d = _indices(tmp_path)
        tiene, _ = op.indice_global(d)
        assert op._existe_en_indice("528043", "EPI", tiene) == "y"
        assert op._existe_en_indice("528043", "RIP", tiene) == ""


class TestPlanRecuperacion:
    def test_asociar_cuando_ya_existe(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        p = op.plan_expediente(db, "HUS528043", _indices(tmp_path))
        assert len(p["pasos"]) == 1
        paso = p["pasos"][0]
        assert paso["modo"] == "ASOCIAR" and "servidor 'y'" in paso["accion"]
        assert paso["probabilidad"] == 1.0  # por regla vigente: único faltante
        assert "POR REGLA VIGENTE" in paso["base_probabilidad"]
        assert "LISTA" in paso["impacto"] and "4,000,000" in paso["impacto"]
        # El tiempo viene del mapa curado (entrada ASOCIAR), citando la fuente.
        assert paso["tiempo_min"] == 1 and "esfuerzos.json" in paso["fuente_tiempo"]
        assert p["total_minutos"] == 1 and p["tiempos_completos"]

    def test_conseguir_cuando_no_existe(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        p = op.plan_expediente(db, "HUS528047", _indices(tmp_path))
        paso = p["pasos"][0]
        assert paso["modo"] == "CONSEGUIR" and paso["causa"] == "EPI"
        assert paso["responsable"] == "Historias Clínicas"  # data/esfuerzos.json
        assert paso["tiempo_min"] == 3

    def test_tiempo_desconocido_no_se_inventa(self, tmp_path, monkeypatch):
        db = _sembrar(tmp_path / "h.db")
        monkeypatch.setattr(op, "RUTA_ESFUERZOS", tmp_path / "no_existe.json")
        p = op.plan_expediente(db, "HUS528047", _indices(tmp_path))
        paso = p["pasos"][0]
        assert paso["tiempo_min"] is None and "por estimar" in paso["fuente_tiempo"]
        assert not p["tiempos_completos"]

    def test_lista_y_desconocida(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        assert op.plan_expediente(db, "HUS528046", _indices(tmp_path))["pasos"] == []
        assert "error" in op.plan_expediente(db, "HUS999999", _indices(tmp_path))


class TestOportunidades:
    def test_masivas_exactas_y_asociables(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        o = op.oportunidades(db, _indices(tmp_path))
        por_nombre = {x["oportunidad"]: x for x in o["oportunidades"]}
        asociar = next(x for n, x in por_nombre.items() if n.startswith("Asociar HEV"))
        # 528043 y 528044 faltan HEV… pero solo 528043 lo tiene indexado.
        assert asociar["expedientes"] == 1
        assert asociar["facturas_liberadas"] == 1  # 528043 queda LISTA solo con eso
        assert asociar["valor_liberado"] == 4_000_000
        assert "índice" in asociar["base"]
        conseguir_hev = next(x for n, x in por_nombre.items() if n == "Conseguir/corregir HEV")
        assert conseguir_hev["facturas_liberadas"] == 1  # 528045 (no indexado)
        assert conseguir_hev["valor_liberado"] == 1_500_000
        # Totales exactos: todos los pendientes con hallazgos.
        assert o["facturas_potenciales"] == 4
        assert o["total_recuperable"] == 8_400_000
        # Los sin tipificar se reportan como POTENCIAL, sin dinero inventado.
        assert o["sin_tipificar"]["expedientes"] == 1
        assert o["sin_tipificar"]["valor_liberado"] is None
        assert "POTENCIAL" in o["sin_tipificar"]["base"]

    def test_agente_solo_propone(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        res = op.AgenteCorreccionMasiva().ejecutar(
            Mision(codigo="M", tipo="CORRECCION_MASIVA"),
            {"db_path": db, "dir_indices": _indices(tmp_path)},
        )
        assert res.resultado == "OK"
        assert "recuperable" in res.detalle
        nota = res.salida["oportunidades"]["nota"]
        assert "Nada se ejecuta" in nota


class TestIndicadores:
    def test_cuatro_bloques_honestos(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        ind = op.calcular_indicadores(db)
        assert ind["calidad"]["pct_listas"] == 20.0  # 1 de 5
        assert ind["calidad"]["pct_revisar"] == 80.0
        assert ind["financieros"]["valor_listo"] == 3_000_000
        assert ind["financieros"]["valor_recuperable"] == 8_400_000
        # Lo que no se puede medir queda None con su razón — no un número.
        assert ind["financieros"]["valor_perdido"] is None
        assert ind["operativos"]["dias_hasta_pago"] is None
        # 528046: REVISAR (corrida 1) → LISTA (corrida 2) = 1 día.
        assert ind["operativos"]["casos_hasta_lista"] == 1
        assert ind["operativos"]["dias_hasta_lista"] == 1.0
        # Y quedó persistido para comparar corridas.
        con = hospiai_db.abrir(db)
        filas = con.execute("SELECT COUNT(*) n FROM indicadores WHERE corrida_id=2").fetchone()
        con.close()
        assert filas["n"] >= 12

    def test_repersistir_no_duplica(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        op.calcular_indicadores(db)
        op.calcular_indicadores(db)
        con = hospiai_db.abrir(db)
        n = con.execute("SELECT COUNT(*) n FROM indicadores WHERE nombre='pct_listas'").fetchone()[
            "n"
        ]
        con.close()
        assert n == 1


class TestFichaYGemelo:
    def test_ficha_viva_por_pagador(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        fichas = {f["pagador"]: f for f in op.ficha_pagador(db)}
        coo = fichas["COOSALUD"]
        assert coo["expedientes"] == 3 and coo["pct_listas"] == 33.3
        assert coo["valor_detenido"] == 6_000_000
        assert coo["causas_frecuentes"][0].startswith("HEV")
        assert "sin historial" in coo["nota_historial"]  # glosas aún no cargadas
        assert "HEV" in coo["recomendacion"]
        solo = op.ficha_pagador(db, "NUEVA")
        assert len(solo) == 1 and solo[0]["pagador"] == "NUEVA EPS"

    def test_gemelo_declara_fuentes_y_vacios(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        g = op.gemelo_eps(db, "COOSALUD")
        assert g["expedientes"] == 3 and g["pct_listas"] == 33.3
        assert g["exigencia_observada_pct"] == 66.7  # 2 de 3 con hallazgos
        assert "interna" in g["fuente_exigencia"]
        assert g["faltantes_tipicos"][0].startswith("HEV")
        assert g["demora_promedio_dias"] is None and "historial" in g["nota_demora"]
        assert "sin historial de glosas" in g["devuelve_frecuentemente"][0]
        assert "error" in op.gemelo_eps(db, "NO_EXISTE")


class TestMejoraContinua:
    def test_informe_del_viernes(self, tmp_path):
        db = _sembrar(tmp_path / "h.db")
        m = op.mejora_semanal(db, _indices(tmp_path))
        # 528046 pasó a LISTA y su HEV desapareció entre corridas.
        assert any("% LISTAS" in x for x in m["que_mejoro"])
        assert m["cambiar_el_lunes"]  # las oportunidades top con su cifra
        assert any("$" in x for x in m["cambiar_el_lunes"])
        r = op.AgenteMejoraContinua().ejecutar(
            Mision(codigo="M", tipo="MEJORA_CONTINUA"),
            {"db_path": db, "dir_indices": _indices(tmp_path)},
        )
        assert r.resultado == "OK"


class TestCriterioAceptacion:
    def test_hospiai_plan(self, tmp_path, capsys, monkeypatch):
        db = _sembrar(tmp_path / "h.db")
        import hospiai_indexador as idx

        monkeypatch.setattr(idx, "DIR_INDICES", _indices(tmp_path))
        assert hospiai.main(["--db", str(db), "plan", "HUS528043"]) == 0
        out = capsys.readouterr().out
        assert "PLAN DE RECUPERACIÓN · HUS528043" in out
        assert "Para quedar LISTA debe:" in out
        assert "Asociar HEV" in out and "Responsable" in out
        assert "Tiempo estimado" in out and "Probabilidad     : 100%" in out
        assert "Pasa inmediatamente a LISTA" in out

    def test_hospiai_oportunidades(self, tmp_path, capsys, monkeypatch):
        db = _sembrar(tmp_path / "h.db")
        import hospiai_indexador as idx

        monkeypatch.setattr(idx, "DIR_INDICES", _indices(tmp_path))
        assert hospiai.main(["--db", str(db), "oportunidades"]) == 0
        out = capsys.readouterr().out
        assert "OPORTUNIDADES DE ALTO IMPACTO" in out
        assert "Asociar HEV" in out and "TOTAL recuperable: $ 8,400,000" in out
        assert "Facturas potencialmente liberadas: 4" in out

    def test_api_y_panel_sirven_fase3(self, tmp_path, monkeypatch):
        from hospiai_api import Servicios
        from hospiai_panel_ejecutivo import render

        db = _sembrar(tmp_path / "h.db")
        import hospiai_indexador as idx

        monkeypatch.setattr(idx, "DIR_INDICES", _indices(tmp_path))
        s = Servicios(db)
        assert s.plan("HUS528043")["pasos"]
        assert s.oportunidades()["total_recuperable"] == 8_400_000
        assert s.indicadores()["calidad"]["pct_listas"] == 20.0
        assert s.fichas("COOSALUD")[0]["expedientes"] == 3
        assert s.gemelo("COOSALUD")["exigencia_observada_pct"] == 66.7
        assert s.mejora()["cambiar_el_lunes"]
        html_out = render(s)
        assert "Oportunidades de alto impacto" in html_out
        assert "nada se ejecuta" in html_out

    def test_regla_de_oro_en_las_fichas(self):
        """Todo agente de la Fase 3 responde las 5 preguntas obligatorias."""
        registro = json.loads(
            (Path(__file__).resolve().parent.parent.parent / "data" / "agentes.json").read_text(
                encoding="utf-8-sig"
            )
        )
        fichas = {a["id"]: a for a in registro["agentes"]}
        for ag in ("AG024", "AG025", "AG026", "AG027", "AG028"):
            j = fichas[ag].get("justificacion_operativa")
            assert j, f"{ag} sin justificación operativa (regla de oro)"
            for pregunta in ("problema", "dinero", "horas", "indicador", "medicion"):
                assert j.get(pregunta), f"{ag}: falta '{pregunta}'"

    def test_registro_central_incluye_ag024_a_ag028(self):
        from hospiai_agentes import registro_con_implementaciones

        reg = registro_con_implementaciones()
        for ag_id, capacidad in (
            ("AG024", "PLAN_RECUPERACION"),
            ("AG025", "CORRECCION_MASIVA"),
            ("AG026", "FICHA_CONTRATO"),
            ("AG027", "GEMELO_EPS"),
            ("AG028", "MEJORA_CONTINUA"),
        ):
            assert any(a["id"] == ag_id for a in reg.por_capacidad(capacidad)), capacidad
            assert reg.instanciar(ag_id).id == ag_id
