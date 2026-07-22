"""Tests de HOSPIAI Fase 1.7 — Architecture Governance.

Cubre: el registro único de artefactos (descubrimiento + deriva de huellas),
los contratos de compatibilidad (declarativos y EN VIVO — un agente roto se
detecta solo), el banco de casos de referencia (regresión funcional del motor
real), los Decision Records y la API interna (capa de servicios).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import hospiai_api as api  # noqa: E402
import hospiai_db as hdb  # noqa: E402
import hospiai_gobernanza as gob  # noqa: E402
import hospiai_sdk as sdk  # noqa: E402
import radicar_facturacion as rad  # noqa: E402


class TestRegistroArtefactos:
    def test_descubre_todo_como_artefacto(self):
        arts = gob.descubrir_artefactos()
        tipos = {a["tipo"] for a in arts}
        assert {"SDK", "MOTOR", "REGLAS", "CATALOGO", "ONTOLOGIA", "AGENTE"} <= tipos
        assert len(arts) >= 18  # núcleo + reglas + catálogo + 5+ ontologías + 11 agentes
        assert all(a.get("version") for a in arts)
        assert all(a.get("huella") for a in arts if a["origen"].startswith(("tools/", "data/")))

    def test_deriva_detecta_cambio_sin_subir_version(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gob, "RUTA_HUELLAS", tmp_path / "huellas.json")
        arts = gob.descubrir_artefactos()
        assert gob.verificar_deriva(arts, actualizar=True) == []  # sella la base
        # Mismo artefacto, misma versión, contenido distinto → deriva.
        arts2 = [dict(a) for a in arts]
        arts2[0]["huella"] = "cambiada000000"
        avisos = gob.verificar_deriva(arts2)
        assert len(avisos) == 1 and "subir la versión" in avisos[0]

    def test_version_nueva_no_es_deriva(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gob, "RUTA_HUELLAS", tmp_path / "huellas.json")
        arts = gob.descubrir_artefactos()
        gob.verificar_deriva(arts, actualizar=True)
        arts2 = [dict(a) for a in arts]
        arts2[0]["huella"] = "cambiada000000"
        arts2[0]["version"] = "999.0"  # subió la versión: cambio legítimo
        assert gob.verificar_deriva(arts2) == []


class TestContratosCompatibilidad:
    def test_agentes_sdk_actuales_compatibles(self):
        informes = gob.verificar_compatibilidad()
        con_impl = {i["id"]: i for i in informes if i["id"] in ("AG002", "AG003", "AG011")}
        assert len(con_impl) == 3
        assert all(i["compatible"] for i in con_impl.values())

    def test_agente_roto_se_detecta_solo(self, monkeypatch):
        # Simula un agente que NO cumple el contrato (sin _trabajar): el
        # verificador debe marcarlo incompatible sin que nadie lo declare.
        import hospiai_agentes as hag

        class AgenteRoto(sdk.Agente):
            id = "AG997"
            nombre = "Roto"
            capacidades = ["ROMPER"]

        original = hag.registro_con_implementaciones

        def con_roto(ruta=None):
            reg = original(ruta)
            reg.registrar_clase(AgenteRoto)
            return reg

        monkeypatch.setattr(hag, "registro_con_implementaciones", con_roto)
        informes = {i["id"]: i for i in gob.verificar_compatibilidad()}
        assert informes["AG997"]["compatible"] is False
        assert any("_trabajar" in m for m in informes["AG997"]["motivos"])

    def test_sdk_mayor_distinto_es_incompatible(self, monkeypatch):
        monkeypatch.setattr(sdk, "VERSION_SDK", "2.0")
        informes = {i["id"]: i for i in gob.verificar_compatibilidad()}
        assert informes["AG002"]["compatible"] is False
        assert any("SDK 1.x" in m for m in informes["AG002"]["motivos"])


class TestBancoGolden:
    def test_todos_los_casos_en_verde(self):
        resultados = gob.correr_golden()
        fallas = [r for r in resultados if not r["ok"]]
        assert len(resultados) >= 10
        assert fallas == [], f"Regresión funcional: {fallas}"

    def test_una_regresion_se_detecta(self, tmp_path):
        # Si el esperado cambia (simulando que una regla alteró el motor), el
        # banco lo reporta como falla — la red de regresión funciona.
        casos = json.loads(gob.RUTA_GOLDEN.read_text(encoding="utf-8-sig"))
        casos["casos"][0]["esperado"]["dictamen"] = "SIN_FEV"
        f = tmp_path / "casos.json"
        f.write_text(json.dumps(casos), encoding="utf-8")
        resultados = gob.correr_golden(f)
        assert any(not r["ok"] for r in resultados)


class TestDecisionRecords:
    def test_cada_corrida_deja_decision_auditable(self, tmp_path):
        cfg = rad.cargar_perfiles(None)
        rad.cargar_reglas(None, cfg)
        d = tmp_path / "fe" / "HUS528043"
        d.mkdir(parents=True)
        (d / "Rips_HUS528043.json").write_text(
            json.dumps(
                {
                    "numFactura": "HUS528043",
                    "usuarios": [{"servicios": {"procedimientos": [{"vrServicio": 1}]}}],
                }
            ),
            encoding="utf-8",
        )
        (d / "FEV_900006037_HUS528043.xml").write_text(
            '<?xml version="1.0"?><Invoice xmlns:cbc="x"><cbc:ID>HUS528043</cbc:ID></Invoice>',
            encoding="utf-8",
        )
        (d / "CUV_900006037_HUS528043.json").write_text("{}", encoding="utf-8")
        archivos = rad._archivos_de(d)
        res = rad.procesar_factura("HUS528043", archivos, d, "COOSALUD", cfg)
        db = tmp_path / "h.db"
        hdb.persistir_corrida(
            db,
            [res],
            {res.factura_norm: archivos},
            version_reglas=cfg.version_reglas,
            version_motor=rad.VERSION_MOTOR,
            regla_id_por_codigo=cfg.regla_id_por_codigo,
            reglas_registro=cfg.reglas_registro,
            clasificar=lambda n: rad.clasificar_soporte(n)[0],
        )
        s = api.Servicios(db)
        decs = s.decisiones("HUS528043")
        assert len(decs) == 1
        dec = decs[0]
        assert dec["codigo"].startswith("DEC-")
        assert dec["dictamen"] == "REVISAR_TIPIFICACION"
        assert "HEV" in dec["motivo"]
        assert dec["regla_id"] == cfg.regla_id_por_codigo["HEV"]
        assert dec["version_motor"] == rad.VERSION_MOTOR
        assert dec["version_reglas"] == "1.0"


class TestAPIServicios:
    def _db_con_expediente(self, tmp_path):
        cfg = rad.cargar_perfiles(None)
        rad.cargar_reglas(None, cfg)
        d = tmp_path / "fe" / "HUS900050"
        d.mkdir(parents=True)
        (d / "Rips_HUS900050.json").write_text(
            json.dumps(
                {
                    "numFactura": "HUS900050",
                    "usuarios": [{"servicios": {"consultas": [{"vrServicio": 1}]}}],
                }
            ),
            encoding="utf-8",
        )
        (d / "FEV_900006037_HUS900050.xml").write_text(
            '<?xml version="1.0"?><Invoice xmlns:cbc="x"><cbc:ID>HUS900050</cbc:ID></Invoice>',
            encoding="utf-8",
        )
        (d / "CUV_900006037_HUS900050.json").write_text("{}", encoding="utf-8")
        archivos = rad._archivos_de(d)
        res = rad.procesar_factura("HUS900050", archivos, d, "COOSALUD", cfg)
        db = tmp_path / "h.db"
        hdb.persistir_corrida(
            db,
            [res],
            {res.factura_norm: archivos},
            version_reglas="1.0",
            version_motor="t",
            clasificar=lambda n: rad.clasificar_soporte(n)[0],
        )
        return db

    def test_expediente_agentes_capacidades_ontologia(self, tmp_path):
        db = self._db_con_expediente(tmp_path)
        s = api.Servicios(db)
        exp = s.expediente("HUS900050")
        assert exp["dictamen"] == "LISTA" and len(exp["documentos"]) == 3
        assert s.expediente("HUS999999") is None
        ags = s.agentes()
        assert any(a["id"] == "AG011" for a in ags)
        caps = s.capacidades()
        assert caps["EXPLICAR_CONCEPTO"] == ["AG011"]
        ont = s.ontologia("DQX")
        assert ont["hallado"] and ont["ontologia"] == "documental"
        assert s.salud()["misiones"] == {}
