"""Defectos hallados el 20-08-2026 probando dictámenes reales en el portal.

Yesid corrió cinco glosas de prueba en «Analizar glosa» y pegó los dictámenes.
Salieron tres defectos que se radicaban ante la EPS:

  1. una cifra de plata convertida en código de procedimiento («CUPS 100000»);
  2. el dictamen afirmando y negando lo mismo en un renglón («correspondiente
     al SERVICIO CUBIERTO … se acepta por corresponder a un SERVICIO NO
     CUBIERTO»);
  3. una glosa aceptada PARCIALMENTE radicada como «ACEPTADA AL 100%», con lo
     que el hospital renunciaba a la parte que sí estaba defendiendo.

Cada clase de acá abajo es uno de esos casos, con el texto tal como llegó.
"""

from __future__ import annotations

import re

from app.api.routers.analizar import (
    _construir_dictamen_aceptacion,
    _decidir_estado_y_codigo,
)
from app.utils.parsers_glosa import (
    _descripcion_servicio,
    _detectar_servicio_desde_texto,
    _extraer_valores_glosa,
)

# El texto exacto que Yesid escribió en el portal.
GLOSA_MUNDIAL = "SO5801 - existe ausencia total de soporte de la curacion, valor glosado 100000"
GLOSA_COOSALUD = "CO4601 - se glosa omeprazol capsulas por no estar cubierto"


def _plano(html: str) -> str:
    """El HTML del dictamen, como texto corrido, para poder leerlo."""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


class TestLaPlataNoEsUnCups:
    """«valor glosado 100000» son cien mil pesos, no un procedimiento."""

    def test_el_caso_de_yesid_ya_no_inventa_el_cups(self):
        assert _detectar_servicio_desde_texto(GLOSA_MUNDIAL, "") is None

    def test_y_no_llega_al_dictamen_que_se_radica(self):
        html = _construir_dictamen_aceptacion(
            eps="COMPAÑIA MUNDIAL DE SEGUROS",
            codigo_glosa="SO5801",
            val_obj=40_000,
            val_ac=40_000,
            estado="ACEPTADA",
            cod_resp="RE9702",
            desc_resp="GLOSA ACEPTADA AL 100%",
            tabla_excel=GLOSA_MUNDIAL,
            contexto_pdf="",
        )
        assert "CUPS 100000" not in _plano(html)

    def test_otras_maneras_de_nombrar_la_plata(self):
        """La EPS no siempre escribe «valor glosado»."""
        for texto in (
            "SO0101 - falta soporte, valor objetado 250000",
            "TA0201 - mayor valor cobrado por valor de 150000",
            "FA0102 - insumo no facturable, monto 120000",
            "CO0301 - servicio no cubierto, cuantia 890600",
        ):
            detectado = _detectar_servicio_desde_texto(texto, "") or ""
            assert "CUPS" not in detectado, f"tomó plata como CUPS en: {texto}"

    def test_pero_un_cups_de_verdad_si_se_detecta(self):
        """El arreglo no puede dejar ciego al detector: es media corrección."""
        detectado = _detectar_servicio_desde_texto("SO0201 - 890201 CONSULTA DE URGENCIAS", "")
        assert detectado and "890201" in detectado

    def test_y_el_cups_de_un_estudio_tambien(self):
        detectado = _detectar_servicio_desde_texto(
            "TA0801 - estudio de coloracion basica en biopsia 898040", ""
        )
        assert detectado and "898040" in detectado

    def test_la_cola_de_un_contrato_no_es_un_cups(self):
        """Regresión de agosto: «S-13-1-03-1-04958» dejaba «CUPS 04958»."""
        detectado = _detectar_servicio_desde_texto(
            "FA0102 - contrato S-13-1-03-1-04958 insumo no facturable", ""
        )
        assert "04958" not in (detectado or "")


class TestElDictamenNoSeContradice:
    """Aceptar una glosa y negar el motivo en el mismo renglón."""

    def test_el_caso_de_yesid_cubierto_y_no_cubierto(self):
        html = _construir_dictamen_aceptacion(
            eps="COOSALUD",
            codigo_glosa="CO4601",
            val_obj=200,
            val_ac=200,
            estado="ACEPTADA",
            cod_resp="RE9702",
            desc_resp="GLOSA ACEPTADA AL 100%",
            tabla_excel=GLOSA_COOSALUD,
            contexto_pdf="",
        )
        texto = _plano(html)
        # El motivo (lo que de verdad pasó) se conserva…
        assert "SERVICIO NO CUBIERTO" in texto
        # …y la frase que lo negaba, ya no está.
        assert "CORRESPONDIENTE AL SERVICIO CUBIERTO" not in texto

    def test_autorizacion_no_se_afirma_y_se_niega(self):
        html = _construir_dictamen_aceptacion(
            eps="SURA",
            codigo_glosa="AU0101",
            val_obj=5_000,
            val_ac=5_000,
            estado="ACEPTADA",
            cod_resp="RE9702",
            desc_resp="GLOSA ACEPTADA AL 100%",
            tabla_excel="AU0101 - servicio sin autorizacion previa",
            contexto_pdf="",
        )
        texto = _plano(html)
        assert "NO ACREDITARSE LA AUTORIZACIÓN" in texto
        assert "PROCEDIMIENTO AUTORIZADO" not in texto

    def test_soportes_no_se_afirman_y_se_niegan(self):
        html = _construir_dictamen_aceptacion(
            eps="COMPAÑIA MUNDIAL DE SEGUROS",
            codigo_glosa="SO5801",
            val_obj=40_000,
            val_ac=40_000,
            estado="ACEPTADA",
            cod_resp="RE9702",
            desc_resp="GLOSA ACEPTADA AL 100%",
            tabla_excel=GLOSA_MUNDIAL,
            contexto_pdf="",
        )
        texto = _plano(html)
        assert "NO APORTARSE EL SOPORTE" in texto
        assert "Y SUS SOPORTES DOCUMENTALES" not in texto

    def test_ninguna_familia_afirma_lo_que_el_motivo_niega(self):
        """Barrido: el complemento nunca puede chocar con su propio motivo."""
        choques = {
            "CO": "CUBIERTO",
            "AU": "AUTORIZADO",
        }
        for familia, palabra_prohibida in choques.items():
            complemento = _descripcion_servicio(f"{familia}0101")
            assert palabra_prohibida not in complemento, (
                f"{familia}: el complemento «{complemento}» afirma "
                f"«{palabra_prohibida}», que es justo lo que se está aceptando que falta"
            )

    def test_lo_que_si_es_un_hecho_se_conserva(self):
        """No neutralizar de más: el cargo se facturó, el procedimiento se
        prestó. Eso no está en discusión y ayuda a leer el dictamen."""
        assert "CARGO FACTURADO" in _descripcion_servicio("FA0102")
        assert "PROCEDIMIENTO MÉDICO PRESTADO" in _descripcion_servicio("CL0801")
        assert "MEDICAMENTO DISPENSADO" in _descripcion_servicio("ME0101")


