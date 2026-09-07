"""Reglas duras de la Pre-Auditoría Concurrente (V3, Pilar 2 — 04-09-2026).

Estas pruebas son el contrato con el facturador. Lo que se protege acá:

  · Que el motor NO invente. Si no hay tarifa cargada, se calla; si no hay
    sexo declarado, no deduce; si no hay epicrisis, lo dice.
  · Que los códigos de glosa proyectados sean los OFICIALES del Manual Único.
    Un código inventado desprestigia la herramienta el primer día.
  · Que un mismo ítem no sume su riesgo tres veces.
  · Los dos casos que pidió el auditor: MÚLTIPLES CIRUGÍAS (la misma cirugía
    facturada por dos vías) y ESTANCIA EN UCI INJUSTIFICADA.
"""

from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import TarifaContratadaRecord
from app.services.catalogo_glosas import CATALOGO_COMPLETO
from app.services.preauditoria_contrato import (
    Alerta,
    PayloadFactura,
    consolidar_valor_en_riesgo,
)
from app.services.preauditoria_reglas_duras import (
    CAUSAL_POR_TIPO,
    Contexto,
    correr_reglas_duras,
    familia_quirurgica,
    regla_aritmetica,
    regla_contrato_vigente,
    regla_cruce_edad,
    regla_cruce_genero,
    regla_doble_facturacion,
    regla_fechas_y_estancia,
    regla_topes_tarifarios,
    regla_uci_sin_soporte,
    regla_vias_quirurgicas,
    tipo_de,
    via_de,
)

CTX = Contexto(ahora=datetime(2026, 9, 4))


@pytest.fixture
def db():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    sesion = sessionmaker(bind=eng)()
    try:
        yield sesion
    finally:
        sesion.close()
        eng.dispose()


def factura(**kw) -> PayloadFactura:
    """Una factura mínima y sana; cada prueba le cambia lo que necesita."""
    base = {
        "factura": "HUS500123",
        "eps": "COOSALUD",
        "paciente": {"sexo": "F", "edad_anios": 34},
        "atencion": {
            "tipo": "HOSPITALIZACION",
            "fecha_ingreso": "2026-09-01",
            "fecha_egreso": "2026-09-04",
        },
        "items": [],
        "epicrisis": "Paciente estable, evolución satisfactoria.",
    }
    base.update(kw)
    return PayloadFactura(**base)


def item(**kw) -> dict:
    base = {"cups": "", "descripcion": "", "cantidad": 1, "valor_unitario": 0, "valor_total": 0}
    base.update(kw)
    return base


# ═══════════════════════════════════════════════════════════════════════
class TestLosCodigosSonLosOficiales:
    """Si un código no está en el Manual Único, la EPS no sabe de qué le hablan."""

    def test_ningun_codigo_proyectado_es_inventado(self):
        proyectados = {c for mapa in CAUSAL_POR_TIPO.values() for c in mapa.values()}
        inventados = sorted(proyectados - set(CATALOGO_COMPLETO))
        assert inventados == [], f"códigos que no existen en el Manual Único: {inventados}"

    def test_todo_tipo_de_servicio_tiene_las_cuatro_familias(self):
        for tipo, mapa in CAUSAL_POR_TIPO.items():
            assert set(mapa) == {"TA", "FA", "CL", "CO"}, f"{tipo} está incompleto"


# ═══════════════════════════════════════════════════════════════════════
class TestAritmetica:
    def test_la_linea_que_no_cuadra_bloquea(self):
        p = factura(
            items=[item(cups="890201", cantidad=2, valor_unitario=50_000, valor_total=150_000)],
            valor_total=150_000,
        )
        alertas = regla_aritmetica(p, CTX)
        assert [a.severidad for a in alertas] == ["BLOQUEO"]
        assert alertas[0].valor_en_riesgo == 50_000
        assert alertas[0].regla == "aritmetica_linea"

    def test_la_factura_que_no_suma_bloquea(self):
        p = factura(
            items=[item(cups="890201", cantidad=1, valor_unitario=50_000, valor_total=50_000)],
            valor_total=90_000,
        )
        alertas = [a for a in regla_aritmetica(p, CTX) if a.regla == "aritmetica_factura"]
        assert len(alertas) == 1
        assert alertas[0].valor_en_riesgo == 40_000

    def test_un_peso_de_diferencia_es_redondeo_y_no_alerta(self):
        p = factura(
            items=[item(cups="890201", cantidad=3, valor_unitario=33_333, valor_total=100_000)],
            valor_total=100_000,
        )
        assert regla_aritmetica(p, CTX) == []

    def test_la_factura_sana_no_dice_nada(self):
        p = factura(
            items=[item(cups="890201", cantidad=2, valor_unitario=50_000, valor_total=100_000)],
            valor_total=100_000,
        )
        assert regla_aritmetica(p, CTX) == []


