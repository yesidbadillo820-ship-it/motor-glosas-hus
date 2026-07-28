"""Tests del ajustador de detallados (tools/ajustar_detallado_glosas.py).

El fixture reproduce la factura HUS352890 tal como la trae el sistema (el
"ANTES" del documento del auditor) y su reporte de glosas del paquete 31068,
para verificar que el bot deje solo lo que la entidad sigue glosando.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

openpyxl = pytest.importorskip("openpyxl")

import ajustar_detallado_glosas as aj  # noqa: E402

# ─── Fixtures: la factura HUS352890 y su reporte de glosas ───────────────────

# (codigo, nombre, cantidad, vr_unit) por grupo, en el orden del detallado real.
GRUPOS_HUS352890 = [
    ("CONSULTAS MEDICAS", [("39145", "CONSULTA DE URGENCIAS", 1, 85800)]),
    ("MEDICAMENTOS POS", [("19992190-3", "DICLOFENACO SODICO AMP X 75MG/3ML", 1, 900)]),
    (
        "PROCEDIMIENTOS  TERAPEUTICOS NO QUIRURGICO",
        [("37206", "INMOVILIZACION MIEMBRO SUPERIOR O|INFERIOR TOTAL O PARCIAL", 1, 82000)],
    ),
    ("DERECHOS DE SALA", [("39221", "DERECHOS DE SALA DE YESOS", 1, 100700)]),
    (
        "MATERIALES E INSUMOS",
        [
            ("FMQ0042", "VENDA DE ALGODON 6 X 5 YARDAS", 4, 4600),
            ("FMQ0046", "VENDA DE GASA 6 X 5 YARDAS", 6, 9400),
            ("FMQ0055", "VENDA ELASTICA 6 X 5 YARDAS", 4, 5400),
        ],
    ),
    ("IMAGENOLOGIA", [("21102", "BRAZO, PIERNA, RODILLA, FEMUR, HOMBRO, OMOPLATO", 1, 95300)]),
]

COL_CODIGO, COL_NOMBRE, COL_CANT, COL_UNIT, COL_PAC, COL_ENT = 3, 4, 7, 8, 9, 10


def _hoja_detallado(ws, factura: str, grupos=GRUPOS_HUS352890) -> None:
    """Arma una hoja con la pinta del detallado que baja el sistema."""
    # Encabezado institucional (lo que el bot debe borrar).
    ws.cell(row=1, column=3, value="Carrrera 33 # 28 -126  Teléfono 6910030")
    ws.cell(row=2, column=3, value="NIT 900.006.037-4")
    ws.cell(row=3, column=3, value="Bucaramanga")
    ws.cell(row=4, column=12, value="Página 1/1")
    ws.cell(row=5, column=1, value="CUFE:00a8dd40ad98f18932a3551ef3d97121391d260f783dc02cf4ac1")

    ws.cell(row=11, column=1, value="FACTURA ELECTRONICA DE")
    ws.cell(row=11, column=5, value=factura)
    ws.cell(row=11, column=10, value="20 feb 2025 04:50 PM")
    ws.cell(row=12, column=1, value="CLIENTE")
    ws.cell(row=12, column=2, value="ADMINISTRADORA DE LOS RECURSOS DEL SISTEMA")
    ws.merge_cells(start_row=12, start_column=2, end_row=12, end_column=6)

    for col, etiqueta in (
        (COL_CODIGO - 1, "CÓDIGO"), (COL_NOMBRE, "NOMBRE"), (COL_CANT, "CANT"),
        (COL_UNIT, "VR UNIT"), (COL_PAC, "VR PAC"), (COL_ENT, "VR ENT"),
    ):
        ws.cell(row=20, column=col, value=etiqueta)

    fila = 21
    for titulo, items in grupos:
        fila += 1
        ws.cell(row=fila, column=1, value=titulo)
        fila += 1  # renglón en blanco que trae el formato
        for codigo, nombre, cant, unit in items:
            fila += 1
            partes = nombre.split("|")
            ws.cell(row=fila, column=COL_CODIGO, value=codigo)
            ws.cell(row=fila, column=COL_NOMBRE, value=partes[0])
            ws.cell(row=fila, column=COL_CANT, value=float(cant))
            ws.cell(row=fila, column=COL_UNIT, value=float(unit))
            ws.cell(row=fila, column=COL_PAC, value=0.0)
            ws.cell(row=fila, column=COL_ENT, value=float(cant * unit))
            for extra in partes[1:]:  # nombre largo partido en dos renglones
                fila += 1
                ws.cell(row=fila, column=COL_NOMBRE, value=extra)

    subtotal = sum(c * u for _, items in grupos for _, _, c, u in items)
    fila += 2
    for etiqueta, valor in (
        ("VALOR SUBTOTAL DE SERVICIOS PRESTADOS", float(subtotal)),
        ("VALOR CUOTA COPAGO Y/O CUOTA MODERADORA", 0.0),
        ("VALOR ANTICIPO PAGADO POR EL USUARIO", 0.0),
        ("VALOR CUOTA DE COPAGO Y/O CUOTA MODERADORA ASUMIDA POR EL USUARIO", 0.0),
        ("VALOR TOTAL ORDEN DE SERVICIO", float(subtotal)),
    ):
        ws.cell(row=fila, column=1, value=etiqueta)
        ws.cell(row=fila, column=COL_ENT, value=valor)
        fila += 1
    ws.cell(row=fila, column=1, value="TOTAL:")
    ws.cell(row=fila, column=2, value="")
    ws.cell(row=fila + 1, column=1, value="NOTAS FINALES:")


# Las 9 filas del ReporteGlosasReclamPAQUETE 31068 para HUS352890, tal como
# vienen en el documento: la venda de gasa llega repartida en DOS filas.
FILAS_REPORTE = [
    # cod, descripcion, cant_recl, vlr_recl, cant_apr, vlr_apr, glosado, glosa
    ("39221", "Derechos de sala de yesos", 1, 100700, 1, 100700, 0, ""),
    ("2016DM-0000315-R2", "VENDA DE GASA 6 X 5 YARDAS", 4, 37600, 0, 0, 37600,
     "3106- Soporte de material ausente o incompleto"),
    ("39145", "Consulta de urgencias", 1, 85800, 0, 0, 85800,
     "3202- La consulta no esta justificada"),
    ("2022DM-0008875-R1", "VENDA DE ALGODON 6 X 5 YARDAS", 4, 18400, 4, 18400, 0, ""),
    ("2017DM-0016044", "VENDA ELASTICA 6 X 5 YARDAS", 4, 21600, 4, 21600, 0, ""),
    ("2016DM-0000315-R2", "VENDA DE GASA 6 X 5 YARDAS", 2, 18800, 2, 9400, 9400,
     "3106- Soporte de material ausente o incompleto"),
    ("19992190-3", "DICLOFENACO SODICO 75MG/3ML CAJA POR 10 AMPOLLAS", 1, 900, 1, 900, 0, ""),
    ("37206", "Inmovilización miembro superior o inferior total o parcial", 1, 82000, 1, 82000, 0, ""),
    ("21102", "Brazo, pierna, rodilla, fémur, hombro, omoplato", 1, 95300, 1, 95300, 0, ""),
]


@pytest.fixture()
def archivos(tmp_path: Path):
    """(detallado, reporte_glosas, consolidado) listos para correr el bot."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "HUS352890"
    _hoja_detallado(ws, "HUS352890")
    # Una segunda factura que NO está en el consolidado: debe desaparecer.
    ws2 = wb.create_sheet("HUS999999")
    _hoja_detallado(ws2, "HUS999999")
    detallado = tmp_path / "detallados.xlsx"
    wb.save(detallado)

    wbg = openpyxl.Workbook()
    wsg = wbg.active
    wsg.append([
        "Código Habilitación", "Número Radicación", "Número Factura", "Número Paquete",
        "Cantidad Reclamado", "Valor Reclamado", "Cantidad Aprobada", "Valor Aprobado",
        "Valor Glosado", "Tip- Num Doc Victima", "Consecutivo Item", "Tipo Elemento",
        "Cod Elemento", "Descripción Elemento", "Descripción Glosa", "Descripción Anotación",
    ])
    for cod, desc, cr, vr, ca, va, vg, glosa in FILAS_REPORTE:
        wsg.append([
            "680010079201", "14344788", "HUS352890", "31068", cr, vr, ca, va, vg,
            "CC-1005338825", "", "Procedimientos", cod, desc, glosa, "",
        ])
    reporte = tmp_path / "ReporteGlosasReclamPAQUETE 31068.xlsx"
    wbg.save(reporte)

    wbc = openpyxl.Workbook()
    wsc = wbc.active
    wsc.append(["NUMERO FACTURA"])
    for fac in ("HUS352890", "HUS352890", "hus0000352890"):  # con duplicados
        wsc.append([fac])
    consolidado = tmp_path / "consolidado.xlsx"
    wbc.save(consolidado)

    return detallado, reporte, consolidado


