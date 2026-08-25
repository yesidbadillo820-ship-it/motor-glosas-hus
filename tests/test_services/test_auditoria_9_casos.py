"""Los defectos que encontró la auditoría independiente de 9 dictámenes
(24-08-2026).

Un segundo auditor revisó nueve dictámenes reales del motor (GL-188 a GL-198)
con un criterio duro: «nunca dar por cierto lo que no está soportado». Veredicto:
7 de 9 no aptos para radicar, promedio 25/100, y —lo más incómodo— **fallas
críticas en 4 de los 5 casos que el propio Quality Gate había marcado como
validados**. El sello de «✓ validado» revisa consistencia de citas, no si el
argumento responde a la causal ni si el contrato es el de la EPS correcta.

Cada prueba de acá nace de un hallazgo concreto de esa auditoría, con el caso
que lo destapó anotado.
"""

from __future__ import annotations

import pytest

from app.services.eps_del_texto import (
    choque_de_eps,
    eps_declaradas_en_texto,
    mensaje_de_choque,
)
from app.services.glosa_service import _solo_normas_citables


class TestElFundamentoNormativoSoloTraeNormas:
    """GL-198: bajo el título «3 normas más relevantes para este caso» se
    imprimió «LA NORMATIVA DE CONTINUIDAD Y COBERTURA DEL SISTEMA GENERAL DE
    SALUD». Eso no es una norma: no tiene ley, decreto ni artículo, y nadie
    puede ir a verificarlo ante la EPS.

    Sale de una defensa que SÍ funciona —cuando la glosa no es de urgencias,
    el motor reemplaza la cita del Art. 168 Ley 100 por esa frase neutra para
    no citar una norma inaplicable— pero la frase se colaba a la lista, donde
    parece una cita. La lista iba de la IA al HTML sin ningún filtro.
    """

    def test_la_frase_del_caso_real_no_pasa(self):
        entrada = (
            "LA NORMATIVA DE CONTINUIDAD Y COBERTURA DEL SISTEMA GENERAL DE SALUD"
            "|RESOLUCIÓN 2284/2023"
            "|ARTÍCULO 87 DEL DECRETO 2423 DE 1996"
        )
        salida = _solo_normas_citables(entrada)
        assert "CONTINUIDAD Y COBERTURA" not in salida
        assert "RESOLUCIÓN 2284/2023" in salida
        assert "DECRETO 2423 DE 1996" in salida

    @pytest.mark.parametrize(
        "norma",
        [
            "CIRCULAR EXTERNA 047 DE 2025",
            "RESOLUCIÓN 2284/2023",
            "ARTÍCULO 87 DEL DECRETO 2423 DE 1996",
            "SENTENCIA T-760 DE 2008",
            "ANEXO TÉCNICO No. 6 RESOLUCIÓN 3047 DE 2008",
            "CONSTITUCIÓN POLÍTICA ART. 49",
            "ART. 1602 C.C.",
            "LEY 1438 DE 2011",
        ],
    )
    def test_las_normas_de_verdad_pasan(self, norma):
        """El filtro no puede volverse un censor: si corta normas reales, el
        dictamen se queda sin fundamento y eso es peor."""
        assert _solo_normas_citables(norma) == norma

    @pytest.mark.parametrize(
        "frase",
        [
            "LA NORMATIVA DE CONTINUIDAD Y COBERTURA DEL SISTEMA GENERAL DE SALUD",
            "EL PRINCIPIO DE BUENA FE CONTRACTUAL",
            "LA JURISPRUDENCIA APLICABLE AL CASO",
            "EL MARCO NORMATIVO VIGENTE",
        ],
    )
    def test_las_frases_sin_norma_se_cortan(self, frase):
        assert _solo_normas_citables(frase) == ""

    def test_si_no_queda_ninguna_no_se_pinta_el_bloque(self):
        """Mejor sin fundamento que con uno que no se puede verificar: el
        HTML solo dibuja el bloque cuando `normas_clave` tiene algo."""
        assert _solo_normas_citables("EL MARCO NORMATIVO|LA JURISPRUDENCIA") == ""

    def test_una_frase_que_SI_cita_articulos_se_conserva(self):
        """«PACTA SUNT SERVANDA — ART. 1602 C.C. Y ART. 871 C.CO.» es prosa,
        pero trae artículos citables: el auditor puede ir a verificarlos."""
        entrada = "EL RÉGIMEN TARIFARIO Y CONTRACTUAL APLICABLE (PACTA SUNT SERVANDA — ART. 1602 C.C. Y ART. 871 C.CO.)"
        assert _solo_normas_citables(entrada) == entrada


