"""El contrato que regía el día del hecho — no el que esté cargado hoy.

Dos cosas que el sistema no sabía hacer y que cambian un dictamen:

1. Elegir por FECHA. `CONTRATOS_HUS` guardaba la vigencia como texto libre
   —'2025', '15/04/2026 — 14/04/2027'— y nadie la leía. Una atención de marzo
   de 2026 se defendía citando el contrato de FAMISANAR que empezó el 15 de
   abril: un contrato que no regía el día del hecho.

2. Manejar VARIOS contratos por pagador. COOSALUD tiene dos —subsidiado y
   contributivo, con fechas distintas— y el PPL tiene el original más un
   otrosí que lo extiende.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services import malla_contractual as m


class TestVigenciaPorFecha:
    def test_famisanar_no_cubre_una_atencion_anterior_a_su_inicio(self):
        """El contrato arranca el 15-abr-2026. Marzo no está cubierto."""
        assert m.vigente("FAMISANAR", date(2026, 3, 20)) is None
        vigente = m.vigente("FAMISANAR", date(2026, 5, 20))
        assert vigente is not None
        assert vigente.numero == "S13103104958"

    def test_coosalud_resuelve_el_contrato_correcto_segun_la_fecha(self):
        """Dos contratos: el subsidiado terminó el 30-abr-2026, el
        contributivo sigue hasta 2027. Antes de esa fecha valían los dos."""
        antes = m.vigente("COOSALUD", date(2026, 1, 15))
        assert antes is not None
        despues = m.vigente("COOSALUD", date(2026, 6, 15))
        assert despues is not None
        assert despues.numero == "68001C00060340-24"

    def test_el_ppl_usa_el_otrosi_para_2026(self):
        """El contrato original terminó el 30-nov-2025; el otrosí 26 cubre 2026."""
        assert m.vigente("PPL", date(2025, 6, 1)).numero == "IPS-001B-2022"
        assert "Otros" in m.vigente("PPL", date(2026, 3, 1)).numero

    def test_sin_contrato_ese_dia_devuelve_none(self):
        """No es un fallo de búsqueda: es un hecho que cambia la defensa."""
        assert m.vigente("PPL", date(2025, 12, 15)) is None

    def test_pagador_desconocido(self):
        assert m.vigente("EPS QUE NO EXISTE", date(2026, 7, 1)) is None
        assert m.contratos_de("EPS QUE NO EXISTE") == []


class TestElNombreQueEscribeLaEps:
    """La EPS no escribe el pagador como lo escribe contratación."""

    @pytest.mark.parametrize(
        "escrito,esperado",
        [
            ("DISPENSARIO", "DISPENSARIO MEDICO"),
            ("DSE EJERCITO", "DISPENSARIO MEDICO"),
            ("dispensario medico", "DISPENSARIO MEDICO"),
            ("SEGUROS AURORA / ARL", "AURORA"),
            ("PREVISORA", "FOMAG"),
            ("SUMIMEDICAL S.A.S", "SUMIMEDICAL"),
        ],
    )
    def test_reconoce_las_variantes(self, escrito, esperado):
        encontrados = m.contratos_de(escrito)
        assert encontrados, f"no reconoció '{escrito}'"
        assert encontrados[0].pagador == esperado

    def test_lo_especifico_no_lo_tapa_lo_general(self):
        """'POLICIA NACIONAL' no puede eclipsar a 'POLICIA NACIONAL ONCOLOGIA':
        son dos contratos con números y objetos distintos."""
        onco = m.contratos_de("POLICIA NACIONAL ONCOLOGIA")
        assert onco[0].numero == "068-5-200006-26"


class TestEstadoDeVigencia:
    """Facturar contra un contrato vencido es una glosa segura."""

    def test_al_29_de_julio_de_2026_hay_contratos_vencidos(self):
        e = m.estado_vigencia(date(2026, 7, 29))
        vencidos = {c["numero"] for c in e["vencidos"]}
        assert "68001S00060339-24" in vencidos  # COOSALUD subsidiado
        assert "CSS009-2024" in vencidos  # COMPENSAR
        assert "02-01-06-00077-2017" in vencidos  # NUEVA EPS

    def test_el_contrato_del_dispensario_vence_el_30_de_julio(self):
        """Es el mayor volumen del hospital: el aviso tiene que ser visible."""
        e = m.estado_vigencia(date(2026, 7, 29))
        disp = next(c for c in e["por_vencer"] if c["numero"] == "440-DIGSA/DMBUG-2025")
        assert disp["dias"] == 1
        assert disp["hasta_agotar_recurso"] is True

    def test_lo_indeterminado_no_se_cuenta_como_vencido(self):
        """FOMAG continúa hasta formalizar: no tiene fecha de terminación."""
        e = m.estado_vigencia(date(2026, 7, 29))
        indet = {c["pagador"] for c in e["indeterminados"]}
        assert "FOMAG" in indet
        assert "FOMAG" not in {c["pagador"] for c in e["vencidos"]}

    def test_el_aviso_llega_antes_de_que_se_venza(self):
        """Renegociar toma semanas; avisar el día que se acaba no sirve."""
        e = m.estado_vigencia(date(2026, 7, 29), dias_aviso=60)
        assert e["por_vencer"], "nadie avisó de nada"
        assert all(0 <= c["dias"] <= 60 for c in e["por_vencer"])

    def test_todos_los_contratos_quedan_clasificados(self):
        e = m.estado_vigencia(date(2026, 7, 29))
        total = (
            len(e["vencidos"])
            + len(e["por_vencer"])
            + len(e["vigentes"])
            + len(e["indeterminados"])
        )
        assert total == e["total"] == len(m.MALLA)


class TestLaMallaEstaCompleta:
    def test_cada_contrato_tiene_lo_minimo_para_citarlo(self):
        for c in m.MALLA:
            assert c.pagador.strip()
            assert c.tarifa_texto.strip(), c.pagador
            assert c.desde <= (c.hasta or date(2099, 1, 1)), c.pagador

    def test_el_factor_concuerda_con_el_descuento_del_texto(self):
        """Un factor mal puesto hace que la IA defienda una tarifa equivocada."""
        import re

        for c in m.MALLA:
            if c.factor is None:
                continue
            pct = re.search(r"-\s*(\d+)\s*%", c.tarifa_texto)
            if pct:
                esperado = 1 - int(pct.group(1)) / 100
                assert abs(c.factor - esperado) < 0.001, (
                    f"{c.pagador}: texto dice -{pct.group(1)}% y el factor es {c.factor}"
                )

    def test_las_exclusiones_estan_donde_la_malla_las_declara(self):
        """Que COOSALUD no cubra oncológicos cambia la defensa de esa glosa."""
        coosalud = m.contratos_de("COOSALUD")[0]
        assert any("oncol" in e.lower() for e in coosalud.exclusiones)
        compensar = m.contratos_de("COMPENSAR")[0]
        assert any("MAOS" in e for e in compensar.exclusiones)
