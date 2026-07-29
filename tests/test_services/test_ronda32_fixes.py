"""Ronda 32 (22-jul-2026): fixes salidos de los 4 casos de prueba difíciles.

Evidencia (dictámenes reales pegados por Yesid el 22-jul):
  1. Los 4 casos citaron el número de FACTURA como CUPS ("CUPS 224871"…).
  2. Caso 3 ($16.8M) y caso 4 ($18.6M) corrieron en Groq — el valor solo
     escalaba a Claude desde $50M.
  3. Caso 2 (AURORA/ARL): la glosa venía encuadrada en "Ley 100 régimen
     contributivo" y el dictamen no corrigió el régimen ni citó el
     Decreto-Ley 1295/1994.
  4. Caso 3: fechas de factura y de glosa EN EL TEXTO (38 hábiles > 20)
     pero formulario sin fechas → extemporaneidad no detectada.
"""

from __future__ import annotations

from app.services.extemporaneidad_texto import detectar_extemporaneidad_en_texto
from app.services.glosa_ia_prompts import REGIMEN_ESPECIAL, _detectar_regimen_especial
from app.services.glosa_service import _neutralizar_cups_igual_factura
from app.services.routing_complejidad import detectar_complejidad_critica


# ─── Fix 32.4: ruteo por monto — valor solo escala desde $10M ─────────────


class TestRuteoPorMonto:
    def test_16_8m_solo_es_complejo(self):
        r = detectar_complejidad_critica(valor=16_800_000)
        assert r.es_complejo is True
        assert any("valor-alto" in m for m in r.motivos)

    def test_18_6m_solo_es_complejo(self):
        r = detectar_complejidad_critica(valor=18_600_000)
        assert r.es_complejo is True

    def test_10m_exacto_es_complejo(self):
        r = detectar_complejidad_critica(valor=10_000_000)
        assert r.es_complejo is True

    def test_9_9m_solo_no_es_complejo(self):
        r = detectar_complejidad_critica(valor=9_900_000)
        assert r.es_complejo is False

    def test_50m_conserva_motivo_original(self):
        r = detectar_complejidad_critica(valor=50_000_000)
        assert r.es_complejo is True
        assert any(m.startswith("valor=$") for m in r.motivos)
        assert not any("valor-alto" in m for m in r.motivos)

    def test_umbral_ajustable_por_env(self, monkeypatch):
        monkeypatch.setenv("ROUTING_VALOR_SOLO_MIN", "30000000")
        assert detectar_complejidad_critica(valor=16_800_000).es_complejo is False
        assert detectar_complejidad_critica(valor=35_000_000).es_complejo is True

    def test_env_ilegible_cae_al_default(self, monkeypatch):
        monkeypatch.setenv("ROUTING_VALOR_SOLO_MIN", "diez millones")
        assert detectar_complejidad_critica(valor=16_800_000).es_complejo is True


# ─── Fix 32.3: régimen ARL — regla fuerte en AURORA/POSITIVA + corrección ──


class TestRegimenArl:
    def test_bloque_aurora_trae_regla_estrategica(self):
        b = REGIMEN_ESPECIAL["AURORA"]
        assert "1295/1994" in b
        assert "NO citar Ley 100" in b

    def test_bloque_positiva_trae_regla_estrategica(self):
        b = REGIMEN_ESPECIAL["POSITIVA"]
        assert "1295/1994" in b
        assert "NO citar Ley 100" in b

    def test_glosa_aurora_con_ley_100_agrega_correccion(self):
        # Caso 2 de las pruebas: la ARL encuadró la glosa en Ley 100.
        bloque = _detectar_regimen_especial(
            "AURORA",
            "",
            texto_glosa="CONFORME A LA LEY 100 DE 1993, RÉGIMEN CONTRIBUTIVO, SE GLOSA...",
        )
        assert "CORRECCIÓN DE RÉGIMEN OBLIGATORIA" in bloque
        assert "Decreto-Ley 1295/1994" in bloque

    def test_glosa_arl_sin_ley_100_no_agrega_correccion(self):
        bloque = _detectar_regimen_especial(
            "AURORA", "", texto_glosa="GLOSA POR TARIFAS SEGÚN FURAT ADJUNTO"
        )
        assert "CORRECCIÓN DE RÉGIMEN" not in bloque
        assert "1295/1994" in bloque  # el bloque ARL base sí va

    def test_sin_texto_no_agrega_correccion_cache_estable(self):
        # El system prompt llama sin texto_glosa: debe seguir estable.
        bloque = _detectar_regimen_especial("AURORA", "")
        assert "CORRECCIÓN DE RÉGIMEN" not in bloque

    def test_arl_detectada_por_texto_con_ley_100(self):
        bloque = _detectar_regimen_especial(
            "OTRA / SIN DEFINIR",
            "",
            texto_glosa="LA ARL BOLÍVAR GLOSA CONFORME AL RÉGIMEN CONTRIBUTIVO DE LA LEY 100",
        )
        assert "RIESGOS LABORALES" in bloque
        assert "CORRECCIÓN DE RÉGIMEN OBLIGATORIA" in bloque

    def test_regimen_no_arl_nunca_lleva_correccion(self):
        # Un régimen especial NO ARL (PPL) no debe llevar la corrección
        # aunque el texto mencione Ley 100.
        bloque = _detectar_regimen_especial(
            "PPL", "", texto_glosa="SEGÚN LA LEY 100 RÉGIMEN CONTRIBUTIVO"
        )
        assert "CORRECCIÓN DE RÉGIMEN" not in bloque


