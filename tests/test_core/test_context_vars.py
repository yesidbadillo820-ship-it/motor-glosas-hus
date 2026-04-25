"""Tests de los ContextVar request-scoped (R56 P1).

Garantizan:
  - defaults sensatos sin contaminación entre tests
  - propagación a tareas asyncio (importante para FastAPI)
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.logging_utils import (
    glosa_id_var,
    request_id_var,
    set_request_id,
    user_email_var,
)


class TestContextVars:
    def test_defaults_vacios(self):
        """Un test fresco no debe heredar valores de tests anteriores."""
        # Resetear con tokens propios para aislar
        tok_u = user_email_var.set("")
        tok_g = glosa_id_var.set(None)
        try:
            assert user_email_var.get() == ""
            assert glosa_id_var.get() is None
        finally:
            user_email_var.reset(tok_u)
            glosa_id_var.reset(tok_g)

    def test_set_y_get_user_email(self):
        tok = user_email_var.set("auditor@hus.com")
        try:
            assert user_email_var.get() == "auditor@hus.com"
        finally:
            user_email_var.reset(tok)

    def test_set_y_get_glosa_id(self):
        tok = glosa_id_var.set(42)
        try:
            assert glosa_id_var.get() == 42
        finally:
            glosa_id_var.reset(tok)

    def test_request_id_aislado_por_request(self):
        """request_id debe regenerarse cada vez que se llama set_request_id
        sin argumentos."""
        a = set_request_id()
        b = set_request_id()
        assert a != b
        # set_request_id con argumento debe respetarlo
        assert set_request_id("custom-id") == "custom-id"
        assert request_id_var.get() == "custom-id"

    @pytest.mark.asyncio
    async def test_propagacion_a_tareas_asincronas(self):
        """El ContextVar se propaga a sub-tareas async (importante porque
        FastAPI/asyncio crean tareas para cada request)."""
        tok = user_email_var.set("X@hus.com")
        try:
            async def _leer():
                return user_email_var.get()
            resultado = await _leer()
            assert resultado == "X@hus.com"
        finally:
            user_email_var.reset(tok)
