"""El Excel de POSITIVA no puede cargarse con el SOAT pleno (24-08-2026).

QUÉ PASÓ. Se subió el Excel «TARIFAS ESE HUS 2025 - POSITIVA» por la pantalla
de Tarifas. La hoja SOAT trae dos columnas de plata: «VALOR 2025» (el SOAT
pleno) y «SOAT -15%» (lo pactado en el Otrosí 03 del contrato 0525/2017). El
importador conocía VALOR 2025 y no conocía SOAT -15%, así que cargó 4.742
tarifas con el valor pleno: $915.051 donde lo pactado era $777.793.

Con eso, cada dictamen de tarifas de POSITIVA defendería un valor 15% más
alto que el contrato: la EPS ratifica la glosa y el dictamen es falso. Es la
prioridad número 1 de este proyecto.

Y DOS MÁS DEL MISMO ARCHIVO:

- Excel guarda el CUPS como número y se come el cero de adelante (010101 →
  10101). Como el sistema compara texto exacto, esas tarifas quedaban
  invisibles para el motor: decía «sin tarifa pactada» teniéndola.
- El mismo CUPS aparece varias veces con valores que NO coinciden (103204
  traía cinco, de $94.399 a $1.926.567). Cargarlos todos deja que el azar
  del orden decida cuál cita el dictamen. La regla del proyecto es no
  inventar: se omiten y se avisa cuáles, para que el auditor decida.
"""

from __future__ import annotations

import io

import openpyxl
import pytest

from app.services.tarifas_excel_parser import parsear_excel_tarifas


def _excel(hojas: dict[str, list[list]]) -> bytes:
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for fila in filas:
            ws.append(fila)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


ENCABEZADO_SOAT = [
    "CUPS",
    "DESCRIPCIÓN CUPS",
    "HOMOLOGO SOAT",
    "DESCRIPCIÓN SOAT",
    " VALOR 2025 ",
    "SOAT -15%",
]
ENCABEZADO_INST = [
    "CUPS",
    "DESCRIPCIÓN CUPS",
    "COD. PROPIO",
    "DESCRIPCIÓN PROPIA",
    "TARIFA 2025",
    "ESPECIALIDAD",
    "SERVICIO",
]


class TestLaColumnaPactadaGana:
    def test_carga_el_soat_menos_15_y_no_el_pleno(self):
        """El caso literal del 24-08: 10101 a $915.051 en vez de $777.793,35."""
        r = parsear_excel_tarifas(
            _excel(
                {
                    "SOAT": [
                        ENCABEZADO_SOAT,
                        [
                            10101,
                            "PUNCION CISTERNAL, VIA LATERAL",
                            1250,
                            "PUNCION CISTERNAL",
                            915051,
                            777793.35,
                        ],
                    ],
                }
            )
        )
        assert len(r["filas"]) == 1
        assert r["filas"][0]["valor_pactado"] == 777793.35, (
            "Cargó el SOAT pleno: el dictamen defendería un valor 15% más "
            "alto que el contrato y la glosa se ratifica."
        )

    def test_tambien_con_el_signo_pegado_o_con_espacios(self):
        for encabezado in ("SOAT-15%", "SOAT - 15 %", "SOAT –15%"):
            r = parsear_excel_tarifas(
                _excel(
                    {
                        "SOAT": [
                            ["CUPS", "DESCRIPCIÓN CUPS", " VALOR 2025 ", encabezado],
                            [10101, "PUNCION", 915051, 777793.35],
                        ],
                    }
                )
            )
            assert r["filas"][0]["valor_pactado"] == 777793.35, encabezado

    def test_sin_columna_de_descuento_todo_sigue_igual(self):
        """La hoja INSTITUCIONALES no trae descuento: manda TARIFA 2025."""
        r = parsear_excel_tarifas(
            _excel(
                {
                    "INSTITUCIONALES": [
                        ENCABEZADO_INST,
                        [
                            13205,
                            "SECCION DEL CUERPO CALLOSO",
                            "013205H",
                            "SECCION",
                            8771100,
                            "NEUROCIRUGÍA",
                            "CIRUGÍA",
                        ],
                    ],
                }
            )
        )
        assert r["filas"][0]["valor_pactado"] == 8771100


