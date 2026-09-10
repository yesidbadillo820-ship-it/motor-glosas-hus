"""El motivo del oficio de devolución sale numerado y una observación por renglón.

08-09-2026 (Yesid, con el DEV-PRE-AUD-0149-2026 en la mano). Los gestores
escriben varias observaciones en un solo motivo separadas con «//», y el PDF
las imprimía como un bloque corrido, ilegible — tanto que al área le habían
dado un *prompt* de IA para numerarlas a mano cada vez. Eso lo hace el sistema:

  · cada «//» es un corte: la siguiente observación arranca con «2- », «3- »…
  · la primera siempre con «1- »,
  · un renglón en blanco entre observaciones,
  · el «//» no se imprime,
  · y no se cambia ni una palabra del texto.

Con UNA sola observación no se toca nada (no se le fuerza el «1- »).
"""

from __future__ import annotations

import re
from datetime import datetime
from io import BytesIO

from app.services.oficio_devolucion_pdf import (
    generar_pdf_oficio_devolucion,
    motivo_para_pdf,
    partes_del_motivo,
)

# El caso real, tal como lo escribió el gestor (arranca con «//»).
REAL = (
    "//EN EL APARTADO III DEL FURIPS, INDICAR CUÁL ES LA DIRECCIÓN DE RESIDENCIA, "
    "YA QUE EN EL INFOPOL SALE COMO CALLE 45 10 OCC 52 CAMPOHERMOSO, MIENTRAS QUE "
    "EN EL FURIPS SALE CL 104C 12A 13. // EN LA FACTURA ELECTRÓNICA DE VENTA FALTA "
    "EL SERVICIO FMO01298 PLACA L ARNETT CON PUENTE LARGO DE 0.8MM DE GROSOR "
    "SISTEMA 2.0MM. // FALTA TARJETA TRIPLE IMPLANTE CON LOS SERVICIOS: 1 FMO01286 "
    "TORNILLO MAXDRIVE DEL SISTEMA 1.5MM X 3MM A 8MM CANT: 10,00"
)


class TestPartirElMotivo:
    def test_cada_doble_barra_es_un_corte_y_la_del_inicio_no_cuenta(self):
        partes = partes_del_motivo(REAL)
        assert len(partes) == 3
        assert partes[0].startswith("EN EL APARTADO III DEL FURIPS")
        assert partes[1].startswith("EN LA FACTURA ELECTRÓNICA")
        assert partes[2].startswith("FALTA TARJETA TRIPLE IMPLANTE")

    def test_no_cambia_ni_una_palabra(self):
        """Regla estricta del área: solo separar y numerar, nunca reescribir."""
        partes = partes_del_motivo(REAL)
        assert partes[0].endswith("EN EL FURIPS SALE CL 104C 12A 13.")
        assert "SISTEMA 2.0MM." in partes[1]
        assert "CANT: 10,00" in partes[2]

    def test_una_sola_observacion_queda_tal_cual(self):
        assert partes_del_motivo("Falta FURIPS") == ["Falta FURIPS"]
        assert motivo_para_pdf("Falta FURIPS") == "Falta FURIPS"  # sin «1- » forzado

    def test_vacio_o_nulo_es_raya(self):
        assert partes_del_motivo(None) == []
        assert partes_del_motivo("   ") == []
        assert motivo_para_pdf(None) == "—"
        assert motivo_para_pdf("//") == "—"

    def test_si_el_gestor_ya_numero_a_mano_no_se_duplica(self):
        """«1- A // 2- B» no puede salir como «1- 1- A»."""
        assert partes_del_motivo("1- FALTA A // 2- FALTA B") == ["FALTA A", "FALTA B"]
        assert motivo_para_pdf("1- FALTA A // 2- FALTA B") == "1- FALTA A<br/><br/>2- FALTA B"


class TestParaElPdf:
    def test_numera_y_deja_un_renglon_en_blanco_entre_observaciones(self):
        salida = motivo_para_pdf(REAL)
        assert salida.startswith("1- EN EL APARTADO III DEL FURIPS")
        assert "<br/><br/>2- EN LA FACTURA ELECTRÓNICA" in salida
        assert "<br/><br/>3- FALTA TARJETA TRIPLE IMPLANTE" in salida
        assert "//" not in salida

    def test_escapa_lo_que_rompia_el_pdf(self):
        """Un «<» o un «&» en el motivo tumbaba el párrafo de reportlab."""
        salida = motivo_para_pdf("VALOR < AL PACTADO // CUPS & TARIFA")
        assert "&lt;" in salida and "&amp;" in salida
        assert "<br/><br/>" in salida  # los cortes SÍ siguen siendo etiquetas


class TestElPdfDeVerdad:
    def _texto(self, pdf: bytes) -> str:
        from PyPDF2 import PdfReader

        crudo = "".join(p.extract_text() or "" for p in PdfReader(BytesIO(pdf)).pages)
        return re.sub(r"\s+", " ", crudo)

    def test_el_oficio_imprime_las_observaciones_numeradas(self):
        pdf = generar_pdf_oficio_devolucion(
            consecutivo="DEV-PRE-AUD-0149-2026",
            fecha_generado=datetime(2026, 9, 8, 9, 54),
            numero_radicado="FHUS-AS-I01299-26",
            facturas=[
                {
                    "envio": "234296",
                    "factura": "HUS0000556635",
                    "fecha_factura": datetime(2026, 8, 28),
                    "valor": 6344350,
                    "nit": "860002180",
                    "entidad": "SEGUROS COMERCIALES BOLIVAR S.A.",
                    "oficio": "FHUS-AS-I01299-26",
                    "motivo_devolucion": REAL,
                }
            ],
            generado_por="ELIAS CARVAJAL",
            fecha_recibido=datetime(2026, 9, 3, 14, 3),
        )
        assert pdf[:5] == b"%PDF-"
        texto = self._texto(pdf)
        assert "1- EN EL APARTADO III DEL FURIPS" in texto
        assert "2- EN LA FACTURA ELECTRÓNICA" in texto
        assert "3- FALTA TARJETA TRIPLE IMPLANTE" in texto
        assert "//" not in texto

    def test_un_motivo_con_simbolos_ya_no_tumba_el_pdf(self):
        pdf = generar_pdf_oficio_devolucion(
            consecutivo="DEV-PRE-AUD-0150-2026",
            fecha_generado=datetime(2026, 9, 8, 10, 0),
            numero_radicado="FHUS-AS-I01300-26",
            facturas=[{"factura": "HUS1", "valor": 1, "motivo_devolucion": "VALOR < PACTADO & X"}],
        )
        assert pdf[:5] == b"%PDF-"
        assert "VALOR < PACTADO & X" in self._texto(pdf)
