"""El gestor tiene que saber QUÉ HACER, no solo qué llegó — 20-08-2026.

Yesid, sobre el correo que reciben los gestores cuando recepción sube el
archivo del día: «está muy plana, no explica muy bien». Y sobre la pantalla:
«que sepan qué entidad deben trabajar, cómo la deben trabajar, qué respuesta es
la más adecuada, los tiempos de radicación vs el tiempo de la notificación de
la glosa; si es médica que se trabaje en conjunto con el médico auditor; si son
extemporáneas tener cuidado; las ratificadas de una vez que salga el mensaje de
texto fijo».

Lo que llegaba era esto, y nada más:

    HUS0000502686 — SEGUROS SURAMERICANA — $213.752 — vence 2026-09-03  AMARILLO

Todo lo que hace falta ya viene en el archivo de recepción: el tipo de glosa,
el profesional médico, los días entre radicación y notificación, y la causal
de cada concepto. Solo faltaba usarlo.
"""

from __future__ import annotations

import pytest

from app.services.glosa_service import TEXTO_RATIFICADA
from app.services.plan_de_trabajo import construir_plan, familia_de


class TestLaFamiliaDeLaCausal:
    @pytest.mark.parametrize(
        "codigo,familia",
        [
            ("CL0801", "CL"),
            ("CO0601", "CO"),
            ("SO5801", "SO"),
            ("TA0201", "TA"),
            ("FA0101", "FA"),
            ("AU0301", "AU"),
        ],
    )
    def test_reconoce_las_del_manual_unico(self, codigo, familia):
        assert familia_de(codigo) == familia

    @pytest.mark.parametrize("basura", [None, "", "X", "ZZ9999", "  "])
    def test_lo_que_no_reconoce_no_lo_inventa(self, basura):
        assert familia_de(basura) == ""

    def test_una_causal_desconocida_no_deja_al_gestor_sin_instruccion(self):
        p = construir_plan(codigo_glosa="ZZ9999")
        assert p.respuesta_sugerida
        assert "clasificar" in p.titular.lower()


class TestLaUrgencia:
    @pytest.mark.parametrize(
        "dias,urgencia",
        [(-3, "VENCIDA"), (0, "HOY"), (2, "URGENTE"), (8, "PRONTO"), (30, "NORMAL")],
    )
    def test_traduce_los_dias_a_algo_que_se_entiende(self, dias, urgencia):
        assert construir_plan(dias_restantes=dias).urgencia == urgencia

    def test_sin_fecha_no_inventa_urgencia(self):
        assert construir_plan(dias_restantes=None).urgencia == "NORMAL"

    def test_una_vencida_va_de_primera(self):
        assert construir_plan(dias_restantes=-1).prioridad == 0


class TestLoQueNecesitaMedico:
    def test_pertinencia_y_calidad_van_con_el_medico(self):
        for codigo in ("CL0801", "PE0101"):
            assert construir_plan(codigo_glosa=codigo).con_medico, codigo

    def test_el_tipo_del_archivo_tambien_manda(self):
        """El archivo de recepción trae «Mixta» y «Administrativo»."""
        assert construir_plan(codigo_glosa="CO0601", tipo_glosa="Mixta").con_medico
        assert not construir_plan(codigo_glosa="CO0601", tipo_glosa="Administrativo").con_medico

    def test_dice_el_nombre_del_medico_cuando_viene(self):
        p = construir_plan(codigo_glosa="CL0801", profesional_medico="DRA. LOPEZ")
        assert "DRA. LOPEZ" in p.ruta

    def test_una_administrativa_no_manda_a_molestar_al_medico(self):
        p = construir_plan(codigo_glosa="TA0201", tipo_glosa="Administrativo")
        assert not p.con_medico
        assert "cartera" in p.ruta.lower()


class TestLasRatificadas:
    def _plan(self):
        return construir_plan(
            codigo_glosa="SO5801", ratificada=True, texto_ratificada=TEXTO_RATIFICADA
        )

    def test_el_texto_fijo_llega_listo_para_copiar(self):
        """Yesid: «de una vez que salga el mensaje de texto fijo»."""
        assert self._plan().texto_listo == TEXTO_RATIFICADA

    def test_avisa_que_es_la_segunda_vuelta(self):
        avisos = " ".join(self._plan().avisos).upper()
        assert "RATIFICADA" in avisos
        assert "SUPERINTENDENCIA" in avisos

    def test_pesa_mas_que_una_inicial(self):
        assert self._plan().prioridad <= 1

    def test_una_inicial_no_trae_texto_de_ratificada(self):
        assert construir_plan(codigo_glosa="SO5801").texto_listo == ""


class TestLasExtemporaneas:
    def test_avisa_y_dice_por_donde_empezar(self):
        """Yesid: «si son extemporáneas tener cuidado con eso»."""
        avisos = " ".join(construir_plan(extemporanea=True).avisos)
        assert "EXTEMPORÁNEA" in avisos
        assert "57" in avisos, "no cita el artículo que la sustenta"
        assert "PRIMERO" in avisos.upper()

    def test_sube_de_prioridad(self):
        assert construir_plan(dias_restantes=30, extemporanea=True).prioridad <= 1


class TestLosTiempos:
    def test_dice_cuanto_se_tardo_la_eps(self):
        """Radicación vs notificación: el dato que sustenta la extemporaneidad.
        En el archivo real de Yesid hay glosas con 54 días."""
        avisos = " ".join(construir_plan(dias_radicacion=54).avisos)
        assert "54 días" in avisos

    def test_no_dice_nada_si_no_hay_dato(self):
        assert not [a for a in construir_plan(dias_radicacion=None).avisos if "días entre" in a]


class TestLaPlata:
    def test_una_glosa_grande_se_mira_antes(self):
        assert construir_plan(dias_restantes=30, valor_objetado=6_000_000).prioridad <= 1

    def test_una_pequena_no_desordena_la_fila(self):
        assert construir_plan(dias_restantes=30, valor_objetado=2400).prioridad == 3

    def test_un_valor_roto_no_revienta(self):
        for malo in (None, "", "no es un numero"):
            assert construir_plan(valor_objetado=malo).prioridad == 3


class TestNuncaSeQuedaMudo:
    """Pase lo que pase, el gestor recibe algo que puede seguir."""

    def test_sin_ningun_dato(self):
        p = construir_plan()
        assert p.titular and p.ruta and p.respuesta_sugerida

    def test_con_todo_en_None(self):
        p = construir_plan(
            codigo_glosa=None,
            tipo_glosa=None,
            dias_restantes=None,
            dias_radicacion=None,
            valor_objetado=None,
            profesional_medico=None,
        )
        assert p.titular and p.ruta
