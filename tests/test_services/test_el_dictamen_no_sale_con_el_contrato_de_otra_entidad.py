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
            # «SANIDAD MILITAR» a secas se retiró el mismo día que se agregó.
            # No es un nombre: es un régimen, y aparece en prosa corriente
            # («cotización avalada por sanidad militar»). En una glosa real del
            # auditor hizo que el motor «corrigiera» una entidad que ya estaba
            # bien elegida, y con otro desplegable habría respondido una glosa
            # de FAMISANAR con el contrato del Dispensario. Ver
            # TestLaMismaEntidadConDosNombresNoEsContradiccion, abajo.
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


class TestLaMismaEntidadConDosNombresNoEsContradiccion:
    """Regresión introducida y corregida el mismo día, 09-09-2026.

    Al agregar los regímenes especiales a la lista de pagadores, dos análisis
    de la MISMA factura del auditor salieron con la entidad escrita distinto:
    uno dijo «DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA»
    y el otro «DMBUG», con un aviso amarillo de «entidad pagadora corregida»
    que no corregía nada.

    Dos causas, las dos mías:

    **1 · Se comparaban los nombres tal cual.** El desplegable traía el
    nombre oficial largo y el catálogo devuelve la sigla: no comparten ni una
    letra seguida, así que el motor los daba por entidades distintas. Ahora se
    comparan por el nombre canónico, que es lo que de verdad decide qué
    contrato se carga.

    **2 · «SANIDAD MILITAR» era un token demasiado suelto.** La glosa decía
    «cotización avalada por SANIDAD MILITAR» — eso describe quién debe avalar,
    no nombra al pagador. Con ese token, una glosa de FAMISANAR que mencionara
    el término se habría respondido con el contrato del Dispensario.
    """

    CASO_REAL = (
        "SO4201 - Existe ausencia total, parcial o inconsistencia de la lista de "
        "precios - CUPS FMQ6276 - MICROGUÍA CON PUNTA 0,10 - SE OBJETA MATERIAL DE "
        "PROCEDIMIENTO NO SE EVIDENCIA FRA DE COMPRA Y COTIZACION AVALADA POR "
        "SANIDAD MILITAR PARA SU RESPECTIVO COBRO."
    )
    NOMBRE_LARGO = "DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA"

    def test_no_se_corrige_lo_que_ya_estaba_bien(self):
        eps, corrigio, _ = resolver_eps_efectiva(self.NOMBRE_LARGO, self.CASO_REAL)
        assert not corrigio, (
            "Avisa de una «corrección» sobre la entidad que el auditor ya había "
            "elegido bien. El aviso confunde y encima cambia el nombre claro "
            "del encabezado por la sigla."
        )

    def test_y_se_conserva_el_nombre_que_eligio_el_auditor(self):
        eps, _, _ = resolver_eps_efectiva(self.NOMBRE_LARGO, self.CASO_REAL)
        assert eps == self.NOMBRE_LARGO

    def test_dos_glosas_de_la_misma_factura_dan_la_misma_entidad(self):
        """Lo que lo destapó: dos análisis de HUS0000541440 salieron con la
        entidad escrita distinto según qué decía el texto de cada concepto."""
        otra = "FA0701 - ... - SE OBJETA MEDIO DE CONTRASTE UTILIZADO SEGUN NOTA OPERATORIA"
        a, _, _ = resolver_eps_efectiva(self.NOMBRE_LARGO, self.CASO_REAL)
        b, _, _ = resolver_eps_efectiva(self.NOMBRE_LARGO, otra)
        assert a == b, f"La misma factura resolvió a {a!r} y a {b!r}."

    def test_la_frase_suelta_no_secuestra_una_glosa_de_otra_eps(self):
        """El daño mayor que evitaba el token suelto: una glosa de FAMISANAR
        respondida con el contrato del Dispensario."""
        eps, corrigio, _ = resolver_eps_efectiva(
            "FAMISANAR EPS", "TA0201 cotización avalada por sanidad militar"
        )
        assert not corrigio and eps == "FAMISANAR EPS"

    def test_pero_el_Dispensario_de_verdad_sigue_detectandose(self):
        """El arreglo no puede deshacer lo que vino a arreglar."""
        eps, corrigio, _ = resolver_eps_efectiva("FAMISANAR EPS", "GLOSA DMBUG TA0801")
        assert corrigio and eps == "DMBUG"

    def test_y_una_contradiccion_de_verdad_se_sigue_avisando(self):
        eps, corrigio, _ = resolver_eps_efectiva("FAMISANAR EPS", "COOSALUD AU0201 $555.000")
        assert corrigio and eps == "COOSALUD"
