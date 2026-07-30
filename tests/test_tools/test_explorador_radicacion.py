"""Tests del Explorador de Radicación (tools/explorador_radicacion.py).

Cubre: la frase "¿qué le falta?" por estado, la lectura del reporte del
radicador, los conteos/orden por estado y el render del HTML autocontenido.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import explorador_radicacion as exp  # noqa: E402
from _explorador_html import render_html  # noqa: E402

HEADERS = [
    "factura",
    "entidad",
    "entidad_id",
    "canal",
    "valor_total",
    "servicios",
    "soportes_presentes",
    "soportes_faltantes",
    "soportes_esperados_faltantes",
    "archivos_sin_clasificar",
    "estado",
    "detalle",
    "ruta_paquete",
    "carpeta",
]


def _csv(ruta: Path, filas: list[list]) -> None:
    with ruta.open("w", newline="", encoding="utf-8") as fh:
        csv.writer(fh).writerows(filas)


class TestFalta:
    def test_sin_rips(self):
        assert exp._falta("SIN_RIPS", {}) == "Falta el RIPS (.json)"

    def test_sin_cuv(self):
        assert "CUV" in exp._falta("SIN_CUV", {})

    def test_faltan_soportes_lista(self):
        assert "FEV" in exp._falta("FALTAN_SOPORTES", {"soportes_faltantes": "FEV"})

    def test_revisar_archivo_sin_tipificar(self):
        assert "basura.pdf" in exp._falta(
            "REVISAR_TIPIFICACION", {"archivos_sin_clasificar": "basura.pdf"}
        )

    def test_revisar_soporte_clinico(self):
        assert "EPI" in exp._falta("REVISAR_TIPIFICACION", {"soportes_esperados_faltantes": "EPI"})

    def test_lista_sin_falta(self):
        assert exp._falta("LISTA", {}) == ""

    def test_entidad_no_resuelta_muestra_pagador(self):
        det = "No se pudo resolver la entidad (pista: 'UT SALUD INTEGRAL MAISFEN')."
        assert "MAISFEN" in exp._falta("ENTIDAD_NO_RESUELTA", {"detalle": det})


class TestPagadorNoResuelto:
    def test_extrae_pista(self):
        assert exp._pagador_no_resuelto("algo (pista: 'ABC EPS'). más") == "ABC EPS"

    def test_pista_guion_es_vacia(self):
        assert exp._pagador_no_resuelto("pista: '—'") == ""

    def test_sin_pista(self):
        assert exp._pagador_no_resuelto("texto sin pista") == ""

    def test_cargar_pone_pagador_en_entidad(self, tmp_path):
        r = tmp_path / "rep.csv"
        _csv(
            r,
            [
                HEADERS,
                [
                    "HUS900",
                    "SIN_PERFIL",
                    "",
                    "",
                    "850000",
                    "procedimientos:1",
                    "FEV RIP CUV",
                    "",
                    "",
                    "",
                    "ENTIDAD_NO_RESUELTA",
                    "No se pudo resolver la entidad (pista: 'UNION TEMPORAL MAISFEN').",
                    "",
                    "Y:\\HUS900",
                ],
            ],
        )
        regs = exp.cargar_reporte(r)
        assert regs[0]["entidad"] == "UNION TEMPORAL MAISFEN"  # no "SIN_PERFIL"


class TestCargaYAgregacion:
    def _reporte(self, tmp_path: Path) -> Path:
        r = tmp_path / "rep.csv"
        _csv(
            r,
            [
                HEADERS,
                [
                    "HUS100",
                    "COOSALUD EPS",
                    "COOSALUD",
                    "PORTAL",
                    "52300",
                    "consultas:1",
                    "FEV RIP CUV",
                    "",
                    "",
                    "",
                    "LISTA",
                    "Lista.",
                    "",
                    "Y:\\HUS100",
                ],
                [
                    "HUS200",
                    "NUEVA EPS",
                    "NUEVA_EPS",
                    "PORTAL",
                    "90000",
                    "procedimientos:1",
                    "FEV",
                    "",
                    "",
                    "",
                    "SIN_RIPS",
                    "Falta RIPS.",
                    "",
                    "Y:\\HUS200",
                ],
                [
                    "HUS300",
                    "NUEVA EPS",
                    "NUEVA_EPS",
                    "PORTAL",
                    "5000",
                    "medicamentos:1",
                    "RIP CUV",
                    "FEV",
                    "",
                    "",
                    "FALTAN_SOPORTES",
                    "Faltan: FEV.",
                    "",
                    "Y:\\HUS300",
                ],
            ],
        )
        return r

    def test_cargar(self, tmp_path):
        regs = exp.cargar_reporte(self._reporte(tmp_path))
        assert len(regs) == 3
        f200 = next(r for r in regs if r["factura"] == "HUS200")
        assert f200["estado"] == "SIN_RIPS"
        assert f200["falta"] == "Falta el RIPS (.json)"
        assert f200["carpeta"] == "Y:\\HUS200"
        assert f200["valor"] == 90000.0

    def test_agregar_conteos_y_orden(self, tmp_path):
        datos = exp.agregar(exp.cargar_reporte(self._reporte(tmp_path)))
        assert datos["total"] == 3
        d = {e["estado"]: e["n"] for e in datos["estados"]}
        assert d == {"SIN_RIPS": 1, "FALTAN_SOPORTES": 1, "LISTA": 1}
        # Los problemas van antes que LISTA (prioridad de gestión).
        assert datos["estados"][-1]["estado"] == "LISTA"
        assert "NUEVA EPS" in datos["entidades"]

    def test_reporte_no_es_del_radicador(self, tmp_path):
        r = tmp_path / "bad.csv"
        _csv(r, [["columna_a", "columna_b"], ["1", "2"]])
        with pytest.raises(ValueError):
            exp.cargar_reporte(r)


class TestRender:
    def test_html_autocontenido(self, tmp_path):
        r = tmp_path / "rep.csv"
        _csv(
            r,
            [
                HEADERS,
                [
                    "HUS100",
                    "COOSALUD EPS",
                    "COOSALUD",
                    "PORTAL",
                    "52300",
                    "consultas:1",
                    "FEV RIP CUV",
                    "",
                    "",
                    "",
                    "LISTA",
                    "Lista.",
                    "",
                    "Y:\\HUS100",
                ],
            ],
        )
        datos = exp.agregar(exp.cargar_reporte(r))
        datos["titulo"] = "Prueba HUS"
        html = render_html(datos)
        assert "<!DOCTYPE html>" in html
        assert "Prueba HUS" in html
        assert "HUS100" in html
        assert "__DATA__" not in html
        assert "const DATA =" in html


class TestValorNoSeDividePorMil:
    """Novena copia del lector de pesos, con el mismo agujero que las otras.

    La condición era `s.count(".") > 1`: con dos puntos de miles funcionaba,
    con uno solo no. `"$ 950.000"` se leía como **950,00**. Es el mismo
    `950.000 → 950` del informe de cartera, del acta de conciliación y de la
    hoja maestra — cuatro sitios, una sola causa: cada herramienta escribió su
    propio lector.
    """

    @pytest.mark.parametrize(
        "crudo,esperado",
        [
            ("$ 950.000", 950000.0),
            ("50.000", 50000.0),
            ("2.500", 2500.0),
            ("3.211.891", 3211891.0),
            ("1.365,50", 1365.50),
        ],
    )
    def test_lee_el_formato_colombiano(self, crudo, esperado):
        assert exp._parse_valor(crudo) == pytest.approx(esperado)

    def test_novecientos_cincuenta_mil_no_es_novecientos_cincuenta(self):
        assert exp._parse_valor("$ 950.000") == 950000.0
        assert exp._parse_valor("$ 950.000") != 950.0
