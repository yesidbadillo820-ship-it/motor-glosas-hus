"""Ronda 30 — regresiones de lógica de servicios.

#54 CUPS institucionales (S/M/FMQ) no deben homologarse por dígitos.
#56 defensa clínica: 'inhibidor de bomba de protones' no dispara hemofilia.
#58 BM25 tokeniza igual MAYÚSCULAS con tilde que minúsculas.
#60 routing: 'inhibidor de bomba de protones' no escala a Anthropic.
#61 UVB: redondeo half-up real en el punto medio.
"""

from __future__ import annotations


class TestCupsInstitucionalNoHomologa:  # #54
    def test_codigo_con_letra_inicial_no_genera_candidatos_por_digitos(self):
        from app.services.cups_soat_service import _normalizar_cups

        cands = _normalizar_cups("S11101")
        # no debe aparecer la forma zfill de solo-dígitos (colisiona con SOAT)
        assert "011101" not in cands
        assert "11101" not in cands

    def test_codigo_numerico_si_homologa(self):
        from app.services.cups_soat_service import _normalizar_cups

        cands = _normalizar_cups("39101")
        assert "039101" in cands or "39101" in cands


class TestDefensaClinicaContexto:  # #56
    def test_inhibidor_bomba_protones_no_dispara_hemofilia(self):
        from app.services.defensa_clinica import detectar_defensa_clinica

        d = detectar_defensa_clinica("Se objeta omeprazol, inhibidor de bomba de protones")
        assert d is None or d.get("key") != "hemofilia_inhibidores"

    def test_hemofilia_con_inhibidor_del_factor_si_dispara(self):
        from app.services.defensa_clinica import detectar_defensa_clinica

        d = detectar_defensa_clinica("Paciente con hemofilia A e inhibidor del factor VIII")
        assert d is not None and d.get("key") == "hemofilia_inhibidores"


class TestRagTokenizacion:  # #58
    def test_mayusculas_con_tilde_tokeniza_igual(self):
        from app.services.rag_service import _tokenizar

        assert _tokenizar("FACTURACIÓN MÉDICA") == _tokenizar("facturación médica")


class TestRoutingInhibidor:  # #60
    def test_ibp_no_escala(self):
        from app.services.routing_complejidad import detectar_complejidad_critica

        r = detectar_complejidad_critica(
            valor=45_000,
            num_pdfs=0,
            num_codigos=1,
            texto_glosa="Se objeta omeprazol, inhibidor de bomba de protones",
            contexto_pdf="",
        )
        assert not r.es_complejo

    def test_hemofilia_con_inhibidor_del_factor_si_escala(self):
        from app.services.routing_complejidad import detectar_complejidad_critica

        r = detectar_complejidad_critica(
            valor=45_000,
            num_pdfs=0,
            num_codigos=1,
            texto_glosa="Hemofilia con inhibidor del factor VIII, se aplica FEIBA",
            contexto_pdf="",
        )
        assert r.es_complejo


class TestUvbRedondeo:  # #61
    def test_punto_medio_sube(self):
        from app.services.uvb import _redondear_a_centena

        assert _redondear_a_centena(71_850.0) == 71_900
        assert _redondear_a_centena(6_850.0) == 6_900
