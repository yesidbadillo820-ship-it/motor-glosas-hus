#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga data/plantillas_hus_base.json en la base de datos de producción.

Uso:
    python scripts/seed_plantillas_hus.py [--dry-run]

Requisitos:
    DATABASE_URL en .env o en el entorno (same as the app).
    Ejecutar desde la raíz del proyecto.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def main():
    parser = argparse.ArgumentParser(description="Seed plantillas HUS base")
    parser.add_argument("--dry-run", action="store_true", help="Solo muestra lo que haría")
    parser.add_argument(
        "--archivo",
        default="data/plantillas_hus_base.json",
        help="Ruta al JSON de plantillas (default: data/plantillas_hus_base.json)",
    )
    args = parser.parse_args()

    # Cargar .env si existe
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    archivo = args.archivo
    if not os.path.exists(archivo):
        print(f"[ERROR] No encontré {archivo}")
        sys.exit(1)

    with open(archivo, encoding="utf-8") as f:
        data = json.load(f)

    filas = data.get("plantillas", [])
    print(f"[INFO] {len(filas)} plantillas en {archivo}")

    if args.dry_run:
        for i, fila in enumerate(filas, 1):
            print(
                f"  [{i:02d}] {fila['eps']:10s} | {fila['codigo_glosa']:10s} | {fila['titulo'][:60]}"
            )
        print("[DRY-RUN] No se modificó la base de datos.")
        return

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models.db import PlantillaGoldRecord

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./glosas.db")
    engine = create_engine(
        db_url, connect_args={"check_same_thread": False} if "sqlite" in db_url else {}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    import hashlib, re as _re

    def _hash(eps, codigo, argumento):
        norm = " ".join((eps or "").upper().split())
        norm += "|" + " ".join((codigo or "").upper().split())
        arg_norm = _re.sub(r"\s+", " ", (argumento or "").strip())[:5000]
        norm += "|" + arg_norm
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    hashes_existentes = {
        _hash(p.eps, p.codigo_glosa, p.argumento) for p in db.query(PlantillaGoldRecord).all()
    }

    creadas = 0
    omitidas = 0
    for fila in filas:
        eps = (fila.get("eps") or "").upper().strip()
        cod = (fila.get("codigo_glosa") or "").upper().strip()
        arg = (fila.get("argumento") or "").strip()
        h = _hash(eps, cod, arg)
        if h in hashes_existentes:
            omitidas += 1
            continue
        rec = PlantillaGoldRecord(
            eps=eps,
            codigo_glosa=cod,
            tipo=fila.get("tipo") or "PLANTILLA_HUS_BASE",
            titulo=(fila.get("titulo") or f"{cod} · {eps}")[:200],
            argumento=arg,
            notas=fila.get("notas") or None,
            creado_por="seed_plantillas_hus.py",
            activa=1,
        )
        db.add(rec)
        hashes_existentes.add(h)
        creadas += 1

    db.commit()
    db.close()
    print(f"[OK] Creadas: {creadas} | Omitidas (duplicado): {omitidas}")


if __name__ == "__main__":
    main()