# ─── Utilidades ──────────────────────────────────────────────────────────────


class TestParseo:
    def test_valor_cop(self):
        assert aj._parse_valor("$ 85.800,00") == 85800.0
        assert aj._parse_valor("56.400") == 56400.0
        assert aj._parse_valor(9400) == 9400.0
        assert aj._parse_valor("") == 0.0

    def test_norm_desc_ignora_tildes_y_puntuacion(self):
        assert aj._norm_desc("Inmovilización miembro superior") == "INMOVILIZACION MIEMBRO SUPERIOR"
        assert aj._norm_desc("Brazo, pierna, rodilla") == "BRAZO PIERNA RODILLA"

    def test_norm_codigo(self):
        assert aj._norm_codigo(" 19992190-3 ") == "19992190-3"
        assert aj._norm_codigo("2016DM-0000315-R2") == "2016DM-0000315-R2"


class TestNumeroALetras:
    @pytest.mark.parametrize(
        "valor,esperado",
        [
            (0, "CERO PESOS M/CTE"),
            (95200, "NOVENTA Y CINCO MIL DOSCIENTOS PESOS M/CTE"),
            (132800, "CIENTO TREINTA Y DOS MIL OCHOCIENTOS PESOS M/CTE"),
            (100, "CIEN PESOS M/CTE"),
            (1000, "MIL PESOS M/CTE"),
            (21000, "VEINTIUN MIL PESOS M/CTE"),
            (1_000_000, "UN MILLON PESOS M/CTE"),
            (2_500_300, "DOS MILLONES QUINIENTOS MIL TRESCIENTOS PESOS M/CTE"),
        ],
    )
    def test_letras(self, valor, esperado):
        assert aj.numero_a_letras(valor) == esperado


