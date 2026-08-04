"""Confianza visible (ronda 32): analizador de confianza del dictamen."""

from __future__ import annotations

from app.services.confianza_dictamen import analizar_confianza


class TestAnalizarConfianza:
    def test_alta_con_contrato_soportes_y_norma(self):
        d = (
            "ESE HUS NO ACEPTA. Conforme a la TARIFA PACTADA en el contrato y al "
            "folio 2 de la historia clínica, y según la Ley 1438 de 2011, se "
            "solicita el levantamiento."
        )
        r = analizar_confianza(d, numero_contrato="CONTRATO S-13-1-03-1-04958", score=8)
        assert r["nivel"] == "alta"
        assert "Contrato real de la EPS" in r["fuentes"]
        assert "Soportes clínicos (folios/HC)" in r["fuentes"]
        assert "Fundamento normativo" in r["fuentes"]

    def test_cita_numero_de_contrato_real(self):
        d = "Según el contrato S-13-1-03-1-04958 vigente, la tarifa es SOAT -5%. Ley 100."
        r = analizar_confianza(d, numero_contrato="CONTRATO S-13-1-03-1-04958", score=7)
        assert r["senales"]["cita_contrato"] is True

    def test_media_solo_norma(self):
        d = "ESE HUS NO ACEPTA. Según la Resolución 3047 de 2008 se solicita levantamiento."
        r = analizar_confianza(d, numero_contrato="", score=6)
        assert r["nivel"] in ("media", "alta")
        assert r["senales"]["cita_norma"] is True
        assert r["senales"]["cita_soportes"] is False

    def test_baja_defensa_generica(self):
        d = "ESE HUS NO ACEPTA la glosa. Se solicita el levantamiento de la misma."
        r = analizar_confianza(d, numero_contrato="", score=None)
        assert r["nivel"] == "baja"
        assert r["fuentes"] == []

    def test_soportes_folio(self):
        d = "El médico tratante dejó constancia en el folio 5 de la epicrisis."
        r = analizar_confianza(d, numero_contrato="", score=None)
        assert r["senales"]["cita_soportes"] is True