# ─── Fix 32.1: número de factura citado como CUPS ─────────────────────────


class TestCupsIgualFactura:
    def test_neutraliza_cups_factura_basico(self):
        r = _neutralizar_cups_igual_factura(
            "SOBRE EL CUPS 224871 SE APLICÓ TARIFA INCORRECTA", "224871"
        )
        assert "224871" not in r
        assert "procedimiento facturado" in r

    def test_neutraliza_codigo_cups_con_prefijo_hus(self):
        r = _neutralizar_cups_igual_factura(
            "EL CÓDIGO CUPS HUS0000224871 CORRESPONDE AL SERVICIO", "HUS0000224871"
        )
        assert "224871" not in r

    def test_neutraliza_factura_con_ceros(self):
        # Factura HUS con ceros → el dictamen la cita pelada como CUPS.
        r = _neutralizar_cups_igual_factura("BAJO EL CUPS 219004 FACTURADO", "HUS0000219004")
        assert "219004" not in r

    def test_respeta_cups_real_distinto(self):
        texto = "EL CUPS 890201 CORRESPONDE A CONSULTA DE URGENCIAS"
        assert _neutralizar_cups_igual_factura(texto, "224871") == texto

    def test_sin_factura_no_toca(self):
        texto = "EL CUPS 224871 DEL SERVICIO"
        assert _neutralizar_cups_igual_factura(texto, "") == texto
        assert _neutralizar_cups_igual_factura(texto, None) == texto

    def test_factura_citada_como_factura_se_respeta(self):
        # Solo se neutraliza en contexto CUPS: "FACTURA 224871" es correcto.
        texto = "LA FACTURA 224871 FUE RADICADA EN TÉRMINOS"
        assert _neutralizar_cups_igual_factura(texto, "224871") == texto

    def test_no_toca_cups_con_sufijo_cum(self):
        # "224871-3" parece CUM — conservador: no tocar.
        texto = "EL CUPS 224871-3 DEL MEDICAMENTO"
        assert _neutralizar_cups_igual_factura(texto, "224871") == texto

    def test_neutraliza_cups_con_dos_puntos(self):
        r = _neutralizar_cups_igual_factura("SERVICIO CON CUPS: 220617 GLOSADO", "220617")
        assert "220617" not in r


# ─── Fix 32.2: extemporaneidad desde el texto de la glosa ─────────────────


