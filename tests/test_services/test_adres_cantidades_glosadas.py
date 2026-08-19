"""Las cantidades del ADRES llegan a la pantalla, incluida la glosada.

19-08-2026. El reporte del ADRES trae cinco columnas por renglón: Cantidad
Reclamado, Valor Reclamado, Cantidad Aprobada, Valor Aprobado y Valor Glosado.
El sistema las guardaba todas, pero solo le mandaba cuatro a la pantalla: la
CANTIDAD APROBADA se quedaba en la base de datos.

Sin ese dato el gestor no puede saber cuántos ítems le glosaron. Pasa de
verdad: en el paquete 31068 hay 277 renglones donde el ADRES reclamó unos
ítems y aprobó otros — por ejemplo la factura HUS353885, dispositivo
2022DM-0008875-R1, con 3 reclamados, 1 aprobado y $9.200 glosados. El gestor
veía «$9.200 glosados» y ninguna cantidad, así que al aceptar declaraba la
cantidad completa.
"""

from __future__ import annotations

from app.models.db import GlosaAdresRecord
from app.services.preauditoria_adres import cantidad_glosada, glosa_dict


def _glosa(**campos) -> GlosaAdresRecord:
    base = dict(
        id=1,
        codigo="2022DM-0008875-R1",
        descripcion="EQUIPO DE INFUSION",
        cant_reclamada=3.0,
        valor_reclamado=13800.0,
        cant_aprobada=1.0,
        valor_aprobado=4600.0,
        valor_glosado=9200.0,
    )
    base.update(campos)
    return GlosaAdresRecord(**base)


def test_la_pantalla_recibe_las_cinco_columnas_del_adres():
    d = glosa_dict(_glosa())
    assert d["cant_reclamada"] == 3.0
    assert d["valor_reclamado"] == 13800.0
    assert d["cant_aprobada"] == 1.0
    assert d["valor_aprobado"] == 4600.0
    assert d["valor_glosado"] == 9200.0


def test_la_cantidad_glosada_es_lo_reclamado_menos_lo_aprobado():
    # El caso real de HUS353885: reclamó 3, le aprobaron 1, le glosaron 2.
    assert glosa_dict(_glosa())["cant_glosada"] == 2.0


def test_glosa_total_del_renglon_glosa_toda_la_cantidad():
    d = glosa_dict(_glosa(cant_aprobada=0.0, valor_aprobado=0.0, valor_glosado=13800.0))
    assert d["cant_glosada"] == 3.0


def test_glosa_de_tarifa_no_glosa_cantidad():
    # HUS354131, CUPS 21706: 1 reclamado, 1 aprobado, $100 glosados. No le
    # quitaron ítems, le bajaron el precio: la cantidad glosada es CERO y eso
    # es correcto, no un dato faltante.
    d = glosa_dict(
        _glosa(
            codigo="21706",
            cant_reclamada=1.0,
            valor_reclamado=799900.0,
            cant_aprobada=1.0,
            valor_aprobado=799800.0,
            valor_glosado=100.0,
        )
    )
    assert d["cant_glosada"] == 0.0
    assert d["valor_glosado"] == 100.0


def test_nunca_devuelve_una_cantidad_glosada_negativa():
    # Si el reporte trae aprobado mayor que reclamado (dato sucio del portal),
    # no se puede decir «menos dos ítems glosados».
    assert cantidad_glosada(1, 3) == 0.0


def test_campos_vacios_no_revientan():
    assert cantidad_glosada(None, None) == 0.0
    assert glosa_dict(_glosa(cant_reclamada=None, cant_aprobada=None))["cant_glosada"] == 0.0