# ═══════════════════════════════════════════════════════════════════════
class TestTopesTarifarios:
    def _cargar(self, db, cups="511002", valor=1_200_000, eps="COOSALUD"):
        db.add(
            TarifaContratadaRecord(
                eps=eps,
                codigo_cups=cups,
                descripcion="COLECISTECTOMÍA LAPAROSCÓPICA",
                valor_pactado=valor,
                tipo_tarifa="VALOR_FIJO",
                contrato_numero="CT-2026-001",
            )
        )
        db.commit()

    def test_cobrar_por_encima_de_lo_pactado_bloquea_con_el_exceso_exacto(self, db):
        self._cargar(db)
        p = factura(
            items=[
                item(
                    cups="511002",
                    descripcion="COLECISTECTOMÍA LAPAROSCÓPICA",
                    tipo="QUIRURGICO",
                    cantidad=1,
                    valor_unitario=1_500_000,
                    valor_total=1_500_000,
                )
            ],
            valor_total=1_500_000,
        )
        alertas = regla_topes_tarifarios(p, Contexto(db=db))
        assert len(alertas) == 1
        assert alertas[0].severidad == "BLOQUEO"
        assert alertas[0].codigo_glosa == "TA5801"
        assert alertas[0].valor_en_riesgo == 300_000
        assert "CT-2026-001" in alertas[0].detalle

    def test_el_exceso_se_multiplica_por_la_cantidad(self, db):
        self._cargar(db)
        p = factura(
            items=[
                item(
                    cups="511002",
                    tipo="QUIRURGICO",
                    cantidad=3,
                    valor_unitario=1_300_000,
                    valor_total=3_900_000,
                )
            ]
        )
        assert regla_topes_tarifarios(p, Contexto(db=db))[0].valor_en_riesgo == 300_000

    def test_dentro_de_la_tolerancia_del_medio_por_ciento_no_alerta(self, db):
        self._cargar(db)
        p = factura(items=[item(cups="511002", tipo="QUIRURGICO", valor_unitario=1_204_000)])
        assert regla_topes_tarifarios(p, Contexto(db=db)) == []

    def test_sin_tarifa_cargada_el_motor_se_calla_en_vez_de_estimar(self, db):
        """La regla de oro: no inventar. Sin tarifa no hay con qué comparar."""
        p = factura(items=[item(cups="999999", tipo="QUIRURGICO", valor_unitario=99_000_000)])
        assert regla_topes_tarifarios(p, Contexto(db=db)) == []

    def test_sin_base_de_datos_tampoco_opina(self):
        p = factura(items=[item(cups="511002", valor_unitario=99_000_000)])
        assert regla_topes_tarifarios(p, Contexto(db=None)) == []

    def test_la_tarifa_se_consulta_una_sola_vez_por_cups(self, db, monkeypatch):
        """Regla de rendimiento: nada de una consulta por línea (N+1)."""
        self._cargar(db)
        import app.services.tarifa_lookup_service as tls

        llamadas = []
        original = tls.tarifa_pactada_de

        def espia(*a, **kw):
            llamadas.append(a[2])
            return original(*a, **kw)

        monkeypatch.setattr(tls, "tarifa_pactada_de", espia)
        p = factura(items=[item(cups="511002", tipo="QUIRURGICO", valor_unitario=1_500_000)] * 12)
        regla_topes_tarifarios(p, Contexto(db=db))
        assert llamadas.count("511002") == 1, f"se consultó {llamadas.count('511002')} veces"


