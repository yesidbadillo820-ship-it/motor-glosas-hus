"""
separar_credenciales — Saca las contraseñas de config/entidades.json a un
archivo local que NO se versiona (config/entidades.credenciales.json).

Por qué: entidades.json se comparte y se guarda en el repositorio. Las
contraseñas de los portales NO pueden quedar en el repositorio. Este script
deja en entidades.json sólo la información no sensible (portal, usuario,
correo, contacto, estado) y guarda las contraseñas aparte, en el equipo.

Cuándo correrlo: una sola vez para migrar, y cada vez que se regenere
entidades.json desde el Excel maestro RADICAR_FACTURAS_ENTIDADES.xlsx.

Uso:
    python herramientas/separar_credenciales.py
    python herramientas/separar_credenciales.py ruta/a/entidades.json

La Suite (nucleo.registro) vuelve a unir las dos partes en memoria al abrir,
así que el analista sigue viendo todo completo en su equipo.
"""

import json
import os
import shutil
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Debe coincidir con nucleo.registro.CAMPOS_SECRETOS
CAMPOS_SECRETOS = (
    ("radicacion", "contrasena"),
    ("cartera", "clave"),
    ("devoluciones", "credenciales"),
    ("glosas", "credenciales"),
)

CABECERA_OVERLAY = (
    "Contraseñas de los portales — ARCHIVO LOCAL, NO SE SUBE AL REPOSITORIO. "
    "La Suite lo une con entidades.json al abrir (emparejando por NIT/nombre). "
    "Si regenera entidades.json desde el Excel, vuelva a correr "
    "herramientas/separar_credenciales.py."
)


def separar(ruta_entidades):
    with open(ruta_entidades, "r", encoding="utf-8") as f:
        data = json.load(f)
    entidades = data.get("entidades", [])

    overlay = []
    n_campos = 0
    for e in entidades:
        campos = {}
        for seccion, campo in CAMPOS_SECRETOS:
            valor = (e.get(seccion) or {}).get(campo)
            if isinstance(valor, str) and valor.strip():
                campos["%s.%s" % (seccion, campo)] = valor
                e[seccion][campo] = ""  # redactar en la parte pública
                n_campos += 1
        if campos:
            entrada = {"nit": e.get("nit", ""), "nombre": e.get("nombre", "")}
            entrada.update(campos)
            overlay.append(entrada)

    return data, overlay, n_campos


def main(argv):
    ruta_entidades = argv[1] if len(argv) > 1 else os.path.join(BASE, "config", "entidades.json")
    if not os.path.exists(ruta_entidades):
        print("[X] No existe: %s" % ruta_entidades)
        return 1

    data, overlay, n_campos = separar(ruta_entidades)
    if n_campos == 0:
        print(
            "[i] No se encontraron contraseñas en %s. Ya estaba limpio: "
            "no se toca nada." % os.path.basename(ruta_entidades)
        )
        return 0

    carpeta = os.path.dirname(ruta_entidades)
    ruta_overlay = os.path.join(carpeta, "entidades.credenciales.json")
    ruta_ejemplo = os.path.join(carpeta, "entidades.credenciales.example.json")

    # 1) sobrescribir entidades.json ya redactado (sin contraseñas)
    with open(ruta_entidades, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    # 2) escribir el overlay local; si ya existía, respaldarlo antes
    if os.path.exists(ruta_overlay):
        shutil.copy2(ruta_overlay, ruta_overlay + ".bak")
        print("[i] Respaldo del overlay previo: %s.bak" % os.path.basename(ruta_overlay))
    with open(ruta_overlay, "w", encoding="utf-8") as f:
        json.dump(
            {"_LEAME": CABECERA_OVERLAY, "credenciales": overlay}, f, ensure_ascii=False, indent=1
        )

    # 3) escribir un ejemplo versionable (estructura, sin secretos reales)
    ejemplo = {
        "_LEAME": CABECERA_OVERLAY,
        "credenciales": [
            {
                "nit": "900006037",
                "nombre": "EJEMPLO EPS S.A.S.",
                "radicacion.contrasena": "PEGUE_AQUI_LA_CLAVE",
                "devoluciones.credenciales": "USUARIO: xxxx\nCONTRASEÑA: xxxx",
            }
        ],
    }
    with open(ruta_ejemplo, "w", encoding="utf-8") as f:
        json.dump(ejemplo, f, ensure_ascii=False, indent=1)

    print(
        "[OK] %d contraseñas movidas a %s (local, no versionado)."
        % (n_campos, os.path.basename(ruta_overlay))
    )
    print("     entidades.json quedó SIN contraseñas (apto para el repositorio).")
    print("     Plantilla de referencia: %s" % os.path.basename(ruta_ejemplo))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
