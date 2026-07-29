"""Tests del módulo de Pre-auditoría SINAC v2 (el consolidado como base de datos).

Cubre el flujo completo: subir fuentes (Radicación + DGReport) → registrar
oficio → escribir envío (autocompletar, dedup, subsanación) → auditar
(radicar/devolver, tope 3) → oficio de devolución PDF → estadísticas, más
el auto-sync (re-subir una fuente corregida se refleja en el consolidado).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth import get_password_hash
from app.database import Base, get_db
from app.models.db import DgReportRecord, RadicacionCuentaRecord, UsuarioRecord
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

    def test_clics_repetidos_no_duplican_el_historial(self, client):
        """Si el servidor va lento el auditor hace varios clics: solo uno debe
        quedar. (En producción llegaron 5 eventos RADICADA de la misma factura.)"""
        self._setup(client)
        fid = _factura_id(client, F1)
        respuestas = [_radicar(client, fid) for _ in range(5)]
        assert respuestas[0].status_code == 200
        assert all(r.status_code == 409 for r in respuestas[1:])
        h = client.get(f"/preauditoria/facturas/{F1}/historial").json()
        radicadas = [e for e in h["eventos"] if e["tipo"] == "RADICADA"]
        assert len(radicadas) == 1

    def test_devolver_sin_motivo_no_cambia_el_estado(self, client):
        """La validación va ANTES de tomar la factura: un intento inválido no
        puede dejarla marcada como devuelta."""
        self._setup(client)
        fid = _factura_id(client, F1)
        r = client.patch(
            f"/preauditoria/facturas/{fid}/auditar",
            json={"resultado": "DEVUELTA", "motivo_devolucion": "   "},
        )
        assert r.status_code == 400
        d = client.get(f"/preauditoria/facturas/{fid}").json()
        assert d["resultado"] == "PENDIENTE" and d["num_devoluciones"] == 0
        # y después sí se puede decidir normalmente
        assert _radicar(client, fid).status_code == 200

    def test_la_observacion_se_guarda_y_queda_en_el_historial(self, client):
        """Lo que el auditor escribe al radicar ya no se pierde."""
        self._setup(client)
        fid = _factura_id(client, F1)
        r = client.patch(
            f"/preauditoria/facturas/{fid}/auditar",
            json={"resultado": "RADICAR", "observaciones": "Soportes revisados con la EPS"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["observaciones"] == "Soportes revisados con la EPS"
        h = client.get(f"/preauditoria/facturas/{F1}/historial").json()
        assert h["actual"]["observaciones"] == "Soportes revisados con la EPS"
        radicada = [e for e in h["eventos"] if e["tipo"] == "RADICADA"][0]
        assert radicada["observaciones"] == "Soportes revisados con la EPS"

    def test_lo_escrito_en_motivo_al_radicar_no_se_pierde(self, client):
        """Caso real 29-07-2026: el auditor escribió "OKAY SOPORTES" en el
        recuadro de motivo (el de arriba) y radicó. El texto se descartaba en
        silencio y el historial salía vacío. Ahora se guarda como observación."""
        self._setup(client)
        fid = _factura_id(client, F1)
        r = client.patch(
            f"/preauditoria/facturas/{fid}/auditar",
            json={"resultado": "RADICAR", "motivo_devolucion": "OKAY SOPORTES"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["observaciones"] == "OKAY SOPORTES"
        h = client.get(f"/preauditoria/facturas/{F1}/historial").json()
        assert h["actual"]["observaciones"] == "OKAY SOPORTES"
        radicada = [e for e in h["eventos"] if e["tipo"] == "RADICADA"][0]
        assert radicada["observaciones"] == "OKAY SOPORTES"

    def test_si_escribe_en_los_dos_recuadros_se_conservan_ambos(self, client):
        self._setup(client)
        fid = _factura_id(client, F1)
        r = client.patch(
            f"/preauditoria/facturas/{fid}/auditar",
            json={
                "resultado": "RADICAR",
                "observaciones": "Soportes completos",
                "motivo_devolucion": "OKAY SOPORTES",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["observaciones"] == "Soportes completos — OKAY SOPORTES"

    def test_el_mismo_texto_en_los_dos_recuadros_no_se_duplica(self, client):
        self._setup(client)
        fid = _factura_id(client, F1)
        r = client.patch(
            f"/preauditoria/facturas/{fid}/auditar",
            json={
                "resultado": "RADICAR",
                "observaciones": "OKAY SOPORTES",
                "motivo_devolucion": "OKAY SOPORTES",
            },
        )
        assert r.json()["observaciones"] == "OKAY SOPORTES"

    def test_al_devolver_el_motivo_sigue_siendo_motivo(self, client):
        """El arreglo del radicar no puede contaminar la devolución: ahí el
        motivo es motivo y no debe colarse en la observación."""
        self._setup(client)
        fid = _factura_id(client, F1)
        r = client.patch(
            f"/preauditoria/facturas/{fid}/auditar",
            json={"resultado": "DEVUELTA", "motivo_devolucion": "Falta epicrisis"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["motivo_devolucion"] == "Falta epicrisis"
        assert not r.json()["observaciones"]
        h = client.get(f"/preauditoria/facturas/{F1}/historial").json()
        dev = [e for e in h["eventos"] if e["tipo"] == "DEVUELTA"][0]
        assert dev["motivo"] == "Falta epicrisis"

    def test_anotar_la_observacion_de_una_factura_ya_radicada(self, client):
        """Las facturas que ya se radicaron sin observación se pueden anotar
        ahora, sin revertirlas ni volverlas a radicar."""
        self._setup(client)
        fid = _factura_id(client, F1)
        assert _radicar(client, fid).status_code == 200
        r = client.patch(
            f"/preauditoria/facturas/{fid}/observacion",
            json={"observaciones": "OKAY SOPORTES"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["observaciones"] == "OKAY SOPORTES"
        # la decisión NO cambió
        assert r.json()["resultado"] == "RADICAR"
        assert r.json()["estado"] == "RADICADA"
        h = client.get(f"/preauditoria/facturas/{F1}/historial").json()
        anotacion = [e for e in h["eventos"] if e["tipo"] == "OBSERVACION"]
        assert len(anotacion) == 1
        assert anotacion[0]["observaciones"] == "OKAY SOPORTES"
        # y la RADICADA original sigue intacta (historial inmutable)
        assert len([e for e in h["eventos"] if e["tipo"] == "RADICADA"]) == 1

    def test_no_se_puede_anotar_una_observacion_vacia(self, client):
        self._setup(client)
        fid = _factura_id(client, F1)
        _radicar(client, fid)
        r = client.patch(f"/preauditoria/facturas/{fid}/observacion", json={"observaciones": "   "})
        assert r.status_code == 400

    def test_la_fila_revertida_muestra_la_observacion(self, client):
        """Antes la fila REVERTIDA salía siempre vacía en el historial."""
        self._setup(client)
        fid = _factura_id(client, F1)
        client.patch(
            f"/preauditoria/facturas/{fid}/auditar",
            json={"resultado": "RADICAR", "observaciones": "OKAY SOPORTES"},
        )
        r = client.patch(f"/preauditoria/facturas/{fid}/auditar", json={"resultado": "PENDIENTE"})
        assert r.status_code == 200, r.text
        h = client.get(f"/preauditoria/facturas/{F1}/historial").json()
        rev = [e for e in h["eventos"] if e["tipo"] == "REVERTIDA"][0]
        assert rev["observaciones"] == "OKAY SOPORTES"

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

    def test_consecutivo_escrito_por_el_auditor(self, client):
        """La numeración la lleva SINAC por fuera: el auditor escribe la que va."""
        anio = datetime.now().year
        # el sistema sugiere el siguiente según lo registrado aquí
        sug = client.get("/preauditoria/consecutivo-sugerido").json()
        assert sug["consecutivo"] == f"DEV-PRE-AUD-0001-{anio}"

        o = self._setup_devueltas(client)
        # …pero el auditor escribe el 89, que es el que le corresponde
        r = client.post(
            f"/preauditoria/oficios/{o['id']}/oficio-devolucion", json={"consecutivo": "89"}
        )
        assert r.status_code == 200, r.text
        assert r.json()["consecutivo"] == f"DEV-PRE-AUD-0089-{anio}"
        # el PDF sale con ese consecutivo
        pdf = client.get(r.json()["pdf_url"])
        assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
        # y la sugerencia siguiente continúa desde ahí
        assert client.get("/preauditoria/consecutivo-sugerido").json()["consecutivo"] == (
            f"DEV-PRE-AUD-0090-{anio}"
        )

    def test_consecutivo_completo_y_repetido(self, client):
        anio = datetime.now().year
        o = self._setup_devueltas(client)
        r = client.post(
            f"/preauditoria/oficios/{o['id']}/oficio-devolucion",
            json={"consecutivo": f"dev-pre-aud-0120-{anio}"},  # completo, en minúsculas
        )
        assert r.status_code == 200, r.text
        assert r.json()["consecutivo"] == f"DEV-PRE-AUD-0120-{anio}"

        # el mismo consecutivo en otro oficio: se rechaza con mensaje claro
        _subir_radicacion(client, [_rad_fila("777777", "HUS0000700001", 5000)])
        o2 = _crear_oficio(client, "FHUS-OTRO-1", "2026-07-21T08:00")
        _escribir(client, o2["id"], "777777")
        _devolver(client, _factura_id(client, "HUS0000700001"))
        r2 = client.post(
            f"/preauditoria/oficios/{o2['id']}/oficio-devolucion",
            json={"consecutivo": f"DEV-PRE-AUD-0120-{anio}"},
        )
        assert r2.status_code == 409
        assert "ya fue usado" in r2.json()["detail"]

    def test_consecutivo_vacio_usa_el_sugerido(self, client):
        o = self._setup_devueltas(client)
        r = client.post(
            f"/preauditoria/oficios/{o['id']}/oficio-devolucion", json={"consecutivo": "  "}
        )
        assert r.status_code == 200, r.text
        assert r.json()["consecutivo"] == f"DEV-PRE-AUD-0001-{datetime.now().year}"

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
# Eliminar un oficio de DEVOLUCIÓN generado por error
# ------------------------------------------------------------------


class TestEliminarOficioDevolucion:
    def _admin(self, db_session):
        u = UsuarioRecord(
            id=3,
            nombre="ADMIN",
            email="admin2@hus.gov.co",
            rol="SUPER_ADMIN",
            activo=1,
            password_hash=get_password_hash("xxxx"),
        )
        db_session.add(u)
        db_session.commit()
        return u

    def _con_devolucion(self, client):
        """Deja una factura devuelta y su oficio de devolución generado."""
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        _devolver(client, _factura_id(client, F1))
        dev = client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion").json()
        return o, dev

    def test_auditor_no_puede_eliminar(self, client):
        _o, dev = self._con_devolucion(client)
        r = client.delete(f"/preauditoria/oficios-devolucion/{dev['id']}")
        assert r.status_code == 403  # el fixture es rol AUDITOR

    def test_admin_elimina_y_libera_las_facturas(self, client, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)
        _o, dev = self._con_devolucion(client)
        r = client.delete(f"/preauditoria/oficios-devolucion/{dev['id']}")
        assert r.status_code == 200, r.text
        assert r.json()["consecutivo"] == dev["consecutivo"]
        assert r.json()["facturas_liberadas"] == 1
        # desaparece del listado y su PDF ya no existe
        assert client.get("/preauditoria/oficios-devolucion").json()["total"] == 0
        assert client.get(f"/preauditoria/oficios-devolucion/{dev['id']}/pdf").status_code == 404
        # la factura SIGUE devuelta: no se le cambió la decisión
        f = client.get(f"/preauditoria/facturas/{_factura_id(client, F1)}").json()
        assert f["resultado"] == "DEVUELTA"
        assert f["num_devoluciones"] == 1
        assert f["oficio_devolucion_id"] is None

    def test_tras_eliminar_se_puede_generar_el_oficio_de_nuevo(self, client, db_session):
        """El caso de uso real: el consecutivo salió equivocado y hay que
        rehacer el oficio con el número correcto."""
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)
        o, dev = self._con_devolucion(client)
        client.delete(f"/preauditoria/oficios-devolucion/{dev['id']}")
        r = client.post(
            f"/preauditoria/oficios/{o['id']}/oficio-devolucion",
            json={"consecutivo": "77"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["consecutivo"].startswith("DEV-PRE-AUD-0077-")
        assert r.json()["total_facturas"] == 1

    def test_el_consecutivo_borrado_se_puede_reutilizar(self, client, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)
        o, dev = self._con_devolucion(client)
        usado = dev["consecutivo"]
        client.delete(f"/preauditoria/oficios-devolucion/{dev['id']}")
        r = client.post(
            f"/preauditoria/oficios/{o['id']}/oficio-devolucion",
            json={"consecutivo": usado},
        )
        assert r.status_code == 200, r.text
        assert r.json()["consecutivo"] == usado

    def test_tras_eliminar_la_factura_se_puede_revertir(self, client, db_session):
        """Con el oficio emitido la reversión está bloqueada; al eliminarlo,
        la factura vuelve a poder corregirse."""
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)
        _o, dev = self._con_devolucion(client)
        fid = _factura_id(client, F1)
        bloqueada = client.patch(
            f"/preauditoria/facturas/{fid}/auditar", json={"resultado": "PENDIENTE"}
        )
        assert bloqueada.status_code == 409
        client.delete(f"/preauditoria/oficios-devolucion/{dev['id']}")
        r = client.patch(f"/preauditoria/facturas/{fid}/auditar", json={"resultado": "PENDIENTE"})
        assert r.status_code == 200, r.text
        assert client.get(f"/preauditoria/facturas/{fid}").json()["resultado"] == "PENDIENTE"

    def test_el_historial_de_la_devolucion_no_se_borra(self, client, db_session):
        """Queda constancia de que la factura sí fue devuelta ese día."""
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)
        _o, dev = self._con_devolucion(client)
        client.delete(f"/preauditoria/oficios-devolucion/{dev['id']}")
        h = client.get(f"/preauditoria/facturas/{F1}/historial").json()
        devueltas = [e for e in h["eventos"] if e["tipo"] == "DEVUELTA"]
        assert len(devueltas) == 1
        assert devueltas[0]["motivo"]

    def test_eliminar_uno_que_no_existe(self, client, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)
        assert client.delete("/preauditoria/oficios-devolucion/9999").status_code == 404


# ------------------------------------------------------------------
# Eliminar UN envío cargado por error (solo admin/coordinador)
# ------------------------------------------------------------------


class TestEliminarEnvio:
    def _admin(self, db_session):
        u = UsuarioRecord(
            id=4,
            nombre="ADMIN",
            email="admin4@hus.gov.co",
            rol="SUPER_ADMIN",
            activo=1,
            password_hash=get_password_hash("xxxx"),
        )
        db_session.add(u)
        db_session.commit()
        return u

    def _como_admin(self, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)

    def test_auditor_no_puede(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        assert client.delete(f"/preauditoria/oficios/{o['id']}/envios/{ENV}").status_code == 403

    def test_borra_solo_ese_envio_y_lo_libera(self, client, db_session):
        self._como_admin(db_session)
        otro = "229999"
        _subir_radicacion(
            client,
            [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000), _rad_fila(otro, F3, 55000)],
        )
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        _escribir(client, o["id"], otro)
        assert client.get("/preauditoria/consolidado").json()["total"] == 3

        r = client.delete(f"/preauditoria/oficios/{o['id']}/envios/{ENV}")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["envio"] == ENV and d["facturas_borradas"] == 2

        # el otro envío quedó intacto…
        cons = client.get("/preauditoria/consolidado").json()
        assert cons["total"] == 1 and cons["items"][0]["factura"] == F3
        # …el oficio sigue existiendo con un solo envío…
        assert [e["envio"] for e in d["oficio"]["envios_escritos"]] == [otro]
        # …y el envío borrado se puede volver a escribir
        assert _escribir(client, o["id"], ENV).json()["nuevas"] == 2

    def test_envio_inexistente(self, client, db_session):
        self._como_admin(db_session)
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        r = client.delete(f"/preauditoria/oficios/{o['id']}/envios/{ENV}")
        assert r.status_code == 404
        assert "no está cargado" in r.json()["detail"]

    def test_no_borra_con_pdf_emitido(self, client, db_session):
        self._como_admin(db_session)
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        _devolver(client, _factura_id(client, F1))
        client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion")
        r = client.delete(f"/preauditoria/oficios/{o['id']}/envios/{ENV}")
        assert r.status_code == 409
        assert "devolución ya" in r.json()["detail"]

    def test_reingreso_vuelve_a_su_devolucion(self, client, db_session):
        """Si el envío traía una factura a subsanar, quitarlo la devuelve a su
        estado anterior sin borrarla ni perder el historial."""
        self._como_admin(db_session)
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o1 = _crear_oficio(client, "FHUS-1")
        _escribir(client, o1["id"], ENV)
        _devolver(client, _factura_id(client, F1), motivo="Falta epicrisis")
        # reingresa en otro oficio/envío para subsanar
        _subir_radicacion(client, [_rad_fila("229305", F1, 250700)])
        o2 = _crear_oficio(client, "FHUS-2", "2026-07-21T08:00")
        assert _escribir(client, o2["id"], "229305").json()["reingresos"] == 1

        r = client.delete(f"/preauditoria/oficios/{o2['id']}/envios/229305")
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["facturas_borradas"] == 0 and d["subsanaciones_revertidas"] == 1
        # la factura sigue viva, devuelta y en su oficio original
        h = client.get(f"/preauditoria/facturas/{F1}/historial").json()
        assert h["actual"]["resultado"] == "DEVUELTA"
        assert h["actual"]["oficio_fhus"] == "FHUS-1"
        assert h["actual"]["motivo_devolucion"] == "Falta epicrisis"


# ------------------------------------------------------------------
# Limpiar TODO el módulo (solo admin/coordinador)
# ------------------------------------------------------------------


class TestLimpiarTodo:
    def _admin(self, db_session):
        u = UsuarioRecord(
            id=3,
            nombre="ADMIN",
            email="admin2@hus.gov.co",
            rol="SUPER_ADMIN",
            activo=1,
            password_hash=get_password_hash("xxxx"),
        )
        db_session.add(u)
        db_session.commit()
        return u

    def _poblar(self, client):
        """Deja el módulo con datos de todas las tablas: 1 oficio, 1 envío,
        2 facturas (1 radicada + 1 devuelta), 4 eventos y 1 oficio de
        devolución emitido."""
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000)])
        _subir_dgreport(client, [F1])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        _radicar(client, _factura_id(client, F1))
        _devolver(client, _factura_id(client, F2))
        assert client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion").status_code == 200
        return o

    def test_auditor_no_puede(self, client):
        r = client.post("/preauditoria/admin/limpiar-todo", json={"confirmacion": "BORRAR TODO"})
        assert r.status_code == 403  # el fixture es rol AUDITOR

    def test_exige_confirmacion_exacta(self, client, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)
        r = client.post("/preauditoria/admin/limpiar-todo", json={"confirmacion": "si, borrar"})
        assert r.status_code == 400
        assert "BORRAR TODO" in r.json()["detail"]

    def test_limpia_proceso_y_conserva_fuentes(self, client, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)
        self._poblar(client)
        # La confirmación tolera minúsculas/espacios.
        r = client.post("/preauditoria/admin/limpiar-todo", json={"confirmacion": " borrar todo "})
        assert r.status_code == 200, r.text
        b = r.json()["borrado"]
        assert b["oficios_recepcion"] == 1
        assert b["facturas"] == 2
        assert b["eventos"] == 4  # 2 escritas + 1 radicada + 1 devuelta
        assert b["envios_cargados"] == 1
        assert b["oficios_devolucion"] == 1
        assert "fuente_radicacion" not in b  # las fuentes NO se tocaron
        # El proceso quedó en cero…
        assert client.get("/preauditoria/oficios").json()["total"] == 0
        assert client.get("/preauditoria/consolidado").json()["total"] == 0
        assert client.get("/preauditoria/oficios-devolucion").json()["total"] == 0
        # …pero las fuentes siguen cargadas.
        res = client.get("/preauditoria/fuentes/resumen").json()
        assert res["radicacion_facturas"] == 2
        assert res["dgreport_facturas"] == 1
        # Se puede empezar de cero: mismo envío re-escribible y consecutivo
        # SINAC reiniciado en 0001.
        o2 = _crear_oficio(client, "FHUS-DESPUES-1")
        assert _escribir(client, o2["id"], ENV).json()["nuevas"] == 2
        _devolver(client, _factura_id(client, F2))
        d = client.post(f"/preauditoria/oficios/{o2['id']}/oficio-devolucion").json()
        assert d["consecutivo"].startswith("DEV-PRE-AUD-0001-")

    def test_limpia_incluyendo_fuentes(self, client, db_session):
        from app.api.deps import get_coordinador_o_admin
        from app.main import app

        app.dependency_overrides[get_coordinador_o_admin] = lambda: self._admin(db_session)
        self._poblar(client)
        r = client.post(
            "/preauditoria/admin/limpiar-todo",
            json={"confirmacion": "BORRAR TODO", "incluir_fuentes": True},
        )
        assert r.status_code == 200, r.text
        b = r.json()["borrado"]
        assert b["fuente_radicacion"] == 2
        assert b["fuente_facturacion_electronica"] == 1
        res = client.get("/preauditoria/fuentes/resumen").json()
        assert res["radicacion_facturas"] == 0
        assert res["dgreport_facturas"] == 0


# ------------------------------------------------------------------
# Excel especial para oficios de ADRES (información completa)
# ------------------------------------------------------------------

ENTIDAD_ADRES = "ADMINISTRADORA DE LOS RECURSOS DEL SISTEMA GENERAL DE SEGURIDAD SOCIAL EN SALUD "


class TestExportAdres:
    def test_descarga_con_formato_del_consolidado(self, client):
        _subir_radicacion(
            client,
            [
                _rad_fila(ENV, F1, 250700, nit=svc.NIT_ADRES, entidad=ENTIDAD_ADRES),
                _rad_fila(ENV, F2, 98000, nit=svc.NIT_ADRES, entidad=ENTIDAD_ADRES),
                _rad_fila(ENV, F3, 55000),  # otra entidad: NO debe salir en el Excel
            ],
        )
        _subir_dgreport(client, [F1])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        _radicar(client, _factura_id(client, F1))
        _devolver(client, _factura_id(client, F2), motivo="Falta FURIPS")
        assert client.post(f"/preauditoria/oficios/{o['id']}/oficio-devolucion").status_code == 200
        # La lista de oficios marca que este tiene facturas de ADRES.
        of = client.get("/preauditoria/oficios").json()["items"][0]
        assert of["tiene_adres"] is True
        r = client.get(f"/preauditoria/oficios/{o['id']}/export-adres.xlsx")
        assert r.status_code == 200
        from openpyxl import load_workbook

        ws = load_workbook(BytesIO(r.content)).active
        filas = list(ws.iter_rows(values_only=True))
        encabezado = list(filas[0])
        # Tramo SINAC en el orden del consolidado real…
        assert encabezado[:14] == [
            "Item",
            "Fecha_Recibido",
            "Envío",
            "AUD",
            "HUS",
            "Fecha_Factura",
            "Valor",
            "NIT",
            "Entidad",
            "Correo F.E.",
            "Observación Preauditoria Radicación SINAC",
            "Radicar_1",
            "Observaciones Adicionales",
            "Fecha_Entrega_Fact",
        ]
        # …seguido de las columnas de las otras áreas (vienen vacías).
        assert encabezado[14] == "Observación_FACTURACIÓN"
        assert encabezado[-1] == "INFOPOL"
        assert "Radicar_2" in encabezado
        assert len(filas) == 3  # encabezado + las 2 facturas ADRES (F3 no sale)
        assert [f[0] for f in filas[1:]] == [1, 2]  # Item consecutivo
        por_hus = {
            dict(zip(encabezado[:14], f))["HUS"]: dict(zip(encabezado[:14], f)) for f in filas[1:]
        }
        # F1 radicada
        f1 = por_hus[F1]
        assert f1["HUS"] == F1
        assert f1["AUD"] == "CLAUDIA"
        assert str(f1["NIT"]) == svc.NIT_ADRES
        assert f1["Entidad"] == ENTIDAD_ADRES.strip()
        assert f1["Correo F.E."] == "SI"
        assert f1["Valor"] == 250700
        assert f1["Radicar_1"] == "SI"
        assert f1["Observación Preauditoria Radicación SINAC"] == "SOPORTES COMPLETOS"
        assert f1["Fecha_Entrega_Fact"] in ("", None)  # la llena a mano quien entrega
        # F2 devuelta: motivo + consecutivo del oficio de devolución, Radicar_1=NO
        f2 = por_hus[F2]
        assert f2["HUS"] == F2
        assert f2["Correo F.E."] == "NO"
        assert f2["Radicar_1"] == "NO"
        obs2 = f2["Observación Preauditoria Radicación SINAC"]
        assert "Falta FURIPS" in obs2 and "DEV-PRE-AUD-0001" in obs2
        # el tramo de las otras áreas viene vacío
        assert all(v in ("", None) for v in filas[1][14:])

    def test_reconoce_adres_por_nombre_sin_nit(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700, nit="901037916-6", entidad="ADRES ")])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        assert client.get("/preauditoria/oficios").json()["items"][0]["tiene_adres"] is True

    def test_oficio_sin_adres_no_aplica(self, client):
        _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
        o = _crear_oficio(client)
        _escribir(client, o["id"], ENV)
        of = client.get("/preauditoria/oficios").json()["items"][0]
        assert of["tiene_adres"] is False
        r = client.get(f"/preauditoria/oficios/{o['id']}/export-adres.xlsx")
        assert r.status_code == 404
        assert "ADRES" in r.json()["detail"]


# ------------------------------------------------------------------
# Cargue masivo por bloques (memoria acotada en el servidor de 1 GB)
# ------------------------------------------------------------------


class TestCargueMasivoPorBloques:
    """Los archivos grandes se guardan por bloques para no agotar la memoria.

    Estas pruebas fijan que trocear el cargue NO cambia el resultado: mismos
    conteos, sin duplicar y sin perder la idempotencia del upsert.
    """

    def _filas(self, n, valor=100.0):
        return [
            {
                "factura": f"HUS{i:07d}",
                "envio": ENV,
                "f_recibido": datetime(2026, 7, 20),
                "f_factura": datetime(2026, 7, 1),
                "valor": valor + i,
                "nit": svc.NIT_ADRES,
                "entidad": "ADRES",
                "estado_radicacion": "Registrado",
            }
            for i in range(n)
        ]

    def test_conteos_exactos_cruzando_bloques(self, db_session, monkeypatch):
        monkeypatch.setattr(svc, "TAM_BLOQUE_UPSERT", 3)  # 10 filas → 4 bloques
        filas = self._filas(10)
        assert svc.upsert_radicacion(db_session, filas, "a.xlsx", "YESID") == {
            "nuevas": 10,
            "actualizadas": 0,
            "sin_cambio": 0,
        }
        # re-subir el mismo archivo: todo sin cambio (idempotente)
        assert svc.upsert_radicacion(db_session, filas, "a.xlsx", "YESID") == {
            "nuevas": 0,
            "actualizadas": 0,
            "sin_cambio": 10,
        }
        # subir el archivo corregido: todo actualizado, sin duplicar
        for f in filas:
            f["valor"] += 1
        assert svc.upsert_radicacion(db_session, filas, "b.xlsx", "YESID") == {
            "nuevas": 0,
            "actualizadas": 10,
            "sin_cambio": 0,
        }
        assert db_session.query(RadicacionCuentaRecord).count() == 10

    def test_factura_repetida_en_otro_bloque_no_duplica(self, db_session, monkeypatch):
        monkeypatch.setattr(svc, "TAM_BLOQUE_UPSERT", 2)
        filas = self._filas(3)
        filas.append(dict(filas[0]))  # la misma factura, ya en otro bloque
        res = svc.upsert_radicacion(db_session, filas, "a.xlsx", "YESID")
        assert res["nuevas"] == 3 and res["sin_cambio"] == 1
        assert db_session.query(RadicacionCuentaRecord).count() == 3

    def test_dgreport_por_bloques(self, db_session, monkeypatch):
        monkeypatch.setattr(svc, "TAM_BLOQUE_UPSERT", 2)
        filas = [
            {"factura": f"HUS{i:07d}", "correo_fe": "SI", "numero_fe": f"CUFE{i}"} for i in range(7)
        ]
        assert svc.upsert_dgreport(db_session, filas, "d.xlsx", "YESID")["nuevas"] == 7
        assert svc.upsert_dgreport(db_session, filas, "d.xlsx", "YESID")["sin_cambio"] == 7
        assert db_session.query(DgReportRecord).count() == 7

    def test_archivo_mas_grande_que_un_bloque_real(self, db_session):
        """Con el tamaño de bloque real (2.000): un archivo de 2.500 filas."""
        filas = self._filas(2500)
        assert svc.upsert_radicacion(db_session, filas, "a.xlsx", "YESID")["nuevas"] == 2500
        assert db_session.query(RadicacionCuentaRecord).count() == 2500
        assert svc.upsert_radicacion(db_session, filas, "a.xlsx", "YESID")["sin_cambio"] == 2500

    def test_el_parseo_comparte_los_textos_repetidos(self, client):
        """ENTIDAD/NIT se repiten miles de veces: deben compartir una sola copia."""
        filas = [_rad_fila(ENV, f"HUS{i:07d}", 1000 + i) for i in range(50)]
        datos = svc.parsear_excel_radicacion(_excel(RAD_HEADERS, filas))
        entidades = [f["entidad"] for f in datos["facturas"]]
        assert len(entidades) == 50
        # todas las filas apuntan al MISMO objeto de texto, no a 50 copias
        assert len({id(e) for e in entidades}) == 1
        assert entidades[0] == "AXA COLPATRIA"  # y se sigue recortando


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

    def test_salta_encabezados_y_totales_repetidos(self):
        """El reporte real repite el encabezado y trae filas de TOTAL: se saltan.

        Cubre el atajo rápido del parseo (evitar normalizar 191.859 veces):
        los valores ASCII alfanuméricos se comparan directo y los que traen
        acentos o signos siguen pasando por la normalización completa.
        """
        filas = [
            _rad_fila(ENV, F1, 250700),
            _rad_fila(ENV, "FACTURA", 0),  # encabezado repetido
            _rad_fila(ENV, "Total", 999),  # fila de total
            _rad_fila(ENV, " total ", 999),  # con espacios
            _rad_fila(ENV, "FACTÚRA", 0),  # con acento → normalizada
            _rad_fila(ENV, F2, 98000),
        ]
        r = svc.parsear_excel_radicacion(_excel(RAD_HEADERS, filas))
        assert sorted(f["factura"] for f in r["facturas"]) == sorted([F1, F2])

    def test_anulado_en_cualquier_forma_se_descarta(self):
        """El estado llega escrito de varias formas; todas cuentan como anulada."""
        filas = [
            _rad_fila(ENV, F1, 1, estado="Anulado"),
            _rad_fila(ENV, F2, 2, estado="ANULADA"),
            _rad_fila(ENV, F3, 3, estado="anulado_entidad"),
            _rad_fila(ENV, "HUS0000999999", 4, estado="Radicado_Entidad"),
        ]
        r = svc.parsear_excel_radicacion(_excel(RAD_HEADERS, filas))
        assert [f["factura"] for f in r["facturas"]] == ["HUS0000999999"]
        assert "3 radicación(es) 'Anulado' descartada(s)" in r["advertencias"]

    def test_lee_archivos_sin_dimensiones_declaradas(self):
        """El reporte de DGH no declara <dimension>: debe leerse igual.

        Se omite el barrido previo de openpyxl (12 s en el archivo real), así
        que esta prueba fija que quitarlo no cambia lo que se lee.
        """
        import zipfile

        contenido = _excel(RAD_HEADERS, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000)])
        # el Excel de prueba sí declara dimensiones: se le quitan para simular
        # el reporte real de Dinámica Gerencial
        entrada = BytesIO()
        with zipfile.ZipFile(BytesIO(contenido)) as orig:
            with zipfile.ZipFile(entrada, "w", zipfile.ZIP_DEFLATED) as nuevo:
                for item in orig.infolist():
                    datos = orig.read(item.filename)
                    if item.filename.startswith("xl/worksheets/sheet"):
                        datos = re.sub(rb"<dimension[^>]*/>", b"", datos)
                    nuevo.writestr(item, datos)
        sin_dim = entrada.getvalue()
        assert b"<dimension" not in zipfile.ZipFile(BytesIO(sin_dim)).read(
            "xl/worksheets/sheet1.xml"
        )
        r = svc.parsear_excel_radicacion(sin_dim)
        assert sorted(f["factura"] for f in r["facturas"]) == sorted([F1, F2])
        assert r["leidas"] == 2