class TestExtemporaneidadTexto:
    def test_caso3_fechas_en_el_texto(self):
        texto = (
            "GLOSA A LA FACTURA N° 219004. FECHA DE LA FACTURA: 02/04/2026. "
            "LA PRESENTE GLOSA FUE RADICADA EL 28/05/2026 POR PERTINENCIA MÉDICA."
        )
        d = detectar_extemporaneidad_en_texto(texto)
        assert d is not None
        assert d["fecha_inicio"] == "2026-04-02"
        assert d["fecha_glosa"] == "2026-05-28"
        assert d["dias_habiles"] > 20
        assert d["es_extemporanea"] is True

    def test_dentro_de_terminos(self):
        texto = "FECHA DE RADICACIÓN DE LA FACTURA: 05/05/2026. GLOSA NOTIFICADA EL 15/05/2026."
        d = detectar_extemporaneidad_en_texto(texto)
        assert d is not None
        assert d["es_extemporanea"] is False

    def test_mes_en_letras(self):
        texto = (
            "FECHA DE LA FACTURA: 2 DE ABRIL DE 2026. RADICACIÓN DE LA GLOSA: 28 DE MAYO DE 2026."
        )
        d = detectar_extemporaneidad_en_texto(texto)
        assert d is not None
        assert d["fecha_inicio"] == "2026-04-02"
        assert d["fecha_glosa"] == "2026-05-28"

    def test_formato_iso(self):
        texto = "FECHA DE FACTURA 2026-04-02 Y GLOSA RADICADA EL 2026-05-28"
        d = detectar_extemporaneidad_en_texto(texto)
        assert d is not None
        assert d["es_extemporanea"] is True

    def test_sin_fechas_etiquetadas_devuelve_none(self):
        assert detectar_extemporaneidad_en_texto("GLOSA POR TARIFAS SIN SOPORTE") is None

    def test_fechas_sueltas_sin_etiqueta_no_disparan(self):
        # Fechas presentes pero sin etiqueta de factura/glosa → None
        # (conservador: nunca adivinar roles de fechas sueltas).
        texto = "EL 02/04/2026 SE ATENDIÓ AL PACIENTE. EL 28/05/2026 SE DIO EGRESO."
        assert detectar_extemporaneidad_en_texto(texto) is None

    def test_fechas_incoherentes_devuelve_none(self):
        # Glosa "anterior" a la factura → mejor no opinar.
        texto = "FECHA DE LA FACTURA: 28/05/2026. GLOSA RADICADA EL 02/04/2026."
        assert detectar_extemporaneidad_en_texto(texto) is None

    def test_gap_mayor_a_un_ano_devuelve_none(self):
        texto = "FECHA DE LA FACTURA: 02/04/2024. GLOSA RADICADA EL 28/05/2026."
        assert detectar_extemporaneidad_en_texto(texto) is None

    def test_texto_vacio(self):
        assert detectar_extemporaneidad_en_texto("") is None
        assert detectar_extemporaneidad_en_texto(None) is None


# ─── Regresiones de la revisión adversarial (22-jul-2026) ─────────────────


