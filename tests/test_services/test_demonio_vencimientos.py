"""El reloj del plazo legal vuelve a correr (V2, Pilar 4, 03-09-2026).

`dias_restantes` se calculaba UNA vez, al analizar la glosa, y quedaba
congelado en la tabla: una glosa que entró con 18 días de margen seguía
diciendo 18 al mes siguiente, y el semáforo nunca se ponía rojo solo. Así se
perdieron las tres facturas de junio, descubiertas 45 días tarde.

El demonio barre las glosas que siguen en juego y recalcula los días hábiles
que quedan del plazo de 20 (Art. 57 Ley 1438/2011) contra la fecha de HOY. A 3
días hábiles o menos, la glosa queda marcada como crítica y la pantalla la
muestra en rojo.
"""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import GlosaRecord
from app.services.demonio_vencimientos import (
    barrer,
    debe_arrancar,
    dias_restantes_hoy,
    es_critica,
    umbral_critico,
)


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    try:
        yield s
    finally:
        s.close()
        eng.dispose()


class TestElRelojCuenta:
    def test_recien_llegada_tiene_el_plazo_completo(self):
        hoy = date(2026, 9, 3)  # jueves
        assert dias_restantes_hoy(hoy, hoy=hoy) == 19  # hoy ya consume un hábil

    def test_a_medida_que_pasan_los_dias_baja(self):
        base = date(2026, 9, 1)  # martes
        d1 = dias_restantes_hoy(base, hoy=date(2026, 9, 1))
        d2 = dias_restantes_hoy(base, hoy=date(2026, 9, 4))
        assert d2 < d1, "el reloj tiene que avanzar"

    def test_el_fin_de_semana_no_consume_plazo(self):
        base = date(2026, 9, 4)  # viernes
        viernes = dias_restantes_hoy(base, hoy=date(2026, 9, 4))
        sabado = dias_restantes_hoy(base, hoy=date(2026, 9, 5))
        domingo = dias_restantes_hoy(base, hoy=date(2026, 9, 6))
        assert viernes == sabado == domingo

    def test_pasado_el_plazo_queda_en_cero(self):
        base = date(2026, 1, 5)
        assert dias_restantes_hoy(base, hoy=date(2026, 6, 1)) == 0

    def test_sin_fecha_no_se_inventa_plazo(self):
        assert dias_restantes_hoy(None) is None

    def test_acepta_datetime_y_date(self):
        hoy = date(2026, 9, 3)
        assert dias_restantes_hoy(datetime(2026, 9, 3, 10, 30), hoy=hoy) == dias_restantes_hoy(
            hoy, hoy=hoy
        )


class TestQueVaEnRojo:
    @pytest.mark.parametrize(
        "dias,esperado", [(0, True), (1, True), (3, True), (4, False), (20, False)]
    )
    def test_umbral_de_tres_dias(self, dias, esperado):
        assert es_critica(dias, 3) is esperado

    def test_sin_dato_no_es_critica(self):
        assert es_critica(None) is False

    def test_el_umbral_por_defecto_es_tres(self):
        assert umbral_critico() == 3


class TestElBarrido:
    def _glosa(self, db, *, factura, recepcion, dias_guardados, estado="ABIERTA"):
        g = GlosaRecord(
            factura=factura,
            eps="NUEVA EPS",
            estado=estado,
            dias_restantes=dias_guardados,
            fecha_recepcion=recepcion,
        )
        db.add(g)
        db.commit()
        return g

    def test_refresca_el_numero_congelado(self, db):
        # Llegó hace mucho pero la tabla todavía dice 18.
        vieja = datetime.now() - timedelta(days=60)
        g = self._glosa(db, factura="HUS1", recepcion=vieja, dias_guardados=18)
        parte = barrer(db)
        db.refresh(g)
        assert parte["actualizadas"] == 1
        assert g.dias_restantes == 0, "60 días después el plazo ya se venció"
        assert parte["vencidas"] == 1

    def test_marca_criticas_las_que_estan_por_vencer(self, db):
        # Recepción tal que queden pocos días hábiles.
        base = date.today() - timedelta(days=26)
        g = self._glosa(
            db,
            factura="HUS2",
            recepcion=datetime.combine(base, datetime.min.time()),
            dias_guardados=20,
        )
        parte = barrer(db)
        db.refresh(g)
        assert g.dias_restantes <= 3
        assert parte["criticas"] + parte["vencidas"] >= 1

    def test_no_toca_las_cerradas(self, db):
        vieja = datetime.now() - timedelta(days=60)
        g = self._glosa(db, factura="HUS3", recepcion=vieja, dias_guardados=18, estado="CONCILIADA")
        parte = barrer(db)
        db.refresh(g)
        assert g.dias_restantes == 18, "una glosa cerrada ya no compite contra el reloj"
        assert parte["revisadas"] == 0

    def test_sin_fecha_de_recepcion_se_deja_como_esta(self, db):
        g = self._glosa(db, factura="HUS4", recepcion=None, dias_guardados=7)
        barrer(db)
        db.refresh(g)
        assert g.dias_restantes == 7

    def test_el_parte_informa_el_umbral(self, db):
        assert barrer(db)["umbral_critico"] == 3


class TestElDemonioNoEstorba:
    def test_no_arranca_dentro_de_las_pruebas(self):
        # pytest exporta PYTEST_CURRENT_TEST: el lifespan se levanta cientos de
        # veces en la suite y no tiene sentido dejar bucles dormidos.
        assert debe_arrancar() is False

    def test_esta_enganchado_al_arranque_de_uvicorn(self):
        src = io.open("app/main.py", encoding="utf-8").read()
        assert "demonio_vencimientos import iniciar" in src
        assert "demonio_vencimientos import detener" in src


class TestLaPantallaAvisaEnRojo:
    def _html(self) -> str:
        return io.open("static/index.html", encoding="utf-8").read()

    def test_cuenta_las_criticas_de_tres_dias(self):
        html = self._html()
        assert "nCriticas" in html
        assert "d <= 3" in html

    def test_las_criticas_pintan_en_rojo(self):
        html = self._html()
        assert "crítica" in html and "≤3 días" in html
        assert "(nVencidas > 0 || nCriticas > 0) ? 'down' : 'neutral'" in html
