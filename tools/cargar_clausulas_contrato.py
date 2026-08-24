"""Carga las cláusulas de un contrato desde un archivo, sin necesitar clave.

POR QUÉ EXISTE (24-08-2026). Las cláusulas del contrato se cargan de dos
maneras: subiendo el PDF para que la IA las extraiga, o mandándolas ya escritas
por la ruta `/contratos/{eps}/clausulas-manual`. La primera falla cuando el PDF
está escaneado —el de POSITIVA lo está, tiene cero texto— y la segunda exige un
token, que un auditor no tiene a mano.

Este bot cierra el hueco: lee un archivo con las cláusulas ya transcritas y las
guarda, corriendo en el mismo PC del motor. Aplica exactamente las mismas
reglas que la ruta web, para que no haya dos comportamientos distintos según
por dónde se cargue.

USO
    python tools/cargar_clausulas_contrato.py POSITIVA data\\clausulas_positiva.json
    python tools/cargar_clausulas_contrato.py POSITIVA archivo.json --agregar
    python tools/cargar_clausulas_contrato.py POSITIVA archivo.json --ensayo

Por defecto REEMPLAZA las cláusulas que esa EPS ya tenga. Con `--agregar` las
suma a las existentes. Con `--ensayo` no guarda nada: solo dice qué haría.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Las mismas reglas que aplica la ruta web (app/api/routers/contratos.py).
TEMAS_VALIDOS = {"TA", "SO", "AU", "CO", "FA", "NN"}
MINIMO_TEXTO = 30
TOPE_TEXTO = 5000
TOPE_NUMERO = 80
TOPE_TITULO = 300

NOMBRE_TEMA = {
    "TA": "Tarifas",
    "SO": "Soportes",
    "AU": "Autorizaciones",
    "CO": "Cobertura",
    "FA": "Facturación",
    "NN": "Generales",
}


def leer_lote(ruta: Path) -> list[dict]:
    """Acepta tanto el archivo del lote como una lista suelta de cláusulas."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    if isinstance(datos, dict):
        datos = datos.get("clausulas", [])
    if not isinstance(datos, list):
        raise ValueError("El archivo no trae una lista de cláusulas.")
    return datos


def revisar(crudas: list[dict]) -> tuple[list[dict], list[str]]:
    """Deja las que sirven y explica, una por una, las que no."""
    buenas: list[dict] = []
    avisos: list[str] = []
    for i, c in enumerate(crudas, 1):
        texto = (c.get("texto_literal") or "").strip()
        if len(texto) < MINIMO_TEXTO:
            avisos.append(
                f"cláusula {i}: se omite porque su texto tiene {len(texto)} "
                f"caracteres y el mínimo son {MINIMO_TEXTO}"
            )
            continue
        tema = (c.get("tema") or "NN").upper().strip()
        if tema not in TEMAS_VALIDOS:
            avisos.append(f"cláusula {i}: tema «{tema}» no existe, se guarda como NN")
            tema = "NN"
        buenas.append(
            {
                "numero": (c.get("numero") or "").strip()[:TOPE_NUMERO],
                "tema": tema,
                "titulo": (c.get("titulo") or "").strip()[:TOPE_TITULO],
                "texto_literal": texto[:TOPE_TEXTO],
                "pagina": c.get("pagina"),
            }
        )
    return buenas, avisos


def base_en_uso() -> str:
    """A qué base de datos va a escribir este bot.

    Se muestra SIEMPRE antes de guardar, por una lección aprendida el 20-08:
    en el PC de cartera convivieron dos bases (glosas.db y motorglosas.db) y
    un motor apuntando a la equivocada escondió el consolidado entero de una
    auditora. Escribir cláusulas en la base que el portal no mira se vería
    como «cargó bien» y el dictamen seguiría saliendo sin contrato.
    """
    from app.database import engine

    return str(engine.url)


