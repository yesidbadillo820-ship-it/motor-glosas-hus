"""Escenarios adversariales temporales (NO commitear)."""

from __future__ import annotations

from datetime import timedelta

import pytest  # noqa: F401

from tests.test_api.test_preauditoria import *  # noqa: F401,F403
from tests.test_api.test_preauditoria import (
    ENV,
    F1,
    F2,
    F3,
    _crear_oficio,
    _escribir,
    _factura_id,
    _rad_fila,
    _subir_dgreport,
    _subir_radicacion,
)
from app.auth import get_password_hash
from app.models.db import (
    FacturaEventoRecord,
    FacturaPreauditoriaRecord,
    OficioDevolucionRecord,
    RadicacionCuentaRecord,
    UsuarioRecord,
)


def _admin(db_session, uid=77):
    u = UsuarioRecord(
        id=uid,
        nombre="ADMIN ADV",
        email=f"admin{uid}@hus.gov.co",
        rol="SUPER_ADMIN",
        activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    return u


def _como_admin(db_session):
    from app.api.deps import get_coordinador_o_admin
    from app.main import app

    app.dependency_overrides[get_coordinador_o_admin] = lambda: _admin(db_session)


def _devolver(client, fid, motivo="Falta soporte"):
    r = client.post(
        f"/preauditoria/facturas/{fid}/auditar",
        json={"resultado": "DEVUELTA", "motivo": motivo},
    )
    assert r.status_code == 200, r.text
    return r


def _envejecer_todo(db_session, dias=30):
    from app.core.tz import ahora_utc

    for fila in db_session.query(RadicacionCuentaRecord).all():
        fila.importado_en = ahora_utc() - timedelta(days=dias)
        fila.actualizado_en = fila.importado_en
    db_session.commit()


# =====================================================================
# INVARIANTE 5 — falsos positivos del aviso de "fuente rezagada"
# =====================================================================


def test_inv5_falso_positivo_al_corregir_UNA_fila(client, db_session):
    """Cargue completo el dia 1; el dia 30 se re-sube el MISMO Excel con
    UNA sola correccion (el valor de F1). Solo F1 cambia de fecha."""
    _subir_radicacion(
        client,
        [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000), _rad_fila(ENV, F3, 55000)],
    )
    _envejecer_todo(db_session, dias=30)
    # mismo archivo completo, con el valor de F1 corregido por facturacion
    _subir_radicacion(
        client,
        [_rad_fila(ENV, F1, 250800), _rad_fila(ENV, F2, 98000), _rad_fila(ENV, F3, 55000)],
    )
    o = _crear_oficio(client)
    p = client.get(f"/preauditoria/oficios/{o['id']}/envios/{ENV}/preview").json()
    print("REZAGADAS(correccion de 1 fila):", p["facturas_rezagadas"])
    for a in p["avisos_fuente"]:
        print("  aviso:", a)
    assert p["facturas_rezagadas"] == [], "FALSO POSITIVO: se acusan las 2 facturas buenas"


def test_inv5_falso_positivo_al_agregar_una_factura_al_envio(client, db_session):
    """Facturacion AGREGA una factura al envio y se re-sube el Excel."""
    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000)])
    _envejecer_todo(db_session, dias=30)
    _subir_radicacion(
        client,
        [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000), _rad_fila(ENV, F3, 55000)],
    )
    o = _crear_oficio(client)
    p = client.get(f"/preauditoria/oficios/{o['id']}/envios/{ENV}/preview").json()
    print("REZAGADAS(factura agregada):", p["facturas_rezagadas"])
    assert p["facturas_rezagadas"] == [], "FALSO POSITIVO: acusa a las viejas, no a la nueva"


def test_inv5_no_detecta_el_caso_real_232047(client, db_session):
    """Caso real: las 13 filas entraron el mismo dia; luego facturacion saca
    una del envio y esa fila simplemente deja de venir en el Excel."""
    _subir_radicacion(
        client,
        [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000), _rad_fila(ENV, F3, 55000)],
    )
    _envejecer_todo(db_session, dias=30)
    # Excel nuevo: F3 ya no aparece (facturacion la saco del envio)
    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000)])
    o = _crear_oficio(client)
    p = client.get(f"/preauditoria/oficios/{o['id']}/envios/{ENV}/preview").json()
    print("REZAGADAS(caso real):", p["facturas_rezagadas"], "total en fuente:", p["total_en_fuente"])
    assert p["facturas_rezagadas"] == [F3], "NO detecta la fantasma del caso que lo origina"


