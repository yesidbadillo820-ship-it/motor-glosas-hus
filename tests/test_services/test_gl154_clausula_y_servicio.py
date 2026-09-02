"""Lo que GL-154 dejó ver, aparte del contrato ajeno.

PRUEBA 3 DE ESTRÉS (01-09-2026) — glosa AU0201, factura HUS0000602233.

1. «Servicio objetado: DE URGENCIAS». La glosa no nombraba ningún
   procedimiento y no había CUPS, así que la extracción se quedó con un jirón
   de frase. Un renglón que empieza por preposición no es el nombre de un
   servicio: es lo que sobró de recortar.

2. «LA CLÁUSULA SEXTA DEL CONTRATO S-13-1-03-1-04958 DISPOSA QUE "LA
   FACTURACIÓN, PAGO, GLOSAS Y DEVOLUCIONES SE REALIZARÁN…"» — y el único PDF
   aportado era la historia clínica. Ese contrato no lo vio nadie.

Lo segundo es lo grave: es el mismo reproche que le hacemos a la entidad
cuando invoca una cláusula que no existe, cometido por nosotros. Ya había una
red para esto (Ronda 15, Bug Q) y no disparó, por dos huecos: exigía el ordinal
en NÚMEROS («cláusula 5») y verbos exactos («dice:»). Acá venía «CLÁUSULA
SEXTA» y «DISPOSA QUE».
"""

import io

import pytest

from app.services.glosa_service import (
    _clausulas_transcritas_sin_respaldo,
    _es_descripcion_rota,
    _linea_servicio_determinista,
)

SOLO_HISTORIA = "═══ DOCUMENTO: historia_clinica_urgencias.pdf ═══\nINGRESO POR URGENCIAS"
CON_CONTRATO = "═══ DOCUMENTO: contrato_famisanar.pdf ═══\nCLAUSULA SEXTA: LA FACTURACION..."

DICTAMEN_GL154 = (
    "EL SERVICIO SE PRESTO EN URGENCIAS, CONFORME AL PROTOCOLO DE ATENCION "
    "INMEDIATA. ADICIONALMENTE, LA CLAUSULA SEXTA DEL CONTRATO S-13-1-03-1-04958 "
    "DISPOSA QUE «LA FACTURACION, PAGO, GLOSAS Y DEVOLUCIONES SE REALIZARAN DE "
    "CONFORMIDAD CON LO ESTABLECIDO EN LAS LEYES VIGENTES». SE SOLICITA EL "
    "LEVANTAMIENTO DE LA GLOSA."
)


class TestElRenglonRoto:
    @pytest.mark.parametrize(
        "roto",
        ["DE URGENCIAS", "EL PROCEDIMIENTO", "LA ATENCION", "POR URGENCIAS", "QUE SE PRESTO"],
    )
    def test_un_jiron_de_frase_no_es_un_servicio(self, roto: str):
        assert _linea_servicio_determinista("", roto, "", "AU0201") == "NO ESPECIFICADO EN LA GLOSA"

    @pytest.mark.parametrize(
        "bueno", ["OSTEOSÍNTESIS DE FÉMUR", "HEMOGRAMA IV", "CONSULTA DE PRIMERA VEZ", "ATENCION"]
    )
    def test_una_descripcion_de_verdad_se_respeta(self, bueno: str):
        assert _linea_servicio_determinista("", bueno, "", "AU0201") == bueno

    def test_el_cups_del_catalogo_siempre_manda(self):
        """Con descripción oficial no se rotula nada como faltante."""
        r = _linea_servicio_determinista("902210", "DE URGENCIAS", "", "AU0201")
        assert "HEMOGRAMA" in r

    def test_sin_nada_sigue_devolviendo_vacio(self):
        assert _linea_servicio_determinista("", "", "", "AU0201") == ""

    def test_muy_corta_tambien_es_rota(self):
        assert _es_descripcion_rota("RX")
        assert not _es_descripcion_rota("HEMOGRAMA")


