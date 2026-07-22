#!/usr/bin/env python3
"""HOSPIAI — Motor Semántico (Knowledge Layer).

La capa que convierte códigos en SIGNIFICADO. Hasta aquí la plataforma sabía
qué documentos y reglas existen; con esta capa sabe qué SON: que K35 es una
apendicitis aguda, que una apendicitis suele terminar en cirugía, que una
cirugía exige descripción quirúrgica + registro anestésico + epicrisis, y que
la DQX es un documento clínico que debe llevar paciente, fecha y firma.

Las ontologías viven en `data/ontologias/*.json` (documental, clínica,
normativa, contractual, y las tablas cargadas: cie10.json, cups.json).
Principio innegociable: los códigos clínicos NUNCA se inventan — la semilla
trae solo ejemplos verificados y las tablas completas se cargan desde los
archivos OFICIALES del hospital (`cargar-cie10`) o se importan de activos ya
existentes en el repo (`importar-cups` lee la tabla de la Res. 2641/2025 que
trae el Motor de Glosas).

Uso:
    py tools\\hospiai_semantica.py resumen
    py tools\\hospiai_semantica.py explicar DQX
    py tools\\hospiai_semantica.py explicar K35
    py tools\\hospiai_semantica.py importar-cups
    py tools\\hospiai_semantica.py cargar-cie10 data\\cie10_oficial.csv

Solo lee las ontologías y escribe archivos nuevos en data/ontologias/.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import sys
from pathlib import Path

DIR_ONTOLOGIAS_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "ontologias"
RUTA_HOMOLOGADOR = (
    Path(__file__).resolve().parent.parent / "app" / "services" / "homologador_cups.py"
)


class MotorSemantico:
    """Carga todas las ontologías y responde qué significa un código y qué
    implica para la auditoría."""

    def __init__(self, dir_ontologias: Path | None = None):
        self.dir = Path(dir_ontologias) if dir_ontologias else DIR_ONTOLOGIAS_DEFAULT
        self.ontologias: dict[str, dict] = {}
        self._indice: dict[str, tuple[str, dict]] = {}  # COD → (ontología, concepto)
        if self.dir.is_dir():
            for f in sorted(self.dir.glob("*.json")):
                data = json.loads(f.read_text(encoding="utf-8-sig"))
                nombre = data.get("ontologia", f.stem)
                self.ontologias[nombre] = data
                for cod, concepto in (data.get("conceptos") or {}).items():
                    if not cod.startswith("_"):
                        self._indice.setdefault(cod.upper(), (nombre, concepto))

    # ── Consultas ──────────────────────────────────────────────────────────

    def concepto(self, codigo: str) -> tuple[str, dict] | None:
        """(ontología, concepto) para un código, o None si no se conoce."""
        return self._indice.get((codigo or "").strip().upper())

    def soportes_para(self, tipo_atencion: str) -> list[str]:
        tipos = (self.ontologias.get("clinica") or {}).get("tipos_atencion") or {}
        return list((tipos.get((tipo_atencion or "").upper()) or {}).get("soportes_esperados", []))

    def explicar(self, codigo: str) -> list[str]:
        """La cadena semántica de un código, legible para un auditor:
        código → significado → clase/tipo → qué implica → qué exige."""
        hallado = self.concepto(codigo)
        if hallado is None:
            return [
                f"{codigo}: no está en las ontologías cargadas (¿falta cargar la tabla oficial?)."
            ]
        ontologia, c = hallado
        cadena = [f"{codigo.upper()} = {c.get('nombre', '?')}  [ontología {ontologia}]"]
        if c.get("clase"):
            cadena.append(f"clase: {c['clase']}")
        if c.get("tipo"):
            cadena.append(f"tipo: {c['tipo']}")
        for rel in ("parte_de", "asociado_a", "valida_a", "equivale_a", "define"):
            if c.get(rel):
                cadena.append(f"{rel.replace('_', ' ')}: {c[rel]}")
        if c.get("acompanado_de"):
            cadena.append("acompañado de: " + ", ".join(c["acompanado_de"]))
        if c.get("satisfecho_por"):
            cadena.append("lo satisface también: " + ", ".join(c["satisfecho_por"]))
        if c.get("atributos_requeridos"):
            cadena.append(
                "atributos exigidos: "
                + ", ".join(c["atributos_requeridos"])
                + f"  ({c.get('fuente_atributos', '')})".rstrip("() ")
            )
        if c.get("exige_documentos"):
            cadena.append("exige documentos: " + ", ".join(c["exige_documentos"]))
        ta = c.get("tipo_atencion_frecuente")
        if ta:
            cadena.append(f"atención frecuente: {ta}")
            soportes = self.soportes_para(ta)
            if soportes:
                cadena.append(f"⇒ por ser {ta}, se esperan: " + ", ".join(soportes))
        if c.get("semilla"):
            cadena.append("(código semilla verificado; cargar la tabla oficial completa)")
        return cadena

    def resumen(self) -> dict[str, int]:
        return {
            nombre: len([k for k in (o.get("conceptos") or {}) if not k.startswith("_")])
            for nombre, o in sorted(self.ontologias.items())
        }


# ─── Cargadores (los códigos JAMÁS se inventan: vienen de fuente oficial) ────


def importar_cups(destino: Path | None = None, ruta_homologador: Path | None = None) -> int:
    """Importa las descripciones CUPS oficiales (Res. 2641/2025) que ya trae el
    Motor de Glosas (app/services/homologador_cups.py). Se extraen por AST —
    sin ejecutar el módulo — para no depender de sus librerías."""
    ruta = ruta_homologador or RUTA_HOMOLOGADOR
    arbol = ast.parse(ruta.read_text(encoding="utf-8"))
    tabla: dict[str, str] = {}
    for nodo in ast.walk(arbol):
        # La tabla puede venir con anotación de tipo (AnnAssign) o sin ella.
        objetivos = []
        if isinstance(nodo, ast.Assign):
            objetivos = nodo.targets
        elif isinstance(nodo, ast.AnnAssign) and nodo.value is not None:
            objetivos = [nodo.target]
        for objetivo in objetivos:
            if getattr(objetivo, "id", "") == "DESCRIPCIONES_CUPS_2025":
                tabla = ast.literal_eval(nodo.value)
    if not tabla:
        raise SystemExit(f"No encontré DESCRIPCIONES_CUPS_2025 en {ruta}")
    data = {
        "ontologia": "cups",
        "version": "2641-2025",
        "descripcion": "Procedimientos CUPS con descripción oficial, importados del homologador del Motor de Glosas (Res. 2641 de 2025). Regenerar con: py tools\\hospiai_semantica.py importar-cups",
        "fuentes": ["Resolución 2641 de 2025", "app/services/homologador_cups.py"],
        "conceptos": {
            cod: {"nombre": nombre, "tipo": "procedimiento_cups"} for cod, nombre in tabla.items()
        },
    }
    salida = (destino or DIR_ONTOLOGIAS_DEFAULT) / "cups.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"CUPS: {len(tabla)} procedimiento(s) oficiales → {salida}")
    return 0


def cargar_cie10(archivo: Path, destino: Path | None = None, separador: str = ";") -> int:
    """Carga la tabla CIE-10 OFICIAL del hospital (CSV: codigo;nombre por
    línea, con o sin encabezado) a data/ontologias/cie10.json."""
    conceptos: dict[str, dict] = {}
    with archivo.open(encoding="utf-8-sig", newline="") as fh:
        for fila in csv.reader(fh, delimiter=separador):
            if len(fila) < 2:
                continue
            cod, nombre = fila[0].strip().upper(), fila[1].strip()
            if not cod or cod in ("CODIGO", "CÓDIGO") or not nombre:
                continue
            conceptos[cod] = {"nombre": nombre, "tipo": "diagnostico_cie10"}
    if not conceptos:
        raise SystemExit(f"{archivo}: no encontré filas 'codigo{separador}nombre'.")
    data = {
        "ontologia": "cie10",
        "version": archivo.name,
        "descripcion": f"Diagnósticos CIE-10 cargados de la tabla oficial {archivo.name}.",
        "fuentes": [str(archivo)],
        "conceptos": conceptos,
    }
    salida = (destino or DIR_ONTOLOGIAS_DEFAULT) / "cie10.json"
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"CIE-10: {len(conceptos)} diagnóstico(s) → {salida}")
    return 0


# ─── CLI ─────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Motor Semántico HOSPIAI (Knowledge Layer).")
    p.add_argument("--ontologias", type=Path, default=None, help="Carpeta de ontologías.")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("resumen", help="Qué ontologías hay cargadas y cuántos conceptos.")
    se = sub.add_parser("explicar", help="Cadena semántica de un código (DQX, K35, 890201…).")
    se.add_argument("codigo")
    sub.add_parser(
        "importar-cups", help="Importa la tabla CUPS del Motor de Glosas (Res. 2641/2025)."
    )
    sc = sub.add_parser("cargar-cie10", help="Carga la tabla CIE-10 oficial (CSV codigo;nombre).")
    sc.add_argument("archivo", type=Path)
    sc.add_argument("--separador", default=";")
    args = p.parse_args(argv)

    if args.cmd == "importar-cups":
        return importar_cups(args.ontologias)
    if args.cmd == "cargar-cie10":
        if not args.archivo.is_file():
            print(f"ERROR: no existe {args.archivo}")
            return 1
        return cargar_cie10(args.archivo, args.ontologias, args.separador)

    motor = MotorSemantico(args.ontologias)
    if not motor.ontologias:
        print(f"ERROR: no hay ontologías en {motor.dir}")
        return 1
    if args.cmd == "resumen":
        print("=" * 56)
        print("Ontologías cargadas:")
        for nombre, n in motor.resumen().items():
            print(f"  {nombre:<14} {n:>6,} concepto(s)")
        print("=" * 56)
        return 0
    for linea in motor.explicar(args.codigo):
        print(f"  {linea}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
