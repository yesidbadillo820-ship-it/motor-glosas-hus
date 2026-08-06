"""El dictamen no puede citar una cláusula que nada respalda.

OT-001 · 05-08-2026. Glosa de prueba AU0401 de FAMISANAR: el dictamen salió
afirmando

    "SE INCUMPLE LA CLÁUSULA 4.2 DEL CONTRATO S-13-1-03-1-04958 QUE INDICA:
     EN LOS TÉRMINOS DE EL PAGADOR RECONOCERÁ LA FACTURA..."

Esa cláusula no existe en el sistema — el Diagnóstico del hospital reporta 0
cláusulas extraídas de 0 contratos con PDF subido. La EPS abre su contrato,
no encuentra la 4.2 y el dictamen queda desmentido.

Las tres guardas que ya existían no la cazaban:
  · check_contratos_no_fabricados mira el número de CONTRATO, y el
    S-13-1-03-1-04958 es real (está en el catálogo y se inyecta al prompt).
  · check_contrato_de_otra_eps mira a quién pertenece: es de FAMISANAR.
  · _descomillar_citas_falsas solo le quita las comillas y deja la
    afirmación en pie, además de la frase rota "QUE INDICA: EN LOS
    TÉRMINOS DE".
"""

from __future__ import annotations

import pytest

from app.services.glosa_service import (
    _clausulas_cargadas,
    _neutralizar_clausulas_sin_respaldo,
)

# Se captura ANTES de que la fixture lo parchee, para poder probar el lector
# real de la base sin desarmar el resto del archivo.
_LECTOR_REAL = _clausulas_cargadas

DICTAMEN_AU0401 = (
    "LA ENTIDAD PAGADORA OBJETA LA FALTA DE AUTORIZACIÓN. SE INCUMPLE LA "
    "CLÁUSULA 4.2 DEL CONTRATO S-13-1-03-1-04958 QUE INDICA: EN LOS TÉRMINOS "
    "DE EL PAGADOR RECONOCERÁ LA FACTURA DENTRO DE LOS PLAZOS PACTADOS. "
    "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
)


@pytest.fixture(autouse=True)
def _base_vacia(monkeypatch):
    """Por defecto, la base del hospital no tiene cláusulas cargadas."""
    monkeypatch.setattr("app.services.glosa_service._clausulas_cargadas", lambda eps="": set())


class TestElCasoReal:
    def test_la_clausula_inventada_desaparece(self):
        out = _neutralizar_clausulas_sin_respaldo(DICTAMEN_AU0401, "FAMISANAR EPS")
        assert "CLÁUSULA 4.2" not in out.upper()
        assert "4.2" not in out

    def test_el_contrato_se_conserva(self):
        """El contrato SÍ existe: se cae la cláusula, no la referencia."""
        out = _neutralizar_clausulas_sin_respaldo(DICTAMEN_AU0401, "FAMISANAR EPS")
        assert "S-13-1-03-1-04958" in out
        assert "EL CONTRATO S-13-1-03-1-04958" in out

    def test_no_queda_la_frase_rota(self):
        out = _neutralizar_clausulas_sin_respaldo(DICTAMEN_AU0401, "FAMISANAR EPS")
        assert "QUE INDICA: EN LOS TÉRMINOS DE" not in out.upper()
        assert "EN LOS TÉRMINOS DE EL PAGADOR" not in out.upper()
        assert "QUE INDICA QUE EL PAGADOR RECONOCERÁ" in out.upper()

    def test_el_resto_del_dictamen_sobrevive(self):
        out = _neutralizar_clausulas_sin_respaldo(DICTAMEN_AU0401, "FAMISANAR EPS")
        assert "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA." in out
        assert "EL PAGADOR RECONOCERÁ LA FACTURA" in out.upper()


