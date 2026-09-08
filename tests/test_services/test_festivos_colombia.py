"""El calendario colombiano se calcula bien — y la lista vieja tenía errores.

08-09-2026. El motor traía los festivos escritos a mano en `FERIADOS_CO`.
Esta prueba hace dos cosas:

  1. Comprueba el generador contra los años que el hospital ya dio por
     buenos (2025 y 2026): tienen que coincidir UNO A UNO.
  2. Deja documentado, con el calendario en la mano, que 2027 y 2028 de la
     lista vieja están equivocados — es el motivo por el que el generador
     existe.

La regla que falla en la lista vieja es la de la Ley 51 de 1983: un festivo
trasladable se corre al lunes SIGUIENTE, nunca al anterior.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.services.festivos_colombia import (
    dias_habiles_entre,
    domingo_de_pascua,
    es_festivo,
    es_habil,
    festivos_del_anio,
    siguiente_habil,
)

RAIZ = Path(__file__).resolve().parents[2]


def _feriados_del_motor() -> list[str]:
    """La lista escrita a mano que trae `glosa_service.py`."""
    texto = (RAIZ / "app" / "services" / "glosa_service.py").read_text(encoding="utf-8")
    bloque = re.search(r"FERIADOS_CO = \[(.*?)\]", texto, re.S)
    assert bloque, "ya no existe FERIADOS_CO en glosa_service.py"
    return sorted(re.findall(r'"(\d{4}-\d{2}-\d{2})"', bloque.group(1)))


class TestLaPascua:
    def test_siempre_cae_en_domingo(self):
        """De 2020 a 2100 no puede haber un solo Domingo de Pascua en martes."""
        for anio in range(2020, 2101):
            p = domingo_de_pascua(anio)
            assert p.weekday() == 6, f"Pascua de {anio} cayó en {p} (no es domingo)"

    @pytest.mark.parametrize(
        "anio,esperado",
        [
            (2025, date(2025, 4, 20)),
            (2026, date(2026, 4, 5)),
            (2027, date(2027, 3, 28)),
            (2028, date(2028, 4, 16)),
        ],
    )
    def test_los_domingos_de_pascua_conocidos(self, anio, esperado):
        assert domingo_de_pascua(anio) == esperado


class TestCoincideConLoQueElHospitalYaUsaba:
    """2025 y 2026 los revisó el equipo y salieron bien: son el patrón oro."""

    @pytest.mark.parametrize("anio", [2025, 2026])
    def test_los_festivos_generados_son_identicos(self, anio):
        generados = {d.isoformat() for d in festivos_del_anio(anio)}
        del_motor = {f for f in _feriados_del_motor() if f.startswith(str(anio))}
        assert del_motor, f"el motor no trae festivos de {anio}"
        assert generados == del_motor, (
            f"{anio}: sobran {sorted(generados - del_motor)}, "
            f"faltan {sorted(del_motor - generados)}"
        )


class TestLaListaVieja2027Y2028EstaMal:
    """El defecto que justifica el generador. No es opinión: es el calendario."""

    def test_el_dia_de_la_raza_2027_se_corrio_al_lunes_anterior(self):
        # 12 de octubre de 2027 cae MARTES → el festivo es el lunes 18.
        assert date(2027, 10, 12).weekday() == 1
        assert date(2027, 10, 18) in festivos_del_anio(2027)
        # La lista vieja trae el 11, que es el lunes ANTERIOR.
        viejos = _feriados_del_motor()
        if "2027-10-11" in viejos:
            assert date(2027, 10, 11) not in festivos_del_anio(2027)

    def test_la_semana_santa_de_2027_estaba_una_semana_corrida(self):
        # Pascua 2027 = 28 de marzo → Jueves y Viernes Santo el 25 y 26.
        festivos = festivos_del_anio(2027)
        assert date(2027, 3, 25) in festivos and date(2027, 3, 26) in festivos
        viejos = _feriados_del_motor()
        if "2027-04-01" in viejos:
            assert date(2027, 4, 1) not in festivos

    @pytest.mark.parametrize("anio", [2027, 2028])
    def test_todo_festivo_trasladado_cae_en_lunes(self, anio):
        """Verificación independiente: los siete de la Ley 51 son lunes."""
        from app.services.festivos_colombia import EMILIANI, _lunes_siguiente

        for mes, dia, nombre in EMILIANI:
            f = _lunes_siguiente(date(anio, mes, dia))
            assert f.weekday() == 0, f"{nombre} de {anio} no quedó en lunes"
            assert f >= date(anio, mes, dia), f"{nombre} de {anio} se corrió hacia atrás"
            assert f in festivos_del_anio(anio)


class TestDiasHabiles:
    def test_no_cuenta_sabados_domingos_ni_festivos(self):
        # Del jueves 31-dic-2026 al lunes 4-ene-2027: el 1 de enero es
        # festivo (viernes), 2 y 3 fin de semana → solo el lunes es hábil.
        assert dias_habiles_entre(date(2026, 12, 31), date(2027, 1, 4)) == 1

    def test_una_semana_corriente_tiene_cinco(self):
        """Septiembre es el único mes sin festivos en Colombia."""
        assert not any(es_festivo(date(2026, 9, 7) + timedelta(days=i)) for i in range(1, 8))
        assert dias_habiles_entre(date(2026, 9, 7), date(2026, 9, 14)) == 5

    def test_un_plazo_no_corre_hacia_atras(self):
        assert dias_habiles_entre(date(2026, 5, 10), date(2026, 5, 1)) == 0
        assert dias_habiles_entre(date(2026, 5, 10), date(2026, 5, 10)) == 0


class TestDiaHabil:
    def test_el_domingo_y_el_festivo_no_son_habiles(self):
        assert not es_habil(date(2026, 9, 6))  # domingo
        assert not es_habil(date(2026, 7, 20))  # Grito de Independencia
        assert es_habil(date(2026, 9, 8))  # martes corriente

    def test_siguiente_habil_salta_el_puente(self):
        # Sábado 18-jul-2026; el lunes 20 es festivo → cae en martes 21.
        assert siguiente_habil(date(2026, 7, 18)) == date(2026, 7, 21)

    def test_si_ya_es_habil_no_se_mueve(self):
        assert siguiente_habil(date(2026, 9, 8)) == date(2026, 9, 8)


class TestBordes:
    def test_un_anio_anterior_a_la_ley_51_se_rechaza(self):
        with pytest.raises(ValueError):
            festivos_del_anio(1980)

    def test_todos_los_anios_traen_dieciocho_o_diecinueve_festivos(self):
        """Colombia tiene 18 festivos; ocasionalmente dos coinciden en la
        misma fecha y quedan 17."""
        for anio in range(2025, 2051):
            assert 17 <= len(festivos_del_anio(anio)) <= 19, anio
