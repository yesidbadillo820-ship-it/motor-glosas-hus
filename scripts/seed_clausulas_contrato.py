#!/usr/bin/env python3
"""Carga las cláusulas LITERALES de contratos por EPS a la tabla
`clausulas_contrato`, para que la IA las cite textualmente al refutar.

Ronda 23 (jul-2026): la tabla clausulas_contrato estaba vacía en la
práctica (solo la poblaban acciones manuales por-EPS), por lo que la IA
nunca tenía una cláusula real que citar y caía en "SIN CONTRATO PACTADO"
o evadía la cláusula que la EPS invocaba. Este seed permite cargar las
cláusulas en lote desde data/clausulas_contrato_base.json.

Uso:
    python scripts/seed_clausulas_contrato.py                 # carga el JSON
    python scripts/seed_clausulas_contrato.py --dry-run       # solo muestra
    python scripts/seed_clausulas_contrato.py --archivo otro.json

Idempotente: (eps, numero_clausula, tema) que ya exista se ACTUALIZA, no
se duplica.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_TEMAS_VALIDOS = {"TA", "SO", "AU", "CO", "FA", "NN"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Seed cláusulas de contrato por EPS")
    ap.add_argument("--dry-run", action="store_true", help="Solo muestra lo que haría")
    ap.add_argument("--archivo", default="data/clausulas_contrato_base.json")
    args = ap.parse_args()

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env_path = os.path.join(raiz, ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

    archivo = args.archivo if os.path.isabs(args.archivo) else os.path.join(raiz, args.archivo)
    if not os.path.exists(archivo):
        print(f"[ERROR] No encontré {archivo}")
        return 1

    with open(archivo, encoding="utf-8") as f:
        data = json.load(f)

    filas = data.get("clausulas", [])
    # Validación mínima (no cargar basura que la IA citaría como real).
    limpias = []
    for i, fila in enumerate(filas, 1):
        eps = (fila.get("eps") or "").upper().strip()
        texto = (fila.get("texto_literal") or "").strip()
        tema = (fila.get("tema") or "NN").upper().strip()
        if not eps or not texto:
            print(f"  [SKIP {i}] falta eps o texto_literal")
            continue
        if texto.startswith("[") and texto.endswith("]"):
            print(f"  [SKIP {i}] texto_literal es un placeholder sin llenar: {texto[:40]}")
            continue
        if tema not in _TEMAS_VALIDOS:
            print(f"  [WARN {i}] tema '{tema}' no válido → NN")
            tema = "NN"
        limpias.append(
            {
                "eps": eps,
                "numero_clausula": (fila.get("numero_clausula") or "").strip(),
                "tema": tema,
                "titulo": (fila.get("titulo") or "").strip(),
                "texto_literal": texto,
                "pagina": fila.get("pagina"),
            }
        )

    print(
        f"[INFO] {len(limpias)} cláusula(s) válida(s) de {len(filas)} en {os.path.basename(archivo)}"
    )
    if not limpias:
        print(
            "[INFO] Nada que cargar. Llená data/clausulas_contrato_base.json con tus cláusulas reales."
        )
        return 0

    if args.dry_run:
        for c in limpias:
            print(
                f"  {c['eps']:12s} | cl.{c['numero_clausula']:4s} | {c['tema']} | {c['titulo'][:50]}"
            )
        print("[DRY-RUN] No se modificó la base de datos.")
        return 0

    sys.path.insert(0, raiz)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.models.db import ClausulaContrato

    db_url = os.environ.get("DATABASE_URL", "sqlite:///./motor_glosas.db")
    engine = create_engine(
        db_url, connect_args={"check_same_thread": False} if "sqlite" in db_url else {}
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    creadas = actualizadas = 0
    try:
        for c in limpias:
            # Ronda 26: la clave de idempotencia es (eps, numero_clausula) —
            # SIN el tema. Si una cláusula se re-clasifica (ej. FA -> NN para
            # que se inyecte en cualquier glosa), se ACTUALIZA el tema en vez
            # de crear una fila duplicada con el texto repetido.
            existente = (
                db.query(ClausulaContrato)
                .filter(ClausulaContrato.eps == c["eps"])
                .filter(ClausulaContrato.numero_clausula == c["numero_clausula"])
                .first()
            )
            if existente:
                existente.tema = c["tema"]
                existente.titulo = c["titulo"]
                existente.texto_literal = c["texto_literal"]
                existente.pagina = c["pagina"]
                actualizadas += 1
            else:
                db.add(ClausulaContrato(**c))
                creadas += 1
        db.commit()
        print(f"[OK] {creadas} creada(s), {actualizadas} actualizada(s).")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