class TestLaClausulaQueNadieLeyo:
    def test_borra_la_transcripcion_de_gl154(self):
        limpio, borrados = _clausulas_transcritas_sin_respaldo(DICTAMEN_GL154, SOLO_HISTORIA)
        assert borrados, "no detectó la cláusula transcrita"
        assert "LA FACTURACION, PAGO, GLOSAS" not in limpio

    def test_no_deja_el_renglon_roto(self):
        """Borrar solo las comillas dejaría «la cláusula sexta dispone que.»"""
        limpio, _ = _clausulas_transcritas_sin_respaldo(DICTAMEN_GL154, SOLO_HISTORIA)
        assert "DISPOSA QUE" not in limpio
        assert "CLAUSULA SEXTA" not in limpio

    def test_conserva_lo_que_si_era_valido(self):
        limpio, _ = _clausulas_transcritas_sin_respaldo(DICTAMEN_GL154, SOLO_HISTORIA)
        assert "EL SERVICIO SE PRESTO EN URGENCIAS" in limpio
        assert "SE SOLICITA EL LEVANTAMIENTO" in limpio

    @pytest.mark.parametrize(
        "verbo", ["DISPOSA QUE", "DISPONE QUE", "ESTABLECE QUE", "SEÑALA QUE", "REZA", "INDICA QUE"]
    )
    def test_no_depende_del_verbo(self, verbo: str):
        d = f"LA CLAUSULA SEXTA DEL CONTRATO X {verbo} «TEXTO INVENTADO DE LA CLAUSULA AQUI»."
        _, borrados = _clausulas_transcritas_sin_respaldo(d, SOLO_HISTORIA)
        assert borrados, verbo

    @pytest.mark.parametrize("ordinal", ["SEXTA", "DECIMA SEGUNDA", "5", "12", "PRIMERA"])
    def test_no_depende_del_ordinal(self, ordinal: str):
        """El hueco de la red vieja: exigía el ordinal en números."""
        d = f"LA CLAUSULA {ordinal} DEL CONTRATO X DISPONE QUE «TEXTO INVENTADO DE LA CLAUSULA»."
        _, borrados = _clausulas_transcritas_sin_respaldo(d, SOLO_HISTORIA)
        assert borrados, ordinal

    def test_aguanta_comillas_rectas(self):
        d = 'LA CLAUSULA SEXTA DEL CONTRATO X DISPONE QUE "TEXTO INVENTADO DE LA CLAUSULA".'
        _, borrados = _clausulas_transcritas_sin_respaldo(d, SOLO_HISTORIA)
        assert borrados


class TestLoQueNoSePuedeTocar:
    def test_las_normas_se_transcriben_y_estan_bien(self):
        """El Art. 17 de la Ley 1751 está en el corpus y se verifica."""
        ley = (
            "EL ARTICULO 17 DE LA LEY 1751 DE 2015 DISPONE QUE «SE GARANTIZA LA "
            "AUTONOMIA DE LOS PROFESIONALES DE LA SALUD PARA ADOPTAR DECISIONES»."
        )
        limpio, borrados = _clausulas_transcritas_sin_respaldo(ley, SOLO_HISTORIA)
        assert limpio == ley
        assert borrados == []

    def test_con_el_contrato_adjunto_no_se_borra_nada(self):
        """Si la IA sí pudo leerlo, la transcripción puede ser legítima."""
        limpio, borrados = _clausulas_transcritas_sin_respaldo(DICTAMEN_GL154, CON_CONTRATO)
        assert limpio == DICTAMEN_GL154
        assert borrados == []

    def test_dictamen_vacio_no_rompe(self):
        assert _clausulas_transcritas_sin_respaldo("", SOLO_HISTORIA) == ("", [])

    def test_sin_comillas_no_hay_transcripcion(self):
        d = "LA CLAUSULA SEXTA DEL CONTRATO X REGULA EL TRAMITE DE GLOSAS."
        limpio, borrados = _clausulas_transcritas_sin_respaldo(d, SOLO_HISTORIA)
        assert limpio == d and borrados == []


