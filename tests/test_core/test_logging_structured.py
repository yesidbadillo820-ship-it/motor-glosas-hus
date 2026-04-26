"""Tests del StructuredFormatter (R80 P1)."""
from __future__ import annotations

import json
import logging

from app.core.logging_utils import (
    StructuredFormatter,
    glosa_id_var,
    user_email_var,
)


def _crear_record(msg="test"):
    return logging.LogRecord(
        name="test", level=logging.INFO, pathname="x", lineno=1,
        msg=msg, args=(), exc_info=None,
    )


def test_formatter_incluye_campos_basicos():
    f = StructuredFormatter()
    rec = _crear_record("hello")
    out = json.loads(f.format(rec))
    assert out["message"] == "hello"
    assert out["level"] == "INFO"
    assert "timestamp" in out
    assert "request_id" in out


def test_formatter_emite_glosa_id_si_set():
    """REGRESIÓN R80 P1: si glosa_id_var tiene valor, debe aparecer
    en el log JSON."""
    f = StructuredFormatter()
    tok = glosa_id_var.set(42)
    try:
        out = json.loads(f.format(_crear_record("x")))
        assert out["glosa_id"] == 42
    finally:
        glosa_id_var.reset(tok)


def test_formatter_emite_user_email_si_set():
    f = StructuredFormatter()
    tok = user_email_var.set("auditor@hus.com")
    try:
        out = json.loads(f.format(_crear_record("x")))
        assert out["user_email"] == "auditor@hus.com"
    finally:
        user_email_var.reset(tok)


def test_formatter_omite_glosa_id_si_none():
    """Sin glosa_id en context → no aparece la key (evita ruido)."""
    f = StructuredFormatter()
    tok = glosa_id_var.set(None)
    try:
        out = json.loads(f.format(_crear_record("x")))
        assert "glosa_id" not in out
    finally:
        glosa_id_var.reset(tok)


def test_formatter_omite_user_email_si_vacio():
    f = StructuredFormatter()
    tok = user_email_var.set("")
    try:
        out = json.loads(f.format(_crear_record("x")))
        assert "user_email" not in out
    finally:
        user_email_var.reset(tok)