# ═══════════════════════════════════════════════════════════════════════
class TestCruceDeGenero:
    def test_parto_en_paciente_masculino_bloquea(self):
        p = factura(
            paciente={"sexo": "M", "edad_anios": 30},
            items=[
                item(
                    cups="740101",
                    descripcion="PARTO VAGINAL ESPONTÁNEO",
                    tipo="QUIRURGICO",
                    valor_unitario=800_000,
                    valor_total=800_000,
                )
            ],
        )
        alertas = regla_cruce_genero(p, CTX)
        assert len(alertas) == 1
        assert alertas[0].severidad == "BLOQUEO"
        assert alertas[0].valor_en_riesgo == 800_000
        assert "MASCULINO" in alertas[0].detalle

    def test_prostatectomia_en_paciente_femenino_bloquea(self):
        p = factura(
            paciente={"sexo": "FEMENINO", "edad_anios": 60},
            items=[item(descripcion="PROSTATECTOMÍA RADICAL", valor_total=4_000_000)],
        )
        assert regla_cruce_genero(p, CTX)[0].severidad == "BLOQUEO"

    def test_parto_en_paciente_femenino_no_dice_nada(self):
        p = factura(items=[item(cups="740101", descripcion="PARTO VAGINAL ESPONTÁNEO")])
        assert regla_cruce_genero(p, CTX) == []

    def test_sin_sexo_declarado_no_se_infiere_nada(self):
        p = factura(
            paciente={"sexo": ""},
            items=[item(descripcion="PARTO VAGINAL ESPONTÁNEO")],
        )
        assert regla_cruce_genero(p, CTX) == []

    def test_el_cups_solo_basta_porque_se_busca_la_descripcion(self):
        """El HIS puede mandar el código sin descripción: el motor la busca."""
        p = factura(paciente={"sexo": "M", "edad_anios": 40}, items=[item(cups="740301")])
        alertas = regla_cruce_genero(p, CTX)
        assert len(alertas) == 1 and alertas[0].severidad == "BLOQUEO"


# ═══════════════════════════════════════════════════════════════════════
class TestCruceDeEdad:
    def test_uci_neonatal_en_un_adulto_bloquea(self):
        p = factura(
            paciente={"sexo": "M", "edad_anios": 45},
            items=[
                item(
                    cups="S11203",
                    descripcion="ESTANCIA EN UCI NEONATAL",
                    tipo="ESTANCIA",
                    valor_total=6_000_000,
                )
            ],
        )
        alertas = regla_cruce_edad(p, CTX)
        assert len(alertas) == 1
        assert alertas[0].severidad == "BLOQUEO"
        assert alertas[0].codigo_glosa == "FA0101"
        assert alertas[0].valor_en_riesgo == 6_000_000

    def test_uci_pediatrica_en_un_adulto_bloquea(self):
        p = factura(
            paciente={"sexo": "F", "edad_anios": 52},
            items=[item(cups="S11202", descripcion="ESTANCIA EN UCI PEDIÁTRICA")],
        )
        assert regla_cruce_edad(p, CTX)[0].severidad == "BLOQUEO"

    def test_uci_de_adultos_en_un_nino_bloquea(self):
        p = factura(
            paciente={"sexo": "M", "edad_anios": 5},
            items=[item(cups="S11201", descripcion="ESTANCIA EN UCI ADULTOS")],
        )
        assert regla_cruce_edad(p, CTX)[0].severidad == "BLOQUEO"

    def test_uci_neonatal_en_un_recien_nacido_no_dice_nada(self):
        p = factura(
            paciente={"sexo": "F", "edad_dias": 3},
            items=[item(cups="S11203", descripcion="ESTANCIA EN UCI NEONATAL")],
        )
        assert regla_cruce_edad(p, CTX) == []

    def test_parto_en_una_paciente_de_62_avisa_pero_no_bloquea(self):
        """No es imposible: hay embarazos asistidos. Se avisa, no se cierra."""
        p = factura(
            paciente={"sexo": "F", "edad_anios": 62},
            items=[item(cups="740301", descripcion="PARTO POR CESÁREA")],
        )
        alertas = regla_cruce_edad(p, CTX)
        assert len(alertas) == 1 and alertas[0].severidad == "ADVERTENCIA"

    def test_sin_edad_no_se_opina(self):
        p = factura(
            paciente={"sexo": "M"},
            items=[item(descripcion="ESTANCIA EN UCI NEONATAL")],
        )
        assert regla_cruce_edad(p, CTX) == []

    def test_la_edad_se_calcula_de_la_fecha_de_nacimiento_si_hace_falta(self):
        p = factura(
            paciente={"sexo": "M", "fecha_nacimiento": "1980-01-01"},
            items=[item(descripcion="ESTANCIA EN UCI NEONATAL")],
        )
        assert regla_cruce_edad(p, CTX)[0].severidad == "BLOQUEO"


