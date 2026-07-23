"""Tests del módulo de Pre-auditoría SINAC (/preauditoria).

Cubre: registro de oficios con fecha/hora, importación del Excel DGH
(facturas por envío), auditoría con regla de máximo 3 devoluciones y
subsanación, oficio de devolución en PDF con consecutivo SINAC,
semáforo de 3 días hábiles y estadísticas.
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


def _excel_dgh(filas):
    """Arma un Excel en memoria con el formato del consecutivo DGH."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["ENVIO", "FACTURA", "F_FACTURA", "VALOR", "NIT", "ENTIDAD", "CORREO F.E."])
    for fila in filas:
        ws.append(fila)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _crear_oficio(client, radicado="FHUS-AS-I00768-26", fecha="2026-07-20T08:30"):
    r = client.post(
        "/preauditoria/oficios",
        json={"numero_radicado": radicado, "fecha_recibido": fecha},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _importar(client, oficio_id, filas):
    r = client.post(
        f"/preauditoria/oficios/{oficio_id}/importar-dgh",
        files={
            "archivo": (
                "consecutivo.xlsx",
                _excel_dgh(filas),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )
    assert r.status_code == 200, r.text
    return r.json()


FILA_1 = ["228462", "HUS0000517026", "2026-06-01", 13103611, "860002184", "AXA COLPATRIA", "SI"]
FILA_2 = ["228462", "HUS0000517514", "2026-06-01", 2889036, "860002184", "AXA COLPATRIA", "SI"]
FILA_3 = ["228474", "HUS0000494335", "2026-06-02", 64500, "860002180", "SEGUROS BOLIVAR", "NO"]


# ------------------------------------------------------------------
# Unidad: semáforo de 3 días hábiles
# ------------------------------------------------------------------


class TestSemaforo:
    RECIBIDO = datetime(2026, 7, 20, 8, 30)  # lunes

    def test_plazo_termina_el_tercer_dia_habil(self):
        s = svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 20))
        assert s["fecha_limite"] == "2026-07-23"  # mar, mié, jue

    def test_verde_al_recibir(self):
        assert svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 20))["estado"] == "VERDE"

    def test_verde_primer_dia(self):
        assert svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 21))["estado"] == "VERDE"

    def test_amarillo_penultimo_dia(self):
        s = svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 22))
        assert s["estado"] == "AMARILLO"
        assert s["dias_habiles_restantes"] == 2

    def test_rojo_ultimo_dia(self):
        assert svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 23))["estado"] == "ROJO"

    def test_vencido_despues_del_plazo(self):
        s = svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 24))
        assert s["estado"] == "VENCIDO"
        assert s["dias_vencido"] == 1

    def test_fin_de_semana_no_cuenta(self):
        # Recibido viernes: cuenta lun+mar+mié de la semana siguiente.
        s = svc.calcular_semaforo(datetime(2026, 7, 24, 16, 0), hoy=date(2026, 7, 24))
        assert s["fecha_limite"] == "2026-07-29"

    def test_completado_gana_al_plazo(self):
        s = svc.calcular_semaforo(self.RECIBIDO, hoy=date(2026, 7, 30), completado=True)
        assert s["estado"] == "COMPLETADO"


# ------------------------------------------------------------------
# API: oficios + importación DGH
# ------------------------------------------------------------------


class TestOficios:
    def test_crear_oficio_guarda_fecha_con_hora(self, client):
        o = _crear_oficio(client, fecha="2026-07-20T14:35")
        assert o["numero_radicado"] == "FHUS-AS-I00768-26"
        assert "14:35" in o["fecha_recibido"]
        assert o["semaforo"]["estado"] in ("VERDE", "AMARILLO", "ROJO", "VENCIDO")

    def test_radicado_duplicado_da_409(self, client):
        _crear_oficio(client)
        r = client.post(
            "/preauditoria/oficios",
            json={"numero_radicado": "FHUS-AS-I00768-26", "fecha_recibido": "2026-07-21T09:00"},
        )
        assert r.status_code == 409

    def test_importar_dgh_cuenta_facturas_por_envio(self, client):
        o = _crear_oficio(client)
        d = _importar(client, o["id"], [FILA_1, FILA_2, FILA_3])
        assert d["importadas"] == 3
        envios = {e["envio"]: e["cantidad_facturas"] for e in d["envios"]}
        assert envios == {"228462": 2, "228474": 1}

    def test_importar_no_duplica_facturas(self, client):
        o = _crear_oficio(client)
        _importar(client, o["id"], [FILA_1])
        d = _importar(client, o["id"], [FILA_1])
        assert d["importadas"] == 0
        assert any("no se duplicó" in a for a in d["advertencias"])


# ------------------------------------------------------------------
# API: auditoría, subsanación y regla de 3 devoluciones
# ------------------------------------------------------------------


