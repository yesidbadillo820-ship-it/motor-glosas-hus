"""La cita que se atribuye a sí misma pasaba como verificada.

OT-019 · 06-08-2026. Glosa de sanción de COOSALUD. El dictamen entregado
decía:

    SE RECUERDA QUE “EL CONTRATO ESTABLECE QUE LAS SANCIONES POR
    INCUMPLIMIENTO SOLO PODRÁN APLICARSE CUANDO EXISTAN DISPOSICIONES
    CONTRACTUALES ESPECÍFICAS”.

Nadie había cargado ese contrato: la cita es inventada. Y el dictamen salió
con el sello «7 citas contra corpus · 0 hallazgos», que es peor que no
revisar — le dice al auditor que ya está verificado.

Dos huecos en el verificador:

  · la red de citas literales solo miraba comillas francesas «», y el motor
    escribió comillas tipográficas “”;
  · la red de citas atribuidas exige el verbo ANTES de las comillas, y aquí
    el sujeto normativo va DENTRO ("EL CONTRATO ESTABLECE QUE…").
"""

from __future__ import annotations

from app.services.citation_verifier import verificar_citas

CITA_COOSALUD = (
    "SE RECUERDA QUE “EL CONTRATO ESTABLECE QUE LAS SANCIONES POR INCUMPLIMIENTO "
    "SOLO PODRÁN APLICARSE CUANDO EXISTAN DISPOSICIONES CONTRACTUALES ESPECÍFICAS”."
)


def _falsas(dictamen: str, eps: str = "COOSALUD") -> list[dict]:
    return [
        i for i in verificar_citas(dictamen, eps=eps)["issues"] if i["tipo"] == "CITA_LITERAL_FALSA"
    ]


class TestElCasoReal:
    def test_la_cita_del_contrato_ya_se_marca(self):
        assert _falsas(CITA_COOSALUD), "la cita fabricada sigue pasando como verificada"

    def test_ya_no_se_entrega_con_cero_hallazgos(self):
        r = verificar_citas(CITA_COOSALUD, eps="COOSALUD")
        assert r["total_citas"] >= 1
        assert r["ok"] < r["total_citas"]


class TestOtrosSujetosNormativos:
    def test_clausula(self):
        d = (
            "SEGÚN “LA CLÁUSULA CUARTA DEL CONTRATO OBLIGA AL PAGADOR A RECONOCER LA "
            "FACTURA DENTRO DE LOS VEINTIDÓS DÍAS HÁBILES SIGUIENTES”."
        )
        assert _falsas(d)

    def test_resolucion(self):
        d = (
            "ASÍ, “LA RESOLUCIÓN 9999 DE 2030 ORDENA EL PAGO INMEDIATO DE TODA FACTURA "
            "RADICADA POR CUALQUIER PRESTADOR SIN EXCEPCIÓN ALGUNA”."
        )
        assert _falsas(d)

    def test_comillas_francesas_siguen_funcionando(self):
        d = (
            "«EL CONTRATO ESTABLECE QUE LAS SANCIONES POR INCUMPLIMIENTO SOLO PODRÁN "
            "APLICARSE CUANDO EXISTAN DISPOSICIONES CONTRACTUALES ESPECÍFICAS»."
        )
        assert _falsas(d)


class TestNoSeMarcaDeMas:
    def test_una_cita_corta_del_texto_de_la_glosa(self):
        d = "LA ENTIDAD DICE “no se evidencia epicrisis” EN SU OBJECIÓN."
        assert not _falsas(d)

    def test_una_afirmacion_sin_comillas(self):
        d = (
            "EL CONTRATO ESTABLECE QUE LAS SANCIONES SOLO PODRÁN APLICARSE CUANDO "
            "EXISTAN DISPOSICIONES CONTRACTUALES ESPECÍFICAS."
        )
        assert not _falsas(d)

    def test_una_cita_que_no_arranca_con_sujeto_normativo(self):
        d = "EL AUDITOR ANOTÓ “se solicita revisar el detallado de la factura del mes”."
        assert not _falsas(d)

    def test_dictamen_sin_citas(self):
        d = "ESE HUS NO ACEPTA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
        r = verificar_citas(d, eps="COOSALUD")
        assert not [i for i in r["issues"] if i["tipo"] == "CITA_LITERAL_FALSA"]

    def test_texto_vacio(self):
        r = verificar_citas("", eps="COOSALUD")
        assert r["total_citas"] == 0


class TestLosVerbosQueFaltaban:
    def test_se_recuerda_que(self):
        d = (
            "SE RECUERDA QUE “LAS SANCIONES POR INCUMPLIMIENTO SOLO PODRÁN APLICARSE "
            "CUANDO EXISTAN DISPOSICIONES CONTRACTUALES ESPECÍFICAS Y PREVIAS”."
        )
        assert _falsas(d)

    def test_estipula_y_pacta(self):
        for verbo in ("ESTIPULA", "PACTA", "CONTEMPLA", "DETERMINA"):
            d = (
                f"EL ACUERDO {verbo} QUE “EL PAGADOR RECONOCERÁ LA FACTURA DENTRO DE LOS "
                "VEINTIDÓS DÍAS HÁBILES SIGUIENTES A SU RADICACIÓN EN DEBIDA FORMA”."
            )
            assert _falsas(d), verbo
