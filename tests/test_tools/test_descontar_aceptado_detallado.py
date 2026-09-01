"""Tests del descontador de valores aceptados (tools/descontar_aceptado_detallado.py).

El caso guía es la factura HUS352890 del paquete 31068, la misma que trae el
documento del auditor: la consulta de urgencias queda **SE ACEPTA** por $2.400
y ese dinero tiene que salir del detallado sin desacomodar el resto.

El fixture reproduce la geometría real del detallado —cada dato dentro de un
rango combinado cuyos límites NO coinciden con los del encabezado— porque es
justo ahí donde se rompen los lectores ingenuos.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

openpyxl = pytest.importorskip("openpyxl")

import ajustar_detallado_glosas as aj  # noqa: E402
import descontar_aceptado_detallado as des  # noqa: E402

# ─── Geometría real de la hoja (columnas de cada rango combinado) ────────────

HDR = {
    "codigo": (3, 13),
    "nombre": (14, 29),
    "cantidad": (30, 33),
    "vr_unit": (34, 44),
    "vr_pac": (45, 52),
    "vr_ent": (53, 64),
}
ITEM = {
    "consecutivo": (5, 7),
    "codigo": (8, 13),
    "nombre": (14, 28),
    "cantidad": (29, 33),
    "vr_unit": (34, 43),
    "vr_pac": (44, 58),
    "vr_ent": (59, 64),
}
DESGLOSE = {  # los renglones sin consecutivo van corridos otra vez
    "codigo": (8, 13),
    "nombre": (14, 30),
    "cantidad": (31, 33),
    "vr_unit": (34, 45),
    "vr_pac": (46, 58),
    "vr_ent": (59, 64),
}
TOT_ETIQUETA, TOT_CANT, TOT_VALOR = (6, 31), (32, 53), (54, 66)

ETIQUETAS_HDR = {
    "codigo": "CÓDIGO",
    "nombre": "NOMBRE",
    "cantidad": "CANT",
    "vr_unit": "VR UNIT",
    "vr_pac": "VR PAC",
    "vr_ent": "VR ENT",
}

# La HUS352890 tal como sale del ajustador: solo lo que quedó glosado.
GRUPOS_HUS352890 = [
    ("CONSULTAS MEDICAS", [("39145", "CONSULTA DE URGENCIAS", 1, 85800)]),
    ("MATERIALES E INSUMOS", [("FMQ0046", "VENDA DE GASA 6 X 5 YARDAS", 5, 9400)]),
]


def _poner(ws, fila, span, valor, alto=1):
    ws.cell(row=fila, column=span[0], value=valor)
    if span[1] > span[0] or alto > 1:
        ws.merge_cells(
            start_row=fila, start_column=span[0], end_row=fila + alto - 1, end_column=span[1]
        )


def _poner_desglose(ws, fila: int, filas) -> int:
    """Renglones SIN consecutivo. Devuelve la fila siguiente libre."""
    for codigo, nombre, cant, unit in filas:
        _poner(ws, fila, DESGLOSE["codigo"], codigo)
        _poner(ws, fila, DESGLOSE["nombre"], nombre)
        _poner(ws, fila, DESGLOSE["cantidad"], float(cant))
        _poner(ws, fila, DESGLOSE["vr_unit"], float(unit))
        _poner(ws, fila, DESGLOSE["vr_pac"], 0.0)
        _poner(ws, fila, DESGLOSE["vr_ent"], float(cant * unit))
        fila += 1
    return fila


def escribir_detallado(
    ruta: Path,
    factura: str,
    grupos=GRUPOS_HUS352890,
    desglose=(),
    subtotal=None,
    n_items=None,
) -> Path:
    """Un detallado de UNA sola factura, como los del zip por factura.

    `desglose` son renglones sin consecutivo (honorarios de cirujano, derechos
    de sala) que cuelgan del último ítem escrito. `subtotal` permite forzar el
    valor que trae el archivo, para probar las dos convenciones del formato.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet"
    _poner(ws, 1, (6, 26), aj.TITULO_NUEVO)
    _poner(ws, 1, (27, 49), factura)
    _poner(ws, 3, (6, 8), "Paciente")
    _poner(ws, 3, (17, 47), "JUAN ESTEBAN GARCIA RESTREPO")

    fila = 6
    for campo, span in HDR.items():
        _poner(ws, fila, span, ETIQUETAS_HDR[campo])

    fila += 1
    n = 0
    for titulo, items in grupos:
        fila += 1
        _poner(ws, fila, (2, 67), titulo)
        fila += 2  # el renglón en blanco que trae el formato
        for codigo, nombre, cant, unit, *resto in items:
            n += 1
            _poner(ws, fila, ITEM["consecutivo"], n)
            _poner(ws, fila, ITEM["codigo"], codigo)
            _poner(ws, fila, ITEM["nombre"], nombre)
            _poner(ws, fila, ITEM["cantidad"], float(cant))
            _poner(ws, fila, ITEM["vr_unit"], float(unit))
            _poner(ws, fila, ITEM["vr_pac"], 0.0)
            _poner(ws, fila, ITEM["vr_ent"], float(cant * unit))
            fila += 1
            # Un procedimiento quirúrgico puede traer su desglose colgando.
            fila = _poner_desglose(ws, fila, resto[0] if resto else ())
    fila = _poner_desglose(ws, fila, desglose)

    if subtotal is None:
        subtotal = sum(it[2] * it[3] for _, items in grupos for it in items)
    fila += 2
    for etiqueta, valor in (
        (aj.MARCA_SUBTOTAL, float(subtotal)),
        ("VALOR CUOTA COPAGO Y/0 CUOTA MODERADORA", 0.0),
        (aj.MARCA_TOTAL_ORDEN, float(subtotal)),
    ):
        _poner(ws, fila, TOT_ETIQUETA, etiqueta)
        if etiqueta == aj.MARCA_SUBTOTAL:
            _poner(ws, fila, TOT_CANT, n if n_items is None else n_items)
        _poner(ws, fila, TOT_VALOR, valor)
        fila += 1
    _poner(ws, fila, (6, 10), "TOTAL:")
    _poner(ws, fila, (11, 66), aj.numero_a_letras(subtotal))
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return ruta


