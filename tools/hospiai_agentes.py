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
    reg.registrar_clase(AgenteSemantico)
    from hospiai_directores import (
        AgenteAprendizaje,
        AgenteDirectorAuditoria,
        AgenteDirectorGerencial,
        AgenteDirectorOperativo,
    )

    reg.registrar_clase(AgenteDirectorAuditoria)
    reg.registrar_clase(AgenteDirectorOperativo)
    reg.registrar_clase(AgenteDirectorGerencial)
    reg.registrar_clase(AgenteAprendizaje)
    from hospiai_indexador import AgenteIndexador

    reg.registrar_clase(AgenteIndexador)
    from hospiai_documento import (
        AgenteDocumentCurator,
        AgenteIngesta,
        AgenteStorageOptimizer,
    )

    reg.registrar_clase(AgenteDocumentCurator)
    reg.registrar_clase(AgenteStorageOptimizer)
    reg.registrar_clase(AgenteIngesta)
    from hospiai_conocimiento import (
        AgenteKnowledgeCurator,
        AgentePatternDiscovery,
        AgenteProcessMiner,
        AgenteRecommendation,
        AgenteRootCause,
    )

    reg.registrar_clase(AgenteKnowledgeCurator)
    reg.registrar_clase(AgentePatternDiscovery)
    reg.registrar_clase(AgenteRecommendation)
    reg.registrar_clase(AgenteRootCause)
    reg.registrar_clase(AgenteProcessMiner)
    from hospiai_operacion import (
        AgenteContratos,
        AgenteCorreccionMasiva,
        AgenteGemeloEPS,
        AgenteMejoraContinua,
        AgentePlanRecuperacion,
    )

    reg.registrar_clase(AgentePlanRecuperacion)
    reg.registrar_clase(AgenteCorreccionMasiva)
    reg.registrar_clase(AgenteContratos)
    reg.registrar_clase(AgenteGemeloEPS)
    reg.registrar_clase(AgenteMejoraContinua)
    return reg


class AgenteSemantico(Agente):
    """AG011 — Explica qué SIGNIFICA un código (documento, diagnóstico CIE-10,
    procedimiento CUPS) y qué implica para la auditoría, usando las ontologías
    del Knowledge Layer. Si el código no está en las ontologías, lo reporta
    con confianza baja para que se cargue la tabla oficial que falta."""

    id = "AG011"
    nombre = "MotorSemantico"
    dominio = "KNOWLEDGE"
    version = "1.0"
    entradas = ["codigo"]
    salidas = ["cadena", "hallado", "ontologia"]
    depende_de = []
    herramientas = ["ontologias data/ontologias/*.json"]
    capacidades = ["EXPLICAR_CONCEPTO"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        from hospiai_semantica import MotorSemantico

        motor = MotorSemantico(contexto.get("dir_ontologias"))
        codigo = mision.datos["codigo"]
        hallado = motor.concepto(codigo)
        res.salida = {
            "cadena": motor.explicar(codigo),
            "hallado": hallado is not None,
            "ontologia": hallado[0] if hallado else "",
        }
        res.evidencias.append({"tipo": "ontologias", "valor": ", ".join(motor.resumen())})
        if hallado is None:
            res.confianza = 0.2
            res.detalle = f"'{codigo}' no está en las ontologías: cargar la tabla oficial."
        else:
            res.detalle = res.salida["cadena"][0]
