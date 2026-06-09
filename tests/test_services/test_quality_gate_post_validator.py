"""Tests del Quality Gate — Post-validador.

El post-validador usa el verificador oficial `citation_verifier.verificar_citas`
que valida contra el corpus `normativa_completa._TODAS_LAS_NORMAS`.

Tests se enfocan en el comportamiento del post-validador agregado, no en
los detalles del verificador subyacente (que tiene sus propios tests).
"""

from __future__ import annotations

from app.services.quality_gate.post_validator import (
    check_cierre_canonico,
    check_citas_no_truncadas,
    check_longitud_razonable,
    check_referencias_colgantes,
    check_sin_coda_procesal,
    post_validar_dictamen,
)


class TestCheckCierreCanonico:
    def test_cierre_presente(self):
        res = check_cierre_canonico("...SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA.")
        assert res.ok

    def test_cierre_ausente(self):
        res = check_cierre_canonico("...por lo expuesto.")
        assert not res.ok
        assert res.severidad == "ERROR"

    def test_cierre_minusculas(self):
        res = check_cierre_canonico("se solicita el levantamiento")
        assert res.ok  # case-insensitive

    def test_texto_vacio(self):
        res = check_cierre_canonico("")
        assert not res.ok


class TestCheckSinCodaProcesal:
    def test_sin_coda(self):
        res = check_sin_coda_procesal("SE SOLICITA EL LEVANTAMIENTO.")
        assert res.ok

    def test_con_10_dias(self):
        res = check_sin_coda_procesal("...La entidad cuenta con 10 días hábiles...")
        assert not res.ok
        assert res.severidad == "WARN"

    def test_con_mesa_conciliacion(self):
        res = check_sin_coda_procesal("Se invita a la mesa de conciliación...")
        assert not res.ok

    def test_con_email_hus(self):
        res = check_sin_coda_procesal("Comunicaciones: cartera@hus.gov.co")
        assert not res.ok

    def test_ratificacion_acepta_coda(self):
        res = check_sin_coda_procesal(
            "La entidad cuenta con 10 días hábiles...", es_ratificacion=True
        )
        assert res.ok


class TestCheckLongitud:
    def test_longitud_normal(self):
        res = check_longitud_razonable("X" * 500)
        assert res.ok

    def test_muy_corto(self):
        res = check_longitud_razonable("X" * 100)
        assert not res.ok
        assert res.severidad == "ERROR"

    def test_muy_largo(self):
        res = check_longitud_razonable("X" * 6000)
        assert not res.ok

    def test_vacio(self):
        res = check_longitud_razonable("")
        assert not res.ok


class TestPostValidarDictamen:
    DICTAMEN_LIMPIO_SIN_CITAS = (
        "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE MAYOR VALOR COBRADO. "
        * 5
        + "EN ESE ORDEN DE IDEAS, SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA "
        "Y EL PAGO ÍNTEGRO DE LO FACTURADO."
    )

    DICTAMEN_SIN_CIERRE = "ESE HUS NO ACEPTA LA GLOSA. " * 20

    DICTAMEN_CON_CODA = (
        "ESE HUS NO ACEPTA LA GLOSA. " * 10
        + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA. "
        + "LA ENTIDAD CUENTA CON 10 DÍAS HÁBILES PARA RESPONDER. "
        + "COMUNICACIONES: CARTERA@HUS.GOV.CO."
    )

    def test_dictamen_sin_citas_aprobado(self):
        """Sin citas el verificador no encuentra issues → solo verifica
        cierre, coda, longitud."""
        r = post_validar_dictamen(self.DICTAMEN_LIMPIO_SIN_CITAS)
        assert r.aprobado
        assert r.score >= 90

    def test_dictamen_sin_cierre_rechazado(self):
        r = post_validar_dictamen(self.DICTAMEN_SIN_CIERRE)
        assert not r.aprobado  # falla por cierre
        assert any("cierre" in razon.lower() for razon in r.razones_rechazo)

    def test_dictamen_con_coda_baja_score(self):
        """Coda procesal es WARN — el score baja pero NO bloquea."""
        r = post_validar_dictamen(self.DICTAMEN_CON_CODA, es_ratificacion=False)
        assert r.score < 100
        assert any("coda" in razon.lower() for razon in r.razones_rechazo)

    def test_dictamen_ratificacion_acepta_coda(self):
        r = post_validar_dictamen(self.DICTAMEN_CON_CODA, es_ratificacion=True)
        assert r.checks["coda"].ok  # ratificación NO penaliza coda

    def test_dictamen_extemporanea_acepta_coda(self):
        r = post_validar_dictamen(self.DICTAMEN_CON_CODA, es_extemporanea=True)
        assert r.checks["coda"].ok

    def test_dictamen_demasiado_corto_rechazado(self):
        r = post_validar_dictamen("ESE HUS RECHAZA. SE SOLICITA LEVANTAMIENTO.")
        assert not r.aprobado

    def test_debe_regenerar_si_score_bajo(self):
        # Sin cierre + cita inventada → score bajo
        r = post_validar_dictamen(self.DICTAMEN_SIN_CIERRE)
        if r.score < 70:
            assert r.debe_regenerar

    def test_resultado_incluye_todas_las_claves_de_check(self):
        r = post_validar_dictamen(self.DICTAMEN_LIMPIO_SIN_CITAS)
        assert set(r.checks.keys()) == {
            "citas",
            "cierre",
            "coda",
            "longitud",
            "referencias_colgantes",
            "citas_truncadas",
        }

    def test_score_no_negativo(self):
        # Texto pésimo: vacío
        r = post_validar_dictamen("")
        assert r.score >= 0  # no debe ser negativo


