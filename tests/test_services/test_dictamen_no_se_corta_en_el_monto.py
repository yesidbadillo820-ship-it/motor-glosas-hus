"""El dictamen no se corta dentro de una cifra.

05-08-2026, glosa de prueba de POSITIVA: el dictamen terminó literalmente en

    "...SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA CO0102 Y EL RECONOCIMIENTO
     INTEGRO DEL VALOR $ 12."

No fue el modelo truncando: fue el propio post-proceso. Al recortar la coda
procesal (lo que va después del cierre canónico), buscaba «el siguiente
punto» — y en «$ 12.300.000» el primer punto es el separador de miles.

El mismo defecto cortaba otras tres frases legítimas: «...A LA E.» (por
E.S.E.), «...CONFORME AL ART.» (por ART. 87) y «...FACTURA NO.» (NO. 12345).
"""

from __future__ import annotations

from app.services.dictamen_postprocesor import truncar_despues_de_levantamiento

ANCLA = "SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA"


class TestNoCortaDentroDeUnaCifra:
    def test_el_caso_real_de_positiva(self):
        texto = f"{ANCLA} CO0102 Y EL RECONOCIMIENTO ÍNTEGRO DEL VALOR $ 12.300.000."
        assert truncar_despues_de_levantamiento(texto).endswith("$ 12.300.000.")

    def test_con_decimales_tambien(self):
        texto = f"{ANCLA} Y EL PAGO DE $ 1.250.000,50."
        assert "1.250.000,50" in truncar_despues_de_levantamiento(texto)

    def test_no_corta_en_la_sigla_del_hospital(self):
        texto = f"{ANCLA} Y EL PAGO A LA E.S.E. HOSPITAL UNIVERSITARIO DE SANTANDER."
        salida = truncar_despues_de_levantamiento(texto)
        assert "HOSPITAL UNIVERSITARIO DE SANTANDER" in salida

    def test_no_corta_en_una_abreviatura_con_numero(self):
        for texto in (
            f"{ANCLA} CONFORME AL ART. 87 DEL DECRETO 2423 DE 1996.",
            f"{ANCLA} Y EL PAGO DE LA FACTURA NO. 12345 POR $ 4.000.000.",
        ):
            salida = truncar_despues_de_levantamiento(texto)
            assert not salida.rstrip().endswith(("ART.", "NO.")), salida


class TestSigueRecortandoLaCoda:
    """Lo que la función existe para hacer no puede dejar de hacerse."""

    def test_borra_la_coleta_procesal(self):
        texto = (
            f"{ANCLA} Y EL RECONOCIMIENTO DEL VALOR $ 3.450.000. "
            "LA ENTIDAD CUENTA CON 10 DÍAS HÁBILES PARA RESPONDER. "
            "QUEDAMOS ATENTOS."
        )
        salida = truncar_despues_de_levantamiento(texto)
        assert "3.450.000" in salida
        assert "QUEDAMOS ATENTOS" not in salida
        assert "10 DÍAS HÁBILES" not in salida

    def test_funciona_con_html_pegado_al_punto(self):
        texto = f"{ANCLA} Y EL PAGO DE $ 3.450.000.<br/>QUEDAMOS ATENTOS A SU RESPUESTA."
        salida = truncar_despues_de_levantamiento(texto)
        assert "3.450.000" in salida
        assert "QUEDAMOS ATENTOS" not in salida

    def test_la_coda_por_conjuncion_sigue_cortando_en_el_ancla(self):
        texto = f"{ANCLA} Y, DE PERSISTIR LA OBJECIÓN, SE INVITA A MESA DE CONCILIACIÓN."
        salida = truncar_despues_de_levantamiento(texto)
        assert "MESA DE CONCILIACIÓN" not in salida

    def test_sigue_siendo_idempotente(self):
        texto = f"{ANCLA} Y EL RECONOCIMIENTO DEL VALOR $ 12.300.000. QUEDAMOS ATENTOS."
        una = truncar_despues_de_levantamiento(texto)
        assert truncar_despues_de_levantamiento(una) == una

    def test_sin_ancla_no_toca_nada(self):
        texto = "ESE HUS NO ACEPTA LA GLOSA POR $ 12.300.000."
        assert truncar_despues_de_levantamiento(texto) == texto