# ─── Consolidado y reporte ───────────────────────────────────────────────────


class TestConsolidado:
    def test_quita_duplicados(self, archivos):
        _, _, consolidado = archivos
        unicas, duplicadas = aj.leer_consolidado(consolidado)
        assert unicas == ["HUS352890"]
        assert len(duplicadas) == 2  # el repetido y el mismo con ceros de relleno

    def test_sin_encabezado_rastrea_facturas(self, tmp_path):
        ruta = tmp_path / "lista.csv"
        ruta.write_text("bla;HUS352890\notra;HUS400001\nrepetida;HUS352890\n", encoding="utf-8")
        unicas, duplicadas = aj.leer_consolidado(ruta)
        assert unicas == ["HUS352890", "HUS400001"]
        assert duplicadas == ["HUS352890"]


class TestReporteGlosas:
    def test_agrupa_por_factura(self, archivos):
        _, reporte, _ = archivos
        glosas = aj.leer_reporte_glosas(reporte)
        assert list(glosas) == ["352890"]
        assert len(glosas["352890"]) == 9
        assert sum(g.valor_glosado for g in glosas["352890"]) == 132800

    def test_filtra_por_paquete(self, archivos):
        _, reporte, _ = archivos
        assert aj.leer_reporte_glosas(reporte, paquete="99999") == {}


