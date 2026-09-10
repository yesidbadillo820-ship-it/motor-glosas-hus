"""Los dos indicadores del dictamen no pueden decir cosas opuestas.

09-09-2026, prueba del auditor. En la misma pantalla, con dos renglones de
distancia:

    Indicador de riesgo de ratificación:  BAJO
    «Alta probabilidad de levantamiento»
    ⛔ NO RADICAR TODAVÍA

Los dos números los calcula el motor. Y se contradicen: si el motor encontró
en el escrito un defecto tan serio que prefiere no radicarlo, la entidad va a
encontrar ese mismo defecto y ratificar la glosa. No hay «alta probabilidad
de levantamiento» que valga.

Y entre los dos, el auditor le cree al verde — que es la naturaleza humana y
la razón por la que esto importa más de lo que parece: un indicador optimista
al lado de una advertencia anula la advertencia.

QUÉ CUIDA ESTA PRUEBA. Que cuando el motor bloquea, el riesgo suba a ALTO y
diga por qué (cada motivo del bloqueo entra como factor a la vista), y que
sin bloqueo el cálculo de siempre siga mandando sin que nadie lo toque.
"""

from __future__ import annotations

from app.services.riesgo_ratificacion import calcular_riesgo, elevar_por_bloqueo


def _riesgo_bajo() -> dict:
    """El caso más favorable que sabe producir el motor: extemporánea, de
    urgencias, con contrato y con soportes. Da BAJO."""
    r = calcular_riesgo(
        codigo_glosa="AU0202",
        eps="SANITAS",
        tiene_contrato=True,
        tiene_pdf_soportes=True,
        texto_glosa="URGENCIA VITAL",
        es_extemporanea=True,
        es_ratificacion=False,
    )
    assert r["nivel"] == "BAJO", "El caso base ya no da BAJO: la prueba no probaría nada."
    return r


class TestCuandoElMotorBloquea:
    def test_el_riesgo_deja_de_ser_bajo(self):
        elevado = elevar_por_bloqueo(_riesgo_bajo(), ["Falta el soporte de la causal"])
        assert elevado["nivel"] == "ALTO"
        assert elevado["score"] >= 61

    def test_la_etiqueta_ya_no_promete_levantamiento(self):
        elevado = elevar_por_bloqueo(_riesgo_bajo(), ["Falta el soporte de la causal"])
        assert "levantamiento" not in elevado["etiqueta"].lower(), (
            "Sigue prometiendo levantamiento en un escrito que el motor no deja radicar."
        )
        assert "radicar" in elevado["etiqueta"].lower()

    def test_el_color_y_el_icono_acompanan(self):
        """El auditor lee el color antes que la palabra."""
        elevado = elevar_por_bloqueo(_riesgo_bajo(), ["Falta el soporte de la causal"])
        assert elevado["color"] == "#dc2626"
        assert elevado["icon"] == "🔴"

    def test_se_ve_por_que_subio(self):
        motivos = [
            "Falta el soporte de la causal en el expediente",
            "Dice que mantiene una respuesta anterior que no aparece",
        ]
        elevado = elevar_por_bloqueo(_riesgo_bajo(), motivos)
        texto = " | ".join(elevado["factores"])
        for m in motivos:
            assert m in texto, (
                f"El riesgo subió sin decir por qué: falta «{m}» entre los factores. "
                "Un número que sube solo parece caprichoso y se ignora."
            )

    def test_no_se_pierden_los_factores_que_ya_habia(self):
        base = _riesgo_bajo()
        cuantos = len(base["factores"])
        elevado = elevar_por_bloqueo(base, ["Falta el soporte de la causal"])
        assert len(elevado["factores"]) == cuantos + 1
        for f in base["factores"]:
            assert f in elevado["factores"]

    def test_un_riesgo_que_ya_era_alto_no_baja(self):
        alto = calcular_riesgo(
            codigo_glosa="CL0801",
            eps="COOSALUD EPS",
            tiene_contrato=False,
            tiene_pdf_soportes=False,
            texto_glosa="NO PROCEDE",
            es_extemporanea=False,
            es_ratificacion=True,
        )
        elevado = elevar_por_bloqueo(alto, ["Falta el soporte de la causal"])
        assert elevado["score"] >= alto["score"], "El bloqueo BAJÓ el riesgo."

    def test_no_se_modifica_el_original(self):
        """El riesgo calculado se guarda y se compara con otros: mutarlo por
        debajo enredaría cualquier análisis posterior."""
        base = _riesgo_bajo()
        antes = dict(base)
        elevar_por_bloqueo(base, ["Falta el soporte de la causal"])
        assert base == antes


class TestCuandoNoHayBloqueo:
    """Sin bloqueo manda el cálculo de siempre. Esta red no puede volverse una
    excusa para pintar todo de rojo."""

    def test_el_riesgo_no_se_toca(self):
        base = _riesgo_bajo()
        assert elevar_por_bloqueo(base, []) == base
        assert elevar_por_bloqueo(base, None) == base

    def test_sin_riesgo_calculado_no_se_inventa_uno(self):
        assert elevar_por_bloqueo(None, ["Falta el soporte de la causal"]) is None
