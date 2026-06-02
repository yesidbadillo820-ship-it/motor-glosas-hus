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
# Para 'otrosServicios' no se puede inferir con certeza (insumo/dispositivo/
# osteosíntesis), así que se deja vacío para que lo complete el prestador.
TIPO_SERVICIO_FUR = {
    "consultas": "2",
    "procedimientos": "2",
    "urgencias": "2",
    "hospitalizacion": "2",
    "medicamentos": "1",
    "otrosServicios": "",  # ambiguo → manual
    "recienNacidos": "2",
}


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
                cups = (
                    it.get("codProcedimiento")
                    or it.get("codConsulta")
                    or it.get("codDiagnosticoPrincipal")
                    or ""
                )
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
                lineas.append(
                    {
                        "num_factura": num_factura,
                        "nit_prestador": nit,
                        "tipo_rips": tipo,
                        "tipo_servicio_fur": TIPO_SERVICIO_FUR.get(tipo, ""),
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
