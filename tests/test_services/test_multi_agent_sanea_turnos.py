"""Regresión del 400 "text content blocks must be non-empty" en el
loop multi-turn de multi_agent: NO debe reinyectar bloques text vacíos
junto al tool_use, ni enviar tool_result con contenido vacío.
"""
import json

import pytest

import app.services.multi_agent as ma
from app.services.multi_agent import Agent


class _FakeResp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, segundo_payload, primer_payload):
        self.requests = []
        self._turno = 0
        self._primer = primer_payload
        self._segundo = segundo_payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        self.requests.append(json)
        self._turno += 1
        return _FakeResp(self._primer if self._turno == 1 else self._segundo)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _agente():
    return Agent(
        name="t",
        system_prompt="sys",
        tools=[{"name": "buscar", "description": "d",
                "input_schema": {"type": "object", "properties": {}}}],
    )


@pytest.mark.anyio
async def test_no_reinyecta_text_vacio_junto_a_tool_use(monkeypatch):
    primer = {
        "content": [
            {"type": "text", "text": "   "},  # whitespace → inválido
            {"type": "tool_use", "id": "tu_1", "name": "buscar",
             "input": {"q": "x"}},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 5, "output_tokens": 3},
    }
    segundo = {
        "content": [{"type": "text", "text": "Listo, respuesta final."}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 4, "output_tokens": 2},
    }
    fake = _FakeClient(segundo, primer)
    monkeypatch.setattr(ma.httpx, "AsyncClient", lambda *a, **k: fake)
    monkeypatch.setattr(
        "app.services.ia_tools.execute_tool",
        lambda *a, **k: "resultado de la tool",
    )

    out = await _agente().run("hola", api_key="sk-test", modelo="claude-x", max_turns=4)

    assert out["error"] is None
    assert out["texto"] == "Listo, respuesta final."

    msgs_turno2 = fake.requests[1]["messages"]
    # Garantía real: ningún bloque text vacío/whitespace viaja a Anthropic
    # y el tool_use se conserva en el assistant reinyectado.
    for m in msgs_turno2:
        if isinstance(m["content"], list):
            for b in m["content"]:
                if b.get("type") == "text":
                    assert b["text"].strip(), f"text vacío reinyectado: {b!r}"
    tiene_tool_use = any(
        isinstance(m["content"], list)
        and any(b.get("type") == "tool_use" for b in m["content"])
        for m in msgs_turno2
        if m["role"] == "assistant"
    )
    assert tiene_tool_use, "el tool_use debe conservarse tras el saneo"


@pytest.mark.anyio
async def test_tool_result_vacio_se_reemplaza(monkeypatch):
    primer = {
        "content": [
            {"type": "tool_use", "id": "tu_1", "name": "buscar",
             "input": {}},
        ],
        "stop_reason": "tool_use",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    segundo = {
        "content": [{"type": "text", "text": "fin"}],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    fake = _FakeClient(segundo, primer)
    monkeypatch.setattr(ma.httpx, "AsyncClient", lambda *a, **k: fake)
    monkeypatch.setattr(
        "app.services.ia_tools.execute_tool", lambda *a, **k: "",
    )

    out = await _agente().run("hola", api_key="sk-test", modelo="claude-x", max_turns=4)

    assert out["error"] is None
    tr = [
        b
        for m in fake.requests[1]["messages"]
        if m["role"] == "user" and isinstance(m["content"], list)
        for b in m["content"]
        if b.get("type") == "tool_result"
    ]
    assert tr, "debe haberse enviado el tool_result"
    for b in tr:
        assert str(b["content"]).strip(), "tool_result no debe ir vacío"
