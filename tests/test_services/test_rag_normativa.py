"""Tests del RAG de normativa (Ronda 7)."""
from app.services.rag_normativa import buscar_normas, validar_citas_en_dictamen


def test_buscar_normas_tarifa_soat_retorna_resultados():
    r = buscar_normas("tarifa soat diferencia contrato", top_k=5)
    assert len(r) > 0
    # Alguna de las primeras debería mencionar SOAT o tarifa
    primeros = " ".join(x["nombre"] + " " + x.get("titulo", "") for x in r[:3]).upper()
    assert "SOAT" in primeros or "TARIFA" in primeros or "PROPIA" in primeros


def test_buscar_normas_urgencia():
    r = buscar_normas("urgencias autorizacion sin autorizar", top_k=3)
    # Algún resultado debe estar relacionado con urgencias o Ley 100
    assert len(r) >= 1


def test_buscar_normas_query_vacia():
    assert buscar_normas("") == []
    assert buscar_normas("   ") == []


def test_validar_citas_detecta_formatos_comunes():
    texto = (
        "De conformidad con el Art. 871 del Código de Comercio, "
        "la Ley 1438 de 2011 establece el plazo, y la Resolución 2284 de 2023 "
        "contiene el Manual Único. La Sentencia T-760/2008 aplica al SGSSS."
    )
    r = validar_citas_en_dictamen(texto)
    assert r["total"] >= 3
    nombres = " ".join(r["citas_detectadas"])
    assert "1438" in nombres or "2284" in nombres


def test_validar_citas_sin_texto():
    r = validar_citas_en_dictamen("")
    assert r["total"] == 0
    r = validar_citas_en_dictamen(None)
    assert r["total"] == 0


def test_validar_citas_detecta_alucinacion():
    """Cita inventada 'Res. 9999/2099' debería estar en no_verificadas."""
    texto = "De conformidad con la Resolución 9999 de 2099 y la Ley 1438 de 2011..."
    r = validar_citas_en_dictamen(texto)
    # 9999/2099 debe caer en no_verificadas
    no_verif = " ".join(r["no_verificadas"])
    assert "9999" in no_verif


# ─── Ronda 50 Paso 5: sinónimos y citas literales ───────────────────────

from app.services.rag_normativa import (
    _expandir_con_sinonimos,
    _extraer_citas_literales,
)


def test_expandir_sinonimos_dominio():
    """'plazo' debe traer 'termino' como sinónimo."""
    exp = _expandir_con_sinonimos(["plazo"])
    assert "termino" in exp
    assert "plazo" in exp  # el original se conserva


def test_expandir_no_duplica_si_ya_estaba():
    exp = _expandir_con_sinonimos(["plazo", "termino"])
    # 'termino' sinónimo de 'plazo' ya presente — no se duplica
    assert exp.count("termino") == 1


def test_expandir_multiples_tokens():
    exp = _expandir_con_sinonimos(["ips", "glosa"])
    assert "prestador" in exp
    assert "objecion" in exp


def test_extraer_citas_literales_art_ley():
    citas = _extraer_citas_literales("¿qué dice el Art. 57 de la Ley 1438 de 2011?")
    assert len(citas) >= 2
    assert any("57" in c for c in citas)
    assert any("1438" in c for c in citas)


def test_extraer_citas_resolucion():
    citas = _extraer_citas_literales("según Resolución 2284 de 2023...")
    assert any("2284" in c for c in citas)


def test_extraer_citas_sentencia():
    citas = _extraer_citas_literales("en Sentencia T-760 de 2008")
    assert any("760" in c for c in citas)


def test_buscar_con_sinonimo_encuentra_norma():
    """Buscar 'prestador' debería encontrar normas que hablan de IPS."""
    from app.services.rag_normativa import buscar_normas
    r = buscar_normas("obligaciones del prestador de servicios", top_k=5)
    # Con sinónimos 'prestador' → 'ips' debe matchear normas que mencionan IPS
    assert len(r) > 0


def test_buscar_boost_cita_literal():
    """Si el query menciona 'Ley 1438', esa norma sube en el ranking."""
    from app.services.rag_normativa import buscar_normas
    r = buscar_normas("plazo Ley 1438 Art. 57", top_k=3)
    assert len(r) >= 1
    # La primera debería ser Ley 1438 (por boost ×2)
    assert "1438" in r[0]["clave"]
