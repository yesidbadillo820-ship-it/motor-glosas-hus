"""Arranque unificado del motor (03-09-2026) — incidente del 8080 a medias.

QUÉ PASÓ. El motor de la página llevaba horas corriendo mal configurado: la
pantalla de Diagnóstico mostraba la carpeta de soportes en rojo («/data/soportes
no existe») y el piloto automático apagado, aunque el código estaba desplegado y
`config/soportes_root.txt` intacto.

La causa NO era la ruta. Dos rutas de rescate —`autodeploy_motor_local.cmd` y
`ACTUALIZAR_PAGINA.cmd`— arrancaban **uvicorn crudo**, sin preparar el entorno:
sin `SOPORTES_ROOT`, sin `AUTO_PILOT_ENABLED` y sin releer el `.env` del día. Ese
motor a medias ocupaba el puerto 8080, y el vigilante de verdad se quedaba
PARQUEADO esperando su turno — así que el motor a medias se quedaba arriba
indefinidamente.

Y encima ese rescate dejaba `data\\servidor.log` tomado por su propia
redirección, con lo que el vigilante oficial —al apartarse— no podía ni escribir
su nota de despedida: el auditor solo veía el error crudo de Windows «el proceso
no tiene acceso al archivo porque está siendo utilizado por otro proceso», sin
ninguna explicación de que el script se estaba apartando a propósito.

LO QUE ESTAS PRUEBAS CUIDAN:

1. UNA SOLA PUERTA. Solo `servidor_motor_local.cmd` arranca el motor del 8080.
   Cualquier rescate o despliegue pasa por él y hereda el entorno completo.
2. EL VIGILANTE HABLA POR PANTALLA. Sus avisos no viven solo en un archivo que
   puede estar bloqueado.
3. EL REGISTRO NO MANDA. Un bloqueo de `servidor.log` no puede silenciar ni
   tumbar el arranque.
4. CRLF. Son bots de doble clic para Windows: si pierden el CRLF, no corren.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
TOOLS = RAIZ / "tools"

VIGILANTE = TOOLS / "servidor_motor_local.cmd"
AUTODEPLOY = TOOLS / "autodeploy_motor_local.cmd"
ACTUALIZAR = TOOLS / "ACTUALIZAR_PAGINA.cmd"
REINICIAR = TOOLS / "REINICIAR_MOTOR.cmd"

# Los cuatro bots que toca este arreglo. Todos son de doble clic en Windows.
TOCADOS = [VIGILANTE, AUTODEPLOY, ACTUALIZAR, REINICIAR]


def _texto(ruta: Path) -> str:
    return ruta.read_bytes().decode("utf-8", errors="replace")


def _lineas_de_codigo(ruta: Path) -> list[str]:
    """Las líneas que EJECUTAN algo: sin comentarios (rem/REM) ni vacías.

    Sin esto, las pruebas se engañan solas: los comentarios de estos bots
    citan el código viejo para explicar por qué se cambió.
    """
    fuera = []
    for linea in _texto(ruta).splitlines():
        limpia = linea.strip()
        if not limpia or re.match(r"^(rem\b|::)", limpia, re.IGNORECASE):
            continue
        fuera.append(linea)
    return fuera


class TestUnaSolaPuertaDeArranque:
    """El motor del 8080 lo arranca UNO solo: el vigilante oficial."""

    def test_el_vigilante_es_el_unico_que_lanza_el_motor_del_8080(self):
        culpables = []
        for cmd in sorted(TOOLS.glob("*.cmd")):
            if cmd == VIGILANTE:
                continue
            for linea in _lineas_de_codigo(cmd):
                # Solo importan los ARRANQUES, no los PowerShell que buscan
                # procesos por su línea de órdenes.
                if "CommandLine" in linea:
                    continue
                if "uvicorn app.main:app" in linea and "8080" in linea:
                    culpables.append(f"{cmd.name}: {linea.strip()[:110]}")
        assert not culpables, (
            "arranque crudo del motor de la página fuera del vigilante:\n" + "\n".join(culpables)
        )

    @pytest.mark.parametrize(
        "ruta", [AUTODEPLOY, ACTUALIZAR], ids=["autodeploy", "actualizar_pagina"]
    )
    def test_el_rescate_entra_por_la_puerta_oficial(self, ruta: Path):
        codigo = "\n".join(_lineas_de_codigo(ruta))
        assert "servidor_motor_local.cmd" in codigo, (
            f"{ruta.name} ya no arranca el motor por el camino oficial"
        )
        arranques = [
            ln for ln in _lineas_de_codigo(ruta) if ln.strip().lower().startswith("start ")
        ]
        motores = [ln for ln in arranques if "8080" in ln or "servidor_motor_local" in ln]
        assert motores, f"{ruta.name}: no se encontró el arranque del motor"
        for ln in motores:
            assert "servidor_motor_local.cmd" in ln, (
                f"{ruta.name} arranca el motor sin pasar por el vigilante: {ln.strip()[:110]}"
            )

    def test_el_rescate_ya_no_se_queda_con_el_registro_tomado(self):
        """El `cmd /s /c ... >> servidor.log` del rescate era quien tenía el
        archivo bloqueado. Ese patrón no puede volver."""
        for ruta in (AUTODEPLOY, ACTUALIZAR):
            for linea in _lineas_de_codigo(ruta):
                if linea.strip().lower().startswith("start ") and "servidor.log" in linea:
                    pytest.fail(
                        f"{ruta.name} vuelve a dejar servidor.log tomado por un arranque: "
                        f"{linea.strip()[:110]}"
                    )

    def test_el_vigilante_sigue_arrancando_el_motor(self):
        """No vaya a ser que, de tanto quitar, quede nadie arrancándolo."""
        codigo = "\n".join(_lineas_de_codigo(VIGILANTE))
        assert "-m uvicorn app.main:app" in codigo
        assert "--port 8080" in codigo

    def test_el_vigilante_prepara_el_ecosistema_completo(self):
        codigo = "\n".join(_lineas_de_codigo(VIGILANTE))
        for variable in ("SOPORTES_ROOT", "SOPORTES_LOCAL_ROOT", "AUTO_PILOT_ENABLED"):
            assert f'set "{variable}=' in codigo, f"el vigilante ya no prepara {variable}"
        assert ".env" in codigo, "el vigilante ya no relee el .env del día"


class TestElVigilanteHablaPorPantalla:
    """Lo que le pasó al auditor: un aviso que solo existía en un archivo."""

    def _bloque_del_guardian(self) -> str:
        t = _texto(VIGILANTE)
        i = t.index("if errorlevel 1 (")
        return t[i : t.index("exit /b 0", i) + len("exit /b 0")]

    def test_avisa_por_consola_que_ya_hay_un_vigilante(self):
        bloque = self._bloque_del_guardian()
        avisos = [
            ln.strip()
            for ln in bloque.splitlines()
            if ln.strip().lower().startswith("echo") and ">>" not in ln
        ]
        assert avisos, "el guardián no dice NADA por pantalla al apartarse"
        assert any("vigilante" in a.lower() for a in avisos), (
            "el aviso por pantalla no explica que ya hay un vigilante"
        )

    def test_el_aviso_al_registro_no_puede_tumbar_el_arranque(self):
        bloque = self._bloque_del_guardian()
        crudas = [ln for ln in bloque.splitlines() if ">>" in ln and "2>nul" not in ln]
        assert not crudas, (
            "el guardián vuelve a escribir al registro sin protección "
            f"(un bloqueo imprimiría el error crudo de Windows): {crudas}"
        )
        assert "call :log_seguro" in bloque

    def test_existe_la_rutina_que_traga_el_bloqueo(self):
        t = _texto(VIGILANTE)
        assert ":log_seguro" in t
        i = t.index("\n:log_seguro")
        rutina = t[i : i + 300]
        assert "2>nul" in rutina, "log_seguro no traga el error del archivo tomado"
        assert "exit /b 0" in rutina, "log_seguro no devuelve el control al vigilante"

    def test_el_registro_esta_definido_antes_de_usarse(self):
        """El guardián corre ANTES de donde estaba definido %LOG%."""
        t = _texto(VIGILANTE)
        assert t.index('set "LOG=') < t.index("if errorlevel 1 ("), (
            "%LOG% se define después del guardián que ya lo usa"
        )

    def test_un_registro_bloqueado_no_impide_arrancar_el_motor(self):
        """Si servidor.log está tomado, la redirección de uvicorn falla y el
        motor NO arranca. Tiene que haber salida alterna."""
        codigo = "\n".join(_lineas_de_codigo(VIGILANTE))
        assert "servidor.alterno.log" in codigo, (
            "no hay registro alterno: un archivo bloqueado dejaría la página caída en silencio"
        )
        i = codigo.index("servidor.alterno.log")
        assert "2>nul" in codigo[max(0, i - 400) : i], (
            "la comprobación del registro no está protegida"
        )


class TestElMotorDePruebasNoSeRompio:
    """REINICIAR_MOTOR.cmd es OTRA cosa: el motor local del auditor (8000, en
    primer plano, ventana abierta). No es rescate ni despliegue — no debe pasar
    por el vigilante, pero sí merece el mismo entorno."""

    def test_sigue_arrancando_su_propio_motor_en_su_puerto(self):
        codigo = "\n".join(_lineas_de_codigo(REINICIAR))
        assert "-m uvicorn app.main:app --port %PUERTO%" in codigo
        assert "servidor_motor_local.cmd" not in codigo, (
            "el motor de pruebas no puede convertirse en el de la página (puerto y ventana distintos)"
        )

    def test_ahora_prepara_el_mismo_ecosistema(self):
        codigo = "\n".join(_lineas_de_codigo(REINICIAR))
        for variable in ("SOPORTES_ROOT", "SOPORTES_LOCAL_ROOT", "AUTO_PILOT_ENABLED"):
            assert variable in codigo, f"el motor de pruebas sigue sin {variable}"
        assert "soportes_root.txt" in codigo

    def test_el_env_del_auditor_le_gana_al_valor_por_defecto(self):
        """`if not defined` — lo que ya venga del .env manda."""
        codigo = "\n".join(_lineas_de_codigo(REINICIAR))
        for variable in ("SOPORTES_ROOT", "SOPORTES_LOCAL_ROOT", "AUTO_PILOT_ENABLED"):
            assert re.search(rf"if not defined {variable}\b", codigo), (
                f"{variable} se pisa aunque el .env ya la traiga"
            )


class TestFormatoDeLosBots:
    """Sin CRLF estos bots no corren en Windows."""

    @pytest.mark.parametrize("ruta", TOCADOS, ids=lambda r: r.name)
    def test_finales_de_linea_crlf(self, ruta: Path):
        crudo = ruta.read_bytes()
        assert b"\r\n" in crudo, f"{ruta.name} perdió los finales de línea CRLF"
        assert b"\n" not in crudo.replace(b"\r\n", b""), (
            f"{ruta.name} tiene líneas sueltas en LF (mezcla de finales)"
        )

    def test_la_regla_del_repositorio_sigue_puesta(self):
        ga = (RAIZ / ".gitattributes").read_text(encoding="utf-8", errors="replace")
        assert re.search(r"\*\.cmd\s+text\s+eol=crlf", ga), (
            "se perdió la regla de .gitattributes que fuerza CRLF en los .cmd"
        )
