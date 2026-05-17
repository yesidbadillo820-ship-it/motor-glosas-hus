"""Tests del saneador de content para Anthropic (asistente maestro).

Cubren el bug "messages: text content blocks must be non-empty": ningún
bloque text vacío ni content string vacío debe enviarse a la API.
"""
from app.services.asistente_maestro import _sanear_content


def test_string_vacio_se_descarta():
    assert _sanear_content("") is None
    assert _sanear_content("   ") is None
    assert _sanear_content(None) is None


def test_string_valido_se_conserva():
    assert _sanear_content("hola") == "hola"


def test_bloque_text_vacio_se_elimina_pero_conserva_tool_use():
    content = [
        {"type": "text", "text": ""},
        {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
    ]
    out = _sanear_content(content)
    assert out == [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]


def test_lista_solo_con_text_vacio_devuelve_none():
    assert _sanear_content([{"type": "text", "text": "  "}]) is None


def test_tool_result_vacio_recibe_placeholder():
    out = _sanear_content([
        {"type": "tool_result", "tool_use_id": "a", "content": ""},
    ])
    assert out == [
        {"type": "tool_result", "tool_use_id": "a", "content": "(sin resultado)"},
    ]


def test_bloques_validos_se_conservan_intactos():
    content = [
        {"type": "text", "text": "respuesta"},
        {"type": "tool_use", "id": "t1", "name": "x", "input": {}},
    ]
    assert _sanear_content(content) == content
