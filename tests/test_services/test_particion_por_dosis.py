"""La cuenta la hace Python, no el modelo.

PRUEBA 4 DE ESTRÉS (01-09-2026) — glosa SO0102, factura HUS0000602741.
ALIANZA MEDELLÍN ANTIOQUIA glosó $1.980.000 diciendo que «NO SE EVIDENCIA
REGISTRO DE ADMINISTRACIÓN» del meropenem facturado por 18 dosis.

El kardex aportado SÍ lo registra — pero de 15 dosis, no de 18. Las dos partes
se equivocan: la premisa de la entidad es falsa, y el hospital facturó tres
dosis que no puede probar. La respuesta correcta es PARCIAL.

La IA leyó bien —escribió «QUINCE (15) DOSIS ADMINISTRADAS Y REGISTRADAS»— y
después recomendó defender el 100 % con RE9901. Sabía el dato y no supo qué
hacer con él.

  $1.980.000 ÷ 18 dosis        = $110.000 por dosis
  15 probadas  × 110.000       = $1.650.000  →  se objetan
   3 sin registro × 110.000    =   $330.000  →  se aceptan
"""

import io

import pytest

from app.services.glosa_service import (
    _borrar_documentos_no_aportados,
    _particion_por_dosis,
)

GLOSA = (
    "SO0102 | HUS0000602741 | ALIANZA MEDELLIN ANTIOQUIA EPS SAS\n"
    "FALTA SOPORTE DE LA ATENCION. NO SE EVIDENCIA REGISTRO DE ADMINISTRACION\n"
    "DEL MEDICAMENTO MEROPENEM 1G FACTURADO POR 18 DOSIS. LA HISTORIA CLINICA\n"
    "APORTADA NO REGISTRA LA APLICACION. SE GLOSA EL TOTAL DEL MEDICAMENTO.\n"
    "VALOR FACTURADO: $3.870.000  VALOR GLOSADO: $1.980.000"
)
ARG = "EL KARDEX DETALLA QUINCE (15) DOSIS DE MEROPENEM 1 G ADMINISTRADAS Y REGISTRADAS."
CTX = "═══ DOCUMENTO: kardex_enfermeria.pdf ═══\nx\n═══ DOCUMENTO: factura.pdf ═══\ny"


class TestLaAritmeticaDelCaso:
    def _p(self) -> dict:
        r = _particion_por_dosis(GLOSA, ARG, 1980000.0)
        assert r is not None
        return r

    def test_cuenta_las_dosis_de_cada_lado(self):
        p = self._p()
        assert p["facturadas"] == 18
        assert p["soportadas"] == 15
        assert p["no_soportadas"] == 3

    def test_el_valor_unitario(self):
        assert self._p()["valor_unitario"] == 110000.0

    def test_la_particion_en_plata(self):
        p = self._p()
        assert p["valor_defender"] == 1650000
        assert p["valor_aceptar"] == 330000

    def test_las_dos_partes_suman_lo_objetado(self):
        """Si no suman, el hospital regala o reclama de más."""
        p = self._p()
        assert p["valor_defender"] + p["valor_aceptar"] == 1980000

    def test_el_parrafo_trae_los_numeros(self):
        p = self._p()["parrafo"]
        for dato in ("15 DOSIS", "18 DOSIS", "$1.650.000", "$330.000", "$110.000"):
            assert dato in p, dato

    def test_el_parrafo_desmiente_la_premisa_de_la_entidad(self):
        assert "ES CONTRARIA A LO QUE ACREDITAN LOS SOPORTES" in self._p()["parrafo"]

    def test_muestra_la_cuenta_para_que_se_pueda_verificar(self):
        assert "÷ 18 DOSIS" in self._p()["parrafo"]


