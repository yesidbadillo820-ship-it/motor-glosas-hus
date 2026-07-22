"""Tests del Knowledge Layer — Motor Semántico (tools/hospiai_semantica.py).

Cubre: la carga de ontologías del repo, las cadenas semánticas (documento,
diagnóstico, implicaciones por tipo de atención), la coherencia con el motor
de reglas (equivalencias), la importación de CUPS oficiales desde el activo
del Motor de Glosas, el cargador CIE-10 y el agente AG011 sobre el SDK.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import hospiai_agentes as hag  # noqa: E402
import hospiai_sdk as sdk  # noqa: E402
import hospiai_semantica as sem  # noqa: E402
import radicar_facturacion as rad  # noqa: E402


class TestMotorSemantico:
    def test_carga_ontologias_del_repo(self):
        motor = sem.MotorSemantico()
        r = motor.resumen()
        assert r["documental"] >= 25
        assert r["clinica"] >= 5
        assert r["normativa"] >= 4

    def test_cadena_documental_dqx(self):
        motor = sem.MotorSemantico()
        cadena = "\n".join(motor.explicar("DQX"))
        assert "Descripción quirúrgica" in cadena
        assert "CLINICO" in cadena
        assert "RAN" in cadena  # acompañado del registro anestésico
        assert "firma_profesional" in cadena  # atributos exigidos
        assert "1995" in cadena  # fuente de los atributos

    def test_cadena_clinica_k35_implica_soportes(self):
        # K35 (apendicitis) → QUIRURGICO → se esperan DQX RAN EPI HEV.
        motor = sem.MotorSemantico()
        cadena = "\n".join(motor.explicar("K35"))
        assert "Apendicitis" in cadena
        assert "QUIRURGICO" in cadena
        for cod in ("DQX", "RAN", "EPI"):
            assert cod in cadena

    def test_equivalencias_coherentes_con_el_motor(self):
        # La ontología documental dice lo MISMO que el motor de reglas: EPI y
        # HAU los satisface la HEV. Un solo conocimiento, dos vistas.
        motor = sem.MotorSemantico()
        _, epi = motor.concepto("EPI")
        assert epi["satisfecho_por"] == [
            c for c in rad.EQUIVALENCIAS_SOPORTE_DEFAULT["EPI"] if c != "EPI"
        ]

    def test_codigo_desconocido_no_inventa(self):
        motor = sem.MotorSemantico()
        assert motor.concepto("ZZZ99") is None
        assert "no está en las ontologías" in motor.explicar("ZZZ99")[0]

    def test_soportes_para_tipo_atencion(self):
        motor = sem.MotorSemantico()
        assert motor.soportes_para("quirurgico") == ["DQX", "RAN", "EPI", "HEV"]
        assert motor.soportes_para("AMBULATORIO") == []
        assert motor.soportes_para("inexistente") == []


class TestCargadores:
    def test_importar_cups_desde_motor_de_glosas(self, tmp_path):
        # Los CUPS NO se inventan: se extraen (por AST, sin ejecutar) de la
        # tabla oficial Res. 2641/2025 que ya trae el Motor de Glosas.
        sem.importar_cups(destino=tmp_path)
        data = json.loads((tmp_path / "cups.json").read_text(encoding="utf-8"))
        assert len(data["conceptos"]) >= 100
        assert data["version"] == "2641-2025"
        cod, concepto = next(iter(data["conceptos"].items()))
        assert cod.isdigit() and concepto["nombre"]

    def test_cargar_cie10_desde_csv_oficial(self, tmp_path):
        f = tmp_path / "cie10.csv"
        f.write_text("CODIGO;NOMBRE\nK35;Apendicitis aguda\nJ18;Neumonía\n", encoding="utf-8")
        sem.cargar_cie10(f, destino=tmp_path)
        data = json.loads((tmp_path / "cie10.json").read_text(encoding="utf-8"))
        assert data["conceptos"]["K35"]["nombre"] == "Apendicitis aguda"
        assert len(data["conceptos"]) == 2

    def test_ontologia_cargada_entra_al_motor(self, tmp_path):
        # Una tabla cargada en una carpeta propia queda consultable de una.
        f = tmp_path / "cie10.csv"
        f.write_text("A00;Cólera\n", encoding="utf-8")
        sem.cargar_cie10(f, destino=tmp_path)
        motor = sem.MotorSemantico(tmp_path)
        assert motor.concepto("A00")[1]["nombre"] == "Cólera"


class TestAgenteSemantico:
    def test_ag011_explica_por_mision(self, tmp_path):
        db = tmp_path / "h.db"
        m = sdk.Mision(
            codigo="MISION-000021",
            tipo="EXPLICAR_CONCEPTO",
            expediente="",
            datos={"codigo": "DQX"},
        )
        res = hag.AgenteSemantico().ejecutar(m, {"db_path": db})
        assert res.resultado == "OK" and res.salida["hallado"] is True
        assert res.salida["ontologia"] == "documental"
        assert any("Descripción quirúrgica" in x for x in res.salida["cadena"])

    def test_ag011_codigo_desconocido_baja_confianza(self):
        m = sdk.Mision(codigo="MISION-000022", tipo="EXPLICAR_CONCEPTO", datos={"codigo": "XX9"})
        res = hag.AgenteSemantico().ejecutar(m)
        assert res.salida["hallado"] is False
        assert res.confianza == 0.2

    def test_ag011_en_el_registro(self):
        reg = hag.registro_con_implementaciones()
        assert [a["id"] for a in reg.por_capacidad("EXPLICAR_CONCEPTO")] == ["AG011"]
        assert reg.instanciar("AG011").nombre == "MotorSemantico"