class TestElPromptTambienLoProhibe:
    def _base(self) -> str:
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        return SYSTEM_BASE

    def test_la_prohibicion_esta_escrita(self):
        assert "PROHIBICIÓN ABSOLUTA — CLÁUSULAS" in self._base()

    def test_le_da_la_salida_correcta(self):
        b = self._base()
        assert "regula el trámite de glosas» SÍ" in b

    def test_aclara_que_las_normas_si_se_pueden_citar(self):
        assert "Las NORMAS sí se pueden transcribir" in self._base()

    def test_el_gestor_se_entera_cuando_pasa(self):
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert "Inventar la redacción de una cláusula" in motor


class TestSegundaCorridaDeLaPrueba3:
    """Lo que la corrida GL-1 dejó ver: dos redes que no llegaban a actuar.

    01-09-2026, ya con la #578 desplegada.

    1. El panel de correcciones decía «Agregué de entrada la refutación» y la
       ARGUMENTACIÓN no la traía. El dictamen decía una cosa y el panel otra.
       Causa: la inyección iba justo después de leer el <argumento>, y más
       abajo el pase de refinamiento hace `arg_ia = _arg_refinado` —vuelve a
       pedirle el argumento a la IA y reemplaza el string entero—, así que se
       llevaba el párrafo por delante.

    2. La IA volvió a transcribir la cláusula sexta, ahora con «DISPONE:», y la
       red la dejó pasar. Dos causas: perseguía verbos, y su guarda buscaba la
       palabra «contrato» en el TEXTO COMPLETO de los PDF — una historia clínica
       la menciona sin ser un contrato, y con eso la red se desactivaba siempre.
    """

    HC_SOLA = (
        "═══ DOCUMENTO: historia_clinica_urgencias.pdf ═══\n"
        "INGRESO POR URGENCIAS 04/04/2026. contrato de prestacion de servicios."
    )

    def test_la_historia_clinica_ya_no_desactiva_la_red(self):
        """Menciona «contrato» en su texto y NO es un contrato aportado."""
        d = "LA CLAUSULA SEXTA DEL CONTRATO X DISPONE: «TEXTO INVENTADO DE LA CLAUSULA AQUI»."
        _, borrados = _clausulas_transcritas_sin_respaldo(d, self.HC_SOLA)
        assert borrados, "la palabra «contrato» dentro del PDF volvió a apagar la red"

    def test_el_nombre_del_archivo_si_la_desactiva(self):
        d = "LA CLAUSULA SEXTA DEL CONTRATO X DISPONE: «TEXTO INVENTADO DE LA CLAUSULA AQUI»."
        ctx = "═══ DOCUMENTO: contrato_famisanar.pdf ═══\ncualquier cosa"
        assert _clausulas_transcritas_sin_respaldo(d, ctx)[1] == []

    @pytest.mark.parametrize(
        "conector",
        ["DISPONE:", "DISPONE QUE", "ESTABLECE:", "REZA ASI:", "EN LOS SIGUIENTES TERMINOS:", ":"],
    )
    def test_ya_no_depende_de_ningun_verbo(self, conector: str):
        """Perseguir verbos es perseguir sinónimos: siempre hay uno más."""
        d = f"LA CLAUSULA SEXTA DEL CONTRATO X {conector} «TEXTO INVENTADO DE LA CLAUSULA AQUI»."
        _, borrados = _clausulas_transcritas_sin_respaldo(d, self.HC_SOLA)
        assert borrados, conector

    def test_la_refutacion_se_inyecta_despues_del_refinamiento(self):
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        i_iny = motor.index("[CONTRATO-AJENO] refutación inyectada al inicio")
        i_ref = motor.index("arg_ia = _arg_refinado")
        assert i_ref < i_iny, (
            "la inyección volvió a quedar ANTES del refinamiento: el pase de "
            "refinamiento reemplaza arg_ia entero y se la lleva por delante"
        )

    def test_no_se_duplica_si_ya_estaba(self):
        motor = io.open("app/services/glosa_service.py", encoding="utf-8").read()
        assert '"RELATIVIDAD DE LOS CONTRATOS" not in arg_ia.upper()' in motor
