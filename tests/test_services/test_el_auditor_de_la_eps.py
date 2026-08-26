"""Leer el dictamen como lo leeria el auditor de la EPS, antes de radicar.

26-08-2026, de las propuestas al motor.

Los defectos graves de agosto los encontraron TRES auditorias independientes
—y las tres DESPUES de que los dictamenes salieran—. Cada ronda costo un dia
de correcciones sobre documentos ya entregados.

El motor ya tenia doce revisiones, pero todas de CUMPLIMIENTO: que la apertura
sea la correcta, que la extension alcance, que no queden placeholders. Ninguna
preguntaba lo unico que importa del otro lado de la mesa: «¿por donde tumbaria
yo esta respuesta?».

DONDE SE ENCHUFA, y es lo importante: cuando el revisor de citas NO encontro
nada. Ese es justo el caso que quemo esta semana — los dictamenes con los
defectos mas graves salieron con el sello «citas verificadas · 0 hallazgos».
Cuando el revisor SI marca algo, el gestor ya tiene que mirar y el
recordatorio sobraria.
"""

from app.services.multi_agente import agente_auditor_eps


class TestLosFlancosPorLosQueDeVerdadSeCayeron:
    """Cada flanco sale de un dictamen real de agosto, no de una lista teórica."""

    def test_la_cita_que_no_dice_lo_que_se_le_atribuye(self):
        """GL-127: le atribuyó al Art. 57 una carga de la prueba que no tiene."""
        r = agente_auditor_eps("CONFORME AL ARTÍCULO 57 DE LA LEY 1438…", "FA1606", "NUEVA EPS")
        assert any("no dice" in f["flanco"] for f in r["flancos"])

    def test_afirmar_lo_que_no_se_probo(self):
        """Nueve de diez dictámenes afirmaban cosas de la historia clínica."""
        r = agente_auditor_eps(
            "LA HISTORIA CLÍNICA REGISTRA LA AUTORIZACIÓN.", "AU0202", "SALUD TOTAL"
        )
        assert any("no se probó" in f["flanco"] for f in r["flancos"])

    def test_el_documento_que_se_contradice_solo(self):
        """GL-131: «sin contrato pactado» y a la vez invocaba una cláusula."""
        r = agente_auditor_eps(
            "SIN CONTRATO PACTADO. LA CLÁUSULA TERCERA ESTABLECE…", "TA0201", "X"
        )
        assert any("contradice" in f["flanco"] for f in r["flancos"])

    def test_el_codigo_que_no_cruza(self):
        """El mismo 734101 nombró dos servicios distintos."""
        r = agente_auditor_eps("EL SERVICIO CON CUPS 734101 FUE PRESTADO.", "TA0201", "X")
        assert any("cruza" in f["flanco"] for f in r["flancos"])

    def test_el_plazo_contado_al_reves(self):
        """GL-131 dijo que el Art. 57 da diez días para responder: son quince.
        Decirle a la entidad que nuestro plazo es más corto le regala la
        extemporaneidad contra el propio hospital."""
        r = agente_auditor_eps("EL PLAZO DE DIEZ DÍAS HÁBILES PARA RESPONDER.", "TA0801", "X")
        assert any("plazo" in f["flanco"] for f in r["flancos"])

    def test_no_contestar_la_causal_siempre_se_revisa(self):
        """En auditoría, callar sobre un concepto equivale a aceptarlo."""
        r = agente_auditor_eps("TEXTO CUALQUIERA.", "FA0703", "POLICÍA")
        flanco = [f for f in r["flancos"] if "causal" in f["flanco"]]
        assert flanco, "este flanco aplica siempre"
        assert "FA0703" in flanco[0]["como_lo_tumbaria"]


class TestHablaComoElAuditorDeLaEntidad:
    def test_cada_flanco_dice_como_lo_tumbaria(self):
        r = agente_auditor_eps("EL ARTÍCULO 57 Y LA HISTORIA CLÍNICA.", "AU0202", "X")
        for f in r["flancos"]:
            assert f["como_lo_tumbaria"], f
            assert len(f["como_lo_tumbaria"]) > 30, "tiene que explicar el ataque, no rotularlo"

    def test_un_dictamen_sobrio_deja_pocos_flancos(self):
        """Si el dictamen no cita normas ni afirma soportes, casi no hay por
        dónde entrarle — salvo la causal, que siempre se revisa."""
        r = agente_auditor_eps(
            "ESE HUS NO ACEPTA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO.", "TA0201", "X"
        )
        assert len(r["flancos"]) == 1

    def test_no_rompe_sin_datos(self):
        r = agente_auditor_eps("", "", "")
        assert isinstance(r.get("flancos"), list)


class TestElCupsQueDghYaRegistro:
    """El archivo de recepción no trae CUPS. El motor ya no se lo inventa —eso
    era lo grave— pero así pierde el argumento del código. La tabla de
    conceptos SÍ lo tiene cuando la glosa entró por DGH."""

    def test_sin_factura_no_devuelve_nada(self):
        from app.services.glosa_service import _cups_desde_dgh

        assert _cups_desde_dgh(None) == ("", "")
        assert _cups_desde_dgh("") == ("", "")

    def test_una_factura_que_no_esta_no_inventa_un_codigo(self):
        from app.services.glosa_service import _cups_desde_dgh

        assert _cups_desde_dgh("HUS0000000000") == ("", "")


class TestElAvisoSaleCuandoElSelloDijoQueTodoEstabaBien:
    """El auditor de la EPS se enchufa justo donde quema: cuando la revisión
    de citas NO encontró nada. Ese fue el caso de agosto — tres auditorías
    destaparon defectos graves en dictámenes que habían salido con el sello
    «citas verificadas · 0 hallazgos».

    Lo que se revisa aquí es el cableado: que la puerta lea la revisión que ya
    se hizo CON la evidencia, y no vuelva a revisar por su cuenta (sin
    evidencia un folio inventado no se ve, y el sello quedaría en 0 por
    ignorancia, no por estar limpio).
    """

    def _bloque_del_auditor(self) -> str:
        import pathlib

        fuente = pathlib.Path("app/services/glosa_service.py").read_text(encoding="utf-8")
        ini = fuente.find("EL AUDITOR DE LA EPS, ANTES DE RADICAR")
        assert ini > 0, "se perdió el bloque del auditor de la EPS en analizar()"
        fin = fuente.find("[AUDITOR-EPS] no se aplicó", ini)
        assert fin > ini, "se perdió el cierre del bloque del auditor de la EPS"
        return fuente[ini:fin]

    def test_la_puerta_lee_la_revision_ya_hecha(self):
        bloque = self._bloque_del_auditor()
        assert "verif_citas" in bloque, (
            "la puerta tiene que leer `verif_citas` — la revisión que sí llevó evidencia"
        )

    def test_la_puerta_no_vuelve_a_revisar_por_su_cuenta(self):
        bloque = self._bloque_del_auditor()
        assert "verificar_citas" not in bloque, (
            "no se puede volver a correr el revisor aquí: sería sin evidencia, "
            "y un folio inventado pasaría de largo"
        )

    def test_sin_revision_no_se_promete_nada(self):
        bloque = self._bloque_del_auditor()
        assert "-1" in bloque, (
            "si el revisor no pudo correr, la puerta debe quedarse cerrada, "
            "no dar por bueno un cero que nadie calculó"
        )
