"""Regresión del bug 400 "text content blocks must be non-empty".

Simula a Anthropic devolviendo en el turno 1 un bloque text vacío junto
a un tool_use (caso que disparaba el 400 al reinyectarlo en el turno 2).
Verifica que el turno 2 NO reenvía bloques de texto vacíos y que el loop
termina devolviendo la respuesta final.
"""
import json

import pytest

import app.services.asistente_maestro as am


class _FakeResp:
    def __init__(self, payload):
        self.status_code = 200
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


class _FakeClient:
    """Captura los bodies enviados y responde con payloads predefinidos."""

    def __init__(self, *a, **k):
        self.requests = []
        self._turno = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, json=None):
        self.requests.append(json)
        self._turno += 1
        if self._turno == 1:
            return _FakeResp({
                "content": [
                    {"type": "text", "text": ""},  # <-- bloque vacío (el bug)
                    {"type": "tool_use", "id": "tu_1",
                     "name": "buscar", "input": {"q": "x"}},
                ],
                "stop_reason": "tool_use",
                "usage": {"input_tokens": 10, "output_tokens": 5},
            })
        return _FakeResp({
            "content": [{"type": "text", "text": "Respuesta final OK"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 8, "output_tokens": 4},
        })


@pytest.mark.anyio
async def test_loop_no_reenvia_bloques_vacios(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(am.httpx, "AsyncClient", lambda *a, **k: fake)

    async def _fake_tool(name, args, db, current_user):
        return json.dumps({"ok": True})

    monkeypatch.setattr(am, "execute_tool_asistente", _fake_tool)

    res = await am.chat_con_asistente(
        mensajes=[{"role": "user", "content": "hola"}],
        db=None,
        current_user=None,
        api_key="sk-test",
        modelo="claude-test",
    )

    assert res["respuesta"] == "Respuesta final OK"
    assert not res.get("error")

    # El 2º request (tras el tool) NO debe contener ningún bloque
    # text vacío en su historial de mensajes.
    segundo_body = fake.requests[1]
    for msg in segundo_body["messages"]:
        cont = msg["content"]
        if isinstance(cont, list):
            for b in cont:
                if isinstance(b, dict) and b.get("type") == "text":
                    assert b.get("text", "").strip() != "", (
                        "Se reenvió un bloque de texto vacío a Anthropic"
                    )


@pytest.fixture
def anyio_backend():
    return "asyncio"
