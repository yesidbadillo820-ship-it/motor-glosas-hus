"""El homologador CUPS → SOAT 2026 y el código que no existe.

OT-037 · 13-08-2026. Yesid subió el «Homologador CUPS a SOAT año 2026 —
Versión Gold Standard». Al cargarlo apareció un defecto que llevaba meses en
el motor y que no tenía nada que ver con el archivo nuevo:

**La tabla marca 2.966 CUPS como «NO TIENE HOMOLOGACION DIRECTA»**, y esa
frase estaba escrita en la casilla del código SOAT. El motor la leía como si
fuera el código, y le mandaba a la IA, textualmente:

    El CUPS 013205 (…) corresponde oficialmente a los siguientes código(s)
    SOAT del Manual Tarifario:
      • SOAT NO TIENE HOMOLOGACION DIRECTA — NO TIENE HOMOLOGACION DIRECTA
    USA ESTE DATO OFICIAL para fundamentar la tarifa…

Un código inventado, metido en la defensa de la tarifa, con la orden de
usarlo. Entre esos 2.966 hay tarifas del propio contrato de FAMISANAR.

Lo que ahora hace el motor es decir la verdad, que además juega a favor: si
el manual no le asigna código a ese procedimiento, la entidad no puede
objetar la tarifa citando un SOAT que no existe.

Del archivo 2026 se aprovecha además el **artículo del Manual SOAT** donde
está cada código. Es la diferencia entre «corresponde al SOAT 1101» y
«corresponde al SOAT 1101, Artículo 03: Neurocirugía».
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from app.services.cups_soat_service import (
    _cargar,
    bloque_homologacion_para_prompt,
    descripcion_cups,
    homologar_cups_a_soat,
    resumen_homologacion,
    sin_homologacion_directa,
    validar_soat_para_cups,
)

RAIZ = Path(__file__).resolve().parents[2]
DATOS = RAIZ / "app" / "data" / "cups_soat_homologacion.json.gz"

# Sin homologación en el manual. Es además una tarifa del contrato FAMISANAR.
CUPS_SIN_SOAT = "013205"
# Con homologación múltiple (tres códigos de neurocirugía).
CUPS_CON_SOAT = "012403"


@pytest.fixture(autouse=True)
def _sin_cache():
    _cargar.cache_clear()
    yield
    _cargar.cache_clear()


class TestElCodigoQueNoExisteYaNoSale:
    def test_no_se_devuelve_la_frase_como_si_fuera_un_codigo(self):
        for m in homologar_cups_a_soat(CUPS_SIN_SOAT):
            assert "NO TIENE" not in str(m.get("soat", "")).upper()

    def test_ese_cups_no_devuelve_ningun_codigo(self):
        assert homologar_cups_a_soat(CUPS_SIN_SOAT) == []

    def test_pero_el_motor_sabe_que_no_lo_tiene(self):
        """No es lo mismo «no está en la tabla» que «la tabla dice que no
        tiene»: lo segundo es un hecho probado a favor del hospital."""
        assert sin_homologacion_directa(CUPS_SIN_SOAT) is True

    def test_un_cups_que_no_esta_en_la_tabla_no_se_confunde_con_ese_caso(self):
        assert sin_homologacion_directa("999999") is False
        assert homologar_cups_a_soat("999999") == []

    def test_la_frase_no_llega_al_texto_que_lee_la_ia(self):
        bloque = bloque_homologacion_para_prompt(CUPS_SIN_SOAT)
        assert "SOAT NO TIENE HOMOLOGACION" not in bloque.upper()

    def test_en_ninguna_parte_de_la_tabla_queda_como_codigo(self):
        """Barrido completo: si un solo CUPS lo conserva, vuelve el defecto."""
        with gzip.open(DATOS, "rt", encoding="utf-8") as fh:
            tabla = json.load(fh)["cups_a_soat"]
        malos = [
            c
            for c, v in tabla.items()
            if any("NO TIENE" in str(e.get("soat") or "").upper() for e in v)
        ]
        assert not malos, f"{len(malos)} CUPS conservan la frase como código: {malos[:5]}"

    def test_el_dictamen_recibe_el_hecho_util(self):
        bloque = bloque_homologacion_para_prompt(CUPS_SIN_SOAT)
        assert "NO tiene homologación directa" in bloque
        assert "no puede objetar la tarifa" in bloque.lower()
        assert "PROHIBIDO afirmar que corresponde a algún código SOAT" in bloque

    def test_conserva_la_descripcion_del_procedimiento(self):
        """Aunque no tenga código SOAT, el dictamen tiene que poder nombrar
        el procedimiento."""
        assert "CUERPO CALLOSO" in descripcion_cups(CUPS_SIN_SOAT).upper()


class TestLoQueSeGanaConElArchivo2026:
    def test_la_tabla_es_la_del_gold_standard(self):
        meta = resumen_homologacion()
        assert meta.get("version") == "2026-GOLD-STANDARD"
        assert meta.get("cargado") is True

    def test_no_se_perdio_cobertura(self):
        """El archivo 2026 tiene que cubrir lo mismo que el de 2025: 10.024
        CUPS. Si baja, es que el lector está descartando filas."""
        assert resumen_homologacion().get("cups_unicos") == 10024

    def test_trae_el_articulo_del_manual(self):
        mapeos = homologar_cups_a_soat(CUPS_CON_SOAT)
        assert mapeos, "se perdió un CUPS que sí tiene homologación"
        assert any("ARTICULO" in (m.get("articulo") or "").upper() for m in mapeos)

    def test_el_articulo_se_cita_en_el_texto_de_la_ia(self):
        bloque = bloque_homologacion_para_prompt(CUPS_CON_SOAT)
        assert "SOAT 1101" in bloque
        assert "NEUROCIRUGIA" in bloque.upper()


class TestLoQueYaFuncionabaSigueIgual:
    def test_el_multimapeo_se_conserva(self):
        assert len(homologar_cups_a_soat(CUPS_CON_SOAT)) >= 3

    def test_validar_soat_sigue_reconociendo_el_codigo_bueno(self):
        assert validar_soat_para_cups(CUPS_CON_SOAT, "1101") is True

    def test_validar_soat_rechaza_uno_ajeno(self):
        assert validar_soat_para_cups(CUPS_CON_SOAT, "9999") is False

    def test_un_cups_sin_homologacion_no_valida_ningun_soat(self):
        """Ni siquiera por accidente: si la entidad le asigna un SOAT, es
        una homologación que el manual no respalda."""
        assert validar_soat_para_cups(CUPS_SIN_SOAT, "1101") is False

    def test_el_cups_sin_ceros_a_la_izquierda_tambien_se_encuentra(self):
        assert homologar_cups_a_soat("12403") == homologar_cups_a_soat("012403")
