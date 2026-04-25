"""Tests de los helpers privados extraídos a app/api/routers/analizar.py
(R55 P3 — cobertura defensiva del split R53 P1).
"""
from __future__ import annotations

from app.api.routers.analizar import (
    _construir_dictamen_aceptacion,
    _decidir_estado_y_codigo,
)


class TestDecidirEstadoYCodigo:
    def test_radicada_default(self):
        """Sin aceptación → estado RADICADA, sin código de respuesta."""
        v_obj, estado, cod, desc = _decidir_estado_y_codigo(100_000, 0)
        assert v_obj == 100_000
        assert estado == "RADICADA"
        assert cod is None
        assert desc is None

    def test_aceptada_total(self):
        """val_aceptado >= val_objetado → ACEPTADA + RE9702."""
        _, estado, cod, desc = _decidir_estado_y_codigo(100_000, 100_000)
        assert estado == "ACEPTADA"
        assert cod == "RE9702"
        assert "100" in desc  # 'GLOSA ACEPTADA AL 100%'

    def test_aceptada_sobreaceptada(self):
        """val_ac > val_obj también es ACEPTADA (no negativa)."""
        _, estado, cod, _ = _decidir_estado_y_codigo(100_000, 150_000)
        assert estado == "ACEPTADA"
        assert cod == "RE9702"

    def test_parcialmente_aceptada(self):
        """val_ac > 0 y < val_obj → PARCIALMENTE_ACEPTADA + RE9801."""
        _, estado, cod, desc = _decidir_estado_y_codigo(100_000, 30_000)
        assert estado == "PARCIALMENTE_ACEPTADA"
        assert cod == "RE9801"
        assert "PARCIAL" in desc.upper()

    def test_bug_fix_val_obj_cero_con_aceptacion(self):
        """REGRESIÓN: si val_obj=0 pero val_ac>0, es aceptación total
        (caso de glosa donde no se extrajo el valor del texto pero el
        coordinador puso el aceptado). val_obj corregido = val_ac."""
        v_obj, estado, cod, _ = _decidir_estado_y_codigo(0, 50_000)
        assert v_obj == 50_000  # corregido
        assert estado == "ACEPTADA"
        assert cod == "RE9702"

    def test_ambos_cero_es_radicada(self):
        v_obj, estado, cod, _ = _decidir_estado_y_codigo(0, 0)
        assert v_obj == 0
        assert estado == "RADICADA"
        assert cod is None


class TestConstruirDictamenAceptacion:
    def test_aceptada_total_html_completo(self):
        html = _construir_dictamen_aceptacion(
            eps="FAMISANAR", codigo_glosa="TA0201",
            val_obj=168_563, val_ac=168_563,
            estado="ACEPTADA", cod_resp="RE9702",
            desc_resp="GLOSA ACEPTADA AL 100%",
            tabla_excel="TA0201 consulta urgencias", contexto_pdf="",
        )
        # Debe traer la tabla de códigos
        assert "TA0201" in html
        assert "RE9702" in html
        assert "168,563" in html
        # Bloque verde de aceptación total
        assert "RESPUESTA A GLOSA" in html
        assert "ACEPTA GLOSA TOTAL" in html
        # Tabla resumen de valores
        assert "Resumen de valores" in html
        # No debe haber bloque "valor en disputa" (es total)
        assert "Valor en disputa" not in html

    def test_parcialmente_aceptada_muestra_disputa(self):
        html = _construir_dictamen_aceptacion(
            eps="FAMISANAR", codigo_glosa="SO0101",
            val_obj=200_000, val_ac=80_000,
            estado="PARCIALMENTE_ACEPTADA", cod_resp="RE9801",
            desc_resp="GLOSA ACEPTADA Y SUBSANADA PARCIALMENTE",
            tabla_excel="texto glosa", contexto_pdf="",
        )
        # Bloque ámbar de aceptación parcial
        assert "ACEPTA GLOSA PARCIAL" in html
        assert "RE9801" in html
        # Diferencia 200k - 80k = 120k debe aparecer como "valor en disputa"
        assert "Valor en disputa" in html
        assert "120,000" in html

    def test_html_no_tiene_valor_negativo(self):
        """Si por error val_ac > val_obj, val_rechazado podría ser
        negativo. abs() debe garantizar valor positivo en disputa."""
        html = _construir_dictamen_aceptacion(
            eps="X", codigo_glosa="Y", val_obj=100, val_ac=150,
            estado="PARCIALMENTE_ACEPTADA", cod_resp="RE9801",
            desc_resp="d", tabla_excel="t", contexto_pdf="",
        )
        # No debe haber un "$-50" en el HTML
        assert "$-" not in html

    def test_eps_y_codigo_aparecen(self):
        html = _construir_dictamen_aceptacion(
            eps="SALUD TOTAL EPS", codigo_glosa="FA0401",
            val_obj=10_000, val_ac=10_000,
            estado="ACEPTADA", cod_resp="RE9702",
            desc_resp="d", tabla_excel="", contexto_pdf="",
        )
        assert "FA0401" in html


