"""A cada código, su plata: el caso GL-206.

QUÉ PASÓ. El dictamen GL-206 (PPL) respondió una glosa con dos códigos. El
texto pegado decía:

    «EPS: PPL · TA2902 $150.000 por tarifa Y ADEMÁS SO3401 $80.000 por falta
     de epicrisis»

El motor hizo bien lo difícil —generó una respuesta por cada código— pero la
respuesta del SO3401 salió impresa diciendo «RESPECTO DEL VALOR OBJETADO DE
$ 150.000», que es la plata del OTRO código. Los $80.000 del SO3401 no
aparecieron en ninguna parte del documento, y el total «A defender» de la
pantalla mostró $150.000 sin sumarlos.

La causa: el motor extrae UN SOLO valor para toda la glosa —el primero que
aparece en el texto— y se lo entrega a todas las secciones con la orden «copia
ese número exacto».

LA REGLA NUEVA ES ESTRECHA A PROPÓSITO. Repartir plata adivinando es peor que
no repartirla: si al SO3401 se le cuelga el monto equivocado, el hospital
radica una cifra falsa ante la EPS. Por eso solo se reparte cuando el texto no
deja lugar a duda, y ante la menor sombra se devuelve vacío y todo queda como
estaba. Estas pruebas cuidan sobre todo los casos en que NO se debe repartir.
"""

import pytest

from app.services.multi_codigo import valores_por_codigo


class TestCuandoSiSeReparte:
    def test_el_caso_gl206_tal_cual_llego(self):
        texto = (
            "EPS: PPL · TA2902 $150.000 por tarifa Y ADEMÁS SO3401 $80.000 por falta de epicrisis"
        )
        assert valores_por_codigo(texto, ["TA2902", "SO3401"]) == {
            "TA2902": "$ 150.000",
            "SO3401": "$ 80.000",
        }

    def test_tres_codigos_cada_uno_con_lo_suyo(self):
        texto = "TA2902 $150.000, SO3401 $80.000, CO0101 $40.000"
        assert valores_por_codigo(texto, ["TA2902", "SO3401", "CO0101"]) == {
            "TA2902": "$ 150.000",
            "SO3401": "$ 80.000",
            "CO0101": "$ 40.000",
        }

    def test_no_importa_el_orden_en_que_vengan_los_codigos(self):
        """Se reparte por dónde están en el texto, no por el orden de la lista."""
        texto = "TA2902 $150.000 y SO3401 $80.000"
        assert valores_por_codigo(texto, ["SO3401", "TA2902"]) == {
            "TA2902": "$ 150.000",
            "SO3401": "$ 80.000",
        }

    def test_el_punto_final_no_se_pega_al_monto(self):
        texto = "TA2902 $150.000 por tarifa. SO3401 $80.000."
        reparto = valores_por_codigo(texto, ["TA2902", "SO3401"])
        assert reparto["SO3401"] == "$ 80.000"


class TestCuandoNoSeRepartePorqueNoSeSabe:
    """Ante la duda, no se reparte: se deja el comportamiento de siempre."""

    @pytest.mark.parametrize(
        "texto,codigos,por_que",
        [
            (
                "Glosa por $230.000. TA2902 por tarifa y SO3401 por epicrisis",
                ["TA2902", "SO3401"],
                "el monto va ANTES del primer código: parece el total de la glosa",
            ),
            (
                "TA2902 $80.000 y SO3401 $80.000",
                ["TA2902", "SO3401"],
                "el mismo monto en los dos: probablemente es un valor global",
            ),
            (
                "TA2902 $150.000 y SO3401 sin valor indicado",
                ["TA2902", "SO3401"],
                "a un código no le toca ningún monto",
            ),
            (
                "TA2902 $150.000 más $20.000 y SO3401 $80.000",
                ["TA2902", "SO3401"],
                "a un código le tocan dos montos: no se sabe cuál es el suyo",
            ),
            (
                "TA2902 $150.000 y también hay un SO9999 no mencionado",
                ["TA2902", "SO3401"],
                "un código de la lista no aparece en el texto",
            ),
            (
                "TA2902 por tarifa y SO3401 por epicrisis, sin cifras",
                ["TA2902", "SO3401"],
                "no hay montos",
            ),
        ],
    )
    def test_devuelve_vacio(self, texto, codigos, por_que):
        assert valores_por_codigo(texto, codigos) == {}, f"repartió cuando {por_que}"

    def test_con_un_solo_codigo_no_hay_nada_que_repartir(self):
        assert valores_por_codigo("TA2902 $150.000", ["TA2902"]) == {}

    def test_texto_vacio_no_rompe(self):
        assert valores_por_codigo("", ["TA2902", "SO3401"]) == {}
        assert valores_por_codigo("TA2902 $1", []) == {}
