"""«Defender el 100 %» de nada: el caso GL-204.

QUÉ PASÓ. El dictamen GL-204 (POSITIVA, CUPS 010101) salió a pantalla con una
caja verde que decía:

    Tarifa pactada encontrada en el contrato · ✅ Defender 100% (facturado < pactado)
    Tarifa pactada en contrato: $915.051
    Recomendación: El hospital facturó $0, MENOR al pactado ($915.051). La glosa
    es INJUSTIFICADA: lo cobrado está dentro del contrato.

El valor objetado de ese caso era $0.00: la glosa se capturó sin la cifra. En
este motor un valor en cero NO quiere decir «cero pesos», quiere decir «no se
pudo leer». Pero la comparación era aritmética, y 0 < 915.051 es cierto, así
que el sistema concluyó que la glosa era injustificada y recomendó defender el
100 % — de nada.

Y el auditor no podía ver de dónde salía: el panel escondía la fila del valor
facturado justamente cuando valía cero, así que en pantalla solo quedaba la
tarifa pactada y el veredicto en verde.

Había además una SEGUNDA puerta que la auditoría encontró: al texto que se le
manda a la IA se le imprimía «Valor facturado HUS: $0» como si fuera un dato, y
al final una regla fija le ordenaba «si tarifa pactada > valor facturado, la
glosa es IMPROCEDENTE». Con esa regla la IA llegaba sola a la misma conclusión
falsa, aunque se arreglara la recomendación. Por eso hay dos guardas, no una.
"""

from app.services.tarifa_lookup_service import _recomendacion


class TestSinCifraNoHayConclusion:
    def test_el_caso_gl204_ya_no_dice_defender_100(self):
        r = _recomendacion(valor_facturado=0.0, valor_pactado=915051.0, valor_objetado=0.0)
        assert r["accion"] == "REVISAR", "volvió a recomendar defender sin tener la cifra"
        assert "100%" not in r["titulo"]

    def test_le_dice_al_gestor_que_hacer(self):
        r = _recomendacion(valor_facturado=0.0, valor_pactado=915051.0, valor_objetado=0.0)
        razon = r["razon"].lower()
        assert "no quedó registrado" in razon or "no quedo registrado" in razon
        assert "vuelva a analizar" in razon

    def test_no_afirma_que_la_glosa_sea_injustificada(self):
        r = _recomendacion(valor_facturado=0.0, valor_pactado=915051.0, valor_objetado=0.0)
        assert "INJUSTIFICADA" not in r["razon"].upper().replace("SEA INJUSTIFICADA", "")


class TestLosCasosLegitimosNoSeTocan:
    """La guarda no puede volverse un apagón: donde hay cifras, se concluye."""

    def test_facturar_por_debajo_de_lo_pactado_sigue_siendo_defender(self):
        r = _recomendacion(valor_facturado=70000.0, valor_pactado=83800.0, valor_objetado=13800.0)
        assert r["accion"] == "DEFENDER_TOTAL"

    def test_facturar_igual_a_lo_pactado_sigue_siendo_defender(self):
        r = _recomendacion(valor_facturado=83800.0, valor_pactado=83800.0, valor_objetado=1000.0)
        assert r["accion"] == "DEFENDER_TOTAL"

    def test_facturar_de_mas_sigue_siendo_aceptar_parcial(self):
        r = _recomendacion(valor_facturado=100000.0, valor_pactado=83800.0, valor_objetado=20000.0)
        assert r["accion"] == "ACEPTAR_PARCIAL"

    def test_un_peso_facturado_ya_permite_comparar(self):
        """El corte es en cero, no en «poco»."""
        r = _recomendacion(valor_facturado=1.0, valor_pactado=83800.0, valor_objetado=100.0)
        assert r["accion"] == "DEFENDER_TOTAL"


class TestElPanelYaNoEscondeElDatoQueFalta:
    def _banner(self, val_fact, val_obj):
        from app.utils.parsers_glosa import _generar_banner_tarifa_html

        return _generar_banner_tarifa_html(
            {
                "encontrada": True,
                "cups": "010101",
                "eps": "POSITIVA",
                "contrato": "OT3-0525-2017",
                "modalidad": "SOAT",
                "descripcion": "PUNCION CISTERNAL",
                "valor_pactado": 915051.0,
                "valor_facturado": val_fact,
                "valor_objetado": val_obj,
                "valor_reconocido": 0.0,
                "fuente": "TARIFAS ESE HUS 2025- POSITIVA.xlsx",
                "recomendacion": _recomendacion(
                    valor_facturado=val_fact, valor_pactado=915051.0, valor_objetado=val_obj
                ),
            }
        )

    def test_dice_que_el_valor_facturado_no_esta(self):
        html = self._banner(0.0, 0.0)
        assert "Valor facturado HUS" in html
        assert "no registrado en el caso" in html

    def test_dice_que_el_valor_objetado_no_esta(self):
        html = self._banner(0.0, 0.0)
        assert "Valor objetado EPS" in html

    def test_cuando_si_hay_cifras_las_muestra(self):
        html = self._banner(70000.0, 13800.0)
        assert "no registrado en el caso" not in html
        assert "70.000" in html or "70,000" in html