class TestElValorObjetadoDiceLaVerdad:
    """5 de los 9 casos (GL-193, 195, 196, 197, 198) salieron con la celda
    VALOR OBJETADO en «$ 0.00» —el texto pegado no traía cifra— y aun así el
    dictamen afirmaba «GLOSA NO ACEPTADA · SUBSANADA EN SU TOTALIDAD» con el
    mismo tono de seguridad que un caso con cifra clara.

    Un documento radicado ante la EPS diciendo que se objetan cero pesos se
    cae solo. No se inventa una cifra —eso ya lo impide otra defensa del
    motor—: se escribe lo único cierto, que el valor está en el expediente.
    """

    def _render(self, valor):
        from app.services.glosa_service import GlosaService

        return GlosaService._generar_dictamen_html(
            GlosaService.__new__(GlosaService),
            codigo="TA2902",
            valor=valor,
            cod_res="RE9901",
            desc_res="GLOSA NO ACEPTADA",
            # Con cuerpo de verdad: el render rechaza los argumentos cortos
            # (DictamenSinArgumentoError), y esa defensa se respeta.
            argumento=(
                "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE DIFERENCIA "
                "TARIFARIA, DADO QUE EL VALOR FACTURADO CORRESPONDE A LA TARIFA "
                "PACTADA ENTRE LAS PARTES PARA LA VIGENCIA DE LA ATENCIÓN. LA "
                "ENTIDAD PAGADORA NO APORTÓ PRUEBA DE UNA TARIFA DISTINTA. SE "
                "SOLICITA EL LEVANTAMIENTO DE LA GLOSA Y EL PAGO ÍNTEGRO."
            ),
            eps="PPL",
            tipo="TA_TARIFA",
        )

    @pytest.mark.parametrize("cero", ["$ 0.00", "$0.00", "$ 0", "0", ""])
    def test_ninguna_forma_del_cero_se_imprime(self, cero):
        html = self._render(cero)
        assert "VALOR EN EL EXPEDIENTE" in html
        assert "$ 0.00" not in html

    def test_una_cifra_de_verdad_se_respeta(self):
        html = self._render("$ 777.793,35")
        assert "$ 777.793,35" in html
        assert "VALOR EN EL EXPEDIENTE" not in html


class TestNoDefenderUnaEpsConElContratoDeOtra:
    """GL-192 y GL-198, el hallazgo más caro del lote: el selector «EPS /
    Entidad Pagadora» quedó con la EPS del caso anterior, el texto pegado
    declaraba otra, y el motor construyó la defensa con el contrato y las
    tarifas de la entidad equivocada — en GL-192 defendió a PPL citando el
    contrato 0525/2017 + Otrosí 03, que es de POSITIVA.

    No es distracción del auditor: el formulario conserva la EPS anterior y el
    texto se pega encima. Pasó DOS veces en nueve casos.
    """

    def test_el_caso_GL192_se_detiene(self):
        texto = "EPS: PPL · Código: AU2001 (falta autorización) · CUPS: 879101 — TAC de cráneo"
        assert choque_de_eps("POSITIVA", texto) == "PPL"

    def test_el_caso_GL198_se_detiene(self):
        texto = "EPS: POSITIVA · Valor glosado: $0 · y otro con $777.793,35"
        assert choque_de_eps("COMPENSAR", texto) == "POSITIVA"

    def test_cuando_coinciden_no_estorba(self):
        texto = "EPS: PPL · Código: TA2902 · Servicio: cualquier CUPS quirúrgico"
        assert choque_de_eps("PPL", texto) is None

    def test_el_mismo_nombre_escrito_distinto_no_es_choque(self):
        """«FAMISANAR» y «FAMISANAR EPS» son la misma entidad: bloquear ahí
        sería estorbar sin razón. Se reusa el comparador del buscador de
        tarifas, que ya resuelve estos alias."""
        assert choque_de_eps("FAMISANAR", "EPS: FAMISANAR EPS · glosa por tarifa") is None
        assert choque_de_eps("FAMISANAR EPS", "EPS: FAMISANAR") is None

    def test_una_mencion_de_paso_no_bloquea(self):
        """«Paciente remitido de SALUD TOTAL» narra el caso, no declara la
        pagadora. Bloquear por eso castigaría al que escribe completo."""
        texto = "Paciente remitido de SALUD TOTAL, se glosa la estancia del 12 al 15"
        assert choque_de_eps("COOSALUD", texto) is None

    def test_sin_rotulo_no_hay_choque(self):
        assert choque_de_eps("POSITIVA", "Se glosa por mayor valor cobrado") is None

    @pytest.mark.parametrize(
        "rotulo",
        ["EPS:", "ENTIDAD PAGADORA:", "PAGADOR:", "ASEGURADORA:", "ERP:"],
    )
    def test_reconoce_las_formas_de_rotular(self, rotulo):
        assert choque_de_eps("POSITIVA", f"{rotulo} PPL · código AU2001") == "PPL"

    def test_ignora_los_rotulos_vacios(self):
        """«EPS: N/A» no declara nada; tratarlo como entidad sería un bloqueo
        absurdo."""
        for vacio in ("N/A", "NO APLICA", "SIN DEFINIR", "PENDIENTE"):
            assert choque_de_eps("POSITIVA", f"EPS: {vacio} · glosa") is None

    def test_el_mensaje_le_dice_al_auditor_que_hacer(self):
        m = mensaje_de_choque("POSITIVA", "PPL")
        assert "POSITIVA" in m and "PPL" in m
        assert "Corrija el selector" in m
        assert "CONTRATO Y LAS TARIFAS DE OTRA" in m

    def test_lee_varias_declaraciones(self):
        texto = "EPS: PPL\nENTIDAD PAGADORA: PPL\nPAGADOR: PPL"
        assert eps_declaradas_en_texto(texto) == ["PPL"]
