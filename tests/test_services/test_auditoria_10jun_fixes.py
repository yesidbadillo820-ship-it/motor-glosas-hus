"""Regresiones de la auditoría 10-jun-2026 (evaluación de estrés con 10
glosas de texto libre contra DISPENSARIO MEDICO).

Hallazgos corregidos aquí:
  P0-1 Citas de cláusulas/normas FABRICADAS entre comillas dobles/simples
       escapaban a la red (solo se verificaban «chevrones»). Caso real:
       "CLÁUSULA 12... ESTABLECE: 'LAS PARTES SE OBLIGAN A NO REBATIR...'"
       (inventada y autodestructiva) se radicó sin alarma.
  P0-2 "$850 millones" se parseaba como $850 (el regex descartaba la
       palabra) → BD/KPIs con valor 10^6 veces menor + router clasificó
       MEDIA→Groq la glosa más grande del día.
  P1-4 El gauge "% éxito" (87-92% en TODO) contradecía la confianza real
       (41-65% REVISAR): bonus por cita regex (las fabricadas SUBÍAN el
       score) y cero descuentos.
  P1-5 Texto libre sin código → Groq (debió ser COMPLEJA→Claude: notas
       2.2/10 vs 7.7/10); DISPENSARIO/DIGSA/DMBUG no estaban en
       eps_critica; clasificador de familias por substring perdía
       UCI/reingreso/tornillos → fallback FA genérico.
  P2-6 La misma cláusula citada DOS veces en un dictamen no la atrapaba
       nadie (_truncar_runaway solo ve loops consecutivos de n-gramas).
"""

from __future__ import annotations

import pytest

from app.services.citation_verifier import verificar_citas
from app.services.glosa_service import (
    GlosaService,
    _ajustar_score_por_evidencia,
    _dedup_oraciones_largas,
)
from app.services.ia_router import clasificar_complejidad, enrutar
from app.utils.moneda import parse_valor_cop


# ─── P0-2: multiplicadores verbales en valores monetarios ───────────────


class TestParseValorMultiplicadores:
    @pytest.mark.parametrize(
        "raw,esperado",
        [
            ("$850 millones", 850_000_000.0),
            ("850 millones", 850_000_000.0),
            ("$ 850 MILLONES", 850_000_000.0),
            ("1 millón", 1_000_000.0),
            ("2,5 millones", 2_500_000.0),
            ("1.5 millones", 1_500_000.0),  # punto decimal informal
            ("120 mil", 120_000.0),
            ("120 mil pesos", 120_000.0),
            ("1,5 mil millones", 1_500_000_000.0),
            ("mil millones", 0.0),  # sin número delante no hay cifra
        ],
    )
    def test_multiplicadores(self, raw, esperado):
        assert parse_valor_cop(raw) == esperado

    @pytest.mark.parametrize(
        "raw,esperado",
        [
            ("$ 1.500.000", 1_500_000.0),
            ("7.700,00", 7_700.0),
            ("$ 850.000.000", 850_000_000.0),
            (850, 850.0),
        ],
    )
    def test_formatos_clasicos_intactos(self, raw, esperado):
        # La corrección de multiplicadores NO debe alterar el parsing
        # clásico (regresión del fix 100× de mayo).
        assert parse_valor_cop(raw) == esperado


class TestExtraerValorMultiplicadores:
    @pytest.fixture
    def svc(self):
        return GlosaService.__new__(GlosaService)  # sin __init__ (no IA)

    def test_850_millones(self, svc):
        # Caso real 10-jun-2026: entró a BD como $850 y el dashboard sumó
        # +850 (visible en los KPIs del header de la app).
        out = svc._extraer_valor(
            "Se objeta factura de $850 millones por presunta atención integral incluida en paquete."
        )
        assert out == "$ 850.000.000"

    def test_120_mil_pesos(self, svc):
        assert svc._extraer_valor("glosa por 120 mil pesos del servicio") == "$ 120.000"

    def test_valor_clasico_intacto(self, svc):
        assert svc._extraer_valor("valor objetado: $ 1.500.000") == "$ 1.500.000"

    def test_sin_valor(self, svc):
        assert svc._extraer_valor("No existe evidencia de realización.") == "$ 0.00"

    def test_fila_tsv_de_excel(self, svc):
        # Caso real 11-jun-2026: fila pegada desde Excel con el valor como
        # columna sin '$' — entraba $0 y la recomendación decía "facturó $0".
        fila = (
            "TA0801\t882298\tECOGRAFIA DOPPLER OBSTETRICA CON EVALUACION DE "
            "CIRCULACION PLACENTARIA\t36.402\tMVC SE RECONOCE A TARIFAS SOAT "
            "VIGENTE UVB NO HAY CONTRATO NI ACUERDO DE TARIFAS."
        )
        assert svc._extraer_valor(fila) == "$ 36.402"

    def test_tsv_no_confunde_cups_ni_codigo(self, svc):
        # "882298" (CUPS, sin puntos) y "TA0801" no deben tomarse como valor.
        fila = "TA0801\t882298\tSERVICIO X\tsin valor en esta fila"
        assert svc._extraer_valor(fila) == "$ 0.00"

    def test_tsv_valor_grande_con_decimales(self, svc):
        fila = "SO0601\t906466\tEXAMEN\t1.234.567,89\tmotivo"
        assert svc._extraer_valor(fila) == "$ 1.234.567,89"


