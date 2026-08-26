"""La malla de atribuciones comparaba contra nuestro propio comentario.

TERCERA auditoría independiente del 25-08-2026, sobre 10 dictámenes nuevos.
El auditor señaló que GL-127 dice:

    «LA LEY 1438/2011 ART. 57 IMPONE QUE LA CARGA DE LA PRUEBA RECAE EN LA EPS»

Verificado contra DOS fuentes oficiales (normograma de la SuperSalud y Senado
de la Republica): el articulo 57 trata de PLAZOS del tramite de glosas y no
menciona la carga de la prueba por ningun lado.

Lo grave no fue la cita: fue que el motor YA TENIA la defensa para esto
—la malla de ATRIBUCION_FALSA, con «la carga de la prueba» en su tabla— y aun
asi la dejo pasar. Fallo por TRES agujeros encadenados, y cada uno es una
leccion distinta:

1. El verbo «IMPONE» no estaba en la lista de verbos de atribucion, asi que
   el patron ni siquiera enganchaba la frase.

2. Ninguno de los patrones aceptaba la abreviatura «ART.» — exigian la
   palabra «ARTICULO» completa. Es la abreviatura mas comun en los dictamenes.

3. Y el peor: la funcion que trae «el texto real del articulo» devolvia
   tambien los campos «aplicacion» y «keywords», que son comentario NUESTRO,
   no la ley. Al articulo 57 se le habia puesto una nota que dice «NO le
   atribuya la carga de la prueba: el articulo no la menciona» — y esa nota
   hacia que la malla encontrara la frase en lo que creia ser el texto legal
   y diera por buena justo la atribucion que la nota prohibia.

   **La advertencia se desactivaba a si misma.** Es la misma autocertificacion
   que este motor lleva todo el dia corrigiendo, en su version mas incomoda.
"""

import app.services.citation_verifier as cv
from app.services.citation_verifier import verificar_citas
from app.services.normativa_completa import _TODAS_LAS_NORMAS as NORMAS

FRASE_GL127 = (
    "ESE HUS NO ACEPTA LA GLOSA. LA EPS NO HA PRESENTADO COMPROBANTE BDUA. "
    "LA LEY 1438/2011 ART. 57 IMPONE QUE LA CARGA DE LA PRUEBA RECAE EN LA EPS, "
    "QUIEN NO HA APORTADO DOCUMENTO BDUA QUE SUSTENTE SU RECLAMO."
)


class TestLaMallaSoloMiraLaLey:
    """El agujero de fondo: comparar contra comentario propio no es verificar."""

    def test_el_texto_real_no_arrastra_nuestro_comentario(self):
        cuerpo = cv._texto_real_del_articulo("LEY", "1438", "2011", "57", NORMAS)
        assert cuerpo, "el art. 57 debe tener cuerpo suficiente para comparar"
        art = NORMAS["LEY 1438 DE 2011"]["articulos"]["57"]
        assert art["texto"] in cuerpo, "debe traer el texto de la ley"
        assert art["aplicacion"] not in cuerpo, (
            "«aplicacion» es comentario nuestro, no la ley: no puede entrar en la comparación"
        )

    def test_la_nota_de_advertencia_no_se_desactiva_a_si_misma(self):
        """La nota del art. 57 dice literalmente «NO le atribuya la carga de la
        prueba». Si esa nota entrara en la comparación, la malla encontraría la
        frase y daría por buena la atribución que la nota prohíbe."""
        art = NORMAS["LEY 1438 DE 2011"]["articulos"]["57"]
        assert "carga de la prueba" in art["aplicacion"].lower(), (
            "la nota debe seguir advirtiéndolo — es lo que hace válida esta prueba"
        )
        cuerpo = cv._texto_real_del_articulo("LEY", "1438", "2011", "57", NORMAS)
        assert "carga de la prueba" not in cuerpo.lower()


