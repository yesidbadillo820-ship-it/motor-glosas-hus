"""Tests del extractor automático de facturas (Ronda 5)."""
from app.services.extractor_factura import extraer_de_texto


def test_extractor_caso_famisanar_completo():
    txt = (
        "ESE HOSPITAL UNIVERSITARIO DE SANTANDER\n"
        "FACTURA HUS0000491030\n"
        "PACIENTE: MARIA GOMEZ PEREZ\n"
        "EPS: FAMISANAR EPS\n"
        "RADICACIÓN: 09/04/2026\n"
        "RECEPCIÓN: 14/04/2026\n"
        "CUPS: 890750\n"
        "SERVICIO: CONSULTA DE URGENCIAS POR ESPECIALISTA\n"
        "VALOR FACTURADO: $114,900\n"
        "VALOR RECONOCIDO: $90,000\n"
        "TA0201 OBJETÁNDOSE DIFERENCIA DE $24,900"
    )
    r = extraer_de_texto(txt)
    assert r["numero_factura"] == "HUS0000491030"
    assert r["eps"] == "FAMISANAR"
    assert r["cups"] == "890750"
    assert r["fecha_radicacion"] == "2026-04-09"
    assert r["fecha_recepcion"] == "2026-04-14"
    assert r["valor_facturado"] == 114_900.0
    assert r["valor_reconocido"] == 90_000.0
    assert r["valor_objetado"] == 24_900.0
    assert "TA0201" in r["codigos_glosa"]
    assert r["confianza"] >= 0.8


def test_extractor_texto_vacio():
    r = extraer_de_texto("")
    assert r["confianza"] == 0.0
    assert "error" in r


def test_extractor_codigo_glosa_multiples():
    txt = "Glosas aplicadas: TA0201 y SO0101 y FA0802"
    r = extraer_de_texto(txt)
    assert "TA0201" in r["codigos_glosa"]
    assert "SO0101" in r["codigos_glosa"]
    assert "FA0802" in r["codigos_glosa"]


def test_extractor_cups_con_sufijo_h():
    txt = "Servicio CUPS 372301H ESTUDIO ELECTROFISIOLOGICO"
    r = extraer_de_texto(txt)
    assert r["cups"] == "372301H"


def test_extractor_eps_desconocida_devuelve_vacio_eps():
    txt = "FACTURA ABC-123 CUPS 890202 $100,000"
    r = extraer_de_texto(txt)
    assert r["eps"] == ""  # no reconocida, no devuelve texto


def test_extractor_reconocido_via_contratado_famisanar():
    """El formato Famisanar: 'VALOR UNITARIO CONTRATADO ... 168,000'."""
    txt = (
        "FACTURA HUS123 CUPS 873306 "
        "VALOR UNITARIO CONTRATADO PARA LA FECHA CON EPS FAMISANAR 168,000 "
        "VALOR UNITARIO FACTURADO POR IPS $206,400"
    )
    r = extraer_de_texto(txt)
    assert r["valor_facturado"] == 206_400.0
    assert r["valor_reconocido"] == 168_000.0