class TestElCeroDeAdelante:
    def test_un_cups_de_5_digitos_se_guarda_a_6(self):
        r = parsear_excel_tarifas(
            _excel(
                {
                    "SOAT": [
                        ENCABEZADO_SOAT,
                        [10101, "PUNCION", 1250, "PUNCION", 915051, 777793.35],
                    ],
                }
            )
        )
        assert r["filas"][0]["codigo_cups"] == "010101"

    def test_uno_de_6_y_uno_con_letra_no_se_tocan(self):
        r = parsear_excel_tarifas(
            _excel(
                {
                    "SOAT": [
                        ENCABEZADO_SOAT,
                        [890283, "CONSULTA", 1101, "CONSULTA", 100000, 85000],
                        ["890283H", "CONSULTA HUS", 1101, "CONSULTA", 100000, 85000],
                    ],
                }
            )
        )
        codigos = {f["codigo_cups"] for f in r["filas"]}
        assert codigos == {"890283", "890283H"}

    def test_a_uno_de_4_no_se_le_inventa_nada(self):
        """Los capítulos del CUPS van del 01 al 09: a un código de 4 dígitos
        no le falta UN cero, y rellenarlo inventaría un código."""
        r = parsear_excel_tarifas(
            _excel(
                {
                    "SOAT": [
                        ENCABEZADO_SOAT,
                        [1250, "PUNCION", 1250, "PUNCION", 915051, 777793.35],
                    ],
                }
            )
        )
        assert r["filas"][0]["codigo_cups"] == "1250"


class TestLosAnexosDeMedicamentosDelDispensario:
    """El «TARIFAS DEL CONTRATO» 440 del Dispensario trae 8 anexos de
    medicamentos e insumos (~3.000 códigos CUM, FMQ, QX) y el lector se los
    saltaba TODOS en silencio, por tres razones distintas que estas pruebas
    fijan una a una (24-08-2026)."""

    def test_reconoce_codigo_cum_con_precio_de_venta(self):
        r = parsear_excel_tarifas(
            _excel(
                {
                    "ANEXO 02": [
                        ["", "ANEXO 02 - MEDICAMENTOS", "", ""],
                        ["", "", "", ""],
                        [
                            "CODIGO CUM",
                            "CODIGO AGRUPAMIENTO",
                            "NOMBRE DEL MEDICAMENTO",
                            "PRECIO DE VENTA",
                        ],
                        ["20028352-08", "J05AF06", "ABACAVIR TAB 300 MG", 900],
                    ],
                }
            )
        )
        assert len(r["filas"]) == 1
        assert r["filas"][0]["codigo_cups"] == "20028352-08"
        assert r["filas"][0]["valor_pactado"] == 900

    def test_un_encabezado_de_TRES_columnas_tambien_es_tarifario(self):
        """Era «mínimo 4 columnas»: los anexos 05/06 (CODIGO | NOMBRE |
        PRECIO DE VENTA) perdían 2.000 dispositivos médicos en silencio."""
        r = parsear_excel_tarifas(
            _excel(
                {
                    "ANEXO 05": [
                        ["ANEXO 05 - DISPOSITIVOS", "", ""],
                        ["", "", ""],
                        ["CODIGO", "NOMBRE", "PRECIO DE VENTA"],
                        ["FMQ1764", "ACIDOS GRASOS HIPEROXIGENADOS", 135200],
                    ],
                }
            )
        )
        assert len(r["filas"]) == 1
        assert r["filas"][0]["codigo_cups"] == "FMQ1764"

    def test_cuando_TARIFA_es_un_texto_manda_la_OFERTA(self):
        """La PROPUESTA trae una columna TARIFA con el TEXTO «PROPIA» y el
        valor real en OFERTA: si gana TARIFA, la hoja entera se lee como
        ceros y se descarta sin decir nada."""
        r = parsear_excel_tarifas(
            _excel(
                {
                    "TARIFAS PROPIAS": [
                        [
                            "CUPS",
                            "DESCRIPCION CUPS",
                            "CODIGO IPS",
                            "DESCRIPCION IPS",
                            "TARIFA",
                            "OFERTA",
                        ],
                        [
                            "039001",
                            "INSERCION DE CATETER",
                            "039001H",
                            "INSERCION",
                            "PROPIA",
                            1689585,
                        ],
                    ],
                }
            )
        )
        assert len(r["filas"]) == 1
        assert r["filas"][0]["valor_pactado"] == 1689585


