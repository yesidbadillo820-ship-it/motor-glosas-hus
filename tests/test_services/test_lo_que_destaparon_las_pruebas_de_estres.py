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

from app.services.glosa_ia_prompts import get_contrato, resolver_eps_efectiva
from app.services.glosa_service import (
    GlosaService,
    _familias_afirmadas_sin_respaldo,
    generar_texto_injustificada,
)


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


class TestLaAseguradoraSoatNoEsElMagisterio:
    """Defecto encontrado corriendo la prueba 1 con el auditor.

    «LA PREVISORA» es alias de FOMAG en la malla, y con razón: La Previsora
    administra el Fondo del Magisterio. Pero LA MISMA COMPAÑÍA es también una
    aseguradora SOAT, y ahí es otro pagador y otro régimen.

    Resultado: «LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB» recibía el
    contrato de FOMAG (factor 0.85, SOAT −15 %) cuando una reclamación SOAT se
    liquida a tarifa plena. Es darle a una glosa el contrato de otra entidad, y
    pega donde más duele: en el export real de la base ese pagador es **el que
    más glosas tiene** — 32 de 135.

    La regla es de RÉGIMEN, no de nombre propio: si el pagador se identifica a
    sí mismo como SOAT, ningún alias puede llevarlo a un contrato que no lo sea.
    """

    from app.services import malla_contractual as _m

    @pytest.mark.parametrize(
        "pagador",
        [
            "LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB",
            "ASEGURADORA SOLIDARIA SOAT UVB",
            "SEGUROS DEL ESTADO SOAT",
        ],
    )
    def test_un_pagador_soat_no_hereda_un_contrato_que_no_lo_es(self, pagador):
        assert self._m.contratos_de(pagador) == []

    @pytest.mark.parametrize(
        "pagador",
        ["LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB", "ASEGURADORA SOLIDARIA SOAT UVB"],
    )
    def test_y_se_liquida_a_soat_pleno(self, pagador):
        assert get_contrato(pagador)["factor"] == 1.00

    def test_la_previsora_a_secas_sigue_siendo_fomag(self):
        """Regresión: el alias legítimo no se puede perder."""
        assert [c.pagador for c in self._m.contratos_de("LA PREVISORA")] == ["FOMAG"]
        assert get_contrato("LA PREVISORA")["factor"] == 0.85

    def test_fomag_sigue_igual(self):
        assert get_contrato("FOMAG")["factor"] == 0.85

    @pytest.mark.parametrize("pagador,factor", [("FAMISANAR EPS", 0.95), ("NUEVA EPS", 1.00)])
    def test_los_demas_pagadores_no_se_movieron(self, pagador, factor):
        assert get_contrato(pagador)["factor"] == factor


class TestLaEpsSeSacaDelTextoDeLaGlosa:
    """El auditor lo pidió corriendo la prueba 1: «la IA debe identificar la
    EPS automáticamente», y tiene razón — el nombre está escrito en la primera
    línea de la glosa.

    Ya existía la función que lo hace, pero el token del catálogo es «NUEVA
    EPS» y las glosas reales escriben «NUEVA E.P.S. S.A. - SUBSIDIADO». Con los
    puntos no enganchaba, así que el pagador MÁS FRECUENTE de la base quedaba
    en «OTRA / SIN DEFINIR»: sin contrato, sin tarifa y con el aviso de entidad
    sin identificar.
    """

    @pytest.mark.parametrize(
        "escrito,canonico",
        [
            ("NUEVA E.P.S. S.A. - SUBSIDIADO", "NUEVA EPS"),
            ("NUEVA E.P.S. S.A. - SUBSIDIADO SERVICIOS AMBULATORIOS", "NUEVA EPS"),
            ("NUEVA EPS", "NUEVA EPS"),
            ("FAMISANAR EPS", "FAMISANAR"),
            ("COOSALUD", "COOSALUD"),
        ],
    )
    def test_la_reconoce_en_el_encabezado_de_la_glosa(self, escrito, canonico):
        texto = f"AU0201 | HUS0000601447 | {escrito}\nSERVICIO SIN AUTORIZACION."
        assert resolver_eps_efectiva("OTRA / SIN DEFINIR", texto)[0] == canonico

    def test_si_no_reconoce_ninguna_deja_lo_que_habia(self):
        """No inventar: mejor «sin definir» con su aviso que una EPS adivinada."""
        texto = "AU0201 | HUS1 | ENTIDAD QUE NO ESTA EN NINGUN CATALOGO S.A.S."
        assert resolver_eps_efectiva("OTRA / SIN DEFINIR", texto)[0] == "OTRA / SIN DEFINIR"

    def test_no_pisa_una_eps_ya_escogida_si_coincide(self):
        texto = "AU0201 | HUS1 | FAMISANAR EPS"
        eps, hubo, _ = resolver_eps_efectiva("FAMISANAR EPS", texto)
        assert eps == "FAMISANAR EPS" and hubo is False