class TestLosTresAgujerosDelPatron:
    def test_reconoce_el_verbo_impone(self):
        assert "IMPONE" in cv._VERBOS_DE_ATRIBUCION

    def test_reconoce_los_verbos_que_salieron_en_los_dictamenes(self):
        for v in ("FIJA", "OTORGA", "EXIGE", "OBLIGA", "GARANTIZA"):
            assert v in cv._VERBOS_DE_ATRIBUCION, v

    def test_acepta_la_abreviatura_art(self):
        """«ART. 57» es como lo escriben los dictámenes; los tres patrones
        exigían la palabra «ARTÍCULO» completa."""
        assert cv.PAT_ATRIBUCION_NORMA_ART_PEGADO.search(FRASE_GL127)

    def test_acepta_la_forma_norma_articulo_pegados(self):
        """«La Ley 1438/2011 Art. 57 impone que...» — sin el «en su»."""
        m = cv.PAT_ATRIBUCION_NORMA_ART_PEGADO.search(FRASE_GL127)
        assert m and m.groups()[:4] == ("LEY", "1438", "2011", "57")

    def test_las_otras_dos_formas_siguen_funcionando(self):
        for frase in (
            "EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 ESTABLECE QUE LA CARGA DE LA PRUEBA RECAE EN LA EPS",
            "LA LEY 1438 DE 2011, EN SU ARTÍCULO 57, DISPONE QUE LA CARGA DE LA PRUEBA RECAE EN LA EPS",
        ):
            enganchó = cv.PAT_ATRIBUCION_ART_PRIMERO.search(frase) or (
                cv.PAT_ATRIBUCION_NORMA_PRIMERO.search(frase)
            )
            assert enganchó, frase


class TestElCasoCompleto:
    def test_el_dictamen_gl127_ahora_se_marca(self):
        iss = verificar_citas(FRASE_GL127).get("issues", [])
        atrib = [i for i in iss if i["tipo"] == "ATRIBUCION_FALSA"]
        assert atrib, "la atribución falsa del Art. 57 debe salir marcada"
        assert atrib[0]["severidad"] == "ALTA"
        assert "carga de la prueba" in atrib[0]["detalle"].lower()

    def test_una_atribucion_correcta_no_se_marca(self):
        """El Art. 57 SÍ trata de plazos: atribuirle eso está bien y la malla
        no puede molestar."""
        bien = (
            "EL ARTÍCULO 57 DE LA LEY 1438 DE 2011 ESTABLECE QUE EL PRESTADOR DEBE DAR "
            "RESPUESTA DENTRO DE LOS QUINCE (15) DÍAS HÁBILES SIGUIENTES A SU RECEPCIÓN."
        )
        iss = verificar_citas(bien).get("issues", [])
        assert not [i for i in iss if i["tipo"] == "ATRIBUCION_FALSA"]


class TestElArticulo57QuedoConSuTextoReal:
    ART = NORMAS["LEY 1438 DE 2011"]["articulos"]["57"]

    def test_trae_los_plazos_dentro_del_texto_y_no_en_una_lista_aparte(self):
        """De ahí salió el GL-131, que escribió «el artículo 57 fija DIEZ (10)
        días hábiles para responder» — son QUINCE. Decirle a la entidad que
        nuestro plazo es más corto le regala la extemporaneidad contra el
        propio hospital."""
        for n in ("veinte (20)", "quince (15)", "diez (10)"):
            assert n in self.ART["texto"], n

    def test_ya_no_le_atribuye_frases_que_no_estan_en_la_ley(self):
        texto = self.ART["texto"].lower()
        assert "carga de la prueba" not in texto
        assert "arbitraje" not in texto
        assert "se entenderá aceptada la glosa" not in texto

    def test_manda_a_la_fuente_real_de_la_aceptacion_tacita(self):
        """La consecuencia es real, pero viene del código RE2202 del Manual
        Único (Res. 2284 de 2023), no del artículo."""
        assert "RE2202" in self.ART["aplicacion"]

    def test_conserva_la_defensa_de_los_hechos_nuevos(self):
        assert "hechos nuevos" in self.ART["texto"]
