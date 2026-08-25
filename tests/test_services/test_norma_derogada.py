"""El motor citaba como vigente una resolución derogada hace tres meses.

QUÉ PASÓ (24-08-2026). Revisando el corpus apareció que la **Resolución 2275 de
2023** —la de factura electrónica y RIPS, que el motor cita en seis sitios
distintos como fundamento— **fue derogada el 14 de mayo de 2026** por la
Resolución 948 de 2026. Verificado en el PDF oficial del Ministerio, cuyo
artículo de vigencia dice: «rige a partir de su expedición y deroga las
Resoluciones 2275 de 2023, 558 y 1884 de 2024».

Un dictamen radicado hoy que se apoye en ella le entrega a la EPS la forma de
desmontar el argumento: le basta con mostrar la derogatoria.

Y había algo peor de fondo: **el corpus tenía desde siempre un campo que dice si
la norma sigue vigente, y el revisor de citas nunca lo miraba**. Ocho normas
estaban marcadas como no vigentes y ninguna producía el menor aviso.

QUÉ SE HIZO. El revisor ahora avisa cuando el dictamen cita una norma que el
sistema sabe derogada, diciendo cuál la derogó y desde cuándo. El aviso es de
severidad MEDIA y no ALTA a propósito: si el servicio se prestó mientras la
norma regía, citarla es lo correcto. Quien sabe la fecha del servicio es el
gestor, así que se le avisa y él decide. Por lo mismo, este hallazgo NO borra
frases del dictamen.

Se cargó además la Resolución 948 de 2026 —que el sistema no tenía— y los seis
textos que citaban la derogada ahora nombran la vigente con la regla de la
fecha, para que el motor no se equivoque de norma según cuándo se prestó el
servicio.
"""

from app.services.citation_verifier import verificar_citas


def _hallazgos(texto: str) -> list[dict]:
    return verificar_citas(texto)["issues"]


class TestSeAvisaCuandoLaNormaYaNoRige:
    CITA = "LA FACTURA CUMPLE CON LA RESOLUCIÓN 2275 DE 2023 SOBRE FACTURACIÓN ELECTRÓNICA."

    def test_la_resolucion_2275_ya_no_pasa_en_silencio(self):
        tipos = [h["tipo"] for h in _hallazgos(self.CITA)]
        assert "NORMA_DEROGADA" in tipos

    def test_el_aviso_dice_quien_la_derogo_y_desde_cuando(self):
        h = [x for x in _hallazgos(self.CITA) if x["tipo"] == "NORMA_DEROGADA"][0]
        assert "948" in h["detalle"]
        assert "14 de mayo de 2026" in h["detalle"]

    def test_es_aviso_y_no_acusacion(self):
        """Si el servicio es anterior a la derogatoria, citarla es correcto."""
        h = [x for x in _hallazgos(self.CITA) if x["tipo"] == "NORMA_DEROGADA"][0]
        assert h["severidad"] == "MEDIA"
        assert "mientras regía" in h["detalle"]

    def test_no_se_confunde_con_una_norma_inexistente(self):
        tipos = [h["tipo"] for h in _hallazgos(self.CITA)]
        assert "NORMA_INEXISTENTE" not in tipos, "la norma existe: solo dejó de regir"

    def test_la_norma_vigente_pasa_limpia(self):
        assert _hallazgos("LA FACTURA CUMPLE CON LA RESOLUCIÓN 948 DE 2026 SOBRE RIPS.") == []

    def test_una_norma_vigente_cualquiera_no_se_marca(self):
        tipos = [h["tipo"] for h in _hallazgos("CONFORME A LA RESOLUCIÓN 2284 DE 2023.")]
        assert "NORMA_DEROGADA" not in tipos


class TestNoSeLeBorraLaFraseAlDictamen:
    def test_la_oracion_con_la_norma_derogada_se_conserva(self):
        """El gestor decide: es él quien sabe la fecha del servicio."""
        from app.services.dictamen_postprocesor import quitar_citas_invalidas_dinamico

        dictamen = (
            "ESE HUS NO ACEPTA LA GLOSA. " * 5
            + "LA FACTURA CUMPLE CON LA RESOLUCIÓN 2275 DE 2023. "
            + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        )
        assert "2275" in quitar_citas_invalidas_dinamico(dictamen)


class TestElCorpusSabeCualRigeHoy:
    def test_la_2275_quedo_marcada_como_no_vigente(self):
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        n = _TODAS_LAS_NORMAS["RESOLUCION 2275 DE 2023"]
        assert n["vigente"] is False
        assert "948" in n["derogada_por"]

    def test_la_948_de_2026_esta_cargada_y_verificada(self):
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        n = _TODAS_LAS_NORMAS["RESOLUCION 948 DE 2026"]
        assert n["vigente"] is True
        assert n.get("verificada")
        assert "RIPS" in n["titulo"]

    def test_la_nota_recuerda_mirar_la_fecha_del_servicio(self):
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        notas = _TODAS_LAS_NORMAS["RESOLUCION 948 DE 2026"]["notas"]
        assert "FECHA DEL SERVICIO" in notas.upper()
        assert "2275" in notas


