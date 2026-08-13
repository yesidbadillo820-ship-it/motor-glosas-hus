"""Pruebas del semáforo del trámite de glosas en SIIFA.

Lo que se cuida acá es la etapa 4: cuando la EPS reitera, al hospital le
quedan SIETE días hábiles para subsanar. Si esta herramienta clasifica mal
una glosa reiterada —o la da por ganada— el plazo se vence sin que nadie se
entere y la glosa queda en firme.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import siifa_estado_tramite as et  # noqa: E402


def _fila(**kw):
    base = {
        "id_seguimiento_factura_glosa": 1,
        "numero_factura": "HUS465198",
        "tipo_seguimiento": "GLOSA",
        "razon_social_eps": "SANITAS",
        "valor_glosa": 1_396_804,
        "codigo_glosa": "TA0801",
        "tiene_respuesta": "SI",
        "codigo_respuesta": "RE9901",
        "fecha_formulacion": "2026-01-29",
        "fecha_respuesta": "2026-08-05T14:07:00",
        "codigo_reiteracion": "",
        "descripcion_reiteracion": "",
        "codigo_reiteracion_respuesta": "",
    }
    base.update(kw)
    return base


def test_sin_responder_le_toca_al_hospital():
    f = _fila(tiene_respuesta="NO")

    assert et.clasificar(f) == et.SIN_RESPONDER
    assert et.LE_TOCA[et.SIN_RESPONDER] == "HOSPITAL"


def test_respondida_sin_decision_espera_a_la_eps():
    assert et.clasificar(_fila()) == et.ESPERANDO_EPS
    assert et.LE_TOCA[et.ESPERANDO_EPS] == "EPS"


def test_glosa_levantada_es_ganada():
    f = _fila(codigo_reiteracion="GTL002", descripcion_reiteracion="Glosa totalmente levantada")

    assert et.clasificar(f) == et.LEVANTADA


def test_glosa_reiterada_le_devuelve_la_pelota_al_hospital():
    """El caso crítico: 7 días hábiles para subsanar y nadie avisa."""
    f = _fila(codigo_reiteracion="GRE003", descripcion_reiteracion="Glosa Reiterada")

    assert et.clasificar(f) == et.POR_SUBSANAR
    assert et.LE_TOCA[et.POR_SUBSANAR] == "HOSPITAL"


def test_devolucion_reiterada_tambien_le_toca_al_hospital():
    f = _fila(
        tipo_seguimiento="DEVOLUCION",
        codigo_reiteracion="DRE003",
        descripcion_reiteracion="Devolución Reiterada",
    )

    assert et.clasificar(f) == et.POR_SUBSANAR


def test_una_glosa_levantada_a_medias_no_se_da_por_ganada():
    """Si la EPS levanta sólo una parte, el resto sigue vivo y hay que
    subsanarlo. Darla por ganada dejaría ese resto sin defensa."""
    f = _fila(codigo_reiteracion="GPL001", descripcion_reiteracion="Glosa parcialmente levantada")

    assert et.clasificar(f) == et.POR_SUBSANAR


def test_ya_subsanada_vuelve_a_esperar_a_la_eps():
    f = _fila(
        codigo_reiteracion="GRE003",
        descripcion_reiteracion="Glosa Reiterada",
        codigo_reiteracion_respuesta="RE9901",
    )

    assert et.clasificar(f) == et.SUBSANADA
    assert et.LE_TOCA[et.SUBSANADA] == "EPS"


def test_una_decision_sin_descripcion_no_se_toma_por_no_decidida():
    """Si SIIFA manda el código pero no el texto, hay decisión igual.

    Tratarla como «esperando a la EPS» escondería una reiteración: el plazo
    de subsanación correría sin que el informe lo mostrara.
    """
    f = _fila(codigo_reiteracion="GRE003", descripcion_reiteracion="")

    assert et.clasificar(f) == et.POR_SUBSANAR


def test_los_dias_habiles_no_cuentan_fines_de_semana():
    # jueves 6 a lunes 10 de agosto de 2026: viernes, lunes = 2 hábiles
    assert et.habiles(date(2026, 8, 6), date(2026, 8, 10)) == 2
    assert et.habiles(date(2026, 8, 6), date(2026, 8, 6)) == 0


def test_sumar_habiles_cae_en_dia_laboral():
    # viernes 7 + 1 hábil = lunes 10
    assert et.sumar_habiles(date(2026, 8, 7), 1) == date(2026, 8, 10)
    assert et.sumar_habiles(date(2026, 8, 7), 7).weekday() < 5


def test_avisa_cuando_el_plazo_de_subsanacion_esta_vencido():
    f = _fila(
        codigo_reiteracion="GRE003",
        descripcion_reiteracion="Glosa Reiterada",
        fecha_respuesta="2026-07-01T10:00:00",
    )

    ev = et.evaluar([f], date(2026, 8, 13))[0]

    assert ev["etapa"] == et.POR_SUBSANAR
    assert ev["situacion"].startswith("VENCIDA")
    assert ev["le_toca_a"] == "HOSPITAL"


def test_dentro_del_plazo_dice_cuanto_queda():
    f = _fila(
        codigo_reiteracion="GRE003",
        descripcion_reiteracion="Glosa Reiterada",
        fecha_respuesta="2026-08-12T10:00:00",
    )

    ev = et.evaluar([f], date(2026, 8, 13))[0]

    assert ev["situacion"] == "Quedan 6 día(s) hábil(es)"
    assert ev["vence"] == "2026-08-21"


def test_la_eps_tambien_se_vence():
    """Que la EPS incumpla su plazo es reclamable: tiene que verse."""
    f = _fila(fecha_respuesta="2026-06-01T10:00:00")

    ev = et.evaluar([f], date(2026, 8, 13))[0]

    assert ev["etapa"] == et.ESPERANDO_EPS
    assert ev["le_toca_a"] == "EPS"
    assert ev["situacion"].startswith("VENCIDA")


def test_una_subsanacion_recien_cargada_no_sale_vencida():
    """El plazo de la decisión final corre desde la SUBSANACIÓN, no desde la
    primera respuesta —y esa fecha no viene en el informe—.

    Contándolo mal, la subsanación cargada el 13-08 salía «VENCIDA» ese mismo
    día porque la respuesta original era del 5 de agosto. Una mora inventada
    de la EPS es un reclamo que no se puede sostener.
    """
    f = _fila(
        codigo_reiteracion="GRE003",
        descripcion_reiteracion="Glosa Reiterada",
        codigo_reiteracion_respuesta="RE9901",
        fecha_respuesta="2026-08-05T14:07:00",
    )

    ev = et.evaluar([f], date(2026, 8, 13))[0]

    assert ev["etapa"] == et.SUBSANADA
    assert not ev["situacion"].startswith("VENCIDA")
    assert "subsanación" in ev["situacion"]


def test_una_glosa_cerrada_no_tiene_plazo_corriendo():
    f = _fila(
        codigo_reiteracion="GTL002",
        descripcion_reiteracion="Glosa totalmente levantada",
    )

    ev = et.evaluar([f], date(2026, 8, 13))[0]

    assert ev["situacion"] == "Cerrada"
    assert ev["vence"] == ""


def test_sin_fecha_no_se_inventa_un_plazo():
    f = _fila(fecha_respuesta="")

    ev = et.evaluar([f], date(2026, 8, 13))[0]

    assert ev["situacion"] == "Sin fecha para calcular"


def test_el_resumen_va_en_el_orden_del_tramite():
    filas = [
        _fila(tiene_respuesta="NO"),
        _fila(codigo_reiteracion="GTL002", descripcion_reiteracion="Glosa totalmente levantada"),
        _fila(),
    ]

    orden = [e for e, *_ in et.resumen(et.evaluar(filas, date(2026, 8, 13)))]

    assert orden == [et.SIN_RESPONDER, et.ESPERANDO_EPS, et.LEVANTADA]


def test_el_resumen_cuenta_valores_y_vencidas():
    filas = [
        _fila(valor_glosa=1000, fecha_respuesta="2026-06-01T10:00:00"),
        _fila(valor_glosa=2000, fecha_respuesta="2026-08-12T10:00:00"),
    ]

    (_etapa, _toca, n, _f, valor, vencidas) = et.resumen(et.evaluar(filas, date(2026, 8, 13)))[0]

    assert (n, valor, vencidas) == (2, 3000, 1)


def test_las_devoluciones_no_inflan_el_valor_de_la_etapa():
    """Las 1.341 líneas de devolución daban $25.221 millones en la etapa 2,
    donde hay $310 millones. El semáforo usa la misma regla que el resto del
    repo: una devolución vale una vez por factura."""
    filas = [
        _fila(numero_factura="HUS479521", tipo_seguimiento="DEVOLUCION", valor_glosa=3_735_688)
        for _ in range(200)
    ]

    (_etapa, _toca, n, facturas, valor, _v) = et.resumen(et.evaluar(filas, date(2026, 8, 13)))[0]

    assert (n, facturas) == (200, 1)
    assert valor == 3_735_688


def test_el_valor_se_lee_con_el_lector_unico():
    filas = [_fila(valor_glosa="$1.396.804")]

    (*_, valor, _) = et.resumen(et.evaluar(filas, date(2026, 8, 13)))[0]

    assert valor == 1_396_804
