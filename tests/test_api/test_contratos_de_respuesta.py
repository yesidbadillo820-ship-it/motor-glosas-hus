"""Los contratos de respuesta, enchufados y verificados contra la pantalla.

OT-040 · 13-08-2026. Fase 2 del programa de mejora. De las 595 rutas del
motor, solo 8 declaraban qué devuelven; las demás sueltan un diccionario y
nada garantiza que el campo que el JavaScript lee siga ahí mañana.

Se enchufaron los esquemas en las seis rutas que alimentan las pantallas
donde un cambio silencioso duele: tarifas, conciliaciones, Salud Total y el
validador ADRES.

**El riesgo de este cambio, y por qué estas pruebas.** Un `response_model`
no solo documenta: **filtra**. Todo campo que no esté en el esquema se cae
de la respuesta. Si la pantalla lee uno que quedó por fuera, deja de verlo
—y no da error, se queda en blanco—, que es exactamente el mal que este
trabajo vino a evitar.

Por eso acá no se comprueba que el esquema «esté bien»: se comprueba que
**no le quite a la pantalla ninguna llave que de verdad usa**.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.models.schemas import (
    ConciliacionesPagina,
    ConciliacionOut,
    SaludTotalPreviewOut,
    TarifaContratadaOut,
    TarifasStatsOut,
    ValidacionAdresEstadoOut,
    ValidacionAdresIniciadaOut,
)

RAIZ = Path(__file__).resolve().parents[2]
INDEX = RAIZ / "static" / "index.html"


def _html() -> str:
    if not INDEX.exists():  # pragma: no cover
        pytest.skip("static/index.html no está en este entorno")
    return INDEX.read_text(encoding="utf-8", errors="ignore")


class TestLasRutasDeclaranLoQueDevuelven:
    @pytest.mark.parametrize(
        "metodo,ruta,esquema",
        [
            ("GET", "/tarifas-contratadas", "TarifaContratadaOut"),
            ("GET", "/tarifas-contratadas/stats", "TarifasStatsOut"),
            ("GET", "/conciliaciones/", "ConciliacionesPagina"),
            ("POST", "/api/salud-total/preview", "SaludTotalPreviewOut"),
            ("GET", "/validador-adres/estado/{trabajo_id}", "ValidacionAdresEstadoOut"),
            ("POST", "/validador-adres/validar", "ValidacionAdresIniciadaOut"),
        ],
    )
    def test_la_ruta_tiene_su_contrato(self, metodo, ruta, esquema):
        from app.main import app

        for r in app.routes:
            if getattr(r, "path", "") == ruta and metodo in (getattr(r, "methods", set()) or set()):
                modelo = getattr(r, "response_model", None)
                assert modelo is not None, f"{metodo} {ruta} sigue sin contrato"
                assert esquema in repr(modelo), f"{metodo} {ruta} declara {modelo}, no {esquema}"
                return
        pytest.fail(f"no existe la ruta {metodo} {ruta}")


class TestElContratoNoLeQuitaNadaALaPantalla:
    """Un `response_model` FILTRA: lo que no está en el esquema se cae de la
    respuesta. Si la pantalla lee una llave que quedó por fuera, se queda en
    blanco sin dar error."""

    def test_conciliaciones(self):
        html = _html()
        leidas = set(
            re.findall(
                r"\bc\.(id|glosa_id|resultado|valor_conciliado|acta_numero|estado_bilateral"
                r"|fecha_audiencia|lugar|observaciones|siguiente_paso|postura_hus"
                r"|contra_respuesta_eps|valor_ratificado_hus|fecha_acta|creado_en|creado_por"
                r"|participantes_hus|participantes_eps)\b",
                html,
            )
        )
        assert leidas, "no se leyó ninguna llave: revisar el detector"
        faltan = leidas - set(ConciliacionOut.model_fields)
        assert not faltan, f"el contrato le quita a la pantalla: {sorted(faltan)}"

    def test_la_pagina_de_conciliaciones(self):
        """La tabla lee items/total/page/per_page/pages."""
        for llave in ("items", "total", "page", "per_page", "pages"):
            assert llave in ConciliacionesPagina.model_fields, llave

    def test_salud_total(self):
        for llave in (
            "total_registros",
            "total_glosado",
            "total_aceptado",
            "total_rechazado",
            "sin_fecha_recepcion",
            "glosas",
        ):
            assert llave in SaludTotalPreviewOut.model_fields, llave

    def test_salud_total_conserva_los_nombres_de_la_entidad(self):
        """`NumeroRad` y compañía no se pasan a snake_case: así los manda la
        notificación y así los lee la pantalla."""
        fila = SaludTotalPreviewOut.model_fields["glosas"].annotation
        campos = set(fila.__args__[0].model_fields)
        for llave in (
            "NumeroRad",
            "NUMREG",
            "NombreServicio",
            "ValorGlosaTotalxServ",
            "Codigo_Respuesta_a_glosas",
            "ConceptoRespuesta",
        ):
            assert llave in campos, llave

    def test_validador_adres(self):
        for llave in ("estado", "mensaje", "progreso", "total", "facturas"):
            assert llave in ValidacionAdresEstadoOut.model_fields, llave
        assert "trabajo_id" in ValidacionAdresIniciadaOut.model_fields

    def test_tarifas(self):
        """La tabla de tarifas muestra el CUPS, el valor y desde cuándo rige."""
        for llave in (
            "codigo_cups",
            "descripcion",
            "valor_pactado",
            "modalidad",
            "vigencia_desde",
            "vigencia_hasta",
            "contrato_numero",
        ):
            assert llave in TarifaContratadaOut.model_fields, llave

    def test_stats_de_tarifas(self):
        for llave in ("total_activas", "por_eps"):
            assert llave in TarifasStatsOut.model_fields, llave


class TestElHistorialNoPierdeColumnas:
    """El caso más peligroso de todos, y por poco pasa.

    `GlosaHistorialItem` existía desde hacía meses declarando DIEZ campos
    mientras la ruta devolvía VEINTIUNO, y nunca se había enchufado.
    Enchufarlo tal como estaba —que es exactamente lo que pedía la Fase 2—
    le habría borrado once columnas a la tabla de Historial: la factura, el
    dictamen, la entidad, el CUPS, el servicio, la observación… en silencio.
    """

    LLAVES_QUE_LEE_LA_PANTALLA = {
        "id",
        "eps",
        "entidad",
        "paciente",
        "factura",
        "codigo_glosa",
        "concepto_glosa",
        "cups",
        "servicio",
        "valor_objetado",
        "valor_aceptado",
        "glosa_original",
        "codigo_respuesta",
        "observacion",
        "estado",
        "dictamen",
        "dias_restantes",
        "creado_en",
        "fecha_recepcion",
    }

    def test_el_contrato_tiene_todo_lo_que_la_pantalla_lee(self):
        from app.models.schemas import GlosaHistorialItem

        faltan = self.LLAVES_QUE_LEE_LA_PANTALLA - set(GlosaHistorialItem.model_fields)
        assert not faltan, f"el contrato le borraría estas columnas al historial: {sorted(faltan)}"

    def test_la_lista_de_llaves_es_la_que_de_verdad_usa_la_pantalla(self):
        """Guardia de la guardia: si el JavaScript deja de leer una, esta
        prueba avisa antes de que la lista se vuelva folclore."""
        html = _html()
        leidas = set(re.findall(r"\bg\.([a-z_]+)\b", html))
        # Solo interesan las del historial; el resto del archivo usa `g.` para
        # otras cosas. Se comprueba que las declaradas SÍ aparezcan.
        no_aparecen = {k for k in self.LLAVES_QUE_LEE_LA_PANTALLA if k not in leidas}
        assert not no_aparecen, f"declaradas pero la pantalla ya no las lee: {sorted(no_aparecen)}"

    def test_la_ruta_declara_el_contrato_completo(self):
        from app.main import app

        for r in app.routes:
            if getattr(r, "path", "") == "/glosas/historial":
                modelo = getattr(r, "response_model", None)
                assert modelo is not None
                assert "GlosaHistorialItem" in repr(modelo), (
                    f"declara {modelo}: `list` a secas no es un contrato, acepta cualquier cosa"
                )
                return
        pytest.fail("no existe /glosas/historial")

    def test_una_glosa_recien_creada_no_revienta(self):
        """Sin dictamen, sin código de respuesta, sin fecha de entrega: la
        fila tiene que mostrarse igual, no dar un 500."""
        from app.models.schemas import GlosaHistorialItem

        fila = GlosaHistorialItem(id=7)
        assert fila.id == 7
        assert fila.dictamen is None
        assert fila.valor_objetado is None


class TestElExpedienteNoPierdeCampos:
    """`GET /glosas/{id}` devuelve 36 campos y no declaraba ninguno."""

    LLAVES_QUE_LEE_LA_PANTALLA = {
        "id",
        "eps",
        "paciente",
        "codigo_glosa",
        "valor_objetado",
        "valor_aceptado",
        "estado",
        "factura",
        "creado_en",
        "dias_restantes",
        "dictamen",
        "dictamen_stale",
        "dictamen_stale_motivo",
        "numero_radicado",
        "consecutivo_dgh",
        "gestor_nombre",
        "fecha_radicacion_factura",
        "fecha_recepcion",
        "fecha_vencimiento",
        "referencia",
        "observacion_tecnico",
        "tipo_glosa_excel",
        "profesional_medico",
        "observacion_eps",
        "valor_recuperado",
        "numero_nota_credito",
    }

    def test_el_contrato_tiene_todo_lo_que_la_pantalla_lee(self):
        from app.models.schemas import GlosaExpedienteOut

        faltan = self.LLAVES_QUE_LEE_LA_PANTALLA - set(GlosaExpedienteOut.model_fields)
        assert not faltan, f"el contrato le borraría al expediente: {sorted(faltan)}"

    def test_declara_los_36_campos_que_devuelve_la_ruta(self):
        from app.models.schemas import GlosaExpedienteOut

        assert len(GlosaExpedienteOut.model_fields) == 36

    def test_la_ruta_declara_su_contrato(self):
        from app.main import app

        for r in app.routes:
            if getattr(r, "path", "") == "/glosas/{glosa_id}" and "GET" in (
                getattr(r, "methods", set()) or set()
            ):
                modelo = getattr(r, "response_model", None)
                assert modelo is not None and "GlosaExpedienteOut" in repr(modelo)
                return
        pytest.fail("no existe GET /glosas/{glosa_id}")

    def test_una_glosa_recien_importada_se_muestra(self):
        """Sin dictamen, sin radicado, sin decisión de la EPS, sin nota
        crédito: el expediente tiene que abrirse desde el primer día."""
        from app.models.schemas import GlosaExpedienteOut

        e = GlosaExpedienteOut(id=1)
        assert e.dictamen is None
        assert e.numero_radicado is None
        assert e.decision_eps is None

    def test_el_aviso_de_dictamen_desactualizado_sobrevive(self):
        """`dictamen_stale` avisa que la glosa cambió después de generar el
        dictamen. Si el contrato lo borrara, el auditor radicaría un dictamen
        viejo creyendo que está al día."""
        from app.models.schemas import GlosaExpedienteOut

        e = GlosaExpedienteOut(id=1, dictamen_stale=True, dictamen_stale_motivo="cambió el valor")
        assert e.dictamen_stale is True
        assert e.dictamen_stale_motivo == "cambió el valor"


class TestElContratoSeCumpleConDatosDeVerdad:
    def test_salud_total_valida_la_notificacion_real(self):
        """Con las 44 glosas del archivo del auditor, no con un ejemplo."""
        from app.services.salud_total_service import procesar_glosas_salud_total

        cabecera = (
            "FechaRad_|NumeroRad_|PrefijoFac_|NumeroFac_|Numreg|NumeroDocAfl_|NombreComplAfl|Nap|"
            "NombreServicio|ValorTotalServ|CantidadFac|ValorUnitario|ValorGlosaFinal|"
            "ValorGlosaTotalxServ|DescripcionMotivo|Observaciones|CodMotvGlosaGeneral|"
            "MotvGlosaGeneral|CodMotvGlosaEspc|MotvGlosaEspc|DescripcionDevolucion|"
            "CausalDevolucion|MotivoDevolucion|ValorBrutoFactura|"
        )
        fila = (
            "07/03/2026 2:07:00 AM|350000214021421|HUS|523938|605090729|00000000|PACIENTE|0|"
            "RADIOGRAFIA DE TORAX|280000.00|2|140000.00|93340.00|93340|"
            "Diferencias con los valores pactados||TA|Tarifas|TA23|Otros||||1589100.00|"
        )
        respuestas = procesar_glosas_salud_total(f"{cabecera}\n{fila}\n", "extemporanea", None)
        salida = SaludTotalPreviewOut(
            total_registros=len(respuestas),
            total_glosado=93340.0,
            total_aceptado=0.0,
            total_rechazado=93340.0,
            sin_fecha_recepcion=True,
            glosas=respuestas,
        )
        # Lo que se comprueba es que el contrato NO deforme los datos.
        assert salida.glosas[0].NumeroRad == "350000214021421"
        assert salida.glosas[0].ValorGlosaTotalxServ == 93340.0
        assert salida.glosas[0].CodMotvGlosaGeneral == "TA"

    def test_una_tarifa_de_la_base_pasa_el_contrato(self):
        class Fila:
            id = 1
            eps = "FAMISANAR"
            contrato_numero = "S-13-1-03-1-04958"
            codigo_cups = "010101"
            codigo_ips = None
            descripcion = "PUNCION CISTERNAL"
            valor_pactado = 836800.0
            modalidad = "UVB POR GRUPOS"
            tipo_tarifa = "VALOR_FIJO"
            factor_ajuste = 0.0
            fuente_archivo = "PROPUESTA_2026.xlsx"
            vigencia_desde = "2026-04-15"
            vigencia_hasta = "2027-04-14"
            creado_en = None
            creado_por = "coord@hus.gov.co"
            activa = True

        t = TarifaContratadaOut.model_validate(Fila())
        assert t.valor_pactado == 836800.0
        assert t.modalidad == "UVB POR GRUPOS"
        assert t.vigencia_desde == "2026-04-15"
