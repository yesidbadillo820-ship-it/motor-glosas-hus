"""Los medicamentos van a Servicio Farmacéutico (21-08-2026).

**Decisión de Yesid**, tomada después de mirar los datos reales del DGH del 19
de agosto (669 filas).

LO QUE SE ENCONTRÓ MIRANDO ESOS DATOS, y conviene que quede escrito: el centro
de costos **no es una propiedad del servicio**. El mismo `CATETER INTRAVENOSO
20` aparece en Urgencias, Sala de Partos **y** Radiografía — es el área donde
estaba el paciente. Por eso las «371 filas sin propuesta» nunca fueron un
hueco: eran las reglas negándose, con razón, a adivinar.

Con la decisión tomada, lo que faltaba era reconocer el medicamento cuando el
archivo **no trae la columna «tipo de elemento»**, que es la mayoría de las
veces.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import preauditar_glosas_adres as pa  # noqa: E402


class TestMedicamentosEInsumosAFarmaceutico:
    @pytest.mark.parametrize(
        "servicio",
        [
            "ACETAMINOFEN TAB X 500 MG",
            "ACIDO TRANEXAMICO AMP 500 MG/5 ML",
            "CEFAZOLINA VIAL X 1 G (1000 MG)",
            "ACETAMINOFEN JARABE 150MG/ML FCO X 60 ML",
            "DIPIRONA SODICA 1G/2ML SOL INY",
            "ZINC SULFATO 2 MG/ML FRASCO X 120 ML",
            "SOLUCION SALINA NORMAL BOLSA X 500 ML",
        ],
    )
    def test_medicamentos_sin_tipo_de_elemento(self, servicio):
        """Sin la columna «tipo de elemento» estos quedaban SIN propuesta y el
        gestor los llenaba a mano, uno por uno."""
        assert "FARMACEUTICO" in pa.centro_de_costos("", servicio)

    @pytest.mark.parametrize(
        "servicio",
        [
            "CATETER INTRAVENOSO 20",
            "SONDA NELATON 14 FR",
            "AGUJA DESECHABLE NO. 18 X 1 PULGADA HIPODERMICA",
            "BOLSA RECOLECTORA DE ORINA ADULTO",
            "ELECTRODO ECG ADULTO REF 302A",
            "CANULA NASAL PARA OXIGENO ADULTO TERMINAL 5 YARDAS",
            "EQUIPO DE BOMBA DE INFUSION (ESTANDAR) REF 14001",
        ],
    )
    def test_insumos_sin_tipo_de_elemento(self, servicio):
        assert "FARMACEUTICO" in pa.centro_de_costos("", servicio)

    def test_una_palabra_no_engancha_dentro_de_otra(self):
        """«AMP» no puede casar con AMPUTACION ni «TAB» con TABIQUE: los
        patrones están anclados a palabra completa."""
        assert "FARMACEUTICO" not in pa.centro_de_costos("", "AMPUTACION DE DEDO DEL PIE")
        assert "FARMACEUTICO" not in pa.centro_de_costos("", "CORRECCION DE TABIQUE NASAL")


class TestElExamenNoEsElMedicamento:
    """El defecto que ya existía y salió a la luz: la pista de laboratorio
    enganchaba medicamentos por «potasio» y «lactato», que también son nombres
    de exámenes."""

    def test_el_medicamento_va_a_farmaceutico(self):
        assert "FARMACEUTICO" in pa.centro_de_costos("", "POTASIO CLORURO AMP X 2 MEQ/ML X 10 ML")
        assert "FARMACEUTICO" in pa.centro_de_costos("", "SOLUCION LACTATO DE RINGER BOLSA X 500ML")

    def test_pero_el_examen_sigue_yendo_a_laboratorio(self):
        """La otra mitad: un examen de verdad no trae forma farmacéutica."""
        assert "LABORATORIO" in pa.centro_de_costos("", "POTASIO EN SUERO U OTROS FLUIDOS")
        assert "LABORATORIO" in pa.centro_de_costos("", "SODIO EN SUERO U OTROS FLUIDOS")


class TestLoObstetricoNoVaAQuirofanos:
    """El hospital carga la cesárea y el parto a Urgencias Ginecobstétricas
    (733101 — «Sala de Partos» en el archivo del DGH), no a quirófanos."""

    @pytest.mark.parametrize(
        "servicio",
        [
            "CESAREA SEGMENTARIA TRANSPERITONEAL",
            "ASISTENCIA DEL PARTO CON O SIN EPISIORRAFIA O PERINEORRAFIA",
            "ABLACION U OCLUSION DE TROMPA DE FALOPIO BILATERAL POR LAPAROTOMIA",
            "AMNIOCENTESIS DIAGNOSTICA",
        ],
    )
    def test_va_a_ginecobstetricas(self, servicio):
        assert "GINECOBSTETRICAS" in pa.centro_de_costos("", servicio)

    def test_lo_quirurgico_de_verdad_sigue_en_quirofanos(self):
        assert "QUIROFANOS" in pa.centro_de_costos(
            "", "CONDROPLASTIA DE ABRASION PARA ZONA PATELAR POR ARTROSCOPIA"
        )


class TestLosSublaboratorios:
    """El hospital separa el laboratorio por especialidad, cada uno con su
    código. Pero el catálogo base de este script son los 45 centros de la hoja
    oculta de la macro, y ahí los sublaboratorios NO están: escribir en la
    macro un centro que ella no reconoce puede romper el cargue."""

    CATALOGO_REAL = list(pa.CATALOGO_CENTROS_COSTOS) + [
        "734003-LABORATORIO - QUIMICA",
        "734004-LABORATORIO - HEMATOLOGIA",
        "734006-LABORATORIO - BACTERIOLOGIA",
    ]

    def test_con_el_catalogo_del_hospital_se_usa_el_fino(self):
        assert (
            pa.centro_de_costos("", "HEMOGRAMA IV", self.CATALOGO_REAL)
            == "734004-LABORATORIO - HEMATOLOGIA"
        )
        assert (
            pa.centro_de_costos("", "TRANSAMINASA GLUTAMICO-PIRUVICA", self.CATALOGO_REAL)
            == "734003-LABORATORIO - QUIMICA"
        )

    def test_sin_esos_codigos_cae_al_generico_y_NO_inventa(self):
        """Nunca se escribe un centro que el catálogo en uso no reconozca."""
        r = pa.centro_de_costos("", "HEMOGRAMA IV")
        assert r == "734001-LABORATORIO CLINICO"

    def test_el_catalogo_base_sigue_siendo_el_de_la_macro(self):
        """45 centros, todos con código. Si esto cambia, la macro puede
        rechazar el cargue."""
        assert len(pa.CATALOGO_CENTROS_COSTOS) == 45
