"""A las médicas auditoras también les llega el correo con sus glosas.

QUÉ PASÓ (25-08-2026). Se importaron 117 glosas del archivo de recepción. Los
seis gestores recibieron su correo. **Las tres médicas auditoras no recibieron
nada** — ni Laura Díaz, ni Zulay González, ni Leidy Sanguino — aunque doce
glosas venían marcadas «Mixta» o «Medico» y con el nombre de cada una en la
columna PROFESIONAL(MEDICO) del Excel.

LA CAUSA, y es sutil. El nombre de la médica SÍ se leía del Excel y SÍ quedaba
guardado en la glosa. Pero después, al completar el plan de trabajo con la
causal de cada glosa, el plan **se vuelve a armar** — y en esa segunda pasada
se le pasaba `profesional_medico=None`, que borraba el nombre.

El correo usa justamente ese campo para saber a qué doctora mandarle lo suyo.
Sin nombre, la lista de médicas salía vacía y no se le escribía a ninguna. En
la pantalla se notaba: el plan decía «CON EL MÉDICO AUDITOR.» a secas, sin el
nombre que el código pone cuando lo tiene.

Ahora el nombre se conserva. Se saca de la MISMA consulta que ya se hacía para
la causal, así que no hay una segunda vuelta a la base.
"""

import pytest

from app.services.email_service import _doctoras_nombradas, _hay_glosas_medicas
from app.services.recepcion_service import _plan_de


def _plan(codigo: str, tipo: str, medico=None) -> dict:
    return _plan_de(
        codigo_glosa=codigo,
        tipo_glosa=tipo,
        dias_restantes=7,
        dias_radicacion=None,
        estado="INICIAL",
        valor=1_000_000,
        profesional_medico=medico,
    )


class TestElPlanConservaElNombreDeLaMedica:
    def test_con_nombre_lo_guarda(self):
        p = _plan("CL0801", "Mixta", "LAURA DIAZ")
        assert p["con_medico"] is True
        assert p["profesional_medico"] == "LAURA DIAZ"

    def test_y_lo_escribe_en_la_ruta_para_que_se_vea(self):
        p = _plan("CL0801", "Mixta", "LAURA DIAZ")
        assert "LAURA DIAZ" in p["ruta"]

    def test_sin_nombre_la_ruta_queda_a_secas(self):
        """Así se veía en pantalla el día del defecto: sin nombre después."""
        p = _plan("CL0801", "Mixta", None)
        assert p["con_medico"] is True
        assert p["profesional_medico"] == ""
        assert p["ruta"].startswith("CON EL MÉDICO AUDITOR.")


class TestElCorreoSabeAQuienEscribirle:
    """Con los datos reales del lote del 25-08."""

    RESUMEN = {
        "por_gestor": {
            "EQUIPO ASEGURADORAS": [
                {"factura": "HUS0000539750", "plan": _plan("CL0801", "Mixta", "LAURA DIAZ")},
                {"factura": "HUS0000544828", "plan": _plan("CL0801", "Mixta", "ZULAY GONZALEZ")},
                {"factura": "HUS0000534470", "plan": _plan("CL2301", "Medico", "LEIDY SANGUINO")},
                {"factura": "HUS0000533280", "plan": _plan("FA0801", "Administrativa", None)},
            ]
        }
    }

    def test_detecta_que_el_lote_trae_glosas_medicas(self):
        assert _hay_glosas_medicas(self.RESUMEN) is True

    def test_nombra_a_las_tres_medicas(self):
        assert _doctoras_nombradas(self.RESUMEN) == [
            "LAURA DIAZ",
            "ZULAY GONZALEZ",
            "LEIDY SANGUINO",
        ]

    def test_no_repite_a_una_medica_con_varias_glosas(self):
        resumen = {
            "por_gestor": {
                "X": [
                    {"plan": _plan("CL0801", "Mixta", "LAURA DIAZ")},
                    {"plan": _plan("CL2301", "Medico", "laura diaz")},
                ]
            }
        }
        assert _doctoras_nombradas(resumen) == ["LAURA DIAZ"]

    def test_una_glosa_administrativa_no_nombra_a_nadie(self):
        resumen = {"por_gestor": {"X": [{"plan": _plan("FA0801", "Administrativa", None)}]}}
        assert _hay_glosas_medicas(resumen) is False
        assert _doctoras_nombradas(resumen) == []


class TestElDefectoQueSeCorrigio:
    """Lo que pasaba al rehacer el plan con la causal."""

    def test_rehacer_el_plan_sin_el_nombre_deja_al_correo_sin_a_quien_escribir(self):
        """Este es exactamente el estado en que quedaba el resumen antes."""
        resumen_roto = {"por_gestor": {"X": [{"plan": _plan("CL0801", "Mixta", None)}]}}
        # El lote SÍ tiene glosas médicas...
        assert _hay_glosas_medicas(resumen_roto) is True
        # ...pero no hay a quién escribirle.
        assert _doctoras_nombradas(resumen_roto) == []

    def test_conservando_el_nombre_si_hay_a_quien_escribirle(self):
        resumen_sano = {"por_gestor": {"X": [{"plan": _plan("CL0801", "Mixta", "LEIDY SANGUINO")}]}}
        assert _doctoras_nombradas(resumen_sano) == ["LEIDY SANGUINO"]


class TestElNombreDelExcelYElDelPortalPuedenDiferir:
    @pytest.mark.parametrize(
        "en_el_excel,en_el_portal",
        [
            ("LAURA DIAZ", "LAURA DIAZ"),
            ("ZULAY GONZALEZ", "LEYDI ZULAY GONZALEZ"),
            ("LEIDY SANGUINO", "LEIDY JHOANA SANGUINO"),
        ],
    )
    def test_el_resolvedor_por_tokens_los_junta(self, en_el_excel, en_el_portal):
        """El Excel escribe el nombre corto y el portal el completo. Sin
        comparar por partes del nombre, esos correos no saldrían nunca."""
        from app.services.recepcion_service import (
            construir_indice_usuarios,
            resolver_gestor_a_email,
        )

        class _Usuaria:
            nombre = en_el_portal
            email = "auditora@sinacsc.com"
            activo = 1
            vacaciones_desde = None
            vacaciones_hasta = None
            delega_a_email = None

        class _Consulta:
            def filter(self, *a, **k):
                return self

            def all(self):
                return [_Usuaria()]

        class _Db:
            def query(self, *a, **k):
                return _Consulta()

        indice = construir_indice_usuarios(_Db())
        email, _motivo = resolver_gestor_a_email(en_el_excel, indice)
        assert email == "auditora@sinacsc.com", f"no juntó «{en_el_excel}» con «{en_el_portal}»"
