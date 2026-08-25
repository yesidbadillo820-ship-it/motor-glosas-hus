"""La bitácora del detallado ADRES lee los pesos en los dos formatos.

19-08-2026. `importar_bitacora` leía los valores con
`float(str(v).replace(",", "."))`. Eso sirve para el CSV tal como lo escribe el
ajustador (`93340.00`), pero si el auditor abre esa bitácora en Excel y la
guarda, Excel la reescribe al formato colombiano y entonces:

    "93.340"       ->    93.34   (mil veces menos)
    "1.589.100,00" ->     0.0    ¡y en silencio!, por el `except ValueError`

Esos valores son el glosado / reclamado / aprobado de cada ítem del detallado
del paquete ADRES: son la plata que el hospital reclama.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import ItemDetalladoAdresRecord, PaqueteAdresRecord
from app.services.preauditoria_adres import importar_bitacora

CABECERA = (
    "FACTURA;HOJA;GRUPO;CODIGO;NOMBRE;CANT_ORIGINAL;VR_ENT_ORIGINAL;VALOR_RECLAMADO;"
    "VALOR_APROBADO;VALOR_GLOSADO;ACCION;CANT_NUEVA;VR_ENT_NUEVO;CRUCE_POR;"
    "FILAS_REPORTE;CAUSALES_GLOSA;TIPO_RENGLON;OBSERVACION"
)


def _csv(valor_glosado: str, valor_reclamado: str = "0") -> bytes:
    fila = (
        f"HUS468334;h1;G;C1;SERVICIO;1;0;{valor_reclamado};0;{valor_glosado};"
        "AJUSTADA;1;0;codigo;1;TA01;normal;obs"
    )
    return ("\n".join([CABECERA, fila])).encode("utf-8-sig")


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    s.add(PaqueteAdresRecord(id=1, numero_paquete="31068"))
    s.commit()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _glosado(db, contenido: bytes) -> float:
    db.query(ItemDetalladoAdresRecord).delete()
    db.commit()
    importar_bitacora(db, contenido, paquete_id=1)
    item = db.query(ItemDetalladoAdresRecord).first()
    assert item is not None, "no se importó ningún ítem"
    return float(item.valor_glosado)


class TestLosDosFormatos:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("93340", 93_340.0),  # entero pelado
            ("93340.00", 93_340.0),  # el que escribe el ajustador — no debe cambiar
            ("93340,50", 93_340.5),  # coma decimal
            ("93.340", 93_340.0),  # colombiano: antes daba 93,34
            ("1.589.100", 1_589_100.0),  # antes daba 0.0 en silencio
            ("1.589.100,00", 1_589_100.0),  # antes daba 0.0 en silencio
        ],
    )
    def test_valor_glosado(self, db, texto, esperado):
        assert _glosado(db, _csv(texto)) == esperado

    def test_el_formato_del_ajustador_no_cambio(self, db):
        """Lo que ya funcionaba tiene que seguir igual."""
        assert _glosado(db, _csv("93340.00", "280000.00")) == 93_340.0

    def test_el_millon_ya_no_se_vuelve_cero(self, db):
        """El caso más peligroso: fallaba callado y el ítem quedaba en $0."""
        assert _glosado(db, _csv("1.589.100,00")) != 0.0

    def test_vacio_sigue_siendo_cero(self, db):
        assert _glosado(db, _csv("")) == 0.0

    def test_basura_no_revienta_la_importacion(self, db):
        assert _glosado(db, _csv("no es un numero")) == 0.0
