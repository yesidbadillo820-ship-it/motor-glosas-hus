"""Ronda 26 (2-jul-2026) — hallazgos de la prueba de producción con HC
ficticia (casos COMPENSAR artroplastia y AURORA tibia).

6 hallazgos reales:
  1. Opus 404 (key sin acceso) reventaba la cadena → el caso de $20.2M
     terminó en Groq/Llama. Ahora degrada Opus→Sonnet (texto y multimodal).
  2. "ADICIONALMENTE SE GLOSA" no partía sub-conceptos (solo "SE OBJETA")
     → la prótesis de $3.9M quedó sin respuesta.
  3. _extraer_valor tomaba el PRIMER '$' (el facturado $20.2M) en vez del
     "VALOR OBJETADO: $6.4M" etiquetado.
  4. "código CUPS 27535" alucinado (no existe en ningún dato del caso).
  5. Cita que arranca con "Conforme al..." recibía el conector "en los
     términos de" → "en los términos de conforme al" (roto).
  6. Cláusula AURORA Octava num. 3 con tema FA no se inyectaba en glosas
     AU → retag a NN + seed retag-aware.
"""

from __future__ import annotations

import json


TEXTO_C1 = (
    "COMPENSAR EPS — GLOSA TA0201 MAYOR VALOR. FACTURA FE-HUS-118432. "
    "CUPS 815103 REEMPLAZO PROTÉSICO TOTAL PRIMARIO SIMPLE DE CADERA. "
    "VALOR FACTURADO: $20.200.092. VALOR OBJETADO: $6.434.900. "
    "OBSERVACIÓN: SE EVIDENCIA MAYOR VALOR COBRADO: LA IPS FACTURA "
    "$7.860.092 CUANDO CORRESPONDE SOAT 2025 MENOS 20% ($5.345.192), SE "
    "GLOSA LA DIFERENCIA DE $2.514.900. ADICIONALMENTE SE GLOSA LA "
    "PRÓTESIS TOTAL DE CADERA POR VALOR DE $3.920.000 POR ENCONTRARSE "
    "INCLUIDA EN EL PAQUETE QUIRÚRGICO."
).upper()


# ─── 3. Valor objetado etiquetado tiene prioridad ────────────────────


def test_extraer_valor_prioriza_objetado_etiquetado():
    from app.services.glosa_service import GlosaService

    gs = GlosaService.__new__(GlosaService)
    assert gs._extraer_valor(TEXTO_C1) == "$ 6.434.900"


def test_extraer_valor_sin_etiqueta_sigue_tomando_primero():
    from app.services.glosa_service import GlosaService

    gs = GlosaService.__new__(GlosaService)
    assert gs._extraer_valor("SE GLOSA LA FACTURA POR $1.500.000 TOTAL") == "$ 1.500.000"


# ─── 2. Sub-conceptos en prosa ("ADICIONALMENTE SE GLOSA") ───────────


def test_adicionalmente_se_glosa_parte_el_caso():
    from app.services.subconceptos_glosa import detectar_subconceptos

    res = detectar_subconceptos(TEXTO_C1)
    assert res and len(res) >= 2, (
        "El 'ADICIONALMENTE SE GLOSA' (prótesis $3.9M) debe generar un "
        f"segundo sub-concepto — detectados: {res}"
    )


# ─── 4. CUPS fantasma en el argumento ────────────────────────────────


def test_cups_fantasma_detectado():
    from app.services.validador_dictamen import detectar_defectos_criticos

    xml = (
        "<paciente>X</paciente><servicio>Y</servicio>"
        "<argumento>ESE HUS NO ACEPTA LA GLOSA. EL SERVICIO CORRESPONDE AL "
        "CÓDIGO CUPS 27535 DERIVADO DE ACCIDENTE DE TRABAJO. SE SOLICITA "
        "EL LEVANTAMIENTO.</argumento>"
    )
    defectos = detectar_defectos_criticos(
        xml, codigo_glosa="AU0101", texto_glosa="GLOSA AU0101 CUPS 793713 FACTURA FE-119206"
    )
    assert any(d["regla"] == "cups_fantasma" for d in defectos)


def test_cups_legitimo_no_se_marca():
    from app.services.validador_dictamen import detectar_defectos_criticos

    xml = (
        "<paciente>X</paciente><servicio>Y</servicio>"
        "<argumento>ESE HUS NO ACEPTA LA GLOSA SOBRE EL CUPS 793713, "
        "HOMOLOGADO AL CÓDIGO SOAT 13570 DEL MANUAL TARIFARIO. SE SOLICITA "
        "EL LEVANTAMIENTO.</argumento>"
    )
    defectos = detectar_defectos_criticos(
        xml, codigo_glosa="AU0101", texto_glosa="GLOSA AU0101 CUPS 793713 FACTURA FE-119206"
    )
    # 793713 está en la glosa ✓; "SOAT 13570" no está rotulado CUPS ✓
    assert not any(d["regla"] == "cups_fantasma" for d in defectos)


# ─── 1. Opus no disponible degrada a Sonnet (multimodal) ─────────────


