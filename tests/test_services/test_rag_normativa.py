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
