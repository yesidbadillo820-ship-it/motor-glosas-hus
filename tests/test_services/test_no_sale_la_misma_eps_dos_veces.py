"""La misma entidad, escrita de dos maneras, salía dos veces en el desplegable.

10-09-2026. Yesid abrió «EPS / Entidad Pagadora» del botón Analizar y contó
los pares: SALUD TOTAL y SALUD TOTAL EPS, SURA y SURA EPS, ADRES ACCIDENTES
DE TRANSITO y ADRES-ACCIDENTES DE TRANSITO, DISPENSARIO MEDICO y DIRECCION
DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA.

Dos renglones que parecen dos entidades obligan al auditor a adivinar cuál
elegir, y elegir mal manda el dictamen con el nombre que la EPS no reconoce.

La otra mitad de la prueba es la que impide el arreglo fácil: hay sufijos
que SÍ distinguen y fundirlos costaría plata —UVT/UVB es la unidad con la
que se liquida el SOAT, CONTRIBUTIVO/SUBSIDIADO es el régimen—.
"""

from __future__ import annotations

import pytest

from app.services.catalogo_eps import EPS_CONOCIDAS, eps_seleccionables, misma_entidad

# El desplegable tal como lo fotografió Yesid el 10-09-2026.
DESPLEGABLE_REAL = [
    "ADRES ACCIDENTES DE TRANSITO",
    "ADRES-ACCIDENTES DE TRANSITO",
    "ALIANZA MEDELLIN ANTIOQUIA EPS SAS CONTRIBUTIVO",
    "ALIANZA MEDELLIN ANTIOQUIA EPS SAS SUBSIDIADO",
    "ASEGURADORA SOLIDARIA SEGUROS",
    "AURORA",
    "AXA COLPATRIA SEGUROS S.A. SOAT",
    "AXA COLPATRIA SEGUROS S.A. SOAT - UVT",
    "AXA COLPATRIA SEGUROS S.A. SOAT UVB",
    "CAJACOPI",
    "COLMENA ARL",
    "COMFENALCO",
    "COMPAÑIA MUNDIAL DE SEGUROS S.A. SOAT UVB",
    "COMPENSAR",
    "COOSALUD",
    "DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA",
    "DISPENSARIO MEDICO",
    "ECOOPSOS",
    "EMSSANAR",
    "HOSPITAL NAVAL NIVEL III DE CARTAGENA",
    "LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT - UVT",
    "LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB",
    "MUTUAL SER",
    "NUEVA EPS",
    "POLICIA NACIONAL",
    "POSITIVA",
    "PPL",
    "PRECIMED",
    "PROTEGER EPS S.A.S. CONTRIBUTIVO",
    "PROTEGER EPS S.A.S. SUBSIDIADO",
    "SALUD MIA",
    "SALUD TOTAL",
    "SALUD TOTAL EPS",
    "SANITAS",
    "SAVIA",
    "SUMIMEDICAL",
    "SURA",
    "SURA EPS",
]


class TestLosDuplicadosQueVioElAuditor:
    @pytest.mark.parametrize(
        "a,b",
        [
            ("ADRES ACCIDENTES DE TRANSITO", "ADRES-ACCIDENTES DE TRANSITO"),
            ("SALUD TOTAL", "SALUD TOTAL EPS"),
            ("SURA", "SURA EPS"),
            (
                "DISPENSARIO MEDICO",
                "DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA",
            ),
        ],
    )
    def test_son_la_misma_entidad(self, a, b):
        assert misma_entidad(a, b), f"«{a}» y «{b}» son el mismo pagador"

    def test_del_desplegable_real_desaparece_el_duplicado(self):
        salida = eps_seleccionables(DESPLEGABLE_REAL)
        for repetido in ("ADRES-ACCIDENTES DE TRANSITO", "SALUD TOTAL EPS", "SURA EPS"):
            assert repetido not in salida, f"«{repetido}» seguía saliendo aparte"
        assert "SALUD TOTAL" in salida
        assert "SURA" in salida
        assert "ADRES ACCIDENTES DE TRANSITO" in salida

    def test_el_dispensario_sale_una_sola_vez(self):
        salida = eps_seleccionables(DESPLEGABLE_REAL)
        dispensarios = [e for e in salida if "DISPENSARIO" in e]
        assert len(dispensarios) == 1, dispensarios