ENCABEZADO_MACRO = {
    des.COL_FACTURA: "NUMERO FACTURA",
    des.COL_CANT_RECLAMADA: "CANTIDAD RECLAMADA",
    des.COL_VALOR_RECLAMADO: "VALOR RECLAMADO",
    des.COL_CANT_APROBADA: "CANTIDAD APROBADA",
    des.COL_VALOR_APROBADO: "VALOR APROBADO",
    des.COL_VALOR_GLOSADO: "VALOR GLOSADO",
    des.COL_TIPO_ELEMENTO: "TIPO ELEMENTO",
    des.COL_COD_ELEMENTO: "COD ELEMENTO",
    des.COL_DESC_ELEMENTO: "DESCRIPCION ELEMENTO",
    des.COL_DESC_GLOSA: "DESCRIPCION GLOSA",
    des.COL_OBSERVACION: "OBSERVACION",
    des.COL_VALOR_ACEPTADO: "VALOR ACEPTADO",
}


def escribir_macro(ruta: Path, filas) -> Path:
    """La macro de respuesta: una fila por causal, con su VALOR ACEPTADO."""
    wb = openpyxl.Workbook()
    ws = wb.active
    for col, texto in ENCABEZADO_MACRO.items():
        ws.cell(row=1, column=col, value=texto)
    for i, f in enumerate(filas, start=2):
        for col, valor in f.items():
            ws.cell(row=i, column=col, value=valor)
    wb.save(ruta)
    return ruta


def fila_macro(
    factura,
    codigo,
    descripcion,
    *,
    tipo="Procedimientos",
    cant=1,
    reclamado=0,
    aprobado=0,
    glosado=0,
    aceptado=0,
    glosa="",
    observacion="",
):
    return {
        des.COL_FACTURA: factura,
        des.COL_CANT_RECLAMADA: cant,
        des.COL_VALOR_RECLAMADO: reclamado,
        des.COL_CANT_APROBADA: 0,
        des.COL_VALOR_APROBADO: aprobado,
        des.COL_VALOR_GLOSADO: glosado,
        des.COL_TIPO_ELEMENTO: tipo,
        des.COL_COD_ELEMENTO: codigo,
        des.COL_DESC_ELEMENTO: descripcion,
        des.COL_DESC_GLOSA: glosa,
        des.COL_OBSERVACION: observacion,
        des.COL_VALOR_ACEPTADO: aceptado,
    }


