#!/usr/bin/env python3
"""HOSPIAI — Agentes de referencia sobre el Agent SDK (Fase 1.6).

Primeros agentes implementados con el contrato único (`hospiai_sdk.Agente`).
Envuelven capacidades ya probadas del motor para demostrar la migración
"módulo → agente" sin reescribir la lógica: la función sigue siendo la misma,
el AGENTE le agrega identidad, validación, formato estándar, registro en el
Expediente y desacoplamiento por misiones.

El resto del pipeline (AG001, AG005–AG007) se migra progresivamente con este
mismo patrón; mientras tanto corre "legacy" dentro del radicador y así lo
declara el Registro Central (data/agentes.json).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import radicar_facturacion as rad  # noqa: E402
from hospiai_sdk import Agente, Mision, RegistroAgentes, ResultadoAgente  # noqa: E402


class AgenteAnalizadorRuta(Agente):
    """AG002 — De una ruta del share extrae año, mes, responsable, lote y
    factura. Determinístico (confianza 1.0)."""

    id = "AG002"
    nombre = "AnalizadorRuta"
    dominio = "D1"
    version = "1.1"
    entradas = ["ruta"]
    salidas = ["anio", "mes", "responsable", "lote", "factura"]
    depende_de = ["AG001"]
    herramientas = ["ninguna (puro texto)"]
    capacidades = ["ANALIZAR_RUTA"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        ruta = mision.datos["ruta"]
        info = rad.analizar_ruta(ruta)
        res.salida = {k: info.get(k) for k in self.salidas}
        res.evidencias.append({"tipo": "ruta", "valor": ruta})
        res.detalle = f"responsable={info.get('responsable') or '—'} lote={info.get('lote') or '—'}"


class AgenteClasificadorDocumental(Agente):
    """AG003 — De un nombre de archivo determina el código ADRES del soporte
    (FEV, RIP, CUV, HEV, EPI…). Si no lo reconoce, lo reporta como hallazgo
    SIN_TIPIFICAR para que el área lo renombre o se amplíe el diccionario."""

    id = "AG003"
    nombre = "ClasificadorDocumental"
    dominio = "D1"
    version = "1.1"
    entradas = ["nombre"]
    salidas = ["codigo", "descripcion", "reconocido"]
    depende_de = ["AG001"]
    herramientas = ["diccionario ADRES (Res. 2284/2023) + alias HUS"]
    capacidades = ["CLASIFICAR_DOCUMENTO"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        nombre = mision.datos["nombre"]
        codigo, descripcion, reconocido = rad.clasificar_soporte(nombre)
        res.salida = {"codigo": codigo, "descripcion": descripcion, "reconocido": reconocido}
        res.evidencias.append({"tipo": "nombre_archivo", "valor": nombre})
        res.detalle = f"{nombre} → {codigo}"
        if not reconocido:
            res.confianza = 0.5  # ADM por descarte: que lo revise un humano
            res.hallazgos.append(
                {
                    "tipo": "SIN_TIPIFICAR",
                    "codigo": "",
                    "criticidad": "ADVERTENCIA",
                    "detalle": f"Archivo sin tipificar: {nombre}",
                    "evidencia": f"Nombre observado: {nombre}",
                    "confianza": 0.5,
                }
            )


def registro_con_implementaciones(ruta=None) -> RegistroAgentes:
    """Registro Central con las implementaciones SDK vinculadas. El Supervisor
    parte de aquí: pregunta al registro, jamás importa clases por su cuenta."""
    reg = RegistroAgentes(ruta)
    reg.registrar_clase(AgenteAnalizadorRuta)
    reg.registrar_clase(AgenteClasificadorDocumental)
    return reg