class TestNoLlamarFacturadoAlValorObjetado:
    """Defecto que salió al corregir el anterior — y solo por eso.

    Mientras el motor confundía facturado con glosado, la plantilla de tarifas
    decía «FACTURADA POR {valor}» y la etiqueta coincidía por accidente. Al
    corregir el valor, el número pasó a ser el objetado y la palabra quedó
    mintiendo: el dictamen decía «FACTURADA POR $1.254.000» cuando la factura
    era de $4.180.000.

    Lo vio el auditor en la tercera corrida de la prueba TA0301, en producción.

    Un dictamen que le dice a la entidad un valor facturado que no es el de la
    factura se cae solo: ella tiene la factura.
    """

    def test_el_valor_va_rotulado_como_objetado(self):
        t = generar_texto_injustificada(
            eps="OTRA / SIN DEFINIR", codigo="TA0301", valor="$ 1.254.000"
        )
        assert "POR VALOR OBJETADO DE $ 1.254.000" in t

    def test_ya_no_lo_llama_facturado(self):
        t = generar_texto_injustificada(
            eps="OTRA / SIN DEFINIR", codigo="TA0301", valor="$ 1.254.000"
        )
        assert "FACTURADA POR" not in t

    def test_sin_valor_no_inventa_una_cifra(self):
        """Regresión: el texto de respaldo cuando la glosa no trae valor."""
        t = generar_texto_injustificada(eps="OTRA / SIN DEFINIR", codigo="TA0301", valor="")
        assert "EL VALOR INDICADO EN EL EXPEDIENTE" in t

    def test_el_resto_del_argumento_sigue_intacto(self):
        """No se puede perder el fundamento por arreglar una etiqueta."""
        t = generar_texto_injustificada(
            eps="OTRA / SIN DEFINIR", codigo="TA0301", valor="$ 1.254.000"
        )
        for pieza in (
            "NO EXISTE CONTRATO PACTADO",
            "CIRCULAR EXTERNA 047 DE 2025",
            "DECRETO 780 DE 2016",
            "ARTÍCULO 871",
        ):
            assert pieza in t, pieza