class TestLoQueNoSeDebeTocar:
    def test_un_dictamen_sin_clausulas_sale_identico(self):
        d = (
            "LA GLOSA SE FUNDA EN LA RESOLUCIÓN 2284 DE 2023. EL SERVICIO FUE "
            "PRESTADO Y FACTURADO CONFORME A LO PACTADO. SE SOLICITA EL "
            "LEVANTAMIENTO DE LA GLOSA."
        )
        assert _neutralizar_clausulas_sin_respaldo(d, "NUEVA EPS") == d

    def test_texto_vacio(self):
        assert _neutralizar_clausulas_sin_respaldo("", "NUEVA EPS") == ""

    def test_la_clausula_en_palabras_no_se_toca(self):
        """ "CLÁUSULA OCTAVA" es la forma del banco de respuestas aprobado
        del HUS y del archivo semilla (data/clausulas_contrato_base.json trae
        "Octava, numeral 3"). Borrarla sería romper texto ya validado por los
        auditores."""
        d = "LA CLÁUSULA OCTAVA DEL CONTRATO ESTABLECE EL PLAZO DE PAGO."
        assert _neutralizar_clausulas_sin_respaldo(d, "AURORA") == d

    def test_la_clausula_que_cita_la_propia_eps_se_conserva(self):
        """Si el número lo puso la EPS en su glosa, no es invención del
        motor: es el dato con el que hay que discutir."""
        glosa = (
            "AU0401 — SE INCUMPLE LA CLÁUSULA 4.2 DEL CONTRATO "
            "S-13-1-03-1-04958 SUSCRITO ENTRE LAS PARTES."
        )
        out = _neutralizar_clausulas_sin_respaldo(
            DICTAMEN_AU0401, "FAMISANAR EPS", texto_glosa=glosa
        )
        assert out == DICTAMEN_AU0401

    def test_la_clausula_cargada_en_la_base_se_conserva(self, monkeypatch):
        monkeypatch.setattr(
            "app.services.glosa_service._clausulas_cargadas",
            lambda eps="": {"4.2", "OCTAVA, NUMERAL 3"},
        )
        out = _neutralizar_clausulas_sin_respaldo(DICTAMEN_AU0401, "FAMISANAR EPS")
        assert out == DICTAMEN_AU0401

    def test_sin_base_disponible_no_borra_nada(self, monkeypatch):
        """Si la consulta a la base falla, la red se apaga sola en vez de
        vaciar el dictamen."""
        import app.services.glosa_service as gs

        def _explota(eps=""):
            raise RuntimeError("base caída")

        monkeypatch.setattr(gs, "_clausulas_cargadas", _explota)
        with pytest.raises(RuntimeError):
            gs._neutralizar_clausulas_sin_respaldo(DICTAMEN_AU0401, "FAMISANAR EPS")

    def test_el_lector_real_devuelve_conjunto_sin_reventar(self):
        """El lector de la base nunca propaga un fallo: devuelve conjunto."""
        assert isinstance(_LECTOR_REAL("FAMISANAR EPS"), set)
        assert isinstance(_LECTOR_REAL(""), set)