class TestLosRepetidosQueSeContradicen:
    def test_dos_valores_distintos_no_se_cargan_y_se_avisa(self):
        """El 103204 real traía CINCO valores. Cargarlos deja que el orden de
        llegada decida cuál cita el dictamen."""
        r = parsear_excel_tarifas(
            _excel(
                {
                    "SOAT": [
                        ENCABEZADO_SOAT,
                        [103204, "TERAPIA", 1250, "X", 111111, 94399.3],
                        [103204, "TERAPIA", 1301, "Y", 222222, 777379.4],
                    ],
                }
            )
        )
        assert r["filas"] == []
        assert len(r["errores"]) == 1
        aviso = r["errores"][0]
        assert "103204" in aviso
        assert "94.399" in aviso and "777.379" in aviso
        assert "dictámenes falsos" in aviso or "dictamenes falsos" in aviso

    def test_tambien_si_la_contradiccion_es_entre_hojas(self):
        """El mismo CUPS en la hoja SOAT y en la INSTITUCIONALES con valores
        distintos: el contrato dice cuál rige, el archivo no."""
        r = parsear_excel_tarifas(
            _excel(
                {
                    "SOAT": [ENCABEZADO_SOAT, [48201, "INYECCION", 1250, "X", 727853, 618675]],
                    "INSTITUCIONALES": [
                        ENCABEZADO_INST,
                        [48201, "INYECCION", "048201H", "INYECCION", 500000, "DOLOR", "CX"],
                    ],
                }
            )
        )
        assert r["filas"] == []
        assert "048201" in r["errores"][0]

    def test_repetido_con_el_MISMO_valor_se_carga_una_vez(self):
        """Repetir no es contradecirse."""
        r = parsear_excel_tarifas(
            _excel(
                {
                    "SOAT": [
                        ENCABEZADO_SOAT,
                        [10101, "PUNCION", 1250, "X", 915051, 777793.35],
                        [10101, "PUNCION", 1250, "X", 915051, 777793.35],
                    ],
                }
            )
        )
        assert len(r["filas"]) == 1
        assert r["errores"] == []

    def test_los_limpios_no_pagan_por_los_conflictivos(self):
        r = parsear_excel_tarifas(
            _excel(
                {
                    "SOAT": [
                        ENCABEZADO_SOAT,
                        [10101, "PUNCION", 1250, "X", 915051, 777793.35],
                        [103204, "TERAPIA", 1250, "X", 111111, 94399.3],
                        [103204, "TERAPIA", 1301, "Y", 222222, 777379.4],
                    ],
                }
            )
        )
        assert [f["codigo_cups"] for f in r["filas"]] == ["010101"]


class TestElLookupEncuentraLoQueYaQuedoGuardadoSinCero:
    """Las 4.742 que entraron el 24-08 quedaron sin el cero (10101). Mientras
    se recargan, una glosa que llega con 010101 tiene que encontrarlas."""

    @pytest.fixture()
    def db(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool

        from app.models.db import Base

        e = create_engine(
            "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(e)
        s = sessionmaker(bind=e)()
        try:
            yield s
        finally:
            s.close()
            e.dispose()

    def _tarifa(self, db, cups, valor=777793.35):
        from app.models.db import TarifaContratadaRecord

        db.add(
            TarifaContratadaRecord(
                eps="POSITIVA",
                codigo_cups=cups,
                descripcion="PUNCION",
                valor_pactado=valor,
                tipo_tarifa="VALOR_FIJO",
                activa=1,
            )
        )
        db.commit()

    def test_glosa_con_cero_encuentra_tarifa_sin_cero(self, db):
        from app.services.tarifa_lookup_service import _buscar

        self._tarifa(db, "10101")
        fila = _buscar(db, "POSITIVA", "010101")
        assert fila is not None and fila.valor_pactado == 777793.35

    def test_y_al_reves(self, db):
        from app.services.tarifa_lookup_service import _buscar

        self._tarifa(db, "010101")
        assert _buscar(db, "POSITIVA", "10101") is not None

    def test_un_codigo_con_letra_no_entra_en_ese_juego(self, db):
        from app.services.tarifa_lookup_service import _buscar

        self._tarifa(db, "890283H")
        assert _buscar(db, "POSITIVA", "0890283H") is None
