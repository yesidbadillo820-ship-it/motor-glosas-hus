"""Scratch debug: ver los timestamps reales de la fuente."""

from datetime import timedelta as _td

from app.core.tz import ahora_utc
from app.models.db import RadicacionCuentaRecord

from tests.test_api.test_preauditoria import (  # noqa: F401
    ENV,
    F1,
    F2,
    F3,
    _crear_oficio,
    _rad_fila,
    _subir_radicacion,
    client,
    db_session,
    usuario,
)


def _dump(db_session, etiqueta):
    print("---", etiqueta)
    for f in db_session.query(RadicacionCuentaRecord).order_by(RadicacionCuentaRecord.factura):
        db_session.refresh(f)
        print(f"   {f.factura} env={f.envio} imp={f.importado_en!r} act={f.actualizado_en!r}")


def test_dbg_nueva_fila_timestamps(client, db_session):
    _subir_radicacion(client, [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000)])
    _dump(db_session, "tras primer cargue")
    for fila in db_session.query(RadicacionCuentaRecord).all():
        fila.actualizado_en = ahora_utc() - _td(days=30)
        fila.importado_en = fila.actualizado_en
    db_session.commit()
    _dump(db_session, "tras envejecer 30 dias")
    r = _subir_radicacion(
        client,
        [_rad_fila(ENV, F1, 250700), _rad_fila(ENV, F2, 98000), _rad_fila(ENV, F3, 55000)],
    )
    print("upsert ->", r.json())
    _dump(db_session, "tras agregar F3 (nueva legitima)")
    o = _crear_oficio(client)
    p = client.get(f"/preauditoria/oficios/{o['id']}/envios/{ENV}/preview").json()
    print("rezagadas ->", p["facturas_rezagadas"])
    print("avisos ->", p["avisos_fuente"])
