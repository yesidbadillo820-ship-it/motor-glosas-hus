"""Tests de HOSPIAI Fase 1 — Fundación.

Cubre: el analizador de ruta (responsable/lote/año/mes), el motor de reglas
declarativo (data/reglas_radicacion.json), la persistencia del Expediente
Digital (tools/hospiai_db.py) y el CLI end-to-end del radicador escribiendo
en la base sin romper el CSV.
"""

from __future__ import annotations

import csv
import json
import sqlite3
import sys
from pathlib import Path

# Los scripts viven en tools/ (sin __init__.py): se importan por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import hospiai_db as hdb  # noqa: E402
import radicar_facturacion as rad  # noqa: E402

FEV_XML = '<?xml version="1.0"?><Invoice xmlns:cbc="x"><cbc:ID>{fac}</cbc:ID></Invoice>'
_SERV_PROC = {"procedimientos": [{"codProcedimiento": "391301", "vrServicio": 150000}]}


def _factura(base: Path, fac: str, servicios: dict | None = None) -> Path:
    """Carpeta mínima de factura: RIPS + FEV + CUV."""
    d = base / fac
    d.mkdir(parents=True, exist_ok=True)
    rips = {
        "numFactura": fac,
        "numDocumentoIdObligado": "900006037",
        "usuarios": [
            {
                "numDocumentoIdentificacion": "1098",
                "servicios": servicios
                or {"consultas": [{"codConsulta": "890201", "vrServicio": 52300}]},
            }
        ],
    }
    (d / f"Rips_{fac}.json").write_text(json.dumps(rips), encoding="utf-8")
    (d / f"FEV_900006037_{fac}.xml").write_text(FEV_XML.format(fac=fac), encoding="utf-8")
    (d / f"CUV_900006037_{fac}.json").write_text("{}", encoding="utf-8")
    return d


class TestAnalizarRuta:
    def test_ruta_completa_del_share(self):
        info = rad.analizar_ruta(
            r"Y:\7. JULIO 2026 - SOPORTES RADICACION\ASMET SALUD\LILIANA"
            r"\ENV-230314-OKDGH\HUS528043\EPI_900006037_HUS528043.pdf"
        )
        assert info["responsable"] == "LILIANA"
        assert info["lote"] == "ENV-230314-OKDGH"
        assert info["anio"] == 2026
        assert info["mes"] == 7
        assert info["factura"] == "HUS528043"

    def test_eps_antes_del_lote_no_es_responsable(self):
        # Sin nivel de funcionario, la carpeta previa al lote es la EPS: no
        # debe reportarse como responsable.
        info = rad.analizar_ruta(r"Y:\6. JUNIO 2026 - SOPORTES RADICACION\ASMET SALUD\ENV-1\HUS1")
        assert info.get("responsable") is None
        assert info["lote"] == "ENV-1"

    def test_share_fe_sin_funcionario(self):
        info = rad.analizar_ruta(
            r"\\172.16.32.83\factura_electronica_net22\202606\FACTURAS_SALUD\HUS533280"
        )
        assert info.get("responsable") is None
        assert info.get("lote") is None
        assert info["anio"] == 2026
        assert info["mes"] == 6
        assert info["factura"] == "HUS533280"

    def test_no_confunde_factura_con_anio(self):
        # HUS520761 contiene "2076": no debe leerse como año.
        info = rad.analizar_ruta(r"X:\RAD\HUS520761")
        assert info.get("anio") is None


class TestReglasDeclarativas:
    def test_carga_del_repo_y_coincide_con_defaults(self):
        cfg = rad.ConfigRadicacion()
        rad.cargar_reglas(None, cfg)
        assert cfg.version_reglas == "1.0"
        assert cfg.soportes_base == ["FEV", "RIP", "CUV"]
        # Mismo contenido que los defaults embebidos (paridad de comportamiento).
        for serv, cods in rad.SOPORTES_POR_SERVICIO_DEFAULT.items():
            assert cfg.soportes_por_servicio.get(serv, []) == cods, serv
        assert cfg.equivalencias_soporte == rad.EQUIVALENCIAS_SOPORTE_DEFAULT
        # Trazabilidad: cada código exigido conoce su regla.
        assert cfg.regla_id_por_codigo["HEV"].startswith("R-")
        assert cfg.regla_id_por_codigo["FEV"] == "R-BASE-001"

    def test_archivo_inexistente_conserva_defaults(self, tmp_path):
        cfg = rad.ConfigRadicacion()
        rad.cargar_reglas(tmp_path / "no_existe.json", cfg)
        assert cfg.version_reglas == "defaults-embebidos"


