"""Tests del divisor de dictámenes multi-código (dictamen_secciones).

Fixtures calcados del formato REAL que producen glosa_service
(_generar_dictamen_html: tabla CÓDIGO GLOSA/VALOR OBJETADO/CÓDIGO
RESPUESTA + bloque ARGUMENTACIÓN JURÍDICA + nota IA) y multi_codigo
(construir_encabezado_html + _wrap_seccion_html con el título
«═══ RESPUESTA AL CÓDIGO XXNNNN — FAMILIA ═══»). Origen: filas
duplicadas en el Excel radicable del 12-jun-2026.

Datos 100 % ficticios (FAC-TEST-*, argumentos de prueba).
"""

from app.services.dictamen_secciones import (
    extraer_codigo_principal_del_dictamen,
    extraer_seccion_por_codigo,
    indice_codigos_del_dictamen,
)
from app.utils.html_a_texto import dictamen_a_texto_plano

# ─── Fixtures: dictamen multi-código realista (TA0201 + SO0601 + AU0301) ─────

ENCABEZADO_MULTI = (
    '<div style="background:#eef2ff;border:2px solid #6366f1;border-radius:8px;'
    'padding:10px 14px;margin-bottom:12px;font-size:12px;color:#312e81;">'
    "<b>CÓDIGOS GLOSA: TA0201, SO0601, AU0301</b> — La glosa agrupa varios códigos; "
    "este documento contiene una respuesta por cada código.</div>"
)

TABLA_CABECERA = (
    '<table border="1" style="width:100%;border-collapse:collapse;font-size:11px;">'
    '<tr style="background-color:#1e40af;color:white;">'
    '<th style="padding:10px;text-align:center;">CÓDIGO GLOSA</th>'
    '<th style="padding:10px;text-align:center;">VALOR OBJETADO</th>'
    '<th style="padding:10px;text-align:center;">CÓDIGO RESPUESTA</th></tr>'
    '<tr><td style="padding:10px;text-align:center;font-weight:bold;">TA0201</td>'
    '<td style="padding:10px;text-align:center;font-weight:bold;color:#1e40af;">$120.000</td>'
    '<td style="padding:10px;text-align:center;"><b>RE9901</b><br>'
    '<span style="font-size:10px">Defensa de tarifas</span></td></tr></table>'
)

CUERPO_PRINCIPAL = (
    '<div style="background:#f8fafc;border-radius:12px;padding:20px;">'
    '<h4 style="color:#0f172a;">ARGUMENTACIÓN JURÍDICA</h4>'
    '<div style="font-size:12px;">LAS TARIFAS FACTURADAS CORRESPONDEN AL ANEXO '
    "TARIFARIO PACTADO. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA TA0201.</div></div>"
    '<div style="margin-top:15px;padding:12px;background:#fef2f2;">'
    "<b>Nota:</b> Generado con asistencia de IA. Verificar antes de radicar ante la EPS.</div>"
)

SECCION_SO = (
    '<div style="margin:18px 0 6px 0;text-align:center;font-weight:700;color:#7c3aed;">'
    "═══ RESPUESTA AL CÓDIGO SO0601 — SOPORTES ═══</div>"
    '<div style="background:#f8fafc;border-radius:12px;padding:20px;">'
    '<h4 style="color:#0f172a;">ARGUMENTACIÓN JURÍDICA — CÓDIGO SO0601</h4>'
    '<div style="font-size:12px;">LOS SOPORTES DOCUMENTALES FUERON RADICADOS CON LA '
    "FACTURA FAC-TEST-001. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA SO0601.</div></div>"
)

SECCION_AU = (
    '<div style="margin:18px 0 6px 0;text-align:center;font-weight:700;color:#059669;">'
    "═══ RESPUESTA AL CÓDIGO AU0301 — AUTORIZACIÓN ═══</div>"
    '<div style="background:#f8fafc;border-radius:12px;padding:20px;">'
    '<h4 style="color:#0f172a;">ARGUMENTACIÓN JURÍDICA — CÓDIGO AU0301</h4>'
    '<div style="font-size:12px;">LA ATENCIÓN CONTÓ CON AUTORIZACIÓN EMITIDA POR LA '
    "PROPIA ENTIDAD. SE SOLICITA EL LEVANTAMIENTO DE LA GLOSA AU0301.</div></div>"
)

DICTAMEN_MULTI = ENCABEZADO_MULTI + TABLA_CABECERA + CUERPO_PRINCIPAL + SECCION_SO + SECCION_AU

DICTAMEN_SIMPLE = TABLA_CABECERA + CUERPO_PRINCIPAL  # un solo código, sin separadores

# Pie que el render radicable (static/index.html) anexa al final del doc.
PIE_FIRMA = (
    '<div class="doc-firma-cargo">Área de Cartera · Glosas y Devoluciones — ESE HUS</div>'
    '<div class="doc-sello-txt">Generado por IA con Quality Gate<br/>SINAC SC SAS</div>'
)