class TestLasAseguradorasSoatSeDetectanSolas:
    """El auditor confirmó el nombre oficial: «LA PREVISORA S.A.».

    LA PARTE DELICADA, y por eso queda escrita: La Previsora S.A. es LA MISMA
    EMPRESA que administra el Fondo del Magisterio, y por eso la malla la tiene
    como alias de FOMAG. El nombre solo NO distingue si la glosa es del
    magisterio o de SOAT — eso lo dice el «SOAT» o el «UVB» del propio texto.

    Por eso el nombre canónico CONSERVA el marcador SOAT. Si devolviera «LA
    PREVISORA S.A.» a secas, la malla le daría el contrato de FOMAG (factor
    0.85) y volveríamos al defecto corregido esta misma tarde.
    """

    @pytest.mark.parametrize(
        "escrito,esperado",
        [
            ("LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB", "LA PREVISORA S.A. — SOAT"),
            ("LA PREVISORA S.A. SOAT UVB", "LA PREVISORA S.A. — SOAT"),
            ("ASEGURADORA SOLIDARIA SOAT UVB", "ASEGURADORA SOLIDARIA — SOAT"),
            ("SEGUROS DEL ESTADO SOAT", "SEGUROS DEL ESTADO — SOAT"),
            ("COMPAÑIA MUNDIAL DE SEGUROS S.A. SOAT UVB", "COMPAÑIA MUNDIAL DE SEGUROS — SOAT"),
        ],
    )
    def test_las_reconoce_en_el_texto(self, escrito, esperado):
        texto = f"TA0301 | HUS0000601447 | {escrito}\nMAYOR VALOR COBRADO."
        assert resolver_eps_efectiva("OTRA / SIN DEFINIR", texto)[0] == esperado

    @pytest.mark.parametrize(
        "escrito",
        [
            "LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB",
            "LA PREVISORA S.A. SOAT UVB",
            "ASEGURADORA SOLIDARIA SOAT UVB",
        ],
    )
    def test_y_liquidan_a_soat_pleno_no_al_0_85_de_fomag(self, escrito):
        """La cadena completa: detección → contrato → factor. Es donde estaba
        el defecto y donde tiene que quedar comprobado."""
        det = resolver_eps_efectiva("OTRA / SIN DEFINIR", f"TA0301 | HUS1 | {escrito}")[0]
        assert get_contrato(det)["factor"] == 1.00

    def test_el_canonico_conserva_el_marcador_soat(self):
        """Sin el marcador, la malla le devolvería el contrato de FOMAG."""
        det = resolver_eps_efectiva(
            "OTRA / SIN DEFINIR", "TA0301 | HUS1 | LA PREVISORA S.A. SOAT UVB"
        )[0]
        assert "SOAT" in det

    @pytest.mark.parametrize("texto", ["FIDUCIARIA PREVISORA FOMAG", "MAGISTERIO"])
    def test_el_magisterio_manda_sobre_el_nombre_de_la_compania(self, texto):
        """La Previsora S.A. es la MISMA empresa que administra el FOMAG.

        Primer intento de este arreglo: se metió «PREVISORA» como token suelto
        y se tragó «FIDUCIARIA PREVISORA FOMAG», que es magisterio puro. Lo
        atajó una prueba de la ronda 13 que existe desde junio.

        La regla pide LAS DOS COSAS —nombre de compañía Y marcador SOAT— y
        cede ante el magisterio, que es más específico sobre el pagador que la
        palabra «SOAT», que puede estar ahí solo por la tarifa.
        """
        from app.services.glosa_ia_prompts import _detectar_pagador_en_texto

        assert _detectar_pagador_en_texto(texto) == "FOMAG"

    def test_el_nombre_de_la_compania_solo_no_basta(self):
        """Sin marcador SOAT no se puede afirmar de qué negocio viene."""
        from app.services.glosa_ia_prompts import _detectar_pagador_en_texto

        assert _detectar_pagador_en_texto("LA PREVISORA") == ""

    def test_fomag_a_secas_no_se_movio(self):
        """Regresión: el magisterio conserva su contrato y su factor."""
        assert get_contrato("FOMAG")["factor"] == 0.85

    def test_las_eps_normales_no_se_vieron_afectadas(self):
        for escrito, esperado in (
            ("NUEVA E.P.S. S.A. - SUBSIDIADO", "NUEVA EPS"),
            ("FAMISANAR EPS", "FAMISANAR"),
        ):
            det = resolver_eps_efectiva("OTRA / SIN DEFINIR", f"AU0201 | HUS1 | {escrito}")[0]
            assert det == esperado