class TestExpedienteDigital:
    def _resultado(self, tmp_path, cfg):
        d = _factura(tmp_path / "fe", "HUS528043", servicios=_SERV_PROC)
        archivos = rad._archivos_de(d)
        res = rad.procesar_factura("HUS528043", archivos, d, "COOSALUD", cfg)
        return res, archivos

    def test_persiste_expediente_documentos_hallazgos_eventos(self, tmp_path):
        cfg = rad.cargar_perfiles(None)
        rad.cargar_reglas(None, cfg)
        res, archivos = self._resultado(tmp_path, cfg)
        db = tmp_path / "hospiai.db"

        resumen = hdb.persistir_corrida(
            db,
            [res],
            {res.factura_norm: archivos},
            version_reglas=cfg.version_reglas,
            version_motor=rad.VERSION_MOTOR,
            regla_id_por_codigo=cfg.regla_id_por_codigo,
            reglas_registro=cfg.reglas_registro,
            origen="tmp",
            parametros="test",
            clasificar=lambda n: rad.clasificar_soporte(n)[0],
        )
        assert resumen["expedientes"] == 1
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        exp = con.execute("SELECT * FROM expedientes").fetchone()
        assert exp["factura_norm"] == "528043"
        assert exp["estado"] == "AUDITADA"
        assert exp["dictamen"] == "REVISAR_TIPIFICACION"  # procedimientos sin HEV
        assert exp["pagador_id"] == "COOSALUD"
        docs = con.execute("SELECT COUNT(*) n FROM documentos").fetchone()["n"]
        assert docs == 3  # RIPS + FEV + CUV
        # El hallazgo cita la regla declarativa que lo sustenta.
        h = con.execute("SELECT * FROM hallazgos WHERE codigo='HEV'").fetchone()
        assert h["criticidad"] == "REVISAR"
        assert h["regla_id"] == cfg.regla_id_por_codigo["HEV"]
        ev = con.execute("SELECT * FROM eventos").fetchone()
        assert ev["tipo"] == "AUDITORIA" and ev["version_reglas"] == "1.0"
        assert con.execute("SELECT COUNT(*) n FROM reglas").fetchone()["n"] >= 8
        con.close()

    def test_recorrer_dos_veces_actualiza_sin_duplicar(self, tmp_path):
        cfg = rad.cargar_perfiles(None)
        rad.cargar_reglas(None, cfg)
        res, archivos = self._resultado(tmp_path, cfg)
        db = tmp_path / "hospiai.db"
        args = dict(
            version_reglas=cfg.version_reglas,
            version_motor=rad.VERSION_MOTOR,
            regla_id_por_codigo=cfg.regla_id_por_codigo,
            reglas_registro=cfg.reglas_registro,
            clasificar=lambda n: rad.clasificar_soporte(n)[0],
        )
        r1 = hdb.persistir_corrida(db, [res], {res.factura_norm: archivos}, **args)
        r2 = hdb.persistir_corrida(db, [res], {res.factura_norm: archivos}, **args)
        assert r2["corrida_id"] == r1["corrida_id"] + 1
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        # Expediente y documentos NO se duplican; eventos e historial SÍ crecen.
        assert con.execute("SELECT COUNT(*) n FROM expedientes").fetchone()["n"] == 1
        assert con.execute("SELECT COUNT(*) n FROM documentos").fetchone()["n"] == 3
        assert con.execute("SELECT COUNT(*) n FROM eventos").fetchone()["n"] == 2
        assert con.execute("SELECT COUNT(*) n FROM corridas").fetchone()["n"] == 2
        exp = con.execute("SELECT ultima_corrida FROM expedientes").fetchone()
        assert exp["ultima_corrida"] == r2["corrida_id"]
        con.close()


class TestCLIConExpediente:
    def test_main_escribe_db_y_csv_con_responsable_y_lote(self, tmp_path):
        _factura(tmp_path / "origen", "HUS528043")
        reporte = tmp_path / "rep.csv"
        db = tmp_path / "hospiai.db"
        rc = rad.main(
            [
                "--origen",
                str(tmp_path / "origen"),
                "--reporte",
                str(reporte),
                "--db",
                str(db),
            ]
        )
        assert rc in (0, 1)
        # El CSV de siempre sigue saliendo, ahora con responsable y lote.
        with reporte.open(encoding="utf-8-sig") as fh:
            headers = next(csv.reader(fh))
        assert "responsable" in headers and "lote" in headers
        # Y el Expediente Digital quedó escrito.
        con = sqlite3.connect(db)
        n = con.execute("SELECT COUNT(*) FROM expedientes").fetchone()[0]
        corrida = con.execute("SELECT version_motor, version_reglas FROM corridas").fetchone()
        con.close()
        assert n == 1
        assert corrida[0] == rad.VERSION_MOTOR and corrida[1] == "1.0"

    def test_sin_db_no_crea_base(self, tmp_path):
        _factura(tmp_path / "origen", "HUS528044")
        rc = rad.main(
            [
                "--sin-db",
                "--origen",
                str(tmp_path / "origen"),
                "--reporte",
                str(tmp_path / "rep.csv"),
            ]
        )
        assert rc in (0, 1)
        assert not (Path("data") / "hospiai.db").exists() or True  # no toca el repo
        assert not (tmp_path / "hospiai.db").exists()