@pytest.fixture()
def caso_hus352890(tmp_path: Path):
    """(carpeta de detallados, macro) del ejemplo del auditor."""
    carpeta = tmp_path / "por_factura"
    escribir_detallado(carpeta / "HUS352890.xlsx", "HUS352890")
    macro = escribir_macro(
        tmp_path / "macro.xlsx",
        [
            fila_macro(
                "HUS352890",
                "39145",
                "Consulta de urgencias",
                cant=1,
                reclamado=85800,
                glosado=85800,
                aceptado=2400,
                glosa="3202- La consulta no esta justificada",
                observacion="SE ACEPTA",
            ),
            fila_macro(
                "HUS352890",
                "2016DM-0000315-R2",
                "VENDA DE GASA 6 X 5 YARDAS",
                tipo="Dispositivos Médicos",
                cant=5,
                reclamado=47000,
                glosado=47000,
                aceptado=0,
                glosa="3106- Soporte de material ausente o incompleto",
                observacion="SE OBJETA",
            ),
        ],
    )
    return carpeta, macro


# ─── Lectura de la macro ─────────────────────────────────────────────────────


class TestLeerAceptados:
    def test_solo_las_filas_con_valor_aceptado(self, caso_hus352890):
        _, macro = caso_hus352890
        aceptados, _ = des.leer_aceptados(macro)
        assert list(aceptados) == ["352890"]  # la clave va sin el HUS ni los ceros
        assert len(aceptados["352890"]) == 1
        fila = aceptados["352890"][0]
        assert fila.codigo == "39145"
        # El aceptado viaja en valor_glosado: es lo que se le descuenta al ítem.
        assert fila.valor_glosado == 2400

    def test_ignora_las_filas_que_no_son_de_una_factura(self, tmp_path):
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [
                fila_macro("TOTAL GENERAL", "", "", aceptado=999999),
                fila_macro("HUS400001", "39145", "Consulta", aceptado=1000),
            ],
        )
        assert list(des.leer_aceptados(macro)[0]) == ["400001"]

    def test_suma_las_filas_repetidas_del_mismo_item(self, tmp_path):
        """El reporte del ADRES abre una fila por causal: 2 causales, un ítem."""
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [
                fila_macro("HUS1", "39145", "Consulta", aceptado=1000, glosa="3202- Causal A"),
                fila_macro("HUS1", "39145", "Consulta", aceptado=500, glosa="4506- Causal B"),
            ],
        )
        items = des._agrupar(des.leer_aceptados(macro)[0]["1"])
        assert len(items) == 1
        assert items[0].valor_glosado == 1500
        assert items[0].causales == "3202- Causal A | 4506- Causal B"


