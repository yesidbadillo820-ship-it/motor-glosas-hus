"""¿Quién sigue entrando con la contraseña que le pusimos el primer día?

11-09-2026. Hasta hoy la contraseña inicial de cada gestor era **la parte de
su correo antes de la arroba**. Eso ya se corrigió para los usuarios nuevos,
y el motor ya no deja trabajar a quien no la haya cambiado.

Pero eso no arregla a los que YA estaban. Si alguno entró alguna vez y el
motor le quitó la marca sin exigirle el cambio —que es justo lo que pasaba—,
hoy sigue con una contraseña que cualquiera deduce de su correo.

Este programa lo revisa. No adivina: agarra la contraseña que tendría cada
quien según la regla vieja y la compara contra lo que hay guardado en la
base. Si coincide, esa cuenta está abierta de par en par.

CÓMO SE USA — desde la carpeta del motor, con la sesión normal de Windows
(no hace falta «ejecutar como administrador»):

    rem  1) Ver quién está en riesgo. No cambia NADA.
    venv\\Scripts\\python.exe tools\\revisar_claves_iniciales.py

    rem  2) Obligarlos a cambiarla en su próximo ingreso.
    venv\\Scripts\\python.exe tools\\revisar_claves_iniciales.py --marcar

Con `--marcar` NO se le cambia la contraseña a nadie ni se le saca de la
sesión: simplemente, la próxima vez que entre, el motor le pedirá una nueva
antes de dejarlo usar cualquier pantalla.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def _clave_de_la_regla_vieja(email: str) -> str:
    """La que el generador ponía: el correo sin la arroba ni el dominio."""
    return (email or "").split("@")[0]


def revisar(marcar: bool = False) -> int:
    from app.auth import verify_password
    from app.database import SessionLocal
    from app.models.db import UsuarioRecord

    db = SessionLocal()
    try:
        usuarios = db.query(UsuarioRecord).order_by(UsuarioRecord.email).all()
        en_riesgo = []
        ya_marcados = []
        for u in usuarios:
            candidata = _clave_de_la_regla_vieja(u.email)
            if not candidata or not u.password_hash:
                continue
            try:
                coincide = verify_password(candidata, u.password_hash)
            except Exception:  # noqa: BLE001 — un hash raro no tumba la revisión
                continue
            if coincide:
                (ya_marcados if u.must_change_password else en_riesgo).append(u)

        print()
        print("=" * 68)
        print("  ¿QUIÉN SIGUE CON LA CONTRASEÑA DEL PRIMER DÍA?")
        print("=" * 68)
        print(f"  Usuarios revisados ................. {len(usuarios)}")
        print(f"  Con la clave vieja Y ya marcados ... {len(ya_marcados)}  (el motor ya los frena)")
        print(f"  Con la clave vieja SIN marcar ...... {len(en_riesgo)}  <-- estos entran a todo")
        print()

        if not en_riesgo:
            print("  No hay nadie en riesgo. Nada que hacer.")
            print()
            return 0

        print("  En riesgo:")
        for u in en_riesgo:
            print(f"     · {u.email:<38} ({u.rol})")
        print()

        if not marcar:
            print("  Esto NO cambió nada. Para que el motor les exija una contraseña")
            print("  nueva en su próximo ingreso, vuelva a correrlo con  --marcar")
            print()
            return 1

        for u in en_riesgo:
            u.must_change_password = 1
        db.commit()
        print(f"  Listo: {len(en_riesgo)} cuenta(s) marcadas.")
        print("  A nadie se le cambió la contraseña ni se le sacó de la sesión.")
        print("  La próxima vez que entren, el motor les pedirá una nueva antes")
        print("  de dejarlos abrir cualquier pantalla.")
        print()
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--marcar",
        action="store_true",
        help="obligarlos a cambiar la contraseña en el próximo ingreso",
    )
    return revisar(marcar=ap.parse_args(argv).marcar)


if __name__ == "__main__":
    raise SystemExit(main())
