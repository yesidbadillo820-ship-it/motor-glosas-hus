"""El RIPS se encuentra yendo directo a la carpeta, no recorriendo el servidor.

08-09-2026. Estructura real del servidor de facturación electrónica:

    <raíz>/<AAAAMM>/FACTURAS_SALUD/<HUSxxxx>/[RIPS/]Rips_<HUSxxxx>.json

Las pruebas arman esa estructura en carpetas temporales, con las variantes
que de verdad aparecen: la factura archivada en el mes de al lado, la carpeta
con y sin ceros, el RIPS suelto o dentro de `RIPS\\`, y el nombre en
mayúsculas. Y sobre todo: que cuando NO está, conteste rápido y con motivo.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from app.services.rips_localizador import (
    localizar,
    periodo_de,
    periodo_vecino,
    raiz_facturacion_electronica,
)

CONTENIDO = {"numFactura": "HUS0000556635", "usuarios": []}


def _sembrar(raiz, periodo, factura, *, sub="", nombre="Rips_%s.json", tipo="FACTURAS_SALUD"):
    carpeta = raiz / periodo / tipo / factura
    if sub:
        carpeta = carpeta / sub
    carpeta.mkdir(parents=True, exist_ok=True)
    archivo = carpeta / (nombre % factura if "%s" in nombre else nombre)
    archivo.write_text(json.dumps(CONTENIDO), encoding="utf-8")
    return archivo


class TestPeriodos:
    def test_el_periodo_sale_de_la_fecha(self):
        assert periodo_de(date(2026, 3, 15)) == "202603"
        assert periodo_de(datetime(2026, 12, 1, 8, 0)) == "202612"
        assert periodo_de("2026-01-05") == "202601"
        assert periodo_de("2026-01-05 14:30") == "202601"

    def test_una_fecha_que_no_es_fecha_no_da_periodo(self):
        assert periodo_de(None) is None
        assert periodo_de("cuando sea") is None

    def test_el_mes_vecino_cruza_bien_el_ano(self):
        assert periodo_vecino("202601", -1) == "202512"
        assert periodo_vecino("202612", 1) == "202701"
        assert periodo_vecino("202606", 1) == "202607"

    def test_un_periodo_torcido_no_revienta(self):
        assert periodo_vecino("abcd", 1) is None
        assert periodo_vecino("202613", 1) is None


class TestLoEncuentra:
    def test_en_su_carpeta_y_su_periodo(self, tmp_path):
        esperado = _sembrar(tmp_path, "202603", "HUS0000556635")
        r = localizar("HUS0000556635", date(2026, 3, 20), raiz=str(tmp_path))
        assert r.encontrado
        assert r.ruta == str(esperado)
        assert not r.problema

    def test_dentro_de_la_subcarpeta_RIPS(self, tmp_path):
        esperado = _sembrar(tmp_path, "202603", "HUS0000556635", sub="RIPS")
        r = localizar("HUS0000556635", date(2026, 3, 20), raiz=str(tmp_path))
        assert r.ruta == str(esperado)

    def test_aunque_este_archivada_en_el_mes_siguiente(self, tmp_path):
        """Se factura a fin de mes y se radica al principio del otro."""
        esperado = _sembrar(tmp_path, "202604", "HUS0000556635")
        r = localizar("HUS0000556635", date(2026, 3, 31), raiz=str(tmp_path))
        assert r.ruta == str(esperado)

    def test_aunque_este_archivada_en_el_mes_anterior(self, tmp_path):
        esperado = _sembrar(tmp_path, "202602", "HUS0000556635")
        r = localizar("HUS0000556635", date(2026, 3, 2), raiz=str(tmp_path))
        assert r.ruta == str(esperado)

    def test_aunque_la_carpeta_no_traiga_los_ceros(self, tmp_path):
        esperado = _sembrar(tmp_path, "202603", "HUS556635")
        r = localizar("HUS0000556635", date(2026, 3, 20), raiz=str(tmp_path))
        assert r.ruta == str(esperado)

    def test_aunque_el_archivo_este_en_mayusculas(self, tmp_path):
        esperado = _sembrar(tmp_path, "202603", "HUS0000556635", nombre="RIPS_HUS0000556635.JSON")
        r = localizar("HUS0000556635", date(2026, 3, 20), raiz=str(tmp_path))
        assert r.ruta == str(esperado)

    def test_tambien_busca_en_las_notas_credito(self, tmp_path):
        esperado = _sembrar(tmp_path, "202603", "NE12345", tipo="FACTURAS_NOTA")
        r = localizar("NE12345", date(2026, 3, 20), raiz=str(tmp_path))
        assert r.ruta == str(esperado)


class TestCuandoNoEsta:
    def test_lo_dice_con_los_periodos_que_miro(self, tmp_path):
        (tmp_path / "202603" / "FACTURAS_SALUD").mkdir(parents=True)
        r = localizar("HUS0000999999", date(2026, 3, 20), raiz=str(tmp_path))
        assert not r.encontrado
        assert "No se encontró" in r.problema
        assert "202603" in r.problema

    def test_no_se_va_dos_meses_atras_por_su_cuenta(self, tmp_path):
        """Solo mira el mes de la factura y sus vecinos: si estuviera más
        lejos, es un problema de archivo que hay que arreglar allá."""
        _sembrar(tmp_path, "202601", "HUS0000556635")
        r = localizar("HUS0000556635", date(2026, 3, 20), raiz=str(tmp_path))
        assert not r.encontrado

    def test_se_puede_ampliar_la_ventana_de_meses(self, tmp_path):
        esperado = _sembrar(tmp_path, "202601", "HUS0000556635")
        r = localizar("HUS0000556635", date(2026, 3, 20), raiz=str(tmp_path), meses_alrededor=2)
        assert r.ruta == str(esperado)

    def test_sin_fecha_de_factura_no_se_adivina_el_periodo(self, tmp_path):
        _sembrar(tmp_path, "202603", "HUS0000556635")
        r = localizar("HUS0000556635", None, raiz=str(tmp_path))
        assert not r.encontrado
        assert "no se sabe en qué período" in r.problema

    def test_si_el_servidor_no_responde_lo_dice(self, tmp_path):
        r = localizar("HUS1", date(2026, 3, 1), raiz=str(tmp_path / "no_existe"))
        assert not r.encontrado
        assert "No se puede llegar al servidor" in r.problema

    def test_una_carpeta_de_factura_vacia_no_es_un_hallazgo(self, tmp_path):
        (tmp_path / "202603" / "FACTURAS_SALUD" / "HUS0000556635").mkdir(parents=True)
        r = localizar("HUS0000556635", date(2026, 3, 20), raiz=str(tmp_path))
        assert not r.encontrado

    def test_un_pdf_no_se_confunde_con_el_rips(self, tmp_path):
        carpeta = tmp_path / "202603" / "FACTURAS_SALUD" / "HUS0000556635"
        carpeta.mkdir(parents=True)
        (carpeta / "FEV_900006037_HUS0000556635.pdf").write_text("x", encoding="utf-8")
        assert not localizar("HUS0000556635", date(2026, 3, 20), raiz=str(tmp_path)).encontrado


class TestLaConfiguracion:
    def test_sin_configurar_no_se_inventa_una_ruta(self, monkeypatch):
        monkeypatch.delenv("FACTURACION_ELECTRONICA_ROOT", raising=False)
        monkeypatch.delenv("FE_ROOT", raising=False)
        monkeypatch.setattr("app.services.rips_localizador._raiz_configurada", lambda: None)
        assert raiz_facturacion_electronica() == ""
        r = localizar("HUS1", date(2026, 3, 1))
        assert not r.encontrado
        assert "no está configurado" in r.problema.lower()

    def test_la_variable_de_entorno_sirve(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.services.rips_localizador._raiz_configurada", lambda: None)
        monkeypatch.setenv("FACTURACION_ELECTRONICA_ROOT", str(tmp_path))
        assert raiz_facturacion_electronica() == str(tmp_path)

    def test_el_archivo_de_configuracion_manda_sobre_la_variable(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FACTURACION_ELECTRONICA_ROOT", "/otra/cosa")
        monkeypatch.setattr(
            "app.services.rips_localizador._raiz_configurada", lambda: str(tmp_path)
        )
        assert raiz_facturacion_electronica() == str(tmp_path)


class TestSeIntegraConElLector:
    def test_lo_que_localiza_se_puede_leer(self, tmp_path):
        """El localizador y el lector encajan sin pegante en el medio."""
        from app.services.rips_fechas_atencion import fechas_de_archivo

        carpeta = tmp_path / "202603" / "FACTURAS_SALUD" / "HUS0000556635"
        carpeta.mkdir(parents=True)
        (carpeta / "Rips_HUS0000556635.json").write_text(
            json.dumps(
                {
                    "numFactura": "HUS0000556635",
                    "usuarios": [
                        {
                            "tipoDocumentoIdentificacion": "CC",
                            "numDocumentoIdentificacion": "1",
                            "codSexo": "M",
                            "servicios": {
                                "hospitalizacion": [
                                    {
                                        "fechaInicioAtencion": "2026-03-10 08:00",
                                        "fechaEgreso": "2026-03-18 10:00",
                                    }
                                ]
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        ubicado = localizar("HUS0000556635", date(2026, 3, 20), raiz=str(tmp_path))
        assert ubicado.encontrado
        fechas = fechas_de_archivo(ubicado.ruta)
        assert fechas.completas
        assert fechas.fecha_egreso.date() == date(2026, 3, 18)


@pytest.mark.parametrize("factura", ["HUS0000556635", "HUS556635", "556635"])
def test_da_igual_como_escriban_la_factura(tmp_path, factura):
    _sembrar(tmp_path, "202603", "HUS0000556635")
    assert localizar(factura, date(2026, 3, 20), raiz=str(tmp_path)).encontrado