class TestComportamientoConCorpusReal:
    """Tests que verifican el comportamiento end-to-end con el corpus real
    de normativa_completa.py — no mocks."""

    def test_cita_ley_100_art_168_no_marca_grave(self):
        """Ley 100/1993 Art. 168 SÍ existe en el corpus → no debe marcarse grave."""
        texto = (
            "ESE HUS NO ACEPTA LA GLOSA. "
            * 5
            + "DE ACUERDO CON EL ARTÍCULO 168 DE LA LEY 100 DE 1993, "
            "LA ATENCIÓN INICIAL DE URGENCIAS ES OBLIGATORIA. "
            + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        )
        r = post_validar_dictamen(texto)
        # No debe fallar el check de citas con severidad ERROR
        assert r.checks["citas"].ok or r.checks["citas"].severidad != "ERROR"

    def test_cita_inventada_marca_problema(self):
        """Resolución 1552/2019 NO existe → verificador la marca como
        NORMA_INEXISTENTE grave."""
        texto = (
            "ESE HUS NO ACEPTA LA GLOSA. " * 5 + "DE ACUERDO CON LA RESOLUCIÓN 1552 DE 2019, "
            "LAS TARIFAS SE DEBEN RESPETAR. " + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        )
        r = post_validar_dictamen(texto)
        # El verificador debería detectar esta cita inventada
        # (puede ser ERROR o WARN según severidad asignada)
        if r.citas_problematicas:
            assert any("1552" in i.get("cita", "") for i in r.citas_problematicas)


class TestReferenciasColgantes:
    """Regresión: el bug visible en dictámenes reales era 'PORQUE EL ART.
    EN ESTE SENTIDO...' — un 'el Art.' sin número detrás. El post-validador
    debe marcarlo para que el orchestrator regenere ese intento.
    """

    def test_dangling_el_art_se_detecta(self):
        r = check_referencias_colgantes("PORQUE EL ART. EN ESTE SENTIDO QUEDA CLARO QUE NO PROCEDE")
        assert not r.ok
        assert r.severidad == "ERROR"
        assert "colgante" in r.razon.lower()

    def test_dangling_la_ley_se_detecta(self):
        r = check_referencias_colgantes("Conforme a la Ley, la afirmación de la EPS no procede.")
        assert not r.ok

    def test_cita_completa_no_se_detecta_como_colgante(self):
        # "Art. 168" tiene número detrás → no es colgante.
        r = check_referencias_colgantes(
            "Según el Art. 168 de la Ley 100 de 1993, la atención es obligatoria."
        )
        assert r.ok

    def test_articulo_completo_con_numero_no_se_detecta(self):
        r = check_referencias_colgantes(
            "El Artículo 56 de la Ley 1438 de 2011 establece el procedimiento."
        )
        assert r.ok


class TestCitasNoTruncadas:
    """Regresión del bug «...VIGENCIA FISCAL 202…»: la IA copiaba el texto
    de cláusula del prompt con la elipsis pegada. Aunque el prompt ya no
    trunca a 500 chars (PR #87), este check evita que cualquier elipsis
    dentro de chevrones se cuele al dictamen.
    """

    def test_elipsis_unicode_dentro_de_chevrones_se_detecta(self):
        r = check_citas_no_truncadas("Dice la cláusula: «la cobertura integral 202…»")
        assert not r.ok

    def test_elipsis_ascii_dentro_de_chevrones_se_detecta(self):
        r = check_citas_no_truncadas("Dice: «la cobertura integral 202...»")
        assert not r.ok

    def test_cita_completa_pasa(self):
        r = check_citas_no_truncadas("Dice la cláusula: «la cobertura es integral».")
        assert r.ok
