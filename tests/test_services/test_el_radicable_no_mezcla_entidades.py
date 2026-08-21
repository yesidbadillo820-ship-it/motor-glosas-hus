"""Un Excel radicable se presenta ante UNA entidad (20-08-2026).

Caso real. Yesid importó el lote del 19 de agosto: 35 glosas, de las cuales
**29 son de COOSALUD y 6 del DISPENSARIO MÉDICO / EJÉRCITO**. Descargó el
«Excel radicable» y salió UN archivo:

    RESPUESTA_GLOSAS_COOSALUD_19AGO2026_HUS.xlsx
    encabezado: «CONTRATO 68001C00060340-24»   ← el de COOSALUD
    adentro:    las 35 facturas                ← incluidas las 6 del Ejército

O sea, se le radicaban a COOSALUD **$10.290.042 en facturas de otro pagador**,
bajo un contrato que nada tiene que ver con ellas. COOSALUD lo devuelve, y de
paso el hospital le enseña a una EPS las facturas de otra.

La causa: el archivo se rotulaba con la entidad MÁS FRECUENTE del lote, pero
no se filtraba por ella.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.db import Base, GlosaRecord
from app.services.excel_radicable import (
    entidades_del_lote,
    generar_excel_radicable_con_nombre,
)

COOSALUD = "C240031 - COOSALUD ENTIDAD PROMOTORA DE SALUD S.A. SUBSIDIADO"
EJERCITO = "U220311 - DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA"

# Las 6 facturas del Ejército que se colaban en el radicable de COOSALUD.
FACTURAS_EJERCITO = [
    ("HUS0000538907", 2_319_514),
    ("HUS0000539712", 257_412),
    ("HUS0000538616", 1_980),
    ("HUS0000537794", 4_053_462),
    ("HUS0000538141", 3_269_704),
    ("HUS0000539820", 387_970),
]


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = sessionmaker(bind=engine)()
    # 29 de COOSALUD (mayoría) + las 6 del Ejército, como el lote real.
    for i in range(29):
        sesion.add(
            GlosaRecord(
                eps=COOSALUD,
                factura=f"HUS000053{i:04d}",
                valor_objetado=20_000,
                codigo_glosa="TA2901",
            )
        )
    for factura, valor in FACTURAS_EJERCITO:
        sesion.add(
            GlosaRecord(
                eps=EJERCITO,
                factura=factura,
                valor_objetado=valor,
                codigo_glosa="FA5801",
            )
        )
    sesion.commit()
    yield sesion
    sesion.close()


def _ids(db, eps=None):
    q = db.query(GlosaRecord)
    if eps:
        q = q.filter(GlosaRecord.eps == eps)
    return [g.id for g in q.all()]


def _facturas_del_xlsx(contenido: bytes) -> set[str]:
    import io

    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    ws = wb["RESPUESTA GLOSAS"]
    salida = set()
    for fila in ws.iter_rows(values_only=True):
        for celda in fila:
            texto = str(celda or "").strip()
            if texto.startswith("HUS") and texto[3:].isdigit():
                salida.add(texto)
    return salida


class TestElLoteSabeCuantasEntidadesTrae:
    def test_reconoce_las_dos(self, db):
        entidades = entidades_del_lote(db, glosa_ids=_ids(db))
        assert len(entidades) == 2
        assert {e["eps"] for e in entidades} == {COOSALUD, EJERCITO}

    def test_y_cuantas_facturas_de_cada_una(self, db):
        por_eps = {e["eps"]: e["glosas"] for e in entidades_del_lote(db, glosa_ids=_ids(db))}
        assert por_eps[COOSALUD] == 29
        assert por_eps[EJERCITO] == 6

    def test_un_lote_de_una_sola_entidad_devuelve_una(self, db):
        entidades = entidades_del_lote(db, glosa_ids=_ids(db, EJERCITO))
        assert len(entidades) == 1
        assert entidades[0]["eps"] == EJERCITO


class TestNoSeLeRadicaAUnaEpsLoDeOtra:
    """El defecto que costaba $10.290.042 mal radicados."""

    def test_el_radicable_de_coosalud_no_trae_facturas_del_ejercito(self, db):
        contenido, nombre = generar_excel_radicable_con_nombre(
            db, glosa_ids=_ids(db), eps_filtro=COOSALUD
        )
        facturas = _facturas_del_xlsx(contenido)
        coladas = [f for f, _ in FACTURAS_EJERCITO if f in facturas]
        assert not coladas, (
            f"Facturas del Ejército dentro del radicable de COOSALUD: {coladas}. "
            "Se le estaría radicando a una EPS lo de otro pagador."
        )

    def test_pero_si_trae_las_de_coosalud(self, db):
        """La otra mitad: filtrar de más dejaría al hospital sin radicar."""
        contenido, _ = generar_excel_radicable_con_nombre(
            db, glosa_ids=_ids(db), eps_filtro=COOSALUD
        )
        assert len(_facturas_del_xlsx(contenido)) == 29

    def test_el_del_ejercito_trae_las_seis_y_solo_esas(self, db):
        contenido, nombre = generar_excel_radicable_con_nombre(
            db, glosa_ids=_ids(db), eps_filtro=EJERCITO
        )
        facturas = _facturas_del_xlsx(contenido)
        assert facturas == {f for f, _ in FACTURAS_EJERCITO}

    def test_el_nombre_del_archivo_dice_de_quien_es(self, db):
        _, nombre_coo = generar_excel_radicable_con_nombre(
            db, glosa_ids=_ids(db), eps_filtro=COOSALUD
        )
        _, nombre_eje = generar_excel_radicable_con_nombre(
            db, glosa_ids=_ids(db), eps_filtro=EJERCITO
        )
        assert nombre_coo != nombre_eje, (
            "Los dos radicables se llamarían igual y uno pisaría al otro en la carpeta de descargas"
        )

    def test_sin_filtro_se_conserva_el_comportamiento_de_antes(self, db):
        """El filtro es opcional: quien no lo pase recibe lo de siempre. Así
        ningún llamador viejo cambia de golpe."""
        contenido, _ = generar_excel_radicable_con_nombre(db, glosa_ids=_ids(db))
        assert len(_facturas_del_xlsx(contenido)) == 35
