"""Tests de HOSPIAI Fase 1.6 — Agent Framework.

Cubre: el contrato único de agente (formato estándar, captura de errores,
validación → OMITIDO), el Registro Central (data/agentes.json, capacidades,
disponibles), la cola de misiones persistente (crear/tomar/completar/fallar
con reintento), los agentes de referencia sobre el SDK, y el DSL de reglas
(compilación, alias, errores con línea, y paridad con el motor existente).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import hospiai_agentes as hag  # noqa: E402
import hospiai_dsl as dsl  # noqa: E402
import hospiai_sdk as sdk  # noqa: E402
import radicar_facturacion as rad  # noqa: E402


class _AgenteEco(sdk.Agente):
    id = "AG998"
    nombre = "Eco"
    dominio = "TEST"
    version = "9.9"
    entradas = ["mensaje"]
    salidas = ["eco"]
    capacidades = ["ECO"]

    def _trabajar(self, mision, contexto, res):
        res.salida = {"eco": mision.datos["mensaje"].upper()}
        res.detalle = "eco emitido"


class _AgenteQueFalla(sdk.Agente):
    id = "AG999"
    nombre = "Fallador"
    dominio = "TEST"
    capacidades = ["FALLAR"]

    def _trabajar(self, mision, contexto, res):
        raise RuntimeError("explotó a propósito")


class TestContratoAgente:
    def test_resultado_estandar(self):
        m = sdk.Mision(
            codigo="MISION-000001", tipo="ECO", expediente="528043", datos={"mensaje": "hola"}
        )
        res = _AgenteEco().ejecutar(m, {"version_reglas": "1.0"})
        d = res.a_dict()
        # El formato es EXACTAMENTE el mismo para todos los agentes.
        assert set(d) == {
            "agente",
            "version",
            "expediente",
            "resultado",
            "confianza",
            "hallazgos",
            "evidencias",
            "salida",
            "detalle",
            "duracion_ms",
            "versiones",
        }
        assert d["agente"] == "AG998" and d["resultado"] == "OK"
        assert d["salida"]["eco"] == "HOLA"
        assert d["versiones"]["reglas"] == "1.0" and d["versiones"]["agente"] == "9.9"
        assert d["duracion_ms"] >= 0

    def test_error_capturado_no_tumba_la_plataforma(self):
        m = sdk.Mision(codigo="MISION-000002", tipo="FALLAR")
        res = _AgenteQueFalla().ejecutar(m)
        assert res.resultado == "ERROR"
        assert "explotó a propósito" in res.detalle
        assert res.confianza == 0.0

    def test_mision_no_atendible_queda_omitida(self):
        m = sdk.Mision(codigo="MISION-000003", tipo="OCR", datos={})
        res = _AgenteEco().ejecutar(m)
        assert res.resultado == "OMITIDO"
        assert "no atiende" in res.detalle

    def test_entradas_faltantes_omiten(self):
        m = sdk.Mision(codigo="MISION-000004", tipo="ECO", datos={})
        res = _AgenteEco().ejecutar(m)
        assert res.resultado == "OMITIDO" and "mensaje" in res.detalle

    def test_explicar_sin_mirar_codigo(self):
        exp = _AgenteEco().explicar()
        assert exp["id"] == "AG998"
        assert exp["capacidades"] == ["ECO"]
        assert exp["entradas"] == ["mensaje"] and exp["salidas"] == ["eco"]


class TestRegistroCentral:
    def test_carga_del_repo(self):
        reg = hag.registro_con_implementaciones()
        ids = [a["id"] for a in reg.listar()]
        assert "AG002" in ids and "AG010" in ids
        # AG010 (Supervisor) ya es ACTIVO desde Fase 2; el OCR sigue PLANEADO
        # y por eso NO aparece entre los disponibles.
        assert any(a["id"] == "AG010" for a in reg.disponibles())
        assert all(a["id"] != "AG004" for a in reg.disponibles())

    def test_busqueda_por_capacidad(self):
        reg = hag.registro_con_implementaciones()
        assert [a["id"] for a in reg.por_capacidad("ANALIZAR_RUTA")] == ["AG002"]
        # OCR existe en el registro pero PLANEADO → no disponible aún.
        assert reg.por_capacidad("OCR") == []

    def test_instanciar_por_id_no_por_clase(self):
        reg = hag.registro_con_implementaciones()
        ag = reg.instanciar("AG003")
        assert ag.nombre == "ClasificadorDocumental"
        with pytest.raises(KeyError):
            reg.instanciar("AG004")  # sin implementación todavía


class TestColaMisiones:
    def test_ciclo_completo(self, tmp_path):
        cola = sdk.ColaMisiones(tmp_path / "h.db")
        m = cola.crear(
            "ANALIZAR_RUTA",
            expediente="528043",
            prioridad="ALTA",
            datos={"ruta": "Y:\\x"},
            creada_por="AG001",
        )
        assert m.codigo.startswith("MISION-") and m.estado == "PENDIENTE"
        tomada = cola.tomar(["ANALIZAR_RUTA"], "AG002")
        assert tomada is not None and tomada.codigo == m.codigo
        assert cola.tomar(["ANALIZAR_RUTA"], "AG002") is None  # ya no hay pendientes
        res = sdk.ResultadoAgente(agente="AG002", version="1.1", resultado="OK")
        cola.completar(tomada, res)
        assert cola.estado() == {"OK": 1}

    def test_prioridad_alta_primero(self, tmp_path):
        cola = sdk.ColaMisiones(tmp_path / "h.db")
        cola.crear("T", datos={}, prioridad="NORMAL")
        alta = cola.crear("T", datos={}, prioridad="ALTA")
        assert cola.tomar(["T"], "X").codigo == alta.codigo

    def test_fallo_reintenta_y_luego_error(self, tmp_path):
        cola = sdk.ColaMisiones(tmp_path / "h.db")
        cola.crear("T", datos={}, max_intentos=2)
        err = sdk.ResultadoAgente(agente="X", version="1", resultado="ERROR")
        m1 = cola.tomar(["T"], "X")
        cola.fallar(m1, err)  # intento 1/2 → vuelve a PENDIENTE
        assert cola.estado() == {"PENDIENTE": 1}
        m2 = cola.tomar(["T"], "X")
        cola.fallar(m2, err)  # intento 2/2 → ERROR definitivo
        assert cola.estado() == {"ERROR": 1}


class TestAgentesReferencia:
    def test_analizador_ruta_como_agente(self, tmp_path):
        db = tmp_path / "h.db"
        cola = sdk.ColaMisiones(db)
        cola.crear(
            "ANALIZAR_RUTA",
            expediente="528043",
            datos={
                "ruta": r"Y:\7. JULIO 2026 - SOPORTES RADICACION\ASMET SALUD\LILIANA"
                r"\ENV-230314-OKDGH\HUS528043\EPI.pdf"
            },
        )
        tomada = cola.tomar(["ANALIZAR_RUTA"], "AG002")
        res = hag.AgenteAnalizadorRuta().ejecutar(tomada, {"db_path": db})
        cola.completar(tomada, res)
        assert res.resultado == "OK"
        assert res.salida["responsable"] == "LILIANA"
        assert res.salida["lote"] == "ENV-230314-OKDGH"
        # Dejó huella en el Expediente Digital (evento con misión y duración).
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        ev = con.execute("SELECT * FROM eventos WHERE factura_norm='528043'").fetchone()
        assert ev["agente"] == "AG002 v1.1" and "MISION-" in ev["detalle"]
        con.close()

    def test_clasificador_reporta_hallazgo_si_no_reconoce(self, tmp_path):
        db = tmp_path / "h.db"
        m = sdk.Mision(
            codigo="MISION-000009",
            tipo="CLASIFICAR_DOCUMENTO",
            expediente="1",
            datos={"nombre": "documento_raro.pdf"},
        )
        res = hag.AgenteClasificadorDocumental().ejecutar(m, {"db_path": db})
        assert res.salida["reconocido"] is False
        assert res.confianza == 0.5
        con = sqlite3.connect(db)
        n = con.execute("SELECT COUNT(*) FROM hallazgos WHERE tipo='SIN_TIPIFICAR'").fetchone()[0]
        con.close()
        assert n == 1


class TestDSL:
    def test_compila_regla_de_cirugia(self):
        texto = """
        VERSION 2.0
        REGLA CIRUGIA_MAYOR
        SI SERVICIO = CIRUGIA
        REQUIERE DQX RAN EPI HEV
        SI FALTA REVISAR
        FUENTE Resolución 2284 de 2023
        VIGENCIA DESDE 2024-01-01
        NOTA La cirugía exige sus soportes quirúrgicos.
        FIN
        """
        data = dsl.compilar(texto)
        rg = data["reglas"][0]
        assert data["version"] == "2.0"
        assert rg["id"] == "CIRUGIA_MAYOR"
        assert rg["ambito"] == {"servicio": "procedimientos"}  # alias CIRUGIA
        assert rg["exige"] == ["DQX", "RAN", "EPI", "HEV"]
        assert rg["criticidad"] == "REVISAR"
        assert "2284" in rg["fuente"]
        assert rg["vigencia_desde"] == "2024-01-01"

    def test_error_con_linea_y_motivo(self):
        with pytest.raises(dsl.ErrorDSL) as e:
            dsl.compilar("REGLA X\nSI SERVICIO = MARCIANO\nFIN")
        assert "línea 2" in str(e.value) and "MARCIANO" in str(e.value)

    def test_regla_sin_fin_falla(self):
        with pytest.raises(dsl.ErrorDSL) as e:
            dsl.compilar("REGLA X\nSI TODAS\nREQUIERE FEV")
        assert "sin FIN" in str(e.value)

    def test_paridad_con_el_motor(self, tmp_path):
        # El ejemplo del repo compila y, cargado en el motor, produce las MISMAS
        # exigencias que las reglas JSON vigentes: el DSL no cambia el negocio.
        ejemplo = _TOOLS.parent / "data" / "ejemplo_reglas.hospiai"
        data = dsl.compilar(ejemplo.read_text(encoding="utf-8-sig"))
        f = tmp_path / "compiladas.json"
        f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        cfg = rad.ConfigRadicacion()
        rad.cargar_reglas(f, cfg)
        assert cfg.soportes_base == ["FEV", "RIP", "CUV"]
        for serv, cods in rad.SOPORTES_POR_SERVICIO_DEFAULT.items():
            if serv == "consultas":  # la consulta no exige clínicos: sin regla
                continue
            assert cfg.soportes_por_servicio.get(serv, []) == cods, serv
        assert cfg.equivalencias_soporte == {"EPI": ["EPI", "HEV"], "HAU": ["HAU", "HEV"]}

    def test_cli_verificar_y_compilar(self, tmp_path, capsys):
        ejemplo = _TOOLS.parent / "data" / "ejemplo_reglas.hospiai"
        assert dsl.main(["verificar", str(ejemplo)]) == 0
        assert "regla(s)" in capsys.readouterr().out
        salida = tmp_path / "out.json"
        assert dsl.main(["compilar", str(ejemplo), "--salida", str(salida)]) == 0
        assert json.loads(salida.read_text(encoding="utf-8"))["reglas"]


class TestConsolaAgentes:
    def test_comando_agentes_y_misiones(self, tmp_path, capsys):
        import hospiai

        assert hospiai.main(["agentes"]) == 0
        out = capsys.readouterr().out
        assert "AG002" in out and "AnalizadorRuta" in out and "PLANEADO" in out
        db = tmp_path / "h.db"
        sdk.ColaMisiones(db).crear("ANALIZAR_RUTA", datos={"ruta": "x"})
        assert hospiai.main(["--db", str(db), "misiones"]) == 0
        assert "PENDIENTE" in capsys.readouterr().out
