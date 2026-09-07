"""Tests del pre-auditor del paquete ADRES (tools/preauditar_glosas_adres.py).

Lo que más importa acá es que el texto de respuesta salga **carácter por
carácter igual** al que arma la fórmula de la macro, y que una segunda corrida
no le pise al equipo nada de lo que ya escribió.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

openpyxl = pytest.importorskip("openpyxl")

import preauditar_glosas_adres as pa  # noqa: E402

CABECERA_REPORTE = [
    "Código Habilitación",
    "Número Radicación",
    "Número Factura",
    "Número Paquete",
    "Cantidad Reclamado",
    "Valor Reclamado",
    "Cantidad Aprobada",
    "Valor Aprobado",
    "Valor Glosado",
    "Tip- Num Doc Victima",
    "Consecutivo Item",
    "Tipo Elemento",
    "Cod Elemento",
    "Descripción Elemento",
    "Descripción Glosa",
    "Descripción Anotación",
]

# (factura, tipo, cod, descripción, glosado, causal)
FILAS = [
    ("HUS311371", "Procedimientos", "29117", "Terapia respiratoria: sesión", 31800, ""),
    ("HUS311371", "Medicamentos", "19942122-09", "OMEPRAZOL CAPSULAS", 200, ""),
    (
        "HUS352890",
        "Dispositivos Médicos",
        "2016DM-315",
        "VENDA DE GASA 6 X 5 YARDAS",
        37600,
        "3106- Soporte de material  ausente o incompleto",
    ),
    (
        "HUS352890",
        "Procedimientos",
        "39145",
        "Consulta de urgencias",
        85800,
        "3202- La consulta no esta justificada",
    ),
    (
        "HUS352890",
        "Procedimientos",
        "19749",
        "Nitrógeno uréico",
        17400,
        "4307- El valor del medicamento es superior",
    ),
    (
        "HUS352890",
        "Procedimientos",
        "21102",
        "Brazo, pierna, rodilla, fémur",
        95300,
        "4506- El material hace parte de otro servicio",
    ),
    # Glosada por centavos: la macro no la trae y el bot tampoco.
    ("HUS352890", "Insumo", "X1", "TAPABOCAS", 0.45, "3106- Soporte ausente"),
]


@pytest.fixture()
def reporte(tmp_path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    for _ in range(6):  # el reporte real trae el título arriba
        ws.append([])
    ws.append(CABECERA_REPORTE)
    for factura, tipo, cod, desc, glosado, causal in FILAS:
        ws.append(
            [
                "680010079201",
                "14345108",
                factura,
                "31068",
                1,
                glosado + 1000,
                0,
                1000,
                glosado,
                "CC-91246389",
                "",
                tipo,
                cod,
                desc,
                causal,
                "",
            ]
        )
    ruta = tmp_path / "ReporteGlosasReclamPAQUETE 31068.xlsx"
    wb.save(ruta)
    return ruta


def _macro(tmp_path: Path, decisiones: list[tuple[str, str, str, float]]) -> Path:
    """Libro con la pinta de la macro. `decisiones` = (factura, cod, obs, valor)."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Hoja1"
    ws.append([])
    ws.append(pa.COLUMNAS_MACRO)
    tomadas = {(f, c): (o, v) for f, c, o, v in decisiones}
    for factura, tipo, cod, desc, glosado, causal in FILAS:
        if glosado < 1:
            continue
        obs, valor = tomadas.get((factura, cod), ("", 0))
        ws.append(
            [
                "680010079201",
                "14345108",
                factura,
                "31068",
                1,
                glosado + 1000,
                0,
                1000,
                glosado,
                "CC-91246389",
                "",
                tipo,
                cod,
                desc,
                causal,
                "",
                causal[:4].strip(),
                "CLASIF",
                obs,
                "OBS TECNICA" if obs else "",
                "",
                "1" if valor else "",
                valor,
                "",
                "CAROLINA",
                "LEIDY" if factura == "HUS311371" else "",
            ]
        )
    catalogo = wb.create_sheet("Hoja2")
    for area in ("510204-COSTOS", "734001-LABORATORIO CLINICO", "733001-QUIROFANOS"):
        catalogo.append([area])
    ruta = tmp_path / "modelo.xlsm"
    wb.save(ruta)
    return ruta


# ─── Reglas ──────────────────────────────────────────────────────────────────


