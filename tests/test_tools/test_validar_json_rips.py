"""Tests del validador de paquetes FEV-RIPS (tools/validar_json_rips.py).

Cubre: lectura del XML AttachedDocument (factura incrustada en CDATA),
campos obligatorios en null, coherencia tipoNota/numNota, tablas de
referencia, cruce del numero de factura con y sin prefijo, periodo de
facturacion contra la fecha de atencion, suma de valores y el CLI.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# El script vive en tools/ (sin __init__.py): lo importamos por ruta.
_TOOLS = Path(__file__).resolve().parent.parent.parent / "tools"
sys.path.insert(0, str(_TOOLS))

import validar_json_rips as val  # noqa: E402

INVOICE = """<?xml version="1.0" encoding="utf-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
 xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2">
  <ext:UBLExtensions>
    <ext:UBLExtension>
      <ext:ExtensionContent>
        <CustomTagGeneral>
          <Interoperabilidad>
            <Group schemeName="Sector Salud">
              <Collection schemeName="Usuario">
                <AdditionalInformation>
                  <Name>CODIGO_PRESTADOR</Name>
                  <Value>{cod_prestador}</Value>
                </AdditionalInformation>
              </Collection>
            </Group>
          </Interoperabilidad>
        </CustomTagGeneral>
      </ext:ExtensionContent>
    </ext:UBLExtension>
  </ext:UBLExtensions>
  <cbc:ID>{num}</cbc:ID>
  <cbc:UUID schemeID="1" schemeName="CUFE-SHA384">abc123</cbc:UUID>
  <cbc:IssueDate>2026-08-01</cbc:IssueDate>
  <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
  <cac:InvoicePeriod>
    <cbc:StartDate>{inicio}</cbc:StartDate>
    <cbc:EndDate>{fin}</cbc:EndDate>
  </cac:InvoicePeriod>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyTaxScheme>
        <cbc:CompanyID schemeID="3" schemeName="31">{nit}</cbc:CompanyID>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyTaxScheme>
        <cbc:CompanyID schemeID="0" schemeName="13">1100917538</cbc:CompanyID>
      </cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal>
    <cbc:LineExtensionAmount currencyID="COP">{valor}</cbc:LineExtensionAmount>
  </cac:LegalMonetaryTotal>
</Invoice>"""

ATTACHED = """<?xml version="1.0" encoding="utf-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
 xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
 xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:ParentDocumentID>{num}</cbc:ParentDocumentID>
  <cac:Attachment>
    <cac:ExternalReference>
      <cbc:Description><![CDATA[{invoice}]]></cbc:Description>
    </cac:ExternalReference>
  </cac:Attachment>
