"""Historial de versiones del dictamen + restauración.

Cada vez que se genera, refina o regenera un dictamen, se guarda snapshot.
El auditor puede revisar cómo cambió y restaurar una versión anterior.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.db import DictamenVersionRecord, GlosaRecord, UsuarioRecord
from app.api.deps import get_usuario_actual
from app.repositories.audit_repository import AuditRepository

router = APIRouter(prefix="/glosas/{glosa_id}/versiones", tags=["versiones"])


@router.get("/")
def listar(
    glosa_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    if not db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first():
        raise HTTPException(404, "Glosa no encontrada")
    q = (
        db.query(DictamenVersionRecord)
        .filter(DictamenVersionRecord.glosa_id == glosa_id)
        .order_by(DictamenVersionRecord.creado_en.desc())
    )
    return [
        {
            "id": v.id,
            "accion": v.accion,
            "mensaje_refinar": v.mensaje_refinar,
            "autor_email": v.autor_email,
            "creado_en": v.creado_en.isoformat() if v.creado_en else None,
            "preview": (v.dictamen_html or "")[:300],
        }
        for v in q.limit(100).all()
    ]


@router.get("/diff")
def diff_versiones(
    glosa_id: int,
    v1: int,
    v2: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """R63 P1: comparación textual entre dos versiones del dictamen.

    Útil cuando el gestor reanaliza una glosa (R60 P2) y quiere ver
    qué cambió respecto a la versión previa, o al revisar refinamientos
    (R59) entre snapshots intermedios.

    Genera un unified diff sobre el TEXTO PLANO de cada dictamen
    (HTML stripped), línea a línea. Esto es más legible que un diff
    de HTML crudo (donde un cambio menor de texto explota en miles
    de chars de markup).

    Respuesta:
      {
        "glosa_id": 42,
        "v1": {"id": 10, "accion": "CREAR", "creado_en": "..."},
        "v2": {"id": 12, "accion": "REANALIZAR", "creado_en": "..."},
        "diff_unificado": "--- v10\\n+++ v12\\n@@ -1,3 ...",
        "lineas_agregadas": 5,
        "lineas_removidas": 3,
        "sin_cambios": False
      }
    """
    import difflib
    import re

    if v1 == v2:
        raise HTTPException(400, "v1 y v2 deben ser diferentes")

    def _cargar(vid: int):
        v = db.query(DictamenVersionRecord).filter(
            DictamenVersionRecord.id == vid,
            DictamenVersionRecord.glosa_id == glosa_id,
        ).first()
        if not v:
            raise HTTPException(404, f"Versión {vid} no encontrada")
        return v

    rec1 = _cargar(v1)
    rec2 = _cargar(v2)

    def _to_text(html: str) -> list[str]:
        """HTML → texto plano por líneas, sin tags ni espacios extras."""
        if not html:
            return []
        # Reemplazar </p>, </div>, <br/> por saltos de línea
        t = re.sub(r"</(p|div|h[1-6]|li|tr|section)\s*>", "\n", html, flags=re.IGNORECASE)
        t = re.sub(r"<br\s*/?>", "\n", t, flags=re.IGNORECASE)
        # Quitar tags
        t = re.sub(r"<[^>]+>", "", t)
        # Decode entidades comunes
        t = t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        # Normalizar espacios pero PRESERVAR saltos de línea
        lineas = []
        for ln in t.split("\n"):
            ln_norm = re.sub(r"\s+", " ", ln).strip()
            if ln_norm:
                lineas.append(ln_norm)
        return lineas

    txt1 = _to_text(rec1.dictamen_html or "")
    txt2 = _to_text(rec2.dictamen_html or "")

    # difflib produce el diff con marcadores +/- y headers @@.
    diff = list(difflib.unified_diff(
        txt1, txt2,
        fromfile=f"v{rec1.id} ({rec1.accion or '—'})",
        tofile=f"v{rec2.id} ({rec2.accion or '—'})",
        lineterm="",
    ))

    agregadas = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
    removidas = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))

    return {
        "glosa_id": glosa_id,
        "v1": {
            "id": rec1.id, "accion": rec1.accion,
            "creado_en": rec1.creado_en.isoformat() if rec1.creado_en else None,
            "autor_email": rec1.autor_email,
        },
        "v2": {
            "id": rec2.id, "accion": rec2.accion,
            "creado_en": rec2.creado_en.isoformat() if rec2.creado_en else None,
            "autor_email": rec2.autor_email,
        },
        "diff_unificado": "\n".join(diff),
        "lineas_agregadas": agregadas,
        "lineas_removidas": removidas,
        "sin_cambios": agregadas == 0 and removidas == 0,
    }


@router.get("/{version_id}")
def obtener(
    glosa_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    v = db.query(DictamenVersionRecord).filter(
        DictamenVersionRecord.id == version_id,
        DictamenVersionRecord.glosa_id == glosa_id,
    ).first()
    if not v:
        raise HTTPException(404, "Versión no encontrada")
    return {
        "id": v.id,
        "glosa_id": v.glosa_id,
        "accion": v.accion,
        "mensaje_refinar": v.mensaje_refinar,
        "autor_email": v.autor_email,
        "creado_en": v.creado_en.isoformat() if v.creado_en else None,
        "dictamen_html": v.dictamen_html,
    }


@router.post("/{version_id}/restaurar")
def restaurar(
    glosa_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    current_user: UsuarioRecord = Depends(get_usuario_actual),
):
    """Restaura una versión anterior del dictamen como la versión vigente."""
    glosa = db.query(GlosaRecord).filter(GlosaRecord.id == glosa_id).first()
    if not glosa:
        raise HTTPException(404, "Glosa no encontrada")
    v = db.query(DictamenVersionRecord).filter(
        DictamenVersionRecord.id == version_id,
        DictamenVersionRecord.glosa_id == glosa_id,
    ).first()
    if not v:
        raise HTTPException(404, "Versión no encontrada")

    # Snapshot del dictamen actual antes de sobrescribir
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id,
        dictamen_html=glosa.dictamen or "",
        accion="SNAPSHOT_PRE_RESTAURAR",
        autor_email=current_user.email,
    ))
    glosa.dictamen = v.dictamen_html
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id,
        dictamen_html=v.dictamen_html,
        accion="RESTAURAR",
        mensaje_refinar=f"Restaurada desde versión #{version_id}",
        autor_email=current_user.email,
    ))
    db.commit()
    AuditRepository(db).registrar(
        usuario_email=current_user.email, usuario_rol=current_user.rol,
        accion="RESTAURAR_DICTAMEN", tabla="historial",
        registro_id=glosa_id,
        detalle=f"Restauró versión #{version_id}",
    )
    return {"message": "Dictamen restaurado", "version_restaurada": version_id}


def guardar_version(
    db: Session,
    glosa_id: int,
    dictamen_html: str,
    accion: str,
    autor_email: str,
    mensaje_refinar: str = None,
):
    """Helper para que otros endpoints guarden snapshot."""
    if not dictamen_html:
        return
    db.add(DictamenVersionRecord(
        glosa_id=glosa_id,
        dictamen_html=dictamen_html,
        accion=accion,
        mensaje_refinar=mensaje_refinar,
        autor_email=autor_email,
    ))
    db.commit()
