#!/usr/bin/env python3
"""HOSPIAI — Interfaz de radicación en portales (RPA · Fase 5, SOLO interfaz).

Por directiva de Fase 2: el RPA NO comienza todavía, pero la interfaz queda
definida para que, cuando gerencia y TI lo autoricen, solo haya que agregar
adaptadores por portal sin tocar la plataforma.

Contrato: todo adaptador implementa `IRadicador` (login/subir/confirmar/
descargar/cerrar). El Supervisor lo invocará vía misiones tipo RPA/RADICAR, que
la política `requiere_aprobacion_humana` bloquea por defecto: la radicación
automática exige autorización expresa (docs/ARQUITECTURA_HOSPIAI.md §10) y
SIEMPRE correrá con aprobación humana previa por lote.

Este módulo no tiene ninguna implementación que toque la red: registrar un
adaptador real será un acto deliberado, nunca un accidente.
"""

from __future__ import annotations


class IRadicador:
    """Contrato único de radicación en el portal de un pagador.

    Ciclo de vida completo de una radicación:
        login() → subir(expediente) → confirmar() → descargar_comprobante()
        → cerrar()
    Cada método devuelve un dict con al menos {"ok": bool, "detalle": str};
    `confirmar` agrega {"numero_radicado": str} y `descargar_comprobante`
    {"comprobante": ruta_local}."""

    portal: str = ""  # p.ej. "ASMET", "NUEVA_EPS", "SANITAS", "ADRES"

    def login(self, credenciales: dict) -> dict:
        raise NotImplementedError

    def subir(self, expediente: dict, archivos: list) -> dict:
        raise NotImplementedError

    def confirmar(self) -> dict:
        raise NotImplementedError

    def descargar_comprobante(self, destino) -> dict:
        raise NotImplementedError

    def cerrar(self) -> dict:
        raise NotImplementedError


# Adaptadores por portal. VACÍO a propósito: se llenan en Fase 5, con
# autorización de gerencia/TI y credenciales gestionadas por TI.
ADAPTADORES: dict[str, type[IRadicador]] = {}


def adaptador(portal: str) -> type[IRadicador]:
    """Adaptador registrado para un portal. Falla claro si aún no existe."""
    clave = (portal or "").strip().upper()
    if clave not in ADAPTADORES:
        raise KeyError(
            f"No hay adaptador RPA para '{portal}'. La radicación automática es Fase 5 "
            "y requiere autorización de gerencia/TI (la política la bloquea por defecto)."
        )
    return ADAPTADORES[clave]
