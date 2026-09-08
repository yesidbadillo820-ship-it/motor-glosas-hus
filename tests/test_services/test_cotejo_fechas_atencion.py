"""El cotejo pilla lo que no cuadra — y dice claro lo que no pudo verificar.

08-09-2026. Lo que se prueba acá es el criterio: qué es un imposible (y por
tanto GRAVE), qué es una diferencia que hay que mirar, y qué es simplemente
un dato que faltó. Y sobre todo: que cuando no hay con qué comparar, el
sistema lo diga en vez de dar por bueno lo que nadie revisó.
"""

from __future__ import annotations

from datetime import date, datetime

from app.services.cotejo_fechas_atencion import (
    ADVIERTE,
    GRAVE,
    INFORMA,
    cotejar,
    hay_reparos_graves,
)
from app.services.rips_fechas_atencion import FechasAtencion

RIPS_BUENO = FechasAtencion(
    factura="HUS0000556635",
    fecha_ingreso=datetime(2025, 3, 10, 8, 0),
    fecha_egreso=datetime(2025, 3, 25, 14, 30),
    tipo_atencion="HOSPITALIZACION",
    archivo="Rips_HUS0000556635.json",
)


def _codigos(hallazgos) -> set[str]:
    return {h.codigo for h in hallazgos}


class TestCuandoTodoCuadra:
    def test_fechas_iguales_a_las_declaradas_no_generan_reparo(self):
        h = cotejar(
            RIPS_BUENO,
            ingreso_declarado=date(2025, 3, 10),
            egreso_declarado=date(2025, 3, 25),
            fecha_factura=date(2025, 3, 28),
            fecha_recibido=date(2025, 4, 2),
        )
        assert h == []
        assert not hay_reparos_graves(h)

    def test_la_hora_no_cuenta_como_diferencia(self):
        """El RIPS trae hora y el Excel no: es la misma fecha."""
        h = cotejar(RIPS_BUENO, egreso_declarado="2025-03-25 23:59")
        assert "EGRESO_NO_COINCIDE" not in _codigos(h)


class TestLosImposibles:
    def test_un_egreso_anterior_al_ingreso(self):
        malo = FechasAtencion(
            fecha_ingreso=datetime(2025, 3, 25),
            fecha_egreso=datetime(2025, 3, 10),
        )
        h = cotejar(malo)
        assert "EGRESO_ANTES_DEL_INGRESO" in _codigos(h)
        assert hay_reparos_graves(h)

    def test_una_factura_anterior_al_egreso(self):
        h = cotejar(RIPS_BUENO, fecha_factura=date(2025, 3, 20))
        assert "FACTURA_ANTES_DEL_EGRESO" in _codigos(h)
        assert hay_reparos_graves(h)

    def test_un_egreso_posterior_a_la_entrega_de_la_cuenta(self):
        h = cotejar(RIPS_BUENO, fecha_recibido=date(2025, 3, 20))
        assert "EGRESO_DESPUES_DE_RECIBIDA" in _codigos(h)
        assert hay_reparos_graves(h)

    def test_la_factura_del_mismo_dia_del_egreso_esta_bien(self):
        h = cotejar(RIPS_BUENO, fecha_factura=date(2025, 3, 25))
        assert "FACTURA_ANTES_DEL_EGRESO" not in _codigos(h)


class TestLasDiferencias:
    def test_un_egreso_distinto_al_declarado_se_reporta_con_los_dias(self):
        h = cotejar(RIPS_BUENO, egreso_declarado=date(2025, 3, 28))
        (reparo,) = [x for x in h if x.codigo == "EGRESO_NO_COINCIDE"]
        assert reparo.gravedad == ADVIERTE
        assert "25/03/2025" in reparo.mensaje and "28/03/2025" in reparo.mensaje
        assert "3 días" in reparo.mensaje

    def test_un_dia_de_diferencia_se_escribe_en_singular(self):
        h = cotejar(RIPS_BUENO, ingreso_declarado=date(2025, 3, 11))
        (reparo,) = [x for x in h if x.codigo == "INGRESO_NO_COINCIDE"]
        assert "1 día " in reparo.mensaje or reparo.mensaje.endswith("1 día).")

    def test_se_puede_aflojar_la_tolerancia(self):
        h = cotejar(RIPS_BUENO, egreso_declarado=date(2025, 3, 26), tolerancia_dias=1)
        assert "EGRESO_NO_COINCIDE" not in _codigos(h)


class TestLoQueNoSePudoVerificar:
    def test_sin_rips_lo_dice_y_no_calla(self):
        h = cotejar(None)
        assert _codigos(h) == {"RIPS_NO_ENCONTRADO"}
        assert h[0].gravedad == ADVIERTE
        assert not hay_reparos_graves(h)

    def test_un_rips_con_problema_se_reporta(self):
        h = cotejar(FechasAtencion(problema="el archivo está vacío: Rips_X.json"))
        assert "RIPS_NO_LEIDO" in _codigos(h)
        assert "vacío" in h[0].mensaje

    def test_sin_fechas_declaradas_avisa_que_nadie_contrasto(self):
        h = cotejar(RIPS_BUENO)
        (aviso,) = [x for x in h if x.codigo == "SIN_FECHAS_DECLARADAS"]
        assert aviso.gravedad == INFORMA
        assert not hay_reparos_graves(h)

    def test_si_hay_declaradas_no_sale_ese_aviso(self):
        h = cotejar(RIPS_BUENO, egreso_declarado=date(2025, 3, 25))
        assert "SIN_FECHAS_DECLARADAS" not in _codigos(h)

    def test_una_fecha_declarada_ilegible_no_se_adivina(self):
        """Un texto que no es fecha no puede volverse una discrepancia falsa."""
        h = cotejar(RIPS_BUENO, egreso_declarado="pendiente")
        assert "EGRESO_NO_COINCIDE" not in _codigos(h)


class TestFormaDeLaSalida:
    def test_cada_hallazgo_viaja_como_json(self):
        import json

        h = cotejar(RIPS_BUENO, fecha_factura=date(2025, 3, 1))
        json.dumps([x.a_dict() for x in h])
        assert all({"codigo", "gravedad", "mensaje"} == set(x.a_dict()) for x in h)

    def test_todas_las_gravedades_son_de_las_tres_conocidas(self):
        h = cotejar(
            FechasAtencion(
                fecha_ingreso=datetime(2025, 3, 25),
                fecha_egreso=datetime(2025, 3, 10),
                problema="algo",
            ),
            egreso_declarado=date(2025, 4, 1),
            fecha_factura=date(2025, 1, 1),
        )
        assert h
        assert all(x.gravedad in {GRAVE, ADVIERTE, INFORMA} for x in h)
