"""Tests de la Suite Cartera HUS (tools/suite_cartera_hus/).

Cubre el núcleo headless de la Suite:
  · detección del tipo REAL por firma binaria (PDF renombrado .cmd, etc.),
  · extracción de ZIP recursiva y anti zip-slip,
  · parseo de importes en formato colombiano — regresión del bug que leía
    '50.000' como 50 en vez de 50000,
  · consolidación de glosas + guardián de valores + generación de OBJECIONES,
  · el estándar único de evidencia (CONTROL.csv / REVISAR.csv / RESUMEN.txt),
  · la fusión de credenciales desde el archivo local que NO se versiona.

Los tests que dependen de pandas se saltan si no está instalado: el motor del
HUS no lo trae de fábrica (usa openpyxl directo); la Suite lo instala aparte
en el equipo del analista.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

# La Suite vive en tools/suite_cartera_hus/ con su propio paquete `nucleo`.
_SUITE = Path(__file__).resolve().parents[2] / "tools" / "suite_cartera_hus"
sys.path.insert(0, str(_SUITE))

from nucleo import archivos, cruces_dgh, registro, reportes  # noqa: E402

try:
    import pandas as _pd
except ImportError:  # pragma: no cover
    _pd = None

requiere_pandas = pytest.mark.skipif(
    _pd is None, reason="pandas no instalado (la Suite lo instala aparte)"
)


# ============================================================ a_numero (crítico)


@pytest.mark.parametrize(
    "entrada,esperado",
    [
        # formato colombiano: punto = miles, coma = decimal
        ("$ 50.000", 50000),
        ("50.000", 50000),  # <- el bug: antes daba 50.0
        ("1.234", 1234),
        ("2.500", 2500),
        ("80.000", 80000),
        ("1.200.000", 1200000),
        ("1.234.567,89", 1234567.89),
        ("1234,56", 1234.56),
        ("COP 80.000", 80000),
        # decimales reales (1 o 2 dígitos a la derecha) se respetan
        ("1.5", 1.5),
        ("12.34", 12.34),
        ("100.5", 100.5),
        # formato US (coma miles, punto decimal)
        ("1,234,567.89", 1234567.89),
        # enteros y basura
        ("1000", 1000),
        ("", 0.0),
        ("-", 0.0),
        (".", 0.0),
        ("$0", 0.0),
        (None, 0.0),
        (1500000, 1500000.0),
        (1234.56, 1234.56),
    ],
)
def test_a_numero(entrada, esperado):
    assert cruces_dgh.a_numero(entrada) == pytest.approx(esperado)


# ============================================================ tipo_real / firmas


def test_tipo_real_pdf_renombrado_cmd(tmp_path):
    f = tmp_path / "HUS001234_FACTURA.cmd"
    f.write_bytes(b"%PDF-1.7\n...")
    assert archivos.tipo_real(str(f)) == "pdf"


def test_tipo_real_xlsx_docx_csv_txt(tmp_path):
    xlsx = tmp_path / "a.xlsx"
    with zipfile.ZipFile(xlsx, "w") as z:
        z.writestr("xl/workbook.xml", "<x/>")
    docx = tmp_path / "b.docx"
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr("word/document.xml", "<x/>")
    csv = tmp_path / "c.csv"
    csv.write_text("a;b;c\n1;2;3\n", encoding="utf-8")
    txt = tmp_path / "d.txt"
    txt.write_text("solo texto sin separadores\n", encoding="utf-8")
    assert archivos.tipo_real(str(xlsx)) == "xlsx"
    assert archivos.tipo_real(str(docx)) == "docx"
    assert archivos.tipo_real(str(csv)) == "csv"
    assert archivos.tipo_real(str(txt)) == "txt"


def test_extraer_factura_y_clasificar():
    assert archivos.extraer_factura("HUS001234_GLOSAS.xlsx") == "HUS001234"
    assert archivos.extraer_factura("detalle_9876543.xls") == "9876543"
    assert archivos.extraer_factura("sin_numero.pdf") is None
    assert archivos.clasificar_archivo("X_GLOSAS.xlsx") == "GLOSAS"
    assert archivos.clasificar_archivo("X_DETALLE.xlsx") == "DETALLE"
    assert archivos.clasificar_archivo("X_FACTURA.pdf") == "FACTURA"
    assert archivos.clasificar_archivo("cualquier.txt") is None


# ============================================================ extracción ZIP


def test_extraer_zip_recursivo(tmp_path):
    interno = tmp_path / "interno.zip"
    with zipfile.ZipFile(interno, "w") as z:
        z.writestr("dentro/hoja.txt", "hola")
    externo = tmp_path / "externo.zip"
    with zipfile.ZipFile(externo, "w") as z:
        z.writestr("factura.txt", "F")
        z.write(interno, "sub/interno.zip")
    destino = tmp_path / "salida"
    extraidos = archivos.extraer_zip_recursivo(str(externo), str(destino), log=lambda *_: None)
    nombres = {Path(p).name for p in extraidos}
    assert "factura.txt" in nombres
    assert "hoja.txt" in nombres  # salió del ZIP anidado
    # no debe quedar ningún .zip intermedio en el destino
    assert not list(destino.rglob("*.zip"))


def test_zip_slip_omitido_sin_abortar(tmp_path):
    """La entrada con ../ se omite, pero el resto del ZIP sí se extrae."""
    malicioso = tmp_path / "evil.zip"
    with zipfile.ZipFile(malicioso, "w") as z:
        z.writestr("../fuera.txt", "escapa")
        z.writestr("bueno.txt", "ok")
    dest = tmp_path / "dest"
    extraidos = archivos.extraer_zip_recursivo(str(malicioso), str(dest), log=lambda *_: None)
    nombres = {Path(p).name for p in extraidos}
    assert "bueno.txt" in nombres  # el archivo sano sí salió
    assert not (tmp_path / "fuera.txt").exists()  # nada escapó del destino


def test_extraer_factura_prioriza_hus():
    # aunque la fecha 20240115 aparece ANTES, gana el formato HUS
    assert archivos.extraer_factura("GLOSA_20240115_HUS001234.xlsx") == "HUS001234"
    # sin HUS, cae al genérico numérico
    assert archivos.extraer_factura("reporte_20240115.xlsx") == "20240115"


def test_zip_anidado_no_colisiona(tmp_path):
    """Dos ZIP anidados con un archivo del mismo nombre no se pisan."""
    a = tmp_path / "a.zip"
    with zipfile.ZipFile(a, "w") as z:
        z.writestr("GLOSAS.xlsx", "AAA")
    b = tmp_path / "b.zip"
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("GLOSAS.xlsx", "BBB")
    externo = tmp_path / "externo.zip"
    with zipfile.ZipFile(externo, "w") as z:
        z.write(a, "rama1/a.zip")
        z.write(b, "rama2/b.zip")
    dest = tmp_path / "dest"
    extraidos = archivos.extraer_zip_recursivo(str(externo), str(dest), log=lambda *_: None)
    glosas = [p for p in extraidos if Path(p).name == "GLOSAS.xlsx"]
    assert len(glosas) == 2  # ambas sobreviven, ninguna sobrescrita
    contenidos = {Path(p).read_text() for p in glosas}
    assert contenidos == {"AAA", "BBB"}


# ============================================================ ReporteEstandar


def test_reporte_estandar_genera_control_revisar_resumen(tmp_path):
    rep = reportes.ReporteEstandar(
        "COOSALUD EPS", "prueba", base=str(tmp_path), log=lambda *_: None
    )
    rep.registrar("HUS1", "CERRADA", "24 glosas", 1500000, "HUS1.png")
    rep.registrar("HUS2", "CERRADA", "3 glosas", 90000)
    rep.excluir("HUS9", "FACTURA_YA_OBJETADA")
    carpeta = Path(rep.cerrar())

    control = (carpeta / "CONTROL.csv").read_text(encoding="utf-8-sig")
    assert "fecha_hora;entidad;proceso;factura;estado;detalle;valor;evidencia" in control
    assert "HUS1" in control and "HUS2" in control
    revisar = (carpeta / "REVISAR.csv").read_text(encoding="utf-8-sig")
    assert "HUS9" in revisar and "FACTURA_YA_OBJETADA" in revisar
    resumen = (carpeta / "RESUMEN.txt").read_text(encoding="utf-8")
    assert "Procesadas: 2" in resumen
    assert "Excluidas a REVISAR: 1" in resumen


def test_reporte_evidencias_sin_imagenes_no_falla(tmp_path):
    rep = reportes.ReporteEstandar("X", "ev", base=str(tmp_path), log=lambda *_: None)
    vacia = tmp_path / "sin_imagenes"
    vacia.mkdir()
    assert rep.compilar_evidencias_word(str(vacia)) is None


# ============================================================ registro / credenciales


def test_buscar_y_resumen_estados():
    ents = [
        {"nombre": "COOSALUD EPS", "nit": "900226715", "estado_radicacion": "OPERATIVA"},
        {"nombre": "NUEVA EPS", "nit": "900156264", "estado_radicacion": "POR_ARMAR"},
    ]
    assert len(registro.buscar(ents, "coosalud")) == 1
    assert len(registro.buscar(ents, "900156264")) == 1
    assert len(registro.buscar(ents, "")) == 2
    assert registro.resumen_estados(ents) == {"OPERATIVA": 1, "POR_ARMAR": 1}


def test_fusion_credenciales_por_nit_y_nombre(tmp_path, monkeypatch):
    overlay = {
        "credenciales": [
            {"nit": "900226715", "nombre": "COOSALUD", "radicacion.contrasena": "secreta1"},
            {"nit": "", "nombre": "ALCALDIA SIN NIT", "cartera.clave": "secreta2"},
        ]
    }
    ruta = tmp_path / "entidades.credenciales.json"
    ruta.write_text(json.dumps(overlay), encoding="utf-8")
    monkeypatch.setattr(registro, "RUTA_CREDENCIALES", str(ruta))

    entidades = [
        {"nit": "900226715", "nombre": "COOSALUD", "radicacion": {"usuario": "u"}},
        {"nit": "", "nombre": "ALCALDIA SIN NIT", "cartera": {}},
    ]
    registro._fusionar_credenciales(entidades)
    assert entidades[0]["radicacion"]["contrasena"] == "secreta1"  # emparejó por NIT
    assert entidades[1]["cartera"]["clave"] == "secreta2"  # emparejó por nombre


def test_entidades_json_del_repo_no_trae_secretos():
    """El entidades.json versionado nunca debe llevar contraseñas."""
    ruta = _SUITE / "config" / "entidades.json"
    data = json.loads(ruta.read_text(encoding="utf-8"))

    def secretos(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                kl = k.lower()
                if any(t in kl for t in ("contrasen", "clave", "credencial")):
                    if isinstance(v, str) and v.strip():
                        yield k
                yield from secretos(v)

    encontrados = [s for e in data.get("entidades", []) for s in secretos(e)]
    assert encontrados == [], f"entidades.json trae secretos: {encontrados}"


# ============================================================ pipeline con pandas


@pytest.fixture
def carpeta_glosas(tmp_path):
    """Arma una carpeta con GLOSAS + DETALLE como los del portal de una EPS."""
    pd = _pd
    g = pd.DataFrame(
        [
            {
                "NUMERO FACTURA": "HUS001234",
                "CODIGO SERVICIO": "890201",
                "NOMBRE SERVICIO": "CONSULTA",
                "CODIGO GLOSA": "CL0101",
                "DESCRIPCION GLOSA": "No pertinente",
                "VALOR GLOSADO": "$ 50.000",
            },
            {
                "NUMERO FACTURA": "HUS001234",
                "CODIGO SERVICIO": "990101",
                "NOMBRE SERVICIO": "ESTANCIA",
                "CODIGO GLOSA": "FA0201",
                "DESCRIPCION GLOSA": "Falta soporte",
                "VALOR GLOSADO": "1.200.000",  # excede el saldo -> guardián
            },
            {  # renglón byte-idéntico al primero: duplicado de exportación
                "NUMERO FACTURA": "HUS001234",
                "CODIGO SERVICIO": "890201",
                "NOMBRE SERVICIO": "CONSULTA",
                "CODIGO GLOSA": "CL0101",
                "DESCRIPCION GLOSA": "No pertinente",
                "VALOR GLOSADO": "$ 50.000",
            },
        ]
    )
    g.to_excel(tmp_path / "HUS001234_GLOSAS.xlsx", index=False)
    d = pd.DataFrame(
        [
            {
                "FACTURA": "HUS001234",
                "CODIGO SERVICIO": "890201",
                "VALOR SERVICIO": "60.000",
                "SALDO": "60.000",
                "COPAGO": "0",
            },
            {
                "FACTURA": "HUS001234",
                "CODIGO SERVICIO": "990101",
                "VALOR SERVICIO": "1.500.000",
                "SALDO": "1.000.000",
                "COPAGO": "0",
            },
        ]
    )
    d.to_excel(tmp_path / "HUS001234_DETALLE.xlsx", index=False)
    return tmp_path


@requiere_pandas
def test_consolidar_parsea_pesos_y_depura_duplicados(carpeta_glosas):
    consolidado, _ = cruces_dgh.consolidar(str(carpeta_glosas), log=lambda *_: None)
    # 3 renglones de entrada, 1 duplicado idéntico -> 2 servicios
    assert len(consolidado) == 2
    fila = consolidado[consolidado["codigo_servicio"] == "890201"].iloc[0]
    # regresión: 50.000 debe valer 50000, no 50 (y el duplicado NO se suma)
    assert cruces_dgh.a_numero(fila["valor_glosado"]) == 50000
    assert cruces_dgh.a_numero(fila["valor_servicio"]) == 60000
    assert fila["tipo_glosa"] == "MEDICA"  # empieza por CL
    assert consolidado["tipo_objecion"].iloc[0] == "MIXTA"


@requiere_pandas
def test_generar_objeciones_guardian_y_lote(carpeta_glosas, tmp_path):
    consolidado, _ = cruces_dgh.consolidar(str(carpeta_glosas), log=lambda *_: None)
    salida = tmp_path / "obj"
    salida.mkdir()
    rutas = cruces_dgh.generar_objeciones(
        consolidado,
        str(salida),
        entidad={"nit": "900226715", "nombre": "COOSALUD"},
        facturas_ya_objetadas=set(),
        reporte=None,
        log=lambda *_: None,
    )
    assert len(rutas) == 1
    obj = _pd.read_excel(rutas[0], dtype=str)  # dtype=str: el archivo guarda el CUPS como texto
    fila_estancia = obj[obj["CODIGO_SERVICIO"] == "990101"].iloc[0]
    # el guardián recorta la objeción al saldo (1.000.000), no al glosado (1.200.000)
    assert cruces_dgh.a_numero(fila_estancia["VALOR_OBJETADO"]) == 1000000
    assert cruces_dgh.a_numero(fila_estancia["VALOR_GLOSADO"]) == 1200000
    # nunca se objeta más de lo glosado
    for _, r in obj.iterrows():
        assert cruces_dgh.a_numero(r["VALOR_OBJETADO"]) <= cruces_dgh.a_numero(r["VALOR_GLOSADO"])


@requiere_pandas
def test_objeciones_excluye_ya_objetadas(carpeta_glosas, tmp_path):
    consolidado, _ = cruces_dgh.consolidar(str(carpeta_glosas), log=lambda *_: None)
    salida = tmp_path / "obj"
    salida.mkdir()
    rutas = cruces_dgh.generar_objeciones(
        consolidado,
        str(salida),
        entidad={"nit": "1", "nombre": "X"},
        facturas_ya_objetadas={"HUS001234"},
        reporte=None,
        log=lambda *_: None,
    )
    # la única factura estaba ya objetada -> no se produce ningún lote
    assert rutas == []


@requiere_pandas
def test_objeciones_error_claro_si_falta_columna(tmp_path):
    df = _pd.DataFrame([{"algo": "x"}])
    with pytest.raises(ValueError, match="columnas internas"):
        cruces_dgh.generar_objeciones(
            df, str(tmp_path), entidad={}, reporte=None, log=lambda *_: None
        )


@requiere_pandas
def test_leer_tabla_una_columna_y_latin1(tmp_path):
    # lista de facturas "ya objetadas": una sola columna, codificación latin-1
    ruta = tmp_path / "ya.csv"
    ruta.write_bytes("factura\nHUS001\nBOGOTÁ-99\n".encode("latin-1"))
    df = cruces_dgh.leer_tabla(str(ruta), log=lambda *_: None)
    assert df.shape[1] == 1  # antes reventaba con ValueError
    valores = df.iloc[:, 0].dropna().astype(str).tolist()
    assert "HUS001" in valores


@requiere_pandas
def test_consolidar_conserva_factura_desconocida(tmp_path):
    """Un renglón sin factura (ni en celda ni en nombre) NO se pierde en silencio."""
    pd = _pd
    # un archivo CON factura en el nombre crea la columna __factura_archivo;
    # el otro no la tiene y trae la celda de factura vacía.
    pd.DataFrame(
        [
            {
                "NUMERO FACTURA": "HUS001",
                "CODIGO SERVICIO": "A",
                "CODIGO GLOSA": "CL1",
                "VALOR GLOSADO": "10.000",
            }
        ]
    ).to_excel(tmp_path / "HUS001_GLOSAS.xlsx", index=False)
    pd.DataFrame(
        [
            {
                "NUMERO FACTURA": "",
                "CODIGO SERVICIO": "B",
                "CODIGO GLOSA": "CL2",
                "VALOR GLOSADO": "20.000",
            }
        ]
    ).to_excel(tmp_path / "GLOSAS_sueltas.xlsx", index=False)
    consolidado, _ = cruces_dgh.consolidar(str(tmp_path), log=lambda *_: None)
    # ambos servicios presentes (el de factura desconocida sobrevive como "")
    assert set(consolidado["codigo_servicio"]) == {"A", "B"}


@requiere_pandas
def test_consolidar_no_confunde_servicio_con_glosa(tmp_path):
    """Si no hay columna de servicio propia, no se agrupa por la de glosa."""
    pd = _pd
    # sólo hay 'CODIGO GLOSA' (no 'CODIGO SERVICIO'); dos glosas distintas
    pd.DataFrame(
        [
            {
                "NUMERO FACTURA": "HUS9",
                "CODIGO GLOSA": "CL1",
                "DESCRIPCION GLOSA": "a",
                "VALOR GLOSADO": "10.000",
            },
            {
                "NUMERO FACTURA": "HUS9",
                "CODIGO GLOSA": "CL2",
                "DESCRIPCION GLOSA": "b",
                "VALOR GLOSADO": "20.000",
            },
        ]
    ).to_excel(tmp_path / "HUS9_GLOSAS.xlsx", index=False)
    consolidado, avisos = cruces_dgh.consolidar(str(tmp_path), log=lambda *_: None)
    # codigo_servicio quedó en blanco (no se robó la columna de glosa)
    assert (consolidado["codigo_servicio"] == "").all()
    # y no se colapsaron las dos glosas en una sola por clave equivocada
    assert set(consolidado["codigo_glosa"]) == {"CL1", "CL2"}
    assert any("servicio" in a.lower() for a in avisos)
