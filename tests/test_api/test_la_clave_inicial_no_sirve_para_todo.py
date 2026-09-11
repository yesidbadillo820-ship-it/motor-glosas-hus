"""Con la contraseña inicial sin cambiar, no se puede usar el motor.

11-09-2026. Auditoría externa, comprobada una por una contra el código antes
de tocar nada:

  1. La contraseña inicial de cada gestor es **la parte de su correo antes de
     la arroba** (`scripts/generar_excel_usuarios.py:136`).
  2. La lista de los 29 usuarios, con esa regla escrita en la hoja, vive en
     `docs/usuarios_motor_glosas.xlsx` y está en el repositorio desde la
     PR #303.
  3. El motor marcaba al usuario con `must_change_password`, el login lo
     devolvía y la pantalla lo mostraba… **pero nadie lo exigía**:
     `app/api/deps.py` ni lo mencionaba.

Juntando las tres: quien supiera el correo de un gestor entraba como él y
usaba la API entera sin cambiar nada. En un sistema con historias clínicas
eso no es deuda técnica, es una puerta abierta.

Lo delicado del arreglo es no encerrar a nadie: el que tiene clave temporal
TIENE que poder cambiarla, salirse y ver su propio nombre.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.auth import create_access_token, get_password_hash
from app.database import SessionLocal
from app.main import app
from app.models.db import UsuarioRecord

CLAVE_TEMPORAL = "claveinicial"
CLAVE_BUENA = "UnaClaveNueva9!"


@pytest.fixture
def gestor_con_clave_temporal():
    """Un usuario real de la base, marcado como recién creado. Se restaura."""
    db = SessionLocal()
    u = db.query(UsuarioRecord).first()
    if u is None:
        db.close()
        pytest.skip("no hay usuarios en la base de prueba")
    antes = (u.must_change_password, u.password_hash)
    u.must_change_password = 1
    u.password_hash = get_password_hash(CLAVE_TEMPORAL)
    db.commit()
    cabeceras = {"Authorization": f"Bearer {create_access_token({'sub': u.email})}"}
    try:
        yield u, cabeceras, db
    finally:
        u.must_change_password, u.password_hash = antes
        db.commit()
        db.close()


class TestConClaveTemporalNoSePuedeTrabajar:
    @pytest.mark.parametrize(
        "ruta",
        [
            "/glosas/alertas",
            "/analytics/",
            "/contratos/",
            "/admin/diagnostico",
            "/preauditoria/consolidado",
        ],
    )
    def test_las_pantallas_del_motor_quedan_cerradas(self, gestor_con_clave_temporal, ruta):
        _u, cabeceras, _db = gestor_con_clave_temporal
        with TestClient(app) as c:
            r = c.get(ruta, headers=cabeceras)
        assert r.status_code == 428, (
            f"{ruta} contestó {r.status_code}: la clave inicial todavía sirve para trabajar"
        )

    def test_el_mensaje_dice_qué_hacer(self, gestor_con_clave_temporal):
        _u, cabeceras, _db = gestor_con_clave_temporal
        with TestClient(app) as c:
            r = c.get("/glosas/alertas", headers=cabeceras)
        detalle = (r.json().get("detail") or "").lower()
        assert "contraseña" in detalle and "cambiar" in detalle


class TestPeroNadieQuedaEncerrado:
    """Si el que tiene clave temporal no pudiera cambiarla, sería peor."""

    def test_puede_cambiar_la_clave(self, gestor_con_clave_temporal):
        _u, cabeceras, _db = gestor_con_clave_temporal
        with TestClient(app) as c:
            r = c.post(
                "/auth/cambiar-password",
                headers=cabeceras,
                json={
                    "password_actual": CLAVE_TEMPORAL,
                    "password_nueva": CLAVE_BUENA,
                    "password_nueva_confirmacion": CLAVE_BUENA,
                },
            )
        assert r.status_code == 200, f"quedaría encerrado: {r.status_code} {r.text[:200]}"

    def test_puede_salirse(self, gestor_con_clave_temporal):
        _u, cabeceras, _db = gestor_con_clave_temporal
        with TestClient(app) as c:
            assert c.post("/auth/logout", headers=cabeceras).status_code == 200

    def test_puede_ver_su_propio_nombre(self, gestor_con_clave_temporal):
        """La pantalla saluda por el nombre antes de pedir la clave nueva."""
        _u, cabeceras, _db = gestor_con_clave_temporal
        with TestClient(app) as c:
            assert c.get("/usuarios/yo", headers=cabeceras).status_code == 200

    def test_tras_cambiarla_puede_trabajar(self, gestor_con_clave_temporal):
        u, cabeceras, db = gestor_con_clave_temporal
        with TestClient(app) as c:
            c.post(
                "/auth/cambiar-password",
                headers=cabeceras,
                json={
                    "password_actual": CLAVE_TEMPORAL,
                    "password_nueva": CLAVE_BUENA,
                    "password_nueva_confirmacion": CLAVE_BUENA,
                },
            )
            db.refresh(u)
            assert u.must_change_password == 0, "no se limpió la marca"
            assert c.get("/glosas/alertas", headers=cabeceras).status_code == 200


class TestElQueYaCambioSuClaveNoSeEntera:
    def test_todo_sigue_igual_de_normal(self):
        db = SessionLocal()
        u = db.query(UsuarioRecord).first()
        if u is None:
            db.close()
            pytest.skip("no hay usuarios")
        antes = u.must_change_password
        u.must_change_password = 0
        db.commit()
        cab = {"Authorization": f"Bearer {create_access_token({'sub': u.email})}"}
        try:
            with TestClient(app) as c:
                for ruta in ("/glosas/alertas", "/analytics/", "/contratos/"):
                    assert c.get(ruta, headers=cab).status_code != 428
        finally:
            u.must_change_password = antes
            db.commit()
            db.close()


class TestElGeneradorNoVuelveAUsarElCorreo:
    """La raíz: mientras la clave se derive del correo, el agujero vuelve."""

    def test_ya_no_deriva_la_clave_del_correo(self):
        """Se mira el CÓDIGO, no los comentarios: el comentario que explica
        el arreglo cita la línea vieja, y eso no es el defecto."""
        import ast
        from pathlib import Path

        arbol = ast.parse(Path("scripts/generar_excel_usuarios.py").read_text(encoding="utf-8"))
        codigo = ast.unparse(arbol).replace(" ", "")
        assert "split('@')[0]" not in codigo and 'split("@")[0]' not in codigo, (
            "la contraseña inicial vuelve a ser la parte del correo antes de la arroba"
        )

    def test_la_clave_inicial_es_impredecible(self):
        """Dos gestores no pueden nacer con la misma clave, ni una deducible."""
        import importlib.util
        from pathlib import Path

        spec = importlib.util.spec_from_file_location(
            "_gen", Path("scripts/generar_excel_usuarios.py")
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        claves = {mod._clave_inicial_al_azar() for _ in range(50)}
        assert len(claves) == 50, "se repiten claves iniciales"
        for c in claves:
            assert len(c) >= 12
            assert any(x.isdigit() for x in c), f"«{c}» sin números"
            assert any(not x.isalnum() for x in c), f"«{c}» sin símbolos"
            # Que no se confundan al dictarlas por teléfono.
            assert not set(c) & set("lI1O0"), f"«{c}» tiene caracteres que se confunden"

    def test_el_excel_de_credenciales_no_vuelve_al_repositorio(self):
        from pathlib import Path

        ignorados = Path(".gitignore").read_text(encoding="utf-8")
        assert "usuarios_motor_glosas.xlsx" in ignorados, (
            "sin esto, el archivo con los correos y sus claves iniciales se vuelve a subir"
        )
