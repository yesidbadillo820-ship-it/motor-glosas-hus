"""Ronda 33 (22-jul-2026): repetición de normas y costuras del placeholder.

Evidencia: dos dictámenes PPL reales pegados por Yesid el 22-jul (glosas de
$218.145 y $5.800):
  1. "RESPECTO DEL PROCEDIMIENTO FACTURADO CON EL PROCEDIMIENTO FACTURADO
     SEGÚN HISTORIA CLÍNICA" — la malla CUPS dejó un tartamudeo.
  2. "descripción detallada de los servicios el procedimiento facturado
     según historia clínica" — costura sin gramática.
  3. Resolución 1995/1999 citada DOS veces con número completo en la misma
     respuesta; Ley 1438 Art. 56 tirada al pasar como "plazos de glosa"
     (los plazos del trámite son del Art. 57) sin argumentar fechas.
  4. Cláusula de PRÓRROGA del Otrosí 26 citada bajo pacta sunt servanda
     como si resolviera una glosa de soportes.
  5. Pagador nombrado "el fondo PPL" / "PPL" a secas.
"""

from __future__ import annotations

from app.services.glosa_ia_prompts import REGIMEN_ESPECIAL, get_system_prompt
from app.services.glosa_service import _neutralizar_alucinaciones_prompt


# ─── Fix 33.1: costuras del placeholder "el procedimiento facturado" ───────


class TestCosturasPlaceholder:
    def test_tartamudeo_con_conector(self):
        # Caso real PPL $5.800: "DEL ... FACTURADO CON EL ... FACTURADO".
        r = _neutralizar_alucinaciones_prompt(
            "RESPECTO DEL PROCEDIMIENTO FACTURADO CON EL PROCEDIMIENTO "
            "FACTURADO SEGÚN HISTORIA CLÍNICA, POR VALOR OBJETADO DE $ 5.800"
        )
        assert r.upper().count("PROCEDIMIENTO FACTURADO") == 1
        # Conserva el tramo inicial con su mayúscula original.
        assert "DEL PROCEDIMIENTO FACTURADO" in r

    def test_tartamudeo_sin_conector(self):
        r = _neutralizar_alucinaciones_prompt(
            "sobre el procedimiento facturado el procedimiento facturado según historia clínica"
        )
        assert r.lower().count("procedimiento facturado") == 1

    def test_los_servicios_descosidos(self):
        # Caso real PPL $218.145.
        r = _neutralizar_alucinaciones_prompt(
            "descripción detallada de los servicios el procedimiento "
            "facturado según historia clínica, valor unitario y total"
        )
        assert "los servicios facturados" in r
        assert "servicios el procedimiento" not in r

    def test_frase_sana_no_se_toca(self):
        texto = "se defiende el procedimiento facturado según historia clínica"
        assert _neutralizar_alucinaciones_prompt(texto) == texto

    def test_los_servicios_facturados_legitimo_no_se_toca(self):
        texto = "los servicios facturados cumplen los requisitos"
        assert _neutralizar_alucinaciones_prompt(texto) == texto

    def test_contraccion_de_el_fondo(self):
        # Caso real PPL $218.145: "emitida a nombre de el fondo PPL".
        r = _neutralizar_alucinaciones_prompt("emitida a nombre de el fondo PPL")
        assert "del fondo" in r
        assert "de el fondo" not in r

    def test_de_el_solo_en_entidades_acotadas(self):
        # Fuera de la lista acotada no se toca (títulos citados, etc.).
        texto = "la obra de El Carnero citada"
        assert _neutralizar_alucinaciones_prompt(texto) == texto


# ─── Fix 33.2: reglas del prompt — normas una sola vez y solo si se usan ───


class TestReglasNormas:
    def _prompt(self):
        return get_system_prompt("SO", "COMPENSAR")

    def test_regla_anti_repeticion_presente(self):
        p = self._prompt()
        assert "8.quaterdecies" in p
        assert "CADA NORMA UNA SOLA VEZ" in p

    def test_regla_prohibe_norma_suelta(self):
        assert "norma APLICADA a un hecho" in self._prompt()

    def test_precision_art_56_vs_57(self):
        p = self._prompt()
        # El marco normativo ya no agrupa "Art. 56-57 (plazos glosas)".
        assert "Art. 56-57 (plazos glosas)" not in p
        assert "Art. 57 (trámite y plazos de glosas)" in p

    def test_historia_clinica_sin_prueba_plena(self):
        assert '"prueba plena"' in self._prompt()  # la regla que lo prohíbe


# ─── Fix 33.3: cláusula de prórroga = prueba de vigencia, no fundamento ────


class TestEncuadreProrroga:
    def test_regla_encuadre_presente(self):
        p = get_system_prompt("SO", "PPL")
        assert "ENCUADRE (RONDA 33)" in p
        assert "prueba de VIGENCIA" in p


# ─── Fix 33.4: nombre correcto del pagador PPL ─────────────────────────────


class TestNombrePagadorPpl:
    def test_bloque_ppl_trae_nombre_completo(self):
        b = REGIMEN_ESPECIAL["PPL"]
        assert "Fondo Nacional de Salud de las Personas Privadas de la Libertad" in b
        assert "NUNCA" in b
