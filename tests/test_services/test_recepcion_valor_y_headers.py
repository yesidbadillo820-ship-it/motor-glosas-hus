"""Regresión delta auditoría jun-2026: tolerancia de la importación de
recepción al formato REAL del Excel del DGH.

1. La hoja INICIAL trae fila 1 de título ("ENTREGA GLOSA INICIAL") y los
   encabezados en la fila 2 — el parser debe encontrarlos igual.
2. VALOR GLOSA se parsea con la semántica COP canónica de
   `parse_valor_cop` (app/utils/moneda.py): "36402" → 36402 y
   "1.234,56" → 1234.56 — NUNCA el parse ingenuo que multiplicaba ×100.
   (El parser interno `_a_float` ya implementa esa semántica; estos tests
   fijan el contrato contra `parse_valor_cop` para que no regrese.)
"""

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.models.db import GlosaRecord
from app.services.recepcion_service import RecepcionService, _a_float
from app.utils.moneda import parse_valor_cop

_HEADERS_INICIAL = [
    "GESTOR",
    "FECHA DE ENTREGA",
    "FECHA RADICACION",
    "FECHA DOCUMENTO DGH",
    "FECHA RECEPCION",
    "ENTIDAD",
    "FACTURA",
    "CONSECUTIVO DGH",
    "VALOR GLOSA",
    "VENCE",
    "DEVOLUCION \nS/N",
    "DIAS \nRADICACION VS RECEPCION",
]


def _excel_con_titulo(filas) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "INICIAL"
    ws.append(["ENTREGA GLOSA INICIAL"] + [""] * (len(_HEADERS_INICIAL) - 1))
    ws.append(_HEADERS_INICIAL)
    for f in filas:
        ws.append(f)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


def _fila(factura, valor, consecutivo="100001"):
    return [
        "GESTOR PRUEBA",
        "10/06/2026",
        "21/05/2026",
        "05/06/2026",
        "05/06/2026",
        "U999999 - EPS DE PRUEBA",
        factura,
        consecutivo,
        valor,
        "26/06/2026",
        "S",
        "11",
    ]


@pytest.fixture
def db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()


def test_header_en_fila_2_con_titulo_importa_todo(db):
    resumen = RecepcionService(db).procesar_excel(
        _excel_con_titulo([_fila("HUS0000000001", "36402")])
    )
    assert resumen.errores == []
    assert resumen.hojas_descartadas == []
    assert resumen.creadas == 1
    g = db.query(GlosaRecord).one()
    assert g.factura == "HUS0000000001"
    assert g.gestor_nombre == "GESTOR PRUEBA"


@pytest.mark.parametrize(
    "valor_celda,esperado",
    [
        ("36402", 36402.0),  # entero como texto (caso real GLOSAS_10_JUNIO)
        (36402, 36402.0),  # entero como número
        ("1.234,56", 1234.56),  # formato colombiano con decimales
        ("1.211.302", 1211302.0),  # miles con punto (caso real abril-2026)
        ("$ 500.000", 500000.0),  # con símbolo de moneda
    ],
)
def test_valor_glosa_semantica_parse_valor_cop(db, valor_celda, esperado):
    """El valor importado coincide con parse_valor_cop — sin el bug ×100."""
    assert abs(parse_valor_cop(valor_celda) - esperado) < 0.01, "premisa del contrato"
    resumen = RecepcionService(db).procesar_excel(
        _excel_con_titulo([_fila("HUS0000000010", valor_celda)])
    )
    assert resumen.creadas == 1
    g = db.query(GlosaRecord).one()
    assert abs(float(g.valor_objetado) - esperado) < 0.01
    assert abs(float(g.valor_objetado) - parse_valor_cop(valor_celda)) < 0.01


@pytest.mark.parametrize(
    "raw",
    ["36402", "7.700,00", "1.500.000", "$ 500.000", "1.234,56"],
)
def test_a_float_coincide_con_parse_valor_cop_en_formatos_cop(raw):
    """Contrato: para strings COP canónicos, el parser interno del
    importador (_a_float) y parse_valor_cop devuelven lo mismo."""
    assert abs(_a_float(raw) - parse_valor_cop(raw)) < 0.01
