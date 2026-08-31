"""anexar_notas_credito_adres.py — Pega la nota crédito al final de la factura.

Para radicar en el ADRES, la nota crédito de cada factura tiene que quedar
DENTRO del folio de la factura, como última hoja. Este bot lo hace solo.

    NC ADRES\\HUS354116.pdf
              +
    GI-XX-XXXXX-2026\\680010079201_HUS354116_FACTURA.pdf
              ↓
    GI-XX-XXXXX-2026\\680010079201_HUS354116_FACTURA.pdf
        (las hojas de siempre + la nota crédito de última)

Cómo empareja: toma el número de factura del nombre de la nota (`HUS354116.pdf`)
y busca en la carpeta de radicación el archivo que termine en
`_HUS354116_FACTURA.pdf`. Los ceros de más no estorban: `HUS0000354116` y
`HUS354116` se consideran la misma factura.

Nunca destruye nada: antes de tocar una factura guarda el original en la
subcarpeta `_FOLIOS_SIN_NOTA`. Si esa copia ya existe, esa factura YA tiene su
nota pegada y el bot la salta — así se puede correr las veces que haga falta sin
que la nota quede dos veces. Con `--rehacer` restaura desde esa copia y vuelve a
pegar la nota (útil si cambió la nota crédito).

Por defecto SOLO SIMULA: muestra el cuadro de lo que haría y no escribe nada.
Para que escriba de verdad hay que pasarle `--aplicar`.

USO:
    py tools\\anexar_notas_credito_adres.py "Z:\\...\\NC ADRES" "Z:\\...\\GI-XX-XXXXX-2026"
    py tools\\anexar_notas_credito_adres.py "...\\NC ADRES" "...\\GI-XX-XXXXX-2026" --aplicar
    py tools\\anexar_notas_credito_adres.py "...\\NC ADRES" "...\\GI-XX-XXXXX-2026" --rehacer --aplicar

Deja siempre el informe `INFORME_NOTAS_CREDITO.csv` en la carpeta de las notas:
factura por factura, cuántas hojas tenía, cuántas trae la nota, cuántas quedaron
y qué pasó. Ese es el papel para el auditor.

Normalmente NO se ejecuta a mano: `ANEXAR_NOTAS_CREDITO.cmd` lo lanza con doble
clic.

Requiere PyPDF2 (o pypdf). El repo ya fija PyPDF2==3.0.1.
"""

from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

# Donde se guarda el folio tal como estaba antes de pegarle la nota.
RESPALDO = "_FOLIOS_SIN_NOTA"
INFORME = "INFORME_NOTAS_CREDITO.csv"

SUFIJO_FACTURA = "_FACTURA.pdf"

# `HUS354116.pdf`, `HUS 0000354116.pdf`, `NC HUS354116.pdf`…
_RE_FACTURA = re.compile(r"HUS\s*0*(\d+)", re.IGNORECASE)


def _cargar_lector_escritor():
    """Devuelve (PdfReader, PdfWriter) desde pypdf o PyPDF2, lo que haya."""
    try:
        from pypdf import PdfReader, PdfWriter

        return PdfReader, PdfWriter
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader, PdfWriter

        return PdfReader, PdfWriter
    except ImportError:
        sys.stderr.write(
            "\nERROR: falta el componente para leer PDF (PyPDF2 / pypdf).\n"
            "       Instálalo con:  py -m pip install PyPDF2\n\n"
        )
        raise SystemExit(2)


def numero_de_factura(nombre: str) -> str | None:
    """`680010079201_HUS0000354116_FACTURA.pdf` → `HUS354116`.

    Devuelve None si el nombre no trae un número de factura reconocible.
    """
    hallado = _RE_FACTURA.search(nombre)
    return f"HUS{hallado.group(1).lstrip('0') or '0'}" if hallado else None


def notas_de_la_carpeta(carpeta: Path) -> dict[str, Path]:
    """Las notas crédito de la carpeta, indexadas por número de factura.

    Si dos archivos apuntan a la misma factura se queda con el primero en orden
    alfabético y el otro se reporta aparte (ver `notas_repetidas`).
    """
    notas: dict[str, Path] = {}
    for pdf in sorted(carpeta.glob("*.pdf")):
        if pdf.parent.name == RESPALDO:
            continue
        factura = numero_de_factura(pdf.name)
        if factura:
            notas.setdefault(factura, pdf)
    return notas


