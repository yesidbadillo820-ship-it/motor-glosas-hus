"""Los tres defectos que destaparon las pruebas de estrés ST-01 a ST-05.

31-08-2026. Cinco casos corridos en el motor del hospital: **cuatro dictámenes
NO APTOS**. De ahí salieron tres defectos, cada uno con su causa raíz.

DEFECTO 1 — EL MOTOR DEFENDÍA EL VALOR FACTURADO, NO EL GLOSADO
Salió en las CINCO pruebas. Con esta glosa:

    VALOR FACTURADO: $3.870.000  VALOR GLOSADO: $1.980.000

el dictamen decía «VALOR OBJETADO $3.870.000». El hospital discutía casi el
doble de lo que le glosaron, y esa desproporción se la tumba cualquier auditor.

CAUSA: `_extraer_valor` solo conocía la palabra «objetado». «GLOSADO» —que es
la que usan las EPS y la que trae la columna VALOR_GLOSADO de los archivos del
ADRES— no estaba, así que el valor caía a los patrones genéricos, que toman el
PRIMER número con «$». En el formato normal de una glosa, el primero es el
facturado.

DEFECTO 2 — «TARIFA PACTADA: SOAT PLENO» SOBRE CONTRATOS QUE PACTABAN −20 %
Salió en NUEVA EPS y en DISPENSARIO MEDICO.

CAUSA: no era que el motor ignorara la tarifa. Los dos contratos EXISTEN y
pactan factor 0.8 — pero **están vencidos** (NUEVA EPS el 2026-03-31, el
440-DIGSA el 2026-07-30). Como la glosa no trae fecha del servicio, el motor
asume hoy, concluye que no hay contrato vigente y cae al fallback de SOAT
pleno. Ese camino YA avisaba que el contrato venció, pero dejaba la línea
«Tarifa pactada: SOAT PLENO» como una afirmación positiva sobre algo que en
ese punto justamente NO se sabe. En una glosa de TARIFA eso le concede a la
entidad justo lo que objetó.

EL FACTOR NO SE TOCÓ: sigue en 1.00 a propósito. Aplicar un descuento pactado
sin saber la fecha también sería inventar, y de los dos errores ese es el que
le cuesta plata al hospital. Lo que se corrigió es la afirmación.

DEFECTO 3 — EL GUARDIÁN DE SOPORTES ERA TODO O NADA
Salió en ST-04: se adjuntaron kardex y factura, y el dictamen escribió «LA
HISTORIA CLÍNICA INTEGRAL Y LOS RIPS RADICADOS SE ENCUENTRAN ADJUNTOS».

CAUSA: el control solo miraba si había CERO soportes. Bastaba adjuntar uno
para que el dictamen pudiera afirmar contenido de cualquier otro documento.
Ahora se compara POR TIPO.
"""

from __future__ import annotations

import datetime as dt

import pytest

from app.services.glosa_ia_prompts import get_contrato
from app.services.glosa_service import GlosaService, _familias_afirmadas_sin_respaldo


@pytest.fixture(scope="module")
def svc() -> GlosaService:
    return GlosaService.__new__(GlosaService)


class TestElValorQueSeDefiendeEsElGlosado:
    @pytest.mark.parametrize(
        "texto,esperado",
        [
            ("VALOR FACTURADO: $3.870.000  VALOR GLOSADO: $1.980.000", "$ 1.980.000"),
            ("VALOR FACTURADO: $4.180.000  VALOR GLOSADO: $1.254.000", "$ 1.254.000"),
            ("VALOR FACTURADO: $18.940.000  VALOR GLOSADO: $7.310.000", "$ 7.310.000"),
            ("VR GLOSADO 250.000 VALOR FACTURADO 900.000", "$ 250.000"),
            ("VLR. GLOSADA: 480.000 · VALOR FACTURADO: 1.200.000", "$ 480.000"),
            ("VALOR NO CONCILIADO: $77.000 VALOR FACTURADO $300.000", "$ 77.000"),
            ("VALOR RECHAZADO: 55.000 VALOR COBRADO 210.000", "$ 55.000"),
        ],
    )
    def test_gana_el_glosado_sobre_el_facturado(self, svc, texto, esperado):
        assert svc._extraer_valor(texto) == esperado

    def test_el_objetado_sigue_funcionando(self, svc):
        """Lo que ya andaba no se puede romper."""
        assert svc._extraer_valor("VALOR OBJETADO: $500.000") == "$ 500.000"
        assert svc._extraer_valor("TOTAL OBJETADO $1.100.000") == "$ 1.100.000"

    def test_iguales_no_es_un_problema(self, svc):
        """Regresión: facturado y glosado con el mismo número."""
        assert svc._extraer_valor("VALOR FACTURADO: $960.000  VALOR GLOSADO: $960.000") == (
            "$ 960.000"
        )

    def test_solo_facturado_sigue_devolviendo_ese_valor(self, svc):
        """Si la glosa NO dice cuánto objetó, el único número que hay es el
        que hay. No se puede devolver cero ni inventar otro."""
        assert svc._extraer_valor("VALOR FACTURADO: $700.000") == "$ 700.000"

    def test_un_solo_valor_suelto(self, svc):
        assert svc._extraer_valor("SE GLOSA POR $150.000") == "$ 150.000"

    def test_sin_ningun_valor(self, svc):
        assert svc._extraer_valor("NO SE ACEPTA LA GLOSA") == "$ 0.00"


