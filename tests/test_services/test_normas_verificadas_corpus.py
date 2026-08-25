"""Las normas del corpus, verificadas una por una contra fuente oficial.

QUÉ PASÓ (25-08-2026). Después de descubrir que dos de cada tres sentencias del
sistema decían algo que la sentencia no dice, se revisaron con el mismo rigor
las leyes, decretos, resoluciones y circulares que el motor cita al redactar.
El resultado repite el patrón:

  · **Resolución 1604 de 2024** — el sistema la daba como «modificaciones al
    RIPS y a la factura electrónica». Es un acto del Ministerio del INTERIOR que
    le reconoce personería jurídica a una iglesia. Ni siquiera es de salud.
  · **Resolución 866 de 2021** — el sistema la daba como «los RIPS» y la ofrecía
    para refutar glosas de soportes en cuatro archivos distintos. Reglamenta los
    datos clínicos para la interoperabilidad de la historia clínica. Se leyó su
    texto completo: la sigla RIPS no aparece ni una vez.
  · **Resolución 2641 de 2025** — no existe. La real es de 2024, y además está
    derogada desde el 1 de enero de 2026.
  · **Resolución 2335 de 2023** — el sistema la daba como «cáncer infantil» y un
    dictamen la citó «en materia de RIPS». Trata de la ejecución y el
    seguimiento de los acuerdos de voluntades, que es MÁS útil para cartera.
  · **Circular 007 de 2025** — el sistema la daba como «cronograma». Es una
    circular conjunta con la Superintendencia que PROHÍBE a las entidades
    imponerle barreras y exigencias no normadas a los prestadores. También más
    útil de lo que decía el rótulo.
  · **Decreto 064 de 2020** — el sistema le agregaba «flujo de recursos», que no
    es suyo. Trata de afiliación al régimen subsidiado y de oficio.

Y tres resultaron no vigentes: la Resolución 2275 de 2023, la Circular 025 de
2024 y la Resolución 042 de 2020 de la DIAN.
"""

import pytest

from app.services.normativa_completa import _TODAS_LAS_NORMAS as CORPUS


class TestLoQueDecianYNoEra:
    @pytest.mark.parametrize(
        "clave,tema_que_no_es_suyo",
        [
            ("RESOLUCION 866 DE 2021", "rips"),
            ("RESOLUCION 1604 DE 2024", "rips"),
            ("RESOLUCION 2335 DE 2023", "cáncer"),
            ("DECRETO 064 DE 2020", "flujo de recursos"),
        ],
    )
    def test_ya_no_se_les_atribuye_el_tema_ajeno(self, clave, tema_que_no_es_suyo):
        datos = CORPUS[clave]
        rotulo = f"{datos.get('titulo', '')} {datos.get('ambito', '')}".lower()
        assert tema_que_no_es_suyo not in rotulo, f"{clave} volvió a rotularse mal"

    def test_la_resolucion_2641_de_2025_no_existe_y_ya_no_esta(self):
        assert "RESOLUCION 2641 DE 2025" not in CORPUS
        assert "RESOLUCION 2641 DE 2024" in CORPUS

    def test_las_que_se_corrigieron_quedaron_marcadas(self):
        for clave in (
            "RESOLUCION 866 DE 2021",
            "RESOLUCION 1604 DE 2024",
            "RESOLUCION 2335 DE 2023",
            "CIRCULAR 007 DE 2025",
            "CIRCULAR 18 DE 2024",
            "DECRETO 064 DE 2020",
            "RESOLUCION 2641 DE 2024",
            "RESOLUCION 2706 DE 2025",
        ):
            assert CORPUS[clave].get("verificada"), f"{clave} quedó sin marca de verificación"


class TestLaCupsQueRigeHoy:
    def test_la_2706_de_2025_esta_cargada(self):
        n = CORPUS["RESOLUCION 2706 DE 2025"]
        assert n["vigente"] is True
        assert "CUPS" in n["titulo"]
        assert "1 de enero de 2026" in n["notas"]

    def test_la_2641_de_2024_quedo_como_derogada(self):
        n = CORPUS["RESOLUCION 2641 DE 2024"]
        assert n["vigente"] is False
        assert "2706" in n["derogada_por"]

    def test_citar_la_2641_avisa_pero_citar_la_2706_pasa_limpio(self):
        from app.services.citation_verifier import verificar_citas

        con_derogada = verificar_citas("CONFORME A LA RESOLUCIÓN 2641 DE 2024.")
        assert any(i["tipo"] == "NORMA_DEROGADA" for i in con_derogada["issues"])
        assert verificar_citas("CONFORME A LA RESOLUCIÓN 2706 DE 2025.")["issues"] == []


class TestLaCitaCorrectaYaNoSeBorra:
    """El motor borraba «Resolución 2641 de 2024» creyéndola inventada."""

    def test_el_dictamen_conserva_la_cita(self):
        from app.services.glosa_service import _neutralizar_alucinaciones_prompt

        texto = "LA RESOLUCIÓN 2641 DE 2024 ESTABLECE LA DESCRIPCIÓN DEL CUPS FACTURADO."
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "2641 DE 2024" in resultado.upper()

    def test_ya_no_deja_la_pseudo_norma_en_su_lugar(self):
        from app.services.glosa_service import _neutralizar_alucinaciones_prompt

        texto = "LA RESOLUCIÓN 2641 DE 2024 ESTABLECE LA DESCRIPCIÓN DEL CUPS."
        resultado = _neutralizar_alucinaciones_prompt(texto).upper()
        assert "LA NORMATIVA VIGENTE DEL MINISTERIO DE SALUD" not in resultado


class TestElMotorYaNoOfreceLa866ComoNormaDeRips:
    RUTAS = [
        "app/services/analizador_motivo_eps.py",
        "app/services/conciliador_ia.py",
        "app/services/multi_agente.py",
    ]

    @pytest.mark.parametrize("ruta", RUTAS)
    def test_ningun_texto_la_presenta_como_rips(self, ruta):
        import io

        renglones = io.open(ruta, encoding="utf-8").read().split("\n")
        for i, renglon in enumerate(renglones):
            if "866" not in renglon or renglon.strip().startswith("#"):
                continue
            vecindad = " ".join(renglones[max(0, i - 2) : i + 3]).upper()
            assert "RIPS" not in vecindad, (
                f"{ruta} volvió a ofrecer la Res. 866/2021 como norma de RIPS: "
                f"{renglon.strip()[:90]}"
            )
