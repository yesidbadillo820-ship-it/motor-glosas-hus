"""Radicación autónoma en los portales de las EPS (V3, Pilar 1).

Arquitectura completa en `docs/ARQUITECTURA_V3_PILAR1_RPA.md`. Aquí vive la
DECISIÓN; el navegador lo maneja el bot del PC (`tools/radicar_glosas_coosalud.py`)
y el transporte lo hace la cola que ya existía (`TrabajoBotRecord`).

Las tres ideas que gobiernan este módulo:

1. LA COLA LLEVA QUÉ RADICAR, NUNCA CÓMO AUTENTICARSE. Las claves de los
   portales viven en `config/entidades.credenciales.json`, en el PC del
   auditor, fuera de la base de datos.

2. ANTE LA DUDA, NO SE ACTÚA. Si el bot pulsó «radicar» y no alcanzó a leer
   el comprobante, la fila queda en EN_PORTAL_SIN_CONFIRMAR y está PROHIBIDO
   reintentar sola: primero una persona (o la pasada de verificación) mira el
   portal. Radicar dos veces le hace daño real al hospital ante la EPS.

3. LOS ESCUDOS DE LA V2 NO SE TOCAN. Nada se radica sin que un humano lo haya
   aprobado: el estado tiene que ser RESPONDIDA, y si la glosa venía del
   Auto-Pilot se exige su fila LIBERADA_POR_HUMANO en la bitácora.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.logging_utils import logger
from app.models.db import (
    RAD_EN_PORTAL_SIN_CONFIRMAR,
    RAD_ESTADOS_VIVOS,
    RAD_FALLIDA,
    RAD_HUMANO_REQUERIDO,
    RAD_PENDIENTE,
    RAD_RADICADA,
    RAD_RECLAMADA,
    RAD_VERIFICAR_MANUAL,
    AutoPilotBitacoraRecord,
    GlosaRecord,
    RadicacionEpsRecord,
)

ACTOR_BOT = "radicador-rpa"

# El estado al que pasa la glosa cuando el portal confirma. Detiene el reloj
# interno del hospital (está en motor_vencimientos.ESTADOS_CERRADOS) y la
# manda a «En espera de EPS».
ESTADO_GLOSA_RADICADA = "RADICADA_EN_EPS"

# Solo se radica lo que un humano dejó listo.
ESTADO_GLOSA_EXIGIDO = "RESPONDIDA"

# Cuántas veces se deja que una fila vuelva a la cola tras una caída temprana
# del bot. A la tercera deja de rebotar y la mira una persona: si un PC se
# cayó tres veces en el mismo sitio, no es mala suerte, es que le falta algo
# (playwright sin instalar, Chrome sin abrir, el motor apagado) y ninguna
# cuarta pasada lo va a arreglar sola.
MAX_INTENTOS_RESCATE = 3

# ── Matriz de portales (decisión del auditor, 03-09-2026) ───────────────
# Usuario y contraseña: el bot puede de punta a punta.
PORTALES_AUTOMATIZABLES = {"COOSALUD", "SIMED", "MUTUAL_SER"}
# Captcha o token dinámico: NO son automatizables. Sus filas nacen en
# HUMANO_REQUERIDO — no se promete autonomía donde técnicamente no la hay.
PORTALES_HUMANO_REQUERIDO = {"FOMAG", "DGH", "NUEVA_EPS"}

# Cómo se reconoce el portal en el nombre que trae la glosa.
_PISTAS_PORTAL = (
    ("COOSALUD", "COOSALUD"),
    ("MUTUAL", "MUTUAL_SER"),
    ("DISPENSARIO", "SIMED"),
    ("SIMED", "SIMED"),
    ("FOMAG", "FOMAG"),
    ("NUEVA EPS", "NUEVA_EPS"),
    ("NUEVAEPS", "NUEVA_EPS"),
    ("DINAMICA", "DGH"),
    ("DGH", "DGH"),
)


def portal_de(eps: str) -> str:
    """A qué portal pertenece una EPS. Cadena vacía si no se reconoce —
    y lo que no se reconoce NO se radica solo."""
    texto = (eps or "").upper().strip()
    for pista, portal in _PISTAS_PORTAL:
        if pista in texto:
            return portal
    return ""


def clave_idempotencia(glosa: Any) -> str:
    """«eps|factura|codigo|etapa». Reconoce el mismo trabajo aunque cambie el
    id de la glosa. Va con índice ÚNICO en la base: es la barrera física
    contra radicar dos veces."""

    def _limpio(v) -> str:
        return re.sub(r"\s+", " ", str(v or "").strip().upper())

    return "|".join(
        (
            _limpio(getattr(glosa, "eps", "")),
            _limpio(getattr(glosa, "factura", "")),
            _limpio(getattr(glosa, "codigo_glosa", "")),
            _limpio(getattr(glosa, "etapa", "")),
        )
    )[:200]


def sha256_de(ruta: str) -> str:
    """Hash del comprobante. Peso probatorio (engancha con el Pilar 6)."""
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def _vino_del_auto_pilot(db: Any, glosa_id: int) -> bool:
    return (
        db.query(AutoPilotBitacoraRecord)
        .filter(AutoPilotBitacoraRecord.glosa_id == glosa_id)
        .filter(AutoPilotBitacoraRecord.decision == "CANDIDATA")
        .first()
        is not None
    )


def _liberada_por_humano(db: Any, glosa_id: int) -> bool:
    return (
        db.query(AutoPilotBitacoraRecord)
        .filter(AutoPilotBitacoraRecord.glosa_id == glosa_id)
        .filter(AutoPilotBitacoraRecord.decision == "LIBERADA_POR_HUMANO")
        .first()
        is not None
    )


def motivo_no_radicable(db: Any, glosa: Any) -> Optional[str]:
    """Por qué esta glosa NO puede irse al portal. None = puede.

    Aquí se replican, del lado del servidor, los escudos de la V2: lo que la
    pantalla impide con un botón gris, esto lo impide de verdad.
    """
    estado = str(getattr(glosa, "workflow_state", "") or "").upper()

    # Escudo 2 — la cuarentena del Auto-Pilot jamás llega al portal.
    if estado == "PENDIENTE_APROBACION_HUMANA":
        return (
            "Está en la bandeja de borradores del Auto-Pilot: nadie la ha "
            "liberado todavía. Sin clic humano no se radica."
        )
    if estado != ESTADO_GLOSA_EXIGIDO:
        return f"Su estado es {estado or 'desconocido'}, y solo se radica lo que está {ESTADO_GLOSA_EXIGIDO}."

    if not str(getattr(glosa, "dictamen", "") or "").strip():
        return "No tiene dictamen: no hay nada que radicar."

    # Escudos 2 + 3 — si la propuso la máquina, exige la liberación humana.
    gid = getattr(glosa, "id", None)
    if gid is not None and _vino_del_auto_pilot(db, gid) and not _liberada_por_humano(db, gid):
        return (
            "La propuso el Auto-Pilot y no consta su liberación humana en la "
            "bitácora. Sin ese clic no se radica."
        )

    # Escudo 13 (nuevo) — dictamen obsoleto frente a tarifas o contratos
    # cargados después de generarlo.
    try:
        from app.services.dictamen_stale import motivo_stale

        stale = motivo_stale(glosa, db)
        if stale:
            return f"El dictamen quedó desactualizado: {stale}"
    except Exception as e:  # noqa: BLE001 — no bloquear por fallo del chequeo
        logger.warning(f"[RADICACION] No se pudo evaluar si el dictamen está vencido: {e}")

    # Escudo 9 — lo que apaga el botón «Marcar como RESPONDIDA» en pantalla
    # también cierra la puerta del portal.
    try:
        from app.services.auditor_dictamen import auditar_dictamen

        aud = auditar_dictamen(glosa, db) or {}
        graves = [h for h in (aud.get("hallazgos") or []) if h.get("severidad") == "alta"]
        if graves:
            return "Control de calidad con hallazgo grave: " + str(graves[0].get("titulo") or "")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[RADICACION] No se pudo auditar el dictamen: {e}")

    return None


def encolar(db: Any, glosa_ids: list[int], trabajo_bot_id: Optional[int] = None) -> dict:
    """Mete glosas al libro de radicación. NO abre ningún navegador.

    Cada glosa cae en uno de tres sitios:
      · PENDIENTE          → el bot la tomará (portal automatizable)
      · HUMANO_REQUERIDO   → portal con captcha o token: la hace una persona
      · rechazada          → no pasó los escudos; se dice por qué
    """
    parte = {"encoladas": 0, "humano_requerido": 0, "rechazadas": [], "ya_estaban": 0}

    for gid in glosa_ids[:500]:
        glosa = db.query(GlosaRecord).filter(GlosaRecord.id == gid).first()
        if glosa is None:
            parte["rechazadas"].append({"glosa_id": gid, "motivo": "No existe esa glosa."})
            continue

        motivo = motivo_no_radicable(db, glosa)
        if motivo:
            parte["rechazadas"].append({"glosa_id": gid, "motivo": motivo})
            continue

        clave = clave_idempotencia(glosa)
        viva = (
            db.query(RadicacionEpsRecord)
            .filter(RadicacionEpsRecord.clave_idempotencia == clave)
            .filter(RadicacionEpsRecord.estado.in_(RAD_ESTADOS_VIVOS))
            .first()
        )
        if viva is not None:
            parte["ya_estaban"] += 1
            continue

        portal = portal_de(getattr(glosa, "eps", ""))
        if portal in PORTALES_AUTOMATIZABLES:
            estado = RAD_PENDIENTE
            parte["encoladas"] += 1
        else:
            # Captcha, token dinámico o portal desconocido: lo hace una persona.
            estado = RAD_HUMANO_REQUERIDO
            parte["humano_requerido"] += 1

        db.add(
            RadicacionEpsRecord(
                glosa_id=gid,
                clave_idempotencia=clave,
                trabajo_bot_id=trabajo_bot_id,
                eps=str(getattr(glosa, "eps", "") or "")[:200],
                portal=portal or "DESCONOCIDO",
                estado=estado,
                intentos=0,
                actor=ACTOR_BOT,
            )
        )
    db.commit()
    logger.info(
        f"[RADICACION] encoladas={parte['encoladas']} "
        f"humano={parte['humano_requerido']} rechazadas={len(parte['rechazadas'])}"
    )
    return parte


def reclamar_una(
    db: Any, portal: str, equipo: str, trabajo_bot_id: Optional[int] = None
) -> Optional[dict]:
    """El bot pide UNA fila. Reclamo atómico: dos agentes no pueden llevarse
    la misma. Devuelve None si no hay nada que radicar."""
    fila = (
        db.query(RadicacionEpsRecord)
        .filter(RadicacionEpsRecord.estado == RAD_PENDIENTE)
        .filter(RadicacionEpsRecord.portal == portal)
        .order_by(RadicacionEpsRecord.id)
        .first()
    )
    if fila is None:
        return None

    # El WHERE sobre el estado es lo que hace atómico el reclamo: si otro
    # agente se adelantó, actualiza 0 filas y aquí no se toma nada.
    tomadas = (
        db.query(RadicacionEpsRecord)
        .filter(RadicacionEpsRecord.id == fila.id)
        .filter(RadicacionEpsRecord.estado == RAD_PENDIENTE)
        .update(
            {
                "estado": RAD_RECLAMADA,
                "intentos": (fila.intentos or 0) + 1,
                "actor": f"{ACTOR_BOT}@{(equipo or 'pc')[:60]}",
                "trabajo_bot_id": trabajo_bot_id or fila.trabajo_bot_id,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if not tomadas:
        return None

    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == fila.glosa_id).first()
    if glosa is None:
        marcar_fallida(db, fila.id, "La glosa desapareció entre encolar y radicar.")
        return None

    # Se vuelve a comprobar contra los escudos: entre encolar y radicar
    # pudieron cargarse tarifas nuevas o alguien pudo reabrir la glosa.
    motivo = motivo_no_radicable(db, glosa)
    if motivo:
        marcar_humano_requerido(db, fila.id, motivo)
        return None

    return {
        "radicacion_id": fila.id,
        "glosa_id": glosa.id,
        "eps": glosa.eps,
        "portal": fila.portal,
        "factura": glosa.factura,
        "codigo_glosa": glosa.codigo_glosa,
        # El código de respuesta que el portal pide al cerrar (RE9901, RE9502…).
        # Sin él, el bot tendría que adivinarlo y el portal registraría otro.
        "codigo_respuesta": getattr(glosa, "codigo_respuesta", "") or "",
        "valor_objetado": glosa.valor_objetado,
        "dictamen": glosa.dictamen,
    }


def marcar_en_portal(db: Any, radicacion_id: int) -> dict:
    """Se va a pulsar «radicar» AHORA. Se deja escrito ANTES de pulsar: si se
    corta la luz en el siguiente milisegundo, la fila ya quedó marcada como
    dudosa y nadie la reintentará a ciegas."""
    fila = db.query(RadicacionEpsRecord).filter(RadicacionEpsRecord.id == radicacion_id).first()
    if fila is None:
        return {"estado": "no_existe"}
    fila.estado = RAD_EN_PORTAL_SIN_CONFIRMAR
    db.commit()
    return {"estado": fila.estado}


def confirmar_radicada(
    db: Any,
    radicacion_id: int,
    radicado_numero: str,
    comprobante_ruta: str = "",
    comprobante_sha256: str = "",
) -> dict:
    """El portal devolvió el comprobante. Se escribe la evidencia y la glosa
    pasa a RADICADA_EN_EPS: sale del semáforo de urgencia y entra a «En
    espera de EPS»."""
    fila = db.query(RadicacionEpsRecord).filter(RadicacionEpsRecord.id == radicacion_id).first()
    if fila is None:
        return {"estado": "no_existe"}
    if not (radicado_numero or "").strip():
        return {"estado": "sin_radicado", "detalle": "Un comprobante sin número no es evidencia."}
    if fila.estado == RAD_RADICADA:
        # Idempotente: repetir la confirmación no duplica ni reescribe.
        return {"estado": RAD_RADICADA, "radicado": fila.radicado_numero, "repetida": True}

    fila.estado = RAD_RADICADA
    fila.radicado_numero = radicado_numero.strip()[:120]
    fila.comprobante_ruta = (comprobante_ruta or "")[:500] or None
    fila.comprobante_sha256 = (comprobante_sha256 or "")[:64] or None
    fila.radicado_en = datetime.now(timezone.utc)

    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == fila.glosa_id).first()
    if glosa is not None:
        glosa.workflow_state = ESTADO_GLOSA_RADICADA
        glosa.nota_workflow = (
            f"Radicada en el portal de {fila.eps or 'la EPS'} · radicado {fila.radicado_numero}"
        )[:500]
    db.commit()
    logger.info(
        f"[RADICACION] glosa={fila.glosa_id} RADICADA en {fila.portal} "
        f"radicado={fila.radicado_numero}"
    )
    return {"estado": RAD_RADICADA, "radicado": fila.radicado_numero}


def marcar_fallida(db: Any, radicacion_id: int, error: str) -> dict:
    """Falló LIMPIO: no se alcanzó a enviar nada. Se puede reintentar."""
    fila = db.query(RadicacionEpsRecord).filter(RadicacionEpsRecord.id == radicacion_id).first()
    if fila is None:
        return {"estado": "no_existe"}
    if fila.estado == RAD_EN_PORTAL_SIN_CONFIRMAR:
        # Desde la duda NO se cae a «fallida»: eso invitaría a reintentar.
        fila.estado = RAD_VERIFICAR_MANUAL
    else:
        fila.estado = RAD_FALLIDA
    fila.ultimo_error = (error or "")[:4000]
    db.commit()
    return {"estado": fila.estado}


def rescatar_reclamada(
    db: Any,
    radicacion_id: int,
    error: str,
    max_intentos: int = MAX_INTENTOS_RESCATE,
) -> dict:
    """El bot se cayó CON LA FILA EN LA MANO, antes de tocar el portal.

    El agujero que tapa: `reclamar_una` marca la fila RECLAMADA y, si el bot
    se muere en el paso siguiente —playwright sin instalar, Chrome sin abrir,
    el navegador que no arranca—, esa fila se quedaba RECLAMADA para siempre.
    No aparecía como pendiente para ningún otro PC, no aparecía como atorada
    para ninguna persona: simplemente desaparecía del mundo con la glosa
    adentro.

    Qué hace: devuelve la fila a PENDIENTE para que otro equipo sano la tome,
    y deja escrito en `ultimo_error` de qué se murió el que la tenía.

    DÓNDE NO SE METE (y es lo importante). Solo rescata filas en RECLAMADA.
    Una fila en EN_PORTAL_SIN_CONFIRMAR NO se toca ni por equivocación: ahí
    ya se pulsó «radicar» y no se leyó el comprobante. Devolverla a la cola
    sería invitar a radicar dos veces la misma glosa, que es el daño real que
    este módulo existe para evitar (idea 2 de la cabecera).

    EL CONTADOR NO SE TOCA ACÁ, y es a propósito: `reclamar_una` ya sumó el
    intento al entregar la fila. Volver a sumarlo haría que el cortacircuito
    saltara a la mitad de los intentos anunciados — dos vueltas en vez de
    tres. Acá solo se LEE para decidir si ya fueron suficientes.
    """
    fila = db.query(RadicacionEpsRecord).filter(RadicacionEpsRecord.id == radicacion_id).first()
    if fila is None:
        return {"estado": "no_existe"}
    if fila.estado != RAD_RECLAMADA:
        # Puede ser una carrera normal (el bot alcanzó a reportar y además
        # avisó de su caída). No es un error: simplemente no hay qué rescatar.
        return {"estado": "no_rescatable", "actual": fila.estado}

    intentos = int(fila.intentos or 0)
    fila.ultimo_error = (error or "")[:4000]

    if intentos >= max_intentos:
        # Cortacircuito: deja de rebotar entre equipos y pasa a manos de una
        # persona, que es quien puede arreglar lo que le falta al PC.
        fila.estado = RAD_HUMANO_REQUERIDO
        db.commit()
        logger.warning(
            f"[RADICACION] rescate agotado glosa={fila.glosa_id} "
            f"intentos={intentos} → {RAD_HUMANO_REQUERIDO}"
        )
        return {"estado": RAD_HUMANO_REQUERIDO, "intentos": intentos, "agotada": True}

    fila.estado = RAD_PENDIENTE
    # Se le quita el sello del PC que la tenía: vuelve a estar libre, y una
    # fila pendiente con el nombre de un equipo encima confunde a quien mira
    # la bandeja.
    fila.actor = ACTOR_BOT
    db.commit()
    logger.info(
        f"[RADICACION] fila rescatada glosa={fila.glosa_id} "
        f"intentos={intentos}/{max_intentos} → {RAD_PENDIENTE}"
    )
    return {"estado": RAD_PENDIENTE, "intentos": intentos, "agotada": False}


def marcar_humano_requerido(db: Any, radicacion_id: int, motivo: str) -> dict:
    """Captcha, token, portal cambiado o dictamen que dejó de ser radicable."""
    fila = db.query(RadicacionEpsRecord).filter(RadicacionEpsRecord.id == radicacion_id).first()
    if fila is None:
        return {"estado": "no_existe"}
    fila.estado = RAD_HUMANO_REQUERIDO
    fila.ultimo_error = (motivo or "")[:4000]
    db.commit()
    return {"estado": fila.estado}


def resolver_verificacion(
    db: Any, radicacion_id: int, quedo_radicada: bool, usuario_email: str, radicado_numero: str = ""
) -> dict:
    """La ÚNICA salida de EN_PORTAL_SIN_CONFIRMAR / VERIFICAR_MANUAL: una
    persona miró el portal y dice qué pasó de verdad."""
    fila = db.query(RadicacionEpsRecord).filter(RadicacionEpsRecord.id == radicacion_id).first()
    if fila is None:
        return {"estado": "no_existe"}
    if fila.estado not in (RAD_EN_PORTAL_SIN_CONFIRMAR, RAD_VERIFICAR_MANUAL):
        return {"estado": "no_requiere_verificacion", "actual": fila.estado}

    fila.verificado_en = datetime.now(timezone.utc)
    fila.verificado_por = (usuario_email or "")[:200]
    if quedo_radicada:
        resultado = confirmar_radicada(db, radicacion_id, radicado_numero or "verificado-a-mano")
        return {"estado": resultado.get("estado"), "verificada": True}
    fila.estado = RAD_PENDIENTE
    fila.ultimo_error = "Verificado a mano: no quedó radicada. Vuelve a la cola."
    db.commit()
    return {"estado": RAD_PENDIENTE, "verificada": True}