class TestLaTarifaNoSeAfirmaCuandoNoSeSabe:
    """Cuatro escenarios distintos, ninguno con el nombre de una entidad
    metido en el código: todos salen de la malla contractual."""

    @pytest.mark.parametrize("eps", ["NUEVA EPS", "DISPENSARIO MEDICO"])
    def test_contrato_vencido_y_sin_fecha_no_afirma_tarifa(self, eps):
        c = get_contrato(eps)
        assert c.get("_tarifa_indeterminada") is True
        assert "NO DETERMINADA" in c["tarifa"].upper()

    @pytest.mark.parametrize("eps", ["NUEVA EPS", "DISPENSARIO MEDICO"])
    def test_dice_que_factor_pactaba_el_contrato_vencido(self, eps):
        """El gestor tiene que ver qué está en juego."""
        assert "factor 0.80" in get_contrato(eps)["tarifa"]

    @pytest.mark.parametrize("eps", ["NUEVA EPS", "DISPENSARIO MEDICO"])
    def test_pide_confirmar_la_fecha(self, eps):
        assert "FECHA DE PRESTACIÓN" in get_contrato(eps)["tarifa"].upper()

    @pytest.mark.parametrize(
        "eps,fecha,factor",
        [
            ("NUEVA EPS", dt.date(2026, 3, 15), 0.8),
            ("DISPENSARIO MEDICO", dt.date(2026, 3, 15), 0.8),
        ],
    )
    def test_con_fecha_dentro_de_vigencia_aplica_el_pactado(self, eps, fecha, factor):
        c = get_contrato(eps, fecha)
        assert c["factor"] == factor
        assert not c.get("_tarifa_indeterminada")

    def test_contrato_vigente_conserva_su_tarifa(self):
        """Regresión: una entidad con contrato al día no se ve afectada."""
        c = get_contrato("FAMISANAR EPS")
        assert c["factor"] == 0.95
        assert not c.get("_tarifa_indeterminada")

    def test_sin_contrato_de_verdad_si_es_soat_pleno(self):
        """SOAT pleno legítimo: no hay contrato ni vencido ni vigente."""
        c = get_contrato("OTRA / SIN DEFINIR")
        assert c["factor"] == 1.00
        assert "SOAT PLENO" in c["tarifa"].upper()
        assert not c.get("_tarifa_indeterminada")

    def test_el_factor_no_se_toco(self):
        """Decisión deliberada: sin fecha no se aplica un descuento pactado.
        Aplicarlo de más también sería inventar, y ese error cuesta plata."""
        assert get_contrato("DISPENSARIO MEDICO")["factor"] == 1.00


