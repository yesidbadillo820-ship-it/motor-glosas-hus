"""Vault de credenciales de plataformas EPS — endpoints (jun-2026).

Flujo:
  1. SUPER_ADMIN sube el Excel maestro en POST /credenciales/importar
     (hoja CONSOLIDADO). Usuario/contraseña/teléfono/correo se cifran
     con Fernet (CRED_VAULT_KEY) antes de tocar la BD.
  2. Cualquier usuario autenticado busca en GET /credenciales/buscar
     "cómo/dónde radicar para la entidad X" — solo metadatos, jamás
     secretos (ni cifrados ni en claro).
  3. COORDINADOR/SUPER_ADMIN revela usuario+contraseña puntualmente en
     POST /credenciales/{id}/revelar con motivo obligatorio → queda
     fila de auditoría. Rate-limited.
  4. SUPER_ADMIN revisa la auditoría en GET /credenciales/audit.

Si CRED_VAULT_KEY no está configurada, los endpoints que cifran o
descifran devuelven 503 (la app arranca igual; /buscar sigue sirviendo
los metadatos en claro).

REGLA DE ORO: ningún log/response fuera de /revelar contiene valores
descifrados. Los logs solo llevan conteos y metadatos.
"""

# NOTA: este módulo NO usa `from __future__ import annotations` a propósito.
# Con PEP 563 las anotaciones se vuelven strings y FastAPI 0.115.x no las
# resuelve a través del wrapper de slowapi (@limiter.limit) — el body model
# RevelarBody terminaba interpretado como query param y el endpoint devolvía
# 422 "Field required in query". Python 3.11 soporta `X | Y` nativo, así que
# el import no hace falta. Reproducido y verificado contra fastapi==0.115.6.

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.deps import get_admin, get_coordinador_o_admin, get_usuario_actual
from app.core.logging_utils import logger
from app.core.rate_limit import limiter
from app.database import get_db
from app.models.db import CredencialAccesoLog, EntidadCredencialRecord, UsuarioRecord
from app.services import credenciales_vault as vault

router = APIRouter(prefix="/credenciales", tags=["Credenciales EPS"])

_MSG_VAULT_OFF = "Vault no configurado — setea CRED_VAULT_KEY"

# Campos sensibles: columna cifrada ← clave del parser
_CAMPOS_CIFRADOS = {
    "usuario_cifrado": "usuario",
    "password_cifrado": "password",
    "telefono_cifrado": "telefono",
    "correo_cifrado": "correo",
}


def _exigir_vault():
    if not vault.vault_disponible():
        raise HTTPException(status_code=503, detail=_MSG_VAULT_OFF)


# ─── Importar ────────────────────────────────────────────────────────────────


