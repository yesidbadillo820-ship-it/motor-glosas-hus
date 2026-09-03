"""Los días restantes se calculan al leer, no se guardan (V2, Pilar 4, 03-09-2026).

La columna `dias_restantes` se escribía una vez, al analizar, y quedaba
congelada. La corrección por barrido periódico se descartó por orden del
auditor: el tiempo es continuo, no se persiste. Ahora `motor_vencimientos.
evaluar()` calcula el plazo EN CALIENTE por glosa —radicación contra HOY,
días hábiles descontando fines de semana y festivos colombianos— y la columna
guardada queda solo como respaldo para glosas sin fechas.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.vencimiento_dinamico import (
    dias_restantes_de,
    dias_restantes_hoy,
    es_critica,
    umbral_critico,
)


def _feriado_entre_semana_2026() -> date:
    """Un festivo colombiano de 2026 que caiga lunes-viernes, tomado del
    calendario real del sistema (FERIADOS_CO): la prueba no inventa fechas."""
    from app.services.glosa_service import FERIADOS_CO

    for f in FERIADOS_CO:
        d = date.fromisoformat(f)
        if d.year == 2026 and d.weekday() < 5:
            return d
    pytest.skip("FERIADOS_CO no trae festivos 2026 entre semana")


class TestElRelojCorreSolo:
    def test_el_mismo_dia_no_consume_plazo(self):
        hoy = date(2026, 9, 3)  # jueves
        assert dias_restantes_hoy(hoy, hoy=hoy) == 20

    def test_cada_dia_habil_consume_uno(self):
        base = date(2026, 9, 1)  # martes
        assert dias_restantes_hoy(base, hoy=date(2026, 9, 2)) == 19
        assert dias_restantes_hoy(base, hoy=date(2026, 9, 4)) == 17

    def test_el_fin_de_semana_no_consume(self):
        base = date(2026, 9, 4)  # viernes
        assert (
            dias_restantes_hoy(base, hoy=date(2026, 9, 5))  # sábado
            == dias_restantes_hoy(base, hoy=date(2026, 9, 6))  # domingo
            == dias_restantes_hoy(base, hoy=base)
        )

    def test_el_festivo_colombiano_no_consume(self):
        festivo = _feriado_entre_semana_2026()
        vispera = festivo - timedelta(days=1)
        # Del día antes del festivo al festivo mismo: cero hábiles consumidos.
        assert dias_restantes_hoy(vispera, hoy=festivo) == dias_restantes_hoy(
            vispera, hoy=vispera
        ), "un festivo de FERIADOS_CO no puede descontar plazo"

    def test_pasado_el_plazo_queda_en_cero(self):
        assert dias_restantes_hoy(date(2026, 1, 5), hoy=date(2026, 6, 1)) == 0

    def test_sin_fecha_no_se_inventa_plazo(self):
        assert dias_restantes_hoy(None) is None

    def test_acepta_datetime_y_date(self):
        hoy = date(2026, 9, 3)
        assert dias_restantes_hoy(datetime(2026, 9, 1, 10, 30), hoy=hoy) == dias_restantes_hoy(
            date(2026, 9, 1), hoy=hoy
        )


class TestLaBaseDelCalculo:
    def test_manda_la_radicacion_de_la_factura(self):
        hoy = date(2026, 9, 10)
        g = SimpleNamespace(
            fecha_radicacion_factura=datetime(2026, 9, 1),
            fecha_recepcion=datetime(2026, 6, 1),
        )
        assert dias_restantes_de(g, hoy=hoy) == dias_restantes_hoy(date(2026, 9, 1), hoy=hoy)

    def test_sin_radicacion_usa_la_recepcion(self):
        hoy = date(2026, 9, 10)
        g = SimpleNamespace(fecha_radicacion_factura=None, fecha_recepcion=datetime(2026, 9, 1))
        assert dias_restantes_de(g, hoy=hoy) == dias_restantes_hoy(date(2026, 9, 1), hoy=hoy)

    def test_sin_ninguna_fecha_devuelve_none(self):
        assert dias_restantes_de(SimpleNamespace()) is None


class TestQueVaEnRojo:
    @pytest.mark.parametrize(
        "dias,esperado", [(0, True), (1, True), (3, True), (4, False), (20, False)]
    )
    def test_umbral_de_tres_dias_habiles(self, dias, esperado):
        assert es_critica(dias, 3) is esperado

    def test_sin_dato_no_es_critica(self):
        assert es_critica(None) is False

    def test_el_umbral_por_defecto_es_tres(self):
        assert umbral_critico() == 3


class TestEvaluarCalculaEnCaliente:
    """`motor_vencimientos.evaluar()` ya no cree en la columna congelada."""

    def _glosa(self, **kw):
        base = dict(
            estado="ABIERTA",
            workflow_state="RADICADA",
            auditor_email="",
            dias_restantes=18,
            fecha_radicacion_factura=None,
            fecha_recepcion=None,
            factura="HUS1",
            eps="NUEVA EPS",
            codigo_glosa="SO0101",
            valor_objetado=100000.0,
        )
        base.update(kw)
        return SimpleNamespace(**base)

    def test_la_columna_congelada_ya_no_engana(self):
        from app.services.motor_vencimientos import Urgencia, evaluar

        # La tabla dice 18 días, pero la factura se radicó hace tres meses.
        vieja = self._glosa(fecha_radicacion_factura=datetime.now() - timedelta(days=90))
        r = evaluar([vieja])
        assert len(r.en_riesgo) == 1
        assert r.en_riesgo[0].dias_restantes == 0, "el plazo real ya se venció"
        assert r.en_riesgo[0].urgencia is Urgencia.CRITICA
        assert r.en_riesgo[0].como_dict()["dias_restantes"] == 0

    def test_sin_fechas_manda_el_respaldo_guardado(self):
        from app.services.motor_vencimientos import evaluar

        sin_fechas = self._glosa(dias_restantes=1)
        r = evaluar([sin_fechas])
        assert len(r.en_riesgo) == 1
        assert r.en_riesgo[0].dias_restantes == 1

    def test_una_cerrada_no_compite_contra_el_reloj(self):
        from app.services.motor_vencimientos import evaluar

        cerrada = self._glosa(
            estado="CONCILIADA",
            fecha_radicacion_factura=datetime.now() - timedelta(days=90),
        )
        assert evaluar([cerrada]).en_riesgo == []

    def test_no_escribe_nada_en_la_glosa(self):
        from app.services.motor_vencimientos import evaluar

        g = self._glosa(fecha_radicacion_factura=datetime.now() - timedelta(days=90))
        evaluar([g])
        assert g.dias_restantes == 18, "evaluar es pura: no toca el objeto ni la base"


class TestNoQuedaRastroDelDemonio:
    def test_el_modulo_del_barrido_ya_no_existe(self):
        import importlib.util

        assert importlib.util.find_spec("app.services.demonio_vencimientos") is None

    def test_el_arranque_de_uvicorn_no_lo_menciona(self):
        src = io.open("app/main.py", encoding="utf-8").read()
        assert "demonio_vencimientos" not in src
        assert "vencimiento_dinamico" in src  # el comentario que explica el cambio


class TestLaPantallaAvisaEnRojo:
    def _html(self) -> str:
        return io.open("static/index.html", encoding="utf-8").read()

    def test_cuenta_las_criticas_de_tres_dias(self):
        html = self._html()
        assert "nCriticas" in html and "d <= 3" in html

    def test_las_criticas_pintan_en_rojo(self):
        html = self._html()
        assert "≤3 días" in html
        assert "(nVencidas > 0 || nCriticas > 0) ? 'down' : 'neutral'" in html

    def test_ya_no_promete_un_demonio(self):
        assert "demonio" not in self._html().lower()