# ─── P0-1: citas atribuidas entre comillas dobles/simples ───────────────


class TestCitaAtribuidaFabricada:
    def test_clausula_fabricada_entre_comillas_simples_se_detecta(self):
        # La "cláusula 12" del caso real — inventada y autodestructiva.
        texto = (
            "SE CITA LA CLÁUSULA 12 DEL CONTRATO DE PRESTACIÓN DE SERVICIOS, "
            "QUE ESTABLECE: 'LAS PARTES SE OBLIGAN A NO REBATIR NI IMPUGNAR LAS "
            "DECISIONES TOMADAS EN EL MARCO DE ESTE CONTRATO, Y A BUSCAR LA "
            "CONCILIACIÓN EN CASO DE CONTROVERSIAS'."
        )
        r = verificar_citas(texto)
        falsas = [i for i in r["issues"] if i["tipo"] == "CITA_LITERAL_FALSA"]
        assert falsas, f"la cláusula fabricada pasó sin alarma: {r}"
        assert falsas[0]["severidad"] == "ALTA"

    def test_articulo_con_texto_fabricado_entre_comillas_dobles(self):
        # Caso real 10: arts. 44/45/46 L1438 con texto literal inventado.
        texto = (
            'EL ARTICULO 44 DE LA LEY 1438 DE 2011 ESTABLECE QUE "LAS ENTIDADES '
            "PROMOTORAS DE SALUD DEBERAN RECONOCER Y PAGAR A LOS PRESTADORES LAS "
            'TARIFAS ACORDADAS EN EL CONTRATO SIN DILACION ALGUNA".'
        )
        r = verificar_citas(texto)
        assert any(i["tipo"] == "CITA_LITERAL_FALSA" for i in r["issues"])

    def test_cita_real_atribuida_pasa(self):
        # El texto REAL del art. 168 L100 (está en el corpus) citado con
        # comillas dobles + verbo de atribución NO debe flaggearse.
        texto = (
            'EL ARTÍCULO 168 DE LA LEY 100 DE 1993 ESTABLECE QUE "LA ATENCIÓN '
            "INICIAL DE URGENCIAS DEBE SER PRESTADA EN FORMA OBLIGATORIA POR TODAS "
            "LAS ENTIDADES PÚBLICAS Y PRIVADAS QUE PRESTEN SERVICIOS DE SALUD, A "
            'TODAS LAS PERSONAS, INDEPENDIENTEMENTE DE LA CAPACIDAD DE PAGO".'
        )
        r = verificar_citas(texto)
        falsas = [i for i in r["issues"] if i["tipo"] == "CITA_LITERAL_FALSA"]
        assert not falsas, f"cita real marcada como falsa: {falsas}"

    def test_cita_del_texto_de_la_glosa_no_se_flaggea(self):
        # Citar la AFIRMACIÓN de la EPS no es una cita normativa — sin
        # verbo de atribución (establece/dispone/...) no entra a la red.
        texto = (
            'LA AFIRMACIÓN DE LA AUDITORÍA DE QUE "NO EXISTE EVIDENCIA DE '
            'REALIZACIÓN DEL PROCEDIMIENTO EN LOS SOPORTES APORTADOS" NO SE '
            "AJUSTA A LA REALIDAD CLÍNICA DEL CASO."
        )
        r = verificar_citas(texto)
        falsas = [i for i in r["issues"] if i["tipo"] == "CITA_LITERAL_FALSA"]
        assert not falsas

    def test_chevrones_siguen_cubiertos(self):
        texto = "EL CONTRATO ESTABLECE «UNA OBLIGACION COMPLETAMENTE INVENTADA DE PAGO INMEDIATO TOTAL SIN AUDITORIA PREVIA ALGUNA»."
        r = verificar_citas(texto)
        assert any(i["tipo"] == "CITA_LITERAL_FALSA" for i in r["issues"])


