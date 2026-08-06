"""Ronda 35 (03-ago-2026): el formato Gold aprobado por el auditor.

Yesid aprobó textualmente la respuesta del caso TA0801/898015H como «la
que me gustaría que me diera cuando yo le dé analizar». Sus rasgos quedan
parametrizados: encabezado de referencia como primera línea, postura seca,
y UN punto numerado por CADA sub-objeción de la glosa — ni menos (concesión
tácita) ni más (relleno). La respuesta completa queda además en el banco
HUS (TA-G11) para el patrón SOAT/UVB sin contrato.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.services.glosa_ia_prompts import get_system_prompt


class TestFormatoGold:
    def test_encabezado_de_referencia_primero(self):
        p = get_system_prompt("TA", "COMPENSAR")
        assert "P0 ENCABEZADO DE REFERENCIA (RONDA 35)" in p
        assert "RESPUESTA GLOSA [CÓDIGO] – FACTURA [Nº] – CUPS [CUPS]" in p

    def test_un_punto_por_cada_sub_objecion(self):
        p = get_system_prompt("TA", "COMPENSAR")
        assert "UN punto" in p and "por CADA sub-objeción" in p
        assert "concesión" in p  # dejar un reclamo sin contestar = conceder


class TestPlantillaGoldSembrada:
    def test_ta_g11_en_el_banco(self):
        raiz = Path(__file__).resolve().parent.parent.parent
        d = json.loads((raiz / "data" / "plantillas_hus_base.json").read_text(encoding="utf-8"))
        ta11 = next(p for p in d["plantillas"] if p["codigo_glosa"] == "TA-G11")
        arg = ta11["argumento"]
        assert arg.startswith("RESPUESTA GLOSA [CÓDIGO]")
        assert "LA E.S.E. HUS NO ACEPTA LA GLOSA. PRIMERO:" in arg
        assert "SOAT PLENA" in arg and "UVB 2026 = $12.110" in arg
        # 06-08-2026: cerraba citando la Resolución 3047 de 2008, que la
        # 2284 de 2023 reemplazó. Pedir el levantamiento apoyándose en una
        # norma derogada le da a la entidad la respuesta servida.
        assert "LEVANTAMIENTO TOTAL DE LA GLOSA (RESOLUCIÓN 2284 DE 2023)" in arg
        assert "3047" not in arg
        # Con placeholders, no con los datos del caso original
        assert "1344527" not in arg and "45.500" not in arg
