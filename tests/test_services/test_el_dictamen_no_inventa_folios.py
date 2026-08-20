"""El dictamen no puede citar un folio que nadie leyó — 20-08-2026.

Los CUPS y los soportes ya se verificaban. Los FOLIOS no. Un dictamen podía
salir sellado con «citas verificadas · 0 hallazgos» diciendo:

    «SEGÚN CONSTA EN EL FOLIO 25 DE LA HISTORIA CLÍNICA»

sin que nadie hubiera abierto una historia clínica. Es la afirmación más fácil
de tumbar que existe: la EPS pide el folio 25, no está, y ratifica la glosa
completa — y en el expediente queda una afirmación documental falsa firmada
por el hospital.

Lo que hace confiable la revisión: **la IA y el validador leen exactamente el
mismo texto**. Si el folio no aparece en lo que la IA pudo leer, la IA no lo
leyó: se lo inventó.
"""

from __future__ import annotations

from app.services.extractor_folios import (
    extraer_referencias_documentales,
    folios_citados,
    folios_en_evidencia,
    folios_inventados,
)
from app.services.validador_dictamen import (
    construir_instruccion_retry,
    detectar_defectos_criticos,
)


def _xml(arg: str) -> str:
    return (
        "<paciente>X</paciente><servicio>S</servicio>"
        "<contrato>C</contrato><tarifa>T</tarifa>"
        "<normas_clave>N1|N2</normas_clave>"
        f"<argumento>{arg}</argumento>"
    )


_ARGUMENTO_CON_FOLIO = (
    "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE SOPORTES SOBRE EL "
    "CÓDIGO SO0201, INTERPUESTA POR COOSALUD. SEGÚN CONSTA EN EL FOLIO 25 DE "
    "LA HISTORIA CLÍNICA, EL SERVICIO FUE EFECTIVAMENTE PRESTADO Y SE "
    "ENCUENTRA DEBIDAMENTE SOPORTADO. POR LO ANTERIOR SE SOLICITA EL "
    "LEVANTAMIENTO DE LA GLOSA Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR "
    "FACTURADO."
)

_ARGUMENTO_SIN_FOLIO = (
    "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE SOPORTES SOBRE EL "
    "CÓDIGO SO0201, INTERPUESTA POR COOSALUD. LA HISTORIA CLÍNICA ACREDITA "
    "QUE EL SERVICIO FUE EFECTIVAMENTE PRESTADO Y SE ENCUENTRA DEBIDAMENTE "
    "SOPORTADO. POR LO ANTERIOR SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y "
    "EL RECONOCIMIENTO ÍNTEGRO DEL VALOR FACTURADO."
)


class TestQueCuentaComoFolioCitado:
    def test_encuentra_el_folio_suelto(self):
        assert folios_citados("SEGÚN CONSTA EN EL FOLIO 25 DE LA HISTORIA") == [25]

    def test_encuentra_listas_y_rangos(self):
        assert folios_citados("OBRA A FOLIOS 12 AL 15 Y FL. 3") == [12, 15, 3]

    def test_encuentra_folio_con_abreviatura_de_numero(self):
        assert folios_citados("SEGUN FOLIO No. 47 SUSCRITO POR EL MEDICO") == [47]

    def test_no_repite_el_mismo_folio(self):
        assert folios_citados("FOLIO 25 ... FOLIO 25 ... FOLIO 25") == [25]

    def test_un_rango_no_se_expande(self):
        """«FOLIOS 1 A 40» afirma dos extremos, no cuarenta folios. Expandirlo
        llenaría la pantalla del auditor de avisos que no puede atender."""
        assert folios_citados("FOLIOS 1 A 40") == [1, 40]


