"""Tests del módulo de Pre-auditoría SINAC v2 (el consolidado como base de datos).

Cubre el flujo completo: subir fuentes (Radicación + DGReport) → registrar
oficio → escribir envío (autocompletar, dedup, subsanación) → auditar
(radicar/devolver, tope 3) → oficio de devolución PDF → estadísticas, más
el auto-sync (re-subir una fuente corregida se refleja en el consolidado).
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import Base, get_db
from app.models.db import UsuarioRecord
from app.services import preauditoria_service as svc


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
def usuario(db_session):
    u = UsuarioRecord(
        id=1,
        nombre="CLAUDIA",
        email="claudia@hus.gov.co",
        rol="AUDITOR",
        activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


@pytest.fixture
def client(db_session, usuario):
    from app.api.deps import get_usuario_actual
    from app.main import app

    app.dependency_overrides[get_db] = lambda: iter([db_session]).__next__()
    app.dependency_overrides[get_usuario_actual] = lambda: usuario
    c = TestClient(app)
    yield c
    app.dependency_overrides.clear()


# ------------------------------------------------------------------
# Helpers: construir Excel de las fuentes reales
# ------------------------------------------------------------------


def _excel(headers, filas):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for f in filas:
        ws.append(f)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


RAD_HEADERS = [
    "Radicacion.Consecutivo",
    "CxC.Factura",
    "Radicacion.FechaDocumento",
    "CxC.Fecha",
    "CxC.Valor",
    "Radicacion.Tercero.Documento",
    "Radicacion.Tercero.NombreCompletoNA",
    "Radicacion.EstadoActual",
]

DG_HEADERS = ["FECHA DE ENVIO CORREO", "NUMERO DE FACTURA", "CUFE"]


def _rad_fila(
    envio, factura, valor, nit="860002400", entidad="AXA COLPATRIA ", estado="Radicado_Entidad"
):
    return [
        envio,
        factura,
        "2026-06-01 00:00:00",
        "2026-05-20 10:00:00",
        valor,
        nit,
        entidad,
        estado,
    ]


def _subir_radicacion(client, filas):
    return client.post(
        "/preauditoria/fuentes/radicacion",
        files={"archivo": ("radicacion.xlsx", _excel(RAD_HEADERS, filas), "application/xlsx")},
    )


def _subir_dgreport(client, facturas):
    filas = [["2026-07-10 09:00:00", f, "CUFE" + f] for f in facturas]
    return client.post(
        "/preauditoria/fuentes/dgreport",
        files={"archivo": ("dgreport.xlsx", _excel(DG_HEADERS, filas), "application/xlsx")},
    )


def _crear_oficio(client, radicado="FHUS-AS-I00877-26", fecha="2026-07-20T08:30"):
    r = client.post(
        "/preauditoria/oficios", json={"numero_radicado": radicado, "fecha_recibido": fecha}
    )
    assert r.status_code == 200, r.text
    return r.json()


def _escribir(client, oficio_id, envio):
    return client.post(f"/preauditoria/oficios/{oficio_id}/envios", json={"envio": str(envio)})


def _factura_id(client, factura):
    d = client.get(f"/preauditoria/facturas/{factura}/historial").json()
    return d["actual"]["id"]


ENV = "229304"
F1 = "HUS0000521680"
F2 = "HUS0000521070"
F3 = "HUS0000521071"


# ------------------------------------------------------------------
# Fuentes
# ------------------------------------------------------------------


class TestFuentes:
    def test_subir_radicacion_upsert(self, client):
        r = _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 10615224)])
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nuevas"] == 2
        # re-subir sin cambios → sin_cambio
        r2 = _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 10615224)])
        assert r2.json()["sin_cambio"] == 2

    def test_radicacion_excluye_anulado(self, client):
        filas = [
            _rad_fila(ENV, F1, 250700, estado="Anulado"),
            _rad_fila("999999", F1, 300000, estado="Radicado_Entidad"),
        ]
        r = _subir_radicacion(client, filas)
        assert r.json()["facturas_validas"] == 1  # la Anulada se descarta
        # la factura quedó en el envío bueno
        lst = client.get("/preauditoria/fuentes/radicacion?envio=999999").json()
        assert lst["total"] == 1

    def test_entidad_se_recorta(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700, entidad="AXA COLPATRIA   ")])
        d = client.get("/preauditoria/fuentes/radicacion").json()
        assert d["items"][0]["entidad"] == "AXA COLPATRIA"

    def test_dgreport_upsert(self, client):
        r = _subir_dgreport(client, [F1, F2])
        assert r.status_code == 200
        assert r.json()["nuevas"] == 2


# ------------------------------------------------------------------
# Escribir envío: autocompletar, varias facturas, dedup
# ------------------------------------------------------------------


class TestEscribirEnvio:
    def test_una_fila_por_factura(self, client):
        _subir_radicacion(
            client,
            [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 10615224), _rad_fila(ENV, F3, 73500)],
        )
        _subir_dgreport(client, [F1])  # solo F1 tuvo correo
        o = _crear_oficio(client)
        r = _escribir(client, o["id"], ENV)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["nuevas"] == 3
        # el consolidado tiene 3 filas, autocompletadas
        cons = client.get("/preauditoria/consolidado").json()
        assert cons["total"] == 3
        porf = {i["factura"]: i for i in cons["items"]}
        assert porf[F1]["valor"] == 250700
        assert porf[F1]["correo_fe"] == "SI"
        assert porf[F2]["correo_fe"] == "NO"
        assert porf[F1]["entidad"] == "AXA COLPATRIA"
        assert porf[F1]["envio"] == ENV

    def test_dedup_envio(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        assert _escribir(client, o["id"], ENV).json()["nuevas"] == 1
        r2 = _escribir(client, o["id"], ENV)
        assert r2.json()["ya_cargado"] is True
        assert "ya fue cargado" in r2.json()["mensaje"].lower()
        # no duplicó
        assert client.get("/preauditoria/consolidado").json()["total"] == 1

    def test_envio_inexistente(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        r = _escribir(client, o["id"], "000000")
        assert r.status_code == 404
        assert "no existe" in r.json()["detail"].lower()

    def test_preview_no_escribe(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 100)])
        o = _crear_oficio(client)
        p = client.get(f"/preauditoria/oficios/{o['id']}/envios/{ENV}/preview").json()
        assert p["total_en_fuente"] == 2 and p["nuevas"] == 2
        assert client.get("/preauditoria/consolidado").json()["total"] == 0  # no escribió


# ------------------------------------------------------------------
# Auditar + subsanaciones + tope 3
# ------------------------------------------------------------------


def _devolver(client, fid, motivo="Falta FURIPS"):
    return client.patch(
        f"/preauditoria/facturas/{fid}/auditar",
        json={"resultado": "DEVUELTA", "motivo_devolucion": motivo},
    )


def _radicar(client, fid):
    return client.patch(f"/preauditoria/facturas/{fid}/auditar", json={"resultado": "RADICAR"})


class TestAuditoria:
    def _setup(self, client, envio=ENV, factura=F1, valor=250700):
        _subir_radicacion(client, [_rad_fila(envio, factura, valor)])
        _subir_dgreport(client, [factura])  # con F.E.: se permite radicar
        o = _crear_oficio(client, f"FHUS-{envio}", "2026-07-20T08:00")
        _escribir(client, o["id"], envio)
        return o, _factura_id(client, factura)

    def test_sin_facturacion_electronica_no_se_radica(self, client):
        # Regla: CORREO F.E. = NO → solo se puede devolver.
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])  # SIN dgreport
        o = _crear_oficio(client, f"FHUS-{ENV}", "2026-07-20T08:00")
        _escribir(client, o["id"], ENV)
        fid = _factura_id(client, F1)
        r = _radicar(client, fid)
        assert r.status_code == 409
        assert (
            "facturación electrónica" in r.json()["detail"].lower()
            or "electr" in r.json()["detail"].lower()
        )
        # devolver sí se permite
        assert _devolver(client, fid).status_code == 200

    def test_radicar_registra_auditor(self, client):
        o, fid = self._setup(client)
        d = _radicar(client, fid).json()
        assert d["resultado"] == "RADICAR"
        assert d["estado"] == "RADICADA"
        assert d["auditor"] == "CLAUDIA"

    def test_devolver_sin_motivo_400(self, client):
        o, fid = self._setup(client)
        r = client.patch(f"/preauditoria/facturas/{fid}/auditar", json={"resultado": "DEVUELTA"})
        assert r.status_code == 400

    def test_devolver_incrementa_contador(self, client):
        o, fid = self._setup(client)
        d = _devolver(client, fid).json()
        assert d["resultado"] == "DEVUELTA"
        assert d["num_devoluciones"] == 1
        assert d["pendiente_subsanacion"] is True
        assert d["estado"] == "DEVUELTA_PEND_SUBSANACION"

    def test_subsanacion_reingreso_no_duplica(self, client):
        # F1 en envío ENV, devuelta; reingresa en un envío NUEVO (re-radicación)
        _subir_dgreport(client, [F1])
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o1 = _crear_oficio(client, "FHUS-1", "2026-07-20T08:00")
        _escribir(client, o1["id"], ENV)
        fid = _factura_id(client, F1)
        _devolver(client, fid)

        # la factura vuelve corregida en un envío nuevo
        _subir_radicacion(client, [_rad_fila("229999", F1, 250700)])
        o2 = _crear_oficio(client, "FHUS-2", "2026-07-21T08:00")
        r = _escribir(client, o2["id"], "229999")
        assert r.json()["reingresos"] == 1
        # NO se creó factura nueva: sigue habiendo una sola fila
        assert client.get("/preauditoria/consolidado").json()["total"] == 1
        d = client.get(f"/preauditoria/facturas/{F1}/historial").json()
        assert d["actual"]["ronda"] == 2
        assert d["actual"]["num_subsanacion"] == 1
        assert d["actual"]["estado"] == "EN_SUBSANACION"
        # radicar → SUBSANADA
        assert _radicar(client, d["actual"]["id"]).json()["estado"] == "SUBSANADA"

    def test_no_doble_devolucion_sin_reingreso(self, client):
        # BUG: devolver dos veces sin reingreso NO debe inflar el contador.
        o, fid = self._setup(client)
        assert _devolver(client, fid).json()["num_devoluciones"] == 1
        r = _devolver(client, fid, motivo="otra vez")
        assert r.status_code == 409
        # el contador sigue en 1
        d = client.get(f"/preauditoria/facturas/{fid}").json()
        assert d["num_devoluciones"] == 1

    def test_no_radicar_ya_radicada(self, client):
        o, fid = self._setup(client)
        assert _radicar(client, fid).status_code == 200
        assert _radicar(client, fid).status_code == 409  # ya radicada

    def test_pdf_inmutable_tras_reingreso(self, client):
        # BUG 1: el PDF de un oficio de devolución ya emitido no debe cambiar
        # aunque la factura reingrese después.
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o1 = _crear_oficio(client, "FHUS-INM-1", "2026-07-20T08:00")
        _escribir(client, o1["id"], ENV)
        _devolver(client, _factura_id(client, F1))
        dev = client.post(f"/preauditoria/oficios/{o1['id']}/oficio-devolucion").json()
        pdf1 = client.get(dev["pdf_url"]).content
        # la factura reingresa en un envío nuevo
        _subir_radicacion(client, [_rad_fila("229995", F1, 250700)])
        o2 = _crear_oficio(client, "FHUS-INM-2", "2026-07-21T08:00")
        _escribir(client, o2["id"], "229995")
        # el PDF del primer oficio SIGUE conteniendo la factura (mismo tamaño, %PDF)
        pdf2 = client.get(dev["pdf_url"]).content
        assert pdf2[:5] == b"%PDF-"
        assert len(pdf2) > 2000  # no quedó vacío
        assert abs(len(pdf1) - len(pdf2)) < 500  # contenido equivalente

    def test_tope_3_devoluciones(self, client):
        _subir_dgreport(client, [F1])
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        # ronda 1
        o = _crear_oficio(client, "FHUS-A", "2026-07-20T08:00")
        _escribir(client, o["id"], ENV)
        fid = _factura_id(client, F1)
        assert _devolver(client, fid).status_code == 200  # dev 1
        # reingresos y devoluciones 2 y 3
        for i, env in enumerate(["229991", "229992"], start=2):
            _subir_radicacion(client, [_rad_fila(env, F1, 250700)])
            oo = _crear_oficio(client, f"FHUS-{env}", f"2026-07-2{i}T08:00")
            _escribir(client, oo["id"], env)
            fid = _factura_id(client, F1)
            assert _devolver(client, fid).status_code == 200
        # 4.º reingreso: devolver debe bloquearse
        _subir_radicacion(client, [_rad_fila("229993", F1, 250700)])
        o4 = _crear_oficio(client, "FHUS-229993", "2026-07-24T08:00")
        _escribir(client, o4["id"], "229993")
        fid = _factura_id(client, F1)
        r = _devolver(client, fid)
        assert r.status_code == 409
        assert "máximo 3" in r.json()["detail"]
        # radicar sí se permite
        assert _radicar(client, fid).json()["estado"] == "SUBSANADA"


# ------------------------------------------------------------------
# Auto-sync: corregir la fuente se refleja en el consolidado
# ------------------------------------------------------------------


class TestAutoSync:
    def test_corregir_valor_y_nit_se_refleja(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700, nit="111")])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        # corregir la fuente (nuevo valor y NIT)
        r = _subir_radicacion(client, [_rad_fila(ENV, F1, 999999, nit="860002400")])
        assert r.json()["actualizadas"] == 1
        item = client.get("/preauditoria/consolidado").json()["items"][0]
        assert item["valor"] == 999999
        assert item["nit"] == "860002400"

    def test_fecha_factura_no_se_corre_un_dia(self, client):
        # HALLAZGO 1: F_FACTURA de la fuente (2026-05-20) no debe mostrarse 05-19.
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        item = client.get("/preauditoria/consolidado").json()["items"][0]
        assert item["f_factura"].startswith("2026-05-20")

    def test_agregar_correo_se_refleja(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        assert client.get("/preauditoria/consolidado").json()["items"][0]["correo_fe"] == "NO"
        _subir_dgreport(client, [F1])
        assert client.get("/preauditoria/consolidado").json()["items"][0]["correo_fe"] == "SI"


# ------------------------------------------------------------------
# Oficio de devolución PDF + estadísticas
# ------------------------------------------------------------------


class TestDevolucionYStats:
    def _setup_devueltas(self, client):
        _subir_radicacion(
            client,
            [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 10615224), _rad_fila(ENV, F3, 73500)],
        )
        _subir_dgreport(client, [F1, F2, F3])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        for f in (F1, F2):
            _devolver(client, _factura_id(client, f))
        return o

    def test_consecutivo_y_pdf(self, client):
        o = self._setup_devueltas(client)
        r = client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["consecutivo"] == f"DEV-PRE-AUD-0001-{datetime.now().year}"
        assert d["total_facturas"] == 2
        pdf = client.get(d["pdf_url"])
        assert pdf.status_code == 200 and pdf.content[:5] == b"%PDF-"
        assert len(pdf.content) > 2000

    def test_sin_devueltas_400(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F3, 73500)])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        assert client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion").status_code == 400

    def test_estadisticas(self, client):
        self._setup_devueltas(client)
        _radicar(client, _factura_id(client, F3))
        d = client.get("/preauditoria/estadisticas").json()
        assert d["total_facturas"] == 3
        assert d["auditadas"] == 3
        assert d["devueltas"] == 2
        assert d["radicar"] == 1
        assert d["por_auditor"][0]["auditor"] == "CLAUDIA"
        assert d["valor_total"] == 250700 + 10615224 + 73500


# ------------------------------------------------------------------
# Eliminar oficios (solo admin/coordinador)
# ------------------------------------------------------------------


class TestEliminarOficio:
    def _admin(self, db_session):
        u = UsuarioRecord(
            id=2,
            nombre="ADMIN",
            email="admin@hus.gov.co",
            rol="SUPER_ADMIN",
            activo=1,
            password_hash=get_password_hash("xxxx"),
        )
        db_session.add(u)
        db_session.commit()
        return u

    def test_auditor_no_puede_eliminar(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        r = client.delete(f"/preauditoria/oficios/{o['id']}")
        assert r.status_code == 403  # el fixture es rol AUDITOR

    def test_admin_elimina_y_libera_envio(self, client, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        admin = self._admin(db_session)
        app.dependency_overrides[get_coordinador_o_admin] = lambda: admin
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        r = client.delete(f"/preauditoria/oficios/{o['id']}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["facturas_borradas"] == 1 and d["envios_liberados"] == 1
        # el consolidado quedó limpio y el envío se puede volver a escribir
        assert client.get("/preauditoria/consolidado").json()["total"] == 0
        o2 = _crear_oficio(client, "FHUS-NUEVO-1", "2026-07-21T08:00")
        assert _escribir(client, o2["id"], ENV).json()["nuevas"] == 1

    def test_no_elimina_con_pdf_emitido(self, client, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        admin = self._admin(db_session)
        app.dependency_overrides[get_coordinador_o_admin] = lambda: admin
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        _devolver(client, _factura_id(client, F1))
        client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion")
        r = client.delete(f"/preauditoria/oficios/{o['id']}")
        assert r.status_code == 409
        assert "devolución" in r.json()["detail"]

    def test_masivo_reporta_rechazados(self, client, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        admin = self._admin(db_session)
        app.dependency_overrides[get_coordinador_o_admin] = lambda: admin
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        r = client.post("/preauditoria/oficios/eliminar-masivo", json={"ids": [o["id"], 9999]})
        d = r.json()
        assert len(d["eliminados"]) == 1
        assert d["rechazados"][0]["id"] == 9999


# ------------------------------------------------------------------
# Semáforo (unidad, sin cambios respecto de v1)
# ------------------------------------------------------------------


class TestSemaforo:
    RECIBIDO = datetime(2026, 7, 20, 8, 30)  # lunes

    def test_limite_tercer_dia_habil(self):
        assert (
            svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 20))["fecha_limite"]
            == "2026-07-23"
        )

    def test_amarillo_penultimo(self):
        assert svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 22))["estado"] == "AMARILLO"

    def test_rojo_ultimo(self):
        assert svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 23))["estado"] == "ROJO"

    def test_vencido(self):
        assert svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 24))["estado"] == "VENCIDO"

    def test_finde_no_cuenta(self):
        assert (
            svc.calcular_semaforo(datetime(2026, 7, 24, 16, 0), hoy=date(2026, 7, 24))[
                "fecha_limite"
            ]
            == "2026-07-29"
        )


# ------------------------------------------------------------------
# Parsers (unidad)
# ------------------------------------------------------------------


class TestParsers:
    def test_radicacion_mapea_columnas_reales(self):
        r = svc.parsear_excel_radicacion(_excel(RAD_HEADERS, [_rad_fila(ENV, F1, 250700)]))
        assert len(r["facturas"]) == 1
        f = r["facturas"][0]
        assert f["factura"] == F1 and f["envio"] == ENV and f["valor"] == 250700
        assert f["nit"] == "860002400"
        assert f["entidad"] == "AXA COLPATRIA"

    def test_dgreport_mapea(self):
        r = svc.parsear_excel_dgreport(_excel(DG_HEADERS, [["2026-07-10", F1, "CUFEX"]]))
        assert r["facturas"][0]["factura"] == F1
        assert r["facturas"][0]["correo_fe"] == "SI"

    def test_radicacion_sin_columnas_avisa(self):
        r = svc.parsear_excel_radicacion(_excel(["OTRA", "COSA"], [[1, 2]]))
        assert r["facturas"] == [] and r["advertencias"]
