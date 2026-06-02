"""rips_lectura.py — Lectura y normalización del RIPS JSON (estándar MSPS).

Módulo compartido por las herramientas ADRES. Sólo librería estándar
(json), para que corra en cualquier PC sin instalar nada.

Expone:
- cargar_rips(ruta) -> dict
- datos_generales(data) -> dict   (numFactura, NIT, usuarios)
- extraer_lineas_servicios(data) -> list[dict]   (una fila por servicio,
  con los campos normalizados que alimentan el FUR SERVICIOS)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# Tipos de servicio del RIPS que se vuelven líneas del FUR SERVICIOS
SERVICIOS_RIPS = (
    "consultas",
    "procedimientos",
    "medicamentos",
    "otrosServicios",
    "urgencias",
    "hospitalizacion",
    "recienNacidos",
)

# Mapeo best-effort del tipo de servicio RIPS → Tipo_de_servicio del FUR SERVICIOS
# (1=Medicamentos, 2=Procedimientos, 5=Insumos, 6=Dispositivos, 7=Osteosíntesis...)
# Para 'otrosServicios' no se puede inferir con certeza desde el tipo RIPS,
# pero SÍ desde el prefijo del código del prestador (ver inferir_tipo_por_codigo).
TIPO_SERVICIO_FUR = {
    "consultas": "2",
    "procedimientos": "2",
    "urgencias": "2",
    "hospitalizacion": "2",
    "medicamentos": "1",
    "otrosServicios": "",  # → se intenta por código (FMO=7, FMQ/QX=5, ...)
    "recienNacidos": "2",
}

# Prefijos del catálogo interno HUS → Tipo_de_servicio del FUR.
# Conocidos hasta hoy: FMO=osteosíntesis, FMQ/QX=insumos quirúrgicos.
# Si aparecen prefijos nuevos, agregarlos acá tras verificar con la factura.
_RE_MEDICAMENTO_CUM = re.compile(r"^\d{4,}-\d{1,}$")  # ej. 19908236-07, 224249-2


def inferir_tipo_por_codigo(codigo: str) -> str:
    """Infiere Tipo_de_servicio del FUR a partir del código del prestador.

    Devuelve "" si no se puede inferir con seguridad (lo deja para revisión
    manual en vez de adivinar mal).
    """
    if not codigo:
        return ""
    c = codigo.strip().upper()
    if c.startswith("FMO"):
        return "7"  # Material de osteosíntesis
    if c.startswith("FMQ") or c.startswith("QX"):
        return "5"  # Insumos quirúrgicos
    if _RE_MEDICAMENTO_CUM.match(c):
        return "1"  # CUM/IUM de medicamento
    if c.isdigit():
        return "2"  # Código CUPS/SOAT numérico = procedimiento
    return ""


def cargar_rips(ruta: Path) -> dict:
    """Carga el RIPS tolerando BOM y distintas codificaciones."""
    ultimo_error: Exception | None = None
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            with ruta.open(encoding=enc) as fh:
                return json.load(fh)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            ultimo_error = e
            continue
    raise ValueError(f"No pude parsear el RIPS {ruta}: {ultimo_error}")


def _num(valor) -> str:
    """Normaliza un valor numérico a string sin separadores ni decimales .0."""
    if valor is None or valor == "":
        return ""
    if isinstance(valor, float) and valor.is_integer():
        return str(int(valor))
    return str(valor)


def datos_generales(data: dict) -> dict:
    return {
        "num_factura": data.get("numFactura") or data.get("numNota") or "",
        "nit_prestador": data.get("numDocumentoIdObligado", ""),
        "tipo_nota": data.get("tipoNota"),
        "num_nota": data.get("numNota"),
        "num_usuarios": len(data.get("usuarios") or []),
    }


def extraer_lineas_servicios(data: dict) -> list[dict]:
    """Devuelve una fila normalizada por cada servicio del RIPS.

    Campos normalizados (los que alimentan el FUR SERVICIOS):
        tipo_rips, tipo_servicio_fur, cod_servicio, cups, descripcion,
        cantidad, vr_unitario, vr_total, doc_usuario
    """
    num_factura = data.get("numFactura") or data.get("numNota") or ""
    nit = data.get("numDocumentoIdObligado", "")
    lineas: list[dict] = []

    for u in data.get("usuarios") or []:
        doc_usuario = u.get("numDocumentoIdentificacion", "")
        servicios = u.get("servicios") or {}
        for tipo in SERVICIOS_RIPS:
            for it in servicios.get(tipo) or []:
                # CUPS sólo de procedimiento/consulta. NO usar codDiagnosticoPrincipal
                # (es un CIE-10 de diagnóstico, p.ej. S820, no un CUPS).
                cups = it.get("codProcedimiento") or it.get("codConsulta") or ""
                cod_servicio = it.get("codTecnologiaSalud", "")
                cantidad = (
                    it.get("cantidadOS")
                    or it.get("cantidadMedicamento")
                    or it.get("cantidad")
                    or (1 if tipo in ("consultas", "procedimientos", "urgencias") else "")
                )
                vr_unitario = (
                    it.get("vrUnitOS") or it.get("vrUnitMedicamento") or it.get("vrServicio") or ""
                )
                vr_total = it.get("vrServicio", "")
                # Tipo: primero por sección RIPS; si queda vacío, por prefijo
                # del código (FMO=7, FMQ/QX=5, dígitos puros=2, CUM=1).
                tipo_fur = TIPO_SERVICIO_FUR.get(tipo, "")
                if not tipo_fur:
                    tipo_fur = inferir_tipo_por_codigo(cod_servicio)
                lineas.append(
                    {
                        "num_factura": num_factura,
                        "nit_prestador": nit,
                        "tipo_rips": tipo,
                        "tipo_servicio_fur": tipo_fur,
                        "cod_servicio": cod_servicio,
                        "cups": cups,
                        "descripcion": it.get("nomTecnologiaSalud", ""),
                        "cantidad": _num(cantidad),
                        "vr_unitario": _num(vr_unitario),
                        "vr_total": _num(vr_total),
                        "doc_usuario": doc_usuario,
                    }
                )
    return lineas
