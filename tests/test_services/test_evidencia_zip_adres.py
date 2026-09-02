"""El PDF de evidencia no se cae, y se pueden bajar todos en un ZIP.

02-09-2026. Yesid, con la factura HUS414206 en pantalla: el botón «PDF de
evidencia» respondió «No se pudo generar el PDF · HTTP 502», y pidió además
«que salga una opción de descargar el PDF también de forma masiva y me quede
en un zip con todas las facturas, un pdf por factura».

Con 81 facturas en el paquete 31078, bajarlos de a uno es un día de trabajo.

Se prueban tres cosas:

  · que la plata que llega como texto ya no reviente el PDF (era un
    `TypeError` que el gestor veía como un error del servidor);
  · que el ZIP traiga un PDF por factura y que **una factura mala no deje sin
    evidencia a las demás**;
  · que armar el paquete completo dé exactamente lo mismo que pedir factura
    por factura, sin una consulta por factura.
"""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.database import Base
from app.models.db import FacturaAdresRecord, GlosaAdresRecord, PaqueteAdresRecord
from app.services.evidencia_adres_pdf import (
    generar_pdf_evidencia,
    generar_zip_evidencias,
    nombre_archivo_evidencia,
    nombre_archivo_zip,
)
from app.services.preauditoria_adres import (
    consultar_factura,
    datos_evidencia_del_paquete,
    normalizar_factura,
)

BASE_GLOSA = dict(
    glosa_total=False,
    valor_glosado=678700.0,
    valor_aceptado=0.0,
    descripcion="Columna cervical, dorsal o lumbar (hasta tres espacios)",
    causal_codigo="3209",
    causal_texto="3209- La ayuda diagnóstica no tiene justificación",
    decision="SE OBJETA",
    observacion_tecnico="SE OBJETA, AYUDA DIAGNOSTICA QUE SE ENCUENTRA JUSTIFICADA",
    cuenta_valor=True,
)


def _datos(glosas, factura="HUS414206"):
    return {
        "factura": factura,
        "radicacion": "14408630",
        "documento_paciente": "CC-1094247405",
        "glosas": glosas,
        "resumen": {"valor_glosado": 1549820, "valor_aceptado": 920, "pendientes": 0},
    }


class TestLaPlataQueLlegaComoTexto:
    """Era el `TypeError` que dejaba al gestor sin PDF."""

    def test_valor_glosado_como_texto_no_revienta(self):
        g = dict(BASE_GLOSA, valor_glosado="678.700")
        assert len(generar_pdf_evidencia(_datos([g]))) > 1000

    def test_valor_aceptado_como_texto_no_revienta(self):
        g = dict(BASE_GLOSA, valor_aceptado="920")
        assert len(generar_pdf_evidencia(_datos([g]))) > 1000

    def test_todo_vacio_no_revienta(self):
        g = {k: None for k in BASE_GLOSA}
        assert len(generar_pdf_evidencia(_datos([g]))) > 1000

    def test_una_factura_sin_glosas_igual_da_pdf(self):
        assert len(generar_pdf_evidencia(_datos([]))) > 1000

    def test_una_respuesta_larguisima_igual_da_pdf(self):
        g = dict(BASE_GLOSA, observacion_tecnico="JUSTIFICADA POR EL CUADRO CLINICO. " * 400)
        assert len(generar_pdf_evidencia(_datos([g]))) > 1000


