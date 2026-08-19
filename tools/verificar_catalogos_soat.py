"""¿Quedaron bien instaladas las tablas del SOAT 2026? Revisa y avisa.

Este chequeo lo corre el auditor, no un programador: por eso imprime en
español y termina diciendo VERIFICADO o FALLA, sin tecnicismos.

Revisa las dos tablas que sostienen cualquier defensa de tarifa:

  1) Homologador CUPS → SOAT (app/data/cups_soat_homologacion.json.gz)
     El puente entre el código que factura el hospital y el código del
     Manual Tarifario. Se revisa además que ningún CUPS haya vuelto a
     guardar la frase "NO TIENE HOMOLOGACION DIRECTA" como si fuera un
     código SOAT — ese era el defecto que se corrigió.

  2) Manual SOAT 2026 (app/data/soat_uvb_2026.json.gz)
     La tarifa oficial en UVB de la Circular Externa 047 de 2025, y su
     equivalente en pesos.

Uso:  python tools/verificar_catalogos_soat.py
      (o doble clic en tools/VERIFICAR_CATALOGOS_SOAT.cmd)
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Códigos escogidos a mano contra el PDF de la Circular 047/2025. Si el
# archivo se regenera mal, estas cifras son las primeras en cambiar.
_MUESTRA_SOAT = [
    ("19001", 5.93, "Acetaminofén"),
    ("19505", 0.567, "Hematocrito"),
    ("39205", 22.52, "Derechos de sala de cirugía, grupo 03"),
    ("513014", 1223.71, "Reemplazo protésico total primario de cadera"),
    ("518003", 279.87, "Cirugía artroscópica de rodilla, primer nivel"),
]

# CUPS escogidos del Gold Standard 2026.
_MUESTRA_CUPS = [
    ("039101", "39100"),  # con homologación
    ("013205", ""),  # sin homologación directa
]


def _pesos(valor: float) -> str:
    return "$" + f"{int(round(valor)):,}".replace(",", ".")


def _titulo(texto: str) -> None:
    print()
    print("═" * 72)
    print(f"  {texto}")
    print("═" * 72)


def main() -> int:
    import gzip
    import json

    from app.services import cups_soat_service as CS
    from app.services.tarifas_oficiales import (
        buscar_tarifa_soat_2026,
        tarifas_soat_2026_completas,
    )
    from app.services.uvb import UVB_2026

    fallas: list[str] = []
    tabla: dict = {}

    # ─── 1. Homologador CUPS → SOAT ────────────────────────────────────
    _titulo("1. HOMOLOGADOR CUPS → SOAT")
    ruta_h = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "app",
        "data",
        "cups_soat_homologacion.json.gz",
    )
    try:
        with gzip.open(ruta_h, "rt", encoding="utf-8") as f:
            homol = json.load(f)
        meta = homol.get("_meta", {})
        tabla = homol.get("cups_a_soat", {})  # noqa: F841 — se usa más abajo
        print(f"  Versión instalada .......... {meta.get('version', '(sin versión)')}")
        print(f"  Códigos CUPS ............... {len(tabla):,}".replace(",", "."))
        print(
            f"  Con artículo del Manual .... {meta.get('con_articulo_soat', 0):,}".replace(",", ".")
        )
        print(
            f"  Sin homologación directa ... {meta.get('sin_homologacion_directa', 0):,}".replace(
                ",", "."
            )
        )
        if meta.get("version") != "2026-GOLD-STANDARD":
            fallas.append(
                "El homologador NO es el del 2026 (versión instalada: "
                f"{meta.get('version')}). Falta actualizar el servidor."
            )
        if len(tabla) < 10_000:
            fallas.append(f"El homologador solo trae {len(tabla)} CUPS; deberían ser 10.024.")
    except OSError as e:
        fallas.append(f"No se pudo leer el homologador: {e}")

    print()
    print("  Prueba: ningún CUPS puede guardar una frase como si fuera código SOAT")
    inventados = [
        cups
        for cups in tabla
        for m in CS._crudos(cups)
        if str(m.get("soat") or "").strip().upper().startswith("NO TIENE")
    ]
    if inventados:
        fallas.append(f"{len(inventados)} CUPS todavía guardan un código SOAT inventado.")
        print(f"     FALLA — {len(inventados)} casos, por ejemplo {inventados[:3]}")
    else:
        print("     BIEN — cero casos.")

    print()
    for cups, soat_esperado in _MUESTRA_CUPS:
        homologaciones = CS.homologar_cups_a_soat(cups)
        if soat_esperado:
            ok = any(m.get("soat") == soat_esperado for m in homologaciones)
            print(f"  CUPS {cups} → SOAT {soat_esperado} .......... {'BIEN' if ok else 'FALLA'}")
            if not ok:
                fallas.append(f"El CUPS {cups} ya no homologa a SOAT {soat_esperado}.")
        else:
            ok = CS.sin_homologacion_directa(cups) and not homologaciones
            print(f"  CUPS {cups} → sin homologación directa ... {'BIEN' if ok else 'FALLA'}")
            if not ok:
                fallas.append(f"El CUPS {cups} debería quedar marcado sin homologación.")

    # ─── 2. Manual SOAT 2026 ───────────────────────────────────────────
    _titulo("2. MANUAL SOAT 2026 — Circular Externa 047 de 2025")
    catalogo = tarifas_soat_2026_completas()
    print(f"  Códigos con tarifa ......... {len(catalogo):,}".replace(",", "."))
    print(f"  Valor de la UVB 2026 ....... {_pesos(UVB_2026)}")
    if len(catalogo) < 1_500:
        fallas.append(
            f"El Manual SOAT solo trae {len(catalogo)} códigos; deberían ser más de 1.500. "
            "Falta el archivo app/data/soat_uvb_2026.json.gz en el servidor."
        )
    print()
    for codigo, uvb_esperado, nombre in _MUESTRA_SOAT:
        fila = buscar_tarifa_soat_2026(codigo)
        if fila is None:
            print(f"  {codigo} ...... FALLA (no está en el catálogo) — {nombre}")
            fallas.append(f"El código SOAT {codigo} no está en el catálogo.")
            continue
        ok = abs(fila["factor_uvb"] - uvb_esperado) < 0.0005
        print(
            f"  {codigo} ...... {'BIEN' if ok else 'FALLA'}  "
            f"{fila['factor_uvb']} UVB = {_pesos(fila['valor_pesos_2026'])}  — {nombre}"
        )
        if not ok:
            fallas.append(
                f"El código SOAT {codigo} dice {fila['factor_uvb']} UVB "
                f"y la Circular dice {uvb_esperado} UVB."
            )

    # ─── Veredicto ─────────────────────────────────────────────────────
    _titulo("RESULTADO")
    if fallas:
        print("  FALLA — el servidor NO tiene las tablas correctas:")
        for f_ in fallas:
            print(f"    • {f_}")
        print()
        print("  Qué hacer: en el servidor de cartera, esperar a que corra el")
        print("  autodeploy (cada 5 minutos) o forzarlo con tools/REINICIAR_MOTOR.cmd,")
        print("  y volver a correr esta verificación.")
        return 1

    print("  VERIFICADO — las dos tablas del SOAT 2026 están bien instaladas.")
    print()
    print("  El motor puede citar el artículo del Manual Tarifario, la tarifa")
    print("  oficial en UVB y su valor en pesos, y ya no le entrega a la IA un")
    print("  código SOAT inventado cuando el CUPS no tiene homologación.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