# ─── extraer_codigo_principal_del_dictamen ───────────────────────────────────


def test_codigo_principal_desde_tabla_html():
    assert extraer_codigo_principal_del_dictamen(DICTAMEN_MULTI) == "TA0201"
    assert extraer_codigo_principal_del_dictamen(DICTAMEN_SIMPLE) == "TA0201"


def test_codigo_principal_desde_texto_plano():
    # Forma exacta que produce dictamen_a_texto_plano para la cabecera.
    texto = "CÓDIGO GLOSA: TA0801 | VALOR OBJETADO: $36.402 | CÓDIGO RESPUESTA: RE9901"
    assert extraer_codigo_principal_del_dictamen(texto) == "TA0801"
    # Y sobre la conversión real del dictamen completo.
    assert extraer_codigo_principal_del_dictamen(dictamen_a_texto_plano(DICTAMEN_MULTI)) == "TA0201"


def test_codigo_principal_sin_tabla_o_vacio():
    assert extraer_codigo_principal_del_dictamen("<p>Texto fijo simple sin tabla.</p>") is None
    assert extraer_codigo_principal_del_dictamen("") is None
    assert extraer_codigo_principal_del_dictamen("   ") is None


def test_codigo_principal_no_confunde_encabezado_plural():
    # El «CÓDIGOS GLOSA: …» (plural) del encabezado multi-código no debe
    # tomarse como tabla de cabecera si esta no existe.
    assert extraer_codigo_principal_del_dictamen(ENCABEZADO_MULTI) is None


# ─── extraer_seccion_por_codigo: dictamen SIN separadores ────────────────────


def test_sin_separadores_codigo_principal_devuelve_todo():
    seccion = extraer_seccion_por_codigo(
        DICTAMEN_SIMPLE, codigo_concepto="TA0201", codigo_principal="TA0201"
    )
    assert seccion == DICTAMEN_SIMPLE


def test_sin_separadores_codigo_distinto_devuelve_none():
    # Caso típico del bug: la glosa solo se analizó para TA0201 y el
    # concepto es de otra familia → el caller pone el texto neutro.
    assert (
        extraer_seccion_por_codigo(
            DICTAMEN_SIMPLE, codigo_concepto="CO0701", codigo_principal="TA0201"
        )
        is None
    )
    # También cuando el principal se deduce de la tabla (sin argumento).
    assert extraer_seccion_por_codigo(DICTAMEN_SIMPLE, codigo_concepto="CO0701") is None


# ─── extraer_seccion_por_codigo: dictamen multi-código de 3 secciones ────────


def test_multi_codigo_cada_codigo_recibe_su_seccion():
    principal = extraer_seccion_por_codigo(DICTAMEN_MULTI, "TA0201", codigo_principal="TA0201")
    so = extraer_seccion_por_codigo(DICTAMEN_MULTI, "SO0601", codigo_principal="TA0201")
    au = extraer_seccion_por_codigo(DICTAMEN_MULTI, "AU0301", codigo_principal="TA0201")

    # Principal: todo lo de arriba del primer separador (encabezado del
    # documento + tabla + argumentación + nota IA), sin las adicionales.
    assert "CÓDIGOS GLOSA: TA0201, SO0601, AU0301" in principal
    assert "LAS TARIFAS FACTURADAS" in principal
    assert "Generado con asistencia de IA" in principal
    assert "RESPUESTA AL CÓDIGO SO0601" not in principal
    assert "LOS SOPORTES DOCUMENTALES" not in principal

    # SO0601: solo su bloque, delimitado por el separador de AU0301.
    assert so.startswith("═══ RESPUESTA AL CÓDIGO SO0601")
    assert "LOS SOPORTES DOCUMENTALES" in so
    assert "LAS TARIFAS FACTURADAS" not in so
    assert "AU0301" not in so

    # AU0301: última sección, hasta el final del documento.
    assert au.startswith("═══ RESPUESTA AL CÓDIGO AU0301")
    assert "LA ATENCIÓN CONTÓ CON AUTORIZACIÓN" in au
    assert "LOS SOPORTES DOCUMENTALES" not in au

    # Tres respuestas distintas — el bug eran filas idénticas.
    assert len({principal, so, au}) == 3


