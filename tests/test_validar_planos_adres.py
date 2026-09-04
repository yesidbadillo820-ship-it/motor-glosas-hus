"""Pruebas del validador de archivos planos de la Circular 022/2023 ADRES."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools" / "adres"))

from validar_planos_adres import (  # noqa: E402
    ADVERTENCIA,
    ERROR,
    detectar_tipo,
    escribir_csv,
    escribir_json,
    validar_archivo,
    validar_linea,
    validar_nomenclatura,
)

REGISTRO_F1_OK_PREFIJO = ",0,HUS374152,123456789,"  # campos 1-5 típicos


def _errores(hallazgos):
    return [h for h in hallazgos if h.severidad == ERROR]


# ── Nomenclatura ─────────────────────────────────────────────────────────────


def test_detecta_tipo_por_prefijo():
    assert detectar_tipo("FURIPS112345678901201102023") == "FURIPS1"
    assert detectar_tipo("furips212345678901201102023") == "FURIPS2"
    assert detectar_tipo("FURTRAN12345678901201102023") == "FURTRAN"
    assert detectar_tipo("FUCTAS2123456012026") == "FUCTAS"
    assert detectar_tipo("FURCEN001011020231430") == "FURCEN"
    assert detectar_tipo("RIPS_HUS374152") is None


def test_nomenclatura_furips1_valida(tmp_path):
    ruta = tmp_path / "FURIPS112345678901201102023.txt"
    assert _errores(validar_nomenclatura(ruta)) == []


def test_nomenclatura_furips1_fecha_inexistente(tmp_path):
    ruta = tmp_path / "FURIPS112345678901232132023.txt"  # 32/13/2023
    assert any("DDMMAAAA" in h.descripcion for h in _errores(validar_nomenclatura(ruta)))


def test_nomenclatura_habilitacion_corta(tmp_path):
    ruta = tmp_path / "FURIPS1123401102023.txt"  # solo 4 dígitos de habilitación
    assert _errores(validar_nomenclatura(ruta))


def test_nomenclatura_fuctas_periodo(tmp_path):
    assert _errores(validar_nomenclatura(tmp_path / "FUCTAS2123456012026.txt")) == []
    con_error = validar_nomenclatura(tmp_path / "FUCTAS2123456132026.txt")  # mes 13
    assert any("MMAAAA" in h.descripcion for h in _errores(con_error))


def test_nomenclatura_furcen_hora(tmp_path):
    assert _errores(validar_nomenclatura(tmp_path / "FURCEN001011020231430.txt")) == []
    con_error = validar_nomenclatura(tmp_path / "FURCEN001011020232561.txt")  # 25:61
    assert any("HHMM" in h.descripcion for h in _errores(con_error))


def test_nomenclatura_extension(tmp_path):
    csv_ = validar_nomenclatura(tmp_path / "FURIPS112345678901201102023.csv")
    assert any(h.severidad == ADVERTENCIA for h in csv_)
    xlsx = validar_nomenclatura(tmp_path / "FURIPS112345678901201102023.xlsx")
    assert any("Extensión" in h.descripcion for h in _errores(xlsx))


# ── Reglas generales por línea ───────────────────────────────────────────────


def _linea_f1(**cambios) -> str:
    campos = [""] * 102
    campos[1] = "0"  # RGO
    campos[2] = "HUS374152"  # factura
    campos[3] = "123456789"  # consecutivo
    for indice, valor in cambios.items():
        campos[int(indice)] = valor
    return ",".join(campos)


def test_linea_numero_de_campos():
    errores = _errores(validar_linea("a,b,c", 1, "FURIPS1", "f.txt"))
    assert any("102" in h.descripcion for h in errores)


def test_linea_comillas_prohibidas():
    linea = _linea_f1(**{"2": '"HUS374152"'})
    assert any(
        "comillas" in h.descripcion for h in _errores(validar_linea(linea, 1, "FURIPS1", "f"))
    )


def test_linea_relleno_espacios():
    linea = _linea_f1(**{"2": " HUS374152"})
    assert any(
        "espacios" in h.descripcion for h in _errores(validar_linea(linea, 1, "FURIPS1", "f"))
    )


def test_linea_separador_de_miles_y_decimales():
    con_miles = validar_linea(_linea_f1(**{"3": "1.234.567"}), 1, "FURIPS1", "f")
    assert any("separador de miles" in h.descripcion for h in _errores(con_miles))
    con_decimales = validar_linea(_linea_f1(**{"3": "1234.50"}), 1, "FURIPS1", "f")
    assert any("decimales" in h.descripcion for h in _errores(con_decimales))


def test_linea_ceros_de_relleno_en_consecutivo():
    errores = _errores(validar_linea(_linea_f1(**{"3": "000123"}), 1, "FURIPS1", "f"))
    assert any("ceros a la izquierda" in h.descripcion for h in errores)


def test_linea_valores_permitidos():
    errores = _errores(validar_linea(_linea_f1(**{"1": "9"}), 1, "FURIPS1", "f"))
    assert any("no está en los permitidos" in h.descripcion for h in errores)


def test_linea_longitud_maxima():
    errores = _errores(validar_linea(_linea_f1(**{"2": "X" * 21}), 1, "FURIPS1", "f"))
    assert any("longitud máxima de 20" in h.descripcion for h in errores)


def test_linea_obligatorio_vacio():
    errores = _errores(validar_linea(_linea_f1(**{"2": ""}), 1, "FURIPS1", "f"))
    assert any("obligatorio vacío" in h.descripcion for h in errores)


def test_furips2_fecha_al_reves():
    campos = ["HUS374152", "123", "1", "COD", "DESC", "1", "100", "100", "100"]
    assert _errores(validar_linea(",".join(campos), 1, "FURIPS2", "f")) == []


def test_furtran_sin_anexo_solo_reglas_globales():
    errores = _errores(validar_linea('a, b ,"c"', 1, "FURTRAN", "f"))
    descripciones = " | ".join(h.descripcion for h in errores)
    assert "comillas" in descripciones and "espacios" in descripciones


# ── Archivo completo y reportes ──────────────────────────────────────────────


def test_archivo_vacio(tmp_path):
    ruta = tmp_path / "FURIPS112345678901201102023.txt"
    ruta.write_text("", encoding="utf-8")
    assert any("vacío" in h.descripcion for h in _errores(validar_archivo(ruta)))


def test_archivo_json_se_omite_con_aviso(tmp_path):
    ruta = tmp_path / "FURIPS112345678901201102023.json"
    ruta.write_text("{}", encoding="utf-8")
    hallazgos = validar_archivo(ruta)
    assert hallazgos and hallazgos[0].severidad == ADVERTENCIA
    assert "omitido" in hallazgos[0].descripcion


def test_archivo_valido_y_reportes(tmp_path):
    # Registro construido campo a campo desde la propia malla E1: para cada
    # campo se genera un valor que cumple su formato/permitidos.
    from validar_planos_adres import TABLAS

    valores = []
    for _numero, _concepto, longitud, formato, permitidos, oblig in TABLAS["FURIPS1"]:
        if oblig != "SI":
            valores.append("")
            continue
        if permitidos:
            valores.append(sorted(permitidos)[0])
        elif formato == "fecha":
            valores.append("01/10/2023")
        elif formato == "hora":
            valores.append("14:30")
        elif formato == "num":
            valores.append("123")
        elif formato == "cie10":
            valores.append("S720")
        elif formato == "depto":
            valores.append("68")
        elif formato == "mun":
            valores.append("001")
        elif formato == "placa":
            valores.append("ABC123")
        else:
            valores.append("DATO"[: longitud or 4])
    ruta = tmp_path / "FURIPS112345678901201102023.txt"
    ruta.write_text(",".join(valores) + "\n", encoding="utf-8")
    hallazgos = validar_archivo(ruta)
    assert _errores(hallazgos) == []

    escribir_json(hallazgos, tmp_path / "rep.json")
    escribir_csv(hallazgos, tmp_path / "rep.csv")
    assert (tmp_path / "rep.json").exists() and (tmp_path / "rep.csv").exists()
    contenido = (tmp_path / "rep.csv").read_text(encoding="utf-8-sig")
    assert "NOMBRE DEL ARCHIVO" in contenido


def test_reporte_xlsx_detallado(tmp_path):
    openpyxl = __import__("pytest").importorskip("openpyxl")
    from validar_planos_adres import Hallazgo, escribir_xlsx

    hallazgos = [
        Hallazgo(
            "FURIPS1X.txt",
            1,
            "3 - Número de factura",
            '"X"',
            "El campo contiene comillas dobles.",
            ERROR,
        ),
        Hallazgo(
            "FURIPS1X.txt",
            2,
            "4 - Consecutivo",
            "000123",
            "Relleno con ceros a la izquierda.",
            ERROR,
        ),
        Hallazgo("FURIPS1X.txt", 0, "Archivo", "", "Aviso informativo.", "INFO"),
    ]
    meta = [{"archivo": "FURIPS1X.txt", "tipo": "FURIPS1", "lineas": 2}]
    destino = tmp_path / "rep.xlsx"
    escribir_xlsx(hallazgos, meta, destino)

    wb = openpyxl.load_workbook(destino)
    assert wb.sheetnames == ["RESUMEN", "HALLAZGOS", "POR CAMPO", "AVISOS", "LEYENDA"]
    assert wb["HALLAZGOS"].max_row == 3  # encabezado + 2 errores (el INFO va en AVISOS)
    assert wb["AVISOS"].max_row == 2
    filas_resumen = [
        str(v) for fila in wb["RESUMEN"].iter_rows(values_only=True) for v in fila if v
    ]
    assert any("CON ERRORES" in v for v in filas_resumen)