class TestElPermisoNoSobreviveAlCambioDeContrato:
    """05-08-2026, dictamen real de AURORA. La glosa decía "Contrato
    S-13-1-03-1-04958, cláusula 7.4". La red de contratos ajenos —que corre
    justo antes— cambió ese número por el contrato de AURORA, y la cláusula
    7.4 se quedó colgando de OTRO contrato: el dictamen terminó afirmando
    que el contrato de AURORA tiene una cláusula 7.4."""

    GLOSA_AURORA = (
        "FA0101 - Se glosa el procedimiento por cuanto el valor facturado supera "
        "la tarifa pactada en el Contrato S-13-1-03-1-04958, cláusula 7.4."
    )

    def test_si_le_cambiaron_el_contrato_la_clausula_se_cae(self):
        d = "SEGUN LO ESTABLECIDO EN EL CONTRATO GID-ARL-0090, CLÁUSULA 7.4, LA TARIFA ES SOAT -3%."
        out = _neutralizar_clausulas_sin_respaldo(d, "AURORA", texto_glosa=self.GLOSA_AURORA)
        assert "CLÁUSULA 7.4" not in out.upper()
        assert "GID-ARL-0090" in out

    def test_no_queda_el_contrato_nombrado_dos_veces(self):
        d = "SEGUN LO ESTABLECIDO EN EL CONTRATO GID-ARL-0090, CLÁUSULA 7.4, LA TARIFA ES SOAT -3%."
        out = _neutralizar_clausulas_sin_respaldo(d, "AURORA", texto_glosa=self.GLOSA_AURORA)
        assert "EL CONTRATO VIGENTE ENTRE LAS PARTES" not in out
        assert ", ," not in out
        assert out == "SEGUN LO ESTABLECIDO EN EL CONTRATO GID-ARL-0090, LA TARIFA ES SOAT -3%."

    def test_si_sigue_en_el_mismo_contrato_se_conserva(self):
        d = "SEGUN LA CLÁUSULA 7.4 DEL CONTRATO S-13-1-03-1-04958 LA TARIFA ES SOAT -3%."
        assert _neutralizar_clausulas_sin_respaldo(d, "FAMISANAR EPS", self.GLOSA_AURORA) == d

    def test_mismo_contrato_con_el_orden_invertido(self):
        d = "EL CONTRATO S-13-1-03-1-04958, CLÁUSULA 7.4, FIJA LA TARIFA."
        assert _neutralizar_clausulas_sin_respaldo(d, "FAMISANAR EPS", self.GLOSA_AURORA) == d

    def test_sin_contrato_cerca_manda_lo_que_dijo_la_eps(self):
        d = "SE INCUMPLE LA CLÁUSULA 7.4 SOBRE TARIFAS."
        assert _neutralizar_clausulas_sin_respaldo(d, "FAMISANAR EPS", self.GLOSA_AURORA) == d


class TestOtrasFormasDeCitarla:
    def test_clausula_suelta_sin_contrato(self):
        d = "SE INCUMPLE LA CLÁUSULA 18 SOBRE OPORTUNIDAD DE PAGO."
        out = _neutralizar_clausulas_sin_respaldo(d, "SANITAS")
        assert "CLÁUSULA 18" not in out.upper()
        assert "EL CONTRATO VIGENTE ENTRE LAS PARTES" in out

    def test_numeracion_de_tres_niveles(self):
        d = "CONFORME A LA CLÁUSULA 4.2.1 DEL CONTRATO S-13-1-03-1-04958."
        out = _neutralizar_clausulas_sin_respaldo(d, "FAMISANAR EPS")
        assert "4.2.1" not in out
        assert "S-13-1-03-1-04958" in out

    def test_varias_clausulas_en_el_mismo_dictamen(self):
        d = (
            "SE INCUMPLE LA CLÁUSULA 4.2 DEL CONTRATO S-13-1-03-1-04958 Y "
            "TAMBIÉN LA CLÁUSULA 7 SOBRE SOPORTES."
        )
        out = _neutralizar_clausulas_sin_respaldo(d, "FAMISANAR EPS")
        assert "CLÁUSULA" not in out.upper()
        assert "S-13-1-03-1-04958" in out
        assert "EL CONTRATO VIGENTE ENTRE LAS PARTES" in out


class TestLaRedEstaEnchufada:
    def test_la_llama_la_cadena_de_redes_finales(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_neutralizar_clausulas_sin_respaldo(" in src
        i = src.index("_neutralizar_clausulas_sin_respaldo(")
        bloque = src[max(0, i - 400) : i + 400]
        assert "texto_base" in bloque, "la red necesita el texto de la glosa de la EPS"
        assert "CLAUSULA-SIN-RESPALDO" in bloque, "un fallo no puede tumbar el dictamen"
