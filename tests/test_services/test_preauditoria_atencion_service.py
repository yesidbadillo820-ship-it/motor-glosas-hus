"""La revisión de una factura del ADRES, de punta a punta.

08-09-2026. Junta las cuatro piezas: localizar el RIPS en el servidor, sacar
ingreso y egreso, cotejarlos y contar el plazo desde el egreso.

Lo que se cuida acá:

  · que la regla corra SOLO para las facturas del ADRES;
  · que cuando el RIPS no aparezca, el motivo que llegue a la pantalla sea el
    del servidor («no se encontró en los períodos…»), no uno genérico;
  · que nunca se invente una fecha ni un dictamen.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models.db import Base, RadicacionCuentaRecord
from app.services.preauditoria_atencion_service import revisar

NIT_ADRES = "901037916"


@pytest.fixture
def db():
    motor = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(motor)
    s = sessionmaker(bind=motor)()
    try:
        yield s
    finally:
        s.close()


def _factura(db, numero="HUS0000556635", *, nit=NIT_ADRES, entidad="ADRES", f_factura=None):
    db.add(
        RadicacionCuentaRecord(
            factura=numero,
            envio="228254",
            f_factura=f_factura or datetime(2024, 3, 28),
            f_recibido=datetime(2024, 4, 2),
            valor=6344350.0,
            nit=nit,
            entidad=entidad,
        )
    )
    db.commit()
    return numero


def _sembrar_rips(raiz, periodo, factura, ingreso, egreso):
    carpeta = raiz / periodo / "FACTURAS_SALUD" / factura
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"Rips_{factura}.json").write_text(
        json.dumps(
            {
                "numFactura": factura,
                "usuarios": [
                    {
                        "tipoDocumentoIdentificacion": "CC",
                        "numDocumentoIdentificacion": "63510000",
                        "codSexo": "F",
                        "servicios": {
                            "hospitalizacion": [
                                {"fechaInicioAtencion": ingreso, "fechaEgreso": egreso}
                            ]
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def servidor(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.rips_localizador._raiz_configurada", lambda: str(tmp_path))
    return tmp_path


class TestSoloParaElAdres:
    def test_una_factura_de_eps_no_se_revisa(self, db, servidor):
        _factura(db, nit="800251440", entidad="NUEVA EPS S.A.")
        r = revisar(db, "HUS0000556635", hoy=date(2026, 9, 8))
        assert r["aplica"] is False
        assert "no es del ADRES" in r["motivo"]
        assert r["prescripcion"] is None and r["hallazgos"] == []

    def test_se_reconoce_al_adres_por_el_nit(self, db, servidor):
        _factura(db, nit="901037916-1", entidad="LO QUE SEA")
        assert revisar(db, "HUS0000556635", hoy=date(2026, 9, 8))["aplica"] is True

    def test_se_reconoce_al_adres_por_el_nombre(self, db, servidor):
        _factura(db, nit="", entidad="ADMINISTRADORA DE LOS RECURSOS DEL SGSSS")
        assert revisar(db, "HUS0000556635", hoy=date(2026, 9, 8))["aplica"] is True


class TestElDictamenCompleto:
    def test_una_cuenta_vieja_sale_prescrita(self, db, servidor):
        _factura(db)
        _sembrar_rips(servidor, "202403", "HUS0000556635", "2024-03-10 08:00", "2024-03-25 14:00")
        r = revisar(db, "HUS0000556635", hoy=date(2026, 9, 8))

        assert r["aplica"] is True
        assert r["fechas"]["fecha_egreso"] == "2024-03-25T14:00:00"
        assert r["fechas"]["tipo_atencion"] == "HOSPITALIZACION"
        # 25-03-2024 + 18 meses = 25-09-2025, ya pasó.
        assert r["prescripcion"]["prescrita"] is True
        assert r["prescripcion"]["fecha_corte"] == "2025-09-25"
        assert r["prescripcion"]["estado"] == "PRESCRITA"
        assert "Prescrita" in r["prescripcion"]["resumen"]

    def test_una_cuenta_reciente_sigue_vigente(self, db, servidor):
        _factura(db, f_factura=datetime(2026, 6, 20))
        _sembrar_rips(servidor, "202606", "HUS0000556635", "2026-06-01 08:00", "2026-06-10 09:00")
        r = revisar(db, "HUS0000556635", hoy=date(2026, 9, 8))
        assert r["prescripcion"]["prescrita"] is False
        assert r["prescripcion"]["estado"] == "VIGENTE"
        assert r["prescripcion"]["fecha_corte"] == "2027-12-10"

    def test_todo_el_dictamen_viaja_como_json(self, db, servidor):
        _factura(db)
        _sembrar_rips(servidor, "202403", "HUS0000556635", "2024-03-10 08:00", "2024-03-25 14:00")
        json.dumps(revisar(db, "HUS0000556635", hoy=date(2026, 9, 8)))


class TestLosReparos:
    def test_una_factura_anterior_al_egreso_es_reparo_grave(self, db, servidor):
        # Factura del 28-03 pero el RIPS dice que el paciente salió el 30-03.
        _factura(db, f_factura=datetime(2024, 3, 28))
        _sembrar_rips(servidor, "202403", "HUS0000556635", "2024-03-10 08:00", "2024-03-30 14:00")
        r = revisar(db, "HUS0000556635", hoy=date(2026, 9, 8))
        assert r["hay_reparos_graves"] is True
        assert "FACTURA_ANTES_DEL_EGRESO" in {h["codigo"] for h in r["hallazgos"]}

    def test_el_egreso_declarado_que_no_coincide_se_reporta(self, db, servidor):
        _factura(db)
        _sembrar_rips(servidor, "202403", "HUS0000556635", "2024-03-10 08:00", "2024-03-25 14:00")
        r = revisar(db, "HUS0000556635", hoy=date(2026, 9, 8), egreso_declarado="2024-03-20")
        codigos = {h["codigo"] for h in r["hallazgos"]}
        assert "EGRESO_NO_COINCIDE" in codigos
        assert "SIN_FECHAS_DECLARADAS" not in codigos


class TestCuandoNoHayRips:
    def test_el_motivo_del_servidor_es_el_que_llega_a_la_pantalla(self, db, servidor):
        _factura(db)  # sin sembrar el RIPS
        r = revisar(db, "HUS0000556635", hoy=date(2026, 9, 8))
        assert r["aplica"] is True
        assert r["fechas"] is None
        assert r["prescripcion"] is None
        (reparo,) = [h for h in r["hallazgos"] if h["codigo"] == "RIPS_NO_ENCONTRADO"]
        assert "No se encontró el RIPS" in reparo["mensaje"]
        assert "202403" in reparo["mensaje"]  # dice dónde buscó
        assert not r["hay_reparos_graves"]  # que falte el archivo no es un imposible

    def test_sin_servidor_configurado_lo_dice(self, db, monkeypatch):
        _factura(db)
        monkeypatch.setattr("app.services.rips_localizador._raiz_configurada", lambda: None)
        monkeypatch.delenv("FACTURACION_ELECTRONICA_ROOT", raising=False)
        monkeypatch.delenv("FE_ROOT", raising=False)
        r = revisar(db, "HUS0000556635", hoy=date(2026, 9, 8))
        (reparo,) = [h for h in r["hallazgos"] if h["codigo"] == "RIPS_NO_ENCONTRADO"]
        assert "no está configurado" in reparo["mensaje"].lower()

    def test_una_factura_que_no_esta_en_la_fuente_no_revienta(self, db, servidor):
        r = revisar(db, "HUS0000000001", hoy=date(2026, 9, 8))
        assert r["aplica"] is False  # sin NIT ni entidad no es ADRES


class TestElPlazoEsParametro:
    def test_se_puede_evaluar_con_otro_plazo(self, db, servidor):
        _factura(db)
        _sembrar_rips(servidor, "202403", "HUS0000556635", "2024-03-10 08:00", "2024-03-25 14:00")
        r = revisar(db, "HUS0000556635", hoy=date(2026, 9, 8), meses_plazo=36)
        assert r["prescripcion"]["meses_plazo"] == 36
        assert r["prescripcion"]["fecha_corte"] == "2027-03-25"
        assert r["prescripcion"]["prescrita"] is False


class TestElFalsoPrescritaDeLasSesiones:
    """08-09-2026, HUS559324. El defecto que casi cuesta una cuenta.

    20 sesiones de terapia del 13-feb al 14-mar de 2025. El RIPS trae una
    sola línea con la primera sesión, así que el egreso «deducido» quedaba un
    mes antes del real y la cuenta salía PRESCRITA cuando le faltaban seis
    días. Ahora manda el egreso de la factura y el sistema avisa del reparo.
    """

    CARATULA = (
        "FACTURA ELECTRONICA DE VENTA HUS0000559324\n"
        "Fec Ingreso 13 feb. 2025 06:54 a. m. Fec Egreso 14 mar. 2025 05:29 p. m."
    )

    def _sembrar_caso(self, raiz, con_pdf=True):
        c = raiz / "202609" / "FACTURAS_SALUD" / "HUS0000559324"
        c.mkdir(parents=True, exist_ok=True)
        # El RIPS: una sola línea de procedimiento, sin fecha de salida.
        (c / "Rips_HUS0000559324.json").write_text(
            json.dumps(
                {
                    "numFactura": "HUS0000559324",
                    "usuarios": [
                        {
                            "tipoDocumentoIdentificacion": "CC",
                            "numDocumentoIdentificacion": "63535112",
                            "codSexo": "F",
                            "servicios": {
                                "procedimientos": [{"fechaInicioAtencion": "2025-02-13 06:55"}]
                            },
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        if con_pdf:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas

            pdf = canvas.Canvas(str(c / "fv1.pdf"), pagesize=letter)
            y = 700
            for linea in self.CARATULA.splitlines():
                pdf.drawString(40, y, linea)
                y -= 14
            pdf.save()
        return c

    def test_con_la_factura_a_la_vista_la_cuenta_NO_esta_prescrita(self, db, servidor):
        _factura(db, numero="HUS0000559324", f_factura=datetime(2026, 9, 4))
        self._sembrar_caso(servidor)

        r = revisar(db, "HUS0000559324", hoy=date(2026, 9, 8))
        assert r["prescripcion"]["prescrita"] is False
        assert r["prescripcion"]["estado"] == "POR_VENCER"
        assert r["prescripcion"]["fecha_corte"] == "2026-09-14"
        assert r["origen_del_egreso"] == "la factura impresa"

    def test_sin_la_factura_avisa_que_el_egreso_es_deducido(self, db, servidor):
        _factura(db, numero="HUS0000559324", f_factura=datetime(2026, 9, 4))
        self._sembrar_caso(servidor, con_pdf=False)

        r = revisar(db, "HUS0000559324", hoy=date(2026, 9, 8))
        codigos = {h["codigo"] for h in r["hallazgos"]}
        assert "EGRESO_DEDUCIDO" in codigos
        (aviso,) = [h for h in r["hallazgos"] if h["codigo"] == "EGRESO_DEDUCIDO"]
        assert "verifíquelo en la factura" in aviso["mensaje"]
        assert r["fechas"]["egreso_deducido"] is True
        assert r["origen_del_egreso"] == "el RIPS"

    def test_una_hospitalizacion_con_egreso_propio_no_se_marca_deducida(self, db, servidor):
        _factura(db, f_factura=datetime(2024, 3, 28))
        _sembrar_rips(servidor, "202403", "HUS0000556635", "2024-03-10 08:00", "2024-03-25 14:00")
        r = revisar(db, "HUS0000556635", hoy=date(2026, 9, 8))
        assert r["fechas"]["egreso_deducido"] is False
        assert "EGRESO_DEDUCIDO" not in {h["codigo"] for h in r["hallazgos"]}
        assert r["origen_del_egreso"] == "el RIPS"