class TestReglas:
    def test_codigo_numerico_es_el_mid_de_la_macro(self):
        assert pa.codigo_numerico("3209- La ayuda diagnóstica no tiene justificación") == "3209"
        assert pa.codigo_numerico("") == ""
        assert pa.codigo_numerico("4506- x") == "4506"

    def test_clasificacion_por_causal(self):
        assert pa.clasificar("3106") == "SOPORTES"
        assert pa.clasificar("3209") == "PERTINENCIA"
        assert pa.clasificar("4307") == "TARIFAS"
        assert pa.clasificar("") == pa.CLASIFICACION_SIN_CAUSAL

    def test_la_4302_tambien_es_tarifas(self):
        """02-09-2026: la 4302 no salió en el paquete 31068 (de donde se aprendió
        la tabla) y sus glosas quedaban «sin clasificar» en el 31073. Yesid
        confirmó que es de TARIFAS, como sus vecinas 4303–4309."""
        assert pa.clasificar("4302") == "TARIFAS"

    def test_clasificacion_aprendida_manda_sobre_la_tabla(self):
        assert pa.clasificar("3106", {"3106": "OTRA COSA"}) == "OTRA COSA"

    def test_centro_de_costos(self):
        # Sale siempre en la forma oficial del catálogo del hospital.
        assert (
            pa.centro_de_costos("Procedimientos", "Cuadro hemático") == "734001-LABORATORIO CLINICO"
        )
        assert (
            pa.centro_de_costos("Procedimientos", "Brazo, pierna, rodilla") == "734101-RADIOLOGIA"
        )
        assert pa.centro_de_costos("Medicamentos", "OMEPRAZOL") == "580501-SERVICIO FARMACEUTICO"
        assert (
            pa.centro_de_costos("Procedimientos", "Derechos de sala de cirugía")
            == "733001-QUIROFANOS"
        )

    def test_el_catalogo_es_el_oficial_del_hospital(self):
        """Los 45 centros de la hoja oculta de la macro, con su código."""
        assert len(pa.CATALOGO_CENTROS_COSTOS) == 45
        assert all(re.match(r"^\d{6}-", c) for c in pa.CATALOGO_CENTROS_COSTOS)
        assert "510406-DIREC SUBGCIA DE ALTO COSTO" in pa.CATALOGO_CENTROS_COSTOS
        assert "733001-QUIROFANOS" in pa.CATALOGO_CENTROS_COSTOS

    def test_centro_oficial_normaliza_lo_que_le_manden(self):
        # Nombre solo → forma oficial.
        assert pa.centro_oficial("QUIROFANOS") == "733001-QUIROFANOS"
        # Ya oficial → se queda igual.
        assert pa.centro_oficial("733001-QUIROFANOS") == "733001-QUIROFANOS"
        # Vacío → vacío, no inventa.
        assert pa.centro_oficial("") == ""
        # Algo que no está en el catálogo se respeta: es lo que alguien escribió.
        assert pa.centro_oficial("AREA NUEVA SIN CODIGO") == "AREA NUEVA SIN CODIGO"

    def test_centro_oficial_acepta_un_catalogo_distinto(self):
        """Si el hospital cambia el plan de cuentas, manda el de la macro."""
        otro = ["999999-QUIROFANOS"]
        assert pa.centro_oficial("QUIROFANOS", otro) == "999999-QUIROFANOS"

    def test_no_inventa_centro_cuando_no_se_puede_saber(self):
        """La habitación no dice de qué especialidad es."""
        assert pa.centro_de_costos("Procedimientos", "Habitación de cuatro ó mas camas") == ""
        assert pa.centro_de_costos("Reclamacion", "") == ""

    def test_sugerencia_por_regla(self):
        decision, confianza, motivo = pa.sugerir("SOPORTES", "3106")
        assert (decision, confianza) == ("SE SUBSANA", "REGLA")
        assert "soporte" in motivo

    def test_no_sugiere_donde_hace_falta_un_medico(self):
        decision, confianza, motivo = pa.sugerir("PERTINENCIA", "3209")
        assert decision == "" and confianza == ""
        assert "médico" in motivo

    def test_el_criterio_del_equipo_manda(self):
        decision, confianza, motivo = pa.sugerir("SOPORTES", "3106", {"3106": ("SE OBJETA", 9, 10)})
        assert (decision, confianza) == ("SE OBJETA", "APRENDIDA")
        assert "9 de 10" in motivo


