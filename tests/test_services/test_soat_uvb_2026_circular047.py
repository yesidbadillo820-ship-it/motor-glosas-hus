"""El Manual SOAT 2026 completo — Circular Externa 047 de 2025.

Qué se está cuidando acá: hasta hoy el sistema conocía cuatro tarifas SOAT
(las que alguien transcribió a mano del PDF) y para todas las demás
contestaba «sin tarifa local». Ahora lee las 1.507 de la Circular. Estas
pruebas existen para que ese catálogo no se dañe en silencio: si mañana
alguien regenera el archivo y las cifras cambian, la suite se cae.

La prueba más importante es test_lo_leido_coincide_con_lo_transcrito_a_mano:
compara lo que sacó el lector automático del PDF escaneado contra lo que un
humano transcribió del mismo PDF. Si coinciden, el lector no inventó cifras.
"""

from __future__ import annotations

import gzip
import json

import pytest

from app.services import tarifas_oficiales as TO
from app.services.tarifas_oficiales import (
    TARIFAS_SOAT_2026,
    buscar_tarifa_soat_2026,
    contexto_tarifa_oficial,
    tarifas_soat_2026_completas,
)
from app.services.uvb import calcular_valor_pesos


@pytest.fixture(autouse=True)
def _catalogo_limpio():
    """Cada prueba arranca sin caché, para que ninguna se apoye en otra."""
    TO._CACHE_SOAT_2026 = None
    yield
    TO._CACHE_SOAT_2026 = None


class TestCatalogo:
    def test_trae_la_tabla_completa_y_no_solo_los_ejemplos(self):
        catalogo = tarifas_soat_2026_completas()
        assert len(catalogo) >= 1500, (
            f"Solo {len(catalogo)} códigos: la Circular 047/2025 trae más de 1.500. "
            "¿Se perdió app/data/soat_uvb_2026.json.gz?"
        )

    def test_lo_leido_coincide_con_lo_transcrito_a_mano(self):
        """Los 4 códigos que un humano copió del PDF contra los 1.507 que
        sacó el lector automático del mismo PDF."""
        with gzip.open(TO._RUTA_SOAT_2026, "rt", encoding="utf-8") as f:
            leidos = json.load(f)["tarifas"]
        for codigo, (uvb_mano, _pesos, _desc, _norma) in TARIFAS_SOAT_2026.items():
            assert codigo in leidos, f"El lector no encontró {codigo}"
            assert abs(float(leidos[codigo]["uvb"]) - uvb_mano) < 0.0005, (
                f"{codigo}: transcrito a mano {uvb_mano} UVB, "
                f"leído del PDF {leidos[codigo]['uvb']} UVB"
            )

    @pytest.mark.parametrize(
        "codigo,uvb,pedazo_descripcion",
        [
            ("19001", 5.93, "Acetaminof"),
            ("19505", 0.567, "Hematocrito"),
            ("19575", 305.7, "Histocompatibilidad"),
            ("39205", 22.52, "Grupo 03"),
            ("513014", 1223.71, "cadera"),
            ("518003", 279.87, "artroscópica"),
            ("516003", 524.37, "maxilar inferior"),
            ("31113", 5.11, "ovulación"),
        ],
    )
    def test_tarifas_puntuales_de_la_circular(self, codigo, uvb, pedazo_descripcion):
        fila = buscar_tarifa_soat_2026(codigo)
        assert fila is not None, f"{codigo} debería estar en la Circular 047/2025"
        assert abs(fila["factor_uvb"] - uvb) < 0.0005
        assert pedazo_descripcion.lower() in fila["descripcion"].lower()
        assert fila["norma"] == "CIRCULAR_047_2025"

    def test_ninguna_tarifa_queda_en_cero_ni_negativa(self):
        malas = [c for c, (uvb, *_r) in tarifas_soat_2026_completas().items() if uvb <= 0]
        assert malas == [], f"Códigos con tarifa imposible: {malas[:10]}"

    def test_ningun_codigo_queda_sin_descripcion(self):
        mudos = [c for c, (_u, _v, desc, _n) in tarifas_soat_2026_completas().items() if not desc]
        assert mudos == [], f"Códigos sin descripción: {mudos[:10]}"

    def test_los_pesos_salen_de_la_formula_oficial(self):
        """Valor en pesos = UVB × $12.110 → centena más próxima."""
        for codigo, (uvb, pesos, _d, _n) in list(tarifas_soat_2026_completas().items())[:200]:
            assert pesos == calcular_valor_pesos(uvb, 2026), f"{codigo} mal liquidado"

    def test_lo_transcrito_a_mano_le_gana_a_lo_leido(self):
        catalogo = tarifas_soat_2026_completas()
        for codigo, fila in TARIFAS_SOAT_2026.items():
            assert catalogo[codigo] == fila


class TestLoQueYaNoContestaSinTarifa:
    """Códigos reales que antes devolvían None y ahora tienen tarifa."""

    @pytest.mark.parametrize("codigo", ["513014", "507002", "509001", "39205", "26102"])
    def test_ahora_si_hay_tarifa(self, codigo):
        assert buscar_tarifa_soat_2026(codigo) is not None

    def test_un_codigo_inventado_sigue_sin_tarifa(self):
        """No inventar: si el código no está en la Circular, no hay tarifa."""
        assert buscar_tarifa_soat_2026("999999") is None
        assert buscar_tarifa_soat_2026("") is None
        assert buscar_tarifa_soat_2026("   ") is None


class TestBloqueQueLeeLaIA:
    def test_los_pesos_van_escritos_a_la_colombiana(self):
        """Al prompt no puede llegar '$14,819,100': la IA lo copia tal cual
        al dictamen que se radica a la EPS."""
        txt = contexto_tarifa_oficial("513014")
        assert "$14.819.100" in txt
        assert "14,819,100" not in txt

    def test_cita_la_norma_y_no_se_la_inventa(self):
        txt = contexto_tarifa_oficial("513014")
        assert "Circular 047/2025" in txt
        assert "Reemplazo protésico total primario de cadera" in txt

    def test_sin_codigo_no_hay_bloque(self):
        assert contexto_tarifa_oficial("999999") == ""


class TestSiFaltaElArchivo:
    def test_sin_catalogo_el_sistema_no_se_cae(self, monkeypatch):
        """Si el .gz no está, quedan los cuatro transcritos a mano y ya —
        nunca una tarifa inventada."""
        monkeypatch.setattr(TO, "_RUTA_SOAT_2026", "/ruta/que/no/existe.json.gz")
        TO._CACHE_SOAT_2026 = None
        catalogo = tarifas_soat_2026_completas()
        assert catalogo == TARIFAS_SOAT_2026

    def test_con_catalogo_dañado_tampoco(self, monkeypatch, tmp_path):
        roto = tmp_path / "roto.json.gz"
        roto.write_bytes(b"esto no es un gzip")
        monkeypatch.setattr(TO, "_RUTA_SOAT_2026", str(roto))
        TO._CACHE_SOAT_2026 = None
        assert tarifas_soat_2026_completas() == TARIFAS_SOAT_2026


class TestMetaDelCatalogo:
    def test_el_archivo_dice_de_donde_salio(self):
        with gzip.open(TO._RUTA_SOAT_2026, "rt", encoding="utf-8") as f:
            meta = json.load(f)["_meta"]
        assert meta["norma"] == "CIRCULAR_047_2025"
        assert meta["version"] == "2026-CIRCULAR-047-2025"
        assert meta["paginas_leidas"] == 49
        assert meta["codigos"] >= 1500
        assert meta["codigos_en_conflicto"] == []