# ─── Lectura de la hoja ──────────────────────────────────────────────────────


class TestEstructura:
    def test_detecta_titulo_tabla_y_totales(self, archivos):
        detallado, _, _ = archivos
        ws = openpyxl.load_workbook(detallado)["HUS352890"]
        est = aj.detectar_estructura(ws)
        assert est["fila_titulo"] == 11
        assert est["fila_hdr"] == 20
        assert est["fila_subtotal"] > est["fila_hdr"]
        assert est["cols"]["cantidad"] == COL_CANT
        assert est["cols"]["vr_ent"] == COL_ENT

    def test_factura_de_hoja(self, archivos):
        detallado, _, _ = archivos
        ws = openpyxl.load_workbook(detallado)["HUS352890"]
        assert aj.factura_de_hoja(ws) == "HUS352890"

    def test_bloques_items_y_continuaciones(self, archivos):
        detallado, _, _ = archivos
        ws = openpyxl.load_workbook(detallado)["HUS352890"]
        bloques = aj.leer_bloques(ws, aj.detectar_estructura(ws))
        titulos = [b.titulo for b in bloques if b.fila_titulo]
        assert titulos == [g[0] for g in GRUPOS_HUS352890]
        items = [i for b in bloques for i in b.items]
        assert len(items) == 8
        inmov = next(i for i in items if i.codigo == "37206")
        # El nombre partido en dos renglones se une para poder cruzarlo.
        assert inmov.nombre == "INMOVILIZACION MIEMBRO SUPERIOR O INFERIOR TOTAL O PARCIAL"
        assert len(inmov.filas) == 2
        gasa = next(i for i in items if i.codigo == "FMQ0046")
        assert (gasa.cantidad, gasa.vr_unit, gasa.vr_ent) == (6.0, 9400.0, 56400.0)


# ─── Cruce y decisión ────────────────────────────────────────────────────────


class TestCruce:
    def _items_y_glosas(self, archivos):
        detallado, reporte, _ = archivos
        ws = openpyxl.load_workbook(detallado)["HUS352890"]
        bloques = aj.leer_bloques(ws, aj.detectar_estructura(ws))
        items = [i for b in bloques for i in b.items]
        glosas = aj.leer_reporte_glosas(reporte)["352890"]
        return items, aj._indexar(glosas)

    def test_cruza_por_codigo(self, archivos):
        items, idx = self._items_y_glosas(archivos)
        item = next(i for i in items if i.codigo == "39145")
        filas, criterio = aj.cruzar_item(item, idx)
        assert criterio == "codigo" and len(filas) == 1

    def test_cruza_dispositivo_por_descripcion(self, archivos):
        """El reporte trae código INVIMA y la factura el código interno."""
        items, idx = self._items_y_glosas(archivos)
        item = next(i for i in items if i.codigo == "FMQ0042")
        filas, criterio = aj.cruzar_item(item, idx)
        assert criterio == "descripcion" and len(filas) == 1

    def test_suma_las_filas_repetidas_del_mismo_item(self, archivos):
        """La venda de gasa viene en dos filas: 37.600 + 9.400 = 47.000."""
        items, idx = self._items_y_glosas(archivos)
        item = next(i for i in items if i.codigo == "FMQ0046")
        filas, _ = aj.cruzar_item(item, idx)
        assert len(filas) == 2
        assert sum(f.valor_glosado for f in filas) == 47000

    def test_no_reutiliza_filas_ya_cruzadas(self, archivos):
        items, idx = self._items_y_glosas(archivos)
        gasa = next(i for i in items if i.codigo == "FMQ0046")
        aj.cruzar_item(gasa, idx)
        assert aj.cruzar_item(gasa, idx) == ([], "")