def test_multi_codigo_sobre_texto_plano_real():
    # La columna del Excel pasa por dictamen_a_texto_plano: el divisor debe
    # funcionar igual sobre esa versión texto del MISMO dictamen.
    texto = dictamen_a_texto_plano(DICTAMEN_MULTI)
    so = extraer_seccion_por_codigo(texto, "SO0601", codigo_principal="TA0201")
    au = extraer_seccion_por_codigo(texto, "AU0301", codigo_principal="TA0201")
    principal = extraer_seccion_por_codigo(texto, "TA0201", codigo_principal="TA0201")
    assert "LOS SOPORTES DOCUMENTALES" in so and "LAS TARIFAS" not in so
    assert "AUTORIZACIÓN EMITIDA" in au and "SOPORTES DOCUMENTALES" not in au
    assert "LAS TARIFAS FACTURADAS" in principal and "SO0601 — SOPORTES" not in principal


def test_codigo_ausente_en_multi_codigo_devuelve_none():
    assert extraer_seccion_por_codigo(DICTAMEN_MULTI, "CO0701", codigo_principal="TA0201") is None


def test_principal_deducido_de_la_tabla_sin_argumento():
    # Sin codigo_principal explícito, la tabla de cabecera basta.
    principal = extraer_seccion_por_codigo(DICTAMEN_MULTI, "TA0201")
    assert principal is not None
    assert "LAS TARIFAS FACTURADAS" in principal
    assert "RESPUESTA AL CÓDIGO SO0601" not in principal


def test_dictamen_vacio_o_codigo_vacio():
    assert extraer_seccion_por_codigo("", "TA0201") is None
    assert extraer_seccion_por_codigo(DICTAMEN_MULTI, "") is None
    assert extraer_seccion_por_codigo(None, "TA0201") is None


# ─── Tolerancia a variantes del separador ────────────────────────────────────


def test_variantes_del_separador():
    casos = [
        # espacios extra alrededor de los ═══ y dentro del título
        "═══   RESPUESTA AL CÓDIGO   SO0601   —   SOPORTES   ═══",
        # minúsculas
        "═══ respuesta al código so0601 — soportes ═══",
        # código con espacio interno
        "═══ RESPUESTA AL CÓDIGO SO 0601 — SOPORTES ═══",
        # familia sin guion
        "═══ RESPUESTA AL CÓDIGO SO0601 SOPORTES ═══",
        # sin familia
        "═══ RESPUESTA AL CÓDIGO SO0601 ═══",
        # sin acento en CÓDIGO y guion ASCII en la familia
        "═══ RESPUESTA AL CODIGO SO0601 - SOPORTES ═══",
    ]
    for titulo in casos:
        dictamen = (
            "CÓDIGO GLOSA: TA0201 | VALOR OBJETADO: $120.000\n"
            "ARGUMENTACIÓN JURÍDICA\nDEFENSA DE TARIFAS.\n"
            f"{titulo}\nDEFENSA DE SOPORTES."
        )
        so = extraer_seccion_por_codigo(dictamen, "SO0601", codigo_principal="TA0201")
        assert so is not None, f"separador no detectado: {titulo!r}"
        assert "DEFENSA DE SOPORTES." in so
        assert "DEFENSA DE TARIFAS." not in so
        principal = extraer_seccion_por_codigo(dictamen, "TA0201", codigo_principal="TA0201")
        assert "DEFENSA DE TARIFAS." in principal
        assert "DEFENSA DE SOPORTES." not in principal


def test_codigo_concepto_tolera_espacios_y_minusculas():
    so = extraer_seccion_por_codigo(DICTAMEN_MULTI, "so 0601", codigo_principal="TA0201")
    assert so is not None and "LOS SOPORTES DOCUMENTALES" in so


# ─── Pie de firma / sello QG ─────────────────────────────────────────────────


def test_pie_de_firma_no_se_duplica_en_secciones_secundarias():
    con_pie = DICTAMEN_MULTI + PIE_FIRMA
    so = extraer_seccion_por_codigo(con_pie, "SO0601", codigo_principal="TA0201")
    au = extraer_seccion_por_codigo(con_pie, "AU0301", codigo_principal="TA0201")
    # La sección intermedia termina en el siguiente separador y la última
    # se corta en el pie: ninguna arrastra la firma/sello del documento.
    for seccion in (so, au):
        assert "Área de Cartera" not in seccion
        assert "Quality Gate" not in seccion
    assert "AUTORIZACIÓN EMITIDA" in au  # el corte no se come el contenido


# ─── indice_codigos_del_dictamen ─────────────────────────────────────────────


def test_indice_codigos_multi():
    assert indice_codigos_del_dictamen(DICTAMEN_MULTI) == ["TA0201", "SO0601", "AU0301"]
    assert indice_codigos_del_dictamen(dictamen_a_texto_plano(DICTAMEN_MULTI)) == [
        "TA0201",
        "SO0601",
        "AU0301",
    ]


def test_indice_codigos_simple_y_vacio():
    assert indice_codigos_del_dictamen(DICTAMEN_SIMPLE) == ["TA0201"]
    assert indice_codigos_del_dictamen("<p>Texto fijo sin códigos.</p>") == []
    assert indice_codigos_del_dictamen("") == []