def notas_repetidas(carpeta: Path) -> list[tuple[str, Path]]:
    """Las notas que apuntan a una factura que ya tenía otra nota."""
    vistas: set[str] = set()
    repetidas: list[tuple[str, Path]] = []
    for pdf in sorted(carpeta.glob("*.pdf")):
        factura = numero_de_factura(pdf.name)
        if not factura:
            continue
        if factura in vistas:
            repetidas.append((factura, pdf))
        vistas.add(factura)
    return repetidas


def facturas_de_la_radicacion(carpeta: Path) -> dict[str, Path]:
    """Los folios `*_FACTURA.pdf` de la carpeta de radicación, por factura."""
    folios: dict[str, Path] = {}
    for pdf in sorted(carpeta.glob(f"*{SUFIJO_FACTURA}")):
        factura = numero_de_factura(pdf.name)
        if factura:
            folios.setdefault(factura, pdf)
    return folios


def hojas(pdf: Path, PdfReader=None) -> int:
    """Cuántas páginas tiene el PDF. 0 si no se puede leer."""
    if PdfReader is None:
        PdfReader, _ = _cargar_lector_escritor()
    try:
        return len(PdfReader(str(pdf)).pages)
    except Exception:
        return 0


@dataclass
class Resultado:
    """Lo que pasó con una factura. Es lo que sale en el informe."""

    factura: str
    nota: str = ""
    folio: str = ""
    hojas_antes: int = 0
    hojas_nota: int = 0
    hojas_despues: int = 0
    estado: str = ""

    @property
    def cuadra(self) -> bool:
        """Las hojas de después tienen que ser las de antes más las de la nota."""
        return self.hojas_despues == self.hojas_antes + self.hojas_nota


def _pegar(folio: Path, nota: Path, PdfReader, PdfWriter) -> int:
    """Escribe el folio con la nota de última hoja. Devuelve las hojas que quedaron."""
    escritor = PdfWriter()
    for pagina in PdfReader(str(folio)).pages:
        escritor.add_page(pagina)
    for pagina in PdfReader(str(nota)).pages:
        escritor.add_page(pagina)
    # Se escribe a un temporal y solo al final se reemplaza: si el disco de red
    # se cae a mitad de camino, el folio bueno no queda partido.
    temporal = folio.with_suffix(".pdf.tmp")
    with temporal.open("wb") as destino:
        escritor.write(destino)
    temporal.replace(folio)
    return len(escritor.pages)


def anexar(
    carpeta_notas: Path,
    carpeta_radicacion: Path,
    aplicar: bool = False,
    rehacer: bool = False,
) -> list[Resultado]:
    """Pega cada nota crédito al final de su factura. Devuelve el informe."""
    PdfReader, PdfWriter = _cargar_lector_escritor()
    notas = notas_de_la_carpeta(carpeta_notas)
    folios = facturas_de_la_radicacion(carpeta_radicacion)
    respaldos = carpeta_radicacion / RESPALDO

    resultados: list[Resultado] = []
    for factura in sorted(notas):
        nota = notas[factura]
        folio = folios.get(factura)
        r = Resultado(factura=factura, nota=nota.name)
        if folio is None:
            r.estado = "la factura no está en la carpeta de radicación"
            resultados.append(r)
            continue

        r.folio = folio.name
        r.hojas_nota = hojas(nota, PdfReader)
        respaldo = respaldos / folio.name
        ya_estaba = respaldo.exists()

        if ya_estaba and not rehacer:
            r.hojas_antes = hojas(respaldo, PdfReader)
            r.hojas_despues = hojas(folio, PdfReader)
            r.estado = "ya tenía la nota pegada, no se toca"
            resultados.append(r)
            continue

        origen = respaldo if (ya_estaba and rehacer) else folio
        r.hojas_antes = hojas(origen, PdfReader)
        if r.hojas_antes == 0 or r.hojas_nota == 0:
            r.estado = "no se pudo leer el PDF (¿dañado o abierto en otro programa?)"
            resultados.append(r)
            continue

        if not aplicar:
            r.hojas_despues = r.hojas_antes + r.hojas_nota
            r.estado = "SIMULACRO: se pegaría la nota de última hoja"
            resultados.append(r)
            continue

        try:
            if ya_estaba and rehacer:
                shutil.copy2(respaldo, folio)
            else:
                respaldos.mkdir(parents=True, exist_ok=True)
                shutil.copy2(folio, respaldo)
            r.hojas_despues = _pegar(folio, nota, PdfReader, PdfWriter)
        except Exception as e:  # el folio original sigue guardado en el respaldo
            r.estado = f"ERROR: {e}"
            resultados.append(r)
            continue

        r.estado = "nota pegada de última hoja" if r.cuadra else "OJO: las hojas no cuadran"
        resultados.append(r)

    # Las facturas del paquete que no tienen nota crédito también se reportan:
    # el auditor necesita saber cuáles quedaron sin nota.
    for factura in sorted(set(folios) - set(notas)):
        resultados.append(
            Resultado(
                factura=factura,
                folio=folios[factura].name,
                estado="sin nota crédito en la carpeta",
            )
        )
    return resultados


