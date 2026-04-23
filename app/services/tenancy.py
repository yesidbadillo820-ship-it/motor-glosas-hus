"""Multi-tenancy (Ronda 14) — skeleton para escalamiento SaaS.

El sistema actual es single-tenant (solo HUS). Esta capa prepara el
terreno para vender el mismo sistema como SaaS a múltiples hospitales
sin duplicar infraestructura.

Estrategia pragmática: column-based multi-tenancy (un solo BD con
columna `tenant_id` en todas las tablas relevantes). Es la que mejor
encaja con SQLAlchemy y permite migración gradual.

Fases:
  1. NOW (este commit): definir `TenantRecord` + helper `get_tenant_id()`
     que por defecto retorna `"HUS"` para mantener compat.
  2. Futuro: migración que agrega `tenant_id VARCHAR(20) DEFAULT 'HUS'`
     a GlosaRecord, UsuarioRecord, ContratoRecord, etc.
  3. Query filter automático vía SQLAlchemy event o scoped session que
     agrega `where tenant_id = current_tenant` a todas las consultas.
  4. Login pide tenant_id (subdominio HUS.ia-glosas.com o query ?org=HUS).

Este módulo expone la API mínima que el resto del código puede empezar a
usar desde ya, sin disrupción.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional


# Contexto por request: cada llamada al API setea su tenant vía middleware
_tenant_actual: ContextVar[Optional[str]] = ContextVar("tenant_actual", default=None)

TENANT_DEFAULT = "HUS"


def get_tenant_id() -> str:
    """Retorna el tenant activo en el request actual.

    Si no hay tenant seteado (ej. endpoints públicos, tests), retorna
    TENANT_DEFAULT ('HUS') para mantener compatibilidad con el sistema
    single-tenant actual.
    """
    t = _tenant_actual.get()
    return t or TENANT_DEFAULT


def set_tenant_id(tenant: str) -> None:
    """Setea el tenant para este contexto (middleware lo llama al inicio
    de cada request)."""
    _tenant_actual.set((tenant or TENANT_DEFAULT).upper())


# Catálogo de tenants conocidos — cuando crezca a BD, mudamos a
# TenantRecord + query. Por ahora dict hardcoded.
TENANTS_CONOCIDOS: dict[str, dict] = {
    "HUS": {
        "nombre": "ESE Hospital Universitario de Santander",
        "nit": "900006037-4",
        "direccion": "Carrera 33 No. 28-126, Bucaramanga",
        "telefono": "(607) 691 2010",
        "activo": True,
        "subdominio": "hus",
    },
    "DEMO": {
        "nombre": "Hospital Demo (pruebas)",
        "nit": "000000000",
        "direccion": "—",
        "telefono": "—",
        "activo": True,
        "subdominio": "demo",
    },
}


def info_tenant(tenant_id: Optional[str] = None) -> dict:
    """Datos del tenant (nombre, NIT, dirección). Usado para branding
    en PDFs, dictámenes y emails."""
    tid = (tenant_id or get_tenant_id()).upper()
    return TENANTS_CONOCIDOS.get(tid, TENANTS_CONOCIDOS[TENANT_DEFAULT])


def resolver_tenant_desde_request(request) -> str:
    """Extrae el tenant del request. Prioridad:
      1. header X-Tenant-ID
      2. query param ?tenant=XXX
      3. subdominio (host tipo 'hus.ia-glosas.com' → 'hus')
      4. default HUS
    """
    try:
        # 1) Header explícito
        h = request.headers.get("x-tenant-id")
        if h:
            return h.upper().strip()
        # 2) Query param
        t = request.query_params.get("tenant")
        if t:
            return t.upper().strip()
        # 3) Subdominio
        host = (request.headers.get("host") or "").split(":")[0].lower()
        if host:
            parts = host.split(".")
            # 'hus.ia-glosas.com' → 'hus'
            if len(parts) >= 3:
                cand = parts[0]
                if cand not in ("www", "api", "app"):
                    return cand.upper()
    except Exception:
        pass
    return TENANT_DEFAULT
