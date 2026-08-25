"""Un contrato vencido no «permanece vigente».

QUÉ PASÓ (25-08-2026). Los dictámenes GL-118 y GL-119 salieron diciendo:

    «...RECHAZAMOS LA AFIRMACIÓN DE AUSENCIA DE CONTRATO, POR EL CONTRATO
     440-DIGSA/DMBUG-2025 PERMANECE VIGENTE HASTA 30 DE JULIO DE 2026.»

Ese día ya había pasado hacía casi un mes. Y en el MISMO documento, tres
renglones más abajo, el encabezado decía:

    Contrato: CONTRATO CON VIGENCIA TERMINADA 440-DIGSA/DMBUG-2025

O sea que el papel que se radica ante la entidad se contradecía solo. Si la
EPS lo revisa, tumba la respuesta entera y de paso queda mal el hospital.

LA CAUSA, y era nuestra. El renglón que el sistema le pasa a la IA se llamaba
«Contrato vigente» SIEMPRE — y cuando la vigencia había terminado, adentro le
metía el texto «CONTRATO CON VIGENCIA TERMINADA». Le estábamos entregando a la
IA un campo llamado «vigente» con un contenido que dice «terminada», y ella
resolvía la contradicción como podía.

QUÉ SE HIZO, en dos capas:

  · **El prompt deja de contradecirse.** Cuando la vigencia terminó, el renglón
    se llama «Contrato (VENCIDO)» y lleva la prohibición escrita: no afirmar
    que está vigente, y si el servicio pudo caer dentro de la vigencia, decirlo
    condicionado a la fecha —o pedirla— en vez de afirmar cobertura.
  · **Una red determinista debajo.** Si aun así el dictamen lo afirma, la
    afirmación se cambia por una que no miente. NO se borra la mención del
    contrato: nombrarlo es correcto y muchas veces necesario. Lo que se quita
    es el «sigue vigente».
"""

import pytest

from app.services.glosa_service import _no_afirmar_contrato_vencido


@pytest.fixture
def vencido(monkeypatch):
    """Una EPS cuyo contrato figura con la vigencia terminada."""
    import app.services.glosa_ia_prompts as prompts

    monkeypatch.setattr(
        prompts,
        "get_contrato",
        lambda eps, *a, **k: {
            "numero": "CONTRATO CON VIGENCIA TERMINADA: 440-DIGSA/DMBUG-2025",
            "_vigencia_vencida": True,
        },
    )


@pytest.fixture
def vigente(monkeypatch):
    import app.services.glosa_ia_prompts as prompts

    monkeypatch.setattr(prompts, "get_contrato", lambda eps, *a, **k: {"numero": "CSS009-2024"})


class TestYaNoAfirmaQueSigueVigente:
    FRASE_GL118 = (
        "RECHAZAMOS LA AFIRMACIÓN DE AUSENCIA DE CONTRATO, POR EL CONTRATO "
        "440-DIGSA/DMBUG-2025 PERMANECE VIGENTE HASTA 30 DE JULIO DE 2026."
    )

    def test_la_frase_exacta_del_expediente(self, vencido):
        r = _no_afirmar_contrato_vencido(self.FRASE_GL118, eps="DISPENSARIO MEDICO")
        assert "PERMANECE VIGENTE" not in r.upper()
        assert "RIGIÓ LA RELACIÓN ENTRE LAS PARTES" in r

    @pytest.mark.parametrize(
        "frase",
        [
            "EL CONTRATO VIGENTE ESTABLECE LA TARIFA.",
            "EL CONTRATO SE ENCUENTRA VIGENTE Y OBLIGA A LAS PARTES.",
            "EL ACUERDO SE ENCUENTRA EN EJECUCIÓN A LA FECHA.",
            "CONFORME AL CONTRATO VIGENTE HASTA EL 30 DE JULIO DE 2026.",
        ],
    )
    def test_las_otras_formas_de_decirlo(self, vencido, frase):
        r = _no_afirmar_contrato_vencido(frase, eps="DISPENSARIO MEDICO")
        assert r != frase, f"se escapó: {frase}"
        assert "VIGENTE" not in r.upper() or "RIGIÓ" in r.upper()

    def test_el_numero_del_contrato_no_se_borra(self, vencido):
        """Nombrar el contrato es correcto; lo que sobra es el «sigue vigente»."""
        r = _no_afirmar_contrato_vencido(self.FRASE_GL118, eps="DISPENSARIO MEDICO")
        assert "440-DIGSA/DMBUG-2025" in r


class TestNoSeTocaLoQueEstaBien:
    def test_con_contrato_al_dia_no_cambia_nada(self, vigente):
        frase = "EL CONTRATO CSS009-2024 PERMANECE VIGENTE Y RIGE LA TARIFA."
        assert _no_afirmar_contrato_vencido(frase, eps="COMPENSAR") == frase

    def test_sin_eps_no_hace_nada(self):
        frase = "EL CONTRATO PERMANECE VIGENTE."
        assert _no_afirmar_contrato_vencido(frase, eps="") == frase

    def test_dictamen_vacio_no_rompe(self, vencido):
        assert _no_afirmar_contrato_vencido("", eps="DISPENSARIO MEDICO") == ""


class TestElPromptYaNoSeContradice:
    def test_el_renglon_cambia_de_nombre_cuando_vencio(self):
        import io

        prompts = io.open("app/services/glosa_ia_prompts.py", encoding="utf-8").read()
        assert '_etiqueta_contrato = "Contrato (VENCIDO)"' in prompts
        assert "• Contrato vigente  : {numero_contrato}" not in prompts, (
            "el renglón volvió a llamarse «vigente» pase lo que pase"
        )

    def test_lleva_la_prohibicion_escrita(self):
        import io

        prompts = io.open("app/services/glosa_ia_prompts.py", encoding="utf-8").read()
        assert "PROHIBIDO afirmar que este contrato está vigente" in prompts

    def test_le_dice_que_hacer_en_vez_de_solo_prohibir(self):
        """Una prohibición sin salida deja a la IA sin qué escribir."""
        import io

        prompts = io.open("app/services/glosa_ia_prompts.py", encoding="utf-8").read()
        assert "condicionado a la fecha" in prompts
        assert "pídela en vez de afirmar cobertura" in prompts
