"""La herramienta que encuentra a quién le quedó la contraseña del primer día.

El arreglo de `deps.py` frena a quien esté marcado con `must_change_password`.
Pero eso no alcanza para los usuarios que YA existían: si alguno entró alguna
vez y el motor le quitó la marca sin exigirle el cambio —que es exactamente lo
que pasaba—, hoy sigue con una contraseña deducible de su correo y el arreglo
no lo toca.

Esta herramienta los encuentra comparando, no adivinando.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from tools.revisar_claves_iniciales import _clave_de_la_regla_vieja, main  # noqa: E402


class TestLaReglaVieja:
    def test_es_el_correo_sin_la_arroba(self):
        assert _clave_de_la_regla_vieja("glosashus04@sinacsc.com") == "glosashus04"

    def test_aguanta_un_correo_raro(self):
        assert _clave_de_la_regla_vieja("") == ""
        assert _clave_de_la_regla_vieja("sinarroba") == "sinarroba"


class TestNoCambiaNadaSiNoSeLoPiden:
    def test_sin_marcar_no_toca_la_base(self, capsys):
        """Correrla sin `--marcar` tiene que ser inofensivo: el auditor la
        corre para mirar, no para cambiar."""
        from app.database import SessionLocal
        from app.models.db import UsuarioRecord

        db = SessionLocal()
        antes = {u.email: u.must_change_password for u in db.query(UsuarioRecord).all()}
        db.close()

        main([])

        db = SessionLocal()
        despues = {u.email: u.must_change_password for u in db.query(UsuarioRecord).all()}
        db.close()
        assert antes == despues, "la revisión sin --marcar cambió la base"

    def test_dice_lo_que_encontro(self, capsys):
        main([])
        salida = capsys.readouterr().out
        assert "Usuarios revisados" in salida
        assert "SIN marcar" in salida

    def test_nunca_escribe_una_contraseña(self):
        """La garantía de fondo, leída del código: esta herramienta NO tiene
        por qué tocar `password_hash`. Si algún día lo hiciera, dejaría de ser
        una revisión y pasaría a ser un cambio masivo de claves."""
        import ast

        import tools.revisar_claves_iniciales as mod

        arbol = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
        asignados = {
            n.attr
            for n in ast.walk(arbol)
            if isinstance(n, ast.Attribute) and isinstance(n.ctx, ast.Store)
        }
        assert "password_hash" not in asignados, (
            "la revisión está escribiendo contraseñas: eso no es revisar"
        )
        assert "must_change_password" in asignados, "entonces --marcar no hace nada"


class TestMarcarNoRompeNada:
    def test_marcar_no_cambia_ninguna_contraseña(self):
        """Lo importante: marcar NO le cambia la clave a nadie ni lo saca de
        la sesión. Solo le pide una nueva la próxima vez que entre."""
        from app.database import SessionLocal
        from app.models.db import UsuarioRecord

        db = SessionLocal()
        hashes_antes = {u.email: u.password_hash for u in db.query(UsuarioRecord).all()}
        marcas_antes = {u.email: u.must_change_password for u in db.query(UsuarioRecord).all()}
        db.close()

        main(["--marcar"])

        db = SessionLocal()
        usuarios = db.query(UsuarioRecord).all()
        hashes_despues = {u.email: u.password_hash for u in usuarios}
        # Se restaura lo que la prueba haya podido marcar.
        for u in usuarios:
            u.must_change_password = marcas_antes.get(u.email, u.must_change_password)
        db.commit()
        db.close()

        assert hashes_antes == hashes_despues, "le cambió la contraseña a alguien"