# ─── P1-5: routing de texto libre y régimen especial ────────────────────


class TestRoutingTextoLibre:
    def test_texto_libre_sin_codigo_es_compleja(self):
        # Las 5 glosas texto-libre que cayeron a Groq promediaron 2.2/10.
        comp = clasificar_complejidad(
            valor=None,
            texto_glosa="Reingreso dentro de los 15 días atribuible a manejo deficiente de la IPS.",
        )
        assert comp == "COMPLEJA"

    def test_texto_libre_enruta_a_anthropic(self):
        d = enrutar(
            eps="NUEVA EPS",
            valor=None,
            texto_glosa="Tornillos y placas no soportados contractualmente.",
            proveedores_disponibles={"groq", "anthropic"},
        )
        assert d.modelo_recomendado == "anthropic"

    def test_con_codigo_en_texto_sigue_media(self):
        comp = clasificar_complejidad(
            valor=50_000,
            texto_glosa="TA0201 - Mayor valor cobrado en consulta por factura FE-1.",
        )
        assert comp == "MEDIA"

    def test_con_codigo_como_parametro_sigue_media(self):
        # El caller puede tener el código aunque el texto no lo repita.
        comp = clasificar_complejidad(
            valor=50_000,
            texto_glosa="Mayor valor cobrado en consulta especializada por factura.",
            codigo_glosa="TA0201",
        )
        assert comp == "MEDIA"

    @pytest.mark.parametrize(
        "eps",
        [
            "DISPENSARIO MEDICO",
            "DIGSA",
            "DMBUG",
            "DIRECCION DE SANIDAD POLICIA",
            "EJERCITO NACIONAL",
        ],
    )
    def test_regimen_especial_militar_es_critico(self, eps):
        d = enrutar(
            eps=eps,
            valor=10_000,
            texto_glosa="TA0201 - diferencia de tarifa en consulta según factura.",
            proveedores_disponibles={"groq", "anthropic"},
        )
        assert d.complejidad == "COMPLEJA"
        assert d.modelo_recomendado == "anthropic"


# ─── P1-4: gauge honesto ─────────────────────────────────────────────────


class TestGaugeHonesto:
    def test_citas_invalidas_descuentan(self):
        verif = {
            "issues": [
                {"severidad": "ALTA"},
                {"severidad": "MEDIA"},
                {"severidad": "MEDIA"},
            ]
        }
        # 92 - 8 - 3 - 3 = 78
        assert _ajustar_score_por_evidencia(92.0, verif, None) == 78.0

    def test_techo_por_confianza(self):
        # Caso real: gauge 92% con confianza 41% → tope 51.
        assert _ajustar_score_por_evidencia(92.0, None, {"score": 0.41}) == 51.0

    def test_combinado_citas_y_confianza(self):
        verif = {"issues": [{"severidad": "ALTA"}]}
        # 90 - 8 = 82 → techo conf 0.57*100+10 = 67
        assert _ajustar_score_por_evidencia(90.0, verif, {"score": 0.57}) == 67.0

    def test_piso_15(self):
        verif = {"issues": [{"severidad": "ALTA"}] * 12}
        assert _ajustar_score_por_evidencia(40.0, verif, None) == 15.0

    def test_sin_evidencia_no_cambia(self):
        assert _ajustar_score_por_evidencia(85.0, None, None) == 85.0

    def test_confianza_malformada_no_rompe(self):
        assert _ajustar_score_por_evidencia(85.0, {"issues": None}, {"score": "n/a"}) == 85.0


# ─── P1-5: clasificador de familias tolerante ────────────────────────────