class TestLoQueNoSeDescuenta:
    """Dos filas de la macro que NO se pueden usar, por más que traigan valor."""

    def test_una_fila_se_objeta_no_toca_el_detallado(self, tmp_path):
        """El equipo la objetó: ese servicio se sigue reclamando completo."""
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [
                fila_macro(
                    "HUS1",
                    "21101",
                    "Mano, dedos, puño",
                    reclamado=73500,
                    aceptado=10000,
                    observacion="SE OBJETA",
                )
            ],
        )
        aceptados, descartes = des.leer_aceptados(macro)
        assert aceptados == {}
        assert "SE OBJETA" in descartes["1"][0]
        assert "se sigue reclamando" in descartes["1"][0]

    def test_una_fila_se_subsana_tampoco(self, tmp_path):
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [
                fila_macro(
                    "HUS1",
                    "39145",
                    "Consulta",
                    reclamado=85800,
                    aceptado=800,
                    observacion="SE SUBSANA CON SOPORTE",
                )
            ],
        )
        assert des.leer_aceptados(macro)[0] == {}

    def test_no_se_puede_aceptar_mas_de_lo_reclamado(self, tmp_path):
        """La columna del Excel quedó corrida: el valor es de otra fila.

        Es lo que pasó en la HUS396996 del paquete 31068."""
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [fila_macro("HUS1", "21101", "Mano, dedos, puño", reclamado=73500, aceptado=758700)],
        )
        aceptados, descartes = des.leer_aceptados(macro)
        assert aceptados == {}
        assert "no se puede aceptar más de lo cobrado" in descartes["1"][0].lower()

    def test_sin_valor_reclamado_no_se_puede_juzgar_y_pasa(self, tmp_path):
        """Sin con qué comparar, la fila se usa: el bot no adivina."""
        macro = escribir_macro(
            tmp_path / "m.xlsx",
            [fila_macro("HUS1", "39145", "Consulta", reclamado=0, aceptado=2400)],
        )
        assert des.leer_aceptados(macro)[0]["1"][0].valor_glosado == 2400

    def test_el_aviso_llega_a_la_factura_y_a_la_bitacora(self, tmp_path):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS400010.xlsx", "HUS400010")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [
                fila_macro(
                    "HUS400010",
                    "39145",
                    "Consulta de urgencias",
                    reclamado=85800,
                    aceptado=2400,
                    observacion="SE OBJETA",
                )
            ],
        )
        bitacora = tmp_path / "b.csv"
        salida = tmp_path / "out"
        res = _correr(carpeta, macro, salida, bitacora)[0]
        assert res.descontado == 0
        assert any("OJO CON LA MACRO" in a for a in res.sin_cruzar)
        assert "OJO CON LA MACRO" in bitacora.read_text(encoding="utf-8-sig")
        # El servicio queda intacto: el hospital lo sigue reclamando.
        ws = openpyxl.load_workbook(salida / "HUS400010.xlsx")["Sheet"]
        fila = _fila_de(salida / "HUS400010.xlsx", "CONSULTA DE URGENCIAS")
        assert ws.cell(row=fila, column=ITEM["vr_ent"][0]).value == 85800

    def test_la_factura_sin_detallado_no_desaparece(self, tmp_path):
        """Si la macro le acepta plata a una factura que no está en la carpeta,
        esa plata tiene que quedar anotada: si no, se sigue reclamando sin que
        nadie se entere."""
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS400011.xlsx", "HUS400011")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [fila_macro("HUS999888", "39145", "Consulta", reclamado=85800, aceptado=10400)],
        )
        bitacora = tmp_path / "b.csv"
        resultados = _correr(carpeta, macro, tmp_path / "out", bitacora)
        sin = [r for r in resultados if r.estado == "SIN_DETALLADO"]
        assert len(sin) == 1
        assert sin[0].factura == "HUS999888"
        assert sin[0].aceptado_macro == 10400
        assert "HUS999888" in bitacora.read_text(encoding="utf-8-sig")


# ─── El subtotal del archivo manda ───────────────────────────────────────────


class TestQueRenglonesSuman:
    """Los renglones sin consecutivo a veces ya están dentro del procedimiento
    que tienen encima y a veces son una cirugía aparte. Se decide acumulando."""

    class _It:
        def __init__(self, vr_ent, desglose):
            self.vr_ent = vr_ent
            self.desglose = desglose

    def _items(self, *pares):
        return [self._It(v, d) for v, d in pares]

    def test_el_desglose_que_completa_el_procedimiento_no_suma(self):
        items = self._items((1_000_000, False), (600_000, True), (400_000, True))
        cuenta, cuadra = des.filas_que_cuentan(items, 1_000_000)
        assert cuenta == [True, False, False] and cuadra

    def test_la_segunda_cirugia_si_suma(self):
        """El caso HUS388262: bajo el procedimiento van los honorarios de ESA
        cirugía (que no suman) y enseguida los de otra (que sí)."""
        items = self._items(
            (1_000_000, False),  # el procedimiento
            (600_000, True),  # su desglose…
            (400_000, True),  # …que acá completa el millón
            (300_000, True),  # otra cirugía: no está dentro de nadie
            (200_000, True),
        )
        cuenta, cuadra = des.filas_que_cuentan(items, 1_500_000)
        assert cuenta == [True, False, False, True, True] and cuadra

    def test_un_desglose_sin_procedimiento_encima_suma(self):
        items = self._items((300_000, True), (200_000, True), (50_000, False))
        cuenta, cuadra = des.filas_que_cuentan(items, 550_000)
        assert cuenta == [True, True, True] and cuadra

    def test_si_nunca_cuadra_con_el_padre_los_renglones_cuentan(self):
        items = self._items((1_000_000, False), (300_000, True), (200_000, True))
        cuenta, cuadra = des.filas_que_cuentan(items, 1_500_000)
        assert cuenta == [True, True, True] and cuadra

    def test_sin_renglones_de_desglose_cuentan_todos(self):
        items = self._items((500, False), (300, False))
        cuenta, cuadra = des.filas_que_cuentan(items, 800)
        assert cuenta == [True, True] and cuadra

    def test_cuando_el_modelo_no_reproduce_el_subtotal_avisa(self):
        """La comprobación de cierre: si no se puede explicar el subtotal del
        archivo, solo se dan por seguros los renglones numerados."""
        items = self._items((1_000_000, False), (600_000, True), (400_000, True))
        cuenta, cuadra = des.filas_que_cuentan(items, 1_234_567)
        assert cuenta == [True, False, False]
        assert not cuadra