async def test_multimodal_opus_404_degrada_a_sonnet(monkeypatch):
    from app.services.glosa_service import GlosaService

    llamadas = []

    class _FakeResp:
        def __init__(self, status, payload, text=""):
            self.status_code = status
            self._payload = payload
            self.text = text

        def json(self):
            return self._payload

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            llamadas.append(json["model"])
            if json["model"].startswith("claude-opus"):
                return _FakeResp(
                    404,
                    {"error": {"message": "model not found"}},
                    text='{"type":"not_found_error"}',
                )
            return _FakeResp(
                200,
                {"content": [{"type": "text", "text": "<argumento>OK</argumento>"}], "usage": {}},
            )

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)

    gs = GlosaService.__new__(GlosaService)
    gs.anthropic_key = "sk-test"
    gs.anthropic_model = "claude-sonnet-4-5"

    # llamar al método ORIGINAL (sin el monkey-patch de Gemini)
    texto, etiqueta = await GlosaService._llamar_anthropic_multimodal(
        gs,
        "system",
        "user",
        [("hc.pdf", b"x" * 2048)],
        modelo_override="claude-opus-4-7",
    )
    assert texto == "<argumento>OK</argumento>"
    assert llamadas == ["claude-opus-4-7", "claude-sonnet-4-5"], llamadas
    assert "claude-sonnet-4-5" in etiqueta


# ─── 5. Cita que arranca con "Conforme" no recibe conector ───────────


def test_descomillar_no_produce_en_los_terminos_de_conforme():
    """Regresión del dictamen COMPENSAR: 'establece: en los términos de
    conforme al Acuerdo...'. La cita que ya trae conector propio ('Conforme
    a...') queda tal cual, sin el prefijo redundante."""
    from app.services.glosa_service import _descomillar_citas_falsas

    cita = "Conforme al Acuerdo Tarifario 2025, los servicios se liquidan a SOAT menos diez"
    texto = f"EL CONTRATO ESTABLECE: «{cita}»"
    issues = [{"tipo": "CITA_LITERAL_FALSA", "cita": f"«{cita}»"}]
    salida = _descomillar_citas_falsas(texto, issues)
    assert "en los términos de conforme" not in salida.lower()
    assert "Conforme al Acuerdo Tarifario 2025" in salida  # la cita queda, sin comillas ni conector


# ─── 6. Retag de la cláusula AURORA + seed retag-aware ───────────────


def test_clausula_aurora_octava_num3_es_comodin():
    with open("data/clausulas_contrato_base.json", encoding="utf-8") as f:
        data = json.load(f)
    octava3 = [
        c
        for c in data["clausulas"]
        if c["eps"].startswith("SEGUROS DE VIDA AURORA") and "numeral 3" in c["numero_clausula"]
    ]
    assert octava3 and octava3[0]["tema"] == "NN", (
        "La cláusula 'no exonera de pagar' debe ser NN (comodín) para "
        "inyectarse también en glosas AU"
    )


def test_seed_retag_actualiza_en_vez_de_duplicar(tmp_path, monkeypatch):
    """El seed con clave (eps, numero_clausula) actualiza el tema en vez de
    crear una fila duplicada."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models.db import ClausulaContrato

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    s.add(
        ClausulaContrato(
            eps="SEGUROS DE VIDA AURORA S.A.",
            numero_clausula="Octava, numeral 3",
            tema="FA",
            titulo="viejo",
            texto_literal="El no cumplimiento de los plazos no exonera a AURORA S.A.",
        )
    )
    s.commit()

    # Simular la lógica del seed (misma clave nueva)
    c = {
        "eps": "SEGUROS DE VIDA AURORA S.A.",
        "numero_clausula": "Octava, numeral 3",
        "tema": "NN",
        "titulo": "nuevo",
        "texto_literal": "El no cumplimiento de los plazos no exonera a AURORA S.A.",
        "pagina": 7,
    }
    existente = (
        s.query(ClausulaContrato)
        .filter(ClausulaContrato.eps == c["eps"])
        .filter(ClausulaContrato.numero_clausula == c["numero_clausula"])
        .first()
    )
    assert existente is not None
    existente.tema = c["tema"]
    s.commit()

    filas = (
        s.query(ClausulaContrato)
        .filter(ClausulaContrato.numero_clausula == "Octava, numeral 3")
        .all()
    )
    assert len(filas) == 1 and filas[0].tema == "NN"
    s.close()


# ─── El caso completo: glosa AU de AURORA ahora recibe la Octava 3 ───


def test_glosa_au_aurora_inyecta_clausula_no_exonera(monkeypatch):
    """Con el retag NN, get_clausulas_para_glosa('AURORA','AU0101') debe
    devolver la cláusula 'no exonera de pagar'."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    import app.database as database
    from app.database import Base
    from app.models.db import ClausulaContrato

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "SessionLocal", Session)

    s = Session()
    s.add(
        ClausulaContrato(
            eps="SEGUROS DE VIDA AURORA S.A.",
            numero_clausula="Octava, numeral 3",
            tema="NN",
            titulo="No exonera de pago",
            texto_literal=(
                "El no cumplimiento de los plazos estipulados en la presente "
                "cláusula no exonera a AURORA S.A. de cancelar los servicios "
                "efectivamente prestados."
            ),
        )
    )
    s.commit()
    s.close()

    from app.services.glosa_ia_prompts import get_clausulas_para_glosa

    cls = get_clausulas_para_glosa("AURORA", "AU0101")
    assert any("no exonera a AURORA" in c["texto_literal"] for c in cls)
