"""validar_json_rips.py — Revisa un paquete FEV-RIPS antes de subirlo a MinSalud.

Para que el Ministerio genere el **CUV**, el JSON de RIPS y el XML de la
factura electronica tienen que estar perfectos y ademas coincidir entre si.
El validador de escritorio del Ministerio solo avisa del primer problema de
estructura; los cruces contra la factura los descubre uno cuando ya envio el
paquete y le responde "Rechazado".

Este script hace las dos revisiones ANTES de subir nada:

  1. ESTRUCTURA  — que ningun campo obligatorio del JSON venga en null, que
                   las fechas tengan el formato correcto y que los codigos de
                   las tablas de referencia existan.
  2. CRUCE       — que el JSON y el XML de la factura hablen de lo mismo:
                   numero de factura (con prefijo), NIT del prestador,
                   documento del paciente, valores y periodo de facturacion.

USO RAPIDO
----------

    # Revisar una carpeta con el XML y el JSON juntos
    py validar_json_rips.py "C:\\Users\\casa\\Desktop\\FV737"

    # Revisar archivos sueltos
    py validar_json_rips.py --json "...\\RP_20260801145548.json" ^
                            --xml  "...\\ad09002993340082600000 2e1.xml"

    # Revisar varias carpetas de una vez (una carpeta por factura)
    py validar_json_rips.py "D:\\FEV\\AGOSTO" --recursivo

    # Guardar el reporte en CSV para adjuntarlo al soporte
    py validar_json_rips.py "D:\\FEV\\AGOSTO" --recursivo --reporte hallazgos.csv

CODIGOS DE SALIDA
-----------------
    0 → todo bien, el paquete puede subirse.
    1 → hay ERRORES (el Ministerio no va a generar el CUV).
    2 → problema de uso (no se encontraron archivos, JSON ilegible, etc).

Las ADVERTENCIAS no bloquean, pero conviene revisarlas: casi siempre son la
causa de un rechazo posterior en la plataforma de la EPS.

DEPENDENCIAS
------------
    Python 3.9+ (solo libreria estandar)
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------------
# Tablas de referencia (Resolucion 2275 de 2023 y sus anexos tecnicos)
# --------------------------------------------------------------------------

# Modalidad de prestacion del servicio de salud.
MODALIDAD_GRUPO_SERVICIO = {
    "01": "Intramural",
    "02": "Extramural - unidad movil",
    "03": "Extramural - domiciliaria",
    "04": "Extramural - jornada de salud",
    "05": "Extramural - atencion prehospitalaria o transporte asistencial",
    "06": "Telemedicina interactiva",
    "07": "Telemedicina no interactiva",
    "08": "Telemedicina telexperticia",
    "09": "Telemedicina telemonitoreo",
}

GRUPO_SERVICIOS = {
    "01": "Consulta externa",
    "02": "Apoyo diagnostico y complementacion terapeutica",
    "03": "Internacion",
    "04": "Quirurgico",
    "05": "Atencion inmediata",
}

CONCEPTO_RECAUDO = {
    "01": "Copago",
    "02": "Cuota moderadora",
    "03": "Cuota de recuperacion",
    "04": "Pagos compartidos en planes voluntarios de salud",
    "05": "No aplica",
}

TIPO_DIAGNOSTICO_PRINCIPAL = {
    "01": "Impresion diagnostica",
    "02": "Confirmado nuevo",
    "03": "Confirmado repetido",
}

TIPOS_NOTA = {"NC", "ND", "NA", "RS"}

# El mismo prestador se identifica con dos largos distintos segun el archivo:
#   - JSON de RIPS  -> 12 caracteres (codigo de habilitacion de la SEDE).
#   - XML de la FEV -> 10 caracteres (codigo del PRESTADOR, tabla IPSCodHabilitacion).
# Mezclarlos es la causa del rechazo RVC011.
LARGO_COD_PRESTADOR_RIPS = 12
LARGO_COD_PRESTADOR_FEV = 10

# --------------------------------------------------------------------------
# Campos obligatorios (no pueden venir en null) por tipo de registro
# --------------------------------------------------------------------------

OBLIGATORIOS_USUARIO = [
    "tipoDocumentoIdentificacion",
    "numDocumentoIdentificacion",
    "tipoUsuario",
    "fechaNacimiento",
    "codSexo",
    "codPaisResidencia",
    "codMunicipioResidencia",
    "codZonaTerritorialResidencia",
    "incapacidad",
    "codPaisOrigen",
    "consecutivo",
]

OBLIGATORIOS_SERVICIO = {
    "consultas": [
        "codPrestador",
        "fechaInicioAtencion",
        "codConsulta",
        "modalidadGrupoServicioTecSal",
        "grupoServicios",
        "codServicio",
        "finalidadTecnologiaSalud",
        "causaMotivoAtencion",
        "codDiagnosticoPrincipal",
        "tipoDiagnosticoPrincipal",
        "tipoDocumentoIdentificacion",
        "numDocumentoIdentificacion",
        "vrServicio",
        "conceptoRecaudo",
        "valorPagoModerador",
        "consecutivo",
    ],
    "procedimientos": [
        "codPrestador",
        "fechaInicioAtencion",
        "codProcedimiento",
        "viaIngresoServicioSalud",
        "modalidadGrupoServicioTecSal",
        "grupoServicios",
        "codServicio",
        "finalidadTecnologiaSalud",
        "codDiagnosticoPrincipal",
        "tipoDocumentoIdentificacion",
        "numDocumentoIdentificacion",
        "vrServicio",
        "conceptoRecaudo",
        "valorPagoModerador",
        "consecutivo",
    ],
    "urgencias": [
        "codPrestador",
        "fechaInicioAtencion",
        "causaMotivoAtencion",
        "codDiagnosticoPrincipal",
        "condicionYDestinoUsuarioEgreso",
        "fechaEgreso",
        "consecutivo",
    ],
    "hospitalizacion": [
        "codPrestador",
        "viaIngresoServicioSalud",
        "fechaInicioAtencion",
        "causaMotivoAtencion",
        "codDiagnosticoPrincipal",
        "condicionYDestinoUsuarioEgreso",
        "fechaEgreso",
        "consecutivo",
    ],
    "medicamentos": [
        "codPrestador",
        "fechaDispensAdmon",
        "codDiagnosticoPrincipal",
        "tipoMedicamento",
        "codTecnologiaSalud",
        "nomTecnologiaSalud",
        "cantidadMedicamento",
        "tipoUnidadMedida",
        "tipoDocumentoIdentificacion",
        "numDocumentoIdentificacion",
        "vrUnitMedicamento",
        "vrServicio",
        "conceptoRecaudo",
        "valorPagoModerador",
        "consecutivo",
    ],
    "otrosServicios": [
        "codPrestador",
        "fechaSuministroTecnologia",
        "tipoOS",
        "codTecnologiaSalud",
        "nomTecnologiaSalud",
        "cantidadOS",
        "tipoDocumentoIdentificacion",
        "numDocumentoIdentificacion",
        "vrUnitOS",
        "vrServicio",
        "conceptoRecaudo",
        "valorPagoModerador",
        "consecutivo",
    ],
    "recienNacidos": [
        "codPrestador",
        "tipoDocumentoIdentificacion",
        "numDocumentoIdentificacion",
        "fechaNacimiento",
        "edadGestacional",
        "codSexoBiologico",
        "peso",
        "codDiagnosticoPrincipal",
        "condicionDestinoUsuarioEgreso",
        "fechaEgreso",
        "consecutivo",
    ],
}

# Campos de fecha y el formato que exige el anexo tecnico.
FECHAS_CON_HORA = {
    "fechaInicioAtencion",
    "fechaEgreso",
    "fechaSalida",
    "fechaDispensAdmon",
    "fechaSuministroTecnologia",
}
FECHAS_SIN_HORA = {"fechaNacimiento"}

RE_FECHA_HORA = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

NS = {
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
}


# --------------------------------------------------------------------------
# Hallazgos
# --------------------------------------------------------------------------


class Hallazgo:
    """Un problema encontrado en el paquete."""

    def __init__(self, nivel: str, campo: str, detalle: str, solucion: str = ""):
        self.nivel = nivel  # ERROR | AVISO
        self.campo = campo
        self.detalle = detalle
        self.solucion = solucion

    def __str__(self) -> str:
        marca = "ERROR" if self.nivel == "ERROR" else "AVISO"
        texto = f"  [{marca}] {self.campo}\n         {self.detalle}"
        if self.solucion:
            texto += f"\n         -> {self.solucion}"
        return texto


# --------------------------------------------------------------------------
# Lectura del XML de la factura electronica
# --------------------------------------------------------------------------


def _texto(nodo: ET.Element | None) -> str:
    return (nodo.text or "").strip() if nodo is not None else ""


def extraer_invoice(ruta_xml: Path) -> ET.Element | None:
    """Devuelve el nodo <Invoice>.

    El XML que entrega el facturador suele ser un AttachedDocument: la factura
    real viene incrustada como texto dentro de <cbc:Description>. Aqui se
    desempaqueta ese contenido para poder leerla.
    """
    try:
        raiz = ET.parse(ruta_xml).getroot()
    except ET.ParseError:
        return None

    if raiz.tag.endswith("}Invoice") or raiz.tag == "Invoice":
        return raiz

    for desc in raiz.iter(f"{{{NS['cbc']}}}Description"):
        contenido = (desc.text or "").strip()
        if "<Invoice" not in contenido:
            continue
        try:
            return ET.fromstring(contenido)
        except ET.ParseError:
            continue
    return None


def codigo_prestador_xml(invoice: ET.Element) -> str:
    """Lee el CODIGO_PRESTADOR del bloque de interoperabilidad del sector salud.

    Vive en ext:UBLExtensions > CustomTagGeneral > Interoperabilidad, como un
    par <Name>CODIGO_PRESTADOR</Name> / <Value>...</Value>. Es el campo que el
    Ministerio compara contra la tabla de habilitacion (rechazo RVC011).
    """
    for nodo in invoice.iter():
        if not nodo.tag.endswith("AdditionalInformation"):
            continue
        nombre = ""
        valor = ""
        for hijo in nodo:
            etiqueta = hijo.tag.split("}")[-1]
            if etiqueta == "Name":
                nombre = (hijo.text or "").strip()
            elif etiqueta == "Value":
                valor = (hijo.text or "").strip()
        if nombre == "CODIGO_PRESTADOR":
            return valor
    return ""


def datos_factura(ruta_xml: Path) -> dict:
    """Saca del XML los datos que el Ministerio cruza contra el JSON."""
    invoice = extraer_invoice(ruta_xml)
    if invoice is None:
        return {}

    proveedor = invoice.find("cac:AccountingSupplierParty//cac:PartyTaxScheme", NS)
    cliente = invoice.find("cac:AccountingCustomerParty//cac:PartyTaxScheme", NS)
    periodo = invoice.find("cac:InvoicePeriod", NS)
    totales = invoice.find("cac:LegalMonetaryTotal", NS)

    return {
        "num_factura": _texto(invoice.find("cbc:ID", NS)),
        "cufe": _texto(invoice.find("cbc:UUID", NS)),
        "fecha_emision": _texto(invoice.find("cbc:IssueDate", NS)),
        "tipo_documento": _texto(invoice.find("cbc:InvoiceTypeCode", NS)),
        "nit_prestador": _texto(
            proveedor.find("cbc:CompanyID", NS) if proveedor is not None else None
        ),
        "doc_adquiriente": _texto(
            cliente.find("cbc:CompanyID", NS) if cliente is not None else None
        ),
        "periodo_inicio": _texto(
            periodo.find("cbc:StartDate", NS) if periodo is not None else None
        ),
        "periodo_fin": _texto(periodo.find("cbc:EndDate", NS) if periodo is not None else None),
        "valor_bruto": _texto(
            totales.find("cbc:LineExtensionAmount", NS) if totales is not None else None
        ),
        "codigo_prestador": codigo_prestador_xml(invoice),
    }


# --------------------------------------------------------------------------
# Revision de estructura del JSON
# --------------------------------------------------------------------------


def _falta(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and not valor.strip())


def revisar_fecha(campo: str, valor: Any, ubicacion: str) -> list[Hallazgo]:
    if _falta(valor) or not isinstance(valor, str):
        return []
    if campo in FECHAS_CON_HORA and not RE_FECHA_HORA.match(valor):
        return [
            Hallazgo(
                "ERROR",
                f"{ubicacion}.{campo}",
                f"La fecha '{valor}' no tiene el formato que exige el Ministerio.",
                "Debe escribirse como AAAA-MM-DD HH:MM (ejemplo: 2026-07-31 16:00).",
            )
        ]
    if campo in FECHAS_SIN_HORA and not RE_FECHA.match(valor):
        return [
            Hallazgo(
                "ERROR",
                f"{ubicacion}.{campo}",
                f"La fecha '{valor}' no tiene el formato que exige el Ministerio.",
                "Debe escribirse como AAAA-MM-DD (ejemplo: 1976-03-31).",
            )
        ]
    return []


def revisar_codigos(servicio: dict, ubicacion: str) -> list[Hallazgo]:
    """Revisa los codigos contra las tablas de referencia."""
    hallazgos: list[Hallazgo] = []
    tablas = [
        ("modalidadGrupoServicioTecSal", MODALIDAD_GRUPO_SERVICIO),
        ("grupoServicios", GRUPO_SERVICIOS),
        ("conceptoRecaudo", CONCEPTO_RECAUDO),
        ("tipoDiagnosticoPrincipal", TIPO_DIAGNOSTICO_PRINCIPAL),
    ]
    for campo, tabla in tablas:
        valor = servicio.get(campo)
        if _falta(valor):
            continue
        if str(valor) not in tabla:
            opciones = ", ".join(f"{k} ({v})" for k, v in tabla.items())
            hallazgos.append(
                Hallazgo(
                    "ERROR",
                    f"{ubicacion}.{campo}",
                    f"El codigo '{valor}' no existe en la tabla de referencia.",
                    f"Valores validos: {opciones}.",
                )
            )
    return hallazgos


def revisar_servicio(tipo: str, servicio: dict, ubicacion: str) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []
    for campo in OBLIGATORIOS_SERVICIO.get(tipo, []):
        if _falta(servicio.get(campo)):
            solucion = ""
            if campo == "modalidadGrupoServicioTecSal":
                solucion = (
                    "Para una atencion presencial en la sede va '01' (Intramural); "
                    "si fue por telemedicina interactiva, '06'."
                )
            elif campo == "grupoServicios":
                solucion = "Para consulta externa va '01'."
            hallazgos.append(
                Hallazgo(
                    "ERROR",
                    f"{ubicacion}.{campo}",
                    "Campo obligatorio que viene vacio (null). "
                    "El Ministerio lo rechaza con 'Dato requerido'.",
                    solucion,
                )
            )
    for campo in FECHAS_CON_HORA | FECHAS_SIN_HORA:
        if campo in servicio:
            hallazgos.extend(revisar_fecha(campo, servicio[campo], ubicacion))
    hallazgos.extend(revisar_codigos(servicio, ubicacion))

    # En el JSON el codigo va completo: prestador (10) + sede (2) = 12.
    cod = servicio.get("codPrestador")
    if isinstance(cod, str) and cod.strip() and len(cod.strip()) != LARGO_COD_PRESTADOR_RIPS:
        hallazgos.append(
            Hallazgo(
                "ERROR",
                f"{ubicacion}.codPrestador",
                f"El codigo tiene {len(cod.strip())} caracteres y en el RIPS debe tener "
                f"{LARGO_COD_PRESTADOR_RIPS}.",
                "Es el codigo de habilitacion de la SEDE: municipio (5) + prestador (5) + "
                "sede (2). Se consulta en REPS con el NIT.",
            )
        )

    # El valor del pago moderador tiene que ser coherente con el concepto.
    concepto = servicio.get("conceptoRecaudo")
    moderador = servicio.get("valorPagoModerador")
    if concepto == "05" and isinstance(moderador, (int, float)) and moderador > 0:
        hallazgos.append(
            Hallazgo(
                "AVISO",
                f"{ubicacion}.valorPagoModerador",
                "El concepto de recaudo dice 'No aplica' (05) pero hay un valor "
                f"de pago moderador de {moderador}.",
                "O se pone el concepto real (copago/cuota moderadora) o el valor va en 0.",
            )
        )
    return hallazgos


def revisar_estructura(data: dict) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []

    if _falta(data.get("numDocumentoIdObligado")):
        hallazgos.append(
            Hallazgo(
                "ERROR",
                "numDocumentoIdObligado",
                "Falta el NIT del prestador que factura.",
            )
        )

    tipo_nota = data.get("tipoNota")
    num_nota = data.get("numNota")
    if _falta(tipo_nota) and not _falta(num_nota):
        hallazgos.append(
            Hallazgo(
                "ERROR",
                "numNota",
                f"Viene un numero de nota ('{num_nota}') pero 'tipoNota' esta vacio. "
                "En una factura de venta los dos campos van en null.",
                'Dejar "tipoNota": null y "numNota": null.',
            )
        )
    if not _falta(tipo_nota):
        if str(tipo_nota) not in TIPOS_NOTA:
            hallazgos.append(
                Hallazgo(
                    "ERROR",
                    "tipoNota",
                    f"El tipo de nota '{tipo_nota}' no es valido.",
                    f"Valores validos: {', '.join(sorted(TIPOS_NOTA))}.",
                )
            )
        if _falta(num_nota):
            hallazgos.append(
                Hallazgo(
                    "ERROR",
                    "numNota",
                    f"Se informo tipoNota '{tipo_nota}' pero no el numero de la nota.",
                )
            )

    usuarios = data.get("usuarios")
    if not isinstance(usuarios, list) or not usuarios:
        hallazgos.append(Hallazgo("ERROR", "usuarios", "El JSON no trae ningun usuario."))
        return hallazgos

    for i, usuario in enumerate(usuarios):
        ubic_u = f"usuarios[{i}]"
        for campo in OBLIGATORIOS_USUARIO:
            if _falta(usuario.get(campo)):
                hallazgos.append(
                    Hallazgo(
                        "ERROR",
                        f"{ubic_u}.{campo}",
                        "Campo obligatorio del usuario que viene vacio (null).",
                    )
                )
        hallazgos.extend(revisar_fecha("fechaNacimiento", usuario.get("fechaNacimiento"), ubic_u))

        servicios = usuario.get("servicios") or {}
        if not servicios:
            hallazgos.append(
                Hallazgo(
                    "ERROR",
                    f"{ubic_u}.servicios",
                    "El usuario no tiene ningun servicio registrado.",
                )
            )
            continue
        for tipo, registros in servicios.items():
            if not isinstance(registros, list):
                continue
            for j, servicio in enumerate(registros):
                hallazgos.extend(
                    revisar_servicio(tipo, servicio, f"{ubic_u}.servicios.{tipo}[{j}]")
                )
    return hallazgos


# --------------------------------------------------------------------------
# Cruce JSON <-> XML
# --------------------------------------------------------------------------


def _fechas_atencion(data: dict) -> Iterable[tuple[str, str]]:
    """Devuelve (ubicacion, fecha) de cada atencion del JSON."""
    for i, usuario in enumerate(data.get("usuarios") or []):
        for tipo, registros in (usuario.get("servicios") or {}).items():
            if not isinstance(registros, list):
                continue
            for j, servicio in enumerate(registros):
                for campo in (
                    "fechaInicioAtencion",
                    "fechaDispensAdmon",
                    "fechaSuministroTecnologia",
                ):
                    valor = servicio.get(campo)
                    if isinstance(valor, str) and valor.strip():
                        yield (f"usuarios[{i}].servicios.{tipo}[{j}].{campo}", valor)


def _codigos_prestador(data: dict) -> Iterable[tuple[str, str]]:
    """Devuelve (ubicacion, codPrestador) de cada servicio del JSON."""
    for i, usuario in enumerate(data.get("usuarios") or []):
        for tipo, registros in (usuario.get("servicios") or {}).items():
            if not isinstance(registros, list):
                continue
            for j, servicio in enumerate(registros):
                valor = servicio.get("codPrestador")
                if isinstance(valor, str) and valor.strip():
                    yield (
                        f"usuarios[{i}].servicios.{tipo}[{j}].codPrestador",
                        valor.strip(),
                    )


def revisar_cruce(data: dict, factura: dict) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []
    if not factura:
        return [
            Hallazgo(
                "AVISO",
                "factura",
                "No se pudo leer la factura del XML; no se hizo el cruce.",
            )
        ]

    num_json = str(data.get("numFactura") or "").strip()
    num_xml = factura["num_factura"]
    if num_json and num_xml and num_json != num_xml:
        detalle = (
            f"El JSON dice numero de factura '{num_json}' y la factura electronica es '{num_xml}'."
        )
        if num_xml.endswith(num_json):
            detalle += " Le falta el prefijo de la resolucion de facturacion."
        hallazgos.append(
            Hallazgo(
                "ERROR",
                "numFactura",
                detalle,
                f'Escribir "numFactura": "{num_xml}" tal como quedo radicada en la DIAN.',
            )
        )

    # Codigo de prestador: el XML lo lleva a 10 y el RIPS a 12. Si el facturador
    # puso el de 12 en el XML, el Ministerio rechaza con RVC011 y no hay nada que
    # corregir en el JSON: hay que reexpedir la factura.
    cod_xml = str(factura.get("codigo_prestador") or "").strip()
    if cod_xml:
        if len(cod_xml) != LARGO_COD_PRESTADOR_FEV:
            hallazgos.append(
                Hallazgo(
                    "ERROR",
                    "CODIGO_PRESTADOR (XML)",
                    f"En la factura el codigo tiene {len(cod_xml)} caracteres "
                    f"('{cod_xml}') y debe tener {LARGO_COD_PRESTADOR_FEV}. "
                    "Es el rechazo RVC011 del Ministerio.",
                    "El XML esta firmado y no se puede editar: facturacion debe reexpedir "
                    f"la factura con el codigo de prestador a {LARGO_COD_PRESTADOR_FEV} "
                    f"digitos ('{cod_xml[:LARGO_COD_PRESTADOR_FEV]}').",
                )
            )
        for ubicacion, cod_json in _codigos_prestador(data):
            if not cod_json or len(cod_json) < LARGO_COD_PRESTADOR_FEV:
                continue
            if cod_json[:LARGO_COD_PRESTADOR_FEV] != cod_xml[:LARGO_COD_PRESTADOR_FEV]:
                hallazgos.append(
                    Hallazgo(
                        "ERROR",
                        ubicacion,
                        f"El prestador del RIPS ('{cod_json}') y el de la factura "
                        f"('{cod_xml}') no son el mismo.",
                        "Los dos deben salir del mismo registro de REPS.",
                    )
                )

    nit_json = str(data.get("numDocumentoIdObligado") or "").strip()
    nit_xml = factura["nit_prestador"]
    if nit_json and nit_xml and nit_json != nit_xml:
        hallazgos.append(
            Hallazgo(
                "ERROR",
                "numDocumentoIdObligado",
                f"El NIT del JSON ('{nit_json}') no es el mismo de la factura ('{nit_xml}').",
            )
        )

    # Las atenciones tienen que caer dentro del periodo de facturacion del XML.
    inicio, fin = factura["periodo_inicio"], factura["periodo_fin"]
    if inicio and fin:
        for ubicacion, valor in _fechas_atencion(data):
            dia = valor[:10]
            if not RE_FECHA.match(dia):
                continue
            if dia < inicio or dia > fin:
                hallazgos.append(
                    Hallazgo(
                        "ERROR",
                        ubicacion,
                        f"La atencion es del {dia} pero la factura cubre el periodo "
                        f"{inicio} a {fin}.",
                        "O se corrige la fecha del servicio, o facturacion reexpide "
                        "la factura con el periodo real de la atencion.",
                    )
                )

    # Suma de los servicios contra el valor bruto de la factura.
    total_json = 0.0
    for usuario in data.get("usuarios") or []:
        for registros in (usuario.get("servicios") or {}).values():
            if not isinstance(registros, list):
                continue
            for servicio in registros:
                valor = servicio.get("vrServicio")
                if isinstance(valor, (int, float)):
                    total_json += float(valor)
    try:
        total_xml = float(factura["valor_bruto"])
    except (TypeError, ValueError):
        total_xml = None
    if total_xml is not None and abs(total_json - total_xml) > 0.5:
        hallazgos.append(
            Hallazgo(
                "AVISO",
                "vrServicio",
                f"Los servicios del JSON suman {total_json:,.0f} y la factura "
                f"registra {total_xml:,.0f}.",
                "Revisar que no falte o sobre un servicio en los RIPS.",
            )
        )

    return hallazgos


# --------------------------------------------------------------------------
# Recorrido de carpetas
# --------------------------------------------------------------------------


def buscar_paquetes(raiz: Path, recursivo: bool) -> list[tuple[Path, Path | None]]:
    """Devuelve pares (json, xml) de cada carpeta que tenga RIPS."""
    carpetas = [raiz]
    if recursivo:
        carpetas += [p for p in sorted(raiz.rglob("*")) if p.is_dir()]

    paquetes: list[tuple[Path, Path | None]] = []
    for carpeta in carpetas:
        jsons = [
            p
            for p in sorted(carpeta.glob("*.json"))
            if not p.name.lower().startswith(("resultadosdoker", "resultados_"))
        ]
        xmls = sorted(carpeta.glob("*.xml"))
        for ruta_json in jsons:
            paquetes.append((ruta_json, xmls[0] if xmls else None))
    return paquetes


def validar_paquete(ruta_json: Path, ruta_xml: Path | None) -> tuple[list[Hallazgo], dict]:
    try:
        data = json.loads(ruta_json.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return (
            [
                Hallazgo(
                    "ERROR",
                    ruta_json.name,
                    f"No se pudo leer el JSON: {exc}",
                    "Casi siempre es una coma de mas o un acento mal guardado. "
                    "Guardar el archivo como UTF-8.",
                )
            ],
            {},
        )

    hallazgos = revisar_estructura(data)
    factura = datos_factura(ruta_xml) if ruta_xml else {}
    if ruta_xml is None:
        hallazgos.append(
            Hallazgo(
                "AVISO",
                "xml",
                "No hay XML de la factura en la carpeta; no se pudo cruzar.",
                "El validador del Ministerio necesita el XML y el JSON juntos.",
            )
        )
    else:
        hallazgos.extend(revisar_cruce(data, factura))
    return hallazgos, factura


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Revisa el JSON de RIPS y el XML de la factura antes de "
        "subirlos al validador del Ministerio (CUV).",
    )
    parser.add_argument(
        "carpeta",
        nargs="?",
        help="Carpeta que contiene el XML y el JSON de la factura.",
    )
    parser.add_argument("--json", dest="ruta_json", help="Ruta del JSON de RIPS.")
    parser.add_argument("--xml", dest="ruta_xml", help="Ruta del XML de la factura.")
    parser.add_argument(
        "--recursivo",
        action="store_true",
        help="Revisar tambien las subcarpetas (una carpeta por factura).",
    )
    parser.add_argument("--reporte", help="Guardar los hallazgos en un CSV.")
    args = parser.parse_args(argv)

    if args.ruta_json:
        paquetes = [(Path(args.ruta_json), Path(args.ruta_xml) if args.ruta_xml else None)]
    elif args.carpeta:
        raiz = Path(args.carpeta)
        if not raiz.exists():
            print(f"No existe la carpeta: {raiz}")
            return 2
        paquetes = buscar_paquetes(raiz, args.recursivo)
    else:
        parser.print_help()
        return 2

    if not paquetes:
        print("No se encontro ningun JSON de RIPS para revisar.")
        return 2

    filas: list[dict] = []
    total_errores = 0
    total_avisos = 0

    for ruta_json, ruta_xml in paquetes:
        hallazgos, factura = validar_paquete(ruta_json, ruta_xml)
        errores = [h for h in hallazgos if h.nivel == "ERROR"]
        avisos = [h for h in hallazgos if h.nivel == "AVISO"]
        total_errores += len(errores)
        total_avisos += len(avisos)

        etiqueta = factura.get("num_factura") or ruta_json.stem
        print("=" * 72)
        print(f"FACTURA {etiqueta}")
        print(f"  JSON : {ruta_json}")
        print(f"  XML  : {ruta_xml if ruta_xml else '(no encontrado)'}")
        if not hallazgos:
            print("  SIN HALLAZGOS — el paquete puede subirse al validador.")
        else:
            for hallazgo in errores + avisos:
                print(hallazgo)
            resumen = f"  {len(errores)} error(es), {len(avisos)} advertencia(s)"
            if errores:
                resumen += " — el Ministerio NO va a generar el CUV asi."
            print(resumen)

        for hallazgo in hallazgos:
            filas.append(
                {
                    "factura": etiqueta,
                    "archivo_json": str(ruta_json),
                    "nivel": hallazgo.nivel,
                    "campo": hallazgo.campo,
                    "detalle": hallazgo.detalle,
                    "solucion": hallazgo.solucion,
                }
            )

    print("=" * 72)
    print(
        f"Revisados {len(paquetes)} paquete(s): "
        f"{total_errores} error(es) y {total_avisos} advertencia(s)."
    )

    if args.reporte:
        destino = Path(args.reporte)
        destino.parent.mkdir(parents=True, exist_ok=True)
        with destino.open("w", newline="", encoding="utf-8-sig") as fh:
            escritor = csv.DictWriter(
                fh,
                fieldnames=[
                    "factura",
                    "archivo_json",
                    "nivel",
                    "campo",
                    "detalle",
                    "solucion",
                ],
                delimiter=";",
            )
            escritor.writeheader()
            escritor.writerows(filas)
        print(f"Reporte guardado en: {destino}")

    return 1 if total_errores else 0


if __name__ == "__main__":
    sys.exit(main())