# ─── Descuento sobre una factura ─────────────────────────────────────────────


def _correr(carpeta: Path, macro: Path, salida: Path, bitacora: Path | None = None):
    return des.procesar(str(carpeta), macro, salida, bitacora)


def _valores(ruta: Path) -> dict[str, list]:
    """{primer texto de la fila: [valores siguientes]} para leer los totales."""
    ws = openpyxl.load_workbook(ruta)["Sheet"]
    salida = {}
    for fila in ws.iter_rows():
        valores = [c.value for c in fila if c.value is not None]
        if valores and isinstance(valores[0], str):
            salida[valores[0]] = valores[1:]
    return salida


def _fila_de(ruta: Path, texto: str) -> int:
    ws = openpyxl.load_workbook(ruta)["Sheet"]
    return next(c.row for f in ws.iter_rows() for c in f if str(c.value or "").startswith(texto))


class TestEjemploDelAuditor:
    """HUS352890: $132.800 − $2.400 aceptados = $130.400."""

    def test_baja_el_valor_del_servicio_aceptado(self, caso_hus352890, tmp_path):
        carpeta, macro = caso_hus352890
        salida = tmp_path / "out"
        res = _correr(carpeta, macro, salida)[0]
        assert res.estado == "AJUSTADA"
        assert (res.subtotal_antes, res.subtotal_despues) == (132800, 130400)
        assert res.descontado == 2400

        ruta = salida / "HUS352890.xlsx"
        ws = openpyxl.load_workbook(ruta)["Sheet"]
        fila = _fila_de(ruta, "CONSULTA DE URGENCIAS")
        assert ws.cell(row=fila, column=ITEM["vr_ent"][0]).value == 83400
        # El VR UNIT se recalcula para que cuadre con la cantidad.
        assert ws.cell(row=fila, column=ITEM["vr_unit"][0]).value == 83400
        assert ws.cell(row=fila, column=ITEM["cantidad"][0]).value == 1.0

    def test_no_toca_lo_que_se_objeto(self, caso_hus352890, tmp_path):
        carpeta, macro = caso_hus352890
        salida = tmp_path / "out"
        _correr(carpeta, macro, salida)
        ruta = salida / "HUS352890.xlsx"
        ws = openpyxl.load_workbook(ruta)["Sheet"]
        fila = _fila_de(ruta, "VENDA DE GASA")
        assert ws.cell(row=fila, column=ITEM["vr_ent"][0]).value == 47000
        assert ws.cell(row=fila, column=ITEM["vr_unit"][0]).value == 9400

    def test_recalcula_subtotal_total_y_letras(self, caso_hus352890, tmp_path):
        carpeta, macro = caso_hus352890
        salida = tmp_path / "out"
        _correr(carpeta, macro, salida)
        valores = _valores(salida / "HUS352890.xlsx")
        assert valores[aj.MARCA_SUBTOTAL] == [2, 130400]
        assert valores[aj.MARCA_TOTAL_ORDEN] == [130400]
        assert valores["TOTAL:"] == [aj.numero_a_letras(130400)]

    def test_cruza_aunque_el_codigo_de_la_macro_sea_otro(self, tmp_path):
        """El detallado dice FMQ0046 y la macro 2016DM-0000315-R2: cruza por
        descripción, que es como cruzan de verdad los dispositivos médicos."""
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS352890.xlsx", "HUS352890")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [
                fila_macro(
                    "HUS352890",
                    "2016DM-0000315-R2",
                    "VENDA DE GASA 6 X 5 YARDAS",
                    tipo="Dispositivos Médicos",
                    cant=5,
                    reclamado=47000,
                    aceptado=9400,
                )
            ],
        )
        res = _correr(carpeta, macro, tmp_path / "out")[0]
        assert res.descuentos[0].codigo == "FMQ0046"
        assert res.descuentos[0].cruce == "descripcion"
        assert res.subtotal_despues == 123400

    def test_no_modifica_el_archivo_original(self, caso_hus352890, tmp_path):
        carpeta, macro = caso_hus352890
        antes = (carpeta / "HUS352890.xlsx").read_bytes()
        _correr(carpeta, macro, tmp_path / "out")
        assert (carpeta / "HUS352890.xlsx").read_bytes() == antes

    def test_la_salida_se_puede_volver_a_leer(self, caso_hus352890, tmp_path):
        """El archivo descontado sigue siendo un detallado válido."""
        carpeta, macro = caso_hus352890
        salida = tmp_path / "out"
        _correr(carpeta, macro, salida)
        idx = aj.IndiceHoja(openpyxl.load_workbook(salida / "HUS352890.xlsx")["Sheet"])
        fac = aj.segmentar_facturas(idx)[0]
        est = aj.detectar_estructura(idx, fac)
        items = [i for b in aj.leer_bloques(idx, est) for i in b.items]
        assert sum(i.vr_ent for i in items) == 130400


