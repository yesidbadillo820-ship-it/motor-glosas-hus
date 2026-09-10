"""Cuatro señales que se contradecían en la misma pantalla (08-09-2026).

Prueba de cinco casos desde el botón Analizar (TA0701, SO3401, CL0101,
FA1605, CO4601). En ninguno fallaba la IA de fondo; lo que fallaba era lo que
el motor DECÍA de sí mismo:

  · el sello verde «VALIDADO POR QUALITY GATE» junto a «⛔ NO RADICAR TODAVÍA»;
  · «INTERPUESTA POR OTRA / SIN DEFINIR» — el marcador del desplegable metido
    en el escrito que se radica ante la EPS;
  · «DEFENSA TÉCNICA: PACIENTE IDENTIFICADO EN EXPEDIENTE» encima de «No se
    encontró el expediente de la factura»;
  · «no se le adjuntó ningún soporte» y, dos renglones abajo, «SÍ se
    adjuntaron soportes, pero ninguno de ese tipo».

Es la misma falla en cuatro sitios: contar una cosa y mostrar otra. En una
audiencia, la EPS usa cualquiera de las cuatro para tumbar la respuesta sin
entrar en el fondo.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.models.schemas import GlosaResult
from app.services.glosa_service import (
    ENTIDAD_SIN_IDENTIFICAR,
    PACIENTE_SIN_IDENTIFICAR,
    _avisos_de_soportes_no_leidos,
    _bloqueos_para_radicar,
    _es_eps_generica,
    _neutralizar_eps_generica_en_dictamen,
    _paciente_honesto,
    _parrafo_cobertura_soat,
)

RAIZ = Path(__file__).resolve().parents[2]


# ═══════════════════════════════════════════════════════════════════════
#  1 · El marcador del desplegable no es el nombre de una entidad
# ═══════════════════════════════════════════════════════════════════════


class TestLaEpsGenerica:
    @pytest.mark.parametrize(
        "eps", ["", None, "OTRA", "otra / sin definir", "OTRA / SIN DEFINIR", "OTRA/SIN DEFINIR"]
    )
    def test_se_reconoce_el_marcador(self, eps):
        assert _es_eps_generica(eps) is True

    @pytest.mark.parametrize("eps", ["COOSALUD", "NUEVA EPS", "SURA", "MUTUAL SER"])
    def test_una_entidad_de_verdad_no_es_generica(self, eps):
        assert _es_eps_generica(eps) is False


class TestElMarcadorNoQuedaEnElEscrito:
    """Casos 4 y 5 de la prueba, palabra por palabra."""

    def test_interpuesta_por(self):
        d = "ESE HUS NO ACEPTA LA GLOSA INTERPUESTA POR OTRA / SIN DEFINIR, RESPECTO DEL..."
        r = _neutralizar_eps_generica_en_dictamen(d, "OTRA / SIN DEFINIR")
        assert "OTRA / SIN DEFINIR" not in r
        assert f"INTERPUESTA POR {ENTIDAD_SIN_IDENTIFICAR}," in r

    def test_se_solicita_a(self):
        d = "SE SOLICITA A OTRA / SIN DEFINIR PRECISAR EL TOPE Y EL VALOR."
        r = _neutralizar_eps_generica_en_dictamen(d, "OTRA / SIN DEFINIR")
        assert r == f"SE SOLICITA A {ENTIDAD_SIN_IDENTIFICAR} PRECISAR EL TOPE Y EL VALOR."

    def test_la_nota_al_gestor_se_conserva_tal_cual(self):
        """El aviso «quedó como «OTRA / SIN DEFINIR»» es para el gestor, no
        para la EPS, y tiene que seguir diciendo exactamente eso."""
        d = (
            "INTERPUESTA POR OTRA / SIN DEFINIR. ⚠ REVISAR ANTES DE RADICAR: NO SE "
            "IDENTIFICÓ LA ENTIDAD PAGADORA (quedó como «OTRA / SIN DEFINIR»)."
        )
        r = _neutralizar_eps_generica_en_dictamen(d, "OTRA / SIN DEFINIR")
        assert "(quedó como «OTRA / SIN DEFINIR»)" in r
        assert r.count("OTRA / SIN DEFINIR") == 1, "solo la del aviso"

    def test_con_una_eps_de_verdad_no_se_toca_nada(self):
        d = "INTERPUESTA POR OTRA / SIN DEFINIR"
        assert _neutralizar_eps_generica_en_dictamen(d, "COOSALUD") == d

    def test_texto_vacio_no_rompe(self):
        assert _neutralizar_eps_generica_en_dictamen("", "OTRA") == ""
        assert _neutralizar_eps_generica_en_dictamen(None, "OTRA") is None

    def test_el_parrafo_de_cobertura_soat_tampoco(self):
        """Caso 5: «SE SOLICITA A OTRA / SIN DEFINIR PRECISAR EL TOPE»."""
        p = _parrafo_cobertura_soat("OTRA / SIN DEFINIR", con_certificado=False)
        assert "OTRA / SIN DEFINIR" not in p
        assert f"SE SOLICITA A {ENTIDAD_SIN_IDENTIFICAR} PRECISAR" in p

    def test_el_parrafo_con_eps_real_sigue_igual(self):
        p = _parrafo_cobertura_soat("COOSALUD", con_certificado=False)
        assert "SE SOLICITA A COOSALUD PRECISAR" in p


# ═══════════════════════════════════════════════════════════════════════
#  2 · Si no hay nombre del paciente, se dice que no lo hay
# ═══════════════════════════════════════════════════════════════════════


class TestElPacienteHonesto:
    @pytest.mark.parametrize(
        "relleno",
        [
            "PACIENTE IDENTIFICADO EN EXPEDIENTE",
            "Paciente identificado en expediente",
            "PACIENTE IDENTIFICADO EN EL EXPEDIENTE",
            "PACIENTE IDENTIFICADO EN LA HISTORIA CLÍNICA",
            "NO IDENTIFICADO",
            "N/A",
            "",
            None,
            "  ",
        ],
    )
    def test_el_relleno_se_dice_como_lo_que_es(self, relleno):
        assert _paciente_honesto(relleno) == PACIENTE_SIN_IDENTIFICAR

    def test_un_nombre_de_verdad_se_conserva(self):
        assert _paciente_honesto("MARÍA FERNANDA LÓPEZ GÓMEZ") == "MARÍA FERNANDA LÓPEZ GÓMEZ"

    def test_el_nombre_se_limpia_de_espacios_sueltos(self):
        assert _paciente_honesto("  JUAN   PÉREZ ") == "JUAN PÉREZ"

    def test_el_prompt_ya_no_ensena_el_relleno_viejo(self):
        """La IA escribía «PACIENTE IDENTIFICADO EN EXPEDIENTE» porque el
        prompt se lo daba como texto por defecto."""
        fuente = (RAIZ / "app" / "services" / "glosa_ia_prompts.py").read_text(encoding="utf-8")
        assert 'sino "PACIENTE IDENTIFICADO EN EXPEDIENTE"' not in fuente
        assert f'sino "{PACIENTE_SIN_IDENTIFICAR}"' in fuente

    def test_el_dictamen_directo_usa_el_mismo_texto(self):
        from app.services.dictamen_directo import generar_dictamen_directo

        defecto = inspect.signature(generar_dictamen_directo).parameters["paciente"].default
        assert defecto == PACIENTE_SIN_IDENTIFICAR


# ═══════════════════════════════════════════════════════════════════════
#  3 · Un aviso de soportes o el otro, nunca los dos
# ═══════════════════════════════════════════════════════════════════════

AFIRMA_EPICRISIS = "LA EPICRISIS DESCRIBE LA EVOLUCIÓN FAVORABLE DEL PACIENTE."
SIN_AFIRMACIONES = "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO."


class TestUnAvisoOElOtro:
    def test_sin_soportes_va_el_de_cero_y_no_el_de_tipo(self):
        """Casos 2, 3 y 5: con la casilla de PDF vacía salían los dos."""
        cero, por_tipo = _avisos_de_soportes_no_leidos(AFIRMA_EPICRISIS, False, "")
        assert cero is True
        assert por_tipo == [], "sin nada adjunto, «sí se adjuntaron soportes» es falso"

    def test_con_soportes_va_el_de_tipo_y_no_el_de_cero(self):
        cero, por_tipo = _avisos_de_soportes_no_leidos(
            AFIRMA_EPICRISIS, True, "KARDEX DE ENFERMERÍA"
        )
        assert cero is False
        assert por_tipo, "afirma la epicrisis y solo llegó un kardex"

    def test_con_el_documento_adjunto_no_hay_aviso(self):
        cero, por_tipo = _avisos_de_soportes_no_leidos(
            AFIRMA_EPICRISIS, True, "EPICRISIS — RESUMEN DE HOSPITALIZACIÓN"
        )
        assert (cero, por_tipo) == (False, [])

    def test_sin_afirmaciones_no_hay_aviso_haya_o_no_soportes(self):
        assert _avisos_de_soportes_no_leidos(SIN_AFIRMACIONES, False, "") == (False, [])
        assert _avisos_de_soportes_no_leidos(SIN_AFIRMACIONES, True, "X") == (False, [])

    def test_nunca_los_dos_a_la_vez(self):
        for tiene in (False, True):
            for texto in ("", "KARDEX", "EPICRISIS"):
                cero, por_tipo = _avisos_de_soportes_no_leidos(AFIRMA_EPICRISIS, tiene, texto)
                assert not (cero and por_tipo), (tiene, texto)


# ═══════════════════════════════════════════════════════════════════════
#  4 · El sello y el «⛔ NO RADICAR» no pueden convivir
# ═══════════════════════════════════════════════════════════════════════


class TestElMotorDiceCuandoBloquea:
    def test_sin_marcas_no_hay_bloqueo(self):
        assert _bloqueos_para_radicar(SIN_AFIRMACIONES) == []
        assert _bloqueos_para_radicar("") == []

    def test_no_radicar_todavia_bloquea(self):
        d = (
            SIN_AFIRMACIONES
            + " ⛔ NO RADICAR TODAVÍA: para responder una glosa SO3401 hace falta la epicrisis."
        )
        motivos = _bloqueos_para_radicar(d)
        assert motivos and "soporte" in motivos[0].lower()

    def test_entidad_sin_identificar_bloquea(self):
        d = SIN_AFIRMACIONES + " ⚠ REVISAR ANTES DE RADICAR: NO SE IDENTIFICÓ LA ENTIDAD PAGADORA."
        assert any("entidad" in m.lower() for m in _bloqueos_para_radicar(d))

    def test_afirmar_un_documento_que_no_se_adjunto_bloquea(self):
        d = "<h4>EL DICTAMEN AFIRMA CONTENIDO DE DOCUMENTOS QUE NO SE ADJUNTARON</h4>"
        assert _bloqueos_para_radicar(d)
        d = "<h4>EL DICTAMEN DICE QUÉ CONTIENE UN DOCUMENTO QUE NO SE APORTÓ: EPICRISIS</h4>"
        assert _bloqueos_para_radicar(d)

    def test_varias_marcas_dan_varios_motivos(self):
        d = (
            "⛔ NO RADICAR TODAVÍA … NO SE IDENTIFICÓ LA ENTIDAD PAGADORA … "
            "AFIRMA CONTENIDO DE DOCUMENTOS QUE NO SE ADJUNTARON"
        )
        assert len(_bloqueos_para_radicar(d)) == 3

    def test_la_respuesta_lleva_los_dos_campos(self):
        """La pantalla los lee para decidir el color del sello."""
        campos = GlosaResult.model_fields
        assert "bloqueado_para_radicar" in campos
        assert "motivos_bloqueo" in campos

    def test_por_defecto_no_se_afirma_nada(self):
        r = GlosaResult(
            tipo="RESPUESTA RE9901",
            resumen="x",
            dictamen="x",
            codigo_glosa="TA0701",
            valor_objetado="$ 1",
            paciente="x",
            mensaje_tiempo="x",
            color_tiempo="x",
        )
        assert r.bloqueado_para_radicar is None and r.motivos_bloqueo is None