class TestLoQueNoEsUnFolio:
    """Falsos positivos: un aviso equivocado en cada dictamen enseña al
    auditor a ignorar los avisos, y ahí se pierde también el verdadero."""

    def test_la_hoja_de_administracion_de_medicamentos_no_es_un_folio(self):
        assert folios_citados("SE APORTA HOJA DE ADMINISTRACIÓN DE MEDICAMENTOS") == []

    def test_contar_folios_no_es_citar_un_folio(self):
        assert folios_citados("SE APORTA HISTORIA CLÍNICA DE 25 FOLIOS") == []

    def test_portafolio_no_es_folio(self):
        assert folios_citados("SERVICIOS DEL PORTAFOLIO 5 DE LA IPS") == []

    def test_una_norma_con_numeros_no_es_un_folio(self):
        texto = "RESOLUCIÓN 2284 DE 2023, ARTÍCULO 57 DE LA LEY 1438 DE 2011"
        assert folios_citados(texto) == []


class TestCuandoUnFolioEstaInventado:
    def test_sin_soportes_leidos_cualquier_folio_esta_inventado(self):
        assert folios_inventados("CONSTA EN EL FOLIO 25", "") == [25]

    def test_si_el_folio_esta_en_el_expediente_no_se_marca(self):
        evidencia = "... folio 24 ... folio 25 ... folio 26 ..."
        assert folios_inventados("CONSTA EN EL FOLIO 25", evidencia) == []

    def test_solo_marca_el_que_falta(self):
        assert folios_inventados("FOLIOS 25 Y 31", "página 31 del expediente") == [25]

    def test_un_dictamen_sin_folios_nunca_se_marca(self):
        assert folios_inventados(_ARGUMENTO_SIN_FOLIO, "") == []

    def test_no_se_compara_contra_la_lista_recortada_del_prompt(self):
        """REGRESIÓN. `extraer_referencias_documentales` devuelve solo los 5
        folios MÁS FRECUENTES, para no saturar el prompt. Si la verificación
        se hiciera contra esa lista, un folio real pero poco repetido saldría
        marcado como inventado y el auditor perdería la confianza en el aviso.
        """
        evidencia = (
            "folio 1 folio 1 folio 1 folio 2 folio 2 folio 2 folio 3 folio 3 "
            "folio 4 folio 4 folio 5 folio 5 folio 9"
        )
        recortada = extraer_referencias_documentales(evidencia)["folios_citables"]
        assert 9 not in recortada  # el folio 9 no entra en el top 5
        assert 9 in folios_en_evidencia(evidencia)  # pero SÍ está en el expediente
        assert folios_inventados("CONSTA EN EL FOLIO 9", evidencia) == []


class TestElValidadorFuerzaElReintento:
    def test_marca_el_folio_inventado_como_defecto(self):
        defectos = detectar_defectos_criticos(
            _xml(_ARGUMENTO_CON_FOLIO),
            codigo_glosa="SO0201",
            evidencia="",
        )
        reglas = {d["regla"] for d in defectos}
        assert "folio_inventado" in reglas

    def test_le_dice_a_la_ia_como_corregirlo(self):
        defectos = detectar_defectos_criticos(
            _xml(_ARGUMENTO_CON_FOLIO),
            codigo_glosa="SO0201",
            evidencia="",
        )
        instr = construir_instruccion_retry(defectos)
        assert "25" in instr
        assert "NO cites números de folio" in instr

    def test_no_marca_cuando_el_folio_es_real(self):
        defectos = detectar_defectos_criticos(
            _xml(_ARGUMENTO_CON_FOLIO),
            codigo_glosa="SO0201",
            evidencia="HISTORIA CLÍNICA — FOLIO 25 — SIGNOS VITALES",
        )
        assert "folio_inventado" not in {d["regla"] for d in defectos}

    def test_sin_evidencia_declarada_no_se_revisa(self):
        """Compatibilidad: quien no pase `evidencia` no puede saber qué leyó
        la IA, así que no se inventa un fallo."""
        defectos = detectar_defectos_criticos(
            _xml(_ARGUMENTO_CON_FOLIO),
            codigo_glosa="SO0201",
        )
        assert "folio_inventado" not in {d["regla"] for d in defectos}


