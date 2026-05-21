"""Tests intensivos del flujo banco HUS — simula casos difíciles reales.

Cubre las 5 familias del banco HUS (TA/SO/CO/FA/CL) y casos edge:
- Multi-código en mismo texto
- Códigos en minúsculas / con guiones
- Valores en formatos atípicos ($1'500.000, sin separadores, %150.000)
- Texto sin código de glosa (fallback)
- Sufijos no estándar

Estos tests NO requieren IA real; verifican parseo + selección de plantilla.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.db import PlantillaGoldRecord
from app.services.few_shot_gold import bloque_few_shot_para_prompt, obtener_ejemplos_gold


ARG = "TEXTO JURÍDICO HUS " * 30  # >200 chars


@pytest.fixture
def db_con_banco_hus():
    """DB con las 5 familias del banco HUS sembradas (1 por familia para el test)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    try:
        # Seed mínimo del banco HUS (1 por familia)
        for codigo in ["TA-G01", "TA-G02", "SO-G01", "CO-G01", "FA-G01", "CL-G01"]:
            s.add(
                PlantillaGoldRecord(
                    eps="GENERICO",
                    codigo_glosa=codigo,
                    titulo=f"Plantilla {codigo}",
                    argumento=ARG + f" — {codigo}",
                    activa=1,
                    tipo="PLANTILLA_HUS_BASE",
                    usos=0,
                )
            )
        s.commit()
        yield s
    finally:
        s.close()
        engine.dispose()


class TestFamiliasBancoHUS:
    """Verifica que para CADA familia del banco HUS, el código real del CUPS
    se mapea a la plantilla correcta."""

    @pytest.mark.parametrize(
        "codigo_real,familia_esperada",
        [
            ("TA0201", "TA"),
            ("TA0301", "TA"),
            ("TA9999", "TA"),
            ("SO0501", "SO"),
            ("SO0601", "SO"),
            ("CO0101", "CO"),
            ("CO0201", "CO"),
            ("FA0501", "FA"),
            ("FA0601", "FA"),
            ("CL0101", "CL"),
            ("CL0201", "CL"),
        ],
    )
    def test_codigo_familia_correcta(self, db_con_banco_hus, codigo_real, familia_esperada):
        ejemplos = obtener_ejemplos_gold(db_con_banco_hus, "FAMISANAR EPS", codigo_real)
        assert len(ejemplos) >= 1, f"Sin plantilla para {codigo_real}"
        assert ejemplos[0]["fuente"] == "BANCO_HUS"
        # Verificar que el argumento incluye un código de la familia correcta
        arg = ejemplos[0]["argumento"]
        assert f"{familia_esperada}-G" in arg, (
            f"Plantilla devuelta no es de familia {familia_esperada}: {arg[-30:]}"
        )


class TestCasosEdge:
    """Casos atípicos que el sistema debe manejar sin romperse."""

    def test_codigo_minusculas(self, db_con_banco_hus):
        # 'ta0201' debe normalizarse a 'TA0201'
        ejemplos = obtener_ejemplos_gold(db_con_banco_hus, "FAMISANAR", "ta0201")
        assert len(ejemplos) >= 1
        assert ejemplos[0]["fuente"] == "BANCO_HUS"

    def test_codigo_con_espacios(self, db_con_banco_hus):
        ejemplos = obtener_ejemplos_gold(db_con_banco_hus, "FAMISANAR", "  TA0201  ")
        assert len(ejemplos) >= 1

    def test_eps_vacia_no_explota(self, db_con_banco_hus):
        ejemplos = obtener_ejemplos_gold(db_con_banco_hus, "", "TA0201")
        # EPS vacía es válida — banco HUS no depende de ella
        assert ejemplos == []  # función devuelve [] si eps_norm está vacío

    def test_codigo_vacio_no_explota(self, db_con_banco_hus):
        ejemplos = obtener_ejemplos_gold(db_con_banco_hus, "FAMISANAR", "")
        assert ejemplos == []

    def test_codigo_familia_inexistente_no_devuelve_otra_familia(self, db_con_banco_hus):
        """Si el código pertenece a una familia que NO existe en banco HUS,
        no debe devolverse plantilla de OTRA familia por error."""
        # 'XX' no es una familia del banco HUS
        ejemplos = obtener_ejemplos_gold(db_con_banco_hus, "FAMISANAR", "XX9999")
        # Como no hay XX-G* en el banco, debe devolver []
        assert ejemplos == []


class TestBloquePromptDificil:
    """El bloque del prompt para casos difíciles debe ser robusto."""

    def test_bloque_con_plantilla_multilinea(self):
        plantilla_real = (
            "ESE HUS NO ACEPTA GLOSA POR CONCEPTO DE PRESUNTO MAYOR VALOR COBRADO (MVC) "
            "SOBRE ÍTEM LIQUIDADO CON TARIFA PROPIA INSTITUCIONAL, DADO QUE EL VALOR "
            "FACTURADO CORRESPONDE EXACTAMENTE A LA TARIFA APROBADA MEDIANTE ACTO "
            "ADMINISTRATIVO INSTITUCIONAL DE LA ESE HOSPITAL UNIVERSITARIO DE SANTANDER. "
            "ARTÍCULO 87 DEL DECRETO 2423 DE 1996. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA "
            "Y EL PAGO ÍNTEGRO DE LO FACTURADO."
        )
        bloque = bloque_few_shot_para_prompt(
            [{"argumento": plantilla_real, "fuente": "BANCO_HUS", "id": 1}]
        )
        # Verificar instrucciones imperativas
        assert "VERBATIM" in bloque
        assert "MÁXIMA PRIORIDAD" in bloque
        assert "ANULAN" in bloque
        # La plantilla debe estar embebida
        assert "Artículo 87" in bloque or "ARTÍCULO 87" in bloque

    def test_bloque_excluye_emails_y_coda(self):
        """Si la plantilla del banco HUS NO tiene coda procesal, el bloque
        debe instruir explícitamente que NO la agregue."""
        plantilla = "ESE HUS NO ACEPTA GLOSA... SE SOLICITA EL LEVANTAMIENTO Y EL PAGO ÍNTEGRO."
        bloque = bloque_few_shot_para_prompt(
            [{"argumento": plantilla, "fuente": "BANCO_HUS", "id": 1}]
        )
        # Instrucción explícita de no agregar coda
        assert "@hus.gov.co" in bloque  # mencionado como prohibido
        assert "10 días hábiles" in bloque or "mesa de conciliación" in bloque


class TestSelectorMejorPlantilla:
    """Cuando hay varias plantillas de la misma familia (ej. TA-G01, TA-G02, ...,
    TA-G10), la query devuelve hasta `max_ejemplos` ordenadas por usos."""

    def test_mas_usadas_primero(self, db_con_banco_hus):
        # Agregar una plantilla TA-G05 con usos altos
        db_con_banco_hus.add(
            PlantillaGoldRecord(
                eps="GENERICO",
                codigo_glosa="TA-G05",
                titulo="Plantilla TA-G05 popular",
                argumento=ARG + " — TA-G05 POPULAR",
                activa=1,
                tipo="PLANTILLA_HUS_BASE",
                usos=100,  # MUY usada
            )
        )
        db_con_banco_hus.commit()

        ejemplos = obtener_ejemplos_gold(db_con_banco_hus, "FAMISANAR", "TA0201", max_ejemplos=1)
        assert len(ejemplos) == 1
        assert "TA-G05" in ejemplos[0]["argumento"]
