"""Seed inicial de la DB nueva (Neon Free).

Pensado para correr UNA SOLA VEZ después de migrar de Render Postgres
expirado a Neon. Pobla:

  1. Usuario SUPER_ADMIN inicial (Yesid).
  2. Contratos por defecto (CONTRATOS_DEFAULT de main.py) — 11 EPS con
     descripciones de tarifa pactada.
  3. Plantillas Gold canónicas (los textos fijos del motor IA: ratificada,
     extemporánea, DMBUG TARIFAS) para que el sistema arranque "tibio"
     en vez de frío.

USO
  Desde Render Web Shell (motor-glosas-hus → Shell tab):
    python -m scripts.seed_initial

  O localmente apuntando a la DB nueva:
    DATABASE_URL="postgresql://..." python -m scripts.seed_initial

IDEMPOTENTE
  Si los registros ya existen (mismo email, misma EPS, mismo título Gold),
  se saltan. Podés correrlo varias veces sin riesgo.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone

# Asegurar que app/ está en PYTHONPATH si se corre desde scripts/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, Base, engine  # noqa: E402
from app.auth import get_password_hash  # noqa: E402
from app.models.db import (  # noqa: E402
    UsuarioRecord,
    ContratoRecord,
    PlantillaGoldRecord,
)
from app.main import CONTRATOS_DEFAULT  # noqa: E402

# ─── CONFIGURACIÓN DEL ADMIN INICIAL ─────────────────────────────────────
# Yesid puede sobreescribir con env vars antes de correr el script:
#   ADMIN_EMAIL="otroemail@hus.gov.co" ADMIN_PASSWORD="mipass" python ...
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "yesidbadillo820@gmail.com")
ADMIN_NOMBRE = os.getenv("ADMIN_NOMBRE", "YESID PEREZ")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "Cambiame123!")
ADMIN_ROL = "SUPER_ADMIN"


def _crear_usuario_admin(db) -> bool:
    """True si lo creó, False si ya existía."""
    existente = db.query(UsuarioRecord).filter(
        UsuarioRecord.email == ADMIN_EMAIL
    ).first()
    if existente:
        print(f"  ↳ Usuario {ADMIN_EMAIL} ya existe (id={existente.id}). Skip.")
        return False
    user = UsuarioRecord(
        nombre=ADMIN_NOMBRE,
        email=ADMIN_EMAIL,
        password_hash=get_password_hash(ADMIN_PASSWORD),
        rol=ADMIN_ROL,
        activo=1,
        # Forzar cambio en primer login porque la password es genérica.
        must_change_password=1,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    print(f"  ✓ Usuario admin creado: {ADMIN_EMAIL} (id={user.id}, rol={ADMIN_ROL})")
    print(f"    Password inicial: {ADMIN_PASSWORD}")
    print(f"    ⚠ El sistema te va a pedir cambiarla en el primer login.")
    return True


def _seed_contratos(db) -> tuple[int, int]:
    """Devuelve (creados, ya_existian)."""
    creados = 0
    ya_existian = 0
    for eps_key, detalles in CONTRATOS_DEFAULT.items():
        existente = db.query(ContratoRecord).filter(
            ContratoRecord.eps == eps_key
        ).first()
        if existente:
            ya_existian += 1
            continue
        c = ContratoRecord(eps=eps_key, detalles=detalles)
        db.add(c)
        creados += 1
    db.commit()
    return creados, ya_existian


# ─── PLANTILLAS GOLD CANÓNICAS ───────────────────────────────────────────
# Textos institucionales que arrancan ya como "Gold" para que el motor IA
# los use como few-shot desde el día uno (sin esperar que glosas LEVANTADAS
# vayan poblando el set de aprendizaje).

def _plantillas_gold_canonicas() -> list[dict]:
    from app.services.glosa_service import (
        TEXTO_RATIFICADA,
        TEXTO_DMBUG_TARIFAS,
    )
    return [
        {
            "eps": "TODAS",
            "codigo_glosa": "RATIFICADA",
            "tipo": "RATIFICADA",
            "titulo": "Glosa ratificada — texto canónico HUS",
            "argumento": TEXTO_RATIFICADA,
            "notas": (
                "Plantilla institucional para ratificadas. Mantiene "
                "respuesta inicial + invita a conciliación."
            ),
        },
        {
            "eps": "DISPENSARIO MEDICO",
            "codigo_glosa": "TA",
            "tipo": "TARIFAS_DMBUG",
            "titulo": "DMBUG — Tarifas con contrato 440-DIGSA/DMBUG-2025",
            "argumento": TEXTO_DMBUG_TARIFAS,
            "notas": (
                "Texto fijo institucional aprobado por Yesid (abr 2026). "
                "Cita contrato 440-DIGSA/DMBUG-2025 con anexo de 7141 "
                "ítems. Refuta agotamiento presupuestal."
            ),
        },
    ]


def _seed_plantillas_gold(db) -> tuple[int, int]:
    """Devuelve (creadas, ya_existian)."""
    creadas = 0
    ya_existian = 0
    for p in _plantillas_gold_canonicas():
        existente = db.query(PlantillaGoldRecord).filter(
            PlantillaGoldRecord.eps == p["eps"],
            PlantillaGoldRecord.codigo_glosa == p["codigo_glosa"],
            PlantillaGoldRecord.titulo == p["titulo"],
        ).first()
        if existente:
            ya_existian += 1
            continue
        rec = PlantillaGoldRecord(
            eps=p["eps"],
            codigo_glosa=p["codigo_glosa"],
            tipo=p["tipo"],
            titulo=p["titulo"],
            argumento=p["argumento"],
            glosa_origen_id=0,  # canónica, no proviene de una glosa
            valor_recuperado=0.0,
            usos=0,
            creado_por="seed_initial",
            notas=p["notas"],
            activa=1,
        )
        db.add(rec)
        creadas += 1
    db.commit()
    return creadas, ya_existian


def main() -> None:
    print("=" * 70)
    print("SEED INICIAL — Motor Glosas HUS (DB nueva)")
    print("=" * 70)
    print(f"DATABASE_URL: {os.getenv('DATABASE_URL', '(no seteada)')[:60]}...")
    print()

    # 1. Crear tablas si no existen (idempotente)
    print("1. Asegurando schema de tablas...")
    Base.metadata.create_all(bind=engine)
    print("   ✓ Schema OK")
    print()

    db = SessionLocal()
    try:
        # 2. Usuario admin
        print("2. Creando usuario admin inicial...")
        _crear_usuario_admin(db)
        print()

        # 3. Contratos default
        print("3. Sembrando contratos default (CONTRATOS_DEFAULT)...")
        c, ya = _seed_contratos(db)
        print(f"   ✓ {c} contratos creados, {ya} ya existían.")
        print()

        # 4. Plantillas Gold canónicas
        print("4. Sembrando Plantillas Gold canónicas...")
        pg, pg_ya = _seed_plantillas_gold(db)
        print(f"   ✓ {pg} Gold creadas, {pg_ya} ya existían.")
        print()

        print("=" * 70)
        print("SEED COMPLETO")
        print("=" * 70)
        print(f"Loguearse en https://motor-glosas-hus.onrender.com con:")
        print(f"  Email:    {ADMIN_EMAIL}")
        print(f"  Password: {ADMIN_PASSWORD}  (cambiala en el primer login)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