def _factura_id(client, oficio_id, numero):
    r = client.get(f"/preauditoria/oficios/{oficio_id}")
    for f in r.json()["facturas"]:
        if f["factura"] == numero:
            return f["id"]
    raise AssertionError(f"{numero} no está en el oficio {oficio_id}")


def _devolver(client, fid, motivo="Falta el FURIPS"):
    return client.patch(
        f"/preauditoria/facturas/{fid}/auditar",
        json={"resultado": "DEVUELTA", "motivo_devolucion": motivo},
    )


class TestAuditoria:
    def test_radicar_registra_auditor(self, client):
        o = _crear_oficio(client)
        _importar(client, o["id"], [FILA_1])
        fid = _factura_id(client, o["id"], "HUS0000517026")
        r = client.patch(f"/preauditoria/facturas/{fid}/auditar", json={"resultado": "RADICAR"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["resultado"] == "RADICAR"
        assert d["auditor"] == "CLAUDIA"
        assert d["fecha_auditoria"]

    def test_devolver_sin_motivo_da_400(self, client):
        o = _crear_oficio(client)
        _importar(client, o["id"], [FILA_1])
        fid = _factura_id(client, o["id"], "HUS0000517026")
        r = client.patch(f"/preauditoria/facturas/{fid}/auditar", json={"resultado": "DEVUELTA"})
        assert r.status_code == 400

    def test_subsanacion_ronda_2(self, client):
        o1 = _crear_oficio(client, "FHUS-AS-I00768-26", "2026-07-20T08:00")
        _importar(client, o1["id"], [FILA_1])
        f1 = _factura_id(client, o1["id"], "HUS0000517026")
        assert _devolver(client, f1).status_code == 200

        # La factura vuelve corregida en un oficio nuevo → ronda 2.
        o2 = _crear_oficio(client, "FHUS-AS-I00804-26", "2026-07-21T08:00")
        d = _importar(client, o2["id"], [FILA_1])
        f2 = _factura_id(client, o2["id"], "HUS0000517026")
        detalle = client.get(f"/preauditoria/facturas/{f2}").json()
        assert detalle["actual"]["ronda"] == 2
        assert detalle["actual"]["es_subsanacion"] is True

        r = client.patch(f"/preauditoria/facturas/{f2}/auditar", json={"resultado": "RADICAR"})
        assert r.json()["estado_subsanacion"] == "SUBSANADA"

    def test_maximo_3_devoluciones(self, client):
        radicados = ["FHUS-AS-I001-26", "FHUS-AS-I002-26", "FHUS-AS-I003-26", "FHUS-AS-I004-26"]
        ids = []
        for i, rad in enumerate(radicados):
            o = _crear_oficio(client, rad, f"2026-07-{20 + i}T08:00")
            _importar(client, o["id"], [FILA_1])
            ids.append(_factura_id(client, o["id"], "HUS0000517026"))

        for fid in ids[:3]:
            assert _devolver(client, fid).status_code == 200

        # Cuarta devolución de la misma factura: bloqueada.
        r = _devolver(client, ids[3])
        assert r.status_code == 409
        assert "máximo 3" in r.json()["detail"]

        # Radicarla sí se permite (y queda SUBSANADA).
        r = client.patch(f"/preauditoria/facturas/{ids[3]}/auditar", json={"resultado": "RADICAR"})
        assert r.status_code == 200
        assert r.json()["estado_subsanacion"] == "SUBSANADA"

    def test_importar_avisa_si_ya_agoto_devoluciones(self, client):
        for i, rad in enumerate(["A-1", "A-2", "A-3"]):
            o = _crear_oficio(client, rad, f"2026-07-{20 + i}T08:00")
            _importar(client, o["id"], [FILA_1])
            fid = _factura_id(client, o["id"], "HUS0000517026")
            assert _devolver(client, fid).status_code == 200
        o4 = _crear_oficio(client, "A-4", "2026-07-23T08:00")
        d = _importar(client, o4["id"], [FILA_1])
        assert d["alertas_limite_devoluciones"]


# ------------------------------------------------------------------
# API: oficio de devolución (consecutivo SINAC + PDF)
# ------------------------------------------------------------------


class TestOficioDevolucion:
    def _preparar_devueltas(self, client):
        o = _crear_oficio(client)
        _importar(client, o["id"], [FILA_1, FILA_2, FILA_3])
        for numero in ("HUS0000517026", "HUS0000517514"):
            fid = _factura_id(client, o["id"], numero)
            assert _devolver(client, fid).status_code == 200
        return o

    def test_consecutivo_sinac_incremental(self, client):
        o = self._preparar_devueltas(client)
        r = client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion")
        assert r.status_code == 200, r.text
        d = r.json()
        anio = datetime.now().year
        assert d["consecutivo"] == f"DEV-PRE-AUD-0001-{anio}"
        assert d["total_facturas"] == 2

    def test_sin_devueltas_da_400(self, client):
        o = _crear_oficio(client)
        _importar(client, o["id"], [FILA_3])
        r = client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion")
        assert r.status_code == 400

    def test_pdf_se_descarga(self, client):
        o = self._preparar_devueltas(client)
        d = client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion").json()
        r = client.get(d["pdf_url"])
        assert r.status_code == 200
        assert r.headers["content-type"] == "application/pdf"
        assert r.content[:5] == b"%PDF-"
        assert len(r.content) > 2000

    def test_no_genera_dos_veces_con_las_mismas_facturas(self, client):
        o = self._preparar_devueltas(client)
        assert client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion").status_code == 200
        # Ya todas las devueltas quedaron amarradas al primer oficio.
        r = client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion")
        assert r.status_code == 400


# ------------------------------------------------------------------
# API: filtros y estadísticas
# ------------------------------------------------------------------


class TestEstadisticas:
    def test_kpis_y_por_auditor(self, client):
        o = _crear_oficio(client)
        _importar(client, o["id"], [FILA_1, FILA_2, FILA_3])
        fid_ok = _factura_id(client, o["id"], "HUS0000494335")
        client.patch(f"/preauditoria/facturas/{fid_ok}/auditar", json={"resultado": "RADICAR"})
        fid_dev = _factura_id(client, o["id"], "HUS0000517026")
        _devolver(client, fid_dev)

        d = client.get("/preauditoria/estadisticas").json()
        assert d["total_facturas"] == 3
        assert d["auditadas"] == 2
        assert d["radicar"] == 1
        assert d["devueltas"] == 1
        assert d["pendientes"] == 1
        assert d["por_auditor"][0]["auditor"] == "CLAUDIA"
        assert d["por_auditor"][0]["auditadas"] == 2

    def test_reincidentes(self, client):
        for i, rad in enumerate(["B-1", "B-2"]):
            o = _crear_oficio(client, rad, f"2026-07-{20 + i}T08:00")
            _importar(client, o["id"], [FILA_1])
            fid = _factura_id(client, o["id"], "HUS0000517026")
            assert _devolver(client, fid).status_code == 200
        d = client.get("/preauditoria/estadisticas").json()
        assert d["reincidentes"] == [{"factura": "HUS0000517026", "veces_devuelta": 2}]

    def test_filtro_facturas_por_resultado(self, client):
        o = _crear_oficio(client)
        _importar(client, o["id"], [FILA_1, FILA_3])
        fid = _factura_id(client, o["id"], "HUS0000517026")
        _devolver(client, fid)
        d = client.get("/preauditoria/facturas?resultado=DEVUELTA").json()
        assert d["total"] == 1
        assert d["items"][0]["factura"] == "HUS0000517026"

    def test_busqueda_individual_con_historial(self, client):
        o1 = _crear_oficio(client, "C-1", "2026-07-20T08:00")
        _importar(client, o1["id"], [FILA_1])
        f1 = _factura_id(client, o1["id"], "HUS0000517026")
        _devolver(client, f1)
        o2 = _crear_oficio(client, "C-2", "2026-07-21T08:00")
        _importar(client, o2["id"], [FILA_1])
        f2 = _factura_id(client, o2["id"], "HUS0000517026")

        d = client.get(f"/preauditoria/facturas/{f2}").json()
        assert len(d["historial"]) == 2
        assert d["devoluciones_totales"] == 1
        assert d["historial"][0]["oficio_radicado"] == "C-1"


# ------------------------------------------------------------------
# Unidad: parser DGH y consecutivo
# ------------------------------------------------------------------


class TestParserDGH:
    def test_columnas_estandar(self):
        r = svc.parsear_excel_dgh(_excel_dgh([FILA_1, FILA_3]))
        assert len(r["facturas"]) == 2
        f = r["facturas"][0]
        assert f["factura"] == "HUS0000517026"
        assert f["envio"] == "228462"
        assert f["valor"] == 13103611.0
        assert f["correo_fe"] == "SI"

    def test_repetidas_en_archivo_avisan(self):
        r = svc.parsear_excel_dgh(_excel_dgh([FILA_1, FILA_1]))
        assert len(r["facturas"]) == 1
        assert any("repetida" in a.lower() for a in r["advertencias"])

    def test_archivo_sin_columna_factura(self):
        from openpyxl import Workbook

        wb = Workbook()
        wb.active.append(["OTRA", "COSA"])
        buf = BytesIO()
        wb.save(buf)
        r = svc.parsear_excel_dgh(buf.getvalue())
        assert r["facturas"] == []
        assert r["advertencias"]

    def test_valor_formato_colombiano(self):
        fila = ["1", "HUS01", "2026-01-01", "1.234.567,89", "900", "X", "SI"]
        r = svc.parsear_excel_dgh(_excel_dgh([fila]))
        assert r["facturas"][0]["valor"] == pytest.approx(1234567.89)
