"""
Pruebas de nucleo.msg_tools (correos .msg de relación de pagos -> Excel).

No requieren archivos .msg reales: `leer_adjuntos_pago` se mockea (igual que
en test_ai_tools.py con las llamadas HTTP) porque no hay forma de fabricar un
.msg sintético válido sin la función de guardado de extract_msg, que este
módulo deliberadamente no usa (ver docstring de msg_tools.py). La lógica que
sí procesa datos reales (lectura del adjunto Excel, consolidación, marcado de
duplicados) se prueba con datos genuinos.
"""

import io
import os
import sys
import zipfile

import pytest

SUITE = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "tools", "suite_cartera_hus")
)
if SUITE not in sys.path:
    sys.path.insert(0, SUITE)

openpyxl = pytest.importorskip("openpyxl")

from nucleo import msg_tools  # noqa: E402


def _silencio(_):
    pass


def _xlsx_bytes(filas, encabezados=None):
    """Arma un adjunto Excel en memoria con encabezado en la fila 1."""
    encabezados = encabezados or [
        "NIT",
        "IPS",
        "NUM FACTURA",
        "FECHA DE PAGO",
        "COMPROBANTE DE EGRESO",
        "VALOR PAGADO",
    ]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(encabezados)
    for fila in filas:
        ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


FECHA = __import__("datetime").datetime(2026, 4, 10)


# ------------------------------------------------------------- import/stub


def test_extract_msg_importa_pese_a_dependencia_rota():
    """red-black-tree-mod no está instalado; el stub debe permitir el import."""
    assert "red_black_dict_mod" in sys.modules
    assert msg_tools.extract_msg is not None


def test_exigir_extract_msg_mensaje_claro(monkeypatch):
    monkeypatch.setattr(msg_tools, "extract_msg", None)
    with pytest.raises(RuntimeError, match="extract-msg"):
        msg_tools._exigir_extract_msg()


# ------------------------------------------------------------- lectura xlsx


def test_filas_desde_adjunto_preserva_tipos():
    datos = _xlsx_bytes([[900006037, "IPS X", "HUS0001", FECHA, "CE001", 100000]])
    encabezados, filas = msg_tools.filas_desde_adjunto(datos, "adjunto.xlsx")
    assert encabezados[0] == "NIT"
    assert len(filas) == 1
    fila = filas[0]
    assert isinstance(fila["NIT"], int) and fila["NIT"] == 900006037
    assert isinstance(fila["VALOR PAGADO"], (int, float)) and fila["VALOR PAGADO"] == 100000
    # la fecha debe seguir siendo un objeto fecha/hora, NUNCA texto
    assert hasattr(fila["FECHA DE PAGO"], "year")


def test_filas_desde_adjunto_descarta_filas_sin_factura():
    datos = _xlsx_bytes(
        [
            [900006037, "IPS X", "HUS0001", FECHA, "CE001", 100000],
            [None, None, None, None, None, None],
            [900006037, "IPS X", "HUS0002", FECHA, "CE001", 50000],
        ]
    )
    _, filas = msg_tools.filas_desde_adjunto(datos, "adjunto.xlsx")
    assert len(filas) == 2


def test_filas_desde_adjunto_sin_encabezado_falla_claro():
    wb = openpyxl.Workbook()
    buf = io.BytesIO()
    wb.save(buf)
    with pytest.raises(ValueError, match="encabezado"):
        msg_tools.filas_desde_adjunto(buf.getvalue(), "vacio.xlsx")


# ------------------------------------------------------------- resolver entradas


def test_resolver_entradas_carpeta(tmp_path):
    (tmp_path / "a.msg").write_bytes(b"x")
    (tmp_path / "b.msg").write_bytes(b"x")
    (tmp_path / "c.txt").write_bytes(b"x")
    rutas = msg_tools._resolver_entradas([str(tmp_path)])
    assert len(rutas) == 2
    assert all(r.endswith(".msg") for r in rutas)


def test_resolver_entradas_zip(tmp_path):
    zpath = tmp_path / "correos.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("uno.msg", b"contenido")
        z.writestr("notas.txt", b"ignorar")
    rutas = msg_tools._resolver_entradas([str(zpath)])
    assert len(rutas) == 1
    assert rutas[0].endswith("uno.msg")
    assert open(rutas[0], "rb").read() == b"contenido"


def test_resolver_entradas_rutas_msg_sueltas(tmp_path):
    f = tmp_path / "correo.msg"
    f.write_bytes(b"x")
    rutas = msg_tools._resolver_entradas([str(f)])
    assert rutas == [str(f)]


# ------------------------------------------------------------- consolidar (mockeado)


