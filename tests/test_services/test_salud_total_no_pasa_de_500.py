"""Salud Total rechaza la fila del TXT si la Observación IPS pasa de 500.

El propio archivo lo dice desde siempre («Las plantillas están calibradas para
quedar dentro del límite incluso con el nombre del servicio»), pero **nadie lo
estaba midiendo**. Se descubrió el 28-08-2026 al alargar dos plantillas para
sacarles la Resolución 3047 de 2008, que está derogada: al medir apareció que
la plantilla de TARIFAS ya se pasaba desde antes.

Por qué importa: cuando el texto se pasa, el recorte automático corta por el
último punto que quepa. Con las plantillas largas eso se lleva por delante
justo el final — «Se solicita el levantamiento de la glosa» y el correo de
Cartera—, que es la parte que pide algo. La EPS recibe un párrafo que se queda
sin petición.

LO QUE ESTA PRUEBA NO HACE: arreglar la de TARIFAS. Ese texto lleva las cifras
del manual tarifario (UVB 2026, Circular 047/2025, Decreto 780/2016) y decidir
qué se recorta es del auditor, no de quien programa. Aquí queda medida y
fijada para que no empeore, y anotada para que se decida.
"""

from __future__ import annotations

import pytest

from app.services.salud_total_service import OBS_MAX_CARACTERES, GlosaSaludTotal

# El nombre del servicio se recorta a 80 caracteres; ese es el peor caso.
SERVICIO_MAS_LARGO_POSIBLE = "X" * 120
# El código más largo que puede quedar cuando la glosa no trae específico.
CODIGO_MAS_LARGO = "GENERAL"

# Medido el 28-08-2026. La de TARIFAS ya venía pasada de antes de ese día:
# 543 con el servicio en su largo máximo. Queda como tope para que no crezca.
TOPE_CONOCIDO_TARIFAS = 543


def _observacion(tipo: str) -> str:
    g = GlosaSaludTotal.__new__(GlosaSaludTotal)
    g.nombre_servicio = SERVICIO_MAS_LARGO_POSIBLE
    g.cod_motv_glosa_general = tipo
    g.cod_motv_glosa_espc = CODIGO_MAS_LARGO
    return g._argumento_tecnico_por_codigo("RE9901")  # noqa: SLF001


class TestCabeEnElCampoDelPortal:
    @pytest.mark.parametrize("tipo", ["FA", "SO", "AU", "IN", "CO"])
    def test_no_pasa_del_limite_ni_en_el_peor_caso(self, tipo: str):
        largo = len(_observacion(tipo))
        assert largo <= OBS_MAX_CARACTERES, (
            f"La plantilla {tipo} mide {largo} y el portal corta en "
            f"{OBS_MAX_CARACTERES}: el recorte se lleva la petición final."
        )

    def test_la_de_tarifas_no_empeora(self):
        """Defecto viejo, medido y congelado — no se arregla aquí a propósito.

        Ver el encabezado del archivo: qué se recorta de ese texto lo decide el
        auditor, porque lleva las cifras del manual tarifario.
        """
        largo = len(_observacion("TA"))
        assert largo <= TOPE_CONOCIDO_TARIFAS, (
            f"La plantilla de TARIFAS creció: mide {largo} y ya venía pasada "
            f"({TOPE_CONOCIDO_TARIFAS}). No agregar texto ahí hasta acortarla."
        )


class TestYaNoCitaLaNormaDerogada:
    @pytest.mark.parametrize("tipo", ["TA", "FA", "SO", "AU", "IN", "CO"])
    def test_ninguna_plantilla_nombra_la_3047(self, tipo: str):
        """Citaban la Res. 3047/2008 como ÚNICA fuente de los soportes, sin
        nombrar ninguna norma vigente: la cita que la entidad tumba sin
        discutir el fondo."""
        assert "3047" not in _observacion(tipo)

    @pytest.mark.parametrize("tipo", ["FA", "SO"])
    def test_las_de_soportes_anclan_en_la_que_rige_hoy(self, tipo: str):
        texto = _observacion(tipo)
        assert "2284/2023" in texto
        assert "1885/2024" in texto, "el Anexo 1 fue sustituido; hay que decirlo"

    @pytest.mark.parametrize("tipo", ["FA", "SO"])
    def test_conserva_la_peticion_final(self, tipo: str):
        """Lo que se pierde si el texto se pasa del límite."""
        assert "levantamiento de la glosa" in _observacion(tipo)
