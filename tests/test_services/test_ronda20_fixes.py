"""Tests de regresión ronda 20 (30-jun-2026) — 4 bugs cosméticos detectados
al reanalizar SALUD TOTAL TMS con ronda 19 desplegada.

Ronda 19 resolvió lo de fondo (detectó SALUD TOTAL del texto, NO trajo
normas militares, rechazó la sanción del 10%, score 30→58). Pero quedaron
defectos de placeholders/cosmética:

  • EE — El banner "EPS corregida automáticamente" salió como "la entidad
    pagadora automáticamente": el sanitizer _sustituir_eps_inventada
    confundió "EPS corregida" con un nombre de EPS inventado. Fix: inyectar
    el banner AL FINAL (tras todos los sanitizers) + texto "Entidad
    pagadora corregida".
  • FF — Bug Y producía "según el contrato contrato CTR-2024" (palabra
    duplicada + truncado a 4 dígitos). El regex capturaba "contrato
    CTR-2024" incluyendo la palabra. Fix: capturar el código completo
    en un grupo, limpio.
  • GG — "el procedimiento facturado según historia clínica" persistía
    en medio del argumento y en el servicio (camino QG). Fix: patrones
    para limpiarlo en cualquier posición (medio, antes de "por valor",
    antes de cierre de tag).
  • HH — "aplicada por salud total la entidad pagadora el servicio":
    nombre EPS + "la entidad pagadora" duplicado sin preposición. Fix:
    reparar a "salud total, respecto del servicio".
"""

import inspect

from app.services.glosa_service import (
    _detectar_contrato_citado_en_glosa,
    _neutralizar_alucinaciones_prompt,
    _reescribir_negacion_contrato,
)


class TestBugEEBannerEPS:
    def test_banner_se_inyecta_al_final_tras_sanitizers(self):
        # El banner debe inyectarse justo antes de construir GlosaResult,
        # no antes de los sanitizers (donde _sustituir_eps_inventada lo rompía).
        import app.services.glosa_service as gs

        src = inspect.getsource(gs.GlosaService.analizar)
        idx_banner = src.find("Entidad pagadora corregida")
        idx_result = src.find("resultado = GlosaResult(")
        assert idx_banner > 0, "banner no encontrado"
        assert idx_result > 0
        # El banner debe estar ANTES de GlosaResult pero DESPUÉS del
        # ajuste de score (final del flujo).
        assert idx_banner < idx_result
        idx_score = src.find("_ajustar_score_por_evidencia")
        assert idx_score < idx_banner, "banner debe ir tras el ajuste de score"

    def test_banner_usa_entidad_pagadora_no_eps(self):
        # El texto del banner NO debe contener "EPS corregida" (que el
        # sanitizer rompía). Debe decir "Entidad pagadora corregida".
        import app.services.glosa_service as gs

        src = inspect.getsource(gs.GlosaService.analizar)
        assert "Entidad pagadora corregida" in src


class TestBugFFContratoDuplicado:
    def test_detecta_codigo_completo_no_truncado(self):
        glosa = "conforme a la Cláusula 18 del contrato CTR-2024-SALUDTOTAL-HUS"
        codigo = _detectar_contrato_citado_en_glosa(glosa)
        assert codigo == "CTR-2024-SALUDTOTAL-HUS"

    def test_no_incluye_palabra_contrato(self):
        glosa = "el contrato vigente CTR-2024-MEDIMAS-HUS define la tarifa"
        codigo = _detectar_contrato_citado_en_glosa(glosa)
        assert codigo is not None
        assert "CONTRATO" not in codigo.upper()
        assert codigo == "CTR-2024-MEDIMAS-HUS"

    def test_contrato_numerico(self):
        glosa = "según contrato N° 12345 vigente entre las partes"
        codigo = _detectar_contrato_citado_en_glosa(glosa)
        assert codigo == "12345"

    def test_contrato_militar_con_slash(self):
        glosa = "facturado conforme al contrato 440-DIGSA/DMBUG-2025"
        codigo = _detectar_contrato_citado_en_glosa(glosa)
        assert codigo == "440-DIGSA/DMBUG-2025"

    def test_reescritura_no_duplica_contrato(self):
        glosa = "Cláusula 18 del contrato CTR-2024-SALUDTOTAL-HUS"
        dictamen = "Contrato: SIN CONTRATO PACTADO. servicio prestado."
        resultado = _reescribir_negacion_contrato(dictamen, texto_glosa=glosa)
        # No debe haber "contrato contrato"
        assert "contrato contrato" not in resultado.lower()
        assert "CTR-2024-SALUDTOTAL-HUS" in resultado
        assert "según el contrato CTR-2024-SALUDTOTAL-HUS" in resultado


