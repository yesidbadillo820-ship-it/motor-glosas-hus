"""
nucleo.registro — Registro de entidades (EPS) y de bots existentes.

- Las entidades vienen de config/entidades.json (generado desde el Excel
  maestro RADICAR_FACTURAS_ENTIDADES.xlsx). Cada una trae su estado:
      OPERATIVA   → tiene plataforma de radicación definida
      POR_ARMAR   → solo hay correo; falta armar el proceso
      SIN_DATOS   → no hay ningún dato de radicación
- Los bots existentes (COOSALUD, MUTUAL SER, FOMAG, SIMED…) se registran en
  config/bots_registrados.json apuntando a su .bat / .py / .exe actual, para
  lanzarlos desde el menú único sin moverlos de donde están.
"""

import json
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUTA_ENTIDADES = os.path.join(BASE, "config", "entidades.json")
RUTA_CREDENCIALES = os.path.join(BASE, "config", "entidades.credenciales.json")
RUTA_BOTS = os.path.join(BASE, "config", "bots_registrados.json")

ETIQUETA_ESTADO = {
    "OPERATIVA": "🟢 Operativa",
    "POR_ARMAR": "🟡 Por armar (solo correo)",
    "SIN_DATOS": "🔴 Sin datos",
}

# Campos con secreto que viven FUERA del repo (en entidades.credenciales.json).
# entidades.json sólo guarda usuario/correo/portal; nunca la contraseña.
CAMPOS_SECRETOS = (
    ("radicacion", "contrasena"),
    ("cartera", "clave"),
    ("devoluciones", "credenciales"),
    ("glosas", "credenciales"),
)


# ------------------------------------------------------------------ entidades


def cargar_entidades():
    if not os.path.exists(RUTA_ENTIDADES):
        return []
    with open(RUTA_ENTIDADES, "r", encoding="utf-8") as f:
        entidades = json.load(f).get("entidades", [])
    _fusionar_credenciales(entidades)
    return entidades


def _fusionar_credenciales(entidades):
    """Superpone las credenciales del archivo local (no versionado) si existe.

    Así la Suite funciona con las contraseñas reales en el equipo del analista,
    pero el repositorio nunca las contiene. Se empareja por NIT y, si el NIT
    viene vacío, por nombre exacto.
    """
    if not os.path.exists(RUTA_CREDENCIALES):
        return
    try:
        with open(RUTA_CREDENCIALES, "r", encoding="utf-8") as f:
            overlay = json.load(f).get("credenciales", [])
    except (ValueError, OSError):
        return
    por_nit = {}
    por_nombre = {}
    for e in entidades:
        nit = str(e.get("nit", "")).strip()
        if nit:
            por_nit.setdefault(nit, e)
        por_nombre.setdefault(str(e.get("nombre", "")).strip().upper(), e)
    for entrada in overlay:
        nit = str(entrada.get("nit", "")).strip()
        nombre = str(entrada.get("nombre", "")).strip().upper()
        ent = por_nit.get(nit) if nit else None
        if ent is None:
            ent = por_nombre.get(nombre)
        if ent is None:
            continue
        for ruta_punto, valor in entrada.items():
            seccion, _, campo = ruta_punto.partition(".")
            if campo and valor:
                ent.setdefault(seccion, {})[campo] = valor


def buscar(entidades, texto):
    """Filtra por nombre o NIT (sin distinguir mayúsculas)."""
    t = texto.strip().upper()
    if not t:
        return entidades
    return [e for e in entidades if t in e["nombre"].upper() or t in str(e.get("nit", ""))]


def resumen_estados(entidades):
    conteo = {}
    for e in entidades:
        est = e.get("estado_radicacion", "SIN_DATOS")
        conteo[est] = conteo.get(est, 0) + 1
    return conteo


# ----------------------------------------------------------------------- bots


def cargar_bots():
    if not os.path.exists(RUTA_BOTS):
        return {}
    with open(RUTA_BOTS, "r", encoding="utf-8") as f:
        return json.load(f)


def guardar_bots(bots):
    with open(RUTA_BOTS, "w", encoding="utf-8") as f:
        json.dump(bots, f, ensure_ascii=False, indent=2)


def registrar_bot(nombre_entidad, nombre_bot, ruta):
    """Asocia un script/ejecutable existente a una entidad."""
    bots = cargar_bots()
    bots.setdefault(nombre_entidad, [])
    bots[nombre_entidad] = [b for b in bots[nombre_entidad] if b.get("nombre") != nombre_bot]
    bots[nombre_entidad].append({"nombre": nombre_bot, "ruta": ruta})
    guardar_bots(bots)
    return bots


def bots_de(nombre_entidad):
    return cargar_bots().get(nombre_entidad, [])


def ejecutar_bot(ruta, log=print):
    """Lanza el bot en una ventana propia (no bloquea la Suite)."""
    if not os.path.exists(ruta):
        log("[!] No existe la ruta del bot: %s" % ruta)
        log("    Actualícela con el botón 'Registrar bot'.")
        return False
    ext = os.path.splitext(ruta)[1].lower()
    carpeta = os.path.dirname(ruta) or "."
    try:
        if os.name == "nt":
            if ext in (".bat", ".cmd"):
                subprocess.Popen('start "" cmd /c "%s"' % ruta, shell=True, cwd=carpeta)
            elif ext == ".py":
                subprocess.Popen('start "" cmd /k python "%s"' % ruta, shell=True, cwd=carpeta)
            elif ext == ".ps1":
                subprocess.Popen(
                    'start "" powershell -ExecutionPolicy Bypass -File "%s"' % ruta,
                    shell=True,
                    cwd=carpeta,
                )
            else:
                os.startfile(ruta)  # exe, accesos directos, etc.
        else:  # entorno de pruebas fuera de Windows
            subprocess.Popen(
                [sys.executable, ruta] if ext == ".py" else ["bash", ruta], cwd=carpeta
            )
        log("Bot lanzado: %s" % os.path.basename(ruta))
        return True
    except Exception as e:
        log("[!] No se pudo lanzar el bot: %s" % e)
        return False