class TestNoSePuedeAfirmarUnDocumentoQueNoLlego:
    KARDEX = "KARDEX DE ADMINISTRACION DE MEDICAMENTOS · MEROPENEM 1 g IV · aplicado"
    HC = "HISTORIA CLINICA - URGENCIAS · MOTIVO DE CONSULTA · EXAMEN FISICO"
    RX = "INFORME DE RADIOLOGIA · TOMOGRAFIA DE ABDOMEN"

    def test_el_caso_st04_tal_como_salio(self):
        """Adjuntaron kardex y factura; el dictamen afirmó HC y RIPS."""
        d = (
            "EL KARDEX REGISTRA 15 DOSIS Y EL HISTORIAL MEDICO CONFIRMA LA SUSPENSION. "
            "LOS RIPS RADICADOS SE ENCUENTRAN ADJUNTOS."
        )
        assert set(_familias_afirmadas_sin_respaldo(d, self.KARDEX)) == {"historia clínica", "RIPS"}

    def test_sin_ningun_adjunto(self):
        d = "LA HISTORIA CLINICA REGISTRA DOLOR ABDOMINAL AGUDO."
        assert _familias_afirmadas_sin_respaldo(d, "") == ["historia clínica"]

    def test_con_la_historia_clinica_adjunta_no_avisa(self):
        d = "LA HISTORIA CLINICA REGISTRA DOLOR ABDOMINAL AGUDO."
        assert _familias_afirmadas_sin_respaldo(d, self.HC) == []

    def test_con_radiologia_adjunta_no_avisa(self):
        d = "EL INFORME DE RADIOLOGIA INDICA FRACTURA DIAFISARIA."
        assert _familias_afirmadas_sin_respaldo(d, self.RX) == []

    def test_varios_soportes_cubren_varias_afirmaciones(self):
        d = "LA HISTORIA CLINICA REGISTRA EL INGRESO Y EL INFORME DE RADIOLOGIA INDICA LA FRACTURA."
        assert _familias_afirmadas_sin_respaldo(d, self.HC + " " + self.RX) == []

    def test_un_documento_que_no_es_clinico_no_respalda_nada(self):
        """Adjuntar una factura no autoriza a hablar de la historia clínica."""
        d = "LA HISTORIA CLINICA REGISTRA DOLOR ABDOMINAL."
        factura = "FACTURA DE VENTA · NUMERO HUS0000602741 · TOTAL $3.870.000"
        assert _familias_afirmadas_sin_respaldo(d, factura) == ["historia clínica"]

    def test_la_afirmacion_juridica_general_es_legitima(self):
        """«La historia clínica constituye prueba» NO implica haberla leído.
        Es la distinción que separa un aviso útil de uno que nadie leerá."""
        d = (
            "LA HISTORIA CLINICA CONSTITUYE PRUEBA DOCUMENTAL CONFORME A LA "
            "RESOLUCION 1995 DE 1999."
        )
        assert _familias_afirmadas_sin_respaldo(d, "") == []

    def test_dictamen_vacio_no_revienta(self):
        assert _familias_afirmadas_sin_respaldo("", "") == []


class TestElNombreDelPagadorConPuntos:
    """DEFECTO ADICIONAL, encontrado al re-verificar los cinco casos.

    En la base del hospital NUEVA EPS aparece escrita «NUEVA E.P.S. S.A. -
    SUBSIDIADO» — es el pagador más frecuente del lote de 135 glosas. Como la
    malla compara por PALABRA COMPLETA, «E.P.S.» nunca era «EPS» y esa entidad
    se quedaba **sin ningún contrato**: el motor la trataba como si nunca
    hubiera existido relación contractual y liquidaba a SOAT pleno, sin avisar
    siquiera que había un contrato de por medio.

    Es el mismo daño que el contrato vencido, pero peor: ahí al menos avisaba.
    """

    from app.services import malla_contractual as _m

    @pytest.mark.parametrize(
        "nombre",
        [
            "NUEVA E.P.S. S.A. - SUBSIDIADO",
            "NUEVA E.P.S. S.A. - SUBSIDIADO SERVICIOS AMBULATORIOS",
            "NUEVA EPS",
            "nueva e.p.s. s.a.",
        ],
    )
    def test_encuentra_el_contrato_aunque_venga_con_puntos(self, nombre):
        assert len(self._m.contratos_de(nombre)) == 1

    @pytest.mark.parametrize("nombre", ["NUEVA E.P.S. S.A. - SUBSIDIADO", "NUEVA EPS"])
    def test_y_le_aplica_el_factor_pactado(self, nombre):
        assert get_contrato(nombre, dt.date(2026, 3, 15))["factor"] == 0.8

    def test_no_se_aflojo_el_guardian_de_falsos_positivos(self):
        """Regresión que importa: «AURORA» no puede engancharse dentro de
        «CLINICA LAURORA IPS». Arreglar los puntos no puede abrir esa puerta."""
        assert self._m.contratos_de("CLINICA LAURORA IPS") == []

    def test_una_entidad_desconocida_sigue_sin_contrato(self):
        assert self._m.contratos_de("IPS QUE NO EXISTE S.A.S.") == []
