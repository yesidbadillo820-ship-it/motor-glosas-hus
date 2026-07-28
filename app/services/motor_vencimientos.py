"""Motor de Vencimientos — capacidad del núcleo (SINAC OS).

Responde una sola pregunta, y la responde igual para todos los que la hagan:
**¿qué glosas están por vencerse, con qué urgencia, y de quién es cada una?**

Por qué existe
──────────────
El reloj del vencimiento no era del sistema: llegaba escrito en la columna
VENCE de un Excel y, si faltaba, la fila se descartaba. El semáforo tenía un
estado NEGRO para lo ya vencido y **no disparaba nada**. Eso costó tres
facturas de junio con 38 objeciones por $20.054.751, descubiertas el 22 de
julio revisando a mano — 45 días después del vencimiento.

El sistema ya tenía construido el envío de correos (`alerta_service.py`):
calcula, ordena por urgencia y arma el HTML. Estaba terminado y desconectado.
Este módulo es la pieza que faltaba en el medio.

Arquitectura
────────────
    Motor de vencimientos   ← este módulo: lógica pura, sin correo ni base
            ↓
    Clasificación por urgencia (umbrales configurables)
            ↓
    Resolución de responsables (por nivel de urgencia)
            ↓
    Canales: correo · tablero · (futuro: bot de mensajería)

Reglas de negocio como CONFIGURACIÓN, no como código
────────────────────────────────────────────────────
El auditor define quién recibe, con cuántos días y desde qué cuenta **sin
esperar un despliegue**. Los umbrales por defecto salen de la tabla que
definió el área:

    10 días → aviso preventivo
     5 días → alerta alta
     2 días → alerta crítica
    vencida → escalamiento

Falla cerrado: sin destinatarios configurados NO se envía nada, pero el
tablero sigue funcionando. Es preferible que el área vea el listado en
pantalla a que el sistema crea que avisó y no haya avisado a nadie.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Optional

from app.core.logging_utils import logger

# Estados en los que la glosa ya no compite contra el reloj.
ESTADOS_CERRADOS = {
    "LEVANTADA",
    "ACEPTADA",
    "CONCILIADA",
    "ARCHIVADA",
    "RESUELTA",
    "PARCIALMENTE_ACEPTADA",
}


class Urgencia(str, Enum):
    """Niveles de urgencia, de menor a mayor. El orden importa: se compara."""

    SIN_RIESGO = "SIN_RIESGO"
    PREVENTIVO = "PREVENTIVO"
    ALTA = "ALTA"
    CRITICA = "CRITICA"
    VENCIDA = "VENCIDA"


#: Orden de severidad para comparar y ordenar.
_ORDEN = {
    Urgencia.SIN_RIESGO: 0,
    Urgencia.PREVENTIVO: 1,
    Urgencia.ALTA: 2,
    Urgencia.CRITICA: 3,
    Urgencia.VENCIDA: 4,
}


def severidad(u: Urgencia) -> int:
    return _ORDEN[u]


@dataclass(frozen=True)
class Umbrales:
    """Días restantes a partir de los cuales aplica cada nivel.

    Se leen de variables de entorno para poder ajustarlos sin desplegar:
      VENCIMIENTOS_DIAS_PREVENTIVO (10) · _ALTA (5) · _CRITICA (2)
    """

    preventivo: int = 10
    alta: int = 5
    critica: int = 2

    @classmethod
    def desde_entorno(cls) -> "Umbrales":
        def _leer(nombre: str, defecto: int) -> int:
            try:
                v = int(str(os.getenv(nombre, "")).strip())
                return v if v >= 0 else defecto
            except (TypeError, ValueError):
                return defecto

        u = cls(
            preventivo=_leer("VENCIMIENTOS_DIAS_PREVENTIVO", 10),
            alta=_leer("VENCIMIENTOS_DIAS_ALTA", 5),
            critica=_leer("VENCIMIENTOS_DIAS_CRITICA", 2),
        )
        # Un orden invertido (crítica > alta) dejaría niveles inalcanzables y
        # el área creería estar avisada cuando no lo está.
        if not (u.critica <= u.alta <= u.preventivo):
            logger.warning(
                "[VENCIMIENTOS] umbrales incoherentes (crítica=%s alta=%s preventivo=%s): "
                "se usan los valores por defecto 2/5/10.",
                u.critica,
                u.alta,
                u.preventivo,
            )
            return cls()
        return u


def clasificar(dias_restantes: Optional[int], umbrales: Optional[Umbrales] = None) -> Urgencia:
    """Nivel de urgencia según los días que faltan.

    `None` (la glosa no trae plazo) se trata como SIN_RIESGO: no se puede
    afirmar que esté por vencerse. Que una glosa llegue sin plazo es un
    problema distinto — lo reporta `resumen()` aparte, para que no se
    esconda.
    """
    if dias_restantes is None:
        return Urgencia.SIN_RIESGO
    u = umbrales or Umbrales.desde_entorno()
    if dias_restantes < 0:
        return Urgencia.VENCIDA
    if dias_restantes <= u.critica:
        return Urgencia.CRITICA
    if dias_restantes <= u.alta:
        return Urgencia.ALTA
    if dias_restantes <= u.preventivo:
        return Urgencia.PREVENTIVO
    return Urgencia.SIN_RIESGO


def esta_en_juego(glosa: Any) -> bool:
    """¿Esta glosa todavía compite contra el reloj?

    Una glosa ya levantada, aceptada o conciliada no vence: alertar sobre
    ella es ruido, y el ruido es lo que hace que se ignoren las alertas que
    sí importan.
    """
    estado = (getattr(glosa, "estado", "") or "").strip().upper()
    if estado in ESTADOS_CERRADOS:
        return False
    wf = (getattr(glosa, "workflow_state", "") or "").strip().upper()
    return wf not in ESTADOS_CERRADOS


@dataclass
class GlosaEnRiesgo:
    """Una glosa que compite contra el reloj, con su urgencia y su dueño."""

    glosa: Any
    urgencia: Urgencia
    dias_restantes: Optional[int]

    @property
    def id(self) -> Optional[int]:
        return getattr(self.glosa, "id", None)

    @property
    def responsable(self) -> str:
        """Correo del gestor asignado, o cadena vacía si no tiene dueño."""
        return (getattr(self.glosa, "auditor_email", "") or "").strip().lower()

    def como_dict(self) -> dict:
        g = self.glosa
        return {
            "id": self.id,
            "factura": getattr(g, "factura", None),
            "eps": getattr(g, "eps", None),
            "codigo_glosa": getattr(g, "codigo_glosa", None),
            "valor_objetado": getattr(g, "valor_objetado", None),
            "dias_restantes": self.dias_restantes,
            "urgencia": self.urgencia.value,
            "responsable": self.responsable or None,
            # El nombre del paciente NO viaja en las alertas: son correos que
            # salen del sistema y pueden reenviarse (Ley 1581/2012).
        }


@dataclass
class ResumenVencimientos:
    """Fotografía del riesgo por vencimiento en un momento dado."""

    en_riesgo: list[GlosaEnRiesgo] = field(default_factory=list)
    sin_plazo: int = 0
    total_evaluadas: int = 0

    def por_urgencia(self, nivel: Urgencia) -> list[GlosaEnRiesgo]:
        return [g for g in self.en_riesgo if g.urgencia is nivel]

    def desde(self, nivel: Urgencia) -> list[GlosaEnRiesgo]:
        """Las de ese nivel y todas las más urgentes."""
        piso = severidad(nivel)
        return [g for g in self.en_riesgo if severidad(g.urgencia) >= piso]

    @property
    def conteos(self) -> dict[str, int]:
        return {
            n.value: len(self.por_urgencia(n)) for n in Urgencia if n is not Urgencia.SIN_RIESGO
        }

    @property
    def valor_en_riesgo(self) -> float:
        total = 0.0
        for g in self.en_riesgo:
            try:
                total += float(getattr(g.glosa, "valor_objetado", 0) or 0)
            except (TypeError, ValueError):
                continue
        return total

    def como_dict(self) -> dict:
        return {
            "conteos": self.conteos,
            "total_en_riesgo": len(self.en_riesgo),
            "valor_en_riesgo": round(self.valor_en_riesgo),
            "sin_plazo": self.sin_plazo,
            "total_evaluadas": self.total_evaluadas,
            "glosas": [g.como_dict() for g in self.en_riesgo],
        }


def evaluar(glosas: Iterable[Any], umbrales: Optional[Umbrales] = None) -> ResumenVencimientos:
    """Clasifica un conjunto de glosas y devuelve la fotografía del riesgo.

    Función PURA: no toca la base ni envía nada. Recibe objetos con
    `dias_restantes`, `estado` y `auditor_email`, y devuelve el resumen
    ordenado de la más urgente a la menos urgente.
    """
    u = umbrales or Umbrales.desde_entorno()
    resumen = ResumenVencimientos()
    for g in glosas:
        resumen.total_evaluadas += 1
        if not esta_en_juego(g):
            continue
        dias = getattr(g, "dias_restantes", None)
        if dias is None:
            resumen.sin_plazo += 1
            continue
        nivel = clasificar(dias, u)
        if nivel is Urgencia.SIN_RIESGO:
            continue
        resumen.en_riesgo.append(GlosaEnRiesgo(glosa=g, urgencia=nivel, dias_restantes=dias))
    resumen.en_riesgo.sort(key=lambda x: (-severidad(x.urgencia), x.dias_restantes or 0))
    return resumen


# ─── Quién recibe qué ────────────────────────────────────────────────────


@dataclass(frozen=True)
class Destinatarios:
    """A quién le llega cada nivel de urgencia.

    Modelo de gobierno definido por el área (28-jul-2026):

      ┌─────────────┬──────────────────────────────────────────────────────┐
      │ Preventivo  │ gestor de la glosa · analista responsable            │
      │ (10 días)   │                                                      │
      ├─────────────┼──────────────────────────────────────────────────────┤
      │ Alta        │ gestor · coordinador de cartera/glosas               │
      │ (5 días)    │                                                      │
      ├─────────────┼──────────────────────────────────────────────────────┤
      │ Crítica     │ gestor · coordinador · líder financiero              │
      │ (2 días)    │                                                      │
      ├─────────────┼──────────────────────────────────────────────────────┤
      │ Vencida     │ gestor · coordinador · dirección financiera ·        │
      │             │ auditoría interna                                    │
      └─────────────┴──────────────────────────────────────────────────────┘

    Dos reglas de gobierno, no de programación:

    1. **El gestor recibe SIEMPRE sus casos**, en todos los niveles. Es quien
       puede actuar; enterarlo tarde no tiene defensa.
    2. **El escalamiento entra al superar el umbral, y no se repite.** Los
       niveles son acumulativos hacia arriba: a quien se declara en ALTA le
       llegan ALTA, CRÍTICA y VENCIDA sin necesidad de repetir su correo en
       las tres variables. Por eso el coordinador se declara UNA vez.

    Configuración (listas separadas por coma; el orden de las variables sigue
    la tabla de arriba):

      VENCIMIENTOS_CORREO_GESTOR      ¿se le avisa al gestor asignado? (1/0)
      VENCIMIENTOS_CORREO_PREVENTIVO  analista responsable
      VENCIMIENTOS_CORREO_ALTA        coordinador de cartera/glosas
      VENCIMIENTOS_CORREO_CRITICA     líder financiero
      VENCIMIENTOS_CORREO_VENCIDA     dirección financiera · auditoría interna

    La cuenta emisora (SMTP_FROM) debe ser institucional —del estilo
    `sinac.alertas@hus.gov.co`— y nunca personal: el aviso tiene que
    sobrevivir a los cambios de personas.
    """

    avisar_al_gestor: bool = True
    preventivo: tuple[str, ...] = ()
    alta: tuple[str, ...] = ()
    critica: tuple[str, ...] = ()
    vencida: tuple[str, ...] = ()

    @staticmethod
    def _lista(nombre: str) -> tuple[str, ...]:
        crudo = os.getenv(nombre, "") or ""
        return tuple(
            c.strip().lower() for c in crudo.replace(";", ",").split(",") if "@" in c.strip()
        )

    @classmethod
    def desde_entorno(cls) -> "Destinatarios":
        flag = (os.getenv("VENCIMIENTOS_CORREO_GESTOR", "1") or "").strip().lower()
        return cls(
            avisar_al_gestor=flag not in ("0", "false", "no", ""),
            preventivo=cls._lista("VENCIMIENTOS_CORREO_PREVENTIVO"),
            alta=cls._lista("VENCIMIENTOS_CORREO_ALTA"),
            critica=cls._lista("VENCIMIENTOS_CORREO_CRITICA"),
            vencida=cls._lista("VENCIMIENTOS_CORREO_VENCIDA"),
        )

    def para(self, item: GlosaEnRiesgo) -> list[str]:
        """Correos que deben enterarse de ESTA glosa, sin repetidos."""
        destinos: list[str] = []
        if self.avisar_al_gestor and item.responsable:
            destinos.append(item.responsable)
        sev = severidad(item.urgencia)
        if sev >= severidad(Urgencia.PREVENTIVO):
            destinos.extend(self.preventivo)
        if sev >= severidad(Urgencia.ALTA):
            destinos.extend(self.alta)
        if sev >= severidad(Urgencia.CRITICA):
            destinos.extend(self.critica)
        if sev >= severidad(Urgencia.VENCIDA):
            destinos.extend(self.vencida)
        vistos: set[str] = set()
        unicos: list[str] = []
        for d in destinos:
            if d and d not in vistos:
                vistos.add(d)
                unicos.append(d)
        return unicos

    @property
    def hay_alguno(self) -> bool:
        return bool(
            self.preventivo or self.alta or self.critica or self.vencida or self.avisar_al_gestor
        )

    @property
    def hay_escalamiento(self) -> bool:
        """¿Hay alguien por encima del gestor?

        Si solo se avisa al gestor, una glosa vencida le llega únicamente a
        quien la dejó vencer — que es exactamente lo que falló con las tres
        facturas de junio. El tablero lo reporta para que se vea.
        """
        return bool(self.preventivo or self.alta or self.critica or self.vencida)


def agrupar_por_destinatario(
    resumen: ResumenVencimientos, destinatarios: Optional[Destinatarios] = None
) -> dict[str, list[GlosaEnRiesgo]]:
    """Un correo por persona con TODO lo suyo, no un correo por glosa.

    Cien glosas críticas no pueden ser cien correos: eso garantiza que nadie
    los lea.
    """
    d = destinatarios or Destinatarios.desde_entorno()
    bandejas: dict[str, list[GlosaEnRiesgo]] = {}
    for item in resumen.en_riesgo:
        for correo in d.para(item):
            bandejas.setdefault(correo, []).append(item)
    return bandejas