class TestCausalesDeDosAreas:
    """La 4506 la trabajan dos áreas: gestores (facturación) y médicas (pertinencia).

    No es un error de criterio del equipo: quién la toma depende de QUÉ se
    glosó. El material de osteosíntesis y el de alto costo lo revisa el médico
    auditor; lo demás, el gestor. El bot solo sugiere — reparte un super admin.
    """

    def test_la_4506_se_marca_para_repartir(self):
        assert pa.necesita_asignacion("4506")
        assert pa.CAUSALES_DE_DOS_AREAS["4506"] == ("FACTURACION", "PERTINENCIA")

    def test_las_demas_causales_no_se_reparten(self):
        assert not pa.necesita_asignacion("3106")
        assert not pa.necesita_asignacion("")
        assert pa.reparto_de_area("3106", "Medicamentos", "OMEPRAZOL") == ("", "")

    def test_osteosintesis_va_a_las_medicas(self):
        area, motivo = pa.reparto_de_area(
            "4506", "Material de Osteosintesis", "TORNILLO CORTICAL 3.5MM"
        )
        assert area == "PERTINENCIA"
        assert "osteosíntesis" in motivo or "alto costo" in motivo

    def test_alto_costo_por_la_descripcion_tambien_va_a_las_medicas(self):
        for desc in (
            "PROTESIS TOTAL DE CADERA",
            "STENT CORONARIO LIBERADOR",
            "APOSITO DE HIDROFIBRA CON PLATA EXTRA 15 X15 CM -AQUACEL AG",
            "HEMOSTATICO DE CELULOSA OXIDADA REGENERADA 7.1CMX10CM",
            "FRESA FINA DIAMANTADA 5.0MM REF 5820-010-250",
            "CUCHILLA PARA CORTE DE HUESO ADULTA 8 CM",
            "PERFORADOR CRANEAL 14/11 MM",
            "Materiales de sutura y curación GRUPOS 04 - 05 - 06",
        ):
            assert pa.reparto_de_area("4506", "Dispositivos Médicos", desc)[0] == "PERTINENCIA", (
                desc
            )

    def test_lo_corriente_va_a_los_gestores(self):
        area, motivo = pa.reparto_de_area("4506", "Insumo", "GASA ESTERIL 10X10")
        assert area == "FACTURACION"
        assert "gestor" in motivo

    def test_no_confunde_lo_corriente_con_lo_de_alto_costo(self):
        """El apósito de gasa no es curación avanzada, ni el bisturí instrumental."""
        for desc in (
            "APOSITO DE GAS 45CMX90CM PARA ESPALDA X 3",
            "APOSITO ADHESIVO DE POLIURETANO TRANSPARENTE ESTERIL",
            "APOSITO TRANSPARENTE PARA CVC ADULTOS",
            "CUCHILLA BISTURI NO. 15 EN ACERO AL CARBONO",
            "AGUJA DESECHABLE NO. 18 X 1 PULGADA",
        ):
            assert pa.reparto_de_area("4506", "Dispositivos Médicos", desc)[0] == "FACTURACION", (
                desc
            )

    def test_siempre_da_un_motivo_escrito(self):
        for tipo, desc in (
            ("Material de Osteosintesis", "PLACA DE TITANIO"),
            ("Insumo", "JERINGA 10ML"),
        ):
            _, motivo = pa.reparto_de_area("4506", tipo, desc)
            assert motivo, "nunca se sugiere un área sin explicar por qué"


class TestTextoDeRespuesta:
    """Réplica exacta de la fórmula de la columna U de la macro."""

    def _fila(self, **kw):
        base = {
            "codigo_numerico": "3106",
            "observacion": "SE SUBSANA",
            "descripcion": "VENDA DE GASA",
            "valor_glosado": 37600,
            "observacion_tecnico": "",
        }
        return pa.FilaMacro(**{**base, **kw})

    def test_sin_valor_aceptado(self):
        # CONCAT(Q,"-",S,"-",N,"POR VALOR DE "," ",TEXT(I,"$#.##0")," ",T)
        assert (
            self._fila().rta_glosa_completa == "3106-SE SUBSANA-VENDA DE GASAPOR VALOR DE  $37.600 "
        )

    def test_con_valor_aceptado(self):
        # CONCAT(Q,"-",S," ",N," "," ","CANTIDAD ACEPTADA"," ",V," ",". POR VALOR ",TEXT(W),...)
        fila = self._fila(
            observacion="SE ACEPTA ",
            cantidad_aceptada="1",
            valor_aceptado=10500,
            descripcion="APOSITO",
            observacion_tecnico="POR SOBREFACTURACION",
        )
        assert (
            fila.rta_glosa_completa
            == "3106-SE ACEPTA  APOSITO  CANTIDAD ACEPTADA 1 . POR VALOR $10.500 POR SOBREFACTURACION"
        )

    def test_sin_causal_arranca_con_guion(self):
        fila = self._fila(codigo_numerico="", descripcion="Terapia respiratoria")
        assert fila.rta_glosa_completa.startswith("-SE SUBSANA-Terapia respiratoria")

    def test_formato_de_moneda_colombiano(self):
        assert pa._moneda(31800) == "$31.800"
        assert pa._moneda(1034350562) == "$1.034.350.562"
        assert pa._moneda(0) == "$0"


