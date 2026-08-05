"""Pruebas del sondeo de rutas de SIIFA.

Nace de un problema concreto (05-08-2026): las devoluciones que el hospital
aceptó se van con el código RE9701 y SIIFA las rechaza diciendo que el código
«no pertenece al grupo RESPUESTA». El código existe —el portal lo ofrece en
el desplegable de Responder Devolución—, así que lo que hay que averiguar es
por qué puerta se responde una devolución. Y hay que averiguarlo SIN escribir
nada en la plataforma del Ministerio.
"""

from __future__ import annotations

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS))

import siifa_sondear_endpoints as son  # noqa: E402


class ClienteFalso:
    """Contesta como SIIFA y deja ver qué se le pidió."""

    def __init__(self, rutas: dict[str, int], catalogos: dict[str, list] | None = None):
        self.rutas = rutas
        self.catalogos = catalogos or {}
        self.metodos: list[str] = []

    def sondear(self, ruta: str, method: str = "GET"):
        self.metodos.append(method)
        return self.rutas.get(ruta, 404), ""

    def catalogo_tipo_codigo(self, grupo: str) -> list:
        return self.catalogos.get(grupo, [])


def test_el_sondeo_no_escribe_nada_en_siifa():
    """La regla: averiguar sin tocar. Solo se consulta, nunca se manda."""
    cliente = ClienteFalso({})

    son.sondear(cliente)

    assert set(cliente.metodos) == {"GET"}


def test_una_ruta_que_existe_se_distingue_de_una_que_no():
    """405 es «existe pero con otro método»; 404 es que no está."""
    cliente = ClienteFalso(
        {
            "/api/SeguimientoFacturaGlosa/Respuesta": 405,
            "/api/SeguimientoFacturaDevolucion/Respuesta": 405,
        }
    )

    lineas = "\n".join(son.sondear(cliente))

    assert "EXISTE" in [line for line in lineas.splitlines() if "Devolucion/Respuesta" in line][0]
    assert (
        "NO existe" in [line for line in lineas.splitlines() if "SeguimientoDevolucion" in line][0]
    )


def test_se_prueba_la_ruta_de_devoluciones_y_la_que_usa_hoy_el_bot():
    """Sin la ruta de control no se sabe si el sondeo mismo sirve."""
    assert "/api/SeguimientoFacturaGlosa/Respuesta" in son.RUTAS
    assert "/api/SeguimientoFacturaDevolucion/Respuesta" in son.RUTAS


def test_el_catalogo_se_busca_tambien_por_el_grupo_de_devoluciones():
    cliente = ClienteFalso(
        {},
        {
            "RESPUESTA_DEVOLUCION": [
                {
                    "idSeguimientoTipoCodigo": "RE9701",
                    "descripcion": "La devolución ha sido aceptada al 100%.",
                }
            ]
        },
    )

    lineas = "\n".join(son.sondear(cliente))

    assert "RE9701" in lineas
    assert "aceptada al 100%" in lineas


def test_los_codigos_se_leen_aunque_la_api_los_nombre_distinto():
    cliente = ClienteFalso({}, {"DEVOLUCION": [{"codigo": "RE9701", "nombre": "aceptada"}]})

    lineas = "\n".join(son.sondear(cliente))

    assert "RE9701" in lineas
    assert "aceptada" in lineas


def test_los_campos_crudos_muestran_el_id_de_la_devolucion():
    """Sin ver los campos tal cual, el nombre del id de devolución es una adivinanza.

    Y con ese id se escribe en la plataforma: equivocarlo es dejar la
    respuesta del hospital puesta sobre otro registro.
    """

    class ClienteConSeguimientos(ClienteFalso):
        def listar_seguimientos(self, numero_factura=None):
            yield {
                "idSeguimientoFacturaDevolucion": 7788,
                "tipoSeguimiento": "DEVOLUCION",
                "factura": {"numeroFactura": numero_factura},
            }

    lineas = "\n".join(ver := son.ver_seguimiento_crudo(ClienteConSeguimientos({}), "HUS494196"))

    assert "idSeguimientoFacturaDevolucion" in lineas
    assert "7788" in lineas
    assert "DEVOLUCION" in lineas
    assert ver, "tiene que devolver algo que el auditor pueda mandar"


def test_si_la_factura_no_trae_seguimientos_se_dice_claro():
    class SinNada(ClienteFalso):
        def listar_seguimientos(self, numero_factura=None):
            return iter([])

    lineas = "\n".join(son.ver_seguimiento_crudo(SinNada({}), "HUS000000"))

    assert "no devolvió seguimientos" in lineas