# =====================================================================
# INVARIANTES 1 y 4 — quitar una factura reingresada cuyo oficio de
# devolucion ANTERIOR ya fue emitido
# =====================================================================


def test_inv1_quitar_reingreso_desella_la_factura_ya_emitida(client, db_session):
    _como_admin(db_session)
    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
    _subir_dgreport(client, [F1])
    oA = _crear_oficio(client, radicado="FHUS-AS-I00001-26")
    _escribir(client, oA["id"], ENV)
    fid = _factura_id(client, F1)
    _devolver(client, fid, motivo="Falta epicrisis")
    dev = client.post(f"/preauditoria/oficios/{oA['id']}/oficio-devolucion").json()
    print("Oficio de devolucion EMITIDO:", dev["consecutivo"], "facturas:", dev["total_facturas"])
    pdf1 = client.get(dev["pdf_url"])
    assert pdf1.status_code == 200

    # facturacion reenvia la subsanacion con el MISMO envio -> oficio B
    oB = _crear_oficio(client, radicado="FHUS-AS-I00002-26")
    _escribir(client, oB["id"], ENV)

    # el admin quita la factura del oficio B con el boton nuevo
    r = client.delete(f"/preauditoria/oficios/{oB['id']}/facturas/{fid}")
    print("quitar_factura ->", r.status_code, r.json())
    assert r.status_code == 200

    f = db_session.get(FacturaPreauditoriaRecord, fid)
    db_session.refresh(f)
    print("tras quitar: resultado=", f.resultado_actual, "oficio_dev_id=", f.oficio_devolucion_id)
    evs = (
        db_session.query(FacturaEventoRecord)
        .filter(FacturaEventoRecord.factura_id == fid)
        .all()
    )
    print("eventos:", [(e.tipo_evento, e.oficio_fhus, e.oficio_devolucion_id) for e in evs])

    # INVARIANTE 4: debe volver EXACTAMENTE a su devolucion anterior
    assert f.oficio_devolucion_id == dev["id"], (
        "no vuelve a su devolucion anterior: pierde el vinculo con el oficio EMITIDO"
    )


def test_inv1_segundo_oficio_de_devolucion_con_pdf_vacio(client, db_session):
    _como_admin(db_session)
    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])
    _subir_dgreport(client, [F1])
    oA = _crear_oficio(client, radicado="FHUS-AS-I00001-26")
    _escribir(client, oA["id"], ENV)
    fid = _factura_id(client, F1)
    _devolver(client, fid, motivo="Falta epicrisis")
    dev1 = client.post(f"/preauditoria/oficios/{oA['id']}/oficio-devolucion").json()

    oB = _crear_oficio(client, radicado="FHUS-AS-I00002-26")
    _escribir(client, oB["id"], ENV)
    client.delete(f"/preauditoria/oficios/{oB['id']}/facturas/{fid}")

    # el oficio A vuelve a mostrar la factura como "devuelta sin oficio"
    oA2 = client.get(f"/preauditoria/oficios/{oA['id']}").json()
    print("oficio A:", {k: v for k, v in oA2.items() if "dev" in k or "total" in k})

    r2 = client.post(f"/preauditoria/oficios/{oA['id']}/oficio-devolucion")
    print("segundo oficio de devolucion:", r2.status_code, r2.json())
    if r2.status_code == 200:
        dev2 = r2.json()
        pdf2 = client.get(dev2["pdf_url"])
        n_ev = (
            db_session.query(FacturaEventoRecord)
            .filter(FacturaEventoRecord.oficio_devolucion_id == dev2["id"])
            .count()
        )
        print("dev2 consecutivo:", dev2["consecutivo"], "total_facturas:", dev2["total_facturas"],
              "eventos sellados:", n_ev, "pdf bytes:", len(pdf2.content))
        n_dev = db_session.query(OficioDevolucionRecord).count()
        print("oficios de devolucion en BD:", n_dev)
        assert n_ev == dev2["total_facturas"], (
            "PDF del oficio emitido queda VACIO: dice %s facturas y no tiene eventos"
            % dev2["total_facturas"]
        )
    else:
        assert False, "esperabamos que NO dejara emitir un segundo oficio; ver mensaje"
