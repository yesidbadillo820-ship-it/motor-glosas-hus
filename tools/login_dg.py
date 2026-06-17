"""login_dg.py — Lanza Dinámica Gerencial .NET y completa el login automáticamente.

Es el primer paso de la Fase 4 del orquestador. Solo loguea y deja DG abierto
en el DashBoard Principal — sin tocar más nada. Cuando este script funcione
de forma confiable, los siguientes scripts asumen "DG ya está abierto y
logueado" y se concentran en navegar al Editor de Trámite de Objeción para
cargar respuestas.

FLUJO QUE AUTOMATIZA
--------------------
1. Lanza C:\\...\\DG.WinDG.exe (o la ruta indicada en DG_EXE_PATH).
2. Espera ventana "Inicio de sesión".
3. Selecciona la empresa del dropdown (por defecto la que ya viene seleccionada).
4. Escribe usuario + contraseña (variables de entorno DG_USUARIO / DG_PASSWORD).
5. Click "Ingresar".
6. Espera la segunda pantalla "Inicio de sesión" con los radios de Área de
   Servicios.
7. Selecciona el área (DG_AREA, por defecto "Hospitalización").
8. Confirma centro de atención (DG_CENTRO, por defecto "01").
9. Click "Continuar".
10. Espera el "DashBoard Principal" como señal de sesión iniciada.

USO RÁPIDO
----------

    REM Una sola vez por máquina — credenciales en variables de entorno:
    setx DG_USUARIO BPY
    setx DG_PASSWORD tu_password
    REM Cerrá y reabrí la terminal para que tome las variables.

    py tools\\login_dg.py
    py tools\\login_dg.py --area "Hospitalizacion"
    py tools\\login_dg.py --no-cerrar     REM deja DG abierto al terminar
    py tools\\login_dg.py --con-ventanas  REM verbose: prints de cada control

DEPENDENCIAS
------------
    py -m pip install pywinauto

NOTA: pywinauto sólo funciona en Windows. Este script no corre en Linux/Mac.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

logger = logging.getLogger("login_dg")


DEFAULT_EXE = (
    Path(os.environ.get("LOCALAPPDATA", ""))
    / r"SYAC\Dinamica Gerencial .NET\1.0.0.0\DG.WinDG.exe"
)


def cargar_credenciales() -> tuple[str, str]:
    user = (os.environ.get("DG_USUARIO") or "").strip()
    password = (os.environ.get("DG_PASSWORD") or "").strip()
    if not user or not password:
        sys.stderr.write(
            "ERROR: faltan credenciales.\n"
            "Setealas con (una sola vez):\n"
            "    setx DG_USUARIO BPY\n"
            "    setx DG_PASSWORD tu_password\n"
            "Despues cerra y reabri la terminal.\n"
        )
        sys.exit(2)
    return user, password


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )


def _esperar(condicion, timeout_s: int, intervalo_s: float = 0.5, etiqueta: str = ""):
    """Polling simple: ejecuta condicion() cada `intervalo_s` y devuelve su
    resultado en cuanto sea truthy, o None al vencer `timeout_s`."""
    fin = time.time() + timeout_s
    while time.time() < fin:
        try:
            res = condicion()
        except Exception:
            res = None
        if res:
            return res
        time.sleep(intervalo_s)
    if etiqueta:
        logger.warning(f"  timeout esperando: {etiqueta}")
    return None


def _print_controles(dlg, prefijo: str = "  ") -> None:
    """Útil cuando algo no se encuentra: imprime el árbol de UIA del dialog."""
    try:
        dlg.print_control_identifiers(depth=6)
    except Exception as e:
        logger.warning(f"{prefijo}no pude imprimir controles: {e}")


def login(
    exe_path: Path,
    usuario: str,
    password: str,
    area: str,
    centro: str,
    timeout_inicial: int,
    con_ventanas: bool,
) -> None:
    """Hace todo el flujo de login y deja DG en el DashBoard Principal."""
    try:
        from pywinauto import Application
        from pywinauto.timings import Timings
    except ImportError:
        sys.stderr.write(
            "ERROR: falta pywinauto.\n"
            "    py -m pip install pywinauto\n"
        )
        sys.exit(2)

    # Hacer pywinauto un poco más paciente con el WPF de DG.
    Timings.fast()
    Timings.window_find_timeout = 30
    Timings.exists_timeout = 5
    Timings.after_clickinput_wait = 0.2

    if not exe_path.is_file():
        logger.error(f"No existe el ejecutable: {exe_path}")
        sys.exit(1)

    logger.info(f"Lanzando {exe_path.name} (puede tardar varios segundos en cargar)…")
    app = Application(backend="uia").start(f'"{exe_path}"', wait_for_idle=False)

    # ── 1) Esperar ventana 'Inicio de sesión' ──────────────────────────────
    logger.info("Esperando ventana 'Inicio de sesión'…")
    dlg_login = _esperar(
        lambda: Application(backend="uia")
        .connect(title_re=r"^Inicio de sesi[oó]n$", timeout=2)
        .window(title_re=r"^Inicio de sesi[oó]n$"),
        timeout_s=timeout_inicial,
        etiqueta="ventana de login",
    )
    if dlg_login is None:
        logger.error("No apareció la ventana de login. Cerrá DG a mano y reintentá.")
        sys.exit(1)
    logger.info("  ✓ ventana de login visible")
    if con_ventanas:
        _print_controles(dlg_login)

    # ── 2) Llenar Usuario y Contraseña ─────────────────────────────────────
    # La empresa viene preseleccionada (30-ESE Hospital Universitario de
    # Santander); no la tocamos. Si en algún momento aparece distinta,
    # agregamos el handling acá.
    logger.info(f"Escribiendo usuario: {usuario}")
    # Buscamos por placeholder/AutomationId típicos; si no, por orden de tabs.
    intento_input_usr = None
    for sel in (
        {"auto_id": "txtUsuario"},
        {"title_re": r"USUARIO"},
        {"control_type": "Edit", "found_index": 0},
    ):
        try:
            ctl = dlg_login.child_window(**sel)
            if ctl.exists():
                intento_input_usr = ctl
                break
        except Exception:
            continue
    if intento_input_usr is None:
        logger.error("No encontré el campo USUARIO. Volvé a correr con --con-ventanas y mandame el árbol.")
        _print_controles(dlg_login)
        sys.exit(1)
    intento_input_usr.click_input()
    intento_input_usr.type_keys(usuario, with_spaces=True, pause=0.02)

    logger.info("Escribiendo contraseña…")
    intento_input_pwd = None
    for sel in (
        {"auto_id": "txtPassword"},
        {"auto_id": "txtContrasena"},
        {"title_re": r"CONTRASE.A"},
        {"control_type": "Edit", "found_index": 1},
    ):
        try:
            ctl = dlg_login.child_window(**sel)
            if ctl.exists():
                intento_input_pwd = ctl
                break
        except Exception:
            continue
    if intento_input_pwd is None:
        logger.error("No encontré el campo CONTRASEÑA.")
        _print_controles(dlg_login)
        sys.exit(1)
    intento_input_pwd.click_input()
    intento_input_pwd.type_keys(password, with_spaces=True, pause=0.02)

    # ── 3) Click 'Ingresar' ────────────────────────────────────────────────
    logger.info("Click 'Ingresar'…")
    boton_ingresar = None
    for sel in (
        {"title_re": r"^Ingresar$", "control_type": "Button"},
        {"title_re": r"Ingresar"},
    ):
        try:
            ctl = dlg_login.child_window(**sel)
            if ctl.exists():
                boton_ingresar = ctl
                break
        except Exception:
            continue
    if boton_ingresar is None:
        logger.error("No encontré el botón 'Ingresar'.")
        _print_controles(dlg_login)
        sys.exit(1)
    boton_ingresar.click_input()

    # ── 4) Segunda ventana: Área de Servicios + Centro de Atención ─────────
    logger.info("Esperando segunda pantalla (Área de Servicios)…")
    dlg_area = _esperar(
        lambda: Application(backend="uia")
        .connect(title_re=r"^Inicio de sesi[oó]n$", timeout=2)
        .window(title_re=r"^Inicio de sesi[oó]n$"),
        timeout_s=30,
        etiqueta="segunda ventana de login",
    )
    if dlg_area is None:
        logger.error("No apareció la pantalla de Área de Servicios. ¿Usuario o contraseña incorrectos?")
        sys.exit(1)
    # Damos tiempo a que renderice los radios
    time.sleep(0.8)
    if con_ventanas:
        _print_controles(dlg_area)

    logger.info(f"Seleccionando área: {area}")
    radio = None
    for sel in (
        {"title_re": rf"^{area}$", "control_type": "RadioButton"},
        {"title_re": area, "control_type": "RadioButton"},
    ):
        try:
            ctl = dlg_area.child_window(**sel)
            if ctl.exists():
                radio = ctl
                break
        except Exception:
            continue
    if radio is None:
        logger.error(f"No encontré el radio para área {area!r}.")
        _print_controles(dlg_area)
        sys.exit(1)
    radio.click_input()

    # El centro normalmente viene en 01 por defecto; lo dejamos como está.
    # Si el usuario indicó otro centro, lo seteamos.
    if centro and centro != "01":
        try:
            combo = dlg_area.child_window(auto_id="cmbCentro")
            if not combo.exists():
                combo = dlg_area.child_window(control_type="ComboBox", found_index=0)
            combo.select(centro)
            logger.info(f"Centro de atención seteado: {centro}")
        except Exception as e:
            logger.warning(f"No pude setear centro {centro!r}: {e}")

    logger.info("Click 'Continuar'…")
    boton_continuar = None
    for sel in (
        {"title_re": r"^Continuar$", "control_type": "Button"},
        {"title_re": r"Continuar"},
    ):
        try:
            ctl = dlg_area.child_window(**sel)
            if ctl.exists():
                boton_continuar = ctl
                break
        except Exception:
            continue
    if boton_continuar is None:
        logger.error("No encontré el botón 'Continuar'.")
        _print_controles(dlg_area)
        sys.exit(1)
    boton_continuar.click_input()

    # ── 5) Esperar DashBoard Principal ─────────────────────────────────────
    logger.info("Esperando DashBoard Principal…")
    dlg_dash = _esperar(
        lambda: Application(backend="uia")
        .connect(title_re=r"DashBoard Principal.*Din[aá]mica Gerencial", timeout=2)
        .window(title_re=r"DashBoard Principal.*Din[aá]mica Gerencial"),
        timeout_s=60,
        etiqueta="DashBoard Principal",
    )
    if dlg_dash is None:
        logger.error("No detecté el DashBoard tras 60s.")
        sys.exit(1)
    logger.info("✓ Sesión iniciada — DG listo en DashBoard Principal.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--exe", type=Path, default=DEFAULT_EXE,
        help=f"Ruta a DG.WinDG.exe (default desde LOCALAPPDATA)."
    )
    parser.add_argument(
        "--area", default=os.environ.get("DG_AREA", "Hospitalización"),
        help="Área de servicios a seleccionar (default Hospitalización)."
    )
    parser.add_argument(
        "--centro", default=os.environ.get("DG_CENTRO", "01"),
        help="Código de centro de atención (default 01)."
    )
    parser.add_argument(
        "--timeout-inicial", type=int, default=60,
        help="Segundos máx esperando la ventana de login (default 60)."
    )
    parser.add_argument(
        "--con-ventanas", action="store_true",
        help="Imprime el árbol de controles UIA de cada ventana (debug)."
    )
    args = parser.parse_args()
    setup_logging(args.con_ventanas)

    if sys.platform != "win32":
        logger.error("Este script solo corre en Windows (DG es .NET WPF nativo).")
        return 2

    usuario, password = cargar_credenciales()
    logger.info(f"DG_USUARIO={usuario}  EXE={args.exe}")
    login(
        exe_path=args.exe,
        usuario=usuario,
        password=password,
        area=args.area,
        centro=args.centro,
        timeout_inicial=args.timeout_inicial,
        con_ventanas=args.con_ventanas,
    )
    logger.info("Login OK. DG queda abierto y listo para los siguientes pasos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
