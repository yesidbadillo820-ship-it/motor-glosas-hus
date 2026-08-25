"""El dictamen no puede radicar un CUPS que no existe — 19-08-2026.

Yesid analizó la factura HUS468334 y el dictamen dijo:

    Servicio objetado: RADIOGRAFÍA DE RODILLA CUPS 348240

Ese código **no existe** en el catálogo oficial. La IA lo inventó. Y el
documento salió sellado con «✓ CITAS VERIFICADAS · 11 citas contra corpus · 0
hallazgos», porque el verificador revisaba resoluciones, decretos, leyes,
acuerdos, circulares y sentencias — pero ningún CUPS.

Un CUPS es de lo primero que la EPS cruza contra su sistema. Uno inventado en
un documento radicado tumba la defensa entera, aunque el argumento jurídico
esté impecable.
"""

from __future__ import annotations

import pytest

from app.services.citation_verifier import verificar_citas


def _issues(html: str, tipo: str = "CUPS_INEXISTENTE") -> list[dict]:
    return [i for i in verificar_citas(html)["issues"] if i["tipo"] == tipo]


class TestElCasoReal:
    def test_atrapa_el_cups_348240(self):
        html = "<p>Servicio objetado: RADIOGRAFÍA DE RODILLA CUPS 348240</p>"
        issues = _issues(html)
        assert len(issues) == 1, "el CUPS inventado volvió a pasar sin marcar"
        assert issues[0]["cita"] == "CUPS 348240"

    def test_lo_marca_como_grave(self):
        """No es un detalle de estilo: va en un documento que se radica."""
        html = "<p>CUPS 348240</p>"
        assert _issues(html)[0]["severidad"] == "ALTA"
        assert verificar_citas(html)["tiene_problemas_graves"] is True

    def test_le_dice_al_auditor_que_hacer(self):
        detalle = _issues("<p>CUPS 348240</p>")[0]
        assert "no existe en el catálogo" in detalle["detalle"]
        assert "Consulta Normativa" in detalle["sugerencia"]


class TestNoMolestaConLosCupsBuenos:
    @pytest.mark.parametrize(
        "cups,servicio",
        [
            ("871121", "radiografía de tórax"),
            ("890201", "consulta de primera vez por medicina general"),
        ],
    )
    def test_un_cups_real_no_se_marca(self, cups, servicio):
        assert _issues(f"<p>Servicio: {servicio.upper()} CUPS {cups}</p>") == []

    def test_varios_cups_reales_en_el_mismo_dictamen(self):
        html = "<p>Se facturó CUPS 871121 y CUPS 890201 en la misma atención.</p>"
        assert _issues(html) == []


class TestFormasDeEscribirlo:
    @pytest.mark.parametrize(
        "texto",
        [
            "CUPS 348240",
            "CUPS: 348240",
            "cups 348240",
            "código CUPS 348240",
        ],
    )
    def test_lo_reconoce_escrito_de_varias_maneras(self, texto):
        assert _issues(f"<p>{texto}</p>"), f"no se detectó en «{texto}»"

    def test_no_repite_el_mismo_codigo_dos_veces(self):
        html = "<p>CUPS 348240 ... más adelante CUPS 348240 otra vez</p>"
        assert len(_issues(html)) == 1

    def test_no_confunde_un_valor_en_pesos_con_un_cups(self):
        """«$348.240» no es un código: sin la palabra CUPS no se mira."""
        assert _issues("<p>Se glosa por valor de $348.240 pesos</p>") == []


class TestNoRompeNada:
    def test_dictamen_sin_cups(self):
        assert _issues("<p>Se solicita el levantamiento de la glosa.</p>") == []

    def test_dictamen_vacio(self):
        assert verificar_citas("")["issues"] == []

    def test_las_otras_revisiones_siguen_funcionando(self):
        """Agregar CUPS no puede apagar la revisión de citas vacías."""
        html = "<p>EN VIRTUD DEL ART. 168 DE LA LEY 100 DE 1993, QUE DISPONE «.»</p>"
        vacias = [i for i in verificar_citas(html)["issues"] if i["tipo"] == "CITA_VACIA"]
        assert vacias, "se perdió la detección de citas vacías"