class TestElAuditorLoVeEnPantalla:
    """Si el reintento no logra quitarlo, el aviso tiene que llegar al
    auditor ANTES de radicar — no quedarse en el log."""

    def test_el_verificador_de_citas_lo_reporta(self):
        from app.services.citation_verifier import verificar_citas

        rep = verificar_citas(_ARGUMENTO_CON_FOLIO, eps="COOSALUD", evidencia="")
        tipos = {i["tipo"] for i in rep["issues"]}
        assert "FOLIO_INVENTADO" in tipos

    def test_lo_reporta_como_grave(self):
        from app.services.citation_verifier import verificar_citas

        rep = verificar_citas(_ARGUMENTO_CON_FOLIO, eps="COOSALUD", evidencia="")
        folio = next(i for i in rep["issues"] if i["tipo"] == "FOLIO_INVENTADO")
        assert folio["severidad"] == "ALTA"
        assert "25" in folio["cita"]
        assert rep["tiene_problemas_graves"] is True

    def test_explica_en_cristiano_por_que_importa(self):
        from app.services.citation_verifier import verificar_citas

        rep = verificar_citas(_ARGUMENTO_CON_FOLIO, eps="COOSALUD", evidencia="")
        folio = next(i for i in rep["issues"] if i["tipo"] == "FOLIO_INVENTADO")
        assert "ratifica la glosa" in folio["detalle"]
        assert folio["sugerencia"]

    def test_quien_no_pasa_evidencia_sigue_viendo_lo_mismo_de_antes(self):
        from app.services.citation_verifier import verificar_citas

        rep = verificar_citas(_ARGUMENTO_CON_FOLIO, eps="COOSALUD")
        assert "FOLIO_INVENTADO" not in {i["tipo"] for i in rep["issues"]}


class TestElCableadoNoSeSuelta:
    """La revisión solo sirve si de verdad se le pasa al validador lo que la
    IA leyó. Si mañana alguien agrega otra llamada sin `evidencia`, ese
    camino vuelve a dejar pasar folios inventados sin que nadie se entere.
    Se revisa el código, no un comentario.
    """

    @staticmethod
    def _llamadas_en_analizar(nombres: set[str]) -> list:
        import ast
        import pathlib

        fuente = pathlib.Path("app/services/glosa_service.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        analizar = next(
            n
            for n in ast.walk(arbol)
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "analizar"
        )
        return [
            n
            for n in ast.walk(analizar)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in nombres
        ]

    def test_el_validador_siempre_recibe_lo_que_leyo_la_ia(self):
        llamadas = self._llamadas_en_analizar({"detectar_defectos_criticos"})
        assert llamadas, "no se encontró ninguna llamada al validador en analizar()"
        for c in llamadas:
            assert "evidencia" in {k.arg for k in c.keywords}, (
                "una llamada a detectar_defectos_criticos no pasa `evidencia`: "
                "por ese camino un folio inventado no se detecta"
            )

    def test_el_verificador_de_citas_tambien(self):
        llamadas = self._llamadas_en_analizar({"_vc"})
        assert llamadas, "no se encontró ninguna llamada a verificar_citas en analizar()"
        for c in llamadas:
            assert "evidencia" in {k.arg for k in c.keywords}, (
                "una llamada a verificar_citas no pasa `evidencia`: por ese "
                "camino el auditor no ve el aviso de folio inventado"
            )

    def test_la_evidencia_incluye_los_pdf_y_el_texto_de_la_glosa(self):
        import ast
        import pathlib

        fuente = pathlib.Path("app/services/glosa_service.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        asignaciones = [
            n
            for n in ast.walk(arbol)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_evidencia_leida" for t in n.targets)
        ]
        assert len(asignaciones) == 1, "la evidencia debe armarse en un solo lugar"
        expr = ast.unparse(asignaciones[0].value)
        assert "contexto_pdf" in expr
        assert "texto_base" in expr


