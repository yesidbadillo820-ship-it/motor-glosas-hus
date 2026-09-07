"""Subir el reparto del área: quién audita cada factura del paquete.

02-09-2026. Yesid mandó la tabla con la que el área repartió el paquete 31078:

    FACTURA      PROFESIONAL        TECNICO
    HUS405724    JEFE LAURA         OSCAR
    HUS406048    SIN PERTINENCIA    CAROLINA

El TÉCNICO es el gestor de cuentas y el PROFESIONAL la médica auditora. Ese
reparto existía en un Excel del área, pero no había por dónde subirlo: por eso
las 81 facturas del 31078 salían «(sin gestor asignado)» en el informe.

Se prueba con el archivo de verdad (xlsx y csv), sobre una base en memoria.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database import Base
from app.models.db import FacturaAdresRecord, GlosaAdresRecord, PaqueteAdresRecord
from app.services.preauditoria_adres import (
    importar_reparto,
    leer_reparto_de_archivo,
    normalizar_factura,
)

# El sistema guarda la factura con la clave normalizada: «HUS405724» y
# «HUS0000405724» son la misma, y por dentro se llaman «405724».
CLAVE = normalizar_factura

# Un pedazo de la tabla real que mandó el área.
REPARTO = [
    ("HUS405724", "JEFE LAURA", "OSCAR "),
    ("HUS405882", "JEFE LEYDY", "CAROLINA"),
    ("HUS406048", "SIN PERTINENCIA", "CAROLINA"),
    ("HUS406125", "JEFE LEYDY", "OSCAR "),
]


def _xlsx(filas, encabezado=("FACTURA", "PROFESIONAL", "TECNICO")) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(list(encabezado))
    for f in filas:
        ws.append(list(f))
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _csv(filas, encabezado=("FACTURA", "PROFESIONAL", "TECNICO")) -> bytes:
    lineas = [";".join(encabezado)] + [";".join(f) for f in filas]
    return ("\n".join(lineas)).encode("utf-8")


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as sesion:
        paquete = PaqueteAdresRecord(numero_paquete="31078", archivo="reporte.xlsx")
        sesion.add(paquete)
        sesion.flush()
        pid = paquete.id
        for numero, _, _ in REPARTO:
            sesion.add(
                FacturaAdresRecord(paquete_id=pid, factura_clave=CLAVE(numero), factura=numero)
            )
            for n in (1, 2):
                sesion.add(
                    GlosaAdresRecord(
                        paquete_id=pid,
                        factura_clave=CLAVE(numero),
                        factura=numero,
                        codigo=f"39{n:03d}",
                        valor_glosado=100.0,
                    )
                )
        # Una factura del paquete que el área no repartió.
        sesion.add(
            FacturaAdresRecord(
                paquete_id=pid, factura_clave=CLAVE("HUS999999"), factura="HUS999999"
            )
        )
        sesion.commit()
        sesion.info["pid"] = pid
        yield sesion


class TestLeerElArchivo:
    def test_reconoce_tecnico_y_profesional(self):
        r = leer_reparto_de_archivo(_xlsx(REPARTO), "reparto.xlsx")
        assert r[CLAVE("HUS405724")] == ("OSCAR", "JEFE LAURA")
        assert len(r) == 4

    def test_le_quita_los_espacios_de_mas(self):
        """El área escribe «OSCAR » con espacio al final."""
        assert leer_reparto_de_archivo(_xlsx(REPARTO), "r.xlsx")[CLAVE("HUS406125")][0] == "OSCAR"

    def test_tambien_entiende_gestor_y_medico(self):
        r = leer_reparto_de_archivo(_xlsx(REPARTO, ("FACTURA", "MEDICO", "GESTOR")), "r.xlsx")
        assert r[CLAVE("HUS405882")] == ("CAROLINA", "JEFE LEYDY")

    def test_lee_csv_igual_que_excel(self):
        assert leer_reparto_de_archivo(_csv(REPARTO), "reparto.csv") == leer_reparto_de_archivo(
            _xlsx(REPARTO), "reparto.xlsx"
        )

    def test_la_factura_con_ceros_es_la_misma(self):
        r = leer_reparto_de_archivo(_xlsx([("HUS0000405724", "DRA ZULAY", "OSCAR")]), "r.xlsx")
        assert CLAVE("HUS405724") in r

    def test_sin_encabezado_reconocible_lo_dice_claro(self):
        with pytest.raises(ValueError, match="encabezado"):
            leer_reparto_de_archivo(_xlsx(REPARTO, ("UNO", "DOS", "TRES")), "r.xlsx")


class TestSubirloAlPaquete:
    def test_pone_gestor_y_medico_en_la_factura(self, db):
        r = importar_reparto(db, _xlsx(REPARTO), paquete_id=db.info["pid"], nombre_archivo="r.xlsx")
        f = db.query(FacturaAdresRecord).filter_by(factura_clave=CLAVE("HUS405724")).one()
        assert (f.gestor, f.medico) == ("OSCAR", "JEFE LAURA")
        assert r["facturas_actualizadas"] == 4
        assert r["en_el_archivo"] == 4

    def test_los_renglones_llevan_el_reparto_de_su_factura(self, db):
        """Para que la hoja POR GESTOR del informe reparta de verdad."""
        r = importar_reparto(db, _xlsx(REPARTO), paquete_id=db.info["pid"])
        glosas = db.query(GlosaAdresRecord).filter_by(factura_clave=CLAVE("HUS405882")).all()
        assert {(g.gestor, g.medico) for g in glosas} == {("CAROLINA", "JEFE LEYDY")}
        assert r["glosas_actualizadas"] == 8

    def test_sin_pertinencia_se_guarda_tal_cual_pero_no_es_una_medica(self, db):
        """Es la anotación del área, no una persona: se respeta el texto."""
        r = importar_reparto(db, _xlsx(REPARTO), paquete_id=db.info["pid"])
        f = db.query(FacturaAdresRecord).filter_by(factura_clave=CLAVE("HUS406048")).one()
        assert f.medico == "SIN PERTINENCIA"
        assert "SIN PERTINENCIA" not in r["medicos"]
        assert r["sin_pertinencia"] == 1
        assert r["medicos"] == ["JEFE LAURA", "JEFE LEYDY"]
        assert r["gestores"] == ["CAROLINA", "OSCAR"]

    def test_avisa_las_facturas_del_paquete_que_nadie_repartio(self, db):
        r = importar_reparto(db, _xlsx(REPARTO), paquete_id=db.info["pid"])
        assert r["sin_asignar"] == [CLAVE("HUS999999")]

    def test_avisa_lo_que_viene_en_el_archivo_y_no_esta_en_el_paquete(self, db):
        extra = REPARTO + [("HUS123456", "DRA ZULAY", "OSCAR")]
        r = importar_reparto(db, _xlsx(extra), paquete_id=db.info["pid"])
        assert r["no_estan_en_el_paquete"] == [CLAVE("HUS123456")]

    def test_una_celda_vacia_no_borra_lo_que_ya_estaba(self, db):
        importar_reparto(db, _xlsx(REPARTO), paquete_id=db.info["pid"])
        importar_reparto(db, _xlsx([("HUS405724", "", "")]), paquete_id=db.info["pid"])
        f = db.query(FacturaAdresRecord).filter_by(factura_clave=CLAVE("HUS405724")).one()
        assert (f.gestor, f.medico) == ("OSCAR", "JEFE LAURA")

    def test_volver_a_subir_el_mismo_reparto_no_cambia_nada(self, db):
        importar_reparto(db, _xlsx(REPARTO), paquete_id=db.info["pid"])
        r = importar_reparto(db, _xlsx(REPARTO), paquete_id=db.info["pid"])
        assert r["facturas_actualizadas"] == 0
        assert r["glosas_actualizadas"] == 0

    def test_corregir_el_reparto_lo_pisa(self, db):
        importar_reparto(db, _xlsx(REPARTO), paquete_id=db.info["pid"])
        importar_reparto(
            db, _xlsx([("HUS405724", "DRA ZULAY", "CAROLINA")]), paquete_id=db.info["pid"]
        )
        f = db.query(FacturaAdresRecord).filter_by(factura_clave=CLAVE("HUS405724")).one()
        assert (f.gestor, f.medico) == ("CAROLINA", "DRA ZULAY")

    def test_no_toca_otro_paquete(self, db):
        otro = PaqueteAdresRecord(numero_paquete="31073", archivo="otro.xlsx")
        db.add(otro)
        db.flush()
        db.add(
            FacturaAdresRecord(
                paquete_id=otro.id, factura_clave=CLAVE("HUS405724"), factura="HUS405724"
            )
        )
        db.commit()
        importar_reparto(db, _xlsx(REPARTO), paquete_id=db.info["pid"])
        ajena = db.query(FacturaAdresRecord).filter_by(paquete_id=otro.id).one()
        assert not ajena.gestor

    def test_un_archivo_sin_facturas_lo_dice(self, db):
        with pytest.raises(ValueError, match="ninguna factura"):
            importar_reparto(db, _xlsx([]), paquete_id=db.info["pid"])
