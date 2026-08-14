"""Tests del bot que saca un Excel por factura desde el reporte del ADRES.

Lo que más importa acá es que **no mienta con la plata**. El reporte del ADRES
abre una fila por cada causal del mismo ítem, así que sumar en bruto infla la
glosa al doble o al triple. El bot junta esas filas, y cuando aun así no cuadra
con la cifra oficial del ADRES lo dice en vez de taparlo: en el paquete 31078
eso pasa en 27 de las 81 facturas, que son las de más plata.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

openpyxl = pytest.importorskip("openpyxl")

import glosas_adres_por_factura as gf  # noqa: E402

CABECERA = [
    "Código Habilitación",
    "Número Radicación",
    "Número Factura",
    "Número Paquete",
    "Cantidad Reclamado",
    "Valor Reclamado",
    "Cantidad Aprobada",
    "Valor Aprobado",
    "Valor Glosado",
    "Tip- Num Doc Victima",
    "Consecutivo Item",
    "Tipo Elemento",
    "Cod Elemento",
    "Descripción Elemento",
    "Descripción Glosa",
    "Descripción Anotación",
]

# (factura, consec, cod, descripción, reclamado, aprobado, glosado, causal)
FILAS = [
    # HUS100001 — un ítem con DOS causales: sale dos veces en el reporte pero
    # es un solo ítem de $50.000. Sumar en bruto daría $100.000.
    (
        "HUS100001",
        "1",
        "39145",
        "Consulta de urgencias",
        50000,
        0,
        50000,
        "3209- Ayuda sin justificar",
    ),
    ("HUS100001", "1", "39145", "Consulta de urgencias", 50000, 0, 50000, "3106- Soporte ausente"),
    # Un ítem con una sola causal.
    ("HUS100001", "2", "21101", "Mano, dedos, puño", 30000, 0, 30000, "3106- Soporte ausente"),
    # Ya aprobado: glosado 0, no debe salir en el archivo.
    ("HUS100001", "3", "19490", "DIPIRONA", 4700, 4700, 0, ""),
    # HUS100002 — el MISMO medicamento cargado dos veces, con la MISMA causal.
    # Son dos ítems de verdad: no se pueden juntar.
    ("HUS100002", "1", "19490", "DIPIRONA 1 G", 4700, 0, 4700, "3107- Soporte de medicamentos"),
    ("HUS100002", "1", "19490", "DIPIRONA 1 G", 4700, 0, 4700, "3107- Soporte de medicamentos"),
]


@pytest.fixture()
def reporte(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    for _ in range(6):  # el reporte real trae el título arriba
        ws.append([])
    ws.append(CABECERA)
    for factura, consec, cod, desc, recl, apro, glos, causal in FILAS:
        ws.append(
            [
                "680010079201",
                "14408660",
                factura,
                "31078",
                1,
                recl,
                1 if apro else 0,
                apro,
                glos,
                "CC-91246389",
                consec,
                "Procedimientos",
                cod,
                desc,
                causal,
                "OBSERVACION DEL ADRES" if causal else "",
            ]
        )
    ruta = tmp_path / "ReporteGlosasReclamPAQUETE 31078.xlsx"
    wb.save(ruta)
    return ruta


def _archivo_facturas(tmp_path: Path, valores: dict[str, float]) -> Path:
    """El archivo oficial del paquete, con la pinta de tabla dinámica real."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "FACTURAS"
    ws.append(
        ["", "No.", "Etiquetas de fila", "Suma de Valor Reclamado", "", "Suma de Valor Glosado"]
    )
    for n, (factura, glosado) in enumerate(valores.items(), start=1):
        ws.append(["", n, factura, 0, 0, glosado])
    ruta = tmp_path / "FACTURAS PAQUETE 31078_2 FACTURAS.xlsx"
    wb.save(ruta)
    return ruta