class TestSinNadaQueDescontar:
    def test_la_factura_se_copia_igual(self, tmp_path):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS400001.xlsx", "HUS400001")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [fila_macro("HUS999999", "39145", "Consulta", aceptado=1000)],
        )
        salida = tmp_path / "out"
        res = _correr(carpeta, macro, salida)[0]
        assert res.estado == "SIN_ACEPTADO"
        assert res.subtotal_antes == res.subtotal_despues == 132800
        assert res.descontado == 0
        assert (salida / "HUS400001.xlsx").exists()
        assert _valores(salida / "HUS400001.xlsx")[aj.MARCA_SUBTOTAL] == [2, 132800]

    def test_las_filas_en_cero_no_descuentan(self, tmp_path):
        """SE OBJETA y SE SUBSANA se siguen reclamando completas."""
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS400002.xlsx", "HUS400002")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [
                fila_macro(
                    "HUS400002",
                    "39145",
                    "Consulta de urgencias",
                    aceptado=0,
                    observacion="SE OBJETA",
                )
            ],
        )
        res = _correr(carpeta, macro, tmp_path / "out")[0]
        assert res.estado == "SIN_ACEPTADO" and res.descontado == 0


class TestAvisos:
    def test_el_aceptado_mayor_que_el_servicio_no_deja_negativos(self, tmp_path):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS400003.xlsx", "HUS400003")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [fila_macro("HUS400003", "39145", "Consulta de urgencias", cant=1, aceptado=100000)],
        )
        salida = tmp_path / "out"
        res = _correr(carpeta, macro, salida)[0]
        assert res.descuentos[0].vr_ent_despues == 0
        assert "mayor que el valor del servicio" in res.sin_cruzar[0]
        # Se descuenta hasta cero, nunca por debajo: 132.800 − 85.800.
        assert res.subtotal_despues == 47000
        assert _valores(salida / "HUS400003.xlsx")[aj.MARCA_TOTAL_ORDEN] == [47000]

    def test_avisa_lo_aceptado_que_no_tiene_item_en_el_detallado(self, tmp_path):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS400004.xlsx", "HUS400004")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [fila_macro("HUS400004", "99999", "SERVICIO QUE NO ESTA", cant=1, aceptado=5000)],
        )
        res = _correr(carpeta, macro, tmp_path / "out")[0]
        assert res.descontado == 0
        assert "sin ítem en el detallado" in res.sin_cruzar[0]

    def test_un_excel_dañado_no_tumba_el_lote(self, tmp_path):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS400005.xlsx", "HUS400005")
        (carpeta / "roto.xlsx").write_bytes(b"esto no es un excel")
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [fila_macro("HUS400005", "39145", "Consulta de urgencias", aceptado=800)],
        )
        resultados = _correr(carpeta, macro, tmp_path / "out")
        estados = {r.factura: r.estado for r in resultados}
        assert estados["HUS400005"] == "AJUSTADA"
        assert estados["roto"] == "ERROR"