class TestUnaParcialNoSeRadicaComoTotal:
    """El defecto que le costaba plata al hospital."""

    def test_el_texto_de_la_glosa_trae_el_valor_objetado(self):
        assert _extraer_valores_glosa(GLOSA_MUNDIAL).get("objetado") == 100_000.0

    def test_con_ese_valor_la_glosa_es_parcial_no_total(self):
        val_obj = _extraer_valores_glosa(GLOSA_MUNDIAL)["objetado"]
        _, estado, cod, _ = _decidir_estado_y_codigo(val_obj, 40_000)
        assert estado == "PARCIALMENTE_ACEPTADA"
        assert cod == "RE9801"

    def test_el_dictamen_defiende_los_sesenta_mil(self):
        val_obj = _extraer_valores_glosa(GLOSA_MUNDIAL)["objetado"]
        val_obj, estado, cod, desc = _decidir_estado_y_codigo(val_obj, 40_000)
        html = _construir_dictamen_aceptacion(
            eps="COMPAÑIA MUNDIAL DE SEGUROS",
            codigo_glosa="SO5801",
            val_obj=val_obj,
            val_ac=40_000,
            estado=estado,
            cod_resp=cod,
            desc_resp=desc,
            tabla_excel=GLOSA_MUNDIAL,
            contexto_pdf="",
        )
        texto = _plano(html)
        assert "ACEPTA GLOSA PARCIAL" in texto
        assert "$60.000" in texto  # lo que se sigue defendiendo
        assert "ACEPTADA AL 100%" not in texto

    def test_el_router_consulta_el_texto_cuando_la_ia_no_trae_el_valor(self):
        """El cableado: que nadie quite la consulta al texto sin darse cuenta."""
        import ast
        import inspect

        from app.api.routers import analizar as mod

        arbol = ast.parse(inspect.getsource(mod))

        # Buscar el respaldo concreto, no «que exista alguna llamada»: el
        # módulo llama a `_extraer_valores_glosa` en cinco sitios más, así que
        # una prueba laxa pasaría igual con el respaldo borrado. Lo que tiene
        # que existir es un `if` sobre val_obj que, adentro, consulte el texto
        # y le vuelva a asignar val_obj.
        def _usa_extractor(nodo) -> bool:
            return any(
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute | ast.Name)
                and "_extraer_valores_glosa"
                in ast.dump(n.func)  # cubre la llamada directa y el .get(...)
                for n in ast.walk(nodo)
            )

        def _reasigna_val_obj(nodo) -> bool:
            return any(
                isinstance(n, ast.Name) and n.id == "val_obj" and isinstance(n.ctx, ast.Store)
                for n in ast.walk(nodo)
            )

        respaldos = [
            n
            for n in ast.walk(arbol)
            if isinstance(n, ast.If)
            and _usa_extractor(n)
            and _reasigna_val_obj(n)
            and "val_obj" in ast.dump(n.test)
        ]
        assert respaldos, (
            "El router ya no consulta el valor objetado en el texto de la glosa "
            "cuando la IA no lo trae. Sin ese respaldo, una aceptación PARCIAL "
            "vuelve a radicarse como «ACEPTADA AL 100%» y el hospital renuncia "
            "a la parte que estaba defendiendo (caso SO5801 de COMPAÑIA MUNDIAL: "
            "objetaron $100.000, se aceptaron $40.000, se regalaban $60.000)."
        )

    def test_si_la_ia_si_trae_el_valor_manda_la_ia(self):
        """El respaldo solo entra cuando falta el dato — no pisa lo bueno."""
        val_obj, estado, cod, _ = _decidir_estado_y_codigo(500_000, 40_000)
        assert val_obj == 500_000
        assert estado == "PARCIALMENTE_ACEPTADA"

    def test_una_aceptacion_total_de_verdad_sigue_siendo_total(self):
        """Sin cifra en el texto y aceptando todo, sigue siendo RE9702."""
        texto = "TA0601 - se glosa mayor valor cobrado en curacion de lesion en piel"
        assert _extraer_valores_glosa(texto).get("objetado") == 0.0
        _, estado, cod, _ = _decidir_estado_y_codigo(0, 168_563)
        assert estado == "ACEPTADA"
        assert cod == "RE9702"
