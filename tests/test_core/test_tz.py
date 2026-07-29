"""Tests del helper TZ-aware (R52 C)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.tz import TZ_BOGOTA, a_utc, ahora_utc, dias_completos


class TestAhoraUtc:
    def test_devuelve_tz_aware(self):
        ahora = ahora_utc()
        assert ahora.tzinfo is not None
        assert ahora.tzinfo == timezone.utc

    def test_resta_funciona_con_columna_tz_aware(self):
        """REGRESIÓN: ahora_utc() - tz_aware no debe lanzar TypeError.

        Antes con datetime.utcnow() (naive) restando contra un valor
        de columna DateTime(timezone=True) (tz-aware) Python lanzaba:
        'can't subtract offset-naive and offset-aware datetimes'.
        """
        col_tz_aware = datetime.now(timezone.utc) - timedelta(days=2)
        delta = ahora_utc() - col_tz_aware
        assert delta.days == 2

    def test_comparacion_funciona_con_columna_tz_aware(self):
        col_tz_aware = datetime.now(timezone.utc) - timedelta(days=2)
        assert col_tz_aware < ahora_utc()


class TestAUtc:
    def test_naive_se_convierte_a_utc(self):
        naive = datetime(2026, 4, 25, 10, 0)
        out = a_utc(naive)
        assert out.tzinfo is not None
        assert out.tzinfo == timezone.utc
        # Mismo "wall clock", solo agrega tz
        assert out.hour == 10

    def test_tz_aware_no_modifica(self):
        aware = datetime(2026, 4, 25, 10, 0, tzinfo=timezone.utc)
        out = a_utc(aware)
        assert out == aware
        assert out.tzinfo == timezone.utc

    def test_none_retorna_none(self):
        assert a_utc(None) is None

    def test_resta_funciona_tras_normalizar(self):
        """Caso típico: campo de BD que pudo quedar naive (legacy) — se
        normaliza con a_utc() antes de comparar contra ahora_utc()."""
        legado_naive = datetime(2026, 4, 25, 10, 0)
        delta = ahora_utc() - a_utc(legado_naive)
        # No explota — esa era la prueba clave
        assert delta is not None


class TestDiasCompletos:
    """La regla del auditor: un día solo cuenta pasadas 24 horas enteras."""

    def test_menos_de_24_horas_es_cero_aunque_cambie_el_dia(self):
        """De las 11 p.m. del lunes a las 8 a.m. del martes cambió la fecha,
        pero solo pasaron 9 horas: son 0 días."""
        recibido = datetime(2026, 7, 20, 23, 0, tzinfo=TZ_BOGOTA)
        generado = datetime(2026, 7, 21, 8, 0, tzinfo=TZ_BOGOTA)
        assert dias_completos(recibido, generado) == 0

    def test_exactamente_24_horas_es_un_dia(self):
        recibido = datetime(2026, 7, 20, 14, 35, tzinfo=TZ_BOGOTA)
        generado = datetime(2026, 7, 21, 14, 35, tzinfo=TZ_BOGOTA)
        assert dias_completos(recibido, generado) == 1

    def test_un_minuto_antes_de_las_24_horas_sigue_en_cero(self):
        recibido = datetime(2026, 7, 20, 14, 35, tzinfo=TZ_BOGOTA)
        generado = datetime(2026, 7, 21, 14, 34, tzinfo=TZ_BOGOTA)
        assert dias_completos(recibido, generado) == 0

    def test_caso_real_del_oficio(self):
        """22/07 2:35 p.m. → 24/07 11:23 a.m. = 44h 48m = 1 día, no 2."""
        recibido = datetime(2026, 7, 22, 14, 35, tzinfo=TZ_BOGOTA)
        generado = datetime(2026, 7, 24, 11, 23, tzinfo=TZ_BOGOTA)
        assert dias_completos(recibido, generado) == 1

    def test_varios_dias(self):
        recibido = datetime(2026, 7, 1, 8, 0, tzinfo=TZ_BOGOTA)
        generado = datetime(2026, 7, 11, 9, 0, tzinfo=TZ_BOGOTA)
        assert dias_completos(recibido, generado) == 10

    def test_no_depende_de_la_hora_de_registro(self):
        """Dos oficios que estuvieron el mismo tiempo dan el mismo número,
        aunque uno haya entrado a primera hora y el otro al cierre."""
        madrugador = dias_completos(
            datetime(2026, 7, 20, 7, 0, tzinfo=TZ_BOGOTA),
            datetime(2026, 7, 22, 7, 0, tzinfo=TZ_BOGOTA),
        )
        tardio = dias_completos(
            datetime(2026, 7, 20, 18, 0, tzinfo=TZ_BOGOTA),
            datetime(2026, 7, 22, 18, 0, tzinfo=TZ_BOGOTA),
        )
        assert madrugador == tardio == 2

    def test_mismo_instante_es_cero(self):
        m = datetime(2026, 7, 20, 14, 35, tzinfo=TZ_BOGOTA)
        assert dias_completos(m, m) == 0

    def test_fecha_invertida_no_da_negativo(self):
        recibido = datetime(2026, 7, 25, 8, 0, tzinfo=TZ_BOGOTA)
        generado = datetime(2026, 7, 20, 8, 0, tzinfo=TZ_BOGOTA)
        assert dias_completos(recibido, generado) == 0

    def test_sin_alguna_fecha_es_none(self):
        m = datetime(2026, 7, 20, 8, 0, tzinfo=TZ_BOGOTA)
        assert dias_completos(None, m) is None
        assert dias_completos(m, None) is None
        assert dias_completos(None, None) is None

    def test_mezcla_naive_y_aware_no_explota(self):
        """Los campos viejos de la base pueden venir sin zona horaria."""
        naive_utc = datetime(2026, 7, 20, 12, 0)  # se asume UTC
        aware = datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc)
        assert dias_completos(naive_utc, aware) == 2

    def test_compara_en_utc_no_por_reloj_de_pared(self):
        """La misma hora de pared en zonas distintas no son el mismo instante."""
        bogota = datetime(2026, 7, 20, 12, 0, tzinfo=TZ_BOGOTA)  # 17:00 UTC
        utc = datetime(2026, 7, 21, 12, 0, tzinfo=timezone.utc)  # 19 horas después
        assert dias_completos(bogota, utc) == 0
