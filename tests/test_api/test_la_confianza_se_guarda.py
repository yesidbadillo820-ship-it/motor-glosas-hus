"""La Confianza que ve el auditor tiene que quedar guardada.

09-09-2026. El auditor corrió el diagnóstico contra la base real del hospital
y salió esto:

    Confianza promedio por modelo
    groq/openai/gpt-oss-120b   382 glosas   77%

Pero él ve 51% al pie de sus dictámenes y llevaba semanas diciendo que «la
confianza no sube del 40%». Los dos números eran ciertos y medían cosas
distintas:

  · `historial.score` (el 77%) es la fórmula VIEJA de probabilidad de éxito:
    99 si es extemporánea, 92 ratificación, 90 urgencia, 75 tarifa, 85 el
    resto, +5 con PDF. No mira el escrito: solo el tipo de glosa.
  · La Confianza (el 51%) sale de `confidence_scorer.calcular_confianza` —
    cláusula del contrato, precedente interno, soportes, citas verificadas,
    cálculo numérico— y es la que dice si el dictamen se sostiene.

Y la segunda **no se guardaba en ninguna parte**: se calculaba, se pintaba en
pantalla y se botaba. Con 397 glosas analizadas, la pregunta que el área
necesitaba responder para decidir si cambiar de modelo de IA —«¿cuál da mejor
Confianza?»— no se podía contestar con datos. No por falta de volumen: porque
el número nunca se escribió.

QUÉ CUIDA ESTA PRUEBA. Que se guarde, que se guarde como se ve (0-100 y no
0-1), y que cuando no se pudo calcular quede en blanco — nunca en cero, que
hundiría el promedio del modelo sin que nada lo explique.
"""

from __future__ import annotations

import pytest

from app.api.routers.analizar import _confianza_para_guardar
from app.models.db import GlosaRecord


class _Resultado:
    """Lo mínimo que mira el helper: el campo `confianza` del análisis."""

    def __init__(self, confianza):
        self.confianza = confianza


class TestSeGuardaComoSeVe:
    def test_el_cero_coma_algo_se_guarda_como_porcentaje(self):
        """En pantalla dice «51%»; en la tabla tiene que decir 51, no 0.51."""
        assert _confianza_para_guardar(_Resultado({"score": 0.51, "nivel": "medio"})) == (
            51.0,
            "medio",
        )

    def test_se_guarda_tambien_el_nivel(self):
        valor, nivel = _confianza_para_guardar(_Resultado({"score": 0.83, "nivel": "alto"}))
        assert valor == 83.0
        assert nivel == "alto"

    def test_se_redondea_a_un_decimal(self):
        valor, _ = _confianza_para_guardar(_Resultado({"score": 0.40666, "nivel": "bajo"}))
        assert valor == 40.7

    def test_los_extremos(self):
        assert _confianza_para_guardar(_Resultado({"score": 1.0, "nivel": "alto"}))[0] == 100.0
        assert _confianza_para_guardar(_Resultado({"score": 0.0, "nivel": "bajo"}))[0] == 0.0


class TestCuandoNoSePudoCalcular:
    """En blanco, nunca en cero. «No se calculó» no es «confianza cero»: con un
    0 el promedio del modelo saldría hundido y nadie sabría por qué."""

    @pytest.mark.parametrize(
        "confianza",
        [None, {}, {"nivel": "alto"}, {"score": None}, "no es un diccionario", 0.51],
    )
    def test_queda_en_blanco(self, confianza):
        assert _confianza_para_guardar(_Resultado(confianza)) == (None, None)

    def test_un_score_ilegible_no_revienta_el_analisis(self):
        """Antes que tumbar un dictamen ya generado, se guarda en blanco."""
        assert _confianza_para_guardar(_Resultado({"score": "ochenta"})) == (None, None)

    def test_un_resultado_sin_el_campo(self):
        class SinCampo:
            pass

        assert _confianza_para_guardar(SinCampo()) == (None, None)


class TestLaTablaTieneDondeGuardarla:
    def test_existen_las_dos_columnas(self):
        for col in ("confianza_score", "confianza_nivel"):
            assert hasattr(GlosaRecord, col), (
                f"Falta la columna {col} en la tabla del historial: la Confianza "
                "se seguiría botando."
            )

    def test_no_se_confunde_con_la_formula_vieja(self):
        """`score` se queda donde está: son datos distintos y las glosas
        viejas solo tienen ese."""
        assert hasattr(GlosaRecord, "score")

    def test_nacen_vacias(self):
        """Las 397 glosas anteriores no la tienen y no se puede reconstruir
        hacia atrás. En blanco es la verdad; un valor por defecto sería
        inventarlo."""
        assert GlosaRecord.__table__.c.confianza_score.default is None
        assert GlosaRecord.__table__.c.confianza_nivel.default is None


class TestElServidorSeActualizaSolo:
    def test_hay_migracion_para_la_base_que_ya_existe(self):
        """La base del hospital ya tiene 397 glosas: la columna hay que
        agregarla en caliente, no solo declararla en el modelo."""
        import inspect

        from app import main

        fuente = inspect.getsource(main)
        assert "ADD COLUMN confianza_score" in fuente, (
            "Sin migración, el servidor arranca contra una tabla sin la columna "
            "y todos los análisis fallan al guardar."
        )
        assert "ADD COLUMN confianza_nivel" in fuente


class TestSeGuardaEnLosDosCaminos:
    """Una glosa se guarda por dos caminos: la primera vez se crea, y al
    re-analizarla se actualiza la fila que ya está. Si solo se enchufa uno,
    la mitad de los análisis sigue sin guardar la Confianza."""

    def test_al_crear_la_glosa(self):
        import inspect

        from app.api.routers import analizar

        fuente = inspect.getsource(analizar)
        i = fuente.index("glosa_repo.crear(")
        assert "confianza_score=_conf_score" in fuente[i : i + 1500]

    def test_al_reanalizar_una_que_ya_existia(self):
        import inspect

        from app.api.routers import analizar

        fuente = inspect.getsource(analizar)
        i = fuente.index("existente.score = resultado.score")
        alrededor = fuente[i : i + 700]
        assert "existente.confianza_score" in alrededor

    def test_al_reanalizar_no_se_borra_la_que_ya_estaba(self):
        """Si el re-análisis salió por un camino que no calcula Confianza, la
        del análisis anterior se conserva: borrarla sería perder el dato."""
        import inspect

        from app.api.routers import analizar

        fuente = inspect.getsource(analizar)
        i = fuente.index("existente.score = resultado.score")
        alrededor = fuente[i : i + 700]
        assert "if _conf_score is not None:" in alrededor, (
            "El re-análisis pisa la Confianza guardada aunque este no la haya "
            "calculado: se perdería el dato del análisis anterior."
        )