class TestDecidir:
    def _item(self, cant=1, unit=1000):
        return aj.ItemDetallado(
            fila=1, filas=[1], grupo="G", codigo="X", nombre="N",
            cantidad=cant, vr_unit=unit, vr_pac=0, vr_ent=cant * unit,
        )

    def _glosa(self, recl, apr, glosado, cant_recl=1, cant_apr=0):
        return aj.FilaGlosa(
            factura="HUS1", codigo="X", descripcion="N", cant_reclamada=cant_recl,
            valor_reclamado=recl, cant_aprobada=cant_apr, valor_aprobado=apr,
            valor_glosado=glosado,
        )

    def test_aprobado_completo_se_quita(self):
        accion, *_ = aj.decidir(self._item(), [self._glosa(1000, 1000, 0)], "ajustar", "conservar")
        assert accion == "QUITADO"

    def test_glosado_completo_se_conserva(self):
        accion, cant, valor, _ = aj.decidir(
            self._item(), [self._glosa(1000, 0, 1000)], "ajustar", "conservar"
        )
        assert (accion, cant, valor) == ("CONSERVADO", 1, 1000)

    def test_parcial_ajusta_cantidad_y_valor(self):
        item = self._item(cant=6, unit=9400)
        filas = [self._glosa(37600, 0, 37600, 4, 0), self._glosa(18800, 9400, 9400, 2, 1)]
        accion, cant, valor, _ = aj.decidir(item, filas, "ajustar", "conservar")
        assert (accion, cant, valor) == ("AJUSTADO", 5.0, 47000)

    def test_parcial_modo_conservar(self):
        item = self._item(cant=6, unit=9400)
        accion, cant, valor, _ = aj.decidir(
            item, [self._glosa(56400, 9400, 47000, 6, 1)], "conservar", "conservar"
        )
        assert (accion, cant, valor) == ("CONSERVADO", 6, 56400)

    def test_sin_cruce_conserva_y_marca(self):
        accion, _, _, nota = aj.decidir(self._item(), [], "ajustar", "conservar")
        assert accion == "SIN_CRUCE" and "REVISAR" in nota

    def test_sin_cruce_quitar(self):
        accion, *_ = aj.decidir(self._item(), [], "ajustar", "quitar")
        assert accion == "QUITADO"


# ─── Corrida completa ────────────────────────────────────────────────────────