class TestClasificadorFamiliasTextoLibre:
    @pytest.fixture
    def svc(self):
        return GlosaService.__new__(GlosaService)

    @pytest.mark.parametrize(
        "texto,familia",
        [
            # Los 6 casos reales del 10-jun-2026 que caían a FA genérico:
            (
                "Se reconocen únicamente 8 días de UCI. Los días restantes se consideran injustificados.",
                "CL_PERTINENCIA",
            ),
            (
                "Reingreso dentro de los 15 días atribuible a manejo deficiente de la IPS.",
                "CL_PERTINENCIA",
            ),
            (
                "No existe relación clínica entre diagnóstico registrado y procedimiento facturado.",
                "CL_PERTINENCIA",
            ),
            (
                "No existe evidencia de realización del procedimiento.",
                "SO_SOPORTES",
            ),
            (
                "Tornillos y placas no soportados contractualmente.",
                "IN_INSUMOS",
            ),
            (
                "No se reconocen dispositivos utilizados las últimas 24 horas antes del fallecimiento.",
                "CL_PERTINENCIA",
            ),
            # "Medicamento fuera del PBS" → módulo ME (trae la defensa
            # correcta: prescripción del tratante + no-PBS→ADRES + FF.MM.)
            (
                "Medicamento fuera del PBS. No procede reconocimiento.",
                "ME_MEDICAMENTOS",
            ),
        ],
    )
    def test_casos_reales_clasifican_bien(self, svc, texto, familia):
        assert svc._determinar_tipo_glosa("XX", texto) == familia

    def test_prefijo_explicito_sigue_mandando(self, svc):
        # Con código, el prefijo manda — los stems no interfieren.
        assert svc._determinar_tipo_glosa("TA", "lo que sea") == "TA_TARIFA"
        assert svc._determinar_tipo_glosa("SO", "tornillos y placas") == "SO_SOPORTES"


# ─── P2-6: dedup de oraciones largas repetidas ───────────────────────────


class TestDedupOracionesLargas:
    CLAUSULA = (
        "CONFORME A LA CLÁUSULA PRIMERA DEL CONTRATO QUE ESTABLECE: «LA "
        "PRESTACIÓN DE LOS SERVICIOS DE SALUD DE MEDIANA Y ALTA COMPLEJIDAD, "
        "GARANTIZANDO LA COBERTURA INTEGRAL DE LAS ATENCIONES INCLUIDAS EN EL "
        "PLAN DE COMPLEJIDAD DE LOS SERVICIOS DE SANIDAD MILITAR Y POLICIAL»."
    )

    def test_clausula_repetida_se_elimina(self):
        # Caso real 7: la misma cláusula completa DOS veces en un párrafo.
        texto = (
            "ESE HUS NO ACEPTA LA GLOSA APLICADA POR CONCEPTO DE FACTURACIÓN "
            "SOBRE EL PROCEDIMIENTO FACTURADO POR LAS SIGUIENTES RAZONES. "
            + self.CLAUSULA
            + " EN VIRTUD DE LO ANTERIOR Y "
            + self.CLAUSULA
            + " SE SOLICITA RESPETUOSAMENTE EL LEVANTAMIENTO DE LA GLOSA."
        )
        out = _dedup_oraciones_largas(texto)
        assert out.count("MEDIANA Y ALTA COMPLEJIDAD") == 1

    def test_frases_cortas_rituales_se_conservan(self):
        texto = (
            "SE SOLICITA EL LEVANTAMIENTO. "
            * 3
            + "ARGUMENTO LARGO QUE NO SE REPITE EN NINGUNA PARTE DEL DICTAMEN "
            "GENERADO PARA ESTA GLOSA DE PRUEBA CON SUFICIENTES PALABRAS PARA "
            "PASAR EL UMBRAL DE QUINCE."
        )
        out = _dedup_oraciones_largas(texto)
        # Las cortas (<15 palabras) no se tocan
        assert out.count("SE SOLICITA EL LEVANTAMIENTO") == 3

    def test_texto_corto_intacto(self):
        assert _dedup_oraciones_largas("corto.") == "corto."


# ─── P0-3: prompt AU condicionado ────────────────────────────────────────


class TestPromptAUCondicionado:
    def test_au_ya_no_asume_urgencias(self):
        from app.services.glosa_ia_prompts import SYSTEM_AU

        # Debe existir la rama electiva y la prohibición explícita de
        # inventar el supuesto fáctico de urgencias.
        assert "SILENCIO ADMINISTRATIVO POSITIVO" in SYSTEM_AU
        assert "NO LO INVENTES" in SYSTEM_AU
        assert "NUNCA describas el servicio como" in SYSTEM_AU
        # La defensa de urgencias sigue disponible para el caso (A)
        assert "Art. 168 Ley 100/1993" in SYSTEM_AU