# ═══════════════════════════════════════════════════════════════════════
class TestMultiplesCirugias:
    """El caso que pidió el auditor: la misma cirugía facturada dos veces
    por vías que se excluyen entre sí."""

    def test_colecistectomia_abierta_y_laparoscopica_en_la_misma_factura(self):
        p = factura(
            items=[
                item(
                    cups="511001",
                    descripcion="COLECISTECTOMÍA POR LAPAROTOMÍA",
                    tipo="QUIRURGICO",
                    valor_unitario=1_800_000,
                    valor_total=1_800_000,
                ),
                item(
                    cups="511002",
                    descripcion="COLECISTECTOMÍA LAPAROSCÓPICA",
                    tipo="QUIRURGICO",
                    valor_unitario=2_400_000,
                    valor_total=2_400_000,
                ),
            ],
            valor_total=4_200_000,
        )
        alertas = regla_vias_quirurgicas(p, CTX)
        assert len(alertas) == 1
        assert alertas[0].severidad == "BLOQUEO"
        assert alertas[0].codigo_glosa == "FA5801"
        # El riesgo es el mayor de las dos, no la suma: solo una sobra.
        assert alertas[0].valor_en_riesgo == 2_400_000
        assert "ABIERTA" in alertas[0].detalle and "LAPAROSCOPICA" in alertas[0].detalle

    def test_apendicectomia_por_las_dos_vias_tambien(self):
        p = factura(
            items=[
                item(cups="470301", descripcion="APENDICECTOMÍA POR LAPAROTOMÍA"),
                item(cups="470302", descripcion="APENDICECTOMÍA LAPAROSCÓPICA"),
            ]
        )
        assert regla_vias_quirurgicas(p, CTX)[0].severidad == "BLOQUEO"

    def test_una_sola_via_no_dice_nada(self):
        p = factura(items=[item(cups="511002", descripcion="COLECISTECTOMÍA LAPAROSCÓPICA")])
        assert regla_vias_quirurgicas(p, CTX) == []

    def test_dos_cirugias_distintas_por_vias_distintas_son_legitimas(self):
        p = factura(
            items=[
                item(cups="511002", descripcion="COLECISTECTOMÍA LAPAROSCÓPICA"),
                item(cups="470301", descripcion="APENDICECTOMÍA POR LAPAROTOMÍA"),
            ]
        )
        assert regla_vias_quirurgicas(p, CTX) == []

    def test_parto_vaginal_y_cesarea_avisan_pero_no_bloquean(self):
        """En un embarazo múltiple puede pasar de verdad. Se avisa."""
        p = factura(
            items=[
                item(cups="740101", descripcion="PARTO VAGINAL ESPONTÁNEO"),
                item(cups="740301", descripcion="PARTO POR CESÁREA"),
            ]
        )
        alertas = regla_vias_quirurgicas(p, CTX)
        assert len(alertas) == 1
        assert alertas[0].severidad == "ADVERTENCIA"
        assert "embarazo múltiple" in alertas[0].detalle

    def test_la_via_declarada_por_el_his_tambien_sirve(self):
        p = factura(
            items=[
                item(descripcion="COLECISTECTOMÍA", via="ABIERTA"),
                item(descripcion="COLECISTECTOMÍA", via="LAPAROSCOPICA"),
            ]
        )
        assert regla_vias_quirurgicas(p, CTX)[0].severidad == "BLOQUEO"

    def test_la_familia_ignora_la_via_al_comparar(self):
        from app.services.preauditoria_contrato import ItemFactura

        a = ItemFactura(descripcion="COLECISTECTOMÍA POR LAPAROTOMÍA")
        b = ItemFactura(descripcion="COLECISTECTOMÍA LAPAROSCÓPICA")
        assert familia_quirurgica(a) == familia_quirurgica(b) == "COLECISTECTOMIA"
        assert via_de(a) == "ABIERTA" and via_de(b) == "LAPAROSCOPICA"


