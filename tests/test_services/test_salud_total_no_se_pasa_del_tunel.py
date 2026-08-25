"""Salud Total: 44 glosas no pueden tumbar la petición (20-08-2026).

Una notificación de SALUD TOTAL trae **44 glosas**. Se analizaban de tres en
tres, con una espera de **120 segundos por glosa**… y el túnel por el que
entra el portal **corta a los ~100**.

O sea: la espera de UNA SOLA glosa ya era más larga que lo que aguanta la
conexión. La petición se caía con un 502 y se perdía todo el trabajo que la IA
ya había hecho — los tokens gastados incluidos —, sin que saliera ni un
archivo.

Lo que NO estaba mal, y por eso no se toca: cada fila sale SIEMPRE con
respuesta por plantilla aunque la IA falle. Eso ya estaba bien resuelto, y es
lo que impide el desastre de verdad — una fila vacía en el archivo que se
radica es una glosa sin responder, y una glosa sin responder se da por
aceptada: la plata se regala.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.config import espera_maxima
from app.services import salud_total_ia as st


class TestNingunaEsperaLeGanaAlTunel:
    def test_el_limite_por_glosa_cabe_en_el_tunel(self):
        assert st._limite_por_glosa() < 100

    def test_el_presupuesto_del_lote_tambien(self):
        assert st._presupuesto_del_lote() < 100

    def test_y_le_deja_margen_al_motor_para_contestar(self):
        """El presupuesto del lote es más corto que el de una glosa: al motor
        le queda tiempo de armar el Excel y devolverlo."""
        assert st._presupuesto_del_lote() < st._limite_por_glosa()

    def test_ya_no_hay_un_120_fijo_escrito_a_mano(self):
        import inspect

        fuente = inspect.getsource(st)
        assert "SEGUNDOS_LIMITE_POR_GLOSA = 120" not in fuente, (
            "Volvió la espera fija de 120 segundos, que es MÁS larga que el "
            "corte del túnel (~100 s): una sola glosa lenta tumba la petición."
        )

    def test_si_el_tunel_fuera_mas_generoso_se_aprovecha(self, monkeypatch):
        """El límite sale del corte real, no de un número inventado."""
        monkeypatch.setenv("TUNEL_CORTA_EN_SEGUNDOS", "600")
        assert espera_maxima(120) == 120


class _ServicioFalso:
    """Una IA de mentira: cada análisis tarda lo que se le diga."""

    # Un dictamen realista: el motor descarta —con razón— los argumentos
    # demasiado cortos, porque con 27 caracteres no se defiende nada.
    DICTAMEN = (
        "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE MAYOR VALOR COBRADO, "
        "DADO QUE EL VALOR FACTURADO CORRESPONDE EXACTAMENTE A LA TARIFA PACTADA "
        "ENTRE LAS PARTES PARA LA VIGENCIA DE LA ATENCIÓN. LA ENTIDAD PAGADORA NO "
        "APORTÓ PRUEBA DE UNA TARIFA DISTINTA. POR LO ANTERIOR SE SOLICITA EL "
        "LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO DE LO FACTURADO."
    )

    def __init__(self, tarda: float = 0.0, dictamen: str = ""):
        self.tarda = tarda
        self.dictamen = dictamen or self.DICTAMEN
        self.llamadas = 0

    async def analizar(self, entrada):
        self.llamadas += 1
        if self.tarda:
            await asyncio.sleep(self.tarda)

        class _R:
            pass

        r = _R()
        r.dictamen = self.dictamen
        r.codigo_respuesta = "RE9901"
        r.modelo_usado = "falso"
        return r


def _filas(cuantas: int) -> list[dict]:
    return [
        {
            "NUMREG": str(i),
            "FACTURA": f"HUS{i:07d}",
            "VALOR_GLOSA": "20000",
            "CODIGO_GLOSA": "TA2901",
            "DESCRIPCION": "MAYOR VALOR COBRADO",
        }
        for i in range(cuantas)
    ]


class TestCuandoSeAcabaElTiempo:
    @pytest.mark.asyncio
    async def test_las_que_faltan_salen_por_plantilla_y_no_vacias(self, monkeypatch):
        """Lo esencial: el archivo sale COMPLETO. Entre «todas con plantilla»
        y «ninguna porque se cayó la petición», la plantilla gana."""
        monkeypatch.setattr(st, "_presupuesto_del_lote", lambda: 0.0)
        servicio = _ServicioFalso()

        respuestas, resumen = await st.analizar_notificacion(_filas(44), servicio=servicio)

        assert len(respuestas) == 44, "el archivo tiene que salir completo"
        assert resumen["analizadas_con_ia"] == 0
        assert resumen["por_plantilla"] == 44
        assert servicio.llamadas == 0, "sin tiempo, no se le pide nada a la IA"

    @pytest.mark.asyncio
    async def test_se_reporta_cuantas_quedaron_por_falta_de_tiempo(self, monkeypatch):
        """No es lo mismo que la IA falle a que no le haya alcanzado el tiempo:
        volviendo a correrlo, estas SÍ pueden mejorar."""
        monkeypatch.setattr(st, "_presupuesto_del_lote", lambda: 0.0)
        _, resumen = await st.analizar_notificacion(_filas(10), servicio=_ServicioFalso())
        assert resumen["sin_tiempo"] == 10

    @pytest.mark.asyncio
    async def test_con_tiempo_de_sobra_todas_pasan_por_la_ia(self):
        servicio = _ServicioFalso()
        respuestas, resumen = await st.analizar_notificacion(_filas(6), servicio=servicio)
        assert len(respuestas) == 6
        assert resumen["analizadas_con_ia"] == 6
        assert resumen["sin_tiempo"] == 0

    @pytest.mark.asyncio
    async def test_ninguna_fila_sale_sin_respuesta(self):
        """La prueba que importa de verdad: una fila vacía en el archivo que se
        radica es una glosa que se da por aceptada."""
        respuestas, _ = await st.analizar_notificacion(_filas(8), servicio=_ServicioFalso())
        for r in respuestas:
            assert r.get("Codigo_Respuesta_a_glosas"), "fila sin código de respuesta"

    @pytest.mark.asyncio
    async def test_una_ia_que_revienta_no_tumba_el_lote(self):
        class _Revienta(_ServicioFalso):
            async def analizar(self, entrada):
                raise RuntimeError("la IA se cayó")

        respuestas, resumen = await st.analizar_notificacion(_filas(5), servicio=_Revienta())
        assert len(respuestas) == 5
        assert resumen["por_plantilla"] == 5
