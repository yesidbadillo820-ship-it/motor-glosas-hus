"""El Art. 3 de la Resolución 1995 ya no lleva pegada una frase del Art. 1.

QUÉ PASÓ (24-08-2026). La segunda auditoría independiente anotó que la cita de
«características de la historia clínica» que aparece en varios dictámenes es
sustancialmente correcta, pero mezcla una frase que en realidad viene del
Art. 1. Se revisó y así era: el corpus guardaba, como texto del Art. 3:

    «La historia clínica debe cumplir con las siguientes características:
     INTEGRALIDAD, SECUENCIALIDAD, RACIONALIDAD CIENTÍFICA, DISPONIBILIDAD y
     OPORTUNIDAD. La historia clínica es un documento privado, obligatorio y
     sometido a reserva.»

La segunda frase no es del Art. 3. Es del literal a) del Art. 1, verificado
contra el PDF oficial del Ministerio de Salud. Como los dictámenes copian ese
texto entre comillas y se lo atribuyen al Art. 3, media cita quedaba mal
atribuida en un documento que se radica ante la EPS.

Los dos artículos quedaron separados, cada uno con su texto oficial. La defensa
no cambia: las dos cosas se siguen pudiendo decir, cada una con su artículo.
"""

from app.services.normativa_completa import _TODAS_LAS_NORMAS

ARTICULOS = _TODAS_LAS_NORMAS["RESOLUCION 1995 DE 1999"]["articulos"]


class TestCadaFraseConSuArticulo:
    def test_estan_los_dos_articulos(self):
        assert "1" in ARTICULOS, "falta el Art. 1 (definiciones)"
        assert "3" in ARTICULOS, "falta el Art. 3 (características)"

    def test_la_reserva_es_del_articulo_1(self):
        texto = ARTICULOS["1"]["texto"].lower()
        assert "documento privado, obligatorio y sometido a reserva" in texto
        assert "cronológicamente" in texto

    def test_el_articulo_3_ya_no_se_queda_con_esa_frase(self):
        texto = ARTICULOS["3"]["texto"].lower()
        assert "sometido a reserva" not in texto, (
            "al Art. 3 le volvieron a pegar la frase que es del Art. 1"
        )

    def test_el_articulo_3_trae_las_cinco_caracteristicas(self):
        texto = ARTICULOS["3"]["texto"].lower()
        for caracteristica in (
            "integralidad",
            "secuencialidad",
            "racionalidad científica",
            "disponibilidad",
            "oportunidad",
        ):
            assert caracteristica in texto, f"falta la característica «{caracteristica}»"


class TestElRevisorDeCitasLasReconoce:
    """Lo que importa de verdad: que una cita correcta siga pasando limpia."""

    def test_citar_las_caracteristicas_como_articulo_3_pasa(self):
        from app.services.citation_verifier import verificar_citas

        dictamen = (
            "CONFORME AL ARTÍCULO 3 DE LA RESOLUCIÓN 1995 DE 1999, QUE ESTABLECE QUE "
            "«LAS CARACTERÍSTICAS BÁSICAS SON: INTEGRALIDAD: LA HISTORIA CLÍNICA DE UN "
            "USUARIO DEBE REUNIR LA INFORMACIÓN DE LOS ASPECTOS CIENTÍFICOS, TÉCNICOS Y "
            "ADMINISTRATIVOS RELATIVOS A LA ATENCIÓN EN SALUD», EL EXPEDIENTE ESTÁ COMPLETO."
        )
        falsas = [
            i for i in verificar_citas(dictamen)["issues"] if i["tipo"] == "CITA_LITERAL_FALSA"
        ]
        assert falsas == [], f"una cita correcta quedó marcada como falsa: {falsas}"

    def test_citar_la_reserva_como_articulo_1_pasa(self):
        from app.services.citation_verifier import verificar_citas

        dictamen = (
            "EL ARTÍCULO 1 DE LA RESOLUCIÓN 1995 DE 1999 DEFINE QUE «LA HISTORIA CLÍNICA "
            "ES UN DOCUMENTO PRIVADO, OBLIGATORIO Y SOMETIDO A RESERVA, EN EL CUAL SE "
            "REGISTRAN CRONOLÓGICAMENTE LAS CONDICIONES DE SALUD DEL PACIENTE»."
        )
        falsas = [
            i for i in verificar_citas(dictamen)["issues"] if i["tipo"] == "CITA_LITERAL_FALSA"
        ]
        assert falsas == [], f"una cita correcta quedó marcada como falsa: {falsas}"