class TestElZip:
    def test_trae_un_pdf_por_factura(self):
        facturas = [_datos([dict(BASE_GLOSA)], f"HUS40{n}") for n in range(5)]
        contenido, novedades = generar_zip_evidencias(facturas)
        assert not novedades
        with zipfile.ZipFile(BytesIO(contenido)) as zf:
            nombres = zf.namelist()
        assert len(nombres) == 5
        assert nombre_archivo_evidencia("HUS401") in nombres
        assert all(n.endswith(".pdf") for n in nombres)

    def test_cada_pdf_es_un_pdf_de_verdad(self):
        contenido, _ = generar_zip_evidencias([_datos([dict(BASE_GLOSA)])])
        with zipfile.ZipFile(BytesIO(contenido)) as zf:
            crudo = zf.read(zf.namelist()[0])
        assert crudo.startswith(b"%PDF")

    def test_una_factura_mala_no_deja_sin_evidencia_a_las_demas(self):
        """La regla: un error en una no puede tumbar las otras ochenta."""

        class Explota(dict):
            def get(self, *a, **k):
                raise RuntimeError("dato corrupto")

        facturas = [
            _datos([dict(BASE_GLOSA)], "HUS1"),
            Explota(factura="HUS2"),
            _datos([dict(BASE_GLOSA)], "HUS3"),
        ]
        contenido, novedades = generar_zip_evidencias(facturas)
        with zipfile.ZipFile(BytesIO(contenido)) as zf:
            nombres = zf.namelist()
            aviso = zf.read("NOVEDADES.txt").decode("utf-8")
        assert nombre_archivo_evidencia("HUS1") in nombres
        assert nombre_archivo_evidencia("HUS3") in nombres
        assert len(novedades) == 1
        assert "dato corrupto" in aviso

    def test_dos_facturas_con_el_mismo_nombre_no_se_pisan(self):
        contenido, _ = generar_zip_evidencias([_datos([], "HUS1"), _datos([], "HUS1")])
        with zipfile.ZipFile(BytesIO(contenido)) as zf:
            assert len(zf.namelist()) == 2

    def test_el_nombre_del_zip_lleva_el_paquete(self):
        assert nombre_archivo_zip("31078") == "RTA_ADRES_PAQ_31078_EVIDENCIAS.zip"
        assert nombre_archivo_zip("") == "RTA_ADRES_PAQUETE_EVIDENCIAS.zip"


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as sesion:
        paquete = PaqueteAdresRecord(numero_paquete="31078", archivo="r.xlsx")
        sesion.add(paquete)
        sesion.flush()
        pid = paquete.id
        for n, estado in ((1, "CERRADA"), (2, "EN PROCESO"), (3, "PENDIENTE")):
            numero = f"HUS41420{n}"
            sesion.add(
                FacturaAdresRecord(
                    paquete_id=pid,
                    factura_clave=normalizar_factura(numero),
                    factura=numero,
                    radicacion="14408630",
                    doc_victima="CC-1094247405",
                    estado=estado,
                )
            )
            for i in range(3):
                sesion.add(
                    GlosaAdresRecord(
                        paquete_id=pid,
                        factura_clave=normalizar_factura(numero),
                        factura=numero,
                        radicacion="14408630",
                        doc_victima="CC-1094247405",
                        codigo=f"2170{i}",
                        **BASE_GLOSA,
                    )
                )
            # Una glosa total: no se responde ítem por ítem.
            sesion.add(
                GlosaAdresRecord(
                    paquete_id=pid,
                    factura_clave=normalizar_factura(numero),
                    factura=numero,
                    codigo="X",
                    **{**BASE_GLOSA, "glosa_total": True},
                )
            )
        sesion.commit()
        sesion.info["pid"] = pid
        yield sesion


class TestArmarloDesdeElPaquete:
    def test_una_entrada_por_factura(self, db):
        datos = datos_evidencia_del_paquete(db, db.info["pid"])
        assert [d["factura"] for d in datos] == ["HUS414201", "HUS414202", "HUS414203"]

    def test_deja_por_fuera_las_glosas_totales(self, db):
        d = datos_evidencia_del_paquete(db, db.info["pid"])[0]
        assert len(d["glosas"]) == 3
        assert d["resumen"]["glosas_totales_ocultas"] == 1

    def test_da_lo_mismo_que_pedir_factura_por_factura(self, db):
        """El ZIP y el botón de una factura tienen que decir lo mismo."""
        pid = db.info["pid"]
        for masivo in datos_evidencia_del_paquete(db, pid):
            uno = consultar_factura(db, masivo["factura"], paquete_id=pid)
            assert masivo["radicacion"] == uno["radicacion"]
            assert masivo["documento_paciente"] == uno["documento_paciente"]
            assert len(masivo["glosas"]) == len(uno["glosas"])
            for clave in (
                "valor_glosado",
                "valor_aceptado",
                "pendientes",
                "glosas_totales_ocultas",
            ):
                assert masivo["resumen"][clave] == uno["resumen"][clave], clave

    def test_se_puede_pedir_solo_un_estado(self, db):
        datos = datos_evidencia_del_paquete(db, db.info["pid"], estado="CERRADA")
        assert [d["factura"] for d in datos] == ["HUS414201"]

    def test_un_paquete_vacio_devuelve_lista_vacia(self, db):
        assert datos_evidencia_del_paquete(db, 999) == []

    def test_no_hace_una_consulta_por_factura(self, db):
        """Con 81 facturas, una consulta por factura son cientos de viajes."""
        consultas = []
        event.listen(db.get_bind(), "before_cursor_execute", lambda *a, **k: consultas.append(1))
        datos_evidencia_del_paquete(db, db.info["pid"])
        assert len(consultas) <= 3, f"hizo {len(consultas)} consultas"

    def test_el_zip_del_paquete_sale_completo(self, db):
        datos = datos_evidencia_del_paquete(db, db.info["pid"])
        contenido, novedades = generar_zip_evidencias(datos)
        assert not novedades
        with zipfile.ZipFile(BytesIO(contenido)) as zf:
            assert len(zf.namelist()) == 3
            assert zf.read(zf.namelist()[0]).startswith(b"%PDF")