class TestCuandoNoHayParticionQueHacer:
    def test_si_coinciden_no_se_reparte(self):
        arg = "EL KARDEX DETALLA 18 DOSIS ADMINISTRADAS Y REGISTRADAS."
        assert _particion_por_dosis(GLOSA, arg, 1980000.0) is None

    def test_mas_soportadas_que_facturadas_es_para_mirar_a_mano(self):
        arg = "EL KARDEX DETALLA 25 DOSIS ADMINISTRADAS Y REGISTRADAS."
        assert _particion_por_dosis(GLOSA, arg, 1980000.0) is None

    def test_si_la_glosa_no_habla_de_dosis_no_aplica(self):
        g = "SO0102 FALTA LA EPICRISIS DEL EGRESO. SE GLOSA EL TOTAL."
        assert _particion_por_dosis(g, ARG, 1980000.0) is None

    def test_si_el_escrito_no_dice_cuantas_estan_soportadas_no_se_inventa(self):
        arg = "EL KARDEX ACREDITA LA ADMINISTRACION DEL MEDICAMENTO."
        assert _particion_por_dosis(GLOSA, arg, 1980000.0) is None

    @pytest.mark.parametrize("valor", [0.0, -1.0])
    def test_sin_valor_objetado_no_se_reparte_nada(self, valor: float):
        assert _particion_por_dosis(GLOSA, ARG, valor) is None

    def test_textos_vacios_no_rompen(self):
        assert _particion_por_dosis("", ARG, 100.0) is None
        assert _particion_por_dosis(GLOSA, "", 100.0) is None


class TestElMotorFuerzaLaAceptacionParcial:
    MOTOR = io.open("app/services/glosa_service.py", encoding="utf-8").read()

    def test_cambia_el_codigo_de_respuesta_a_parcial(self):
        assert (
            'cod_res, desc_res = "RE9801", "GLOSA ACEPTADA Y SUBSANADA PARCIALMENTE"' in self.MOTOR
        )

    def test_lo_hace_despues_del_refinamiento(self):
        """Antes del refinamiento, el pase de la IA se lo llevaría por delante."""
        i_part = self.MOTOR.index("[PARTICION-DOSIS]")
        i_ref = self.MOTOR.index("arg_ia = _arg_refinado")
        assert i_ref < i_part

    def test_no_se_duplica_si_ya_estaba(self):
        assert '"ACEPTA PARCIALMENTE LA GLOSA POR" not in arg_ia.upper()' in self.MOTOR

    def test_el_gestor_ve_la_cuenta(self):
        assert "La respuesta no podía ser " in self.MOTOR

    def test_nunca_tumba_el_dictamen(self):
        assert "[PARTICION-DOSIS] no aplicada" in self.MOTOR


class TestElDocumentoQueNadieAporto:
    def test_lo_saca_de_la_enumeracion(self):
        a = "EL EXPEDIENTE INCLUYE LA HISTORIA CLINICA INTEGRAL, EL KARDEX Y LA FACTURA."
        limpio, fuera = _borrar_documentos_no_aportados(a, CTX)
        assert "HISTORIA CLINICA" not in limpio
        assert "EL KARDEX Y LA FACTURA" in limpio
        assert fuera == ["historia clínica"]

    def test_si_se_aporto_no_se_toca(self):
        a = "EL EXPEDIENTE INCLUYE LA HISTORIA CLINICA INTEGRAL, EL KARDEX Y LA FACTURA."
        ctx = CTX + "\n═══ DOCUMENTO: historia_clinica.pdf ═══\nz"
        assert _borrar_documentos_no_aportados(a, ctx)[1] == []

    def test_la_mencion_juridica_general_se_respeta(self):
        """«La historia clínica es prueba documental idónea» es legítimo."""
        a = "LA HISTORIA CLINICA ES PRUEBA DOCUMENTAL IDONEA SEGUN LA RES. 1995/1999."
        assert _borrar_documentos_no_aportados(a, CTX)[0] == a

    @pytest.mark.parametrize("doc", ["LA EPICRISIS", "LA ORDEN MEDICA"])
    def test_tambien_vigila_epicrisis_y_orden_medica(self, doc: str):
        a = f"EL EXPEDIENTE INCLUYE {doc}, EL KARDEX Y LA FACTURA."
        assert _borrar_documentos_no_aportados(a, CTX)[1] != []

    def test_argumento_vacio_no_rompe(self):
        assert _borrar_documentos_no_aportados("", CTX) == ("", [])
