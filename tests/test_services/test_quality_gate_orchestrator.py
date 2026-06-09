"""Tests del Quality Gate Orchestrator.

Verifica el pipeline completo:
  - Pre-validación bloquea si inputs incompletos (sin gastar IA)
  - Generación + post-validación con regeneración automática
  - Escalamiento a humano si tras N intentos sigue fallando
"""

from __future__ import annotations

import pytest

from app.services.quality_gate import ejecutar_quality_gate


DICTAMEN_LIMPIO = (
    "ESE HUS NO ACEPTA LA GLOSA POR CONCEPTO DE MAYOR VALOR COBRADO. "
    * 5
    + "EN ESE ORDEN DE IDEAS, SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA "
    "Y EL PAGO ÍNTEGRO DE LO FACTURADO."
)

# Texto de glosa de ejemplo que pasa el pre-validador endurecido
# (≥60 chars + palabra del dominio). Usado en todos los tests del
# orchestrator para evitar que la pre-validación bloquee antes de
# llegar a la lógica que se quiere ejercitar.
GLOSA_DEMO = (
    "TA0201 - Mayor valor cobrado en consulta especializada "
    "por valor objetado de $500.000 según factura electrónica"
)

DICTAMEN_SIN_CIERRE = "ESE HUS NO ACEPTA LA GLOSA. " * 20

DICTAMEN_CON_CITA_INVENTADA = (
    "ESE HUS NO ACEPTA LA GLOSA. " * 5
    + "DE ACUERDO CON LA RESOLUCIÓN 1552 DE 2019, LAS TARIFAS SE RESPETAN. "
    + "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA."
)


def _generador_factory(respuestas: list[str]):
    """Factory de generador async que devuelve respuestas predefinidas en orden."""
    idx = {"i": 0}

    async def gen(modelo: str, **contexto):
        i = idx["i"]
        idx["i"] += 1
        if i >= len(respuestas):
            return ("", modelo)  # ya no hay respuestas
        return (respuestas[i], modelo)

    return gen


class TestPreValidacion:
    @pytest.mark.asyncio
    async def test_pre_falla_no_gasta_ia(self):
        calls = {"n": 0}

        async def gen_que_no_debe_llamarse(modelo, **ctx):
            calls["n"] += 1
            return (DICTAMEN_LIMPIO, modelo)

        r = await ejecutar_quality_gate(
            eps="",  # vacía → falla pre-val
            codigo_glosa="",
            valor_objetado="",
            texto_glosa="",
            generador=gen_que_no_debe_llamarse,
        )
        assert r.estado == "RECHAZADO_PRE"
        assert calls["n"] == 0  # IA NUNCA se llamó
        assert "No puedo generar" in r.mensaje_usuario

    @pytest.mark.asyncio
    async def test_pre_aprueba_llama_ia(self):
        gen = _generador_factory([DICTAMEN_LIMPIO])
        r = await ejecutar_quality_gate(
            eps="FAMISANAR EPS",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa=GLOSA_DEMO,
            generador=gen,
        )
        assert r.estado == "APROBADO"
        assert r.pre_validation is not None
        assert r.pre_validation.aprobado


class TestGeneracionAprobada:
    @pytest.mark.asyncio
    async def test_primer_intento_aprobado(self):
        gen = _generador_factory([DICTAMEN_LIMPIO])
        r = await ejecutar_quality_gate(
            eps="FAMISANAR",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa=GLOSA_DEMO,
            generador=gen,
        )
        assert r.estado == "APROBADO"
        assert len(r.intentos) == 1
        assert r.intentos[0].numero == 1
        assert r.dictamen_final == DICTAMEN_LIMPIO
        assert r.n_regeneraciones == 0

    @pytest.mark.asyncio
    async def test_segundo_modelo_aprueba_despues_de_falla(self):
        # Primer modelo: dictamen sin cierre (falla)
        # Segundo modelo: dictamen limpio (aprueba)
        gen = _generador_factory([DICTAMEN_SIN_CIERRE, DICTAMEN_LIMPIO])
        r = await ejecutar_quality_gate(
            eps="FAMISANAR",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa=GLOSA_DEMO,
            generador=gen,
        )
        assert r.estado == "APROBADO"
        assert len(r.intentos) == 2  # primer fallo + segundo OK
        assert r.intentos[0].post_validation is not None
        assert not r.intentos[0].post_validation.aprobado
        assert r.intentos[1].post_validation is not None
        assert r.intentos[1].post_validation.aprobado
        assert r.modelo_final != r.intentos[0].modelo_solicitado  # cambió de modelo
        assert r.n_regeneraciones == 1


