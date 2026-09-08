"""Tests del motor de cruce contra el DGH (tools/_cruce_dgh.py).

El módulo traduce el servicio que nombra la entidad (FAMISANAR, el Dispensario,
…) al código que Dinámica Gerencial reconoce, buscándolo dentro de los
servicios facturados de esa misma factura. Cubre: normalización de códigos y
nombres, lectura del export del DGH, el puntaje del cruce y sus niveles de
confianza, y el reporte de trabajo del auditor.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Los scripts viven en tools/ (sin __init__.py): los importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import _cruce_dgh as cd  # noqa: E402

openpyxl = pytest.importorskip("openpyxl")


_HEADERS_DGH = [
    "SERVICIOS DGH",
    "DESCRIPCION INSTITUCIONAL",
    "SLNSERPRO_CUPS",
    "DESCRIPCION CUPS",
    "CODIGO_MEDICAMENTO",
    "NOMBRE_MEDICAMENTO",
    "NOM_CENTRO_COSTO",
    "FACTURA",
    "CAT_SERVICIOS",
    "Vr_SERVICIO",
    "SALDO_FACT",
]


def _crear_dgh(ruta: Path, filas: list[list], headers: list[str] | None = None) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "DGDATATABLE"
    ws.append(headers or _HEADERS_DGH)
    for f in filas:
        ws.append(f)
    wb.save(str(ruta))
    return ruta


def _linea(codigo, descripcion, cant, valor, centro="URGENCIAS", cups="", cod_med=""):
    return cd.LineaDgh(
        codigo=codigo,
        descripcion=descripcion,
        desc_cups="",
        nombre_med="",
        cups=cups,
        cod_med=cod_med,
        centro=centro,
        cant=cant,
        valor=valor,
    )


# ─── Normalización ───────────────────────────────────────────────────────────


class TestVariantesCodigo:
    def test_letra_que_antepone_la_entidad(self):
        assert cd.variantes_codigo("P32606-02") & cd.variantes_codigo("32606-2")
        assert cd.variantes_codigo("U211363-03") & cd.variantes_codigo("211363-3")

    def test_h_que_agrega_el_dgh_al_cups(self):
        assert cd.variantes_codigo("903437H") & cd.variantes_codigo("903437")

    def test_codigos_distintos_no_se_cruzan(self):
        assert not (cd.variantes_codigo("FMQ0113") & cd.variantes_codigo("FMQ0115"))

    def test_vacio(self):
        assert cd.variantes_codigo("") == set()
        assert cd.variantes_codigo(None) == set()


class TestParecidoDescripcion:
    def test_numero_y_unidad_pegados(self):
        r = cd.parecido_desc(
            cd.norm_desc("LINEA INFUSION E INYECCION - JERINGA 1 ML CON AGUJA 27GA"),
            cd.norm_desc("JERINGA DESECHABLE 1ML"),
        )
        assert r >= 0.55

    def test_sin_palabras_en_comun_no_se_parecen(self):
        r = cd.parecido_desc(
            cd.norm_desc("VITAMINA D3 CAP X 1.000 U.I"), cd.norm_desc("JERINGA 1ML 25G")
        )
        assert r <= 0.30

    def test_formas_alternativas_del_nombre(self):
        formas = cd.formas_descripcion("LINEA CIRUGIA GENERAL - CATETER PREMICATH 28G")
        assert "CATETER PREMICATH 28G" in formas

    def test_factura_corta_a_larga(self):
        assert cd.factura_larga("HUS532670") == "HUS0000532670"
        assert cd.factura_larga("HUS0000532670") == "HUS0000532670"


# ─── Lectura del export del DGH ──────────────────────────────────────────────


class TestLecturaExport:
    def test_lee_las_lineas_por_factura(self, tmp_path):
        ruta = _crear_dgh(
            tmp_path / "DGH.xlsx",
            [
                [
                    "FMQ0113",
                    "CATETER INTRAVENOSO 20",
                    "",
                    "",
                    "",
                    "",
                    "URGENCIAS",
                    "HUS0000000001",
                    2,
                    11600,
                    0,
                ],
                ["FMQ0177", "JERINGA 5ML", "", "", "", "", "SALA", "HUS0000000002", 1, 700, 0],
            ],
        )
        serv = cd.leer_servicios_dgh(ruta)
        assert set(serv) == {"HUS0000000001", "HUS0000000002"}
        linea = serv["HUS0000000001"][0]
        assert linea.codigo == "FMQ0113"
        assert linea.cantidad == 2
        assert linea.valor == 11600
        assert linea.unitario == 5800
        assert linea.centro_costo == "URGENCIAS"

    def test_encabezado_del_codigo_con_error_de_escritura(self, tmp_path):
        """Algunos exports traen "SERVICOS DGH", sin la I."""
        headers = list(_HEADERS_DGH)
        headers[0] = "SERVICOS DGH"
        ruta = _crear_dgh(
            tmp_path / "DGH.xlsx",
            [
                [
                    "FMQ0113",
                    "CATETER INTRAVENOSO 20",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "HUS0000000001",
                    1,
                    5800,
                    0,
                ]
            ],
            headers,
        )
        assert cd.leer_servicios_dgh(ruta)["HUS0000000001"][0].codigo == "FMQ0113"

    def test_sin_columna_de_servicio_usa_el_cups(self, tmp_path):
        headers = [h for h in _HEADERS_DGH if h != "SERVICIOS DGH"]
        ruta = _crear_dgh(
            tmp_path / "DGH.xlsx",
            [["CATETER INTRAVENOSO 20", "903437", "", "", "", "", "HUS0000000001", 1, 5800, 0]],
            headers,
        )
        avisos = []
        assert (
            cd.leer_servicios_dgh(ruta, avisar=avisos.append)["HUS0000000001"][0].codigo == "903437"
        )
        assert avisos and "SERVICIOS DGH" in avisos[0]

    def test_export_que_no_lo_es(self, tmp_path):
        ruta = _crear_dgh(tmp_path / "otro.xlsx", [["x"]], ["CUALQUIER COSA"])
        with pytest.raises(ValueError, match="export de servicios del DGH"):
            cd.leer_servicios_dgh(ruta)

    def test_export_sin_ninguna_columna_de_codigo(self, tmp_path):
        ruta = _crear_dgh(
            tmp_path / "sincod.xlsx",
            [["CATETER", "HUS0000000001", 1, 5800]],
            ["DESCRIPCION INSTITUCIONAL", "FACTURA", "CAT_SERVICIOS", "Vr_SERVICIO"],
        )
        with pytest.raises(ValueError, match="ninguna columna de código"):
            cd.leer_servicios_dgh(ruta)


# ─── El cruce ────────────────────────────────────────────────────────────────


class TestResolverServicio:
    def test_codigo_y_valor_dan_confianza_alta(self):
        lineas = [_linea("32606-2", "SOLUCION LACTATO DE RINGER BOLSA X 500ML", 3, 12600)]
        cruce = cd.resolver_servicio(
            lineas,
            codigo="P32606-02",
            descripcion="LACTATO DE RINGER (BXT) SOLUCION INYECTABLE BOLSA POR 500ML",
            valor=12600,
            valor_unitario=4200,
        )
        assert cruce.confianza == "ALTA"
        assert cruce.linea.codigo == "32606-2"

    def test_solo_el_nombre_tambien_ubica_el_servicio(self):
        """El Dispensario manda el nombre del servicio, sin código."""
        lineas = [
            _linea("895001", "MONITOREO ELECTROCARDIOGRAFICO CONTINUO (HOLTER)", 1, 740516),
            _linea("FMQ0113", "CATETER INTRAVENOSO 20", 1, 5800),
        ]
        cruce = cd.resolver_servicio(
            lineas, descripcion="MONITOREO ELECTROCARDIOGRAFICO CONTINUO (HOLTER)", valor=16600
        )
        assert cruce.linea.codigo == "895001"
        assert cruce.confianza in ("ALTA", "MEDIA")

    def test_valor_unico_identifica_aunque_el_nombre_sea_otro(self):
        lineas = [
            _linea("FMQ9001", "SET BABYFLOW NEONATAL", 1, 270400, "UCI PEDIATRICA"),
            _linea("FMQ0113", "CATETER INTRAVENOSO 20", 1, 5800),
        ]
        cruce = cd.resolver_servicio(
            lineas,
            codigo="91018078",
            descripcion="LINEA RESPIRATORIA - KIT BABYFLOW MASCARA NASAL",
            valor=270400,
            valor_unitario=270400,
        )
        assert cruce.linea.codigo == "FMQ9001"
        assert cruce.linea.centro_costo == "UCI PEDIATRICA"
        assert "valor único en la factura" in cruce.motivos

    def test_valor_repetido_lo_desempata_el_nombre(self):
        lineas = [
            _linea("VIT-1", "VITAMINA D3 CAP X 1.000 U.I", 1, 1300),
            _linea("FMQ3616-1", "JERINGA 1ML + TAPON PARA DOSIS UNITARIA", 1, 1300),
        ]
        cruce = cd.resolver_servicio(
            lineas,
            codigo="91022534",
            descripcion="LINEA INFUSION E INYECCION - JERINGA 1ML 25G x 16 mm",
            valor=1300,
            valor_unitario=1300,
        )
        assert cruce.linea.codigo == "FMQ3616-1"

    def test_sin_datos_del_servicio_no_se_inventa(self):
        lineas = [_linea("FMQ0113", "CATETER INTRAVENOSO 20", 1, 5800)]
        cruce = cd.resolver_servicio(lineas, valor=4638000)
        assert cruce.linea is None
        assert cruce.confianza == "SIN CRUCE"
        assert "completar a mano" in cruce.aviso

    def test_factura_sin_servicios_en_el_export(self):
        cruce = cd.resolver_servicio([], codigo="FMQ0113", valor=5800)
        assert cruce.linea is None
        assert "no está en el export del DGH" in cruce.aviso

    def test_nombre_en_conflicto_cruza_pero_se_marca(self):
        # La entidad busca el código en el catálogo CUPS y no en el del
        # hospital: 150101 es en el DGH una fórmula enteral, no una biopsia.
        # El valor confirma que es la misma línea.
        lineas = [_linea("150101", "ENSURE CLINICAL BOTELLA X 220 ml", 1, 16200)]
        cruce = cd.resolver_servicio(
            lineas,
            codigo="150101",
            descripcion="BIOPSIA DE MUSCULO O TENDON EXTRAOCULAR",
            valor=16200,
            valor_unitario=16200,
        )
        assert cruce.linea is not None
        assert cruce.confianza != "ALTA"
        assert "no coincide" in cruce.aviso

    def test_codigo_igual_y_valor_distinto_no_es_el_mismo_servicio(self):
        lineas = [_linea("150101", "ENSURE CLINICAL BOTELLA X 220 ml", 1, 16200)]
        cruce = cd.resolver_servicio(
            lineas, codigo="150101", descripcion="BIOPSIA DE MUSCULO O TENDON", valor=99999
        )
        assert cruce.linea is None

    def test_objeciones_repetidas_se_reparten_entre_renglones(self):
        lineas = [
            _linea("FMQ0177", "JERINGA DESECHABLES 5ML", 2, 1400),
            _linea("FMQ0177", "JERINGA DESECHABLES 5ML", 2, 1400),
        ]
        kw = dict(codigo="FMQ0177", descripcion="JERINGA DESECHABLES 5ML", valor=1400)
        primero = cd.resolver_servicio(lineas, **kw)
        segundo = cd.resolver_servicio(lineas, **kw)
        assert primero.linea is not segundo.linea


# ─── Reporte de trabajo ──────────────────────────────────────────────────────


class TestReporteCruce:
    def _trazas(self):
        lineas = [_linea("FMQ0113", "CATETER INTRAVENOSO 20", 1, 5800, "URGENCIAS ADULTOS")]
        cruzada = cd.resolver_servicio(
            lineas, codigo="FMQ0113", descripcion="CATETER INTRAVENOSO 20", valor=5800
        )
        vacia = cd.resolver_servicio(lineas, valor=279900)
        return [
            cd.traza(
                factura="HUS0000549272",
                codigo_objecion="CO0601",
                valor=5800,
                cod_entidad="FMQ0113",
                desc_entidad="CATETER INTRAVENOSO 20",
                unitario_entidad=5800,
                observacion="texto de la entidad",
                cruce=cruzada,
            ),
            cd.traza(
                factura="HUS0000549272",
                codigo_objecion="CL0801",
                valor=279900,
                cod_entidad="",
                desc_entidad="",
                unitario_entidad=0,
                observacion="AUD EXTRA - …",
                cruce=vacia,
            ),
        ]

    def test_escribe_las_tres_hojas(self, tmp_path):
        salida = tmp_path / "CRUCE.xlsx"
        cd.escribir_reporte_cruce(self._trazas(), salida, entidad="FAMISANAR")
        wb = openpyxl.load_workbook(str(salida))
        assert wb.sheetnames == ["CRUCE", "REVISAR", "RESUMEN"]
        assert wb["CRUCE"].max_row == 3
        assert wb["REVISAR"].max_row == 2  # sólo la que hay que revisar
        assert "FAMISANAR" in wb["CRUCE"]["D1"].value
        resumen = list(wb["RESUMEN"].iter_rows(min_row=2, values_only=True))
        assert resumen[0][0] == "HUS0000549272"
        assert resumen[0][1] == 2
        assert resumen[0][2] == 285700
        assert "Revisar" in resumen[0][7]
        assert resumen[-1][0] == "TOTAL"


# ─── Las reglas fijas del archivo de OBJECIONES ──────────────────────────────


class TestVerificarReglas:
    def _servicios(self):
        return {"HUS0000549272": [_linea("FMQ0113", "CATETER INTRAVENOSO 20", 1, 5800)]}

    def _renglon(self, **kw):
        base = {
            "factura": "HUS0000549272",
            "slnserpro": "FMQ0113",
            "ctncencos": None,
            "crotipobj": 0,
            "codigo_glosa": "CO0601",
        }
        base.update(kw)
        return base

    def test_archivo_que_cumple(self):
        avisos: list[str] = []
        fallas = cd.verificar_reglas([self._renglon()], self._servicios(), avisar=avisos.append)
        assert fallas == []
        assert avisos and "Reglas verificadas" in avisos[0]

    def test_ctncencos_con_dato(self):
        fallas = cd.verificar_reglas([self._renglon(ctncencos="URGENCIAS")], self._servicios())
        assert any("CTNCENCOS" in f for f in fallas)

    def test_slnserpro_que_no_existe_en_esa_factura(self):
        fallas = cd.verificar_reglas([self._renglon(slnserpro="FMQ9999")], self._servicios())
        assert any("no existen en el export" in f for f in fallas)

    def test_slnserpro_vacio_no_es_falla(self):
        """Los renglones sin cruce van igual en el archivo, con la celda vacía."""
        assert cd.verificar_reglas([self._renglon(slnserpro=None)], self._servicios()) == []

    def test_crotipobj_mal_clasificada(self):
        renglones = [
            self._renglon(codigo_glosa="CO0601", crotipobj=0),
            self._renglon(codigo_glosa="CL0701", crotipobj=0),  # debía ser 2 (mixta)
        ]
        fallas = cd.verificar_reglas(renglones, self._servicios())
        assert any("CROTIPOBJ" in f and "debía ser 2" in f for f in fallas)

    def test_crotipobj_medica_cuando_todas_son_clinicas(self):
        renglones = [self._renglon(codigo_glosa="CL0801", crotipobj=1, slnserpro=None)]
        assert cd.verificar_reglas(renglones, self._servicios()) == []

    def test_crotipobj_distinto_dentro_de_la_misma_factura(self):
        renglones = [
            self._renglon(codigo_glosa="CO0601", crotipobj=0),
            self._renglon(codigo_glosa="TA0801", crotipobj=2),
        ]
        assert any("CROTIPOBJ" in f for f in cd.verificar_reglas(renglones, self._servicios()))

    def test_sin_export_del_dgh_no_revisa_los_codigos(self):
        assert cd.verificar_reglas([self._renglon(slnserpro="LO_QUE_SEA")], None) == []
