"""El CONCEPTO de la EPS (hoja 'i' del DGH) debe llegar a la IA.

Bug reportado 2026-06-10: las hojas I/R se parseaban a ConceptoGlosaRecord
pero texto_glosa_original quedaba vacío, así que el auto-responder caía al
fallback `dictamen` — el placeholder "Pendiente de análisis..." — y la IA
respondía sin leer el motivo real de la glosa.

Cubre:
  1. La importación cruza la hoja 'i' con INICIAL por FACTURA y compila
     texto_glosa_original con código + CUPS + valor + observación EPS.
  2. _texto_glosa_para_ia (auto_responder) devuelve ese texto, NO el
     placeholder.
  3. Fallback: si texto_glosa_original está vacío pero hay conceptos en
     BD (imports viejos), se compone al vuelo.
  4. El texto manual del gestor nunca se pisa al reimportar.
"""

from io import BytesIO

import pytest
from openpyxl import Workbook

from app.models.db import ConceptoGlosaRecord, GlosaRecord
from app.services.auto_responder_service import _texto_glosa_para_ia
from app.services.recepcion_service import (
    MARCA_TEXTO_CONCEPTOS,
    RecepcionService,
    componer_texto_desde_conceptos,
)


# ─── Builders (estructura del export real del DGH) ───────────────────────────

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

_HEADERS_I = [
    "EstadoCxCObjecion",
    "TipoObjecionTramite",
    "Referencia",
    "FacturaCartera.PlanBeneficio.Contrato.Entidad.NombreEntidad",
    "FacturaCartera.Saldo",
    "UsuarioConfirmacion.Descripcion",
    "UsuarioConfirmacion.Nombre",
    "UsuarioCreacion.Descripcion",
    "UsuarioCreacion.Nombre",
    "FacturaCartera.PlanBeneficio.CodigoNombrePlanBeneficios",
    "FacturaCartera.PlanBeneficio.Contrato.Entidad.CodigoEntidad",
    "FacturaCartera.Factura",
    "FechaDocumento",
    "Consecutivo",
    "Observaciones",
    "EstadoActual",
    "FacturaCartera.Valor",
    "FacturaCartera.Fecha",
    "FacturaCartera.Tercero.Documento",
    "FacturaCartera.Tercero.NombreCompletoAN",
    "FechaObjecion",
    "ConceptoObjecion.Codigo",
    "Oid",
    "ConceptoObjecion.Nombre",
    "ValorObjecion",
    "FacturaCartera.Tercero.NombreCompletoNA",
    "ListadoConceptos.ConceptoObjecion.Codigo",
    "ListadoConceptos.Oid",
    "ListadoConceptos.ConceptoObjecion.Nombre",
    "ListadoConceptos.ServicioProductoFactura.Codigo",
    "ListadoConceptos.ServicioProductoFactura.Descripcion",
    "ListadoConceptos.ValorObjecion",
    "ListadoConceptos.ServicioProductoFactura.CentroCosto.CodigoNombreCentro",
    "ListadoConceptos.Observaciones",
]


def _fila_inicial(factura: str, consecutivo: str, valor="36402"):
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


def _fila_concepto(
    factura: str,
    consecutivo: str,
    oid: str,
    codigo="TA0801",
    nombre="Los cargos presentan diferencias con los valores pactados",
    cups="882298",
    cups_desc="ECOGRAFIA DE PRUEBA",
    valor=36402,
    centro="734301 - ECOGRAFIA",
    obs="SE RECONOCE A TARIFAS SOAT VIGENTE NO HAY CONTRATO NI ACUERDO DE TARIFAS.",
):
    fila = [""] * len(_HEADERS_I)
    fila[0] = "Glosa_Inicial"
    fila[1] = "Administrativo"
    fila[11] = factura
    fila[13] = consecutivo
    fila[26] = codigo
    fila[27] = oid
    fila[28] = nombre
    fila[29] = cups
    fila[30] = cups_desc
    fila[31] = valor
    fila[32] = centro
    fila[33] = obs
    return fila


def _excel(filas_inicial, filas_conceptos) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "INICIAL"
    ws.append(["ENTREGA GLOSA INICIAL"] + [""] * (len(_HEADERS_INICIAL) - 1))
    ws.append(_HEADERS_INICIAL)
    for f in filas_inicial:
        ws.append(f)
    wsi = wb.create_sheet("i")
    wsi.append(_HEADERS_I)
    for f in filas_conceptos:
        wsi.append(f)
    out = BytesIO()
    wb.save(out)
    return out.getvalue()


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


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_concepto_cruzado_por_factura_llega_a_texto_glosa(db):
    contenido = _excel(
        [_fila_inicial("HUS0000000001", "100001")],
        [_fila_concepto("HUS0000000001", "100001", oid="900001")],
    )
    resumen = RecepcionService(db).procesar_excel(contenido)
    assert resumen.creadas == 1
    assert resumen.conceptos_creados == 1
    assert resumen.conceptos_huerfanos == []

    g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000001").one()
    texto = g.texto_glosa_original or ""
    assert texto.startswith(MARCA_TEXTO_CONCEPTOS)
    # El concepto completo de la EPS quedó en el texto que leerá la IA
    assert "TA0801" in texto
    assert "ECOGRAFIA DE PRUEBA" in texto
    assert "SE RECONOCE A TARIFAS SOAT VIGENTE" in texto
    assert "$36.402" in texto


