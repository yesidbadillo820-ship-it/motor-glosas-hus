"""Ronda 28 (3-jul-2026) — fixes de la auditoría integral ultracode
(64 agentes, 55 hallazgos confirmados). Regresión de los fixes seguros."""

from __future__ import annotations

import re


# ─── AURORA: tarifa real del contrato (PROPIAS + SOAT −3%) ───────────


def test_aurora_factor_y_tarifa_del_contrato_firmado():
    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("AURORA")
    assert ficha["factor"] == 0.97, "el catálogo volvió a SOAT pleno"
    assert "PROPIAS" in ficha["tarifa"] and "3%" in ficha["tarifa"]
    assert "GID-ARL-0090" in ficha["numero"]


# ─── POLICÍA: la entrada de oncología ya es alcanzable ───────────────


def test_policia_oncologia_resuelve_su_contrato():
    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("POLICIA NACIONAL ONCOLOGIA")
    assert "068-5-200006-26" in ficha["numero"]


def test_policia_oncologia_con_razon_social_larga():
    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("DIRECCION DE SANIDAD POLICIA NACIONAL - SERVICIO ONCOLOGIA")
    assert "068-5-200006-26" in ficha["numero"]


def test_policia_mediana_alta_no_regresa():
    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("POLICIA NACIONAL")
    assert "068-5-200004-26" in ficha["numero"]


def test_match_generico_no_regresa():
    """COMPENSAR sigue resolviendo a SU contrato, no a uno ajeno.

    Cambió el cómo: ahora se resuelve por la FECHA DEL HECHO. El contrato
    CSS009-2024 rigió del 4-abr-2025 al 3-abr-2026 según la malla oficial, así
    que se comprueba dentro de ese rango.
    """
    import datetime as dt

    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("COMPENSAR", dt.date(2025, 9, 15))
    assert "CSS009-2024" in ficha["numero"]


def test_compensar_sin_contrato_despues_de_abril_2026():
    """Y después de que venció, el sistema lo dice en vez de inventarlo.

    Antes devolvía siempre la misma ficha con factor 0,90 —que además no
    coincidía con el 0,85 de la malla—. Ahora, sin contrato vigente, se
    defiende a tarifa SOAT plena, que es lo que corresponde jurídicamente y
    además es más favorable al hospital que el descuento pactado.
    """
    import datetime as dt

    from app.services.glosa_ia_prompts import get_contrato

    ficha = get_contrato("COMPENSAR", dt.date(2026, 7, 29))
    assert ficha["numero"] == "SIN CONTRATO PACTADO"
    assert ficha["factor"] == 1.00
    assert "no había contrato vigente" in ficha["nota"]
    # Y dice cuál existió, para que el auditor sepa qué pasó.
    assert "CSS009-2024" in ficha["nota"]
    assert get_contrato("EPS")["numero"] == "SIN CONTRATO PACTADO"


# ─── Auto-pilot: extemporánea nunca se auto-envía ────────────────────


def test_extemporanea_no_auto_envia():
    from app.services.auto_pilot_decision import decidir_auto_envio

    d = decidir_auto_envio(
        confianza_score=0.99,
        valor_objetado_raw="$100.000",
        texto_glosa="GLOSA TA0201 SIMPLE",
        es_extemporanea=True,
    )
    assert d["auto_enviable"] is False
    assert any("EXTEMPOR" in r.upper() for r in d["razones_contra_envio_auto"])


# ─── Validador: alineado con el prompt adaptativo ────────────────────


def test_extension_acepta_dictamen_simple_de_150_palabras():
    from app.services.validador_dictamen import check_extension

    texto = " ".join(["palabra"] * 150)
    assert check_extension(texto)["aprobado"] is True


def test_enumeracion_exenta_para_dictamen_simple():
    from app.services.validador_dictamen import check_enumeracion

    corto = " ".join(["palabra"] * 150)  # simple: enumeración PROHIBIDA
    assert check_enumeracion(corto)["aprobado"] is True
    largo = " ".join(["palabra"] * 300)  # complejo: sí se exige
    assert check_enumeracion(largo)["aprobado"] is False


# ─── Seguridad: .env.example sin secretos reales ─────────────────────


def test_env_example_solo_placeholders():
    contenido = open(".env.example", encoding="utf-8").read()
    patrones_de_key_real = [
        r"AQ\.[A-Za-z0-9_\-]{20,}",  # Google/Gemini
        r"AIza[A-Za-z0-9_\-]{30,}",  # Google clásica
        r"sk-ant-[A-Za-z0-9_\-]{20,}",  # Anthropic
        r"gsk_[A-Za-z0-9]{20,}",  # Groq
    ]
    for pat in patrones_de_key_real:
        assert not re.search(pat, contenido), f"posible key real en .env.example: {pat}"


# ─── PRECIMED fuera de las listas de detección ───────────────────────


def test_precimed_ya_no_se_detecta_como_pagador():
    for archivo in (
        "app/services/extractor_factura.py",
        "app/services/quality_gate/pre_validator.py",
        "app/api/routers/analizar.py",
    ):
        assert '"PRECIMED"' not in open(archivo, encoding="utf-8").read(), archivo