def guardar(eps: str, clausulas: list[dict], *, reemplazar: bool) -> dict:
    from app.database import SessionLocal
    from app.models.db import ClausulaContrato

    eps_norm = eps.upper().strip()
    db = SessionLocal()
    try:
        if reemplazar:
            db.query(ClausulaContrato).filter(ClausulaContrato.eps.in_([eps, eps_norm])).delete(
                synchronize_session=False
            )
        for c in clausulas:
            # El archivo dice `numero` (igual que la ruta web) pero la columna
            # se llama `numero_clausula`: la traducción va campo por campo, a
            # propósito. Pasar el diccionario entero (**c) fue el defecto del
            # 24-08: reventó en el PC de cartera con "'numero' is an invalid
            # keyword argument" después de decir que todo estaba listo.
            db.add(
                ClausulaContrato(
                    eps=eps_norm,
                    numero_clausula=c["numero"],
                    tema=c["tema"],
                    titulo=c["titulo"],
                    texto_literal=c["texto_literal"],
                    pagina=c.get("pagina"),
                )
            )
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            # 24-08-2026 — SEGUROS MUNDIAL: la EPS no existía en Contratos y
            # la llave foránea tumbó el guardado con un traceback de 60
            # líneas. El auditor no tiene por qué descifrar SQLAlchemy.
            if "FOREIGN KEY" in str(e):
                raise SystemExit(
                    f"\nLa EPS «{eps_norm}» NO existe en la pantalla de Contratos "
                    f"del portal, y las cláusulas se cuelgan de ella.\n"
                    f"Créela primero (Gestión → Contratos, con ese nombre exacto) "
                    f"y vuelva a correr este mismo comando.\n"
                    f"No se guardó ni se borró nada."
                )
            raise
        total = db.query(ClausulaContrato).filter(ClausulaContrato.eps == eps_norm).count()
    finally:
        db.close()
    return {"insertadas": len(clausulas), "total_actual": total}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Carga cláusulas de contrato sin clave.")
    p.add_argument("eps", help="Nombre de la EPS tal como está en Contratos. Ej: POSITIVA")
    p.add_argument("archivo", help="Archivo .json con las cláusulas")
    p.add_argument(
        "--agregar",
        action="store_true",
        help="Sumarlas a las que ya hay (por defecto se reemplazan)",
    )
    p.add_argument(
        "--ensayo",
        action="store_true",
        help="No guarda nada: solo dice qué haría",
    )
    a = p.parse_args(argv)

    ruta = Path(a.archivo)
    if not ruta.is_absolute():
        ruta = (Path.cwd() / ruta).resolve()
    if not ruta.exists():
        print(f"No se encontró el archivo: {ruta}")
        return 2

    try:
        crudas = leer_lote(ruta)
    except Exception as e:
        print(f"No se pudo leer el archivo: {e}")
        return 2

    buenas, avisos = revisar(crudas)
    for aviso in avisos:
        print(f"  OJO: {aviso}")
    if not buenas:
        print("No quedó ninguna cláusula que se pueda guardar.")
        return 1

    por_tema: dict[str, int] = {}
    for c in buenas:
        por_tema[c["tema"]] = por_tema.get(c["tema"], 0) + 1

    print(f"\n{len(buenas)} cláusulas listas para {a.eps.upper()}:")
    for tema, n in sorted(por_tema.items()):
        print(f"   {NOMBRE_TEMA.get(tema, tema):<16} {n}")

    print(f"\nBase de datos en uso: {base_en_uso()}")
    if a.ensayo:
        print("Ensayo: no se guardó nada.")
        return 0

    r = guardar(a.eps, buenas, reemplazar=not a.agregar)
    modo = "agregadas a las que ya había" if a.agregar else "reemplazando las anteriores"
    print(f"\nListo: {r['insertadas']} cláusulas {modo}.")
    print(f"{a.eps.upper()} queda con {r['total_actual']} cláusulas en total.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
