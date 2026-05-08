"""Notificaciones push web (Web Push API).

El frontend registra un service worker y obtiene una PushSubscription.
El backend la guarda asociada al usuario. Para enviar, se requiere:
- VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY en env (por ahora opcional)
- pywebpush instalado (se agrega como dependencia futura; por ahora solo
  guardamos suscripciones y exponemos endpoint de test que las lista)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.tz import ahora_utc
from app.database import get_db
from app.models.db import PushSubscriptionRecord, UsuarioRecord
from app.api.deps import get_usuario_actual

router = APIRouter(prefix="/push", tags=["push"])


class SubscriptionInput(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str | None = None


@router.get("/public-key")
def public_key():
    """Devuelve la VAPID public key para que el cliente se registre.
    Si no está configurada, devuelve un placeholder inofensivo."""
    import os
    return {
        "public_key": os.getenv("VAPID_PUBLIC_KEY", ""),
        "habilitado": bool(os.getenv("VAPID_PUBLIC_KEY")),
    }


@router.post("/subscribe")
def subscribe(
    data: SubscriptionInput,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Guarda/actualiza una suscripción push para el usuario actual."""
    existente = db.query(PushSubscriptionRecord).filter(
        PushSubscriptionRecord.endpoint == data.endpoint
    ).first()
    if existente:
        existente.p256dh = data.p256dh
        existente.auth = data.auth
        existente.user_agent = data.user_agent
        existente.usuario_email = current_user.email
        existente.ultima_usada_en = ahora_utc()
        db.commit()
        return {"message": "Suscripción actualizada", "id": existente.id}
    reg = PushSubscriptionRecord(
        usuario_email=current_user.email,
        endpoint=data.endpoint,
        p256dh=data.p256dh,
        auth=data.auth,
        user_agent=data.user_agent,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    return {"message": "Suscripción guardada", "id": reg.id}


@router.delete("/unsubscribe")
def unsubscribe(
    endpoint: str,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    r = db.query(PushSubscriptionRecord).filter(
        PushSubscriptionRecord.endpoint == endpoint,
        PushSubscriptionRecord.usuario_email == current_user.email,
    ).first()
    if not r:
        raise HTTPException(404, "Suscripción no encontrada")
    db.delete(r)
    db.commit()
    return {"message": "Desuscrito"}


@router.post("/enviar")
def enviar_push(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Envia un push a todas las suscripciones del usuario actual.

    Payload: {
        "title": str,
        "body": str,
        "url": str (opcional, ruta a abrir al hacer click),
        "tag": str (opcional, agrupa notificaciones)
    }

    Usa pywebpush + VAPID. Si VAPID_PRIVATE_KEY no esta configurado,
    devuelve 503 con mensaje claro.
    """
    import os
    import json as _json
    private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    public_key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    vapid_claims_email = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:notificaciones@hus.gov.co")
    if not private_key or not public_key:
        raise HTTPException(503, "VAPID_PRIVATE_KEY/PUBLIC_KEY no configurados")
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        raise HTTPException(503, "pywebpush no instalado en el motor")
    subs = db.query(PushSubscriptionRecord).filter(
        PushSubscriptionRecord.usuario_email == current_user.email
    ).all()
    if not subs:
        return {"ok": True, "enviadas": 0, "msg": "Sin suscripciones"}
    enviadas = 0
    fallidas = 0
    for s in subs:
        try:
            sub_info = {
                "endpoint": s.endpoint,
                "keys": {"p256dh": s.p256dh, "auth": s.auth},
            }
            webpush(
                subscription_info=sub_info,
                data=_json.dumps(payload),
                vapid_private_key=private_key,
                vapid_claims={"sub": vapid_claims_email},
            )
            enviadas += 1
        except Exception as e:
            fallidas += 1
            # Si la suscripcion expiro, borrarla
            if "410" in str(e) or "404" in str(e):
                db.delete(s)
    db.commit()
    return {"ok": True, "enviadas": enviadas, "fallidas": fallidas}


@router.get("/mis-suscripciones")
def mis_suscripciones(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    rows = db.query(PushSubscriptionRecord).filter(
        PushSubscriptionRecord.usuario_email == current_user.email
    ).all()
    return [
        {
            "id": r.id,
            "user_agent": r.user_agent,
            "creado_en": r.creado_en.isoformat() if r.creado_en else None,
            "ultima_usada_en": r.ultima_usada_en.isoformat() if r.ultima_usada_en else None,
        }
        for r in rows
    ]