# ─── Lectura ─────────────────────────────────────────────────────────────────


class TestLectura:
    def test_solo_las_filas_glosadas_y_sin_centavos(self, reporte):
        filas = pa.leer_reporte(reporte)
        assert len(filas) == 6  # la de $0,45 queda afuera
        assert all(f.valor_glosado >= 1 for f in filas)

    def test_conserva_la_descripcion_tal_cual(self, tmp_path):
        """El ADRES cierra algunas descripciones con un espacio de no separación."""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(CABECERA_REPORTE)
        ws.append(
            [
                "1",
                "2",
                "HUS1",
                "31068",
                1,
                2000,
                0,
                0,
                1000,
                "CC-1",
                "",
                "Procedimientos",
                "X",
                "MATERIALES GRUPOS\xa007 - 08\xa0",
                "3110- x",
                "",
            ]
        )
        ruta = tmp_path / "r.xlsx"
        wb.save(ruta)
        assert pa.leer_reporte(ruta)[0].descripcion == "MATERIALES GRUPOS\xa007 - 08\xa0"

    def test_lee_los_catalogos_y_el_reparto_de_la_macro(self, tmp_path):
        macro = _macro(tmp_path, [])
        clasif, reparto, centros, filas = pa.leer_macro(macro)
        assert reparto["311371"] == ("CAROLINA", "LEIDY")
        assert "734001-LABORATORIO CLINICO" in centros
        assert len(filas) == 6

    def test_aprende_solo_con_evidencia_suficiente(self, tmp_path):
        pocas = [("HUS352890", "39145", "SE ACEPTA", 100)]
        _, _, _, filas = pa.leer_macro(_macro(tmp_path, pocas))
        assert pa.aprender_decisiones(filas) == {}
        assert pa.aprender_decisiones(filas, minimo=1) == {"3202": ("SE ACEPTA", 1, 1)}


# ─── Preauditoría ────────────────────────────────────────────────────────────


class TestPreauditar:
    def test_llena_lo_mecanico(self, reporte):
        resumen = pa.preauditar(pa.leer_reporte(reporte))
        por_codigo = {f.codigo: f for f in resumen.filas}
        assert por_codigo["2016DM-315"].codigo_numerico == "3106"
        assert por_codigo["2016DM-315"].clasificacion == "SOPORTES"
        assert por_codigo["29117"].clasificacion == pa.CLASIFICACION_SIN_CAUSAL
        assert por_codigo["19942122-09"].centro_costos == "580501-SERVICIO FARMACEUTICO"
        assert resumen.facturas == 2

    def test_no_toca_la_decision_por_defecto(self, reporte):
        resumen = pa.preauditar(pa.leer_reporte(reporte))
        assert all(f.observacion == "" for f in resumen.filas)
        assert any(f.sugerencia for f in resumen.filas)

    def test_aplicar_todas_escribe_la_sugerencia(self, reporte):
        resumen = pa.preauditar(pa.leer_reporte(reporte), aplicar="todas")
        soportes = next(f for f in resumen.filas if f.clasificacion == "SOPORTES")
        assert soportes.observacion == "SE SUBSANA"
        pertinencia = next(f for f in resumen.filas if f.clasificacion == "PERTINENCIA")
        assert pertinencia.observacion == ""  # sigue siendo del médico

    def test_respeta_lo_que_el_equipo_ya_escribio(self, reporte, tmp_path):
        macro = _macro(tmp_path, [("HUS352890", "39145", "SE OBJETA", 0)])
        _, _, _, filas_macro = pa.leer_macro(macro)
        resumen = pa.preauditar(
            pa.leer_reporte(reporte),
            hecho=pa.trabajo_ya_hecho(filas_macro),
            aplicar="todas",
        )
        decidida = next(f for f in resumen.filas if f.codigo == "39145")
        assert decidida.observacion == "SE OBJETA"
        assert decidida.observacion_tecnico == "OBS TECNICA"
        assert decidida.gestor == "CAROLINA"

    def test_el_medico_se_trae_por_renglon(self, reporte, tmp_path):
        _, _, _, filas_macro = pa.leer_macro(_macro(tmp_path, []))
        resumen = pa.preauditar(pa.leer_reporte(reporte), hecho=pa.trabajo_ya_hecho(filas_macro))
        de_311371 = [f for f in resumen.filas if f.factura == "HUS311371"]
        assert all(f.medico == "LEIDY" for f in de_311371)
        assert all(f.medico == "" for f in resumen.filas if f.factura == "HUS352890")


