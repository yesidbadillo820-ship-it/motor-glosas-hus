"""Tests de Inteligencia Ambiental (Ola 4)."""

from __future__ import annotations

from app.services.inteligencia_ambiental import (
    analisis_rapido,
    generar_sugerencias_contextuales,
)


class TestAnalisisRapido:
    def test_detecta_codigo_simple(self):
        r = analisis_rapido("TA0201 - mayor valor cobrado")
        assert "TA0201" in r.codigos_detectados
        assert r.plantilla_predicha is not None
        assert r.plantilla_predicha.codigo_familia == "TA"

    def test_detecta_valor_con_pesos(self):
        r = analisis_rapido("TA0201 valor objetado $1.500.000")
        assert 1_500_000 in r.valores_detectados or 1500000 in r.valores_detectados

    def test_detecta_multi_codigo(self):
        r = analisis_rapido("TA0201 y SO0501 en la misma factura")
        assert "TA0201" in r.codigos_detectados
        assert "SO0501" in r.codigos_detectados
        assert r.complejidad_estimada == "COMPLEJA"

    def test_detecta_ratificacion(self):
        r = analisis_rapido("la EPS ratifica la glosa anterior")
        assert r.es_ratificacion
        assert r.complejidad_estimada == "COMPLEJA"

    def test_detecta_extemporanea(self):
        r = analisis_rapido("la glosa fue extemporánea, después del plazo")
        assert r.es_extemporanea
        assert r.complejidad_estimada == "COMPLEJA"

    def test_detecta_numero_factura(self):
        r = analisis_rapido("Factura FE-123456 con código TA0201")
        assert r.numero_factura is not None
        assert "123456" in r.numero_factura

    def test_detecta_fecha(self):
        r = analisis_rapido("Glosa radicada el 15/03/2026 con código TA0201")
        assert r.fecha_detectada == "15/03/2026"

    def test_alto_valor_complejo(self):
        r = analisis_rapido("TA0201 por $2.500.000")
        assert r.complejidad_estimada == "COMPLEJA"

    def test_bajo_valor_simple(self):
        r = analisis_rapido("TA0201 por $50.000")
        assert r.complejidad_estimada == "SIMPLE"

    def test_prediccion_familia_so(self):
        r = analisis_rapido("SO0501 falta historia clínica")
        assert r.plantilla_predicha.codigo_familia == "SO"
        assert "SO-G" in r.plantilla_predicha.plantilla_id

    def test_prediccion_familia_cl(self):
        r = analisis_rapido("CL0101 no pertinencia clínica")
        assert r.plantilla_predicha.codigo_familia == "CL"

    def test_sin_codigo_sin_prediccion(self):
        r = analisis_rapido("Mayor valor cobrado pero sin código")
        assert r.codigos_detectados == []
        assert r.plantilla_predicha is None

    def test_texto_vacio(self):
        r = analisis_rapido("")
        assert r.codigos_detectados == []
        assert r.valores_detectados == []
        assert r.complejidad_estimada == "MEDIA"


class TestSugerenciasContextuales:
    def test_victoria_previa(self):
        historico = [
            {
                "eps": "FAMISANAR",
                "codigo": "TA0201",
                "estado": "LEVANTADA",
                "valor": 500_000,
                "dictamen_id": 42,
            }
        ]
        sugs = generar_sugerencias_contextuales(
            eps="FAMISANAR", codigo="TA0201", historico_glosas=historico
        )
        assert any(s.tipo == "victoria_previa" for s in sugs)
        s = next(s for s in sugs if s.tipo == "victoria_previa")
        assert "ganaste" in s.titulo.lower()
        assert "42" in s.descripcion

    def test_warning_multiples_ratificadas(self):
        historico = [
            {"eps": "FAMISANAR", "codigo": "TA0201", "estado": "RATIFICADA", "valor": 100_000}
        ] * 4
        sugs = generar_sugerencias_contextuales(
            eps="FAMISANAR", codigo="TA0201", historico_glosas=historico
        )
        assert any(s.tipo == "warning" for s in sugs)

    def test_alto_valor_sugiere_claude(self):
        sugs = generar_sugerencias_contextuales(
            eps="FAMISANAR", codigo="TA0201", valor=2_000_000, historico_glosas=[]
        )
        # Sin histórico no hay victoria previa, pero sí sugerencia de alto valor
        assert any("alto valor" in s.titulo.lower() for s in sugs)

    def test_orden_por_relevancia(self):
        historico = [
            {
                "eps": "FAMISANAR",
                "codigo": "TA0201",
                "estado": "LEVANTADA",
                "valor": 500_000,
                "dictamen_id": 42,
            }
        ]
        sugs = generar_sugerencias_contextuales(
            eps="FAMISANAR", codigo="TA0201", valor=2_000_000, historico_glosas=historico
        )
        if len(sugs) >= 2:
            assert sugs[0].relevancia >= sugs[1].relevancia

    def test_sin_historico_no_explota(self):
        sugs = generar_sugerencias_contextuales(eps="X", codigo="TA0201")
        assert sugs == []