class TestAgruparItems:
    """La regla que decide cuánta plata se reporta."""

    def test_un_item_con_dos_causales_es_un_solo_item(self, reporte, tmp_path):
        res = gf.procesar(reporte, tmp_path / "salida")
        una = next(r for r in res if r.clave.endswith("100001"))
        # 3 filas glosadas en el reporte -> 2 ítems reales
        assert una.filas_reporte == 3
        assert len(una.items) == 2
        assert una.suma == pytest.approx(80000)  # 50.000 + 30.000, no 130.000

    def test_las_dos_causales_quedan_juntas_en_el_mismo_item(self, reporte, tmp_path):
        res = gf.procesar(reporte, tmp_path / "salida")
        una = next(r for r in res if r.clave.endswith("100001"))
        doble = next(i for i in una.items if i.fila.codigo == "39145")
        assert len(doble.causales) == 2
        assert any("3209" in c for c in doble.causales)
        assert any("3106" in c for c in doble.causales)

    def test_el_mismo_item_repetido_con_la_misma_causal_son_items_de_verdad(
        self, reporte, tmp_path
    ):
        """Una factura puede traer el mismo medicamento cargado dos veces."""
        res = gf.procesar(reporte, tmp_path / "salida")
        otra = next(r for r in res if r.clave.endswith("100002"))
        assert len(otra.items) == 2
        assert otra.suma == pytest.approx(9400)

    def test_lo_ya_aprobado_no_aparece(self, reporte, tmp_path):
        """Glosado en cero es plata que el ADRES ya pagó: no hay qué responder."""
        res = gf.procesar(reporte, tmp_path / "salida")
        una = next(r for r in res if r.clave.endswith("100001"))
        assert all(i.fila.codigo != "19490" for i in una.items)


class TestVerificacionContraElAdres:
    """Sin esto el bot sería peligroso: reportaría cifras infladas como buenas."""

    def test_marca_cuadra_cuando_coincide(self, reporte, tmp_path):
        oficial = _archivo_facturas(tmp_path, {"HUS100001": 80000, "HUS100002": 9400})
        res = gf.procesar(reporte, tmp_path / "salida", facturas=oficial)
        assert all(r.cuadra is True for r in res)

    def test_avisa_cuando_no_cuadra_y_dice_de_cuanto(self, reporte, tmp_path):
        # El ADRES dice que la 100001 tiene glosado 40.000, no 80.000.
        oficial = _archivo_facturas(tmp_path, {"HUS100001": 40000, "HUS100002": 9400})
        res = gf.procesar(reporte, tmp_path / "salida", facturas=oficial)
        mala = next(r for r in res if r.clave.endswith("100001"))
        assert mala.cuadra is False
        assert mala.diferencia == pytest.approx(-40000)

    def test_sin_el_archivo_oficial_queda_sin_verificar(self, reporte, tmp_path):
        res = gf.procesar(reporte, tmp_path / "salida")
        assert all(r.cuadra is None for r in res)

    def test_el_aviso_queda_escrito_dentro_del_excel(self, reporte, tmp_path):
        """El que abra el archivo tiene que ver el problema, no solo el que corra el bot."""
        oficial = _archivo_facturas(tmp_path, {"HUS100001": 40000, "HUS100002": 9400})
        salida = tmp_path / "salida"
        gf.procesar(reporte, salida, facturas=oficial)

        wb = openpyxl.load_workbook(salida / "HUS100001.xlsx")
        texto = " ".join(
            str(c.value) for f in wb.active.iter_rows() for c in f if c.value is not None
        )
        wb.close()
        assert "NO CUADRA" in texto
        assert "portal" in texto.lower()

        wb = openpyxl.load_workbook(salida / "HUS100002.xlsx")
        texto = " ".join(
            str(c.value) for f in wb.active.iter_rows() for c in f if c.value is not None
        )
        wb.close()
        assert "VERIFICADO" in texto


