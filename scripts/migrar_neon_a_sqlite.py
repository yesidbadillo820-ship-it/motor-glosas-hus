"""Migra TODOS los datos de Postgres (Neon) a SQLite (volumen Fly).

Cuándo usarlo: una sola vez, cuando tengas acceso temporal a Neon (tras
el reset mensual de cuota o un upgrade de 1 mes) para mover las glosas a
la nueva DB SQLite y no volver a depender de Neon.

Cómo funciona: usa los modelos SQLAlchemy del proyecto, así que copia
tabla por tabla en el orden correcto de dependencias (FKs). Es idempotente
a nivel de tabla: vacía la tabla destino antes de copiar (--limpiar) para
poder re-correrlo sin duplicar.

Uso:
    # Origen = Postgres (Neon); Destino = SQLite local o del volumen.
    PG_URL="postgresql://neondb_owner:...@ep-...neon.tech/neondb?sslmode=require" \\
    SQLITE_URL="sqlite:////data/motorglosas.db" \\
    python scripts/migrar_neon_a_sqlite.py

    # Prueba en seco (no escribe):
    ... python scripts/migrar_neon_a_sqlite.py --dry-run

Tras migrar, cambia el secret en Fly y redeploy:
    flyctl secrets set DATABASE_URL="sqlite:////data/motorglosas.db" -a motor-glosas-hus
"""

from __future__ import annotations

import argparse
import os
import sys

# Permitir ejecutar el script desde cualquier directorio (agrega la raíz
# del proyecto al path para que `import app...` funcione).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="No escribe; solo cuenta filas")
    parser.add_argument(
        "--limpiar",
        action="store_true",
        default=True,
        help="Vacía cada tabla destino antes de copiar (default: sí)",
    )
    args = parser.parse_args()

    pg_url = os.getenv("PG_URL", "").strip()
    sqlite_url = os.getenv("SQLITE_URL", "sqlite:////data/motorglosas.db").strip()
    if not pg_url:
        print("ERROR: define PG_URL con la cadena de conexión de Neon (Postgres).")
        return 2
    if pg_url.startswith("postgres://"):
        pg_url = pg_url.replace("postgres://", "postgresql://", 1)

    # Importar los modelos para poblar Base.metadata con todas las tablas.
    from app.database import Base
    import app.models.db  # noqa: F401  (registra los modelos en Base.metadata)

    # Crear dir del SQLite si hace falta
    if sqlite_url.startswith("sqlite:///") and ":memory:" not in sqlite_url:
        ruta = sqlite_url.replace("sqlite:///", "", 1)
        d = os.path.dirname(ruta)
        if d:
            os.makedirs(d, exist_ok=True)

    src_engine = create_engine(pg_url)
    dst_engine = create_engine(sqlite_url, connect_args={"check_same_thread": False})

    print(f"Origen (Postgres): {pg_url.split('@')[-1]}")
    print(f"Destino (SQLite):  {sqlite_url}")
    print(f"Modo: {'DRY-RUN (no escribe)' if args.dry_run else 'ESCRITURA'}\n")

    # Crear el schema en destino
    if not args.dry_run:
        Base.metadata.create_all(bind=dst_engine)

    SrcSession = sessionmaker(bind=src_engine)
    DstSession = sessionmaker(bind=dst_engine)
    src = SrcSession()
    dst = DstSession()

    total_filas = 0
    errores = []
    # sorted_tables respeta el orden de FKs (padres antes que hijos)
    try:
        for tabla in Base.metadata.sorted_tables:
            try:
                filas = list(src.execute(tabla.select()).mappings())
            except Exception as e:  # noqa: BLE001
                errores.append(f"{tabla.name}: lectura falló: {e}")
                continue
            n = len(filas)
            print(f"  {tabla.name:32s} {n:6d} filas", end="")
            if args.dry_run:
                print(" (dry-run)")
                total_filas += n
                continue
            if args.limpiar:
                dst.execute(tabla.delete())
            if filas:
                dst.execute(tabla.insert(), [dict(f) for f in filas])
            dst.commit()
            total_filas += n
            print(" ✓")
    finally:
        src.close()
        dst.close()

    print(f"\nTotal filas {'contadas' if args.dry_run else 'copiadas'}: {total_filas}")
    if errores:
        print(f"\n⚠ {len(errores)} tabla(s) con problemas:")
        for e in errores:
            print("  -", e)
        return 1
    print("✓ Migración completada." if not args.dry_run else "✓ Dry-run OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
