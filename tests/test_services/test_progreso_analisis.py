"""Tests para app.services.progreso_analisis — SSE progress."""

from __future__ import annotations

import asyncio

import pytest

from app.services.progreso_analisis import (
    _COLAS,
    cerrar_cola,
    obtener_cola,
    publicar,
)


@pytest.fixture(autouse=True)
def _limpiar_colas():
    """Limpia el dict global entre tests para evitar fugas."""
    _COLAS.clear()
    yield
    _COLAS.clear()


class TestObtenerCola:
    def test_crea_cola_nueva_si_no_existe(self):
        cola = obtener_cola("trace-1")
        assert isinstance(cola, asyncio.Queue)
        assert "trace-1" in _COLAS

    def test_devuelve_misma_cola_para_mismo_trace_id(self):
        c1 = obtener_cola("trace-x")
        c2 = obtener_cola("trace-x")
        assert c1 is c2

    def test_colas_distintas_para_traces_distintos(self):
        c1 = obtener_cola("trace-A")
        c2 = obtener_cola("trace-B")
        assert c1 is not c2


class TestCerrarCola:
    def test_quita_cola_del_dict(self):
        obtener_cola("trace-cerrar")
        assert "trace-cerrar" in _COLAS
        cerrar_cola("trace-cerrar")
        assert "trace-cerrar" not in _COLAS

    def test_idempotente_si_no_existe(self):
        # No debe levantar
        cerrar_cola("nunca-creado")


class TestPublicar:
    def test_publica_evento_en_cola_existente(self):
        cola = obtener_cola("trace-pub")
        publicar("trace-pub", "etapa1", {"k": "v"})
        assert cola.qsize() == 1
        msg = cola.get_nowait()
        assert msg["etapa"] == "etapa1"
        assert msg["datos"] == {"k": "v"}

    def test_sin_cola_no_falla(self):
        # Si nadie escucha, el evento se descarta silenciosamente
        publicar("trace-sin-listener", "etapa1", {"k": "v"})
        assert "trace-sin-listener" not in _COLAS

    def test_trace_id_vacio_es_noop(self):
        obtener_cola("trace-real")
        publicar("", "etapa1", {})
        # No se agregó nada a la cola real
        assert _COLAS["trace-real"].qsize() == 0

    def test_datos_default_es_dict_vacio(self):
        cola = obtener_cola("trace-d")
        publicar("trace-d", "etapa-sin-datos")
        msg = cola.get_nowait()
        assert msg["datos"] == {}

    def test_no_explota_si_cola_llena(self):
        cola = obtener_cola("trace-llena")
        # Llenar la cola al máximo
        for _ in range(cola.maxsize):
            cola.put_nowait({"etapa": "x", "datos": {}})
        # Esto debería ser no-op (cola.full() = True)
        publicar("trace-llena", "extra", {})
        assert cola.qsize() == cola.maxsize