class TestCorridaCompleta:
    def _correr(self, archivos, tmp_path, extra=()):
        detallado, reporte, consolidado = archivos
        salida = tmp_path / "salida.xlsx"
        bitacora = tmp_path / "bitacora.csv"
        codigo = aj.main([
            "--consolidado", str(consolidado),
            "--detallado", str(detallado),
            "--reporte-glosas", str(reporte),
            "--salida", str(salida),
            "--reporte-csv", str(bitacora),
            *extra,
        ])
        assert codigo == 0
        return salida, bitacora

    def test_deja_solo_lo_glosado(self, archivos, tmp_path):
        salida, _ = self._correr(archivos, tmp_path)
        wb = openpyxl.load_workbook(salida)
        # La factura que no estaba en el consolidado desapareció.
        assert wb.sheetnames == ["HUS352890"]
        ws = wb["HUS352890"]

        # Encabezado institucional fuera y título cambiado.
        assert ws.cell(row=1, column=1).value == aj.TITULO_NUEVO
        texto = "\n".join(
            str(c.value) for f in ws.iter_rows() for c in f if c.value is not None
        )
        assert "CUFE" not in texto
        assert "Bucaramanga" not in texto
        assert aj.TITULO_ORIGINAL not in texto

        # Quedan solo los dos grupos con ítems glosados.
        assert "CONSULTAS MEDICAS" in texto and "MATERIALES E INSUMOS" in texto
        for fuera in ("MEDICAMENTOS POS", "DERECHOS DE SALA", "IMAGENOLOGIA"):
            assert fuera not in texto
        for fuera in ("DICLOFENACO", "VENDA DE ALGODON", "VENDA ELASTICA", "INMOVILIZACION"):
            assert fuera not in texto
        assert "CONSULTA DE URGENCIAS" in texto and "VENDA DE GASA" in texto

    def test_ajusta_cantidad_de_la_venda_de_gasa(self, archivos, tmp_path):
        salida, _ = self._correr(archivos, tmp_path)
        ws = openpyxl.load_workbook(salida)["HUS352890"]
        fila = next(
            c.row for f in ws.iter_rows() for c in f
            if str(c.value or "").startswith("VENDA DE GASA")
        )
        assert ws.cell(row=fila, column=COL_CANT).value == 5.0
        assert ws.cell(row=fila, column=COL_ENT).value == 47000

    def test_recalcula_totales_y_total_en_letras(self, archivos, tmp_path):
        salida, _ = self._correr(archivos, tmp_path)
        ws = openpyxl.load_workbook(salida)["HUS352890"]
        valores = {}
        for f in ws.iter_rows():
            etiqueta = str(f[0].value or "")
            if etiqueta.startswith("VALOR ") or etiqueta.startswith("TOTAL:"):
                valores[etiqueta] = [c.value for c in f[1:] if c.value not in (None, "")]
        assert valores["VALOR SUBTOTAL DE SERVICIOS PRESTADOS"][-1] == 132800
        assert valores["VALOR TOTAL ORDEN DE SERVICIO"][-1] == 132800
        assert valores["TOTAL:"][0] == "CIENTO TREINTA Y DOS MIL OCHOCIENTOS PESOS M/CTE"

    def test_bitacora_csv(self, archivos, tmp_path):
        _, bitacora = self._correr(archivos, tmp_path)
        lineas = bitacora.read_text(encoding="utf-8-sig").splitlines()
        assert lineas[0].startswith("FACTURA;HOJA;GRUPO")
        acciones = [ln.split(";")[10] for ln in lineas[1:]]
        assert acciones.count("QUITADO") == 6
        assert acciones.count("AJUSTADO") == 1
        assert acciones.count("CONSERVADO") == 1
        assert "ELIMINADA" in acciones  # la hoja HUS999999

    def test_diagnostico_no_escribe_salida(self, archivos, tmp_path):
        detallado, reporte, consolidado = archivos
        salida = tmp_path / "no_debe_existir.xlsx"
        assert aj.main([
            "--consolidado", str(consolidado),
            "--detallado", str(detallado),
            "--reporte-glosas", str(reporte),
            "--salida", str(salida),
            "--diagnostico",
        ]) == 0
        assert not salida.exists()

    def test_modo_parcial_conservar(self, archivos, tmp_path):
        salida, _ = self._correr(archivos, tmp_path, extra=["--modo-parcial", "conservar"])
        ws = openpyxl.load_workbook(salida)["HUS352890"]
        fila = next(
            c.row for f in ws.iter_rows() for c in f
            if str(c.value or "").startswith("VENDA DE GASA")
        )
        assert ws.cell(row=fila, column=COL_CANT).value == 6.0

    def test_no_toca_los_archivos_originales(self, archivos, tmp_path):
        detallado, _, _ = archivos
        antes = detallado.read_bytes()
        self._correr(archivos, tmp_path)
        assert detallado.read_bytes() == antes


class TestCeldasCombinadas:
    def test_al_borrar_filas_se_corren_las_combinaciones(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        for fila in range(1, 11):
            ws.cell(row=fila, column=1, value=f"r{fila}")
        ws.merge_cells("A8:D8")
        aj.eliminar_filas(ws, {3})
        assert [str(r) for r in ws.merged_cells.ranges] == ["A7:D7"]
        assert ws.cell(row=7, column=1).value == "r8"
