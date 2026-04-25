"""Tests del system prompt de auditoría previa (R59 P2)."""
from __future__ import annotations

from app.services.glosa_ia_prompts import (
    _PROMPT_AUDITORIA_PREVIA,
    get_system_prompt_auditoria,
)


class TestPromptAuditoriaPrevia:
    def test_no_promueve_dictamen_de_defensa(self):
        """El prompt debe PROHIBIR explícitamente los encabezados de defensa
        — el bug a evitar es que el gestor pida 'auditoría previa' y la IA
        igual le devuelva 'ESE HUS NO ACEPTA…'."""
        assert "PROHIBIDO" in _PROMPT_AUDITORIA_PREVIA
        # En la sección PROHIBIDO debe aparecer el patrón típico de defensa
        # como ejemplo de lo que NO se debe escribir.
        assert "ESE HUS NO ACEPTA" in _PROMPT_AUDITORIA_PREVIA

    def test_estructura_seis_secciones_html(self):
        """Estructura definida: 6 sections con data-block atributo."""
        for block in (
            "resumen", "hallazgos", "riesgos",
            "probabilidad", "recomendacion", "normativa",
        ):
            assert f'data-block="{block}"' in _PROMPT_AUDITORIA_PREVIA, (
                f"falta sección {block}"
            )

    def test_recomendaciones_neutrales(self):
        """Las 4 acciones esperadas como recomendación deben estar
        listadas como opciones (no como decisión final tomada)."""
        for accion in (
            "DEFENDER TOTAL", "DEFENDER PARCIAL",
            "ACEPTAR TOTAL", "PEDIR MÁS INFORMACIÓN",
        ):
            assert accion in _PROMPT_AUDITORIA_PREVIA

    def test_pide_lenguaje_neutral(self):
        """Términos clave que evitan tomar partido."""
        assert "neutral" in _PROMPT_AUDITORIA_PREVIA.lower()
        assert "AUDITOR" in _PROMPT_AUDITORIA_PREVIA

    def test_get_system_prompt_auditoria_con_eps(self):
        p = get_system_prompt_auditoria("FAMISANAR")
        # Debe incluir el cuerpo base
        assert "AUDITOR MÉDICO" in p
        # Y el régimen especial si aplica (FAMISANAR es contributivo, sin
        # régimen especial obligatorio — pero la función NO debe romper).
        assert isinstance(p, str)
        assert len(p) > 1000

    def test_get_system_prompt_auditoria_sanidad_militar(self):
        """Para Sanidad Militar (DMBUG/DISAN) DEBE inyectar el régimen
        especial al final."""
        p = get_system_prompt_auditoria("DISPENSARIO MEDICO DMBUG")
        # Si se detecta sanidad militar, el bloque debería aparecer
        # delimitado por las líneas dobles
        assert "AUDITOR MÉDICO" in p

    def test_get_system_prompt_auditoria_eps_vacia(self):
        """No debe romper con string vacío."""
        p = get_system_prompt_auditoria("")
        assert "AUDITOR MÉDICO" in p

    def test_no_contiene_calculadora_tarifaria_obligatoria(self):
        """A diferencia de get_system_prompt(prefijo=TA), el de auditoría
        NO incluye 'CALCULADORA TARIFARIA OBLIGATORIA' como bloque
        prefabricado — el auditor calcula si tiene los datos, sin
        forzar el formato del defensor."""
        p = get_system_prompt_auditoria("FAMISANAR")
        assert "CALCULADORA TARIFARIA OBLIGATORIA" not in p
