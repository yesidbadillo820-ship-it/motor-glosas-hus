"""Tests de /objeciones-dgh — armar el archivo de cargue desde la pantalla.

El auditor sube los dos Excel (glosas de la entidad + servicios facturados del
DGH) y la ruta devuelve el resumen del cruce más las llaves para descargar los
dos archivos. Cubre: catálogo de entidades, el proceso completo, la descarga,
que un resultado sea sólo de quien lo armó, y los errores que el auditor puede
corregir (archivo que no es Excel, falta uno de los dos, fecha al revés).
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.models.db import UsuarioRecord

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


@pytest.fixture
def auditor():
    return UsuarioRecord(id=7, email="auditor@hus.com", rol="AUDITOR", activo=1)


@pytest.fixture
def client(db_session, auditor):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: auditor
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ─── Archivos de prueba ─────────────────────────────────────────────────────


def _excel(hoja: str, headers: list, filas: list[list]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = hoja
    ws.append(headers)
    for f in filas:
        ws.append(f)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


OBS = (
    "Los dispositivos médicos … no están incluidos en la respectiva cobertura  "
    "SERVICIO SIN COBERTURA    FMQ0113 CATETER INTRAVENOSO 20   CÓDIGO    "
    "VALOR UNITARIO FACTURADO POR IPS     $      5,800"
)


def _famisanar() -> bytes:
    return _excel(
        "CONSOLIDADO",
        ["NRO_FACTURA", "CODIGO_DEVOLUCION", "VALOR DEVOLUCION", "OBSERVACION"],
        [["HUS0000548556", "CO0601", 5800, OBS]],
    )


def _dgh() -> bytes:
    return _excel(
        "DGDATATABLE",
        [
            "SERVICIOS DGH",
            "DESCRIPCION INSTITUCIONAL",
            "SLNSERPRO_CUPS",
            "DESCRIPCION CUPS",
            "CODIGO_MEDICAMENTO",
            "FACTURA",
            "CAT_SERVICIOS",
            "Vr_SERVICIO",
            "SALDO_FACT",
        ],
        [["FMQ0113", "CATETER INTRAVENOSO 20", "FMQ0113", "", "", "HUS0000548556", 1, 5800, 90000]],
    )


def _subir(client, bytes_entidad=None, bytes_dgh=None, **campos):
    """Sube los dos Excel. `campos` son los del formulario (entidad, fecha)."""
    archivos = {
        "archivo_entidad": (
            "glosas.xlsx",
            bytes_entidad if bytes_entidad is not None else _famisanar(),
        ),
        "archivo_dgh": ("dgh.xlsx", bytes_dgh if bytes_dgh is not None else _dgh()),
    }
    return client.post("/objeciones-dgh/procesar", files=archivos, data=campos)


# ─── Las rutas ──────────────────────────────────────────────────────────────


def test_catalogo_de_entidades(client):
    r = client.get("/objeciones-dgh/entidades")
    assert r.status_code == 200
    ids = {e["id"] for e in r.json()}
    assert {"famisanar", "dispensario", "sanitas"} <= ids


def test_procesar_devuelve_el_resumen(client):
    r = _subir(client, fecha="2026-09-04")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["entidad_id"] == "famisanar"
    assert d["objeciones"] == 1 and d["facturas"] == 1
    assert d["valor_total"] == 5800
    assert d["confianza"]["ALTA"] == 1
    assert d["pendientes"] == 0
    assert d["reglas_ok"] is True
    assert d["nombre_objeciones"] == "OBJECIONES_FAMISANAR_04092026.xlsx"
    assert d["id"]


def test_descargar_los_dos_archivos(client):
    d = _subir(client, fecha="2026-09-04").json()
    for ruta, nombre in (
        ("objeciones.xlsx", d["nombre_objeciones"]),
        ("cruce.xlsx", d["nombre_cruce"]),
    ):
        r = client.get(f"/objeciones-dgh/{d['id']}/{ruta}")
        assert r.status_code == 200
        assert nombre in r.headers["content-disposition"]
        assert r.content[:2] == b"PK"


def test_el_excel_descargado_cumple_las_reglas(client):
    d = _subir(client, fecha="2026-09-04").json()
    r = client.get(f"/objeciones-dgh/{d['id']}/objeciones.xlsx")
    ws = openpyxl.load_workbook(io.BytesIO(r.content))["OBJECIONES"]
    headers = [c.value for c in ws[1]]
    fila = dict(zip(headers, [c.value for c in ws[2]], strict=True))
    assert fila["CTNCENCOS"] is None
    assert fila["SLNSERPRO"] == "FMQ0113"
    assert fila["CROTIPOBJ"] == 0


def test_paquete_zip_trae_los_dos(client):
    import zipfile

    d = _subir(client, fecha="2026-09-04").json()
    r = client.get(f"/objeciones-dgh/{d['id']}/paquete.zip")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert sorted(z.namelist()) == sorted([d["nombre_objeciones"], d["nombre_cruce"]])


def test_entidad_forzada_a_mano(client):
    r = _subir(client, entidad="famisanar", fecha="2026-09-04")
    assert r.status_code == 200
    assert r.json()["entidad_id"] == "famisanar"


# ─── Lo que el auditor puede corregir ───────────────────────────────────────


def test_archivo_que_no_es_excel(client):
    archivos = {
        "archivo_entidad": ("glosas.pdf", b"%PDF-1.4"),
        "archivo_dgh": ("dgh.xlsx", _dgh()),
    }
    r = client.post("/objeciones-dgh/procesar", files=archivos)
    assert r.status_code == 400
    assert "Excel" in r.json()["detail"]


def test_archivo_vacio(client):
    archivos = {
        "archivo_entidad": ("glosas.xlsx", b""),
        "archivo_dgh": ("dgh.xlsx", _dgh()),
    }
    r = client.post("/objeciones-dgh/procesar", files=archivos)
    assert r.status_code == 400


def test_falta_el_export_del_dgh(client):
    r = client.post(
        "/objeciones-dgh/procesar",
        files={"archivo_entidad": ("glosas.xlsx", _famisanar())},
    )
    assert r.status_code == 422  # FastAPI: falta un campo obligatorio


def test_export_del_dgh_que_no_lo_es(client):
    otro = _excel("Hoja1", ["COSA"], [["x"]])
    r = _subir(client, bytes_dgh=otro)
    assert r.status_code == 400
    assert "DGH" in r.json()["detail"]


def test_entidad_que_no_se_reconoce(client):
    raro = _excel("Hoja1", ["ALGO", "OTRA COSA"], [["a", "b"]])
    r = _subir(client, bytes_entidad=raro)
    assert r.status_code == 400
    assert "No reconozco" in r.json()["detail"]


def test_fecha_al_reves(client):
    r = _subir(client, fecha="04-09-2026")
    assert r.status_code == 400
    assert "Fecha" in r.json()["detail"]


def test_resultado_que_ya_no_existe(client):
    r = client.get("/objeciones-dgh/noexiste/objeciones.xlsx")
    assert r.status_code == 404


def test_el_resultado_es_de_quien_lo_armo(client, db_session):
    """Otro usuario no puede descargar lo que armó el auditor."""
    from app.api.deps import get_usuario_actual
    from app.main import app

    d = _subir(client, fecha="2026-09-04").json()
    otro = UsuarioRecord(id=99, email="otro@hus.com", rol="AUDITOR", activo=1)
    app.dependency_overrides[get_usuario_actual] = lambda: otro
    r = client.get(f"/objeciones-dgh/{d['id']}/objeciones.xlsx")
    assert r.status_code == 403
