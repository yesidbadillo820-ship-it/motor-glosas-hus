"""Las fechas de ingreso y egreso salen del RIPS — y si no salen, se dice.

08-09-2026. El módulo abre el `Rips_HUSxxxx.json` del servidor de facturación
electrónica y saca las dos fechas con las que se cuenta el plazo del ADRES.

Lo que más se prueba acá no es el caso bueno: es el archivo que no está, el
que llegó a medias, el que no es un RIPS y el que no trae egreso. En todos,
la respuesta tiene que ser un motivo entendible y NUNCA una fecha inventada.
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.services.rips_fechas_atencion import (
    MAX_BYTES_RIPS,
    FechasAtencion,
    cargar_json,
    fechas_de_archivo,
    fechas_de_datos,
)


def _rips(servicios: dict, factura: str = "HUS0000556635") -> dict:
    return {
        "numDocumentoIdObligado": "900006037",
        "numFactura": factura,
        "usuarios": [
            {
                "tipoDocumentoIdentificacion": "CC",
                "numDocumentoIdentificacion": "63510000",
                "codSexo": "F",
                "fechaNacimiento": "1985-04-12",
                "servicios": servicios,
            }
        ],
    }


HOSPITALIZACION = _rips(
    {
        "hospitalizacion": [
            {
                "fechaInicioAtencion": "2024-03-10 08:00",
                "fechaEgreso": "2024-03-25 14:30",
                "codDiagnosticoPrincipal": "S720",
            }
        ]
    }
)


class TestElCasoBueno:
    def test_una_hospitalizacion_da_ingreso_y_egreso(self):
        f = fechas_de_datos(HOSPITALIZACION, archivo="Rips_HUS0000556635.json")
        assert f.fecha_ingreso == datetime(2024, 3, 10, 8, 0)
        assert f.fecha_egreso == datetime(2024, 3, 25, 14, 30)
        assert f.tipo_atencion == "HOSPITALIZACION"
        assert f.factura == "HUS0000556635"
        assert f.completas and not f.problema

    def test_urgencias_tambien(self):
        datos = _rips(
            {
                "urgencias": [
                    {"fechaInicioAtencion": "2025-01-02 22:10", "fechaEgreso": "2025-01-03 06:00"}
                ]
            }
        )
        f = fechas_de_datos(datos)
        assert f.tipo_atencion == "URGENCIAS"
        assert f.fecha_egreso == datetime(2025, 1, 3, 6, 0)

    def test_una_cuenta_ambulatoria_toma_la_primera_y_la_ultima_atencion(self):
        datos = _rips(
            {
                "consultas": [
                    {"fechaInicioAtencion": "2025-02-10 09:00", "codConsulta": "890201"},
                    {"fechaInicioAtencion": "2025-02-14 11:00", "codConsulta": "890301"},
                ]
            }
        )
        f = fechas_de_datos(datos)
        assert f.tipo_atencion == "AMBULATORIO"
        assert f.fecha_ingreso == datetime(2025, 2, 10, 9, 0)
        assert f.fecha_egreso == datetime(2025, 2, 14, 11, 0)

    def test_el_dict_viaja_como_json(self):
        d = fechas_de_datos(HOSPITALIZACION).a_dict()
        json.dumps(d)
        assert d["fecha_egreso"] == "2024-03-25T14:30:00"
        assert d["completas"] is True


class TestCuandoElRipsNoAlcanza:
    def test_sin_egreso_lo_dice_y_no_lo_inventa(self):
        datos = _rips({"hospitalizacion": [{"fechaInicioAtencion": "2024-03-10 08:00"}]})
        f = fechas_de_datos(datos)
        assert f.fecha_ingreso is not None
        assert f.fecha_egreso is None
        assert not f.completas
        assert "fecha de egreso" in f.problema

    def test_un_json_que_no_es_rips_se_rechaza(self):
        f = fechas_de_datos({"factura": "HUS1", "valor": 100}, archivo="otro.json")
        assert not f.completas
        assert "no es un RIPS" in f.problema

    def test_un_rips_con_estructura_rota_no_revienta(self):
        """`usuarios` vacío incumple la norma: se reporta, no se cae."""
        f = fechas_de_datos({"numFactura": "HUS1", "usuarios": []})
        assert not f.completas
        assert f.problema  # dice por qué, sin excepción


class TestArchivosDelServidor:
    def test_lee_un_archivo_de_verdad(self, tmp_path):
        p = tmp_path / "Rips_HUS0000556635.json"
        p.write_text(json.dumps(HOSPITALIZACION), encoding="utf-8")
        f = fechas_de_archivo(p)
        assert f.completas
        assert f.archivo == "Rips_HUS0000556635.json"

    def test_tolera_el_bom_de_windows(self, tmp_path):
        p = tmp_path / "Rips_bom.json"
        p.write_text(json.dumps(HOSPITALIZACION), encoding="utf-8-sig")
        assert fechas_de_archivo(p).completas

    def test_tolera_la_codificacion_vieja_del_his(self, tmp_path):
        datos = _rips(
            {
                "hospitalizacion": [
                    {
                        "fechaInicioAtencion": "2024-03-10 08:00",
                        "fechaEgreso": "2024-03-25 14:30",
                        "codDiagnosticoPrincipal": "S720",
                    }
                ]
            }
        )
        datos["usuarios"][0]["nombreMunicipio"] = "PIEDECUESTA - SANTANDER Ñ"
        p = tmp_path / "Rips_latin.json"
        p.write_bytes(json.dumps(datos, ensure_ascii=False).encode("latin-1"))
        assert fechas_de_archivo(p).completas

    def test_si_el_archivo_no_esta_lo_dice(self, tmp_path):
        f = fechas_de_archivo(tmp_path / "Rips_HUS999.json")
        assert not f.completas
        assert "no se encontró" in f.problema

    def test_un_archivo_vacio_no_es_un_rips(self, tmp_path):
        p = tmp_path / "Rips_vacio.json"
        p.write_text("", encoding="utf-8")
        assert "vacío" in fechas_de_archivo(p).problema

    def test_un_archivo_a_medias_no_revienta(self, tmp_path):
        """El share se corta a mitad de copia más seguido de lo que uno cree."""
        p = tmp_path / "Rips_cortado.json"
        p.write_text('{"numFactura": "HUS1", "usuarios": [{"serv', encoding="utf-8")
        f = fechas_de_archivo(p)
        assert not f.completas
        assert "JSON" in f.problema

    def test_una_carpeta_no_es_un_archivo(self, tmp_path):
        assert "no se encontró" in fechas_de_archivo(tmp_path).problema

    def test_un_archivo_enorme_no_se_abre(self, tmp_path, monkeypatch):
        p = tmp_path / "Rips_gigante.json"
        p.write_text(json.dumps(HOSPITALIZACION), encoding="utf-8")
        monkeypatch.setattr("app.services.rips_fechas_atencion.MAX_BYTES_RIPS", 10)
        f = fechas_de_archivo(p)
        assert not f.completas
        assert "no se abrió" in f.problema

    def test_el_tope_de_tamano_es_razonable(self):
        assert 10 * 1024 * 1024 <= MAX_BYTES_RIPS <= 200 * 1024 * 1024


class TestCargarJson:
    def test_devuelve_el_motivo_y_no_lanza(self, tmp_path):
        datos, problema = cargar_json(tmp_path / "no_existe.json")
        assert datos is None and problema

    def test_un_json_que_es_una_lista_no_sirve(self, tmp_path):
        p = tmp_path / "lista.json"
        p.write_text("[1, 2, 3]", encoding="utf-8")
        datos, problema = cargar_json(p)
        assert datos is None
        assert "no tiene la forma de un RIPS" in problema


class TestElContrato:
    def test_sin_fechas_no_esta_completo(self):
        assert not FechasAtencion().completas
        assert not FechasAtencion(fecha_ingreso=datetime(2025, 1, 1)).completas
        assert FechasAtencion(
            fecha_ingreso=datetime(2025, 1, 1), fecha_egreso=datetime(2025, 1, 2)
        ).completas

    def test_es_inmutable(self):
        f = FechasAtencion()
        with pytest.raises(Exception):
            f.fecha_egreso = datetime(2025, 1, 1)