class TestBugGGPlaceholderEnArgumento:
    def test_placeholder_en_medio_con_comas(self):
        arg = (
            "el servicio de hospitalización psiquiátrica con tms, el "
            "procedimiento facturado según historia clínica, por valor objetado"
        )
        resultado = _neutralizar_alucinaciones_prompt(arg)
        assert "procedimiento facturado según historia clínica" not in resultado.lower()
        assert "hospitalización psiquiátrica con tms" in resultado.lower()
        assert "por valor objetado" in resultado.lower()

    def test_placeholder_antes_de_por_valor(self):
        arg = (
            "el tratamiento aplicado, el medicamento facturado según historia "
            "clínica por valor de cinco millones"
        )
        resultado = _neutralizar_alucinaciones_prompt(arg)
        assert "medicamento facturado según historia clínica" not in resultado.lower()

    def test_placeholder_en_servicio_antes_de_cierre_tag(self):
        serv = (
            "<div>HOSPITALIZACIÓN PSIQUIÁTRICA CON TMS, el procedimiento "
            "facturado según historia clínica</div>"
        )
        resultado = _neutralizar_alucinaciones_prompt(serv)
        assert "procedimiento facturado según historia clínica" not in resultado.lower()
        assert "HOSPITALIZACIÓN PSIQUIÁTRICA CON TMS" in resultado

    def test_placeholder_solo_no_se_rompe(self):
        # Si el placeholder es legítimo (reemplaza un CUPS, sin texto antes),
        # NO debe quedar texto roto. Aquí no hay coma antes, así que no aplica.
        arg = "respecto del procedimiento facturado según historia clínica se observa"
        resultado = _neutralizar_alucinaciones_prompt(arg)
        # No tiene coma antes → no se toca por los patrones GG
        assert "procedimiento facturado según historia clínica" in resultado.lower()


class TestBugHHEpsEntidadPagadora:
    def test_eps_entidad_pagadora_con_sustantivo(self):
        hh = "la sanción aplicada por salud total la entidad pagadora el servicio prestado"
        resultado = _neutralizar_alucinaciones_prompt(hh)
        assert "salud total la entidad pagadora" not in resultado.lower()
        assert "respecto del servicio" in resultado.lower()

    def test_eps_entidad_pagadora_sin_sustantivo(self):
        hh = "objetada por compensar la entidad pagadora en la factura"
        resultado = _neutralizar_alucinaciones_prompt(hh)
        assert "compensar la entidad pagadora" not in resultado.lower()
        assert "compensar" in resultado.lower()

    def test_sura_entidad_pagadora(self):
        hh = "la glosa de sura la entidad pagadora el procedimiento facturado"
        resultado = _neutralizar_alucinaciones_prompt(hh)
        assert "sura la entidad pagadora" not in resultado.lower()

    def test_entidad_pagadora_legitima_intacta(self):
        # "la entidad pagadora" sola (sin EPS antes) es legítima
        texto = "la entidad pagadora no tiene facultad sancionatoria"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "la entidad pagadora no tiene facultad" in resultado.lower()


class TestRegresionRondaAnteriores:
    def test_ronda19_eps_resolver_intacto(self):
        from app.services.glosa_ia_prompts import resolver_eps_efectiva

        glosa = "SALUD TOTAL: objeta el servicio"
        eps, corregido, _ = resolver_eps_efectiva("DISPENSARIO MEDICO", glosa)
        assert corregido is True
        assert "SALUD TOTAL" in eps.upper()

    def test_ronda19_t121_corpus_intacto(self):
        from app.services.citation_verifier import _buscar_clave_norma
        from app.services.normativa_completa import _TODAS_LAS_NORMAS

        assert _buscar_clave_norma("t", "121", "2015", _TODAS_LAS_NORMAS) is not None

    def test_ronda18_sancion_intacto(self):
        from app.services.glosa_service import _rechazar_sancion_eps_ilegal

        d = "EL HUS SE AJUSTA A LA SANCIÓN APLICADA POR LA EPS."
        res = _rechazar_sancion_eps_ilegal(d, texto_glosa="SANCIÓN DEL 10%")
        assert "rechaza" in res.lower() or "RECHAZA" in res

    def test_ronda16_cups_neutralizado_intacto(self):
        texto = "PROCEDIMIENTO BAJO EL CUPS 1011"
        resultado = _neutralizar_alucinaciones_prompt(texto)
        assert "CUPS 1011" not in resultado