def test_consolidar_une_varios_correos(tmp_path, monkeypatch):
    correo1 = str(tmp_path / "correo1.msg")
    correo2 = str(tmp_path / "correo2.msg")
    for f in (correo1, correo2):
        open(f, "wb").close()

    datos1 = _xlsx_bytes([[900006037, "IPS X", "HUS0001", FECHA, "CE001", 100000]])
    datos2 = _xlsx_bytes([[900006037, "IPS X", "HUS0002", FECHA, "CE002", 50000]])

    def fake_leer(ruta, log=print):
        meta = dict(archivo=os.path.basename(ruta), asunto="", remitente="", fecha_envio=FECHA)
        datos = datos1 if "correo1" in ruta else datos2
        return meta, [("adjunto.xlsx", datos)]

    monkeypatch.setattr(msg_tools, "leer_adjuntos_pago", fake_leer)

    salida = str(tmp_path / "consolidado.xlsx")
    ruta = msg_tools.consolidar([correo1, correo2], salida, log=_silencio)
    assert ruta == salida

    wb = openpyxl.load_workbook(salida, data_only=True)
    ws = wb["CONSOLIDADO"]
    assert ws.max_row - 1 == 2  # 2 filas de datos (1 por correo)
    facturas = {ws.cell(r, 3).value for r in range(2, ws.max_row + 1)}
    assert facturas == {"HUS0001", "HUS0002"}

    ws2 = wb["RESUMEN"]
    valores_col_b = [ws2.cell(r, 2).value for r in range(2, ws2.max_row + 1)]
    assert 1 in valores_col_b  # cada correo aportó 1 fila


def test_consolidar_marca_duplicados_sin_eliminarlos(tmp_path, monkeypatch):
    correo1 = str(tmp_path / "correo1.msg")
    correo2 = str(tmp_path / "correo2.msg")
    for f in (correo1, correo2):
        open(f, "wb").close()

    # misma factura+comprobante+valor pagado en los DOS correos -> duplicado
    fila_repetida = [900006037, "IPS X", "HUS0001", FECHA, "CE001", 100000]
    datos1 = _xlsx_bytes([fila_repetida])
    datos2 = _xlsx_bytes([fila_repetida])

    def fake_leer(ruta, log=print):
        meta = dict(archivo=os.path.basename(ruta), asunto="", remitente="", fecha_envio=FECHA)
        datos = datos1 if "correo1" in ruta else datos2
        return meta, [("adjunto.xlsx", datos)]

    monkeypatch.setattr(msg_tools, "leer_adjuntos_pago", fake_leer)

    salida = str(tmp_path / "consolidado.xlsx")
    msg_tools.consolidar([correo1, correo2], salida, log=_silencio)

    wb = openpyxl.load_workbook(salida, data_only=True)
    ws = wb["CONSOLIDADO"]
    # ambas filas se CONSERVAN (no se borra nada) pero quedan marcadas
    assert ws.max_row - 1 == 2
    dup_col = next(
        c for c in range(1, ws.max_column + 1) if ws.cell(1, c).value == "_POSIBLE_DUPLICADO"
    )
    marcas = {ws.cell(r, dup_col).value for r in range(2, ws.max_row + 1)}
    assert marcas == {"SI"}


def test_consolidar_registra_correo_sin_adjunto(tmp_path, monkeypatch):
    con_adjunto = str(tmp_path / "con_adjunto.msg")
    sin_adjunto = str(tmp_path / "sin_adjunto.msg")
    for f in (con_adjunto, sin_adjunto):
        open(f, "wb").close()

    datos = _xlsx_bytes([[900006037, "IPS X", "HUS0001", FECHA, "CE001", 100000]])

    def fake_leer(ruta, log=print):
        meta = dict(archivo=os.path.basename(ruta), asunto="", remitente="", fecha_envio=FECHA)
        if "sin_adjunto" in ruta:
            return meta, []
        return meta, [("adjunto.xlsx", datos)]

    monkeypatch.setattr(msg_tools, "leer_adjuntos_pago", fake_leer)

    salida = str(tmp_path / "consolidado.xlsx")
    msg_tools.consolidar([con_adjunto, sin_adjunto], salida, log=_silencio)

    wb = openpyxl.load_workbook(salida, data_only=True)
    ws2 = wb["RESUMEN"]
    texto_hoja = " ".join(
        str(ws2.cell(r, 1).value) for r in range(1, ws2.max_row + 1) if ws2.cell(r, 1).value
    )
    assert "sin_adjunto.msg" in texto_hoja


def test_consolidar_sin_entradas_falla_claro(tmp_path):
    with pytest.raises(ValueError, match="No se encontraron"):
        msg_tools.consolidar(
            [str(tmp_path / "carpeta_vacia")], str(tmp_path / "out.xlsx"), log=_silencio
        )


def test_consolidar_totales_correctos(tmp_path, monkeypatch):
    correo1 = str(tmp_path / "correo1.msg")
    open(correo1, "wb").close()
    datos = _xlsx_bytes(
        [
            [900006037, "IPS X", "HUS0001", FECHA, "CE001", 100000],
            [900006037, "IPS X", "HUS0002", FECHA, "CE002", 250000],
        ]
    )

    def fake_leer(ruta, log=print):
        meta = dict(archivo=os.path.basename(ruta), asunto="", remitente="", fecha_envio=FECHA)
        return meta, [("adjunto.xlsx", datos)]

    monkeypatch.setattr(msg_tools, "leer_adjuntos_pago", fake_leer)

    salida = str(tmp_path / "consolidado.xlsx")
    msg_tools.consolidar([correo1], salida, log=_silencio)

    wb = openpyxl.load_workbook(salida, data_only=True)
    ws2 = wb["RESUMEN"]
    total_pagado = next(
        ws2.cell(r, 2).value
        for r in range(1, ws2.max_row + 1)
        if ws2.cell(r, 1).value == "VALOR PAGADO TOTAL"
    )
    assert total_pagado == 350000
