"""No puede haber cuatro vigilantes (21-08-2026).

El autodeploy corre cada 5 minutos y SIEMPRE llama a
`arrancar_motor_glosas.cmd`, que abre el vigilante **sin preguntar si ya hay
uno**. Cada pasada abría otra ventana: el PC de cartera amaneció con **cuatro
ventanas «MotorGlosasServidor»** y cuatro motores, dos de ellos en el puerto
8000.

Eso no es solo desorden. Cada motor leyó las claves y el código **cuando
arrancó**, así que pueden estar mirando bases de datos distintas. El 20-08 eso
le escondió a la auditora su consolidado entero —1.189 facturas— y costó una
tarde entera entender por qué.

El vigilante ya sabía no arrancar dos motores. Lo que faltaba era que no
hubiera dos vigilantes.
"""

from __future__ import annotations

from pathlib import Path

RUTA = Path(__file__).resolve().parents[2] / "tools" / "servidor_motor_local.cmd"


def _texto() -> str:
    return RUTA.read_bytes().decode("utf-8", errors="replace")


class TestElCandadoExiste:
    def test_cuenta_los_vigilantes_antes_de_seguir(self):
        t = _texto()
        assert "servidor_motor_local" in t and "$n -gt 1" in t, (
            "Se perdió el candado: sin él, cada pasada del autodeploy abre "
            "otra ventana de vigilante."
        )

    def test_el_que_sobra_se_va_sin_arrancar_nada(self):
        t = _texto()
        i_candado = t.index("$n -gt 1")
        i_uvicorn = t.index("-m uvicorn")
        assert i_candado < i_uvicorn, (
            "El candado quedó DESPUÉS de arrancar uvicorn: no sirve de nada."
        )
        assert "exit /b 0" in t[i_candado : i_candado + 400]

    def test_deja_constancia_en_el_registro(self):
        """Si se cierra en silencio y sin dejar rastro, nadie entiende por qué
        la ventana desapareció."""
        t = _texto()
        i = t.index("$n -gt 1")
        assert "servidor.log" in t[i : i + 400]


class TestNoRompeLoQueYaFuncionaba:
    def test_sigue_sin_arrancar_dos_motores(self):
        """El bucle ya comprobaba que no hubiera otro uvicorn en el 8080. Eso
        es una proteccion distinta y tiene que seguir."""
        t = _texto()
        assert "--port\\s+8080" in t or "--port\\\\s+8080" in t or "8080" in t
        assert "uvicorn app.main:app" in t

    def test_sigue_leyendo_el_env(self):
        t = _texto()
        assert "%REPO%\\.env" in t

    def test_sigue_resolviendo_la_carpeta_de_soportes(self):
        t = _texto()
        assert "soportes_root.txt" in t
        assert "SOPORTES_ROOT" in t

    def test_conserva_los_finales_de_linea_de_windows(self):
        """Con finales de Unix la ventana se cierra sin ejecutar nada. Ya se
        sufrió antes en este repositorio."""
        b = RUTA.read_bytes()
        assert b.count(b"\r\n") > 50
        assert b.count(b"\n") == b.count(b"\r\n"), "hay saltos de línea sueltos"
