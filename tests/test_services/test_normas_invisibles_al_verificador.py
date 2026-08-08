"""Dos formas de citar una norma que el verificador no veía.

OT-028 · 06-08-2026. El dictamen lleva un bloque «FUNDAMENTO NORMATIVO» y un
sello que dice cuántas citas se verificaron contra el corpus. Ese sello es lo
que hace que el auditor radique sin volver a revisar. Dos formas de escribir
una norma se le escapaban por completo — ni siquiera se contaban como cita,
así que una norma inventada salía con «0 hallazgos»:

  1. **Resolución sin tilde.** De las cinco palabras clave (Ley, Decreto,
     Acuerdo, Circular, Resolución) solo esta lleva tilde, y el patrón la
     exigía. El dictamen se radica en MAYÚSCULA SOSTENIDA y hay rutas que
     pierden la tilde: escrito "RESOLUCION 9999 DE 2030", invisible.

  2. **Sentencia con «de» en vez de barra.** Solo se reconocía "T-760/2008".
     La forma que el motor escribe en prosa —"Sentencia T-994 de 2029"— no
     se contaba. Es exactamente la trampa que Yesid puso en la glosa CL0301
     de FAMISANAR: esa sentencia no existe.
"""

from __future__ import annotations

from app.services.citation_verifier import verificar_citas


def _inexistentes(texto: str) -> list[dict]:
    r = verificar_citas(texto, eps="COOSALUD")
    return [i for i in r["issues"] if i["tipo"] == "NORMA_INEXISTENTE"]


def _citas(texto: str) -> int:
    return verificar_citas(texto, eps="COOSALUD")["total_citas"]


class TestLaResolucionSinTilde:
    def test_una_resolucion_inventada_ya_se_marca(self):
        assert _inexistentes("EN VIRTUD DE LA RESOLUCION 9999 DE 2030 DEL MINISTERIO.")

    def test_una_resolucion_real_pasa(self):
        assert not _inexistentes("EN VIRTUD DE LA RESOLUCION 2284 DE 2023 DEL MINISTERIO.")

    def test_con_tilde_sigue_funcionando(self):
        assert _inexistentes("EN VIRTUD DE LA RESOLUCIÓN 9999 DE 2030.")
        assert not _inexistentes("EN VIRTUD DE LA RESOLUCIÓN 2284 DE 2023.")

    def test_la_abreviatura_sin_tilde(self):
        assert _citas("SEGUN LA RES. 2284/2023.") >= 1

    def test_antes_ni_se_contaba(self):
        """El defecto no era marcar mal: era no mirar. Sin cita contada, el
        sello del dictamen decía «0 hallazgos» sobre una norma inventada."""
        assert _citas("EN VIRTUD DE LA RESOLUCION 9999 DE 2030.") >= 1


class TestLaSentenciaConDe:
    def test_una_sentencia_inventada_ya_se_marca(self):
        """La trampa de CL0301 de FAMISANAR: la T-994 de 2029 no existe."""
        assert _inexistentes("CONFORME A LA SENTENCIA T-994 DE 2029 DE LA CORTE.")

    def test_una_sentencia_real_pasa(self):
        assert not _inexistentes("CONFORME A LA SENTENCIA T-760 DE 2008.")

    def test_la_forma_con_barra_sigue_funcionando(self):
        assert not _inexistentes("CONFORME A LA SENTENCIA T-760/2008.")
        assert _inexistentes("CONFORME A LA SENTENCIA T-994/2029.")

    def test_las_tres_salas(self):
        for sigla in ("T", "C", "SU"):
            assert _citas(f"SENTENCIA {sigla}-9999 DE 2031.") >= 1, sigla


class TestNoSeMarcaDeMas:
    def test_las_normas_del_dia_a_dia(self):
        d = (
            "EN VIRTUD DEL ARTICULO 57 DE LA LEY 1438 DE 2011, EL DECRETO 4747 DE 2007 "
            "Y LA RESOLUCION 2284 DE 2023, SE SOLICITA EL LEVANTAMIENTO."
        )
        assert not _inexistentes(d)

    def test_un_numero_suelto_no_es_una_sentencia(self):
        """ "C-313" dentro de un código no puede leerse como sentencia."""
        d = "EL PROCEDIMIENTO CON CODIGO INTERNO C-313 FUE PRESTADO."
        assert not _inexistentes(d)

    def test_dictamen_sin_normas(self):
        assert _citas("ESE HUS NO ACEPTA LA GLOSA. SE SOLICITA EL LEVANTAMIENTO.") == 0

    def test_texto_vacio(self):
        assert _citas("") == 0


class TestLasAbreviaturasConDe:
    """Tercer punto ciego del mismo barrido: las abreviaturas solo aceptaban
    barra o guion. "RES. 2284 DE 2023" y "DEC. 4747 DE 2007" son formas que
    el propio prompt del motor usa."""

    def test_resolucion_abreviada_inventada(self):
        assert _inexistentes("SEGUN LA RES. 9999 DE 2030 DEL MINISTERIO.")

    def test_resolucion_abreviada_real(self):
        assert not _inexistentes("SEGUN LA RES. 2284 DE 2023 DEL MINISTERIO.")

    def test_decreto_abreviado_inventado(self):
        assert _inexistentes("SEGUN EL DEC. 8888 DE 2031.")

    def test_decreto_abreviado_real(self):
        assert not _inexistentes("SEGUN EL DEC. 4747 DE 2007.")

    def test_la_forma_con_barra_sigue_funcionando(self):
        assert not _inexistentes("SEGUN LA RES. 2284/2023 Y EL DEC. 4747/2007.")

    def test_todas_las_formas_del_dia_a_dia_se_cuentan(self):
        """Barrido: si mañana alguien angosta un patrón, esto lo dice."""
        for forma in (
            "LEY 1438 DE 2011",
            "LEY 1438/2011",
            "DECRETO 4747 DE 2007",
            "DEC. 4747/2007",
            "DEC. 4747 DE 2007",
            "RESOLUCION 2284 DE 2023",
            "RESOLUCIÓN 2284/2023",
            "RES. 2284 DE 2023",
            "CIRCULAR 030 DE 2013",
            "ACUERDO 260 DE 2004",
            "SENTENCIA T-760 DE 2008",
            "SENTENCIA T-760/2008",
        ):
            assert _citas(forma) >= 1, f"forma no reconocida: {forma}"
