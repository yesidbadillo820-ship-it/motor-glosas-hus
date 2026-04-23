"""Tests del skeleton de multi-tenancy (Ronda 14)."""
from types import SimpleNamespace

from app.services.tenancy import (
    TENANT_DEFAULT,
    get_tenant_id,
    info_tenant,
    resolver_tenant_desde_request,
    set_tenant_id,
)


def test_default_tenant_es_HUS():
    assert get_tenant_id() == "HUS"


def test_set_tenant_persiste_en_contexto():
    set_tenant_id("DEMO")
    assert get_tenant_id() == "DEMO"
    # Reset para no afectar otros tests
    set_tenant_id("HUS")


def test_info_tenant_hus():
    info = info_tenant("HUS")
    assert "SANTANDER" in info["nombre"].upper()
    assert info["nit"] == "900006037-4"


def test_info_tenant_desconocido_cae_a_default():
    info = info_tenant("INEXISTENTE")
    # Degrada a HUS
    assert "SANTANDER" in info["nombre"].upper()


def test_resolver_header_x_tenant():
    req = SimpleNamespace(
        headers={"x-tenant-id": "DEMO"},
        query_params={},
    )
    assert resolver_tenant_desde_request(req) == "DEMO"


def test_resolver_query_param():
    req = SimpleNamespace(
        headers={"host": "ia-glosas.com"},
        query_params={"tenant": "demo"},
    )
    assert resolver_tenant_desde_request(req) == "DEMO"


def test_resolver_subdominio():
    req = SimpleNamespace(
        headers={"host": "hus.ia-glosas.com"},
        query_params={},
    )
    assert resolver_tenant_desde_request(req) == "HUS"


def test_resolver_sin_info_usa_default():
    req = SimpleNamespace(headers={}, query_params={})
    assert resolver_tenant_desde_request(req) == TENANT_DEFAULT