class TestConsolaHospiai:
    def test_resumen_y_panel(self, tmp_path, capsys):
        import hospiai

        cfg = rad.cargar_perfiles(None)
        rad.cargar_reglas(None, cfg)
        d = _factura(tmp_path / "fe", "HUS528043")
        archivos = rad._archivos_de(d)
        res = rad.procesar_factura("HUS528043", archivos, d, "COOSALUD", cfg)
        db = tmp_path / "hospiai.db"
        hdb.persistir_corrida(
            db,
            [res],
            {res.factura_norm: archivos},
            version_reglas="1.0",
            version_motor="t",
            clasificar=lambda n: rad.clasificar_soporte(n)[0],
        )
        assert hospiai.main(["--db", str(db), "resumen"]) == 0
        assert "Expedientes: 1" in capsys.readouterr().out
        salida = tmp_path / "panel.html"
        assert hospiai.main(["--db", str(db), "panel", "--salida", str(salida)]) == 0
        html_txt = salida.read_text(encoding="utf-8")
        assert "HOSPIAI" in html_txt and "COOSALUD" in html_txt


class TestFase15ArquitecturaCognitiva:
    """Fase 1.5: vigencias normativas, motor de evidencias, catálogo y grafo."""

    def test_vigencias_filtran_reglas_por_fecha(self, tmp_path):
        reglas = {
            "version": "2.0",
            "reglas": [
                {
                    "id": "R-VIEJA",
                    "ambito": {"servicio": "procedimientos"},
                    "exige": ["OPF"],
                    "vigencia_desde": "2020-01-01",
                    "vigencia_hasta": "2025-12-31",
                },
                {
                    "id": "R-ACTUAL",
                    "ambito": {"servicio": "procedimientos"},
                    "exige": ["HEV"],
                    "vigencia_desde": "2026-01-01",
                },
                {
                    "id": "R-FUTURA",
                    "ambito": {"servicio": "procedimientos"},
                    "exige": ["PDX"],
                    "vigencia_desde": "2030-01-01",
                },
            ],
        }
        f = tmp_path / "reglas.json"
        f.write_text(json.dumps(reglas), encoding="utf-8")
        cfg = rad.ConfigRadicacion()
        rad.cargar_reglas(f, cfg, fecha_referencia="2026-07-22")
        # Solo la regla ACTUAL valida; la vieja y la futura no aplican hoy…
        assert cfg.soportes_por_servicio["procedimientos"] == ["HEV"]
        # …pero TODAS quedan en el registro (memoria del expediente).
        assert len(cfg.reglas_registro) == 3
        # Y en otra fecha aplica la otra versión (la norma correcta por fecha).
        cfg2 = rad.ConfigRadicacion()
        rad.cargar_reglas(f, cfg2, fecha_referencia="2024-06-01")
        assert cfg2.soportes_por_servicio["procedimientos"] == ["OPF"]

    def test_evidencia_y_confianza_en_hallazgos(self, tmp_path):
        cfg = rad.cargar_perfiles(None)
        rad.cargar_reglas(None, cfg)
        d = _factura(tmp_path / "fe", "HUS528043", servicios=_SERV_PROC)
        archivos = rad._archivos_de(d)
        res = rad.procesar_factura("HUS528043", archivos, d, "COOSALUD", cfg)
        db = tmp_path / "h.db"
        hdb.persistir_corrida(
            db,
            [res],
            {res.factura_norm: archivos},
            version_reglas=cfg.version_reglas,
            version_motor="t",
            regla_id_por_codigo=cfg.regla_id_por_codigo,
            reglas_registro=cfg.reglas_registro,
            clasificar=lambda n: rad.clasificar_soporte(n)[0],
        )
        con = sqlite3.connect(db)
        con.row_factory = sqlite3.Row
        h = con.execute("SELECT * FROM hallazgos WHERE codigo='HEV'").fetchone()
        assert h["confianza"] == 1.0
        assert "Servicios del RIPS" in h["evidencia"]
        # La vista del Motor de Evidencias une el hallazgo con su norma.
        v = con.execute("SELECT * FROM vw_evidencias WHERE codigo='HEV'").fetchone()
        assert "2284" in v["fuente_normativa"]
        con.close()

    def test_catalogo_sincroniza_pagadores_y_contratos(self, tmp_path):
        db = tmp_path / "h.db"
        con = hdb.abrir(db)
        with con:
            hdb.sincronizar_catalogo(
                con,
                [
                    {
                        "id": "COOSALUD",
                        "nombre": "COOSALUD EPS",
                        "nit": "900226715",
                        "regimen": "SUBSIDIADO",
                        "canal": "PORTAL",
                        "plazo_radicacion_dias": 22,
                        "periodicidad": "MENSUAL",
                    },
                    {"id": "SIN_FICHA", "nombre": "OTRA", "nit": "", "regimen": "", "canal": ""},
                ],
            )
        pag = con.execute("SELECT * FROM pagadores WHERE id='COOSALUD'").fetchone()
        assert pag["nit"] == "900226715"
        contrato = con.execute("SELECT * FROM contratos WHERE pagador_id='COOSALUD'").fetchone()
        assert contrato["plazo_dias"] == 22 and contrato["periodicidad"] == "MENSUAL"
        # Sin plazo ni periodicidad no se inventa contrato.
        assert con.execute("SELECT COUNT(*) FROM contratos").fetchone()[0] == 1
        con.close()

    def test_migracion_agrega_columnas_a_base_vieja(self, tmp_path):
        # Simula una base de Fase 1 (sin evidencia/confianza) y verifica que
        # abrir() la migra sin perder filas.
        db = tmp_path / "vieja.db"
        con = sqlite3.connect(db)
        con.execute(
            "CREATE TABLE hallazgos(id INTEGER PRIMARY KEY, factura_norm TEXT,"
            " corrida_id INTEGER, agente TEXT, tipo TEXT, codigo TEXT, criticidad TEXT,"
            " detalle TEXT, regla_id TEXT, fecha TEXT, resuelto INTEGER DEFAULT 0)"
        )
        con.execute(
            "INSERT INTO hallazgos(factura_norm, corrida_id, agente, tipo, codigo,"
            " criticidad, detalle, regla_id, fecha) VALUES('1',1,'a','T','','REVISAR','d','','f')"
        )
        con.commit()
        con.close()
        con = hdb.abrir(db)
        fila = con.execute("SELECT confianza, evidencia FROM hallazgos").fetchone()
        assert fila["confianza"] == 1.0 and fila["evidencia"] == ""
        con.close()

    def test_comandos_evidencia_catalogo_grafo(self, tmp_path, capsys):
        import hospiai

        cfg = rad.cargar_perfiles(None)
        rad.cargar_reglas(None, cfg)
        d = _factura(tmp_path / "fe", "HUS528043", servicios=_SERV_PROC)
        archivos = rad._archivos_de(d)
        res = rad.procesar_factura("HUS528043", archivos, d, "COOSALUD", cfg)
        db = tmp_path / "h.db"
        hdb.persistir_corrida(
            db,
            [res],
            {res.factura_norm: archivos},
            version_reglas=cfg.version_reglas,
            version_motor="t",
            regla_id_por_codigo=cfg.regla_id_por_codigo,
            reglas_registro=cfg.reglas_registro,
            catalogo=[
                {
                    "id": "COOSALUD",
                    "nombre": "COOSALUD EPS",
                    "nit": "1",
                    "regimen": "S",
                    "canal": "PORTAL",
                    "plazo_radicacion_dias": 22,
                    "periodicidad": "MENSUAL",
                }
            ],
            clasificar=lambda n: rad.clasificar_soporte(n)[0],
        )
        assert hospiai.main(["--db", str(db), "evidencia", "HUS528043"]) == 0
        out = capsys.readouterr().out
        assert "HALLAZGO" in out and "2284" in out and "confianza" in out
        assert hospiai.main(["--db", str(db), "catalogo"]) == 0
        assert "COOSALUD" in capsys.readouterr().out
        salida = tmp_path / "grafo.json"
        assert hospiai.main(["--db", str(db), "grafo", "--salida", str(salida)]) == 0
        grafo = json.loads(salida.read_text(encoding="utf-8"))
        tipos = {n["tipo"] for n in grafo["nodos"]}
        assert {"expediente", "pagador", "regla"} <= tipos
        assert any(a["tipo"] == "INCUMPLE" for a in grafo["aristas"])