@router.post("/importar")
async def importar_credenciales(
    archivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Importa el Excel maestro de credenciales (hoja CONSOLIDADO).

    Solo SUPER_ADMIN. Upsert por (nit, bloque): hasta 3 registros por
    entidad (RADICACION/CARTERA/DEVOLUCIONES). Devuelve SOLO conteos —
    nunca valores.
    """
    _exigir_vault()
    if not (archivo.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(400, "Solo se aceptan archivos .xlsx/.xlsm")
    contenido = await archivo.read()
    if len(contenido) > 10_000_000:
        raise HTTPException(413, "Archivo demasiado grande (>10 MB)")

    try:
        resultado = vault.parsear_consolidado(contenido)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception:
        # xlsx corrupto / no-zip / formato ilegible → error del cliente
        raise HTTPException(400, "No se pudo leer el archivo: ¿es un .xlsx válido?")

    creadas = 0
    actualizadas = 0
    entidades_unicas = len({e["nit"] for e in resultado["entidades"]})
    # Cache de registros tocados en ESTE import: si el Excel trae el mismo
    # (nit, bloque) dos veces, la segunda fila actualiza el registro recién
    # creado (last-wins) en vez de chocar con el índice único — la sesión
    # de producción usa autoflush=False y el query no vería el add pendiente.
    procesados: dict[tuple[str, str], EntidadCredencialRecord] = {}
    for ent in resultado["entidades"]:
        for bloque, datos in ent["bloques"].items():
            campos = {
                "nit": ent["nit"][:30],
                "empresa": ent["empresa"][:300],
                "bloque": bloque,
                "link_plataforma": datos.get("link_plataforma") or None,
                "nombre_contacto": (datos.get("nombre_contacto") or ent["nombre_contacto"])[:300]
                or None,
                "cargo": (datos.get("cargo") or "")[:200] or None,
                "manual_radicacion": ent["manual_radicacion"] or None,
                "medio_contacto": (datos.get("medio_contacto") or ent["medio_contacto"])[:300]
                or None,
                "actualizado_por": current_user.email,
            }
            for col, key in _CAMPOS_CIFRADOS.items():
                valor = datos.get(key) or ""
                campos[col] = vault.cifrar(valor) if valor else None

            clave = (campos["nit"], bloque)
            repetido_en_archivo = clave in procesados
            existente = procesados.get(clave) or (
                db.query(EntidadCredencialRecord)
                .filter(
                    EntidadCredencialRecord.nit == campos["nit"],
                    EntidadCredencialRecord.bloque == bloque,
                )
                .first()
            )
            if existente:
                for k, v in campos.items():
                    setattr(existente, k, v)
                if not repetido_en_archivo:
                    actualizadas += 1
                procesados[clave] = existente
            else:
                nuevo = EntidadCredencialRecord(**campos)
                db.add(nuevo)
                creadas += 1
                procesados[clave] = nuevo

    db.add(
        CredencialAccesoLog(
            usuario_email=current_user.email,
            accion="IMPORTAR",
            motivo=(
                f"archivo={archivo.filename} entidades={entidades_unicas} "
                f"creadas={creadas} actualizadas={actualizadas} "
                f"filas_sin_nit={resultado['filas_sin_nit']}"
            ),
        )
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "Error al guardar las credenciales importadas")

    logger.info(
        f"[CRED-VAULT] Import por {current_user.email}: "
        f"entidades={entidades_unicas} creadas={creadas} "
        f"actualizadas={actualizadas} filas_sin_nit={resultado['filas_sin_nit']}"
    )
    return {
        "entidades": entidades_unicas,
        "credenciales_creadas": creadas,
        "actualizadas": actualizadas,
        "filas_sin_nit": resultado["filas_sin_nit"],
    }


# ─── Buscar (sin secretos) ───────────────────────────────────────────────────


@router.get("/buscar")
def buscar_credenciales(
    q: str = Query("", description="Filtro por empresa o NIT (contains, case-insensitive)"),
    limite: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Directorio de plataformas por entidad. NUNCA devuelve secretos —
    solo indica con booleanos si existen usuario/contraseña guardados.
    Disponible para cualquier usuario autenticado, con o sin vault."""
    consulta = db.query(EntidadCredencialRecord)
    q = (q or "").strip()
    if q:
        patron = f"%{q}%"
        consulta = consulta.filter(
            or_(
                EntidadCredencialRecord.empresa.ilike(patron),
                EntidadCredencialRecord.nit.ilike(patron),
            )
        )
    registros = (
        consulta.order_by(EntidadCredencialRecord.empresa, EntidadCredencialRecord.bloque)
        .limit(limite)
        .all()
    )
    return {
        "total": len(registros),
        "items": [
            {
                "id": r.id,
                "nit": r.nit,
                "empresa": r.empresa,
                "bloque": r.bloque,
                "link_plataforma": r.link_plataforma,
                "nombre_contacto": r.nombre_contacto,
                "cargo": r.cargo,
                "medio_contacto": r.medio_contacto,
                "manual_radicacion": r.manual_radicacion,
                "tiene_usuario": bool(r.usuario_cifrado),
                "tiene_password": bool(r.password_cifrado),
                "actualizado_en": r.actualizado_en.isoformat() if r.actualizado_en else None,
            }
            for r in registros
        ],
    }


# ─── Revelar (descifrado puntual, auditado) ──────────────────────────────────


class RevelarBody(BaseModel):
    motivo: str = Field(
        ...,
        min_length=5,
        max_length=500,
        description="Justificación del acceso (queda en la auditoría)",
    )


@router.post("/{credencial_id}/revelar")
@limiter.limit("10/minute")
def revelar_credencial(
    request: Request,
    credencial_id: int,
    body: RevelarBody,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_coordinador_o_admin),
):
    """Descifra y devuelve usuario+contraseña UNA vez. Solo
    COORDINADOR/SUPER_ADMIN, con motivo obligatorio (≥5 caracteres).
    Cada intento (exitoso o fallido) queda en la auditoría."""
    _exigir_vault()
    registro = (
        db.query(EntidadCredencialRecord)
        .filter(EntidadCredencialRecord.id == credencial_id)
        .first()
    )
    if not registro:
        raise HTTPException(404, "Credencial no encontrada")

    motivo = body.motivo.strip()
    try:
        usuario = vault.descifrar(registro.usuario_cifrado) if registro.usuario_cifrado else None
        password = vault.descifrar(registro.password_cifrado) if registro.password_cifrado else None
    except Exception:
        # Clave rotada/incorrecta: token ilegible. Auditar el intento fallido.
        db.add(
            CredencialAccesoLog(
                credencial_id=registro.id,
                usuario_email=current_user.email,
                accion="REVELAR",
                motivo=f"[FALLO DESCIFRADO] {motivo}",
            )
        )
        db.commit()
        raise HTTPException(
            500,
            "No se pudo descifrar — la CRED_VAULT_KEY actual no corresponde a la usada al importar",
        )

    db.add(
        CredencialAccesoLog(
            credencial_id=registro.id,
            usuario_email=current_user.email,
            accion="REVELAR",
            motivo=motivo,
        )
    )
    db.commit()
    logger.info(
        f"[CRED-VAULT] REVELAR id={registro.id} bloque={registro.bloque} por {current_user.email}"
    )
    return {
        "id": registro.id,
        "empresa": registro.empresa,
        "bloque": registro.bloque,
        "usuario": usuario,
        "password": password,
    }


# ─── Auditoría ───────────────────────────────────────────────────────────────


@router.get("/audit")
def audit_credenciales(
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_admin),
):
    """Últimos 100 accesos al vault (IMPORTAR/REVELAR). Solo SUPER_ADMIN."""
    filas = db.query(CredencialAccesoLog).order_by(CredencialAccesoLog.id.desc()).limit(100).all()
    return {
        "total": len(filas),
        "items": [
            {
                "id": f.id,
                "credencial_id": f.credencial_id,
                "usuario_email": f.usuario_email,
                "accion": f.accion,
                "timestamp": f.timestamp.isoformat() if f.timestamp else None,
                "motivo": f.motivo,
            }
            for f in filas
        ],
    }