class TestObtenerFewShots:
    def test_sin_codigo_en_texto_sin_few_shots(self):
        """Si la glosa no tiene un código tipo TA0201, no se invoca BD
        de plantillas y se devuelve lista vacía."""
        from app.api.routers.analizar import _obtener_few_shots
        from unittest.mock import MagicMock
        db = MagicMock()
        few, plant, cod = _obtener_few_shots(db, eps="X", tabla_excel="texto plano sin código")
        assert few == []
        assert plant == []
        assert cod == ""
        # Y la BD no fue llamada
        db.query.assert_not_called()

    def test_codigo_tipico_dispara_lookup(self):
        """Con TA0201 en el texto, debe llamarse a obtener_few_shot."""
        from app.api.routers import analizar as mod
        from unittest.mock import MagicMock, patch
        db = MagicMock()
        with patch.object(mod, "_obtener_few_shots", wraps=mod._obtener_few_shots):
            # Patch indirecto: monkey-patch el import lazy
            from app.api.routers import plantillas_gold as pg
            with patch.object(pg, "obtener_few_shot", return_value=[]) as mock_few:
                few, plant, cod = mod._obtener_few_shots(
                    db, eps="FAMISANAR", tabla_excel="…código TA0201 valor X…",
                )
                assert cod == "TA0201"
                # Sí se invocó la búsqueda en BD
                mock_few.assert_called_once()


import pytest


class TestExtraerPdfs:
    @pytest.mark.asyncio
    async def test_archivos_none_retorna_vacio(self):
        from app.api.routers.analizar import _extraer_pdfs
        contexto, n = await _extraer_pdfs(None, req_id="test")
        assert contexto == ""
        assert n == 0

    @pytest.mark.asyncio
    async def test_archivos_lista_vacia_retorna_vacio(self):
        from app.api.routers.analizar import _extraer_pdfs
        contexto, n = await _extraer_pdfs([], req_id="test")
        assert contexto == ""
        assert n == 0

    @pytest.mark.asyncio
    async def test_archivo_no_pdf_se_ignora(self):
        """Si el primer header no es %PDF, se loggea warning y se ignora."""
        from app.api.routers.analizar import _extraer_pdfs
        from unittest.mock import AsyncMock, MagicMock
        f = MagicMock()
        f.filename = "no-es-pdf.txt"
        f.read = AsyncMock(return_value=b"hola mundo no soy pdf")
        contexto, n = await _extraer_pdfs([f], req_id="test")
        assert contexto == ""
        assert n == 0

    @pytest.mark.asyncio
    async def test_archivo_sin_filename_se_ignora(self):
        from app.api.routers.analizar import _extraer_pdfs
        from unittest.mock import AsyncMock, MagicMock
        f = MagicMock()
        f.filename = ""
        contexto, n = await _extraer_pdfs([f], req_id="test")
        assert n == 0
        # f.read no debió llamarse
        f.read.assert_not_called() if hasattr(f.read, "assert_not_called") else None

    @pytest.mark.asyncio
    async def test_pdf_muy_grande_se_ignora(self):
        """PDFs >15MB se omiten para no saturar el LLM."""
        from app.api.routers.analizar import _extraer_pdfs, MAX_BYTES_PDF
        from unittest.mock import AsyncMock, MagicMock
        f = MagicMock()
        f.filename = "huge.pdf"
        f.read = AsyncMock(return_value=b"%PDF-1.7" + b"x" * (MAX_BYTES_PDF + 1))
        contexto, n = await _extraer_pdfs([f], req_id="test")
        assert n == 0  # ignorado por tamaño

    @pytest.mark.asyncio
    async def test_max_archivos_limite(self):
        """Si llegan >10 PDFs, solo se procesan 10."""
        from app.api.routers.analizar import _extraer_pdfs, MAX_ARCHIVOS
        from unittest.mock import AsyncMock, MagicMock, patch
        archivos = []
        for i in range(MAX_ARCHIVOS + 5):
            f = MagicMock()
            f.filename = f"doc{i}.pdf"
            f.read = AsyncMock(return_value=b"%PDF-1.7\n... fake")
            archivos.append(f)
        # Mockear PdfService.extraer_con_ocr para no parsear de verdad
        with patch("app.services.pdf_service.PdfService.extraer_con_ocr",
                   new_callable=AsyncMock,
                   return_value=("contenido extraído", "nativo")):
            contexto, n = await _extraer_pdfs(archivos, req_id="test")
        assert n == MAX_ARCHIVOS  # se cortó en 10
