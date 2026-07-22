#!/usr/bin/env python3
"""HOSPIAI — DSL de reglas de negocio (Fase 1.6).

Lenguaje propio para que un AUDITOR FUNCIONAL escriba las reglas sin saber
programar. El compilador las convierte al JSON del motor existente
(data/reglas_radicacion.json), así el motor no cambia: cambia quién puede
mantener el conocimiento.

Ejemplo (archivo .hospiai, una o varias reglas):

    VERSION 2.0

    REGLA CIRUGIA_MAYOR
    SI SERVICIO = CIRUGIA
    REQUIERE DQX RAN EPI HEV
    SI FALTA REVISAR
    FUENTE Resolución 2284 de 2023
    VIGENCIA DESDE 2024-01-01
    NOTA La cirugía exige descripción quirúrgica, anestesia y epicrisis.
    FIN

Palabras clave: REGLA/FIN, SI SERVICIO = <servicio> | SI TODAS,
REQUIERE <códigos>, SI FALTA BLOQUEAR|REVISAR|ADVERTIR, FUENTE, CRITICIDAD,
VIGENCIA DESDE/HASTA, NOTA, EQUIVALENCIA <COD> = <códigos>, VERSION.
Comentarios con '#'. Mayúsculas/minúsculas indistintas en las palabras clave.

Uso:
    py tools\\hospiai_dsl.py verificar data\\reglas.hospiai
    py tools\\hospiai_dsl.py compilar  data\\reglas.hospiai --salida data\\reglas_radicacion.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

# Servicio "humano" → clave del RIPS que usa el motor.
SERVICIOS = {
    "CONSULTA": "consultas",
    "CONSULTAS": "consultas",
    "PROCEDIMIENTO": "procedimientos",
    "PROCEDIMIENTOS": "procedimientos",
    "CIRUGIA": "procedimientos",
    "CIRUGÍA": "procedimientos",
    "URGENCIA": "urgencias",
    "URGENCIAS": "urgencias",
    "HOSPITALIZACION": "hospitalizacion",
    "HOSPITALIZACIÓN": "hospitalizacion",
    "MEDICAMENTO": "medicamentos",
    "MEDICAMENTOS": "medicamentos",
    "OTROS": "otrosServicios",
    "OTROSSERVICIOS": "otrosServicios",
    "RECIENNACIDOS": "recienNacidos",
    "RECIEN NACIDOS": "recienNacidos",
}

# SI FALTA <acción> → (criticidad, accion) del motor.
ACCIONES = {
    "BLOQUEAR": ("BLOQUEA_RADICACION", "BLOQUEAR_RADICACION"),
    "REVISAR": ("REVISAR", "REVISAR_ANTES_DE_RADICAR"),
    "ADVERTIR": ("ADVERTENCIA", "ADVERTIR"),
}

_RE_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class ErrorDSL(ValueError):
    """Error de compilación con línea y motivo, para que el auditor lo corrija."""


def _err(num: int, linea: str, motivo: str) -> ErrorDSL:
    return ErrorDSL(f"línea {num}: {motivo}\n    → {linea.strip()}")


def compilar(texto: str) -> dict:
    """Compila el DSL al formato del motor (mismo esquema que
    data/reglas_radicacion.json). Falla con línea y motivo ante cualquier
    ambigüedad: una regla de negocio jamás se adivina."""
    version = "1.0"
    equivalencias: dict[str, list[str]] = {}
    reglas: list[dict] = []
    actual: dict | None = None

    for num, cruda in enumerate(texto.splitlines(), 1):
        linea = cruda.split("#", 1)[0].strip()
        if not linea:
            continue
        u = linea.upper()

        if u.startswith("VERSION "):
            version = linea.split(None, 1)[1].strip()
        elif u.startswith("EQUIVALENCIA "):
            m = re.match(r"(?i)^EQUIVALENCIA\s+(\w+)\s*=\s*(.+)$", linea)
            if not m:
                raise _err(num, cruda, "se esperaba: EQUIVALENCIA COD = COD1 COD2 …")
            equivalencias[m.group(1).upper()] = [c.upper() for c in m.group(2).split()]
        elif u.startswith("REGLA"):
            if actual is not None:
                raise _err(num, cruda, f"la regla {actual['id']} no se cerró con FIN")
            partes = linea.split(None, 1)
            if len(partes) < 2:
                raise _err(num, cruda, "REGLA necesita un nombre (REGLA CIRUGIA_MAYOR)")
            actual = {
                "id": partes[1].strip().upper().replace(" ", "_"),
                "ambito": {},
                "exige": [],
                "criticidad": "REVISAR",
                "accion": "REVISAR_ANTES_DE_RADICAR",
                "fuente": "",
                "nota": "",
                "vigencia_desde": "",
                "vigencia_hasta": "",
            }
        elif actual is None:
            raise _err(num, cruda, "instrucción fuera de una REGLA … FIN")
        elif u == "FIN":
            if not actual["ambito"]:
                raise _err(
                    num, cruda, f"{actual['id']}: falta el ámbito (SI SERVICIO = … | SI TODAS)"
                )
            reglas.append(actual)
            actual = None
        elif u == "SI TODAS" or u == "SI SIEMPRE":
            actual["ambito"] = {"aplica": "todas"}
        elif u.startswith("SI SERVICIO"):
            m = re.match(r"(?i)^SI\s+SERVICIO\s*=\s*(.+)$", linea)
            if not m:
                raise _err(num, cruda, "se esperaba: SI SERVICIO = <servicio>")
            nombre = m.group(1).strip().upper()
            serv = SERVICIOS.get(nombre) or SERVICIOS.get(nombre.replace(" ", ""))
            if serv is None:
                raise _err(
                    num,
                    cruda,
                    f"servicio desconocido '{m.group(1).strip()}'. "
                    f"Válidos: {sorted(set(SERVICIOS))}",
                )
            actual["ambito"] = {"servicio": serv}
        elif u.startswith("SI FALTA"):
            accion = u.replace("SI FALTA", "", 1).strip()
            if accion not in ACCIONES:
                raise _err(num, cruda, f"acción desconocida '{accion}'. Válidas: {list(ACCIONES)}")
            actual["criticidad"], actual["accion"] = ACCIONES[accion]
        elif u.startswith(("REQUIERE", "ENTONCES REQUIERE")):
            cods = linea.split("REQUIERE", 1)[1] if "REQUIERE" in linea else ""
            cods = re.split(r"[\s,]+", cods.strip())
            nuevos = [c.upper() for c in cods if c]
            if not nuevos:
                raise _err(num, cruda, "REQUIERE necesita al menos un código (DQX RAN …)")
            actual["exige"].extend(c for c in nuevos if c not in actual["exige"])
        elif u.startswith("FUENTE"):
            actual["fuente"] = linea.split(None, 1)[1].strip() if " " in linea else ""
        elif u.startswith("CRITICIDAD"):
            # Metadatos del negocio (ALTA/MEDIA/BAJA); el comportamiento lo
            # define SI FALTA. Se conserva para los informes.
            actual["criticidad_declarada"] = linea.split(None, 1)[1].strip().upper()
        elif u.startswith("VIGENCIA DESDE"):
            fecha = linea.split("DESDE", 1)[1].strip()
            if not _RE_FECHA.match(fecha):
                raise _err(num, cruda, f"fecha inválida '{fecha}' (formato AAAA-MM-DD)")
            actual["vigencia_desde"] = fecha
        elif u.startswith("VIGENCIA HASTA"):
            fecha = linea.split("HASTA", 1)[1].strip()
            if not _RE_FECHA.match(fecha):
                raise _err(num, cruda, f"fecha inválida '{fecha}' (formato AAAA-MM-DD)")
            actual["vigencia_hasta"] = fecha
        elif u.startswith("NOTA"):
            actual["nota"] = linea.split(None, 1)[1].strip() if " " in linea else ""
        else:
            raise _err(num, cruda, "instrucción no reconocida del DSL")

    if actual is not None:
        raise ErrorDSL(f"la regla {actual['id']} quedó sin FIN al final del archivo")
    if not reglas:
        raise ErrorDSL("el archivo no define ninguna REGLA")

    return {
        "_comentario": "Compilado por hospiai_dsl.py — NO editar a mano: editar el .hospiai y recompilar.",
        "version": version,
        "actualizado": datetime.now().strftime("%Y-%m-%d"),
        "equivalencias": equivalencias,
        "reglas": reglas,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Compilador del DSL de reglas HOSPIAI.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sv = sub.add_parser("verificar", help="Valida el archivo DSL y muestra el resumen.")
    sv.add_argument("archivo", type=Path)
    sc = sub.add_parser("compilar", help="Compila el DSL al JSON del motor de reglas.")
    sc.add_argument("archivo", type=Path)
    sc.add_argument("--salida", type=Path, required=True)
    args = p.parse_args(argv)

    if not args.archivo.is_file():
        print(f"ERROR: no existe {args.archivo}")
        return 1
    try:
        data = compilar(args.archivo.read_text(encoding="utf-8-sig"))
    except ErrorDSL as e:
        print(f"ERROR de compilación en {args.archivo.name}:\n  {e}")
        return 1

    print(f"{args.archivo.name}: {len(data['reglas'])} regla(s), versión {data['version']} ✔")
    for rg in data["reglas"]:
        amb = rg["ambito"].get("servicio") or rg["ambito"].get("aplica")
        print(
            f"  {rg['id']:<24} {amb:<16} exige {' '.join(rg['exige']) or '—'}  [{rg['criticidad']}]"
        )
    if args.cmd == "compilar":
        args.salida.parent.mkdir(parents=True, exist_ok=True)
        args.salida.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"Compilado → {args.salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