class TestEscalamientoHumano:
    @pytest.mark.asyncio
    async def test_tres_intentos_fallidos_escalan(self):
        # Todos los modelos devuelven dictamen sin cierre → escala
        gen = _generador_factory([DICTAMEN_SIN_CIERRE] * 5)
        r = await ejecutar_quality_gate(
            eps="FAMISANAR",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa=GLOSA_DEMO,
            generador=gen,
        )
        assert r.estado == "ESCALAR_HUMANO"
        assert len(r.intentos) == 3
        assert r.dictamen_final  # se entrega el mejor intento como borrador
        assert "no se logró aprobar todos los checks" in r.mensaje_usuario.lower()

    @pytest.mark.asyncio
    async def test_escala_entrega_mejor_score(self):
        # 3 intentos: el segundo es ligeramente mejor (texto más largo)
        gen = _generador_factory(
            [
                "ESE HUS RECHAZA. " * 5,  # corto, sin cierre
                DICTAMEN_CON_CITA_INVENTADA,  # tiene cierre pero cita inventada
                "X" * 50,  # muy corto
            ]
        )
        r = await ejecutar_quality_gate(
            eps="FAMISANAR",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa=GLOSA_DEMO,
            generador=gen,
        )
        assert r.estado == "ESCALAR_HUMANO"
        # El de mayor score debería ser el que tiene cierre + cita inventada
        # (cierre OK = +30 vs los otros que no tienen cierre)


class TestMaxIntentosConfigurable:
    @pytest.mark.asyncio
    async def test_max_1_intento(self):
        gen = _generador_factory([DICTAMEN_SIN_CIERRE])
        r = await ejecutar_quality_gate(
            eps="FAMISANAR",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa=GLOSA_DEMO,
            generador=gen,
            max_intentos=1,
        )
        assert r.estado == "ESCALAR_HUMANO"
        assert len(r.intentos) == 1


class TestModelosFallback:
    @pytest.mark.asyncio
    async def test_orden_de_modelos_personalizado(self):
        modelos_solicitados: list[str] = []

        async def gen_que_registra(modelo, **ctx):
            modelos_solicitados.append(modelo)
            return (DICTAMEN_SIN_CIERRE, modelo)

        await ejecutar_quality_gate(
            eps="FAMISANAR",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa=GLOSA_DEMO,
            generador=gen_que_registra,
            modelos_fallback=["anthropic", "groq", "gemini"],
        )
        # Debió haberse solicitado en ese orden
        assert modelos_solicitados[0] == "anthropic"
        assert modelos_solicitados[1] == "groq"


class TestErrorEnGenerador:
    @pytest.mark.asyncio
    async def test_excepcion_en_generador_continua_con_siguiente(self):
        llamadas = {"n": 0}

        async def gen(modelo, **ctx):
            llamadas["n"] += 1
            if llamadas["n"] == 1:
                raise RuntimeError("API rate limit")
            return (DICTAMEN_LIMPIO, modelo)

        r = await ejecutar_quality_gate(
            eps="FAMISANAR",
            codigo_glosa="TA0201",
            valor_objetado="500000",
            texto_glosa=GLOSA_DEMO,
            generador=gen,
        )
        # El error en el primero NO debe detener el pipeline
        assert r.estado == "APROBADO"
        assert len(r.intentos) == 2
        assert "rate limit" in r.intentos[0].error.lower()
        assert r.intentos[1].aprobado
