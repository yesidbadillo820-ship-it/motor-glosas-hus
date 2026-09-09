"""Un dictamen no puede salir citando el contrato de otra entidad.

09-09-2026, prueba del auditor. Corrió una glosa que empezaba así:

    «DISPENSARIO MEDICO · Etapa: Inicial
     FA0801 $275.000 APOYO DIAGNOSTICO: SE FACTURAN 4 RADIOGRAFIAS…»

con el desplegable en FAMISANAR (le había quedado de la glosa anterior). El
motor **no corrigió nada**, y el dictamen salió:

    · firmado a nombre de FAMISANAR EPS,
    · citando el contrato S-13-1-03-1-04958 —el de FAMISANAR—,
    · aplicando su tarifa «SOAT UVB VIGENTE −5 %»,

para una factura de **sanidad militar**. Radicado así, la entidad lo tumba
sin leer el fondo: le están respondiendo con el contrato de otra.

POR QUÉ NO LO CORRIGIÓ. `resolver_eps_efectiva` existe justamente para esto
—se escribió en junio por el caso inverso, cuando el desplegable decía
Dispensario y la glosa era de una EPS— pero su lista de pagadores tenía el
Dispensario **solo con el nombre largo**, «DISPENSARIO MEDICO BUCARAMANGA».
El nombre corto, que es como lo escribe medio mundo, no cruzaba. Y con él no
cruzaban tampoco DIGSA, «SANIDAD EJÉRCITO» ni la Policía.

QUÉ CUIDA ESTA PRUEBA. Que los regímenes especiales se detecten en el texto
igual que las EPS del contributivo, que se resuelvan al MISMO nombre canónico
que ya usaba el motor —si se devolviera otro, el contrato se buscaría con un
nombre que la malla no conoce— y que las EPS que ya funcionaban sigan igual.
"""

from __future__ import annotations

import pytest

from app.services.glosa_ia_prompts import get_contrato, resolver_eps_efectiva


class TestElCasoDelAuditor:
    def test_el_dispensario_con_el_nombre_corto_se_detecta(self):
        eps, corrigio, _ = resolver_eps_efectiva(
            "FAMISANAR EPS",
            "DISPENSARIO MEDICO · Etapa: Inicial\nFA0801 $275.000 APOYO DIAGNOSTICO",
        )
        assert corrigio, (
            "El motor dejó FAMISANAR en una glosa del Dispensario. El dictamen "
            "sale con el contrato y la tarifa de otra entidad."
        )
        assert eps == "DMBUG"

    def test_y_trae_SU_contrato_no_el_de_famisanar(self):
        eps, _, _ = resolver_eps_efectiva("FAMISANAR EPS", "DISPENSARIO MEDICO FA0801 $275.000")
        numero = str(get_contrato(eps).get("numero") or "")
        assert "DIGSA" in numero or "DMBUG" in numero, numero
        assert "S-13-1-03-1-04958" not in numero, (
            "Sigue trayendo el contrato de FAMISANAR para una glosa militar."
        )


class TestLasFormasEnQueSeNombraLaSanidadMilitar:
    @pytest.mark.parametrize(
        "texto",
        [
            "DISPENSARIO MEDICO FA0801",
            "DISPENSARIO MÉDICO FA0801",
            "DISPENSARIO MEDICO BUCARAMANGA FA0801",
            "DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA",
            "GLOSA DMBUG TA0801 $12.000",
            "CONTRATO DIGSA TA0801",
            "SANIDAD MILITAR SO0101",
        ],
    )
    def test_todas_llevan_al_mismo_canonico(self, texto):
        eps, _, _ = resolver_eps_efectiva("FAMISANAR EPS", texto)
        assert eps == "DMBUG", (
            f"«{texto}» resolvió a {eps!r}. Si no es el canónico que ya usaba el "
            "motor, el contrato se busca con un nombre que la malla no conoce."
        )


class TestLosOtrosRegimenesEspeciales:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("POLICIA NACIONAL AU0101 $300.000", "POLICIA NACIONAL"),
            ("POLICÍA NACIONAL AU0101", "POLICIA NACIONAL"),
            ("FOMAG - MAGISTERIO SO0101", "FOMAG"),
            ("FIDUPREVISORA SO0101", "FOMAG"),
        ],
    )
    def test_se_detectan_en_el_texto(self, texto, esperado):
        eps, corrigio, _ = resolver_eps_efectiva("FAMISANAR EPS", texto)
        assert corrigio and eps == esperado, f"{texto} -> {eps!r}"

    def test_cada_uno_trae_su_propio_contrato(self):
        """Lo que hace grave el defecto no es el nombre: es el contrato."""
        contratos = {}
        for texto in ("DISPENSARIO MEDICO SO0101", "POLICIA NACIONAL SO0101", "FOMAG SO0101"):
            eps, _, _ = resolver_eps_efectiva("FAMISANAR EPS", texto)
            contratos[eps] = str(get_contrato(eps).get("numero") or "")
        assert len(set(contratos.values())) == 3, (
            f"Dos regímenes distintos comparten contrato: {contratos}"
        )
        for numero in contratos.values():
            assert "S-13-1-03-1-04958" not in numero


class TestLoQueYaFuncionabaSigueIgual:
    """Esta lista la usa todo el motor. Un cambio acá no puede alterar la
    resolución de las EPS que ya venían bien."""

    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("COOSALUD · Etapa: Inicial\nAU0201 $555.000", "COOSALUD"),
            ("COMPENSAR CO0601 $8.750.000", "COMPENSAR"),
            ("NUEVA EPS TA0301", "NUEVA EPS"),
            ("SALUD TOTAL SO0101", "SALUD TOTAL EPS"),
            ("ECOOPSOS FA0101", "ECOOPSOS"),
        ],
    )
    def test_las_eps_del_contributivo(self, texto, esperado):
        eps, _, _ = resolver_eps_efectiva("FAMISANAR EPS", texto)
        assert eps == esperado

    def test_cuando_coinciden_no_se_corrige_nada(self):
        eps, corrigio, _ = resolver_eps_efectiva("FAMISANAR EPS", "FAMISANAR EPS TA0201")
        assert not corrigio and eps == "FAMISANAR EPS"

    def test_sin_entidad_en_el_texto_manda_el_desplegable(self):
        """No se puede inventar una entidad donde el texto no nombra ninguna."""
        eps, corrigio, _ = resolver_eps_efectiva("FAMISANAR EPS", "TA0201 $185.000 CONSULTA")
        assert not corrigio and eps == "FAMISANAR EPS"
