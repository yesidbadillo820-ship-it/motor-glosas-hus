"""Acta de Desacuerdo: la constancia que escala el caso a la Supersalud
(V2, Pilar 5, 03-09-2026).

Cuando la entidad ratifica y la IPS sostiene su respuesta, el camino es la mesa
de conciliación y, sin acuerdo, la Superintendencia (Arts. 57 y 126, Ley
1438/2011). El acta que documenta ese desacuerdo se armaba a mano; ahora el
motor la estructura solo, con los datos REALES del registro.

Reglas que se prueban: no se inventa nada (lo que falta queda en blanco y se
informa), solo aplica a glosas en ratificación/conciliación (a una inicial no
se le fabrica un desacuerdo), y el PDF trae el caso, la mesa y el escalamiento.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pymupdf
import pytest

from app.services.acta_desacuerdo import (
    datos_acta_desacuerdo,
    etapa_procesal_de,
    exige_mesa,
    generar_pdf_acta_desacuerdo,
)


def _glosa(**kw):
    base = dict(
        id=7,
        factura="HUS0000605555",
        eps="COOSALUD",
        codigo_glosa="FA0101",
        valor_objetado=800000.0,
        valor_aceptado=0.0,
        etapa="RESPUESTA A GLOSA",
        numero_radicado="RAD-123",
        fecha_recepcion=datetime(2026, 9, 1),
        texto_glosa_original="RESPUESTA A CONCILIACION. SE RATIFICA LA GLOSA INICIAL.",
        dictamen="",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _texto_pdf(pdf: bytes) -> str:
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return "".join(p.get_text() for p in doc)


class TestCuandoAplica:
    def test_una_ratificacion_exige_mesa(self):
        g = _glosa(texto_glosa_original="LA EPS RATIFICA LA GLOSA POR SOPORTES.")
        assert etapa_procesal_de(g) == "RATIFICACION"
        assert exige_mesa(g)

    def test_una_conciliacion_exige_mesa(self):
        assert exige_mesa(_glosa())  # «RESPUESTA A CONCILIACION» en el texto

    def test_el_campo_etapa_tambien_cuenta(self):
        g = _glosa(texto_glosa_original="TA0201 MAYOR VALOR", etapa="RATIFICACION")
        assert exige_mesa(g)

    def test_a_una_glosa_inicial_no_se_le_fabrica_desacuerdo(self):
        g = _glosa(texto_glosa_original="TA0201 MAYOR VALOR COBRADO SEGUN CONTRATO")
        assert exige_mesa(g) is False


class TestLosDatosNoSeInventan:
    def test_todo_sale_del_registro(self):
        d = datos_acta_desacuerdo(_glosa())
        assert d["factura"] == "HUS0000605555"
        assert d["eps"] == "COOSALUD"
        assert d["codigo_glosa"] == "FA0101"
        assert d["valor_objetado"] == "$800.000"
        assert d["fecha_recepcion"] == "01/09/2026"
        assert d["faltantes"] == []

    def test_lo_que_falta_queda_en_blanco_y_se_informa(self):
        d = datos_acta_desacuerdo(_glosa(factura="N/A", codigo_glosa=None, valor_objetado=0))
        assert d["factura"] == "" and d["codigo_glosa"] == ""
        assert "número de factura" in d["faltantes"]
        assert "código de la glosa" in d["faltantes"]
        assert "valor objetado" in d["faltantes"]


class TestElPdfFirmable:
    def test_trae_el_caso_la_mesa_y_el_escalamiento(self):
        texto = _texto_pdf(generar_pdf_acta_desacuerdo(datos_acta_desacuerdo(_glosa())))
        for esperado in [
            "ACTA DE DESACUERDO",
            "HUS0000605555",
            "COOSALUD",
            "FA0101",
            "$800.000",
            "MESA DE CONCILIACIÓN",
            "SUPERINTENDENCIA NACIONAL DE SALUD",
            "Artículo 57",
            "126",
        ]:
            assert esperado in texto, f"al acta le falta {esperado!r}"

    def test_las_firmas_quedan_en_blanco(self):
        texto = _texto_pdf(generar_pdf_acta_desacuerdo(datos_acta_desacuerdo(_glosa())))
        assert "Por la E.S.E. HUS" in texto
        assert "Por la entidad responsable de pago" in texto
        assert "______" in texto  # líneas para firmar: el acta la firman personas

    def test_con_faltantes_deja_la_nota_interna(self):
        d = datos_acta_desacuerdo(_glosa(factura=None))
        texto = _texto_pdf(generar_pdf_acta_desacuerdo(d))
        assert "diligenciar a mano" in texto
        assert "número de factura" in texto

    def test_fecha_del_acta_controlable(self):
        texto = _texto_pdf(
            generar_pdf_acta_desacuerdo(datos_acta_desacuerdo(_glosa()), hoy=datetime(2026, 9, 3))
        )
        assert "03/09/2026" in texto


class TestElEndpoint:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.api.deps import get_auditor_o_superior, get_usuario_actual
        from app.database import Base, get_db
        from app.main import app
        from app.models.db import UsuarioRecord

        eng = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(eng)
        Sesion = sessionmaker(bind=eng)
        sesion = Sesion()
        usuario = UsuarioRecord(id=1, email="a@hus.gov.co", nombre="A", rol="AUDITOR", activo=1)

        app.dependency_overrides[get_db] = lambda: iter([sesion]).__next__()
        app.dependency_overrides[get_usuario_actual] = lambda: usuario
        app.dependency_overrides[get_auditor_o_superior] = lambda: usuario
        with TestClient(app) as c:
            yield c, sesion
        app.dependency_overrides.clear()
        sesion.close()
        eng.dispose()

    def _guardar(self, sesion, **kw):
        from app.models.db import GlosaRecord

        base = dict(
            eps="COOSALUD",
            factura="HUS0000605555",
            codigo_glosa="FA0101",
            valor_objetado=800000.0,
            etapa="RESPUESTA A GLOSA",
            estado="ABIERTA",
            texto_glosa_original="RESPUESTA A CONCILIACION. SE RATIFICA LA GLOSA INICIAL.",
        )
        base.update(kw)
        g = GlosaRecord(**base)
        sesion.add(g)
        sesion.commit()
        return g

    def test_descarga_el_pdf_para_una_ratificada(self, client):
        c, sesion = client
        g = self._guardar(sesion)
        r = c.get(f"/conciliaciones/acta-desacuerdo/{g.id}/pdf")
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/pdf")
        assert "HUS0000605555" in _texto_pdf(r.content)

    def test_glosa_inicial_es_409(self, client):
        c, sesion = client
        g = self._guardar(sesion, texto_glosa_original="TA0201 MAYOR VALOR SEGUN CONTRATO")
        assert c.get(f"/conciliaciones/acta-desacuerdo/{g.id}/pdf").status_code == 409

    def test_glosa_inexistente_es_404(self, client):
        c, _ = client
        assert c.get("/conciliaciones/acta-desacuerdo/999999/pdf").status_code == 404
