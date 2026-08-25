"""Tests del ajustador de detallados (tools/ajustar_detallado_glosas.py).

El fixture reproduce el formato REAL del detallado que baja el sistema: una
sola hoja con varias facturas apiladas, el membrete del hospital una única vez
al principio, y cada dato dentro de un rango combinado cuyos límites NO
coinciden con los del encabezado de la tabla.

La factura de ejemplo es la HUS352890 del documento del auditor.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

openpyxl = pytest.importorskip("openpyxl")

import ajustar_detallado_glosas as aj  # noqa: E402

# ─── Geometría real de la hoja (columnas de cada rango combinado) ────────────

# Encabezado de la tabla.
HDR = {
    "codigo": (3, 13),
    "nombre": (14, 29),
    "cantidad": (30, 33),
    "vr_unit": (34, 44),
    "vr_pac": (45, 52),
    "vr_ent": (53, 64),
}
# Los ítems van corridos respecto del encabezado: leer "VR ENT" en la columna
# 53 cae dentro del rango de "VR PAC" del ítem (44-58).
ITEM = {
    "consecutivo": (5, 7),
    "codigo": (8, 13),
    "nombre": (14, 28),
    "cantidad": (29, 33),
    "vr_unit": (34, 43),
    "vr_pac": (44, 58),
    "vr_ent": (59, 64),
}
TOT_ETIQUETA, TOT_CANT, TOT_VALOR = (6, 31), (32, 53), (54, 66)

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


def _poner(ws, fila, span, valor, alto=1):
    """Escribe un valor en un rango combinado, como hace el sistema."""
    ws.cell(row=fila, column=span[0], value=valor)
    if span[1] > span[0] or alto > 1:
        ws.merge_cells(
            start_row=fila, start_column=span[0], end_row=fila + alto - 1, end_column=span[1]
        )


def _membrete(ws) -> None:
    _poner(ws, 1, (19, 40), "Carrrera 33 # 28 -126  Teléfono 6910030")
    _poner(ws, 1, (61, 64), "Página 1/1")
    _poner(ws, 3, (19, 40), "NIT 900.006.037-4")
    _poner(ws, 4, (19, 40), "Bucaramanga")
    _poner(ws, 9, (1, 60), "CUFE:00a8dd40ad98f18932a3551ef3d97121391d260f783dc02cf4ac1")


def _pie_archivo(ws, fila) -> None:
    _poner(ws, fila, (5, 60), "AUTORIZACIÓN FACTURA ELECTRÓNICA DE VENTA RESOLUCIÓN Nº 18764")
    _poner(ws, fila + 2, (5, 60), "Nombre reporte : FCRPFacturaEntidad")
    _poner(ws, fila + 3, (6, 60), "LICENCIADO A: [E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER]")


def _factura(ws, fila: int, factura: str, grupos=GRUPOS_HUS352890) -> int:
    """Escribe una factura completa. Devuelve la fila siguiente libre."""
    _poner(ws, fila, (6, 26), "FACTURA ELECTRONICA DE VENTA")
    _poner(ws, fila, (27, 49), factura)
    _poner(ws, fila + 3, (6, 8), "CLIENTE")
    _poner(ws, fila + 3, (10, 37), "ADMINISTRADORA DE LOS RECURSOS DEL SISTEMA")
    _poner(ws, fila + 8, (6, 8), "Paciente")
    _poner(ws, fila + 8, (17, 47), "JUAN ESTEBAN GARCIA RESTREPO")

    fila += 20
    for campo, span in HDR.items():
        etiqueta = {
            "codigo": "CÓDIGO",
            "nombre": "NOMBRE",
            "cantidad": "CANT",
            "vr_unit": "VR UNIT",
            "vr_pac": "VR PAC",
            "vr_ent": "VR ENT",
        }[campo]
        _poner(ws, fila, span, etiqueta)

    fila += 1
    n = 0
    for titulo, items in grupos:
        fila += 1
        _poner(ws, fila, (2, 67), titulo)
        fila += 2  # renglón en blanco que trae el formato
        for codigo, nombre, cant, unit in items:
            n += 1
            partes = nombre.split("|")
            # Los nombres largos ocupan dos filas (merge vertical).
            alto = 2 if len(partes) > 1 else 1
            _poner(ws, fila, ITEM["consecutivo"], n, alto)
            _poner(ws, fila, ITEM["codigo"], codigo, alto)
            _poner(ws, fila, ITEM["nombre"], partes[0])
            _poner(ws, fila, ITEM["cantidad"], float(cant), alto)
            _poner(ws, fila, ITEM["vr_unit"], float(unit), alto)
            _poner(ws, fila, ITEM["vr_pac"], 0.0, alto)
            _poner(ws, fila, ITEM["vr_ent"], float(cant * unit), alto)
            if alto == 2:
                _poner(ws, fila + 1, ITEM["nombre"], partes[1])
            fila += alto

    subtotal = sum(c * u for _, items in grupos for _, _, c, u in items)
    fila += 2
    for etiqueta, valor in (
        ("VALOR SUBTOTAL DE SERVICIOS PRESTADOS", float(subtotal)),
        ("VALOR CUOTA COPAGO Y/0 CUOTA MODERADORA", 0.0),
        ("VALOR ANTICIPO PAGADO POR EL USUARIO", 0.0),
        ("VALOR CUOTA DE COPAGO Y/O CUOTA MODERADORA ASUMIDA POR EL USUARIO", 0.0),
        ("VALOR TOTAL ORDEN DE SERVICIO", float(subtotal)),
    ):
        _poner(ws, fila, TOT_ETIQUETA, etiqueta)
        if etiqueta.startswith("VALOR SUBTOTAL"):
            _poner(ws, fila, TOT_CANT, n)
        _poner(ws, fila, TOT_VALOR, valor)
        fila += 1
    _poner(ws, fila, (6, 10), "TOTAL:")
    _poner(ws, fila, (11, 66), aj.numero_a_letras(subtotal))
    _poner(ws, fila + 1, (6, 14), "NOTAS FINALES:")
    _poner(ws, fila + 2, (6, 20), "ELABORO")
    _poner(ws, fila + 2, (59, 66), "AUDITOR")
    return fila + 4


# Las 9 filas del ReporteGlosasReclamPAQUETE 31068 para HUS352890 del documento
# del auditor: la venda de gasa llega repartida en DOS filas.
FILAS_REPORTE = [
    # tipo, cod, descripcion, cant_recl, vlr_recl, cant_apr, vlr_apr, glosado, glosa
    ("Procedimientos", "39221", "Derechos de sala de yesos", 1, 100700, 1, 100700, 0, ""),
    (
        "Dispositivos Médicos",
        "2016DM-0000315-R2",
        "VENDA DE GASA 6 X 5 YARDAS",
        4,
        37600,
        0,
        0,
        37600,
        "3106- Soporte de material ausente o incompleto",
    ),
    (
        "Procedimientos",
        "39145",
        "Consulta de urgencias",
        1,
        85800,
        0,
        0,
        85800,
        "3202- La consulta no esta justificada",
    ),
    (
        "Dispositivos Médicos",
        "2022DM-0008875-R1",
        "VENDA DE ALGODON 6 X 5 YARDAS",
        4,
        18400,
        4,
        18400,
        0,
        "",
    ),
    (
        "Dispositivos Médicos",
        "2017DM-0016044",
        "VENDA ELASTICA 6 X 5 YARDAS",
        4,
        21600,
        4,
        21600,
        0,
        "",
    ),
    (
        "Dispositivos Médicos",
        "2016DM-0000315-R2",
        "VENDA DE GASA 6 X 5 YARDAS",
        2,
        18800,
        2,
        9400,
        9400,
        "3106- Soporte de material ausente o incompleto",
    ),
    (
        "Medicamentos",
        "19992190-03",
        "DICLOFENACO SODICO 75MG/3ML CAJA POR 10 AMPOLLAS",
        1,
        900,
        1,
        900,
        0,
        "",
    ),
    (
        "Procedimientos",
        "37206",
        "Inmovilización miembro superior o inferior total o parcial",
        1,
        82000,
        1,
        82000,
        0,
        "",
    ),
    (
        "Procedimientos",
        "21102",
        "Brazo, pierna, rodilla, fémur, hombro, omoplato",
        1,
        95300,
        1,
        95300,
        0,
        "",
    ),
]


@pytest.fixture()
def archivos(tmp_path: Path):
    """(detallado, reporte_glosas, consolidado) listos para correr el bot."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet"
    _membrete(ws)
    fila = _factura(ws, 10, "HUS352890")
    # Una segunda factura que NO está en el consolidado: debe desaparecer.
    fila = _factura(ws, fila, "HUS999999")
    _pie_archivo(ws, fila)
    detallado = tmp_path / "detallados.xlsx"
    wb.save(detallado)

    wbg = openpyxl.Workbook()
    wsg = wbg.active
    for _ in range(6):  # el reporte real trae el título arriba del encabezado
        wsg.append([])
    wsg.append(
        [
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
    )
    for tipo, cod, desc, cr, vr, ca, va, vg, glosa in FILAS_REPORTE:
        wsg.append(
            [
                "680010079201",
                "14344788",
                "HUS352890",
                "31068",
                cr,
                vr,
                ca,
                va,
                vg,
                "CC-1005338825",
                "",
                tipo,
                cod,
                desc,
                glosa,
                "",
            ]
        )
    reporte = tmp_path / "ReporteGlosasReclamPAQUETE 31068.xlsx"
    wbg.save(reporte)

    consolidado = tmp_path / "consolidado.txt"
    consolidado.write_text("HUS352890\nHUS352890\nhus0000352890\n", encoding="utf-8")
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

    def test_norm_codigo_iguala_los_ceros_de_relleno(self):
        """La factura dice 19935303-4 y el reporte 19935303-04."""
        assert aj._norm_codigo("19935303-4") == aj._norm_codigo("19935303-04")
        assert aj._norm_codigo("20125214-1") == aj._norm_codigo("20125214-01")
        assert aj._norm_codigo(" 19992190-3 ") == "19992190-3"
        assert aj._norm_codigo("2016DM-0000315-R2") == "2016DM-315-R2"
        assert aj._norm_codigo("20084685-6") != aj._norm_codigo("20084685-18")


class TestNumeroALetras:
    @pytest.mark.parametrize(
        "valor,esperado",
        [
            (0, "CERO PESOS CON CERO CTVS M/Cte."),
            (100, "CIEN PESOS CON CERO CTVS M/Cte."),
            (1000, "MIL PESOS CON CERO CTVS M/Cte."),
            (21000, "VEINTIUN MIL PESOS CON CERO CTVS M/Cte."),
            (69656, "SESENTA Y NUEVE MIL SEISCIENTOS CINCUENTA Y SEIS PESOS CON CERO CTVS M/Cte."),
            (1_000_000, "UN MILLON PESOS CON CERO CTVS M/Cte."),
            (
                2_096_754,
                "DOS MILLONES NOVENTA Y SEIS MIL SETECIENTOS CINCUENTA Y CUATRO PESOS "
                "CON CERO CTVS M/Cte.",
            ),
            (132_800, "CIENTO TREINTA Y DOS MIL OCHOCIENTOS PESOS CON CERO CTVS M/Cte."),
            (100.5, "CIEN PESOS CON CINCUENTA CTVS M/Cte."),
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
    def test_agrupa_por_factura_con_titulo_arriba(self, archivos):
        _, reporte, _ = archivos
        glosas = aj.leer_reporte_glosas(reporte)
        assert list(glosas) == ["352890"]
        assert len(glosas["352890"]) == 9

    def test_filtra_por_paquete(self, archivos):
        _, reporte, _ = archivos
        assert aj.leer_reporte_glosas(reporte, paquete="99999") == {}

    def test_separa_las_glosas_a_la_reclamacion(self):
        """Las filas 'Reclamacion' no son ítems: repiten el total y duplicarían."""
        filas = [
            aj.FilaGlosa(
                factura="HUS1",
                codigo="",
                descripcion="",
                tipo_elemento="Reclamacion",
                valor_reclamado=1000,
                valor_glosado=1000,
            ),
            aj.FilaGlosa(
                factura="HUS1",
                codigo="39145",
                descripcion="Consulta",
                tipo_elemento="Procedimientos",
                cant_reclamada=1,
                valor_reclamado=1000,
                valor_glosado=1000,
            ),
        ]
        items, reclamacion = aj.agrupar_reporte(filas)
        assert len(items) == 1 and len(reclamacion) == 1
        assert items[0].valor_glosado == 1000


# ─── Lectura de la hoja ──────────────────────────────────────────────────────


class TestLecturaHoja:
    def _idx(self, archivos):
        detallado, _, _ = archivos
        ws = openpyxl.load_workbook(detallado)["Sheet"]
        return aj.IndiceHoja(ws)

    def test_segmenta_las_facturas_apiladas(self, archivos):
        facturas = aj.segmentar_facturas(self._idx(archivos))
        assert [f.factura for f in facturas] == ["HUS352890", "HUS999999"]
        assert facturas[0].fila_ini == 10
        assert facturas[0].fila_fin < facturas[1].fila_ini

    def test_el_pie_del_archivo_no_entra_en_la_ultima_factura(self, archivos):
        idx = self._idx(archivos)
        ultima = aj.segmentar_facturas(idx)[-1]
        texto = " ".join(idx.texto_fila(f) for f in range(ultima.fila_ini, ultima.fila_fin + 1))
        assert "LICENCIADO A" not in texto
        assert "Nombre reporte" not in texto

    def test_membrete(self, archivos):
        idx = self._idx(archivos)
        primera = aj.segmentar_facturas(idx)[0]
        filas = aj.filas_encabezado_institucional(idx, primera.fila_ini)
        assert filas == set(range(1, 10))

    def test_detecta_la_tabla_y_los_totales(self, archivos):
        idx = self._idx(archivos)
        fac = aj.segmentar_facturas(idx)[0]
        est = aj.detectar_estructura(idx, fac)
        assert dict(est.cabeceras)["vr_ent"] == HDR["vr_ent"]
        assert est.fila_subtotal > est.fila_hdr

    def test_items_y_continuaciones(self, archivos):
        idx = self._idx(archivos)
        fac = aj.segmentar_facturas(idx)[0]
        bloques = aj.leer_bloques(idx, aj.detectar_estructura(idx, fac))
        assert [b.titulo for b in bloques if b.fila_titulo] == [g[0] for g in GRUPOS_HUS352890]
        items = [i for b in bloques for i in b.items]
        assert len(items) == 8
        inmov = next(i for i in items if i.codigo == "37206")
        assert inmov.nombre == "INMOVILIZACION MIEMBRO SUPERIOR O INFERIOR TOTAL O PARCIAL"
        assert len(inmov.filas) == 2  # el ítem ocupa dos renglones
        gasa = next(i for i in items if i.codigo == "FMQ0046")
        assert (gasa.cantidad, gasa.vr_unit, gasa.vr_ent) == (6.0, 9400.0, 56400.0)


class TestDesglose:
    """Los procedimientos quirúrgicos abren renglones SIN consecutivo cuyo valor
    ya está incluido en el renglón que los encabeza: no vuelven a sumar."""

    def _hoja(self, tmp_path):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Sheet"
        _poner(ws, 1, (6, 26), "FACTURA ELECTRONICA DE VENTA")
        _poner(ws, 1, (27, 49), "HUS400000")
        fila = 5
        for campo, span in HDR.items():
            _poner(
                ws,
                fila,
                span,
                {
                    "codigo": "CÓDIGO",
                    "nombre": "NOMBRE",
                    "cantidad": "CANT",
                    "vr_unit": "VR UNIT",
                    "vr_pac": "VR PAC",
                    "vr_ent": "VR ENT",
                }[campo],
            )
        _poner(ws, fila + 1, (2, 67), "PROCEDIMIENTOS TERAPEUTICOS QUIRURGICOS")
        # Renglón principal (con consecutivo) por 1.000.000…
        _poner(ws, fila + 2, ITEM["consecutivo"], 1)
        _poner(ws, fila + 2, ITEM["codigo"], "15103")
        _poner(ws, fila + 2, ITEM["nombre"], "DESBRIDAMIENTO")
        _poner(ws, fila + 2, ITEM["cantidad"], 1.0)
        _poner(ws, fila + 2, ITEM["vr_unit"], 1000000.0)
        _poner(ws, fila + 2, ITEM["vr_pac"], 0.0)
        _poner(ws, fila + 2, ITEM["vr_ent"], 1000000.0)
        # …y su desglose (sin consecutivo), que suma lo mismo.
        for n, (cod, nom, val) in enumerate(
            [("39005", "HONORARIOS CIRUJANO", 600000.0), ("39209", "DERECHOS DE SALA", 400000.0)]
        ):
            f = fila + 3 + n
            _poner(ws, f, (8, 13), cod)
            _poner(ws, f, (14, 30), nom)
            _poner(ws, f, (31, 33), 1.0)
            _poner(ws, f, (34, 45), val)
            _poner(ws, f, (46, 58), 0.0)
            _poner(ws, f, (59, 64), val)
        fila += 6
        _poner(ws, fila, TOT_ETIQUETA, "VALOR SUBTOTAL DE SERVICIOS PRESTADOS")
        _poner(ws, fila, TOT_CANT, 1)
        _poner(ws, fila, TOT_VALOR, 1000000.0)
        _poner(ws, fila + 1, TOT_ETIQUETA, "VALOR TOTAL ORDEN DE SERVICIO")
        _poner(ws, fila + 1, TOT_VALOR, 1000000.0)
        _poner(ws, fila + 2, (6, 10), "TOTAL:")
        _poner(ws, fila + 2, (11, 66), aj.numero_a_letras(1000000))
        ruta = tmp_path / "desglose.xlsx"
        wb.save(ruta)
        return ruta

    def test_marca_los_renglones_sin_consecutivo(self, tmp_path):
        idx = aj.IndiceHoja(openpyxl.load_workbook(self._hoja(tmp_path))["Sheet"])
        fac = aj.segmentar_facturas(idx)[0]
        est = aj.detectar_estructura(idx, fac)
        items = [i for b in aj.leer_bloques(idx, est) for i in b.items]
        assert [i.desglose for i in items] == [False, True, True]
        assert [i.codigo for i in items] == ["15103", "39005", "39209"]

    def test_el_valor_de_la_factura_no_se_cuenta_dos_veces(self, tmp_path):
        """Sumar los tres renglones daría 2.000.000; la factura vale 1.000.000."""
        idx = aj.IndiceHoja(openpyxl.load_workbook(self._hoja(tmp_path))["Sheet"])
        fac = aj.segmentar_facturas(idx)[0]
        glosas = [
            aj.FilaGlosa(
                factura="HUS400000",
                codigo="15103",
                descripcion="Desbridamiento",
                tipo_elemento="Procedimientos",
                cant_reclamada=0,
                valor_reclamado=0,
            ),
            aj.FilaGlosa(
                factura="HUS400000",
                codigo="39005",
                descripcion="Honorarios cirujano",
                tipo_elemento="Procedimientos",
                cant_reclamada=1,
                valor_reclamado=600000,
                valor_glosado=600000,
            ),
            aj.FilaGlosa(
                factura="HUS400000",
                codigo="39209",
                descripcion="Derechos de sala",
                tipo_elemento="Procedimientos",
                cant_reclamada=1,
                valor_reclamado=400000,
                valor_aprobado=400000,
            ),
        ]
        res, _ = aj.procesar_factura(idx, fac, glosas, hoja="Sheet", aplicar=False)
        assert res.subtotal_antes == 1000000  # el subtotal real, no la suma de renglones
        assert res.subtotal_despues == 600000  # solo el honorario sigue glosado


class TestMapeoPorSolapamiento:
    def test_vr_ent_no_se_lleva_el_bloque_de_vr_pac(self):
        """La columna del rótulo VR ENT (53) cae dentro del rango VR PAC del
        ítem (44-58): sin el desempate, VR ENT leería el valor de VR PAC."""
        cabeceras = sorted(HDR.items(), key=lambda x: x[1][0])
        celdas = [
            aj.Celda(1, 1, *ITEM["consecutivo"], 1),
            aj.Celda(1, 1, *ITEM["codigo"], "39145"),
            aj.Celda(1, 1, *ITEM["nombre"], "CONSULTA DE URGENCIAS"),
            aj.Celda(1, 1, *ITEM["cantidad"], 1),
            aj.Celda(1, 1, *ITEM["vr_unit"], 85800),
            aj.Celda(1, 1, *ITEM["vr_pac"], 0),
            aj.Celda(1, 1, *ITEM["vr_ent"], 85800),
        ]
        celdas = [aj.Celda(1, 1, c.col, c.col_fin, c.valor) for c in celdas]
        campos = aj.mapear_por_solapamiento(cabeceras, celdas)
        assert campos["vr_ent"].valor == 85800
        assert campos["vr_pac"].valor == 0
        assert campos["codigo"].valor == "39145"
        assert campos["cantidad"].valor == 1

    def test_formato_sin_celdas_combinadas(self):
        """Con celdas sueltas (y sin solapamiento) cae en la regla de cercanía."""
        cabeceras = [("codigo", (2, 2)), ("nombre", (4, 4)), ("cantidad", (7, 7))]
        celdas = [
            aj.Celda(1, 1, 3, 3, "X1"),
            aj.Celda(1, 1, 4, 4, "NOMBRE"),
            aj.Celda(1, 1, 7, 7, 2),
        ]
        campos = aj.mapear_por_solapamiento(cabeceras, celdas)
        assert campos["codigo"].valor == "X1"
        assert campos["nombre"].valor == "NOMBRE"
        assert campos["cantidad"].valor == 2


# ─── Emparejamiento ──────────────────────────────────────────────────────────


def _det(codigo, nombre, cant, unit, vr_ent=None):
    return aj.ItemDetallado(
        fila=1,
        filas=[1],
        grupo="G",
        codigo=codigo,
        nombre=nombre,
        cantidad=cant,
        vr_unit=unit,
        vr_pac=0,
        vr_ent=vr_ent if vr_ent is not None else cant * unit,
    )


def _rep(codigo, desc, cant, recl, apr, glo, tipo="Procedimientos", n=1):
    filas = [
        aj.FilaGlosa(
            factura="HUS1",
            codigo=codigo,
            descripcion=desc,
            tipo_elemento=tipo,
            cant_reclamada=cant / n,
            valor_reclamado=recl / n,
            cant_aprobada=0,
            valor_aprobado=apr / n,
            valor_glosado=glo / n,
        )
        for _ in range(n)
    ]
    return aj.ItemReporte(codigo=codigo, descripcion=desc, tipo=tipo, filas=filas)


class TestEmparejar:
    def test_por_codigo_con_ceros_distintos(self):
        d = _det("19935303-4", "ACETAMINOFEN TAB X 500 MG", 8, 400)
        r = _rep("19935303-04", "ACETAMINOFEN 500 MG CAJA POR 100 TABLETAS", 8, 3200, 3200, 0)
        pares, sin = aj.emparejar([d], [r])
        assert pares[0][1] == "codigo" and not sin

    def test_por_descripcion_cuando_el_codigo_no_cruza(self):
        """Dispositivos: código INVIMA en el reporte, código interno en la factura."""
        d = _det("FMQ0042", "VENDA DE ALGODON 6 X 5 YARDAS", 4, 4600)
        r = _rep("2022DM-0008875-R1", "VENDA DE ALGODON 6 X 5 YARDAS", 4, 18400, 18400, 0)
        pares, _ = aj.emparejar([d], [r])
        assert pares[0][1] == "descripcion"

    def test_por_prefijo_cuando_el_reporte_agrega_sufijo(self):
        d = _det("FMO00778", "PLACA LCP TIBIA PROXIMAL 3.5", 2, 4709300)
        r = _rep(
            "",
            "PLACA LCP TIBIA PROXIMAL 3.5 MATERIAL DE OSTEOSINTESIS UNIDAD 01",
            2,
            9418600,
            9418600,
            0,
            tipo="Material de Osteosíntesis",
        )
        pares, _ = aj.emparejar([d], [r])
        assert pares[0][1] == "descripcion~"

    def test_no_empareja_por_valor_unitario_a_ciegas(self):
        """PROCALCITONINA y Calcitonina comparten valor unitario pero NO son el
        mismo servicio: antes se robaban la glosa entre sí."""
        d = _det("906841", "PROCALCITONINA SEMIAUTOMATIZADO O AUTOMATIZADO", 1, 255000)
        r = _rep("19181", "Calcitonina", 2, 510000, 0, 510000, n=2)
        pares, sin = aj.emparejar([d], [r])
        assert pares == {} and sin == [r]

    def test_varios_renglones_del_detallado_para_un_item_del_reporte(self):
        """Dos renglones de tornillos (1 y 4 unidades) = uno del reporte (5)."""
        d1 = _det("FMO00741", "TORNILLO BLOQUEADO DE 3.5 MM DEL 21 A 80 MM", 1, 169500)
        d2 = _det("FMO00782", "TORNILLO BLOQUEADO DE 3.5 MM DEL 21 A 80 MM", 4, 459700)
        d2.vr_ent = 1838800
        r = _rep(
            "",
            "TORNILLO BLOQUEADO DE 3.5 MM DEL 21 A 80 MM MATERIAL DE OSTEOSINTESIS",
            5,
            2008300,
            2008300,
            0,
            tipo="Material de Osteosíntesis",
        )
        pares, sin = aj.emparejar([d1, d2], [r])
        assert len(pares) == 2 and not sin
        assert all(c == "varios-a-uno" for _, c in pares.values())

    def test_varios_a_uno_por_codigo_aunque_la_cantidad_no_cuadre(self):
        """Una cirugía hecha dos veces: el detallado parte los honorarios del
        cirujano en dos renglones de $320.600 que suman exactamente los $641.200
        que reclama la única fila del reporte. Son 2 renglones contra 1 unidad,
        y aun así es el mismo concepto (caso HUS383283)."""
        d1 = _det("39010", "SERVICIOS PROFESIONALES DEL CIRUJANO", 1, 320600)
        d2 = _det("39010", "SERVICIOS PROFESIONALES DEL CIRUJANO", 1, 320600)
        r = _rep("39010", "Servicios profesionales del cirujano", 1, 641200, 293775, 347425)
        pares, sin = aj.emparejar([d1, d2], [r])
        assert len(pares) == 2 and not sin
        assert all(c == "varios-a-uno" for _, c in pares.values())

    def test_varios_a_uno_por_prefijo_sigue_exigiendo_la_cantidad(self):
        """Por prefijo NO alcanza con que el valor cuadre: a la descripción del
        reporte le basta con ser el COMIENZO de la del detallado, y un nombre
        genérico podría llevarse el grupo equivocado. Acá 'HEMOCULTIVO AEROBIO'
        es el principio de dos renglones que suman los $468.800 reclamados,
        pero son 2 renglones contra 5 unidades: no se empareja, se informa."""
        d1 = _det("FMQ1", "HEMOCULTIVO AEROBIO AUTOMATIZADO CADA MUESTRA", 1, 234400)
        d2 = _det("FMQ2", "HEMOCULTIVO AEROBIO AUTOMATIZADO CADA MUESTRA", 1, 234400)
        r = _rep("19514", "HEMOCULTIVO AEROBIO", 5, 468800, 468800, 0)
        assert aj._prefijo("HEMOCULTIVO AEROBIO AUTOMATIZADO CADA MUESTRA", "HEMOCULTIVO AEROBIO")
        pares, sin = aj.emparejar([d1, d2], [r])
        assert pares == {} and sin == [r]

    def test_desempata_por_cantidad_y_valor(self):
        d = _det("20084685-6", "HEPARINA ENOXAPARINA AMP X 40", 4, 12935)
        r1 = _rep("20084685-18", "ENOXAPARINA SODICA 40 MG", 1, 12935, 12935, 0)
        r2 = _rep("20084685-6", "ENOXAPARINA SODICA 40 MG PRELLENADAS", 4, 51740, 51740, 0)
        pares, _ = aj.emparejar([d], [r1, r2])
        assert pares[0][0] is r2


class TestDecidir:
    def test_aprobado_completo_se_quita(self):
        accion, *_ = aj.decidir(
            _det("X", "N", 1, 1000), _rep("X", "N", 1, 1000, 1000, 0), "ajustar", "conservar"
        )
        assert accion == "QUITADO"

    def test_glosado_completo_se_conserva(self):
        accion, cant, valor, _ = aj.decidir(
            _det("X", "N", 1, 1000), _rep("X", "N", 1, 1000, 0, 1000), "ajustar", "conservar"
        )
        assert (accion, cant, valor) == ("CONSERVADO", 1, 1000)

    def test_parcial_por_unidades_ajusta_cantidad(self):
        """Venda de gasa: 6 unidades, el reporte glosa 47.000 de 56.400 → 5."""
        item = _det("FMQ0046", "VENDA DE GASA", 6, 9400)
        rep = _rep("2016DM-315", "VENDA DE GASA", 6, 56400, 9400, 47000, n=2)
        accion, cant, valor, _ = aj.decidir(item, rep, "ajustar", "conservar")
        assert (accion, cant, valor) == ("AJUSTADO", 5.0, 47000)

    def test_parcial_por_valor_no_deja_la_cantidad_en_cero(self):
        """Glosa de $200 sobre un ítem de $95.600: la cantidad NO se redondea a
        0 (dejaría el renglón inservible); solo baja el valor."""
        item = _det("21102", "BRAZO PIERNA RODILLA", 1, 95600)
        rep = _rep("21102", "Brazo, pierna", 1, 95600, 95400, 200)
        accion, cant, valor, nota = aj.decidir(item, rep, "ajustar", "conservar")
        assert (accion, cant, valor) == ("AJUSTADO", 1, 200)
        assert "VALOR" in nota

    def test_avisa_si_el_reporte_glosa_mas_que_el_detallado(self):
        item = _det("21601", "PORTATILES", 4, 83500)
        rep = _rep("21601", "Portátiles", 12, 1002000, 0, 1002000)
        accion, cant, valor, nota = aj.decidir(item, rep, "ajustar", "conservar")
        assert (accion, valor) == ("CONSERVADO", 334000)
        assert "REVISAR" in nota

    def test_reclamado_cero_se_quita_con_aviso(self):
        item = _det("13580", "OSTEOSINTESIS EN TIBIA", 1, 3451800)
        rep = _rep("13580", "Osteosíntesis en tibia o peroné", 0, 0, 0, 0)
        accion, _, _, nota = aj.decidir(item, rep, "ajustar", "conservar")
        assert accion == "QUITADO" and "reclamado 0" in nota

    def test_sin_cruce_conserva_y_marca(self):
        accion, _, _, nota = aj.decidir(_det("X", "N", 1, 1000), None, "ajustar", "conservar")
        assert accion == "SIN_CRUCE" and "REVISAR" in nota

    def test_sin_cruce_quitar(self):
        accion, *_ = aj.decidir(_det("X", "N", 1, 1000), None, "ajustar", "quitar")
        assert accion == "QUITADO"

    def test_parcial_modo_conservar(self):
        item = _det("FMQ0046", "VENDA DE GASA", 6, 9400)
        rep = _rep("2016DM-315", "VENDA DE GASA", 6, 56400, 9400, 47000, n=2)
        accion, cant, valor, _ = aj.decidir(item, rep, "conservar", "conservar")
        assert (accion, cant, valor) == ("CONSERVADO", 6, 56400)


# ─── Borrado masivo de filas ─────────────────────────────────────────────────


class TestEliminarFilas:
    def test_corre_celdas_merges_y_altos(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        for fila in range(1, 11):
            ws.cell(row=fila, column=1, value=f"r{fila}")
        ws.merge_cells("A8:D8")
        ws.row_dimensions[8].height = 42
        aj.eliminar_filas(ws, {3})
        assert [str(r) for r in ws.merged_cells.ranges] == ["A7:D7"]
        assert ws.cell(row=7, column=1).value == "r8"
        assert ws.row_dimensions[7].height == 42
        assert ws.max_row == 9

    def test_merge_que_pierde_todas_sus_filas_desaparece(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        for fila in range(1, 6):
            ws.cell(row=fila, column=1, value=fila)
        ws.merge_cells("A2:C3")
        aj.eliminar_filas(ws, {2, 3})
        assert not list(ws.merged_cells.ranges)
        assert [ws.cell(row=f, column=1).value for f in range(1, 4)] == [1, 4, 5]


# ─── Corrida completa ────────────────────────────────────────────────────────


class TestCorridaCompleta:
    def _correr(self, archivos, tmp_path, extra=()):
        detallado, reporte, consolidado = archivos
        salida = tmp_path / "salida.xlsx"
        bitacora = tmp_path / "bitacora.csv"
        assert (
            aj.main(
                [
                    "--consolidado",
                    str(consolidado),
                    "--detallado",
                    str(detallado),
                    "--reporte-glosas",
                    str(reporte),
                    "--salida",
                    str(salida),
                    "--reporte-csv",
                    str(bitacora),
                    *extra,
                ]
            )
            == 0
        )
        return salida, bitacora

    def _texto(self, ws):
        return "\n".join(str(c.value) for f in ws.iter_rows() for c in f if c.value is not None)

    def test_deja_solo_lo_glosado(self, archivos, tmp_path):
        salida, _ = self._correr(archivos, tmp_path)
        ws = openpyxl.load_workbook(salida)["Sheet"]
        texto = self._texto(ws)

        # Membrete fuera y título cambiado.
        assert ws.cell(row=1, column=6).value == aj.TITULO_NUEVO
        for fuera in ("CUFE", "Bucaramanga", "Carrrera 33", "FACTURA ELECTRONICA DE VENTA"):
            assert fuera not in texto
        # La factura que no estaba en el consolidado desapareció.
        assert "HUS999999" not in texto
        assert "HUS352890" in texto
        # El pie del archivo se conserva.
        assert "LICENCIADO A" in texto

        # Quedan solo los dos grupos con ítems glosados.
        assert "CONSULTAS MEDICAS" in texto and "MATERIALES E INSUMOS" in texto
        for fuera in ("MEDICAMENTOS POS", "DERECHOS DE SALA", "IMAGENOLOGIA"):
            assert fuera not in texto
        for fuera in ("DICLOFENACO", "VENDA DE ALGODON", "VENDA ELASTICA", "INMOVILIZACION"):
            assert fuera not in texto
        assert "CONSULTA DE URGENCIAS" in texto and "VENDA DE GASA" in texto

    def test_ajusta_la_venda_de_gasa_sumando_las_dos_filas(self, archivos, tmp_path):
        salida, _ = self._correr(archivos, tmp_path)
        ws = openpyxl.load_workbook(salida)["Sheet"]
        fila = next(
            c.row
            for f in ws.iter_rows()
            for c in f
            if str(c.value or "").startswith("VENDA DE GASA")
        )
        assert ws.cell(row=fila, column=ITEM["cantidad"][0]).value == 5.0
        assert ws.cell(row=fila, column=ITEM["vr_ent"][0]).value == 47000

    def test_recalcula_totales_cantidad_de_items_y_letras(self, archivos, tmp_path):
        salida, _ = self._correr(archivos, tmp_path)
        ws = openpyxl.load_workbook(salida)["Sheet"]
        etiquetas = {}
        for f in ws.iter_rows():
            valores = [c.value for c in f if c.value is not None]
            if valores and isinstance(valores[0], str):
                etiquetas[valores[0]] = valores[1:]
        assert etiquetas["VALOR SUBTOTAL DE SERVICIOS PRESTADOS"] == [2, 132800]
        assert etiquetas["VALOR TOTAL ORDEN DE SERVICIO"] == [132800]
        assert etiquetas["TOTAL:"] == [aj.numero_a_letras(132800)]

    def test_bitacora_csv(self, archivos, tmp_path):
        _, bitacora = self._correr(archivos, tmp_path)
        lineas = bitacora.read_text(encoding="utf-8-sig").splitlines()
        assert lineas[0].startswith("FACTURA;HOJA;GRUPO")
        acciones = [ln.split(";")[10] for ln in lineas[1:]]
        assert acciones.count("QUITADO") == 6
        assert acciones.count("AJUSTADO") == 1
        assert acciones.count("CONSERVADO") == 1
        assert "ELIMINADA" in acciones  # la factura HUS999999

    def test_diagnostico_no_escribe_salida(self, archivos, tmp_path):
        detallado, reporte, consolidado = archivos
        salida = tmp_path / "no_debe_existir.xlsx"
        assert (
            aj.main(
                [
                    "--consolidado",
                    str(consolidado),
                    "--detallado",
                    str(detallado),
                    "--reporte-glosas",
                    str(reporte),
                    "--salida",
                    str(salida),
                    "--diagnostico",
                ]
            )
            == 0
        )
        assert not salida.exists()

    def test_modo_parcial_conservar(self, archivos, tmp_path):
        salida, _ = self._correr(archivos, tmp_path, extra=["--modo-parcial", "conservar"])
        ws = openpyxl.load_workbook(salida)["Sheet"]
        fila = next(
            c.row
            for f in ws.iter_rows()
            for c in f
            if str(c.value or "").startswith("VENDA DE GASA")
        )
        assert ws.cell(row=fila, column=ITEM["cantidad"][0]).value == 6.0

    def test_no_toca_los_archivos_originales(self, archivos, tmp_path):
        detallado, _, _ = archivos
        antes = detallado.read_bytes()
        self._correr(archivos, tmp_path)
        assert detallado.read_bytes() == antes

    def test_la_salida_se_puede_volver_a_leer(self, archivos, tmp_path):
        """El archivo ajustado sigue siendo un detallado válido."""
        salida, _ = self._correr(archivos, tmp_path)
        idx = aj.IndiceHoja(openpyxl.load_workbook(salida)["Sheet"])
        facturas = aj.segmentar_facturas(idx)
        assert len(facturas) == 1
        est = aj.detectar_estructura(idx, facturas[0])
        assert est is not None
        items = [i for b in aj.leer_bloques(idx, est) for i in b.items]
        assert len(items) == 2
        assert sum(i.vr_ent for i in items) == 132800
