"""Centro de Automatización: el auditor corre las herramientas sin consola.

Hasta ahora las 34 herramientas de `tools/` solo se usaban copiando el guion
a un PC con Python. Estas pruebas verifican lo único que importa: que subir
el Excel del pagador por la aplicación devuelva el archivo del ERP, con el
contenido correcto.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import ROL_AUDITOR, ROL_VIEWER, UsuarioRecord

openpyxl = pytest.importorskip("openpyxl")


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        yield s
    finally:
        s.close()
        engine.dispose()


def _usuario(rol=ROL_AUDITOR):
    return UsuarioRecord(id=1, email="ana@hus.com", nombre="Ana Torres", rol=rol, activo=1)


@pytest.fixture
def cliente(db_session):
    from app.api.deps import get_usuario_actual
    from app.main import app

    estado = {"usuario": _usuario()}
    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: estado["usuario"]
    with TestClient(app) as c:
        c.estado = estado
        yield c
    app.dependency_overrides.clear()


def _excel_savia() -> bytes:
    """Un Excel con el layout real de SAVIA: 8 columnas, dos facturas.

    Los valores llevan centavos a propósito: es el caso que el bot leía
    multiplicado por cien antes de converger los lectores de pesos.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        [
            "Numero_factura",
            "Cod_Servicio",
            "Servicio",
            "Cantidad_Servicio",
            "Valor_Unitario",
            "Valor_Glosa",
            "Motivo_Esp_Glosa_Valor_A",
            "Observacion_Glosa_A",
        ]
    )
    ws.append(["HUS443697", "890201", "CONSULTA", 1, "50.000", "1.365,50", "TA08", "Tarifa"])
    ws.append(["HUS443697", "890301", "CONTROL", 2, "30.000", "60.000", "FA01", "Facturación"])
    ws.append(["HUS503425", "890201", "CONSULTA", 1, "50.000", "950.000", "SO61", "Soportes"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TestCatalogo:
    def test_el_auditor_ve_lo_que_puede_correr(self, cliente):
        d = cliente.get("/automatizaciones").json()
        assert d["total"] >= 4
        ids = {a["id"] for g in d["grupos"] for a in g["automatizaciones"]}
        assert "objeciones-savia" in ids

    def test_cada_ficha_dice_para_que_sirve(self, cliente):
        """Un catálogo sin 'cuándo usarla' obliga a preguntarle a alguien."""
        d = cliente.get("/automatizaciones").json()
        for g in d["grupos"]:
            for a in g["automatizaciones"]:
                assert a["que_hace"].strip()
                assert a["cuando_usarla"].strip()
                assert a["extensiones"]

    def test_el_viewer_no_entra(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        assert cliente.get("/automatizaciones").status_code == 403


class TestCorridaReal:
    """La prueba que importa: entra el Excel del pagador, sale el del ERP."""

    def _ejecutar(self, cliente, opciones=None):
        return cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("SAVIA_SALUD.xlsx", _excel_savia(), "application/vnd.ms-excel")},
            data={"opciones": json.dumps(opciones or {})},
        )

    def test_devuelve_un_archivo_por_factura(self, cliente):
        r = self._ejecutar(cliente)
        assert r.status_code == 200, r.text
        assert r.headers["X-Archivos-Generados"] == "2"
        nombres = zipfile.ZipFile(io.BytesIO(r.content)).namelist()
        assert any("443697" in n for n in nombres)
        assert any("503425" in n for n in nombres)

    def test_el_archivo_trae_las_16_columnas_del_erp(self, cliente):
        r = self._ejecutar(cliente)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        wb = openpyxl.load_workbook(io.BytesIO(z.read(z.namelist()[0])))
        encabezados = [c.value for c in wb["OBJECIONES"][1]]
        assert len(encabezados) == 16
        assert encabezados[0] == "CDCONSEC"
        assert "CROVALOBJ" in encabezados

    def test_el_valor_con_centavos_no_se_infla(self, cliente):
        """`1.365,50` tiene que salir 1.365, no 136.550.

        Es el bug del ×100 verificado de punta a punta: desde el Excel que
        sube el auditor hasta la celda del archivo que se carga al ERP.
        """
        r = self._ejecutar(cliente)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        nombre = next(n for n in z.namelist() if "443697" in n)
        wb = openpyxl.load_workbook(io.BytesIO(z.read(nombre)))
        ws = wb["OBJECIONES"]
        col = [c.value for c in ws[1]].index("CROVALOBJ")
        valores = [ws.cell(row=f, column=col + 1).value for f in range(2, ws.max_row + 1)]
        assert 1365 in valores
        assert 136550 not in valores

    def test_el_valor_con_punto_de_miles_no_se_divide(self, cliente):
        """`950.000` son novecientos cincuenta mil, no novecientos cincuenta."""
        r = self._ejecutar(cliente)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        nombre = next(n for n in z.namelist() if "503425" in n)
        wb = openpyxl.load_workbook(io.BytesIO(z.read(nombre)))
        ws = wb["OBJECIONES"]
        col = [c.value for c in ws[1]].index("CROVALOBJ")
        assert ws.cell(row=2, column=col + 1).value == 950000

    def test_los_parametros_llegan_a_la_herramienta(self, cliente):
        """El sufijo del código lo elige el auditor en la pantalla."""
        r = self._ejecutar(cliente, {"codigo_sufijo": "07"})
        z = zipfile.ZipFile(io.BytesIO(r.content))
        wb = openpyxl.load_workbook(io.BytesIO(z.read(z.namelist()[0])))
        ws = wb["OBJECIONES"]
        col = [c.value for c in ws[1]].index("CRNCONOBJ")
        codigos = {ws.cell(row=f, column=col + 1).value for f in range(2, ws.max_row + 1)}
        assert any(str(c).endswith("07") for c in codigos)


class TestErroresQueSeExplican:
    """Un error que no dice qué hacer obliga al auditor a llamar a alguien."""

    def test_extension_equivocada(self, cliente):
        r = cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("glosas.pdf", b"%PDF-1.4", "application/pdf")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 400
        assert ".xlsx" in r.json()["detail"]

    def test_archivo_vacio(self, cliente):
        r = cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("vacio.xlsx", b"", "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 400
        assert "vac" in r.json()["detail"].lower()

    def test_automatizacion_inexistente(self, cliente):
        r = cliente.post(
            "/automatizaciones/no-existe/ejecutar",
            files={"archivo": ("x.xlsx", b"x", "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 404

    def test_el_viewer_no_ejecuta(self, cliente):
        cliente.estado["usuario"] = _usuario(rol=ROL_VIEWER)
        r = cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("x.xlsx", _excel_savia(), "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        assert r.status_code == 403


class TestQuedaEnAuditoria:
    def test_se_registra_quien_corrio_que(self, cliente, db_session):
        cliente.post(
            "/automatizaciones/objeciones-savia/ejecutar",
            files={"archivo": ("SAVIA.xlsx", _excel_savia(), "application/vnd.ms-excel")},
            data={"opciones": "{}"},
        )
        from app.models.db import AuditLogRecord

        filas = (
            db_session.query(AuditLogRecord)
            .filter(AuditLogRecord.accion == "EJECUTAR_AUTOMATIZACION")
            .all()
        )
        assert filas, "la corrida no quedó registrada"
        assert filas[-1].usuario_email == "ana@hus.com"


class TestLaPantallaExiste:
    """La capacidad sin pantalla es una capacidad que nadie usa.

    El Motor de Vencimientos ya había pasado por eso: construido, probado y
    desconectado de la interfaz durante semanas. Esta prueba amarra el panel
    al endpoint para que no vuelva a pasar.
    """

    def _html(self) -> str:
        from pathlib import Path

        ruta = Path(__file__).resolve().parent.parent.parent / "static" / "index.html"
        return ruta.read_text(encoding="utf-8", errors="ignore")

    def test_hay_entrada_en_el_menu(self):
        assert 'id="sn-automatizacion"' in self._html()

    def test_hay_panel(self):
        assert 'id="p-automatizacion"' in self._html()

    def test_el_panel_se_carga_al_abrir_la_pestana(self):
        assert "if(id==='automatizacion') autoCargar();" in self._html()

    def test_la_pantalla_llama_a_los_dos_endpoints(self):
        html = self._html()
        assert "'/automatizaciones'" in html
        assert "'/automatizaciones/' + id + '/ejecutar'" in html