# ─── Documento de respuesta ──────────────────────────────────────────────────


class TestRespuesta:
    def _filas(self):
        def f(obs, desc, glosado, aceptado=0.0):
            return pa.FilaMacro(
                factura="HUS1",
                codigo_numerico="3106",
                observacion=obs,
                descripcion=desc,
                valor_glosado=glosado,
                valor_aceptado=aceptado,
                cantidad_aceptada="1",
            )

        return [
            f("SE ACEPTA", "APOSITO", 1000, 1000),
            f("SE ACEPTA", "AGUJA", 5000, 5000),
            f("SE ACEPTA", "APOSITO", 1000, 1000),  # repetida: se junta
            f("SE SUBSANA", "VENDA", 3000),
            f("SE SUBSANA", "VENDA", 3000),  # repetida: se junta
        ]

    def test_ordena_las_aceptadas_por_valor(self):
        texto = pa.armar_texto_respuesta(self._filas())
        lineas = [ln for ln in texto.split("\n") if ln.strip()]
        assert "POR VALOR DE $7.000" in lineas[0]  # 1.000 + 5.000 + 1.000
        assert "AGUJA" in lineas[1]  # $5.000 va antes que...
        assert "APOSITO" in lineas[2]  # ...los $2.000 juntados

    def test_las_no_aceptadas_van_despues_y_sin_repetir(self):
        texto = pa.armar_texto_respuesta(self._filas())
        assert texto.count("VENDA") == 1
        assert texto.index("VENDA") > texto.index("AGUJA")

    def test_cierra_con_la_extemporanea(self):
        assert pa.armar_texto_respuesta(self._filas()).endswith(pa.TEXTO_EXTEMPORANEA)

    def test_un_documento_por_factura(self, tmp_path):
        filas = [
            pa.FilaMacro(
                factura="HUS1", observacion="SE SUBSANA", descripcion="A", valor_glosado=1
            ),
            pa.FilaMacro(
                factura="HUS2", observacion="SE SUBSANA", descripcion="B", valor_glosado=2
            ),
        ]
        hechos, _ = pa.generar_respuestas(pa.Resumen(filas=filas), tmp_path)
        assert hechos == 2
        assert list(tmp_path.glob("RTA_GLOSA_HUS*.*"))

    def test_carpeta_por_factura(self, tmp_path):
        filas = [
            pa.FilaMacro(factura="HUS1", observacion="SE SUBSANA", descripcion="A", valor_glosado=1)
        ]
        pa.generar_respuestas(pa.Resumen(filas=filas), tmp_path, carpeta_por_factura=True)
        assert list((tmp_path / "HUS1").glob("RTA_GLOSA_HUS1.*"))


# ─── Corrida completa ────────────────────────────────────────────────────────


class TestCLI:
    def test_corrida_completa(self, reporte, tmp_path):
        macro = _macro(tmp_path, [("HUS352890", "39145", "SE OBJETA", 0)])
        salida = tmp_path / "preauditada.xlsx"
        assert (
            pa.main(
                [
                    "--reporte-glosas",
                    str(reporte),
                    "--macro",
                    str(macro),
                    "--salida",
                    str(salida),
                    "--respuestas",
                    str(tmp_path / "rta"),
                    "--reporte-csv",
                    str(tmp_path / "causales.csv"),
                ]
            )
            == 0
        )
        ws = openpyxl.load_workbook(salida).worksheets[0]
        assert [c.value for c in ws[2]][: len(pa.COLUMNAS_MACRO)] == pa.COLUMNAS_MACRO
        # Las columnas de apoyo van después de la 26 para no correr las de la macro.
        assert ws.cell(row=2, column=27).value == "SUGERENCIA DEL BOT"
        filas = list(ws.iter_rows(min_row=3, values_only=True))
        assert len(filas) == 6
        assert all(f[17] for f in filas)  # clasificación llena en todas
        assert len(list((tmp_path / "rta").glob("RTA_GLOSA_*.*"))) == 2

    def test_no_modifica_la_macro(self, reporte, tmp_path):
        macro = _macro(tmp_path, [])
        antes = macro.read_bytes()
        pa.main(
            [
                "--reporte-glosas",
                str(reporte),
                "--macro",
                str(macro),
                "--salida",
                str(tmp_path / "s.xlsx"),
            ]
        )
        assert macro.read_bytes() == antes