def escribir_informe(resultados: list[Resultado], destino: Path) -> Path:
    """Deja el CSV con lo que pasó factura por factura."""
    with destino.open("w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(
            [
                "FACTURA",
                "NOTA CREDITO",
                "FOLIO DE LA FACTURA",
                "HOJAS ANTES",
                "HOJAS DE LA NOTA",
                "HOJAS DESPUES",
                "QUE PASO",
            ]
        )
        for r in resultados:
            escritor.writerow(
                [
                    r.factura,
                    r.nota,
                    r.folio,
                    r.hojas_antes or "",
                    r.hojas_nota or "",
                    r.hojas_despues or "",
                    r.estado,
                ]
            )
    return destino


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Pega la nota crédito de cada factura como última hoja de su folio."
    )
    p.add_argument("notas", type=Path, help="carpeta con las notas crédito (NC ADRES)")
    p.add_argument("radicacion", type=Path, help="carpeta de radicación (GI-XX-XXXXX-2026)")
    p.add_argument(
        "--aplicar",
        action="store_true",
        help="escribir de verdad (sin esto solo simula y no toca nada)",
    )
    p.add_argument(
        "--rehacer",
        action="store_true",
        help="volver a pegar la nota partiendo del folio guardado en " + RESPALDO,
    )
    a = p.parse_args(argv)

    for carpeta in (a.notas, a.radicacion):
        if not carpeta.is_dir():
            print(f"No existe la carpeta: {carpeta}")
            return 2

    repetidas = notas_repetidas(a.notas)
    resultados = anexar(a.notas, a.radicacion, aplicar=a.aplicar, rehacer=a.rehacer)
    informe = escribir_informe(resultados, a.notas / INFORME)

    pegadas = [r for r in resultados if r.estado.startswith("nota pegada")]
    simuladas = [r for r in resultados if r.estado.startswith("SIMULACRO")]
    ya = [r for r in resultados if r.estado.startswith("ya tenía")]
    sin_folio = [r for r in resultados if r.estado.startswith("la factura no está")]
    sin_nota = [r for r in resultados if r.estado.startswith("sin nota")]
    malos = [r for r in resultados if r.estado.startswith(("ERROR", "OJO", "no se pudo"))]

    print()
    print("=" * 68)
    print("  NOTAS CRÉDITO -> ÚLTIMA HOJA DE LA FACTURA")
    print("=" * 68)
    print(f"  notas crédito en la carpeta : {len(notas_de_la_carpeta(a.notas))}")
    print(f"  facturas en la radicación   : {len(facturas_de_la_radicacion(a.radicacion))}")
    print()
    if a.aplicar:
        print(f"  notas pegadas               : {len(pegadas)}")
    else:
        print(f"  se pegarían (SIMULACRO)     : {len(simuladas)}")
    print(f"  ya la tenían pegada         : {len(ya)}")
    print(f"  notas sin factura           : {len(sin_folio)}")
    print(f"  facturas sin nota           : {len(sin_nota)}")
    print(f"  con problema                : {len(malos)}")
    if repetidas:
        print(f"  notas repetidas (se usó la primera): {len(repetidas)}")

    for r in sin_folio + malos:
        print(f"     - {r.factura}: {r.estado}")
    for factura, pdf in repetidas:
        print(f"     - {factura}: también existe {pdf.name}")

    if not a.aplicar:
        print()
        print("  Esto fue un SIMULACRO: no se tocó ningún archivo.")
        print("  Para hacerlo de verdad, vuelve a correrlo con  --aplicar")
    else:
        print()
        print(f"  Los folios originales quedaron guardados en: {RESPALDO}")
    print(f"  Informe: {informe}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