class TestLosSufijosQueSiDistinguen:
    """Fundir estos costaría plata: la unidad del SOAT y el régimen."""

    @pytest.mark.parametrize(
        "a,b,por_que",
        [
            (
                "AXA COLPATRIA SEGUROS S.A. SOAT - UVT",
                "AXA COLPATRIA SEGUROS S.A. SOAT UVB",
                "UVT y UVB son unidades distintas de liquidación del SOAT",
            ),
            (
                "LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT - UVT",
                "LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB",
                "idem, y es el pagador con más glosas del export real",
            ),
            (
                "PROTEGER EPS S.A.S. CONTRIBUTIVO",
                "PROTEGER EPS S.A.S. SUBSIDIADO",
                "el régimen cambia la norma aplicable",
            ),
            (
                "ALIANZA MEDELLIN ANTIOQUIA EPS SAS CONTRIBUTIVO",
                "ALIANZA MEDELLIN ANTIOQUIA EPS SAS SUBSIDIADO",
                "idem",
            ),
            (
                "AXA COLPATRIA SEGUROS S.A. SOAT",
                "AXA COLPATRIA SEGUROS S.A. SOAT UVB",
                "el nombre pelado no dice la unidad; suponerla sería inventar la tarifa",
            ),
        ],
    )
    def test_no_se_funden(self, a, b, por_que):
        assert not misma_entidad(a, b), por_que

    def test_las_dos_previsoras_siguen_en_la_lista(self):
        salida = eps_seleccionables(DESPLEGABLE_REAL)
        assert "LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT - UVT" in salida
        assert "LA PREVISORA S A COMPAÑIA DE SEGUROS SOAT UVB" in salida

    def test_los_dos_regimenes_de_proteger_siguen(self):
        salida = eps_seleccionables(DESPLEGABLE_REAL)
        assert "PROTEGER EPS S.A.S. CONTRIBUTIVO" in salida
        assert "PROTEGER EPS S.A.S. SUBSIDIADO" in salida


class TestNoFundeEntidadesDistintas:
    @pytest.mark.parametrize(
        "a,b",
        [
            ("SALUD TOTAL", "SALUD MIA"),
            ("COMPENSAR", "COMFENALCO"),
            ("POSITIVA", "PPL"),
            ("SURA", "SAVIA"),
            ("NUEVA EPS", "SALUD TOTAL EPS"),
            ("AURORA", "ASEGURADORA SOLIDARIA SEGUROS"),
        ],
    )
    def test_son_pagadores_distintos(self, a, b):
        assert not misma_entidad(a, b)

    def test_adres_pelado_es_el_mismo_adres(self):
        """Respuesta de Cartera (10-09-2026): «ADRES nada de otros nombres».

        Todo lo de ADRES en este hospital entra por accidentes de tránsito,
        así que el nombre pelado y el largo son el mismo renglón. Estuvo un
        rato al revés en el código, por precaución mía; mandó el dato real.
        """
        assert misma_entidad("ADRES", "ADRES ACCIDENTES DE TRANSITO")
        salida = eps_seleccionables(["ADRES", "ADRES ACCIDENTES DE TRANSITO"])
        assert len([e for e in salida if e.startswith("ADRES")]) == 1

    def test_ninguna_pareja_del_catalogo_curado_choca(self):
        """Si esta prueba se cae, la regla se volvió demasiado laxa."""
        choques = [
            (a, b)
            for i, a in enumerate(EPS_CONOCIDAS)
            for b in EPS_CONOCIDAS[i + 1 :]
            if misma_entidad(a, b)
        ]
        assert not choques, f"la regla fundió entidades reales del catálogo: {choques}"

    def test_el_catalogo_solo_sigue_saliendo_entero(self):
        assert set(eps_seleccionables()) == set(EPS_CONOCIDAS)


class TestQueNombreSobrevive:
    def test_gana_el_nombre_con_el_que_esta_firmado_el_contrato(self):
        """El dictamen debe citar el nombre del contrato, no el del historial."""
        salida = eps_seleccionables(
            ["SALUD TOTAL EPS"],  # historial, sucio
            preferidas=["SALUD TOTAL EPS EJEMPLO DE CONTRATO"],
        )
        assert "SALUD TOTAL EPS EJEMPLO DE CONTRATO" in salida
        assert "SALUD TOTAL EPS" not in salida

    def test_el_dispensario_sale_con_su_nombre_oficial_si_tiene_contrato(self):
        oficial = "DIRECCION DE SANIDAD EJERCITO - DISPENSARIO MEDICO BUCARAMANGA"
        salida = eps_seleccionables(["DISPENSARIO MEDICO"], preferidas=[oficial])
        assert oficial in salida
        assert "DISPENSARIO MEDICO" not in salida

    def test_sin_contrato_gana_el_catalogo_curado_sobre_el_historial(self):
        salida = eps_seleccionables(["SALUD TOTAL EPS"])
        assert "SALUD TOTAL" in salida
        assert "SALUD TOTAL EPS" not in salida


class TestLoQueYaFuncionabaSigueFuncionando:
    def test_sale_ordenado_y_en_mayuscula(self):
        salida = eps_seleccionables(["  zzz inventada  ", "aaa inventada"])
        assert salida == sorted(salida)
        assert "ZZZ INVENTADA" in salida and "AAA INVENTADA" in salida

    def test_ignora_vacios_y_none(self):
        assert set(eps_seleccionables(["", None, "  "])) == set(EPS_CONOCIDAS)

    def test_una_entidad_nueva_de_verdad_si_entra(self):
        assert "COMFAMA" in eps_seleccionables(["COMFAMA"])

    def test_no_deja_ningun_repetido_exacto(self):
        salida = eps_seleccionables(DESPLEGABLE_REAL, DESPLEGABLE_REAL)
        assert len(salida) == len(set(salida))
