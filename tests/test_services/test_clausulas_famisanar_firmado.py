"""Las cláusulas reales del contrato firmado con FAMISANAR.

OT-032 · 13-08-2026. Yesid subió el CONTRATO FIRMADO FAMISANAR 2026 —219
páginas— con sus anexos 3.0 servicios y tarifas, 3.1 medicamentos y 3.2
suministros. Hasta ese día el motor tenía UNA sola cláusula de FAMISANAR, y
era la del anexo tarifario redactada a mano.

De las nueve cláusulas del contrato, tres son las que sirven para responder
glosas y son las que se sembraron con su texto literal:

  · **Cuarta — Tarifas.** Remite al Anexo Servicios y Tarifas y al Anexo
    Tarifas Medicamentos, y obliga a actualizarlos en cada prórroga mediante
    otrosí. Es la que contesta una glosa TA.
  · **Quinta — Mecanismos y forma de pago.** Los requisitos de la factura y
    el Manual de Cuentas Médicas. Contesta una glosa SO de soportes.
  · **Sexta — Trámite de facturación, glosas, pago y devoluciones.** El
    marco del trámite y el correo al que se reportan las glosas.

Y se corrigió algo que ya no era cierto: la cláusula del anexo tarifario
decía «Propuesta Base Final». Mientras fue propuesta estaba bien; con el
contrato firmado, el dictamen no puede seguir llamándola así — la entidad lo
lee.
"""

from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent


def _clausulas() -> list[dict]:
    with (RAIZ / "data" / "clausulas_contrato_base.json").open(encoding="utf-8") as fh:
        return json.load(fh)["clausulas"]


def _famisanar() -> list[dict]:
    return [c for c in _clausulas() if c["eps"].upper().startswith("FAMISANAR")]


class TestLasTresClausulasDelContrato:
    def test_estan_las_tres(self):
        numeros = {c["numero_clausula"].upper() for c in _famisanar()}
        assert {"CUARTA", "QUINTA", "SEXTA"} <= numeros, numeros

    def test_la_cuarta_es_la_de_tarifas(self):
        """Es la que contesta una glosa TA: remite a los anexos."""
        c = next(c for c in _famisanar() if c["numero_clausula"] == "Cuarta")
        assert c["tema"] == "TA"
        t = c["texto_literal"]
        assert "Anexo" in t and "Tarifas" in t
        assert "prórroga" in t.lower(), "falta la obligación de actualizar en cada prórroga"

    def test_la_sexta_es_la_del_tramite_de_glosas(self):
        c = next(c for c in _famisanar() if c["numero_clausula"] == "Sexta")
        t = c["texto_literal"]
        assert "glosas" in t.lower()
        assert "2284 de 2023" in t, "el trámite se rige por la 2284, tiene que estar citada"

    def test_la_quinta_es_la_de_soportes_y_pago(self):
        c = next(c for c in _famisanar() if c["numero_clausula"] == "Quinta")
        assert c["tema"] == "SO"
        assert "Manual de Cuentas Médicas" in c["texto_literal"]

    def test_ninguna_arranca_repitiendo_su_propio_ordinal(self):
        """El PDF trae el ordinal y el título repetidos en la misma línea. Si
        se dejan, el dictamen cita «CUARTA. - TARIFAS. CUARTA. - TARIFAS…»."""
        for c in _famisanar():
            t = c["texto_literal"].upper()
            assert not t.startswith(c["numero_clausula"].upper()), c["numero_clausula"]

    def test_el_texto_es_del_contrato_no_un_resumen(self):
        """Se citan literalmente: si son paráfrasis, el verificador de citas
        las marca como falsas y con razón."""
        for c in _famisanar():
            if c["numero_clausula"] in ("Cuarta", "Quinta", "Sexta"):
                assert len(c["texto_literal"]) >= 300, c["numero_clausula"]


class TestYaNoEsUnaPropuesta:
    def test_ninguna_clausula_la_llama_propuesta(self):
        """Mientras fue propuesta estaba bien decirlo. Con el contrato
        firmado, llamarla así en un dictamen es afirmar algo que no es."""
        for c in _famisanar():
            assert "Propuesta Base Final" not in c["texto_literal"], c["numero_clausula"]

    def test_el_anexo_tarifario_nombra_la_vigencia_del_contrato(self):
        c = next(c for c in _famisanar() if "Anexo" in c["numero_clausula"])
        assert "15/04/2026" in c["texto_literal"]
        assert "14/04/2027" in c["texto_literal"]

    def test_conserva_el_numero_del_contrato(self):
        c = next(c for c in _famisanar() if "Anexo" in c["numero_clausula"])
        assert "S-13-1-03-1-04958" in c["texto_literal"]


class TestElBancoSigueSano:
    def test_ninguna_clausula_quedo_sin_texto(self):
        for c in _clausulas():
            t = (c.get("texto_literal") or "").strip()
            assert t, c.get("numero_clausula")
            assert not (t.startswith("[") and t.endswith("]")), c["numero_clausula"]

    def test_no_hay_dos_clausulas_con_la_misma_llave(self):
        """La llave (eps, número) es la que usa el sembrado para no duplicar."""
        llaves = [(c["eps"].upper(), c["numero_clausula"].upper()) for c in _clausulas()]
        assert len(llaves) == len(set(llaves)), "hay cláusulas repetidas"

    def test_todos_los_temas_son_validos(self):
        for c in _clausulas():
            assert c["tema"] in {"TA", "SO", "AU", "CO", "FA", "NN"}, c["numero_clausula"]