class TestArchivos:
    def test_un_archivo_por_factura_con_su_numero(self, reporte, tmp_path):
        salida = tmp_path / "salida"
        gf.procesar(reporte, salida)
        assert (salida / "HUS100001.xlsx").exists()
        assert (salida / "HUS100002.xlsx").exists()

    def test_carpeta_por_factura(self, reporte, tmp_path):
        salida = tmp_path / "salida"
        gf.procesar(reporte, salida, carpeta_por_factura=True)
        assert (salida / "HUS100001" / "HUS100001.xlsx").exists()

    def test_solo_descuadradas_escribe_unicamente_las_malas(self, reporte, tmp_path):
        oficial = _archivo_facturas(tmp_path, {"HUS100001": 40000, "HUS100002": 9400})
        salida = tmp_path / "salida"
        gf.procesar(reporte, salida, facturas=oficial, solo_descuadradas=True)
        assert (salida / "HUS100001.xlsx").exists()
        assert not (salida / "HUS100002.xlsx").exists()

    def test_el_encabezado_trae_los_datos_de_la_factura(self, reporte, tmp_path):
        salida = tmp_path / "salida"
        gf.procesar(reporte, salida)
        wb = openpyxl.load_workbook(salida / "HUS100001.xlsx")
        ws = wb.active
        texto = " ".join(str(ws.cell(row=f, column=1).value or "") for f in range(1, 8))
        wb.close()
        assert "HUS100001" in texto
        assert "31078" in texto
        assert "14408660" in texto  # radicación
        assert "SIGUE GLOSADO" in texto

    def test_el_resumen_csv_lista_todas_con_su_veredicto(self, reporte, tmp_path):
        oficial = _archivo_facturas(tmp_path, {"HUS100001": 40000, "HUS100002": 9400})
        salida = tmp_path / "salida"
        gf.procesar(reporte, salida, facturas=oficial)
        with open(salida / "RESUMEN_31078.csv", encoding="utf-8-sig") as fh:
            filas = list(csv.DictReader(fh, delimiter=";"))
        por_factura = {f["FACTURA"]: f for f in filas}
        assert por_factura["HUS100001"]["CUADRA"] == "NO"
        assert por_factura["HUS100002"]["CUADRA"] == "SI"
        assert por_factura["HUS100001"]["ITEMS_GLOSADOS"] == "2"

    def test_reporte_vacio_da_error_claro(self, tmp_path):
        wb = openpyxl.Workbook()
        ws = wb.active
        for _ in range(6):
            ws.append([])
        ws.append(CABECERA)
        ruta = tmp_path / "vacio.xlsx"
        wb.save(ruta)
        with pytest.raises(ValueError, match="ninguna fila glosada"):
            gf.procesar(ruta, tmp_path / "salida")


class TestRenglonesSinCausal:
    """En el 31078 hay 1.174 renglones sin causal, en las facturas más caras."""

    def test_se_avisa_cuando_el_reporte_no_dice_la_causal(self, tmp_path):
        wb = openpyxl.Workbook()
        ws = wb.active
        for _ in range(6):
            ws.append([])
        ws.append(CABECERA)
        ws.append(
            [
                "680010079201",
                "14408660",
                "HUS100003",
                "31078",
                1,
                90000,
                0,
                0,
                90000,
                "CC-1",
                "1",
                "Procedimientos",
                "X1",
                "SERVICIO SIN CAUSAL",
                "",
                "",
            ]
        )
        ruta = tmp_path / "sin_causal.xlsx"
        wb.save(ruta)

        salida = tmp_path / "salida"
        gf.procesar(ruta, salida)
        wb2 = openpyxl.load_workbook(salida / "HUS100003.xlsx")
        texto = " ".join(
            str(c.value) for f in wb2.active.iter_rows() for c in f if c.value is not None
        )
        wb2.close()
        assert "SIN causal" in texto
        assert "no dice la causal" in texto  # en la celda de la causal
