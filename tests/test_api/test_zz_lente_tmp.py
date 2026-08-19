"""Scratch: falsos positivos/negativos del aviso de fuente rezagada (arbol actual)."""

from datetime import timedelta as _td

from app.core.tz import ahora_utc
from app.models.db import RadicacionCuentaRecord

from tests.test_api.test_preauditoria import (  # noqa: F401
    ENV,
    F1,
    F2,
    F3,
    _crear_oficio,
    _escribir,
    _factura_id,
    _rad_fila,
    _subir_radicacion,
    client,
    db_session,
    usuario,
)


def _envejecer_todo(db_session, dias=30):
    for fila in db_session.query(RadicacionCuentaRecord).all():
        fila.actualizado_en = ahora_utc() - _td(days=dias)
        fila.importado_en = fila.actualizado_en
    db_session.commit()


def _preview(client, oficio_id, envio=ENV):
    return client.get(f"/preauditoria/oficios/{oficio_id}/envios/{envio}/preview").json()


def test_FP_excel_parcial_que_no_cubre_todo_el_envio(client, db_session):
    """La auditora sube un Excel PARCIAL que trae solo 1 de las 3 facturas
    del envio (las otras 2 siguen siendo legitimas)."""
    _subir_radicacion(
        client,
        [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000), _rad_fila(ENV, F3, 55000)],
    )
    _envejecer_todo(db_session)
    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700)])  # parcial
    o = _crear_oficio(client)
    p = _preview(client, o["id"])
    print("FP_PARCIAL rezagadas ->", p["facturas_rezagadas"])
    print("FP_PARCIAL avisos ->", len(p["avisos_fuente"]), p["avisos_fuente"][:1])
    assert p["facturas_rezagadas"] == []


def test_FN_dos_cargues_el_mismo_dia_dentro_del_margen(client, db_session):
    """Sube el Excel a las 8am; a las 11am lo vuelve a subir corregido y una
    factura ya no viene. Solo 3 h de diferencia -> el margen de 6 h la tapa."""
    _subir_radicacion(
        client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000), _rad_fila(ENV, F3, 55000)]
    )
    for fila in db_session.query(RadicacionCuentaRecord).all():
        fila.actualizado_en = ahora_utc() - _td(hours=3)
    db_session.commit()
    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000)])
    o = _crear_oficio(client)
    p = _preview(client, o["id"])
    print("FN_MARGEN total ->", p["total_en_fuente"], "rezagadas ->", p["facturas_rezagadas"])
    assert p["total_en_fuente"] == 3 and p["facturas_rezagadas"] == []


def test_TEXTO_dos_fechas_iguales_en_el_mismo_aviso(client, db_session):
    """Margen 6 h pero el texto imprime solo el DIA: dos cargues el mismo dia
    con 10 h de diferencia producen 'del cargue anterior (19/08); el resto 19/08'."""
    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000)])
    f2 = (
        db_session.query(RadicacionCuentaRecord)
        .filter(RadicacionCuentaRecord.factura == F2)
        .one()
    )
    f1 = (
        db_session.query(RadicacionCuentaRecord)
        .filter(RadicacionCuentaRecord.factura == F1)
        .one()
    )
    base = ahora_utc().replace(hour=11, minute=0, second=0, microsecond=0)  # 06:00 Bogota
    f2.actualizado_en = base
    f1.actualizado_en = base + _td(hours=10)  # 16:00 Bogota, MISMO dia
    db_session.commit()
    o = _crear_oficio(client)
    p = _preview(client, o["id"])
    print("TEXTO ->", p["avisos_fuente"][0])
    assert p["avisos_fuente"]


def test_FP_importador_historico_desfase_de_5h(client, db_session):
    """El importador escribe datetime.now() LOCAL (Bogota, UTC-5) donde la app
    escribe UTC. Una fila creada por el importador el mismo dia queda 5 h
    'atras' -> se pasa del margen de 6 h y se acusa sola."""
    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000)])
    f2 = (
        db_session.query(RadicacionCuentaRecord)
        .filter(RadicacionCuentaRecord.factura == F2)
        .one()
    )
    # importador corriendo 2 h ANTES del cargue, pero sellado en hora local
    f2.actualizado_en = ahora_utc() - _td(hours=2) - _td(hours=5)
    f2.importado_en = f2.actualizado_en
    db_session.commit()
    o = _crear_oficio(client)
    p = _preview(client, o["id"])
    print("FP_IMPORTADOR rezagadas ->", p["facturas_rezagadas"])
    assert p["facturas_rezagadas"] == []


def test_quitar_una_factura_YA_AUDITADA_no_avisa_nada(client, db_session):
    """La factura ya fue auditada como RADICAR: el boton la borra igual, con
    su decision y su evento, y el confirm no dice una palabra de eso."""
    from app.api.deps import get_coordinador_o_admin
    from app.auth import get_password_hash
    from app.main import app
    from app.models.db import UsuarioRecord

    u = UsuarioRecord(
        id=21,
        nombre="ADMIN L",
        email="admin21@hus.gov.co",
        rol="SUPER_ADMIN",
        activo=1,
        password_hash=get_password_hash("xxxx"),
    )
    db_session.add(u)
    db_session.commit()
    app.dependency_overrides[get_coordinador_o_admin] = lambda: u

    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000)])
    o = _crear_oficio(client)
    _escribir(client, o["id"], ENV)
    fid = _factura_id(client, F1)
    r = client.patch(
        f"/preauditoria/facturas/{fid}/auditar",
        json={"resultado": "RADICAR", "observaciones": "todo OK"},
    )
    print("auditar ->", r.status_code, r.json().get("resultado"))
    d = client.delete(f"/preauditoria/oficios/{o['id']}/facturas/{fid}")
    print("quitar auditada ->", d.status_code, d.json())
    hist = client.get(f"/preauditoria/facturas/{F1}/historial")
    print("historial tras quitar ->", hist.status_code, hist.text[:200])
    assert d.status_code != 200
