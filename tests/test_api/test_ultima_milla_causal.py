"""La causal no sale como código del servicio, pase lo que pase adentro.

01-09-2026. Pedido del auditor tras cinco corridas de la prueba 2: «el LLM es
terco con el código; bórralo a la fuerza por backend, después de que entregue
el texto y antes de enviarlo al cliente».

Ya había dos redes que lo hacen dentro del motor —una sobre el campo <servicio>
del modelo, otra sobre el cuerpo del dictamen— y las dos funcionan contra el
texto exacto que salió en pantalla. Esta tercera va en el último punto por el
que pasa el dictamen antes de persistirse y de viajar al navegador, para que
deje de depender del orden en que corran las de adentro o de que mañana
aparezca un camino nuevo.

Es idempotente: si las de adentro ya limpiaron, esta no encuentra nada.
"""

import io

import pytest

from app.services.glosa_service import _quitar_causal_propia_del_cuerpo

ROUTER = io.open("app/api/routers/analizar.py", encoding="utf-8").read()
PROMPTS = io.open("app/services/glosa_ia_prompts.py", encoding="utf-8").read()


class TestLaLimpiezaEstaEnElUltimoPunto:
    def test_corre_antes_de_persistir_y_de_responder(self):
        i_limpieza = ROUTER.index("[ULTIMA-MILLA]")
        i_guarda = ROUTER.index('if "ARGUMENTACIÓN JURÍDICA" in _dictamen_txt:')
        assert i_limpieza < i_guarda, "la limpieza quedó después de la guarda de persistencia"

    def test_usa_el_codigo_de_la_glosa_del_resultado(self):
        assert 'getattr(resultado, "codigo_glosa", "")' in ROUTER

    def test_nunca_tumba_un_dictamen(self):
        """Una limpieza cosmética no puede costar el análisis."""
        assert "[ULTIMA-MILLA] no aplicada" in ROUTER
        i = ROUTER.index("[ULTIMA-MILLA]")
        assert "try:" in ROUTER[i - 900 : i]


class TestElTextoExactoQueSalioEnPantalla:
    @pytest.mark.parametrize(
        "entrada,esperado",
        [
            (
                "<div><b>Servicio objetado:</b> OSTEOSÍNTESIS DE FÉMUR código CL4506</div>",
                "<div><b>Servicio objetado:</b> OSTEOSÍNTESIS DE FÉMUR</div>",
            ),
            (
                "<div><b>Servicio objetado:</b> OSTEOSÍNTESIS DE FÉMUR – código CL4506</div>",
                "<div><b>Servicio objetado:</b> OSTEOSÍNTESIS DE FÉMUR</div>",
            ),
            (
                "Servicio objetado: OSTEOSÍNTESIS DE FÉMUR (código CL4506)",
                "Servicio objetado: OSTEOSÍNTESIS DE FÉMUR",
            ),
        ],
    )
    def test_lo_borra(self, entrada: str, esperado: str):
        assert _quitar_causal_propia_del_cuerpo(entrada, "CL4506") == esperado

    def test_es_idempotente(self):
        """Correr dos veces da lo mismo: no rompe lo ya limpio."""
        t = "<div>Servicio objetado: OSTEOSÍNTESIS DE FÉMUR código CL4506</div>"
        una = _quitar_causal_propia_del_cuerpo(t, "CL4506")
        assert _quitar_causal_propia_del_cuerpo(una, "CL4506") == una

    def test_no_toca_un_cups_real(self):
        t = "<div>Servicio objetado: HEMOGRAMA IV código 902210</div>"
        assert _quitar_causal_propia_del_cuerpo(t, "CL4506") == t


class TestLaNotaOperatoriaMandaDesdeElSystem:
    """Punto 2 del pedido: no una sugerencia al final, un mandato al arranque."""

    def test_la_regla_abre_el_modulo_de_pertinencia(self):
        i_mod = PROMPTS.index("MÓDULO: PERTINENCIA CLÍNICA (CL/PE)")
        i_regla = PROMPTS.index("REGLA 0", i_mod)
        i_central = PROMPTS.index("ARGUMENTO CENTRAL (cuando NO hay", i_mod)
        assert i_regla < i_central, "la regla volvió a quedar después del argumento central"
        assert i_regla - i_mod < 200, "la regla se alejó del encabezado del módulo"

    def test_prohibe_abrir_con_autonomia_medica(self):
        assert "PROHIBIDO abrir con autonomía médica cuando existe nota operatoria" in PROMPTS

    def test_manda_sobre_el_resto_del_modulo(self):
        assert "MANDA SOBRE TODO LO QUE SIGUE EN ESTE MÓDULO" in PROMPTS

    def test_los_hallazgos_van_primero_y_la_ley_al_final(self):
        i_hall = PROMPTS.index("LOS HALLAZGOS INTRAOPERATORIOS, TRANSCRITOS")
        i_ley = PROMPTS.index("RECIÉN AQUÍ la Ley 1751/2015")
        assert i_hall < i_ley

    def test_los_hallazgos_son_ejemplos_no_una_lista_fija(self):
        """No se puede fijar «fractura diafisaria»: eso es de ESTE caso."""
        assert "Son EJEMPLOS de" in PROMPTS
        assert "transcriba los del documento real, no estos" in PROMPTS

    def test_prohibe_el_folio_inventado(self):
        assert "NUNCA un folio\n      inventado" in PROMPTS or "NUNCA un folio" in PROMPTS
