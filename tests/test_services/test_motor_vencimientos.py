"""Motor de Vencimientos — la capacidad que faltaba (28-jul-2026).

Contexto: el semáforo tenía estado NEGRO para lo ya vencido y no disparaba
nada. Tres facturas de junio con 38 objeciones por $20.054.751 se descubrieron
45 días tarde, revisando a mano. Este motor es la pieza del medio entre el
cálculo de días y el envío de avisos que ya estaba construido.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pytest

from app.services.motor_vencimientos import (
    Destinatarios,
    Umbrales,
    Urgencia,
    agrupar_por_destinatario,
    clasificar,
    esta_en_juego,
    evaluar,
    severidad,
)


@dataclass
class G:
    """Glosa mínima para probar el motor sin base de datos."""

    id: int = 1
    dias_restantes: Optional[int] = 10
    estado: str = "PENDIENTE"
    workflow_state: str = "RADICADA"
    auditor_email: str = ""
    valor_objetado: float = 1_000_000.0
    factura: str = "HUS0000224871"
    eps: str = "COOSALUD"
    codigo_glosa: str = "TA0201"


UMB = Umbrales(preventivo=10, alta=5, critica=2)


class TestClasificacion:
    @pytest.mark.parametrize(
        "dias,esperado",
        [
            (30, Urgencia.SIN_RIESGO),
            (11, Urgencia.SIN_RIESGO),
            (10, Urgencia.PREVENTIVO),
            (6, Urgencia.PREVENTIVO),
            (5, Urgencia.ALTA),
            (3, Urgencia.ALTA),
            (2, Urgencia.CRITICA),
            (1, Urgencia.CRITICA),
            (0, Urgencia.CRITICA),
            (-1, Urgencia.VENCIDA),
            (-45, Urgencia.VENCIDA),
        ],
    )
    def test_umbrales_del_area(self, dias, esperado):
        """La tabla que definió el área: 10 preventivo, 5 alta, 2 crítica."""
        assert clasificar(dias, UMB) is esperado

    def test_el_dia_del_vencimiento_es_critico_no_vencido(self):
        """Con 0 días todavía se puede radicar: es crítico, no perdido."""
        assert clasificar(0, UMB) is Urgencia.CRITICA

    def test_sin_plazo_no_se_inventa_urgencia(self):
        assert clasificar(None, UMB) is Urgencia.SIN_RIESGO

    def test_el_orden_de_severidad_es_estricto(self):
        niveles = [
            Urgencia.SIN_RIESGO,
            Urgencia.PREVENTIVO,
            Urgencia.ALTA,
            Urgencia.CRITICA,
            Urgencia.VENCIDA,
        ]
        assert [severidad(n) for n in niveles] == sorted(severidad(n) for n in niveles)


class TestUmbralesConfigurables:
    def test_se_leen_del_entorno(self, monkeypatch):
        monkeypatch.setenv("VENCIMIENTOS_DIAS_PREVENTIVO", "15")
        monkeypatch.setenv("VENCIMIENTOS_DIAS_ALTA", "7")
        monkeypatch.setenv("VENCIMIENTOS_DIAS_CRITICA", "3")
        u = Umbrales.desde_entorno()
        assert (u.preventivo, u.alta, u.critica) == (15, 7, 3)

    def test_umbrales_incoherentes_caen_al_defecto(self, monkeypatch):
        """Si crítica > alta habría niveles inalcanzables y el área creería
        estar avisada sin estarlo."""
        monkeypatch.setenv("VENCIMIENTOS_DIAS_PREVENTIVO", "2")
        monkeypatch.setenv("VENCIMIENTOS_DIAS_ALTA", "5")
        monkeypatch.setenv("VENCIMIENTOS_DIAS_CRITICA", "10")
        u = Umbrales.desde_entorno()
        assert (u.preventivo, u.alta, u.critica) == (10, 5, 2)

    def test_valor_ilegible_cae_al_defecto(self, monkeypatch):
        monkeypatch.setenv("VENCIMIENTOS_DIAS_ALTA", "cinco")
        assert Umbrales.desde_entorno().alta == 5


class TestGlosasQueYaNoCompiten:
    @pytest.mark.parametrize(
        "estado", ["LEVANTADA", "ACEPTADA", "CONCILIADA", "ARCHIVADA", "RESUELTA"]
    )
    def test_una_glosa_cerrada_no_vence(self, estado):
        assert esta_en_juego(G(estado=estado)) is False

    def test_tambien_se_mira_el_workflow(self):
        assert esta_en_juego(G(estado="PENDIENTE", workflow_state="CONCILIADA")) is False

    def test_una_glosa_abierta_si_compite(self):
        assert esta_en_juego(G(estado="PENDIENTE", workflow_state="RADICADA")) is True

    def test_las_cerradas_no_entran_al_resumen(self):
        r = evaluar([G(id=1, dias_restantes=-5, estado="LEVANTADA")], UMB)
        assert r.en_riesgo == []
        assert r.total_evaluadas == 1


class TestResumen:
    def _muestra(self):
        return [
            G(id=1, dias_restantes=-3, valor_objetado=20_054_751),
            G(id=2, dias_restantes=1, valor_objetado=5_000_000),
            G(id=3, dias_restantes=4, valor_objetado=1_000_000),
            G(id=4, dias_restantes=9, valor_objetado=500_000),
            G(id=5, dias_restantes=60, valor_objetado=900_000),
            G(id=6, dias_restantes=None, valor_objetado=100_000),
            G(id=7, dias_restantes=-1, estado="CONCILIADA"),
        ]

    def test_conteos_por_nivel(self):
        r = evaluar(self._muestra(), UMB)
        assert r.conteos == {"PREVENTIVO": 1, "ALTA": 1, "CRITICA": 1, "VENCIDA": 1}

    def test_ordena_de_lo_mas_urgente_a_lo_menos(self):
        r = evaluar(self._muestra(), UMB)
        assert [g.id for g in r.en_riesgo] == [1, 2, 3, 4]

    def test_las_sin_plazo_se_cuentan_aparte_y_no_se_esconden(self):
        r = evaluar(self._muestra(), UMB)
        assert r.sin_plazo == 1

    def test_valor_en_riesgo(self):
        r = evaluar(self._muestra(), UMB)
        assert r.valor_en_riesgo == 26_554_751.0

    def test_desde_un_nivel_incluye_los_peores(self):
        r = evaluar(self._muestra(), UMB)
        assert [g.id for g in r.desde(Urgencia.CRITICA)] == [1, 2]

    def test_el_dict_no_lleva_datos_del_paciente(self):
        """Las alertas salen por correo y se reenvían (Ley 1581/2012)."""
        r = evaluar(self._muestra(), UMB)
        for g in r.como_dict()["glosas"]:
            assert "paciente" not in g

    def test_resumen_vacio_no_revienta(self):
        r = evaluar([], UMB)
        assert r.conteos == {"PREVENTIVO": 0, "ALTA": 0, "CRITICA": 0, "VENCIDA": 0}
        assert r.valor_en_riesgo == 0.0


class TestDestinatarios:
    def _dest(self):
        return Destinatarios(
            avisar_al_gestor=True,
            alta=("coordinador@hus.com",),
            critica=("cartera@hus.com",),
            vencida=("direccion@hus.com",),
        )

    def test_preventivo_solo_le_llega_al_gestor(self):
        r = evaluar([G(dias_restantes=8, auditor_email="ana@hus.com")], UMB)
        assert self._dest().para(r.en_riesgo[0]) == ["ana@hus.com"]

    def test_alta_suma_al_coordinador(self):
        r = evaluar([G(dias_restantes=4, auditor_email="ana@hus.com")], UMB)
        assert self._dest().para(r.en_riesgo[0]) == ["ana@hus.com", "coordinador@hus.com"]

    def test_los_niveles_son_acumulativos(self):
        """Quien recibe ALTA no necesita repetirse en CRÍTICA ni en VENCIDA."""
        r = evaluar([G(dias_restantes=-2, auditor_email="ana@hus.com")], UMB)
        assert self._dest().para(r.en_riesgo[0]) == [
            "ana@hus.com",
            "coordinador@hus.com",
            "cartera@hus.com",
            "direccion@hus.com",
        ]

    def test_una_vencida_escala_aunque_no_tenga_gestor(self):
        """Es el caso de las 3 facturas de junio: sin dueño y vencidas."""
        r = evaluar([G(dias_restantes=-45, auditor_email="")], UMB)
        destinos = self._dest().para(r.en_riesgo[0])
        assert "direccion@hus.com" in destinos
        assert destinos  # nunca queda huérfana

    def test_no_repite_correos(self):
        d = Destinatarios(
            avisar_al_gestor=True,
            alta=("ana@hus.com",),
            critica=("ana@hus.com",),
            vencida=("ana@hus.com",),
        )
        r = evaluar([G(dias_restantes=-1, auditor_email="ana@hus.com")], UMB)
        assert d.para(r.en_riesgo[0]) == ["ana@hus.com"]

    def test_se_leen_del_entorno(self, monkeypatch):
        monkeypatch.setenv("VENCIMIENTOS_CORREO_ALTA", "a@hus.com; b@hus.com , basura")
        monkeypatch.setenv("VENCIMIENTOS_CORREO_GESTOR", "0")
        d = Destinatarios.desde_entorno()
        assert d.alta == ("a@hus.com", "b@hus.com")
        assert d.avisar_al_gestor is False

    def test_sin_configuracion_no_hay_a_quien_avisar(self, monkeypatch):
        for v in (
            "VENCIMIENTOS_CORREO_ALTA",
            "VENCIMIENTOS_CORREO_CRITICA",
            "VENCIMIENTOS_CORREO_VENCIDA",
        ):
            monkeypatch.setenv(v, "")
        monkeypatch.setenv("VENCIMIENTOS_CORREO_GESTOR", "0")
        assert Destinatarios.desde_entorno().hay_alguno is False


class TestAgrupacion:
    def test_un_correo_por_persona_con_todo_lo_suyo(self):
        """Cien glosas críticas no pueden ser cien correos."""
        glosas = [
            G(id=1, dias_restantes=1, auditor_email="ana@hus.com"),
            G(id=2, dias_restantes=1, auditor_email="ana@hus.com"),
            G(id=3, dias_restantes=1, auditor_email="luis@hus.com"),
        ]
        d = Destinatarios(avisar_al_gestor=True, critica=("cartera@hus.com",))
        bandejas = agrupar_por_destinatario(evaluar(glosas, UMB), d)
        assert sorted(bandejas) == ["ana@hus.com", "cartera@hus.com", "luis@hus.com"]
        assert len(bandejas["ana@hus.com"]) == 2
        assert len(bandejas["cartera@hus.com"]) == 3

    def test_sin_destinatarios_no_hay_bandejas(self):
        d = Destinatarios(avisar_al_gestor=False)
        bandejas = agrupar_por_destinatario(evaluar([G(dias_restantes=1)], UMB), d)
        assert bandejas == {}