class TestLaInstruccionQueCausabaElFolioInventado:
    """La causa, no el síntoma — 20-08-2026.

    El prompt del Auditor Forense traía dos reglas que se contradicen:

        2. «Cita SIEMPRE el folio o página específica (ej: "FOLIO 25")»
        5. «NO inventes folios»

    Cuando el documento no viene foliado no se pueden cumplir las dos. El
    modelo obedece la afirmativa —la que le manda hacer algo— y se inventa
    un folio. Y el ejemplo traía un número copiable: «FOLIO 25», que es
    exactamente el que apareció en los dictámenes inventados.
    """

    @staticmethod
    def _prompt_forense() -> str:
        from app.services.auditor_forense import SYSTEM_AUDITOR_FORENSE

        return SYSTEM_AUDITOR_FORENSE

    def test_ya_no_exige_citar_folio_siempre(self):
        p = self._prompt_forense().upper()
        assert "CITA SIEMPRE EL FOLIO" not in p

    def test_la_regla_es_condicional(self):
        p = self._prompt_forense().upper()
        assert "SOLO CUANDO EL DOCUMENTO LO TRAIGA ESCRITO" in p

    def test_dice_que_hacer_si_no_hay_foliacion(self):
        """Prohibir sin dar la alternativa deja al modelo sin salida."""
        p = self._prompt_forense().upper()
        assert "NO ESTÁ FOLIADO" in p
        assert "FECHA" in p

    def test_sigue_prohibiendo_inventarlos(self):
        p = self._prompt_forense().upper()
        assert "NO INVENTES FOLIOS" in p

    def test_el_anclaje_del_dictamen_tambien_quedo_condicionado(self):
        """El prompt global ofrecía «LA HISTORIA CLÍNICA FOLIO [N]…» como
        primer molde del anclaje probatorio, sin decir cuándo NO usarlo."""
        from app.services.glosa_ia_prompts import SYSTEM_BASE

        p = SYSTEM_BASE.upper()
        assert "ÚNICAMENTE SI EL PDF TRAE ESE NÚMERO ESCRITO" in p


class TestLosFoliosQueSiLeyoElForense:
    """El Auditor Forense corre ANTES del dictamen y antepone al contexto un
    mapa de folios auditados. Esos folios SÍ se leyeron: citarlos es
    correcto, y marcarlos como inventados sería el peor falso positivo
    posible — castigaría justamente al dictamen bien fundamentado.
    """

    EVIDENCIA_FORENSE = (
        "═══ EVIDENCIA FORENSE (folios auditados de los soportes) ═══\n"
        "- FOLIO 3: hoja de atención de urgencias del 28/02/2026, triage II.\n"
        "- FOLIO 7: orden médica de baciloscopia suscrita por el tratante.\n"
        "═══ FIN EVIDENCIA FORENSE ═══\n\n"
    )

    def test_un_folio_auditado_no_se_marca(self):
        assert folios_inventados("OBRA AL FOLIO 7", self.EVIDENCIA_FORENSE) == []

    def test_uno_que_el_forense_no_vio_si_se_marca(self):
        assert folios_inventados("OBRA AL FOLIO 40", self.EVIDENCIA_FORENSE) == [40]

    def test_el_router_le_pasa_al_motor_el_contexto_ya_enriquecido(self):
        """El mapa de folios se antepone a `contexto_pdf` en el router, y ESE
        mismo `contexto_pdf` es el que recibe el motor. Si algún día se le
        pasara otra variable, los folios auditados dejarían de contar como
        leídos y el dictamen bien hecho saldría con avisos falsos.
        """
        import ast
        import pathlib

        fuente = pathlib.Path("app/api/routers/analizar.py").read_text(encoding="utf-8")
        arbol = ast.parse(fuente)
        llamadas = [
            n
            for n in ast.walk(arbol)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "analizar"
        ]
        assert llamadas, "no se encontró la llamada al motor en el router"
        for c in llamadas:
            posicionales = [ast.unparse(a) for a in c.args]
            assert "contexto_pdf" in posicionales, (
                "el motor debe recibir el contexto_pdf ya enriquecido "
                "(inventario de soportes + mapa de folios del forense)"
            )
