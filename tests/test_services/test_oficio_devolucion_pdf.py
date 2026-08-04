"""Tests del PDF del oficio de devolución de pre-auditoría.

Cubre el encabezado de trazabilidad que pidió el auditor: cuándo se recibió
el oficio (con hora), cuándo se generó el documento y cuántos días completos
pasaron entre lo uno y lo otro.
"""

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO

from app.core.tz import TZ_BOGOTA
from app.services.oficio_devolucion_pdf import generar_pdf_oficio_devolucion


def _texto(pdf: bytes) -> str:
    """Texto del PDF con los espacios normalizados.

    reportlab parte las líneas donde le conviene, así que sin normalizar
    'Oficio recibido: 22/07/2026 14:35' puede salir cortado y las
    comparaciones fallarían por un salto de línea.
    """
    from PyPDF2 import PdfReader

    crudo = "".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)
    return re.sub(r"\s+", " ", crudo)


FACTURAS = [
    {
        "envio": "231323",
        "factura": "HUS0000533983",
        "fecha_factura": datetime(2026, 7, 6),
        "valor": 767000,
        "nit": "860002180",
        "entidad": "SEGUROS COMERCIALES BOLIVAR S.A.",
        "oficio": "FHUS-AS-I01054-26",
        "motivo_devolucion": "SIN SOPORTES",
    }
]


def _pdf(recibido, generado):
    return generar_pdf_oficio_devolucion(
        consecutivo="DEV-PRE-AUD-0001-2026",
        fecha_generado=generado,
        numero_radicado="FHUS-AS-I01054-26",
        facturas=FACTURAS,
        generado_por="YESID PEREZ",
        fecha_recibido=recibido,
    )


class TestEncabezadoTrazabilidad:
    def test_muestra_recepcion_generacion_y_dias(self):
        """El caso del oficio real: 22/07 2:35 p.m. → 24/07 11:23 a.m."""
        pdf = _pdf(
            datetime(2026, 7, 22, 14, 35, tzinfo=TZ_BOGOTA),
            datetime(2026, 7, 24, 11, 23, tzinfo=TZ_BOGOTA),
        )
        t = _texto(pdf)
        assert "Oficio recibido: 22/07/2026 14:35" in t
        assert "Generado: 24/07/2026 11:23" in t
        # 44h 48m = 1 día completo, no 2 (aunque el calendario cambió dos veces)
        assert "Transcurridos: 1 día" in t

    def test_menos_de_24_horas_dice_cero_dias(self):
        pdf = _pdf(
            datetime(2026, 7, 20, 23, 0, tzinfo=TZ_BOGOTA),
            datetime(2026, 7, 21, 8, 0, tzinfo=TZ_BOGOTA),
        )
        assert "Transcurridos: 0 días" in _texto(pdf)

    def test_plural_con_varios_dias(self):
        pdf = _pdf(
            datetime(2026, 7, 1, 8, 0, tzinfo=TZ_BOGOTA),
            datetime(2026, 7, 11, 9, 0, tzinfo=TZ_BOGOTA),
        )
        assert "Transcurridos: 10 días" in _texto(pdf)

    def test_sin_fecha_de_recepcion_no_inventa_dias(self):
        """Oficios viejos sin hora de recibido: se omiten las dos líneas en
        vez de imprimir un cero que no significa nada."""
        pdf = _pdf(None, datetime(2026, 7, 24, 11, 23, tzinfo=TZ_BOGOTA))
        t = _texto(pdf)
        assert "Oficio recibido:" not in t
        assert "Transcurridos:" not in t
        assert "Generado: 24/07/2026 11:23" in t

    def test_el_resto_del_oficio_sigue_igual(self):
        """El encabezado nuevo no desplazó ni rompió el contenido."""
        pdf = _pdf(
            datetime(2026, 7, 22, 14, 35, tzinfo=TZ_BOGOTA),
            datetime(2026, 7, 24, 11, 23, tzinfo=TZ_BOGOTA),
        )
        t = _texto(pdf)
        assert "DEV-PRE-AUD-0001-2026" in t
        assert "HUS0000533983" in t
        assert "SIN SOPORTES" in t
        assert "YUDY ALEXANDRA AMAYA GUTIERREZ" in t
        assert "YESID PEREZ" in t