# ═══════════════════════════════════════════════════════════════════════
class TestFechasYEstancia:
    def test_egreso_antes_del_ingreso_bloquea_y_arriesga_la_factura_entera(self):
        p = factura(
            atencion={"fecha_ingreso": "2026-08-25", "fecha_egreso": "2026-08-20"},
            items=[item(cups="S11101", valor_total=900_000)],
            valor_total=900_000,
        )
        alertas = [a for a in regla_fechas_y_estancia(p, CTX) if a.regla == "fechas_invertidas"]
        assert len(alertas) == 1
        assert alertas[0].severidad == "BLOQUEO"
        assert alertas[0].valor_en_riesgo == 900_000

    def test_mas_dias_de_estancia_que_el_episodio_bloquea(self):
        p = factura(
            atencion={
                "fecha_ingreso": "2026-09-01",
                "fecha_egreso": "2026-09-04",
                "dias_estancia": 7,
            },
            items=[item(cups="S11101", tipo="ESTANCIA", valor_unitario=300_000)],
        )
        alertas = [
            a for a in regla_fechas_y_estancia(p, CTX) if a.regla == "estancia_mayor_que_episodio"
        ]
        assert len(alertas) == 1
        assert alertas[0].severidad == "BLOQUEO"
        assert alertas[0].valor_en_riesgo == 4 * 300_000

    def test_ingreso_y_egreso_el_mismo_dia_se_facturan_como_un_dia(self):
        p = factura(
            atencion={
                "fecha_ingreso": "2026-09-01",
                "fecha_egreso": "2026-09-01",
                "dias_estancia": 1,
            }
        )
        assert [
            a for a in regla_fechas_y_estancia(p, CTX) if a.regla == "estancia_mayor_que_episodio"
        ] == []

    def test_mas_uci_que_estancia_bloquea(self):
        p = factura(
            atencion={
                "fecha_ingreso": "2026-09-01",
                "fecha_egreso": "2026-09-04",
                "dias_estancia": 3,
                "dias_uci": 8,
            }
        )
        alertas = [
            a for a in regla_fechas_y_estancia(p, CTX) if a.regla == "uci_mayor_que_estancia"
        ]
        assert len(alertas) == 1 and alertas[0].severidad == "BLOQUEO"

    def test_una_linea_fechada_fuera_del_episodio_avisa(self):
        p = factura(
            items=[item(cups="890201", fecha="2026-10-15", valor_total=120_000)],
        )
        alertas = [
            a for a in regla_fechas_y_estancia(p, CTX) if a.regla == "linea_fuera_del_episodio"
        ]
        assert len(alertas) == 1
        assert alertas[0].severidad == "ADVERTENCIA"
        assert alertas[0].valor_en_riesgo == 120_000

    def test_sin_fechas_no_se_opina(self):
        p = factura(atencion={})
        assert regla_fechas_y_estancia(p, CTX) == []


# ═══════════════════════════════════════════════════════════════════════
class TestDobleFacturacion:
    def test_el_mismo_procedimiento_dos_veces_el_mismo_dia_avisa(self):
        p = factura(
            items=[
                item(cups="470302", tipo="QUIRURGICO", fecha="2026-09-02", valor_total=2_000_000),
                item(cups="470302", tipo="QUIRURGICO", fecha="2026-09-02", valor_total=2_000_000),
            ]
        )
        alertas = regla_doble_facturacion(p, CTX)
        assert len(alertas) == 1
        assert alertas[0].codigo_glosa == "FA2702"
        assert alertas[0].severidad == "ADVERTENCIA"
        assert alertas[0].valor_en_riesgo == 2_000_000  # solo la repetida

    def test_un_medicamento_repetido_es_normal_y_no_avisa(self):
        p = factura(
            items=[
                item(cups="M01101", tipo="MEDICAMENTO", fecha="2026-09-02", valor_total=15_000),
                item(cups="M01101", tipo="MEDICAMENTO", fecha="2026-09-02", valor_total=15_000),
            ]
        )
        assert regla_doble_facturacion(p, CTX) == []

    def test_el_mismo_procedimiento_en_dias_distintos_no_avisa(self):
        p = factura(
            items=[
                item(cups="890201", tipo="CONSULTA", fecha="2026-09-01"),
                item(cups="890201", tipo="CONSULTA", fecha="2026-09-03"),
            ]
        )
        assert regla_doble_facturacion(p, CTX) == []


