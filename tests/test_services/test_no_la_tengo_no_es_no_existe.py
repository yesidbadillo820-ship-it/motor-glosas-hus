"""«No la tengo cargada» no es «no existe».

27-08-2026, dictamen GL-135. La IA citó la **Resolución 839 de 2017** y el
revisor de citas la marcó `NORMA_INEXISTENTE` en severidad **ALTA**, con el
texto «No existe en el corpus normativo cargado».

Se descargó del normograma oficial de la Supersalud: **existe**. Es conjunta de
MinSalud y MinCultura, y modifica justamente la Resolución 1995 de 1999 — la
misma que el dictamen usa para la historia clínica. O sea que la IA citó bien y
el sello le dijo al auditor que era inventada.

ES EL ERROR CONTRARIO al que este revisor existe para evitar, y el que más
rápido le quita la credibilidad al sello: si marca en rojo una norma buena, el
gestor deja de creerle también cuando marca una mala.

El corpus trae las normas de uso diario, no las miles que hay. Que una no esté
cargada no dice **nada** sobre si existe.

Dos cosas se hicieron: cargar la 839 con su texto oficial, y cambiar lo que el
revisor dice cuando no conoce una norma.
"""

from __future__ import annotations

from app.services.citation_verifier import _estado_del_corpus, verificar_citas
from app.services.normativa_completa import _TODAS_LAS_NORMAS


class TestLa839EstaCargadaYVerificada:
    def test_esta_en_el_corpus(self):
        assert "RESOLUCION 839 DE 2017" in _TODAS_LAS_NORMAS

    def test_dice_contra_que_fuente_se_verifico(self):
        norma = _TODAS_LAS_NORMAS["RESOLUCION 839 DE 2017"]
        assert norma.get("verificada"), "sin fuente anotada no cuenta como verificada"
        assert "normograma" in norma["verificada"].lower()

    def test_trae_el_articulo_de_los_quince_anios(self):
        arts = _TODAS_LAS_NORMAS["RESOLUCION 839 DE 2017"]["articulos"]
        assert "quince (15) años" in arts["3"]["texto"]
        assert "archivo de gestión" in arts["3"]["texto"]

    def test_el_corpus_sigue_completo(self):
        estado = _estado_del_corpus()
        assert estado["normas_sin_verificar"] == 0, (
            "una norma cargada sin anotar su fuente deja el sello en «sin contrastar»"
        )
        assert estado["normas_verificadas"] >= 28

    def test_ya_no_la_marca_como_problema(self):
        d = "SE APORTA LA HISTORIA CLÍNICA CONFORME A LA RESOLUCIÓN 839 DE 2017."
        tipos = {i["tipo"] for i in (verificar_citas(d) or {}).get("issues", [])}
        assert "NORMA_INEXISTENTE" not in tipos
        assert "NORMA_SIN_VERIFICAR" not in tipos


class TestLaFechaFuturaSiSePuedeAfirmar:
    """No todo es «no la tengo». Una norma fechada en un año que todavía no
    llega no puede existir, y eso sí se afirma."""

    def _issue(self, dictamen: str):
        for i in (verificar_citas(dictamen) or {}).get("issues", []):
            if i["tipo"] == "NORMA_INEXISTENTE":
                return i
        return None

    def test_una_norma_del_futuro_sigue_en_alta(self):
        i = self._issue("EN VIRTUD DE LA RESOLUCION 9999 DE 2030 DEL MINISTERIO.")
        assert i is not None, "una norma del futuro sí se puede dar por inventada"
        assert i["severidad"] == "ALTA"
        assert "no puede existir" in i["detalle"]

    def test_el_anio_sale_del_reloj_no_escrito_a_mano(self):
        import inspect
        from app.services import citation_verifier

        fuente = inspect.getsource(citation_verifier._falta_del_corpus)
        assert "ahora_utc().year" in fuente, (
            "con el año escrito a mano, en enero empezaría a dar por buenas las "
            "normas del año pasado y por falsas las del nuevo"
        )


class TestElControlDeCalidadNoLaAprueba:
    """El mensaje bajó a MEDIA, pero la puerta no se abre: el prompt le dice al
    modelo qué normas usar, y todas están en el corpus. Citar una de fuera es
    salirse del guion, y eso merece ojos humanos antes de radicar."""

    def test_una_norma_sin_comprobar_no_pasa_el_control(self):
        from app.services.quality_gate.post_validator import check_citas_verificadas

        r, _ = check_citas_verificadas(
            "ESE HUS NO ACEPTA. DE ACUERDO CON LA RESOLUCIÓN 1552 DE 2019, "
            "LAS TARIFAS SE RESPETAN. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA.",
            eps="FAMISANAR",
        )
        assert not r.ok, "un dictamen con derecho que nadie pudo comprobar no se aprueba solo"
        assert r.severidad == "ERROR"


class TestLoQueDiceCuandoNoConoceUnaNorma:
    def _issue(self, dictamen: str):
        for i in (verificar_citas(dictamen) or {}).get("issues", []):
            if i["tipo"] == "NORMA_SIN_VERIFICAR":
                return i
        return None

    def test_no_afirma_que_no_existe(self):
        i = self._issue("SE CITA LA RESOLUCIÓN 7777 DE 2019 PARA EL CASO.")
        assert i is not None, "sigue avisando: no se calla"
        assert "no existe" not in i["detalle"].lower()
        assert "NO quiere decir que no exista" in i["detalle"]

    def test_baja_de_alta_a_media(self):
        i = self._issue("SE CITA LA RESOLUCIÓN 7777 DE 2019 PARA EL CASO.")
        assert i["severidad"] == "MEDIA", (
            "no se puede tratar igual «no la tengo» que una cita comprobadamente falsa"
        )

    def test_le_dice_al_gestor_donde_confirmarla(self):
        i = self._issue("SE CITA LA RESOLUCIÓN 7777 DE 2019 PARA EL CASO.")
        assert "normograma" in i["sugerencia"].lower()
        assert "cargarla" in i["sugerencia"]