class TestDesgloseEnUnaFacturaReal:
    """Las dos convenciones del formato, sobre la misma factura."""

    GRUPOS = [("PROCEDIMIENTOS QUIRURGICOS", [("13580", "OSTEOSINTESIS EN TIBIA", 1, 1000000)])]
    HONORARIOS = [("39005", "HONORARIOS CIRUJANO", 1, 600000), ("39209", "AYUDANTIA", 1, 400000)]

    def _macro(self, tmp_path, factura):
        return escribir_macro(
            tmp_path / "macro.xlsx",
            [fila_macro(factura, "39005", "HONORARIOS CIRUJANO", cant=1, aceptado=100000)],
        )

    def test_cuando_el_desglose_no_suma_el_subtotal_solo_baja_lo_del_padre(self, tmp_path):
        """Subtotal $1.000.000: los honorarios ya están dentro del principal, así
        que descontarles $100.000 NO puede tocar el subtotal."""
        carpeta = tmp_path / "in"
        escribir_detallado(
            carpeta / "HUS500001.xlsx",
            "HUS500001",
            grupos=self.GRUPOS,
            desglose=self.HONORARIOS,
            subtotal=1_000_000,
        )
        salida = tmp_path / "out"
        res = _correr(carpeta, self._macro(tmp_path, "HUS500001"), salida)[0]
        assert res.subtotal_antes == 1_000_000
        assert res.subtotal_despues == 1_000_000
        # El renglón sí baja: el auditor tiene que ver el descuento.
        ruta = salida / "HUS500001.xlsx"
        ws = openpyxl.load_workbook(ruta)["Sheet"]
        fila = _fila_de(ruta, "HONORARIOS CIRUJANO")
        assert ws.cell(row=fila, column=DESGLOSE["vr_ent"][0]).value == 500000

    # La forma de la HUS388262: dos cirugías. Bajo el segundo procedimiento van
    # PRIMERO los honorarios de esa cirugía —que completan su valor y por eso no
    # suman— y ENSEGUIDA los de una cirugía aparte, que sí suman.
    DOS_CIRUGIAS = [
        (
            "PROCEDIMIENTOS QUIRURGICOS",
            [
                ("13580", "OSTEOSINTESIS EN TIBIA", 1, 1000000, HONORARIOS),
                (
                    "13580",
                    "OSTEOSINTESIS EN PERONE",
                    1,
                    2000000,
                    [
                        ("39005", "HONORARIOS CIRUJANO", 1, 1200000),
                        ("39209", "AYUDANTIA", 1, 800000),
                        ("39008", "HONORARIOS CIRUJANO 2", 1, 300000),
                        ("39212", "DERECHOS DE SALA 2", 1, 200000),
                    ],
                ),
            ],
        )
    ]

    def test_la_segunda_cirugia_si_baja_el_subtotal(self, tmp_path):
        """Los $500.000 de la cirugía aparte SÍ están sumados en el subtotal, así
        que aceptarle plata a ese renglón tiene que bajarlo.

        Es el defecto que traía la HUS388262: quedó $1.400.050 de más."""
        carpeta = tmp_path / "in"
        escribir_detallado(
            carpeta / "HUS500002.xlsx",
            "HUS500002",
            grupos=self.DOS_CIRUGIAS,
            subtotal=3_500_000,  # 1.000.000 + 2.000.000 + los 500.000 de la otra
        )
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [fila_macro("HUS500002", "39008", "HONORARIOS CIRUJANO 2", cant=1, aceptado=100000)],
        )
        salida = tmp_path / "out"
        res = _correr(carpeta, macro, salida)[0]
        assert res.subtotal_antes == 3_500_000
        assert res.subtotal_despues == 3_400_000
        assert not res.sin_cruzar
        assert _valores(salida / "HUS500002.xlsx")[aj.MARCA_TOTAL_ORDEN] == [3_400_000]

    def test_los_honorarios_del_procedimiento_siguen_sin_bajar_el_subtotal(self, tmp_path):
        """En la misma factura, el otro renglón: aceptarle plata al cirujano de
        la PRIMERA cirugía no mueve el subtotal, porque ya está dentro."""
        carpeta = tmp_path / "in"
        escribir_detallado(
            carpeta / "HUS500004.xlsx",
            "HUS500004",
            grupos=self.DOS_CIRUGIAS,
            subtotal=3_500_000,
        )
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [fila_macro("HUS500004", "39209", "AYUDANTIA", cant=1, aceptado=50000)],
        )
        res = _correr(carpeta, macro, tmp_path / "out")[0]
        assert res.subtotal_despues == 3_500_000

    def test_si_no_se_puede_explicar_el_subtotal_avisa_y_no_lo_inventa(self, tmp_path):
        """La comprobación de cierre: con un subtotal que no cuadra con ningún
        modelo, solo se descuentan los servicios numerados y queda el aviso."""
        carpeta = tmp_path / "in"
        escribir_detallado(
            carpeta / "HUS500005.xlsx",
            "HUS500005",
            grupos=self.GRUPOS,
            desglose=self.HONORARIOS,
            subtotal=1_234_567,
        )
        res = _correr(carpeta, self._macro(tmp_path, "HUS500005"), tmp_path / "out")[0]
        assert res.subtotal_despues == 1_234_567
        assert any("REVISAR A MANO" in a for a in res.sin_cruzar)

    def test_el_subtotal_nunca_se_recalcula_desde_cero(self, tmp_path):
        """Si el archivo trae un subtotal que no es la suma de los renglones, se
        respeta: el bueno es el del archivo, no el que calcularíamos nosotros."""
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS500003.xlsx", "HUS500003", subtotal=140_000)
        macro = escribir_macro(
            tmp_path / "macro.xlsx",
            [fila_macro("HUS500003", "39145", "Consulta de urgencias", aceptado=2400)],
        )
        res = _correr(carpeta, macro, tmp_path / "out")[0]
        assert res.subtotal_antes == 140_000
        assert res.subtotal_despues == 137_600  # 140.000 − 2.400, no 132.800 − 2.400