# ═══════════════════════════════════════════════════════════════════════
class TestUciInjustificada:
    """El otro caso que pidió el auditor. Es la glosa de estancia más común
    y la que más plata mueve."""

    def _uci(self, epicrisis: str, dias_uci: int = 4) -> PayloadFactura:
        return factura(
            atencion={
                "fecha_ingreso": "2026-09-01",
                "fecha_egreso": "2026-09-10",
                "dias_estancia": 9,
                "dias_uci": dias_uci,
            },
            items=[
                item(
                    cups="S11201",
                    descripcion="ESTANCIA EN UCI ADULTOS",
                    tipo="ESTANCIA",
                    cantidad=dias_uci,
                    valor_unitario=1_500_000,
                    valor_total=dias_uci * 1_500_000,
                )
            ],
            epicrisis=epicrisis,
        )

    def test_uci_sin_un_solo_criterio_de_gravedad_avisa(self):
        p = self._uci(
            "Paciente que ingresa por dolor abdominal. Evoluciona bien, tolera vía oral, "
            "se da egreso en buenas condiciones."
        )
        alertas = regla_uci_sin_soporte(p, CTX)
        assert len(alertas) == 1
        assert alertas[0].codigo_glosa == "CL0101"
        assert alertas[0].severidad == "ADVERTENCIA"
        assert alertas[0].valor_en_riesgo == 6_000_000

    def test_una_uci_con_apache_y_vasopresor_no_se_toca(self):
        p = self._uci(
            "Ingresa en choque séptico, APACHE II de 24, requiere soporte vasopresor con "
            "noradrenalina y ventilación mecánica invasiva."
        )
        assert regla_uci_sin_soporte(p, CTX) == []

    def test_una_uci_con_sofa_tampoco(self):
        assert (
            regla_uci_sin_soporte(self._uci("SOFA 11 al ingreso, falla multiorgánica."), CTX) == []
        )

    def test_sin_epicrisis_se_avisa_y_se_dice_por_que(self):
        p = self._uci("")
        alertas = regla_uci_sin_soporte(p, CTX)
        assert len(alertas) == 1
        assert "no mandó epicrisis" in alertas[0].detalle

    def test_una_factura_sin_uci_no_le_importa_esta_regla(self):
        p = factura(items=[item(cups="890201", descripcion="CONSULTA")], epicrisis="Consulta.")
        assert regla_uci_sin_soporte(p, CTX) == []


# ═══════════════════════════════════════════════════════════════════════
class TestContratoVigente:
    def test_una_atencion_despues_de_vencido_el_contrato_avisa(self):
        """Caso real del hospital: el contrato de AURORA venció el 31-08-2026."""
        p = factura(eps="AURORA", atencion={"fecha_ingreso": "2026-09-02"})
        alertas = regla_contrato_vigente(p, CTX)
        assert len(alertas) == 1
        assert alertas[0].severidad == "ADVERTENCIA"
        # Riesgo de proceso, no de pesos: no infla la cifra de la factura.
        assert alertas[0].valor_en_riesgo == 0.0

    def test_dentro_de_la_vigencia_no_dice_nada(self):
        p = factura(eps="AURORA", atencion={"fecha_ingreso": "2026-03-02"})
        assert regla_contrato_vigente(p, CTX) == []

    def test_una_eps_que_no_esta_en_la_malla_no_se_juzga(self):
        p = factura(eps="EPS QUE NO EXISTE SA", atencion={"fecha_ingreso": "2026-09-02"})
        assert regla_contrato_vigente(p, CTX) == []


