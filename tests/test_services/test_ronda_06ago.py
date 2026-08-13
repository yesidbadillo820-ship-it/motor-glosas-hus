"""Los cuatro defectos que quedaron vivos en la tanda del 06-08-2026.

Glosas de prueba corridas en el motor del hospital, sin soportes adjuntos:

  1. SUMIMEDICAL SO0101 y MUTUAL SER SO0201 — el dictamen fundó la defensa
     en el Anexo Técnico No. 5 de la Resolución 3047 de 2008 y la puso de
     primera en el fundamento normativo. Esa resolución la reemplazó la
     2284 de 2023: fundar en norma derogada le regala el argumento a la
     entidad.
  2. NUEVA EPS FA0201 — "Factura radicada el 15/09/2026. Glosa notificada
     el 03/08/2026". No se puede objetar una factura que todavía no se
     había radicado, y el motor nunca miró las dos fechas.
  3. CO0201 + FA0301 — "se objeta $600.000 ... sobre el mismo ítem se
     objeta nuevamente $600.000". Cada respuesta imprimió $1.200.000 como
     valor objetado: el doble conteo quedó radicado.
  4. MUTUAL SER SO0201 — cuatro objeciones distintas en una frase, y el
     dictamen salió con la plantilla genérica de soportes sin contestar
     ninguna. En auditoría, callar sobre un concepto equivale a aceptarlo.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.glosa_service import (
    _doble_glosa_sobre_el_mismo_item,
    _glosa_anterior_a_la_factura,
)
from app.services.subconceptos_glosa import detectar_subconceptos

RAIZ = Path(__file__).resolve().parent.parent.parent

GLOSA_MUTUAL_SER = (
    "SO0201 - Se glosa porque no se evidencia epicrisis, no se aporta hoja de "
    "administración de medicamentos, la orden médica no tiene firma legible y el "
    "consentimiento informado está incompleto. Valor objetado $3.150.000."
)
GLOSA_FECHAS = (
    "FA0201 - Factura radicada el 15/09/2026. Glosa notificada el 03/08/2026 por "
    "diferencia en el valor total. Valor objetado $890.000."
)
GLOSA_DOBLE = (
    "CO0201 - Servicio no incluido en el plan de beneficios, se objeta $600.000. "
    "FA0301 - Sobre el mismo ítem se objeta nuevamente $600.000 por mayor valor "
    "cobrado. Valor total objetado $1.200.000."
)


class TestUnoLaNormaDerogadaYaNoVaDePrimera:
    def _plantillas(self) -> list[dict]:
        with (RAIZ / "data" / "plantillas_hus_base.json").open(encoding="utf-8") as fh:
            return json.load(fh)["plantillas"]

    def test_ninguna_plantilla_funda_la_defensa_en_la_3047(self):
        """Puede nombrarla como antecedente, nunca como norma propia."""
        from app.main import _MARCAS_NORMA_VIGENTE

        malas = []
        for p in self._plantillas():
            arg = p.get("argumento") or ""
            if "3047" in arg and not any(m in arg for m in _MARCAS_NORMA_VIGENTE):
                malas.append(p["codigo_glosa"])
        assert not malas, f"todavía fundan en la norma derogada: {malas}"

    def test_la_vigente_va_nombrada_en_todas(self):
        for p in self._plantillas():
            arg = p.get("argumento") or ""
            if "3047" in arg:
                assert "2284 DE 2023" in arg, p["codigo_glosa"]

    def test_el_texto_de_soportes_arranca_por_la_vigente(self):
        """Es el que salió en SUMIMEDICAL y en MUTUAL SER."""
        so = [p for p in self._plantillas() if p["codigo_glosa"] == "SO-G02"][0]
        arg = so["argumento"]
        assert arg.index("2284 DE 2023") < arg.index("3047 DE 2008")

    def test_las_plantillas_ya_sembradas_se_corrigen_solas(self):
        """El seed del banco solo CREA lo que falta; sin esto, la base del
        hospital se quedaría con el texto viejo para siempre."""
        import inspect

        from app import main

        src = inspect.getsource(main.lifespan)
        assert "_MARCAS_NORMA_VIGENTE" in src
        assert "hus_actualizadas" in src

    def test_no_se_tocaron_los_titulos(self):
        """El título es parte de la llave con la que se busca la fila ya
        sembrada: cambiarlo crearía duplicados en vez de corregir."""
        titulos = {p["titulo"] for p in self._plantillas()}
        assert "SOPORTES MÍNIMOS COMPLETOS — RES. 3047/2008 + RES. 2284/2023" in titulos


class TestDosLaGlosaEsAnteriorALaFactura:
    def test_el_caso_real_nueva_eps(self):
        r = _glosa_anterior_a_la_factura(GLOSA_FECHAS)
        assert r is not None
        f_rad, f_glo = r
        assert (f_rad.day, f_rad.month, f_rad.year) == (15, 9, 2026)
        assert (f_glo.day, f_glo.month, f_glo.year) == (3, 8, 2026)

    def test_el_orden_normal_no_dispara(self):
        t = "FA0201 - Factura radicada el 15/06/2026. Glosa notificada el 03/08/2026."
        assert _glosa_anterior_a_la_factura(t) is None

    def test_el_mismo_dia_no_dispara(self):
        t = "Factura radicada el 03/08/2026. Glosa notificada el 03/08/2026."
        assert _glosa_anterior_a_la_factura(t) is None

    def test_sin_fechas_no_dispara(self):
        assert _glosa_anterior_a_la_factura("SO0201 FALTA EPICRISIS") is None
        assert _glosa_anterior_a_la_factura("") is None

    def test_formato_aaaa_mm_dd(self):
        t = "Factura radicada el 2026-09-15. Glosa notificada el 2026-08-03."
        assert _glosa_anterior_a_la_factura(t) is not None

    def test_fecha_imposible_no_revienta(self):
        assert (
            _glosa_anterior_a_la_factura("Factura radicada el 31/02/2026. Glosa el 01/01/2026.")
            is None
        )

    def test_el_aviso_esta_enchufado(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_glosa_anterior_a_la_factura(texto_base" in src
        i = src.index("_glosa_anterior_a_la_factura(texto_base")
        assert "GLOSA-ANTES-DE-LA-FACTURA" in src[i : i + 1800]


class TestTresElMismoItemObjetadoDosVeces:
    def test_el_caso_real(self):
        assert _doble_glosa_sobre_el_mismo_item(GLOSA_DOBLE) is True

    def test_otras_formas_de_decirlo(self):
        for t in (
            "CO0201 se objeta $500.000. TA0801 se glosa nuevamente el mismo servicio.",
            "SO0201 falta soporte. FA0301 por segunda vez se descuenta el mismo procedimiento.",
        ):
            assert _doble_glosa_sobre_el_mismo_item(t) is True, t

    def test_un_solo_codigo_no_dispara(self):
        t = "CO0201 - Se objeta nuevamente el mismo ítem del mes pasado."
        assert _doble_glosa_sobre_el_mismo_item(t) is False

    def test_dos_codigos_sobre_items_distintos_no_dispara(self):
        t = "CO0201 - Servicio no cubierto $600.000. FA0301 - Error en la fecha $200.000."
        assert _doble_glosa_sobre_el_mismo_item(t) is False

    def test_texto_vacio(self):
        assert _doble_glosa_sobre_el_mismo_item("") is False

    def test_el_aviso_esta_enchufado(self):
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        assert "_doble_glosa_sobre_el_mismo_item(texto_base" in src
        i = src.index("_doble_glosa_sobre_el_mismo_item(texto_base")
        assert "DOBLE-GLOSA-MISMO-ITEM" in src[i : i + 1800]


class TestCuatroLasCuatroObjecionesSeVen:
    def test_el_caso_real_mutual_ser(self):
        assert len(detectar_subconceptos(GLOSA_MUTUAL_SER)) == 4

    def test_ya_no_se_descartan_por_ser_del_mismo_tipo(self):
        """Cuatro faltas de soporte son cuatro objeciones, no una."""
        subs = detectar_subconceptos(GLOSA_MUTUAL_SER)
        resumenes = [s["resumen"].lower() for s in subs]
        assert any("epicrisis" in r for r in resumenes)
        assert any("hoja de administración" in r for r in resumenes)
        assert any("firma" in r for r in resumenes)
        assert any("incompleto" in r for r in resumenes)

    def test_el_soporte_ilegible_es_su_propia_objecion(self):
        t = (
            "SO0201 - No se aporta epicrisis del ingreso y la orden médica no tiene "
            "firma legible del profesional tratante."
        )
        ids = {s["id"] for s in detectar_subconceptos(t)}
        assert "soporte ilegible o sin firma" in ids

    def test_un_fragmento_muy_corto_no_cuenta_como_objecion(self):
        """El corte de longitud mínima sigue en pie: un pedacito suelto no
        es una objeción y no debe inflar la cuenta."""
        t = "SO0201 - No se aporta epicrisis y no tiene firma."
        assert len(detectar_subconceptos(t)) <= 1

    def test_una_sola_objecion_sigue_siendo_una(self):
        t = "SO0201 - Se glosa porque no se evidencia epicrisis. Valor objetado $500.000."
        assert len(detectar_subconceptos(t)) <= 1

    def test_una_glosa_de_tarifa_no_se_parte(self):
        assert detectar_subconceptos("TA0801 - Tarifa superior a la pactada.") == []

    def test_la_plantilla_del_codigo_no_contesta_por_todas(self):
        """Con varias objeciones, la plantilla genérica ya no corta el paso
        al motor: contestaría una y dejaría mudas las demás."""
        import inspect

        from app.services.glosa_service import GlosaService

        src = inspect.getsource(GlosaService.analizar)
        i = src.index("usa_plantilla = plantilla is not None")
        assert "len(self._subconceptos_actuales) < 2" in src[i : i + 120]