# ─── Bitácora y corrida completa ─────────────────────────────────────────────


class TestBitacora:
    def test_una_linea_por_descuento_con_el_cuadre(self, caso_hus352890, tmp_path):
        carpeta, macro = caso_hus352890
        bitacora = tmp_path / "descuentos.csv"
        _correr(carpeta, macro, tmp_path / "out", bitacora)
        lineas = bitacora.read_text(encoding="utf-8-sig").splitlines()
        assert lineas[0].startswith("FACTURA;ESTADO;SUBTOTAL_ANTES")
        campos = lineas[1].split(";")
        assert campos[0] == "HUS352890"
        assert campos[1] == "AJUSTADA"
        assert campos[4] == "2400.00"  # descontado
        assert campos[5] == "2400.00"  # aceptado en la macro
        assert campos[6] == "SI"  # cuadra
        assert campos[7] == "39145"
        assert campos[13] == "3202- La consulta no esta justificada"

    def test_las_facturas_sin_descuento_tambien_quedan_en_la_bitacora(self, tmp_path):
        carpeta = tmp_path / "in"
        escribir_detallado(carpeta / "HUS400006.xlsx", "HUS400006")
        macro = escribir_macro(tmp_path / "macro.xlsx", [])
        bitacora = tmp_path / "descuentos.csv"
        _correr(carpeta, macro, tmp_path / "out", bitacora)
        lineas = bitacora.read_text(encoding="utf-8-sig").splitlines()
        assert len(lineas) == 2
        assert lineas[1].split(";")[1] == "SIN_ACEPTADO"


class TestCLI:
    def test_corrida_por_linea_de_comandos(self, caso_hus352890, tmp_path, capsys):
        carpeta, macro = caso_hus352890
        salida = tmp_path / "out"
        bitacora = tmp_path / "b.csv"
        assert (
            des.main(
                [
                    "--detallados",
                    str(carpeta),
                    "--macro",
                    str(macro),
                    "--salida",
                    str(salida),
                    "--bitacora",
                    str(bitacora),
                ]
            )
            == 0
        )
        texto = capsys.readouterr().out
        assert "Total descontado      : $2.400" in texto
        assert "TOTAL FINAL           : $130.400" in texto
        assert (salida / "HUS352890.xlsx").exists() and bitacora.exists()

    def test_carpeta_vacia_avisa_y_no_revienta(self, tmp_path, caplog):
        vacia = tmp_path / "vacia"
        vacia.mkdir()
        macro = escribir_macro(tmp_path / "macro.xlsx", [])
        assert (
            des.main(
                ["--detallados", str(vacia), "--macro", str(macro), "--salida", str(tmp_path / "o")]
            )
            == 1
        )
        assert "No se encontró ningún Excel" in caplog.text

    def test_ignora_los_temporales_de_excel(self, caso_hus352890, tmp_path):
        carpeta, macro = caso_hus352890
        (carpeta / "~$HUS352890.xlsx").write_bytes(b"temporal de excel abierto")
        assert len(_correr(carpeta, macro, tmp_path / "out")) == 1


class TestMoneda:
    """El bot no trae su propio formateador: usa el de `_dinero`."""

    @pytest.mark.parametrize(
        "valor,esperado",
        [(0, "$0"), (2400, "$2.400"), (130400, "$130.400"), (627442242, "$627.442.242")],
    )
    def test_formato_de_moneda(self, valor, esperado):
        assert des.a_texto(valor) == esperado