# ═══════════════════════════════════════════════════════════════════════
class TestElRiesgoNoSeCuentaDosVeces:
    def test_dos_alertas_del_mismo_item_valen_la_mayor(self):
        alertas = [
            Alerta(item="511002", valor_en_riesgo=300_000),
            Alerta(item="511002", valor_en_riesgo=1_200_000),
        ]
        assert consolidar_valor_en_riesgo(alertas, 5_000_000) == 1_200_000

    def test_las_alertas_de_items_distintos_si_se_suman(self):
        alertas = [
            Alerta(item="511002", valor_en_riesgo=300_000),
            Alerta(item="890201", valor_en_riesgo=120_000),
        ]
        assert consolidar_valor_en_riesgo(alertas, 5_000_000) == 420_000

    def test_el_riesgo_nunca_supera_el_valor_de_la_factura(self):
        alertas = [Alerta(valor_en_riesgo=9_000_000), Alerta(item="X", valor_en_riesgo=9_000_000)]
        assert consolidar_valor_en_riesgo(alertas, 1_000_000) == 1_000_000

    def test_sin_alertas_el_riesgo_es_cero(self):
        assert consolidar_valor_en_riesgo([], 1_000_000) == 0.0


# ═══════════════════════════════════════════════════════════════════════
class TestLaCadenaCompleta:
    def test_una_regla_rota_no_tumba_a_las_demas(self, monkeypatch):
        import app.services.preauditoria_reglas_duras as mod

        def explota(payload, ctx):
            raise RuntimeError("regla defectuosa")

        monkeypatch.setattr(mod, "REGLAS_DURAS", (explota, mod.regla_aritmetica))
        p = factura(
            items=[item(cups="890201", cantidad=2, valor_unitario=50_000, valor_total=150_000)]
        )
        alertas = correr_reglas_duras(p, CTX)
        assert len(alertas) == 1 and alertas[0].regla == "aritmetica_linea"

    def test_un_bloqueo_no_corta_la_cadena(self):
        """El facturador quiere ver TODOS los reparos de una vez."""
        p = factura(
            paciente={"sexo": "M", "edad_anios": 40},
            atencion={"fecha_ingreso": "2026-09-05", "fecha_egreso": "2026-09-01"},
            items=[
                item(
                    cups="740101",
                    descripcion="PARTO VAGINAL ESPONTÁNEO",
                    cantidad=2,
                    valor_unitario=100_000,
                    valor_total=900_000,
                )
            ],
            valor_total=900_000,
        )
        reglas = {a.regla for a in correr_reglas_duras(p, CTX)}
        assert {"aritmetica_linea", "fechas_invertidas", "cruce_genero"} <= reglas

    def test_una_factura_sana_no_produce_ni_una_alerta(self):
        p = factura(
            eps="EPS QUE NO EXISTE SA",
            paciente={"sexo": "F", "edad_anios": 34},
            atencion={
                "fecha_ingreso": "2026-09-01",
                "fecha_egreso": "2026-09-03",
                "dias_estancia": 2,
            },
            items=[
                item(
                    cups="890201",
                    descripcion="CONSULTA DE PRIMERA VEZ",
                    tipo="CONSULTA",
                    cantidad=1,
                    valor_unitario=60_000,
                    valor_total=60_000,
                    fecha="2026-09-01",
                )
            ],
            valor_total=60_000,
        )
        assert correr_reglas_duras(p, CTX) == []


# ═══════════════════════════════════════════════════════════════════════
class TestDeduccionDeTipo:
    @pytest.mark.parametrize(
        "descripcion,esperado",
        [
            ("ESTANCIA EN UCI ADULTOS", "ESTANCIA"),
            ("CONSULTA DE PRIMERA VEZ POR ESPECIALISTA", "CONSULTA"),
            ("HONORARIOS DE ANESTESIA", "ANESTESIA"),
            ("DERECHOS DE SALA DE CIRUGÍA", "SALA"),
            ("TRASLADO ASISTENCIAL EN AMBULANCIA", "TRASLADO"),
            ("HEMOGRAMA COMPLETO", "APOYO_DIAGNOSTICO"),
            ("TERAPIA RESPIRATORIA", "APOYO_TERAPEUTICO"),
            ("COLECISTECTOMÍA LAPAROSCÓPICA", "QUIRURGICO"),
        ],
    )
    def test_el_tipo_se_deduce_de_la_descripcion(self, descripcion, esperado):
        from app.services.preauditoria_contrato import ItemFactura

        assert tipo_de(ItemFactura(descripcion=descripcion)) == esperado

    def test_lo_que_declara_el_his_manda_sobre_la_deduccion(self):
        from app.services.preauditoria_contrato import ItemFactura

        assert tipo_de(ItemFactura(descripcion="HEMOGRAMA", tipo="MEDICAMENTO")) == "MEDICAMENTO"