class TestElMotorYaNoOfreceLaDerogadaASecas:
    RUTAS = [
        "app/services/glosa_ia_prompts.py",
        "app/services/conciliador_ia.py",
        "app/services/contexto_contractual_enriquecido.py",
        "app/services/glosa_service.py",
    ]

    def test_donde_se_nombra_la_derogada_va_al_lado_la_vigente(self):
        """Se mira el párrafo, no el renglón suelto.

        Los textos del prompt se escriben partidos en varias líneas, así que la
        mención de la norma vigente puede quedar en la línea de al lado. Lo que
        importa es que quien lea ese pedazo se entere de que la 2275 dejó de
        regir, no en qué renglón exacto lo diga.
        """
        import io

        for ruta in self.RUTAS:
            renglones = io.open(ruta, encoding="utf-8").read().split("\n")
            for i, renglon in enumerate(renglones):
                if "2275" not in renglon or renglon.strip().startswith("#"):
                    continue
                vecindad = " ".join(renglones[max(0, i - 3) : i + 4])
                assert "948" in vecindad or "14-05-2026" in vecindad, (
                    f"{ruta} nombra la Res. 2275/2023 sin decir que fue derogada: "
                    f"{renglon.strip()[:100]}"
                )


class TestLaResolucionDePplTambienDejoDeRegir:
    """PPL es uno de los pagadores reales del hospital, y el prompt ordenaba
    citar SIEMPRE una resolución derogada en junio de 2026.

    La Resolución 5159 de 2015 (modelo de atención en salud para la población
    privada de la libertad) fue derogada por el artículo 12 de la Resolución
    1099 de 2026: «rige a partir de la fecha de su expedición y deroga las
    Resoluciones 5159 de 2015 y 3595 de 2016». Verificado en el PDF oficial del
    Ministerio.

    El corpus la tenía como vigente en dos sitios y el prompt decía
    «OBLIGACIÓN: Citar SIEMPRE Res. 5159/2015 al defender cobertura PPL».
    """

    def test_la_5159_quedo_marcada_como_derogada(self):
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        n = _TODAS_LAS_NORMAS["RESOLUCION 5159 DE 2015"]
        assert n["vigente"] is False
        assert "1099" in n["derogada_por"]

    def test_tambien_en_el_catalogo_corto(self):
        """El otro catálogo del repositorio también quedó al día."""
        from app.services.normativa import NORMAS_VIGENTES

        assert NORMAS_VIGENTES["RESOLUCION 5159/2015"]["vigente"] is False
        assert "1099" in NORMAS_VIGENTES["RESOLUCION 5159/2015"]["resumen"]

    def test_citarla_no_se_trata_como_una_cita_equivocada(self):
        """Derogada no es lo mismo que equivocada.

        El catálogo corto tiene un diccionario aparte para citas EQUIVOCADAS
        («la Ley 1122 es de 2007, no de 2011»), y lo que cae ahí sale como
        hallazgo de nivel «error». La Res. 5159 no está equivocada: es la norma
        correcta para las atenciones anteriores a junio de 2026. De la fecha
        avisa el verificador de citas, con severidad media.
        """
        from app.services.normativa import validar_citas

        r = validar_citas("CONFORME A LA RESOLUCION 5159/2015 SE DEFIENDE LA COBERTURA.")
        assert not any("5159" in d["cita"] for d in r["derogadas"])

    def test_la_1099_de_2026_esta_cargada(self):
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        n = _TODAS_LAS_NORMAS["RESOLUCION 1099 DE 2026"]
        assert n["vigente"] is True
        assert n.get("verificada")
        assert "privada de la libertad" in n["titulo"].lower()

    def test_el_prompt_ya_no_ordena_citarla_siempre(self):
        import io

        prompts = io.open("app/services/glosa_ia_prompts.py", encoding="utf-8").read()
        assert "Citar SIEMPRE Res. 5159/2015" not in prompts
        assert "1099/2026" in prompts, "el prompt debe ofrecer la norma vigente"

    def test_citarla_avisa_pero_la_vigente_pasa_limpia(self):
        from app.services.citation_verifier import verificar_citas

        derogada = verificar_citas("CONFORME A LA RESOLUCIÓN 5159 DE 2015.")
        assert any(i["tipo"] == "NORMA_DEROGADA" for i in derogada["issues"])
        assert verificar_citas("CONFORME A LA RESOLUCIÓN 1099 DE 2026.")["issues"] == []
