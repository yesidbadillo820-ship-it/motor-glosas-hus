"""El asistente puede consultar la malla contractual — y está obligado a hacerlo.

Antes, el chat tenía tools para soportes, tarifas CUPS y normas, pero si el
gestor preguntaba «¿qué contrato de COMPENSAR regía en septiembre?» la IA
solo podía adivinar. Ahora la misma malla que usa el análisis responde en el
chat, con la misma regla del día del hecho.
"""

from __future__ import annotations

import json

import pytest

from app.services import asistente_maestro as am


def _tool(nombre: str) -> dict:
    fichas = [t for t in am.TOOLS_ASISTENTE if t["name"] == nombre]
    assert len(fichas) == 1, f"la tool {nombre} debe estar declarada exactamente una vez"
    return fichas[0]


class TestToolMallaDeclarada:
    def test_esta_en_el_catalogo_de_tools(self):
        ficha = _tool("consultar_malla_contractual")
        props = ficha["input_schema"]["properties"]
        assert "pagador" in props and "fecha" in props

    def test_el_sistema_obliga_a_verificar_antes_de_citar(self):
        """La regla dura 9: sin verificación de vigencia no se cita contrato."""
        assert "consultar_malla_contractual" in am.SYSTEM_ASISTENTE_MAESTRO
        assert "DÍA DEL HECHO" in am.SYSTEM_ASISTENTE_MAESTRO


class TestEjecucion:
    async def test_contrato_del_dia_del_hecho(self):
        res = json.loads(
            await am.execute_tool_asistente(
                "consultar_malla_contractual",
                {"pagador": "COMPENSAR", "fecha": "2025-09-15"},
                db=None,
                current_user=None,
            )
        )
        assert res["hay_contrato"] is True
        assert res["contrato"]["numero"] == "CSS009-2024"
        assert res["contrato"]["factor"] == pytest.approx(0.85)

    async def test_dia_sin_contrato_no_inventa(self):
        """Julio 2026: el CSS009-2024 ya venció. La respuesta lo dice y
        muestra qué contratos existen, para que la IA explique en vez de
        citar uno muerto."""
        res = json.loads(
            await am.execute_tool_asistente(
                "consultar_malla_contractual",
                {"pagador": "COMPENSAR", "fecha": "2026-07-20"},
                db=None,
                current_user=None,
            )
        )
        assert res["hay_contrato"] is False
        assert res["contrato"] is None
        numeros = [c["numero"] for c in res["otros_contratos"]]
        assert "CSS009-2024" in numeros

    async def test_sin_pagador_da_el_panorama(self):
        res = json.loads(
            await am.execute_tool_asistente(
                "consultar_malla_contractual", {}, db=None, current_user=None
            )
        )
        for clave in ("vencidos", "por_vencer", "vigentes", "fecha_malla"):
            assert clave in res

    async def test_fecha_malformada_no_revienta(self):
        res = json.loads(
            await am.execute_tool_asistente(
                "consultar_malla_contractual",
                {"pagador": "COMPENSAR", "fecha": "20/07/2026"},
                db=None,
                current_user=None,
            )
        )
        assert "AAAA-MM-DD" in res["error"]