def test_multiples_conceptos_de_la_misma_factura_se_compilan(db):
    contenido = _excel(
        [_fila_inicial("HUS0000000002", "100002", valor="208300")],
        [
            _fila_concepto(
                "HUS0000000002",
                "100002",
                oid="900002",
                obs="GLOSA CRITULINA NO EVIDENCIA ACUERDO DE TARIFAS",
            ),
            _fila_concepto(
                "HUS0000000002",
                "100002",
                oid="900003",
                cups="906611",
                cups_desc="PROTEINAS POR ELECTROFORESIS",
                obs="GLOSA MVC IPS SIN CONTRATO",
            ),
        ],
    )
    RecepcionService(db).procesar_excel(contenido)
    g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000002").one()
    texto = g.texto_glosa_original or ""
    assert "2 concepto(s)" in texto
    assert "CONCEPTO 1:" in texto and "CONCEPTO 2:" in texto
    assert "GLOSA CRITULINA NO EVIDENCIA ACUERDO DE TARIFAS" in texto
    assert "GLOSA MVC IPS SIN CONTRATO" in texto


def test_texto_para_ia_es_el_concepto_no_el_placeholder(db):
    contenido = _excel(
        [_fila_inicial("HUS0000000003", "100003")],
        [_fila_concepto("HUS0000000003", "100003", oid="900004")],
    )
    RecepcionService(db).procesar_excel(contenido)
    g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000003").one()
    # El dictamen sigue siendo el placeholder de importación...
    assert "Pendiente de análisis" in (g.dictamen or "")
    # ...pero la IA recibe el CONCEPTO real
    texto_ia = _texto_glosa_para_ia(db, g)
    assert "SE RECONOCE A TARIFAS SOAT VIGENTE" in texto_ia
    assert "Pendiente de análisis" not in texto_ia


def test_fallback_compone_desde_bd_si_texto_vacio(db):
    """Glosas importadas ANTES de este fix: texto_glosa_original vacío
    pero conceptos en BD — el auto-responder compone al vuelo."""
    g = GlosaRecord(
        eps="EPS DE PRUEBA",
        factura="HUS0000000004",
        consecutivo_dgh="100004",
        estado="RADICADA",
        dictamen="<div><b>Glosa importada desde recepción.</b> Pendiente de análisis...</div>",
    )
    db.add(g)
    db.flush()
    db.add(
        ConceptoGlosaRecord(
            glosa_id=g.id,
            oid_dgh="900005",
            consecutivo_dgh="100004",
            factura="HUS0000000004",
            codigo_glosa="TA0201",
            nombre_glosa="Tarifas no pactadas",
            cups_codigo="906249",
            valor_objetado=86600.0,
            observacion_eps="IPS SIN CONTRATO SE RECONOCE A TARIFA SOAT",
        )
    )
    db.commit()

    texto_ia = _texto_glosa_para_ia(db, g)
    assert "TA0201" in texto_ia
    assert "IPS SIN CONTRATO SE RECONOCE A TARIFA SOAT" in texto_ia
    assert "Pendiente de análisis" not in texto_ia


def test_sin_conceptos_cae_al_dictamen_como_antes(db):
    g = GlosaRecord(
        eps="EPS DE PRUEBA",
        factura="HUS0000000005",
        estado="RADICADA",
        dictamen="dictamen existente con contenido",
    )
    db.add(g)
    db.commit()
    assert componer_texto_desde_conceptos(db, g) == ""
    assert _texto_glosa_para_ia(db, g) == "dictamen existente con contenido"


def test_reimportacion_no_pisa_texto_manual(db):
    contenido = _excel(
        [_fila_inicial("HUS0000000006", "100006")],
        [_fila_concepto("HUS0000000006", "100006", oid="900006")],
    )
    RecepcionService(db).procesar_excel(contenido)
    g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000006").one()
    assert (g.texto_glosa_original or "").startswith(MARCA_TEXTO_CONCEPTOS)

    # El gestor reemplaza el texto a mano
    g.texto_glosa_original = "TEXTO MANUAL DEL GESTOR — no tocar"
    db.commit()

    # Reimportar el mismo archivo: el texto manual sobrevive
    RecepcionService(db).procesar_excel(contenido)
    db.expire_all()
    g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000006").one()
    assert g.texto_glosa_original == "TEXTO MANUAL DEL GESTOR — no tocar"


def test_reimportacion_actualiza_texto_compilado(db):
    """Si el texto fue compilado por una importación previa (marca), una
    reimportación con observación corregida lo regenera."""
    contenido_v1 = _excel(
        [_fila_inicial("HUS0000000007", "100007")],
        [_fila_concepto("HUS0000000007", "100007", oid="900007", obs="OBSERVACION VIEJA")],
    )
    RecepcionService(db).procesar_excel(contenido_v1)

    contenido_v2 = _excel(
        [_fila_inicial("HUS0000000007", "100007")],
        [_fila_concepto("HUS0000000007", "100007", oid="900007", obs="OBSERVACION CORREGIDA")],
    )
    RecepcionService(db).procesar_excel(contenido_v2)
    db.expire_all()
    g = db.query(GlosaRecord).filter(GlosaRecord.factura == "HUS0000000007").one()
    assert "OBSERVACION CORREGIDA" in (g.texto_glosa_original or "")
    assert "OBSERVACION VIEJA" not in (g.texto_glosa_original or "")