</AttachedDocument>"""


def _xml(
    tmp_path: Path,
    num: str = "MED737",
    inicio: str = "2026-07-31",
    fin: str = "2026-07-31",
    nit: str = "900299334",
    valor: str = "180000.00",
    adjunto: bool = True,
    cod_prestador: str = "6800103933",
) -> Path:
    """Escribe un XML de factura (por defecto, AttachedDocument como el real)."""
    invoice = INVOICE.format(
        num=num, inicio=inicio, fin=fin, nit=nit, valor=valor, cod_prestador=cod_prestador
    )
    contenido = ATTACHED.format(num=num, invoice=invoice) if adjunto else invoice
    ruta = tmp_path / "factura.xml"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def _consulta(**cambios) -> dict:
    base = {
        "codPrestador": "680010393301",
        "fechaInicioAtencion": "2026-07-31 16:00",
        "numAutorizacion": None,
        "codConsulta": "890201",
        "modalidadGrupoServicioTecSal": "01",
        "grupoServicios": "01",
        "codServicio": 328,
        "finalidadTecnologiaSalud": "44",
        "causaMotivoAtencion": "38",
        "codDiagnosticoPrincipal": "B351",
        "tipoDiagnosticoPrincipal": "01",
        "tipoDocumentoIdentificacion": "CC",
        "numDocumentoIdentificacion": "91276811",
        "vrServicio": 180000,
        "conceptoRecaudo": "05",
        "valorPagoModerador": 0,
        "numFEVPagoModerador": None,
        "consecutivo": 1,
    }
    base.update(cambios)
    return base


def _rips(consultas=None, **cambios) -> dict:
    base = {
        "numDocumentoIdObligado": "900299334",
        "numFactura": "MED737",
        "tipoNota": None,
        "numNota": None,
        "usuarios": [
            {
                "tipoDocumentoIdentificacion": "CC",
                "numDocumentoIdentificacion": "1100917538",
                "tipoUsuario": "12",
                "fechaNacimiento": "1976-03-31",
                "codSexo": "F",
                "codPaisResidencia": "170",
                "codMunicipioResidencia": "68001",
                "codZonaTerritorialResidencia": "02",
                "incapacidad": "NO",
                "codPaisOrigen": "170",
                "registroSIRAS": None,
                "consecutivo": 1,
                "servicios": {"consultas": consultas if consultas is not None else [_consulta()]},
            }
        ],
    }
    base.update(cambios)
    return base


def _json(tmp_path: Path, data: dict) -> Path:
    ruta = tmp_path / "RP_20260801145548.json"
    ruta.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return ruta


def _errores(hallazgos) -> list[str]:
    return [h.campo for h in hallazgos if h.nivel == "ERROR"]


# --------------------------------------------------------------------------
# Lectura del XML
# --------------------------------------------------------------------------


def test_lee_factura_incrustada_en_attached_document(tmp_path):
    """El XML real trae la factura dentro de un CDATA: hay que desempaquetarla."""
    datos = val.datos_factura(_xml(tmp_path))
    assert datos["num_factura"] == "MED737"
    assert datos["nit_prestador"] == "900299334"
    assert datos["periodo_inicio"] == "2026-07-31"
    assert datos["periodo_fin"] == "2026-07-31"
    assert datos["valor_bruto"] == "180000.00"


def test_lee_factura_suelta(tmp_path):
    datos = val.datos_factura(_xml(tmp_path, adjunto=False))
    assert datos["num_factura"] == "MED737"


def test_xml_ilegible_no_revienta(tmp_path):
    ruta = tmp_path / "roto.xml"
    ruta.write_text("<Invoice><sin cerrar>", encoding="utf-8")
    assert val.datos_factura(ruta) == {}


# --------------------------------------------------------------------------
# Estructura del JSON
# --------------------------------------------------------------------------


def test_paquete_correcto_no_tiene_hallazgos(tmp_path):
    hallazgos, _ = val.validar_paquete(_json(tmp_path, _rips()), _xml(tmp_path))
    assert hallazgos == []


def test_modalidad_en_null_es_error(tmp_path):
    """El rechazo RVG01 'Dato requerido' que devuelve el validador MinSalud."""
    data = _rips(consultas=[_consulta(modalidadGrupoServicioTecSal=None)])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    campos = _errores(hallazgos)
    assert "usuarios[0].servicios.consultas[0].modalidadGrupoServicioTecSal" in campos
    ayuda = next(h.solucion for h in hallazgos if h.campo.endswith("modalidadGrupoServicioTecSal"))
    assert "01" in ayuda


def test_modalidad_fuera_de_tabla_es_error(tmp_path):
    data = _rips(consultas=[_consulta(modalidadGrupoServicioTecSal="99")])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    assert "usuarios[0].servicios.consultas[0].modalidadGrupoServicioTecSal" in _errores(hallazgos)


@pytest.mark.parametrize(
    "campo", ["codPrestador", "codConsulta", "vrServicio", "codDiagnosticoPrincipal"]
)
def test_otros_campos_obligatorios_en_null(tmp_path, campo):
    data = _rips(consultas=[_consulta(**{campo: None})])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    assert f"usuarios[0].servicios.consultas[0].{campo}" in _errores(hallazgos)


def test_campo_obligatorio_del_usuario_en_null(tmp_path):
    data = _rips()
    data["usuarios"][0]["codZonaTerritorialResidencia"] = None
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    assert "usuarios[0].codZonaTerritorialResidencia" in _errores(hallazgos)


def test_num_nota_sin_tipo_nota_es_error(tmp_path):
    """En una factura de venta los dos campos de nota van en null."""
    data = _rips(numNota="2")
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    assert "numNota" in _errores(hallazgos)


def test_tipo_nota_sin_num_nota_es_error(tmp_path):
    data = _rips(tipoNota="NC")
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    assert "numNota" in _errores(hallazgos)


def test_nota_credito_bien_diligenciada_no_es_error(tmp_path):
    data = _rips(tipoNota="NC", numNota="NC123")
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    assert _errores(hallazgos) == []


def test_fecha_con_formato_invalido(tmp_path):
    data = _rips(consultas=[_consulta(fechaInicioAtencion="31/07/2026 16:00")])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    assert "usuarios[0].servicios.consultas[0].fechaInicioAtencion" in _errores(hallazgos)


def test_pago_moderador_incoherente_es_aviso(tmp_path):
    data = _rips(consultas=[_consulta(conceptoRecaudo="05", valorPagoModerador=5000)])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    avisos = [h.campo for h in hallazgos if h.nivel == "AVISO"]
    assert "usuarios[0].servicios.consultas[0].valorPagoModerador" in avisos


# --------------------------------------------------------------------------
# Cruce JSON <-> XML
# --------------------------------------------------------------------------


def test_factura_sin_prefijo_es_error_y_sugiere_el_numero_real(tmp_path):
    hallazgos, _ = val.validar_paquete(_json(tmp_path, _rips(numFactura="737")), _xml(tmp_path))
    assert "numFactura" in _errores(hallazgos)
    hallazgo = next(h for h in hallazgos if h.campo == "numFactura")
    assert "prefijo" in hallazgo.detalle
    assert "MED737" in hallazgo.solucion


def test_nit_distinto_al_de_la_factura(tmp_path):
    hallazgos, _ = val.validar_paquete(
        _json(tmp_path, _rips(numDocumentoIdObligado="800123456")), _xml(tmp_path)
    )
    assert "numDocumentoIdObligado" in _errores(hallazgos)


def test_atencion_fuera_del_periodo_de_facturacion(tmp_path):
    data = _rips(consultas=[_consulta(fechaInicioAtencion="2026-07-27 16:00")])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    campo = "usuarios[0].servicios.consultas[0].fechaInicioAtencion"
    assert campo in _errores(hallazgos)


def test_atencion_dentro_de_un_periodo_amplio(tmp_path):
    data = _rips(consultas=[_consulta(fechaInicioAtencion="2026-07-27 16:00")])
    ruta_xml = _xml(tmp_path, inicio="2026-07-01", fin="2026-07-31")
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), ruta_xml)
    assert _errores(hallazgos) == []


def test_lee_el_codigo_prestador_del_bloque_de_interoperabilidad(tmp_path):
    datos = val.datos_factura(_xml(tmp_path))
    assert datos["codigo_prestador"] == "6800103933"


def test_codigo_prestador_de_12_en_el_xml_es_el_rechazo_rvc011(tmp_path):
    """El caso real de la MED737: el facturador puso el codigo de sede en la FEV."""
    ruta_xml = _xml(tmp_path, cod_prestador="680010393301")
    hallazgos, _ = val.validar_paquete(_json(tmp_path, _rips()), ruta_xml)
    assert "CODIGO_PRESTADOR (XML)" in _errores(hallazgos)
    hallazgo = next(h for h in hallazgos if h.campo == "CODIGO_PRESTADOR (XML)")
    assert "RVC011" in hallazgo.detalle
    # La salida tiene que decir el numero correcto y quien lo corrige.
    assert "6800103933" in hallazgo.solucion
    assert "reexpedir" in hallazgo.solucion


def test_cod_prestador_del_rips_debe_tener_12(tmp_path):
    """El RIPS lleva el codigo de la sede; con 10 el validador rechaza (RVG01)."""
    data = _rips(consultas=[_consulta(codPrestador="6800103933")])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    campo = "usuarios[0].servicios.consultas[0].codPrestador"
    assert campo in _errores(hallazgos)
    hallazgo = next(h for h in hallazgos if h.campo == campo)
    assert "12" in hallazgo.detalle


def test_prestador_del_rips_distinto_al_de_la_factura(tmp_path):
    data = _rips(consultas=[_consulta(codPrestador="680019999901")])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    assert "usuarios[0].servicios.consultas[0].codPrestador" in _errores(hallazgos)


def test_prestador_coherente_no_genera_hallazgo(tmp_path):
    """XML con 10 y RIPS con esos mismos 10 + la sede: correcto."""
    hallazgos, _ = val.validar_paquete(_json(tmp_path, _rips()), _xml(tmp_path))
    assert _errores(hallazgos) == []


def test_xml_sin_bloque_de_interoperabilidad_no_revienta(tmp_path):
    ruta_xml = _xml(tmp_path, cod_prestador="")
    hallazgos, _ = val.validar_paquete(_json(tmp_path, _rips()), ruta_xml)
    assert _errores(hallazgos) == []


def test_suma_de_servicios_distinta_al_valor_facturado(tmp_path):
    data = _rips(consultas=[_consulta(vrServicio=90000)])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), _xml(tmp_path))
    avisos = [h.campo for h in hallazgos if h.nivel == "AVISO"]
    assert "vrServicio" in avisos


def test_sin_xml_avisa_pero_revisa_estructura(tmp_path):
    data = _rips(consultas=[_consulta(modalidadGrupoServicioTecSal=None)])
    hallazgos, _ = val.validar_paquete(_json(tmp_path, data), None)
    assert "xml" in [h.campo for h in hallazgos if h.nivel == "AVISO"]
    assert "usuarios[0].servicios.consultas[0].modalidadGrupoServicioTecSal" in _errores(hallazgos)


def test_json_ilegible_reporta_error_claro(tmp_path):
    ruta = tmp_path / "malo.json"
    ruta.write_text('{"numFactura": "MED737",}', encoding="utf-8")
    hallazgos, _ = val.validar_paquete(ruta, None)
    assert hallazgos[0].nivel == "ERROR"
    assert "No se pudo leer el JSON" in hallazgos[0].detalle


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def test_cli_carpeta_con_paquete_correcto(tmp_path, capsys):
    _xml(tmp_path)
    _json(tmp_path, _rips())
    assert val.main([str(tmp_path)]) == 0
    assert "SIN HALLAZGOS" in capsys.readouterr().out


def test_cli_devuelve_1_cuando_hay_errores(tmp_path, capsys):
    _xml(tmp_path)
    _json(tmp_path, _rips(consultas=[_consulta(modalidadGrupoServicioTecSal=None)]))
    assert val.main([str(tmp_path)]) == 1
    assert "NO va a generar el CUV" in capsys.readouterr().out


def test_cli_ignora_el_json_de_resultados_del_validador(tmp_path, capsys):
    """ResultadosDoker_*.json es la respuesta de MinSalud, no un RIPS."""
    _xml(tmp_path)
    _json(tmp_path, _rips())
    (tmp_path / "ResultadosDoker_737.json").write_text("{}", encoding="utf-8")
    assert val.main([str(tmp_path)]) == 0
    assert "Revisados 1 paquete(s)" in capsys.readouterr().out


def test_cli_recursivo_y_reporte_csv(tmp_path):
    for nombre in ("FV737", "FV738"):
        carpeta = tmp_path / nombre
        carpeta.mkdir()
        _xml(carpeta)
        _json(carpeta, _rips(numFactura="737"))
    reporte = tmp_path / "hallazgos.csv"
    assert val.main([str(tmp_path), "--recursivo", "--reporte", str(reporte)]) == 1
    contenido = reporte.read_text(encoding="utf-8-sig")
    assert contenido.count("numFactura") >= 2


def test_cli_sin_argumentos_devuelve_2(capsys):
    assert val.main([]) == 2


def test_cli_carpeta_inexistente_devuelve_2(tmp_path, capsys):
    assert val.main([str(tmp_path / "no_existe")]) == 2
