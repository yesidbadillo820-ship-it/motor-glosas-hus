"""Al analizar una glosa de soportes, el auditor tiene que ver qué falta.

09-09-2026. Es la otra mitad del pedido de Yesid —«que cuando analicen una
glosa vean qué van a auditar»— que quedó sin hacer cuando se entregó el
panel de tarifas.

Para una glosa de TARIFAS, «lo que va a auditar» es el renglón del contrato.
Para una de SOPORTES —donde más plata se pierde— es esta lista, y tiene tres
fuentes distintas que el motor ya conocía por separado:

  · **lo que la causal exige** — `catalogo_glosas.soportes_que_pide`, o sea
    lo que la Resolución 2284 pide para responder ESE código;
  · **lo que hay en el expediente** — el índice del servidor de radicación;
  · **lo que se adjuntó ahora** — los PDF que subió el gestor.

De ahí sale lo único que el auditor necesita para decidir: **qué falta**.

QUÉ CUIDA ESTA PRUEBA. Que las tres fuentes lleguen sin mezclarse, que basta
UNO de los soportes válidos para la causal, y —lo más importante— que un
índice a medio construir NO se presente como «no hay soportes»: en este motor
«todavía no sé» no es «no hay», y con las dos cosas iguales un dictamen
sacado en mitad de una reindexación acusaba de faltar documentos que sí
estaban.
"""

from __future__ import annotations

import pytest

from app.api.routers.analizar import _evidencia_de_los_soportes


class _Indice:
    """Un índice de soportes de mentiras, con los dos estados que importan."""

    def __init__(self, encontrados=None, construyendo=False):
        self._e = encontrados or []
        self._c = construyendo

    def lookup(self, _factura):
        return self._e

    def stats(self):
        return {"construyendo": self._c}


@pytest.fixture
def indice(monkeypatch):
    """Deja poner el índice que cada caso necesite."""

    def _poner(encontrados=None, construyendo=False):
        import app.services.soportes_autodiscovery_service as mod

        monkeypatch.setattr(
            mod, "get_indexer", lambda: _Indice(encontrados, construyendo), raising=False
        )

    return _poner


class TestLoQueLaCausalExige:
    def test_una_glosa_de_soportes_pide_lo_que_dice_la_norma(self, indice):
        indice()
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        tipos = {x["tipo"] for x in ev["pide_la_causal"]}
        assert "epicrisis" in tipos

    def test_los_nombres_salen_en_cristiano(self, indice):
        indice()
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        nombres = [x["nombre"] for x in ev["pide_la_causal"]]
        assert "la epicrisis" in nombres, nombres

    def test_una_causal_que_no_exige_soporte_no_inventa_uno(self, indice):
        indice()
        ev = _evidencia_de_los_soportes(None, "HUS-1", "XX9999", None)
        assert ev["pide_la_causal"] == []
        assert ev["faltan"] == []


class TestQueFaltaYQueNo:
    def test_sin_el_soporte_de_la_causal_se_dice_que_falta(self, indice):
        indice(encontrados=[{"tipo": "rips", "nombre_archivo": "r.json"}])
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        assert ev["faltan"], "No avisó que falta la epicrisis de una glosa SO0101."

    def test_con_el_soporte_no_falta_nada(self, indice):
        indice(encontrados=[{"tipo": "epicrisis", "nombre_archivo": "epi.pdf"}])
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        assert ev["faltan"] == []

    def test_basta_UNO_de_los_que_sirven(self, indice):
        """La epicrisis y la hoja de urgencias prueban lo mismo según el caso:
        exigir las dos sería inventar un requisito que la norma no pone."""
        indice(encontrados=[{"tipo": "hoja_atencion_urgencias", "nombre_archivo": "u.pdf"}])
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        assert ev["faltan"] == []

    def test_lo_que_hay_se_lista_con_su_archivo(self, indice):
        """El nombre del archivo es lo que le permite al auditor ir a abrirlo."""
        indice(encontrados=[{"tipo": "epicrisis", "nombre_archivo": "EPICRISIS_549713.pdf"}])
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        assert ev["hay_en_el_expediente"][0]["archivo"] == "EPICRISIS_549713.pdf"


class TestTodaviaNoSeNoEsNoHay:
    """El defecto que ya costó una vez: con el índice a medio armar, un
    expediente completo salía como «no se encontró» y bloqueaba la radicación."""

    def test_el_indice_reconstruyendose_se_dice_aparte(self, indice):
        indice(encontrados=[], construyendo=True)
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        assert ev["no_se_pudo_consultar"] is True

    def test_y_NO_se_acusa_de_que_falte_nada(self, indice):
        indice(encontrados=[], construyendo=True)
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        assert ev["faltan"] == [], (
            "Acusó de faltar soportes mientras el índice se reconstruía. Esa "
            "factura puede tener el expediente completo."
        )

    def test_con_el_indice_al_dia_y_vacio_si_se_acusa(self, indice):
        """La otra mitad: si el índice SÍ contestó y no hay nada, hay que
        decirlo. Callarlo sería el error contrario."""
        indice(encontrados=[], construyendo=False)
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        assert ev["no_se_pudo_consultar"] is False
        assert ev["faltan"]

    def test_si_el_indice_revienta_tampoco_se_acusa(self, monkeypatch):
        import app.services.soportes_autodiscovery_service as mod

        def _revienta():
            raise RuntimeError("índice caído")

        monkeypatch.setattr(mod, "get_indexer", _revienta, raising=False)
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        assert ev["no_se_pudo_consultar"] is True
        assert ev["faltan"] == []


class TestLoQueSeAdjuntoAhora:
    def test_se_leen_los_pdf_de_este_analisis(self, indice):
        indice()
        contexto = "═══ DOCUMENTO: epicrisis_firmada.pdf ═══\ntexto del pdf"
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", contexto)
        assert "epicrisis_firmada.pdf" in ev["se_adjunto_en_este_analisis"]

    def test_sin_adjuntos_queda_la_lista_vacia_no_None(self, indice):
        indice()
        ev = _evidencia_de_los_soportes(None, "HUS-1", "SO0101", None)
        assert ev["se_adjunto_en_este_analisis"] == []


class TestCuandoNoAplica:
    @pytest.mark.parametrize("factura", [None, "", "   "])
    def test_sin_numero_de_factura_no_hay_panel(self, factura):
        """Sin factura no hay expediente que consultar: inventar un panel
        vacío sería sugerir que se miró algo."""
        assert _evidencia_de_los_soportes(None, factura, "SO0101", None) is None


class TestElContratoDeLaRespuesta:
    def test_el_campo_existe_y_nace_vacio(self):
        from app.models.schemas import GlosaResult

        assert "evidencia_soportes" in GlosaResult.model_fields
        assert GlosaResult.model_fields["evidencia_soportes"].default is None

    def test_el_analisis_lo_llena(self):
        import inspect

        from app.api.routers import analizar

        fuente = inspect.getsource(analizar)
        assert "resultado.evidencia_soportes = _evidencia_de_los_soportes(" in fuente, (
            "La evidencia se arma pero nadie la pone en el resultado: la "
            "pantalla nunca la recibiría."
        )