class TestRevisionAdversarialRonda32:
    """Cada test reproduce un hallazgo CONFIRMADO por el panel de revisión."""

    def test_periodo_contractual_no_es_fecha_de_factura(self):
        # Hallazgo 1 (alta): "NO CORRESPONDE" era tragado como número de
        # documento y la fecha del PERIODO del contrato quedaba como fecha
        # de factura → extemporaneidad inventada de 99 días.
        texto = (
            "FECHA DE FACTURACION NO CORRESPONDE AL PERIODO 01/01/2026 A "
            "31/12/2026 DEL CONTRATO. GLOSA NOTIFICADA EL 28/05/2026."
        )
        assert detectar_extemporaneidad_en_texto(texto) is None

    def test_se_glosa_verbo_no_captura_fecha_ajena(self):
        # Hallazgo 2 (alta): "SE GLOSA PORQUE LA INCAPACIDAD FUE NOTIFICADA
        # EL..." atribuía a la glosa la fecha de la incapacidad.
        texto = (
            "SE GLOSA PORQUE LA INCAPACIDAD FUE NOTIFICADA EL 10/06/2026 "
            "SIN SOPORTE. FACTURA DE VENTA DEL 02/04/2026."
        )
        assert detectar_extemporaneidad_en_texto(texto) is None

    def test_numero_de_factura_pelado_sin_no_tambien_detecta(self):
        # Hallazgo 3 (media): sin "N°" el número pelado rompía la ventana y
        # el formato más común quedaba sin detectar.
        texto = (
            "RADICACION DE LA FACTURA HUS0000224871 EL 02/04/2026. GLOSA NOTIFICADA EL 28/05/2026."
        )
        d = detectar_extemporaneidad_en_texto(texto)
        assert d is not None and d["es_extemporanea"] is True

        texto2 = "FACTURA 224871 RADICADA EL 02/04/2026. GLOSA NOTIFICADA EL 28/05/2026."
        d2 = detectar_extemporaneidad_en_texto(texto2)
        assert d2 is not None and d2["es_extemporanea"] is True

    def test_glosa_a_la_factura_radicada_no_cruza(self):
        # Hallazgo 13 (baja): "GLOSA A LA FACTURA ... RADICADA EL" habla de
        # la radicación de la FACTURA — la ventana no debe cruzar "FACTURA".
        texto = (
            "GLOSA A LA FACTURA QUE FUE PRESENTADA OPORTUNAMENTE A LA EPS Y "
            "RADICADA EL 02/05/2026. FECHA DE LA FACTURA: 02/04/2026."
        )
        d = detectar_extemporaneidad_en_texto(texto)
        # O no detecta nada, o jamás usa 02/05 como fecha de glosa.
        assert d is None or d["fecha_glosa"] != "2026-05-02"

    def test_anos_sin_feriados_cargados_no_opina(self):
        # Hallazgos 8/18 (baja): sin feriados para esos años el conteo se
        # infla — mejor devolver None que fabricar una extemporánea límite.
        texto = "FECHA DE LA FACTURA: 02/04/2021. GLOSA RADICADA EL 28/05/2021."
        assert detectar_extemporaneidad_en_texto(texto) is None

    def test_pos_quirurgica_no_dispara_correccion_de_regimen(self):
        # Hallazgo 4 (media): \bPOS\b matcheaba "pos-quirúrgica" e imputaba
        # a la ARL un encuadre en Ley 100 que nunca hizo.
        bloque = _detectar_regimen_especial(
            "AURORA", "", texto_glosa="SE GLOSA CURACIÓN POS-QUIRÚRGICA SIN PERTINENCIA"
        )
        assert "CORRECCIÓN DE RÉGIMEN" not in bloque

    def test_pbs_solo_no_dispara_correccion_de_regimen(self):
        # Hallazgos 11/17: "no incluido en el PBS" no es invocar la Ley 100.
        bloque = _detectar_regimen_especial(
            "POSITIVA", "", texto_glosa="SERVICIO NO INCLUIDO EN EL PBS"
        )
        assert "CORRECCIÓN DE RÉGIMEN" not in bloque

    def test_regla_arl_sin_cita_art_18_ley_776(self):
        # Hallazgo 14 (alta): el Art. 18 de la Ley 776/2002 es PRESCRIPCIÓN,
        # no subrogación — la cita mal atribuida no puede ir en el prompt.
        for clave in ("ARL", "AURORA", "POSITIVA"):
            assert "Art. 18" not in REGIMEN_ESPECIAL[clave]
            # La controversia de origen se funda en las Juntas (D. 1352/2013).
            assert "1352/2013" in REGIMEN_ESPECIAL[clave]

    def test_cups_no_abreviado_tambien_se_neutraliza(self):
        # Hallazgo 5 (media): "CUPS No. 224871" pasaba la malla.
        r = _neutralizar_cups_igual_factura("SE OBJETA EL CUPS No. 224871", "HUS0000224871")
        assert "224871" not in r

    def test_enumeracion_de_cups_no_se_rompe(self):
        # Hallazgo 6 (baja): consumir "CUPS" en una enumeración dejaba
        # huérfanos los códigos reales — mejor no tocar la lista.
        texto = "CUPS 224871, 890201 Y 890301 PERTINENTES"
        assert _neutralizar_cups_igual_factura(texto, "224871") == texto

    def test_texto_condicional_sin_afirmaciones_categoricas(self):
        # Hallazgos 9/15/16 (alta): la sección inferida no puede radicar el
        # texto canónico categórico ni el cierre RE9502 ni citar Ley 1438.
        from app.services.glosa_service import generar_texto_extemporanea_condicional

        t = generar_texto_extemporanea_condicional(38, "2026-04-02", "2026-05-28")
        assert "DE CONFIRMARSE" in t
        assert "38 DÍAS HÁBILES" in t
        assert "SE EXIGE" not in t
        assert "PLENO DERECHO" not in t
        assert "CARTERA@HUS.GOV.CO" not in t  # cierre reservado a RE95xx/96xx
        assert "1438" not in t  # sin cita normativa en la variante inferida


# ─── Cableado: las redes nuevas están enganchadas en glosa_service ─────────


class TestCableadoRonda32:
    def _src(self):
        import inspect

        import app.services.glosa_service as gs

        return inspect.getsource(gs)

    def test_red_cups_factura_enganchada(self):
        src = self._src()
        # def + llamada en la RED FINAL
        assert src.count("_neutralizar_cups_igual_factura(") >= 2

    def test_deteccion_extemporaneidad_texto_enganchada(self):
        src = self._src()
        assert "detectar_extemporaneidad_en_texto" in src
        assert "POSIBLE EXTEMPORÁNEA" in src

    def test_seccion_inferida_usa_texto_condicional(self):
        # Hallazgo 15: la sección debe usar la variante condicional y
        # excluir también plantilla/directo_auditor (hallazgo 10).
        src = self._src()
        assert "generar_texto_extemporanea_condicional(" in src
        assert '"plantilla", "directo_auditor"' in src
