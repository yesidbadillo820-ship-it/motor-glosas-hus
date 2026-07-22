#!/usr/bin/env python3
"""HOSPIAI — Document Intelligence Service (DIS · Fase 2.1).

AG001 deja de ser un indexador de rutas: es el SERVICIO DOCUMENTAL de la
plataforma. Cada archivo pasa a ser un OBJETO DOCUMENTAL INTELIGENTE con:

- **Fingerprint** (Capa 2): hash SHA-256, páginas, autor, productor, fechas del
  documento, firma digital, texto extraíble, cifrado, rotación — leídos de la
  ESTRUCTURA real del PDF (inspector propio, sin librerías externas).
- **Clasificación con confianza** (Capa 3): código ADRES + clase de la
  ontología documental + nivel de confianza según la evidencia (token en el
  nombre > carpeta de factura > descarte).
- **Calidad documental** (Capa 5): nota A–D por señales VERIFICABLES
  (estructura válida, páginas, texto, firma, cifrado). Los campos que exigen
  ver el contenido (dpi, % de legibilidad) existen en el perfil pero quedan
  NULOS hasta el OCR de Fase 3 — el DIS no inventa medidas que no puede tomar.
- **Duplicados inteligentes** (Capa 4): exactos (mismo hash) y FUNCIONALES
  (misma factura + mismo tipo de soporte en archivos distintos). El nivel
  paciente+fecha+procedimiento llegará con el OCR, que lee el contenido.
- **Timeline** (Capa 6): creado (fecha del archivo) → indexado → perfilado →
  clasificado + la historia del expediente (auditorías, decisiones, hallazgos).

El perfil vive en la tabla `document_profile` DE CADA base del índice
permanente (data/indices/indice_*.db) — junto a sus archivos, servidor por
servidor. Solo lectura sobre los shares.

Agentes de esta fase:
- **AG016 DocumentCurator**: corruptos, vacíos, duplicados, sin texto
  (escaneo puro), cifrados — ANTES de que lleguen al OCR.
- **AG017 StorageOptimizer**: GB por servidor, crecimiento, duplicados
  recuperables, ausentes, candidatos a archivar.
- **AG018 IngestaInteligente**: rescan incremental + perfilado inmediato de lo
  nuevo + evento en el Expediente — sin esperar la corrida nocturna.

Uso:
    py tools\\hospiai_documento.py perfil HUS528043
    py tools\\hospiai_documento.py curar
    py tools\\hospiai_documento.py almacenamiento
    py tools\\hospiai_documento.py ingesta "Y:\\" …
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hospiai_db  # noqa: E402
import hospiai_indexador as idx  # noqa: E402
import radicar_facturacion as rad  # noqa: E402
from hospiai_sdk import Agente, Mision, ResultadoAgente  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
DB_EXPEDIENTE = RAIZ / "data" / "hospiai.db"

ESQUEMA_PERFIL = """
CREATE TABLE IF NOT EXISTS document_profile(
  ruta TEXT PRIMARY KEY,
  hash TEXT DEFAULT '',
  paginas INTEGER,
  autor TEXT DEFAULT '',
  productor TEXT DEFAULT '',
  fecha_creacion_doc TEXT DEFAULT '',
  fecha_modificacion_doc TEXT DEFAULT '',
  firma INTEGER DEFAULT 0,
  texto INTEGER DEFAULT 0,
  cifrado INTEGER DEFAULT 0,
  rotacion INTEGER DEFAULT 0,
  dpi INTEGER,               -- se llena con OCR (Fase 3)
  legibilidad REAL,          -- se llena con OCR (Fase 3)
  calidad TEXT DEFAULT '',
  clase TEXT DEFAULT '',
  codigo TEXT DEFAULT '',
  confianza REAL DEFAULT 0,
  dup_exacto_de TEXT DEFAULT '',
  dup_funcional INTEGER DEFAULT 0,
  problema TEXT DEFAULT '',
  perfilado_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_perfil_hash ON document_profile(hash);
CREATE INDEX IF NOT EXISTS ix_perfil_calidad ON document_profile(calidad);
"""

_RE_PDF_META = {
    "autor": re.compile(rb"/Author\s*\(([^)]{0,200})\)"),
    "productor": re.compile(rb"/Producer\s*\(([^)]{0,200})\)"),
    "fecha_creacion_doc": re.compile(rb"/CreationDate\s*\(D:(\d{8,14})"),
    "fecha_modificacion_doc": re.compile(rb"/ModDate\s*\(D:(\d{8,14})"),
}
_RE_COUNT = re.compile(rb"/Type\s*/Pages[^>]*?/Count\s+(\d+)", re.DOTALL)
_RE_PAGE = re.compile(rb"/Type\s*/Page[^s]")
_RE_ROTATE = re.compile(rb"/Rotate\s+(\d+)")


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _fecha_pdf(cruda: str) -> str:
    try:
        return datetime.strptime(cruda[:8], "%Y%m%d").strftime("%Y-%m-%d")
    except ValueError:
        return ""


def fingerprint_pdf(ruta: Path, max_bytes: int = 8_000_000) -> dict:
    """Huella del documento leyendo su ESTRUCTURA real (cabecera, objetos,
    diccionario Info, marcas de firma). Para PDFs con streams comprimidos la
    detección de texto usa la presencia de fuentes (/Font): un PDF escaneado
    puro no declara fuentes. Heurística documentada, no adivinación."""
    fp: dict = {
        "hash": "",
        "paginas": None,
        "autor": "",
        "productor": "",
        "fecha_creacion_doc": "",
        "fecha_modificacion_doc": "",
        "firma": 0,
        "texto": 0,
        "cifrado": 0,
        "rotacion": 0,
        "problema": "",
    }
    try:
        datos = ruta.read_bytes()
    except OSError as e:
        fp["problema"] = f"ILEGIBLE: {e}"
        return fp
    fp["hash"] = hashlib.sha256(datos).hexdigest()[:32]
    if not datos:
        fp["problema"] = "VACIO"
        return fp
    if ruta.suffix.lower() != ".pdf":
        return fp  # otros formatos: solo hash (el OCR de Fase 3 los abordará)
    cab = datos[:1024]
    if not cab.lstrip().startswith(b"%PDF"):
        fp["problema"] = "CORRUPTO: sin cabecera %PDF"
        return fp
    cuerpo = datos[:max_bytes]
    if b"%%EOF" not in datos[-2048:] and b"%%EOF" not in cuerpo:
        fp["problema"] = "INCOMPLETO: sin %%EOF (¿descarga/copia interrumpida?)"
    m = _RE_COUNT.search(cuerpo)
    if m:
        fp["paginas"] = int(m.group(1))
    else:
        n = len(_RE_PAGE.findall(cuerpo))
        fp["paginas"] = n or None
    for campo, rx in _RE_PDF_META.items():
        mm = rx.search(cuerpo)
        if mm:
            valor = mm.group(1).decode("latin-1", "replace").strip()
            fp[campo] = _fecha_pdf(valor) if campo.startswith("fecha") else valor
    fp["firma"] = (
        1 if (b"/ByteRange" in cuerpo or b"/Type/Sig" in cuerpo or b"/Type /Sig" in cuerpo) else 0
    )
    fp["texto"] = 1 if b"/Font" in cuerpo else 0
    fp["cifrado"] = 1 if b"/Encrypt" in cuerpo else 0
    mr = _RE_ROTATE.search(cuerpo)
    fp["rotacion"] = int(mr.group(1)) % 360 if mr else 0
    return fp


def calificar(fp: dict) -> str:
    """Nota A–D por señales verificables. (dpi/legibilidad llegan con el OCR.)
    A: estructura válida + texto + firma · B: válida + texto · C: válida sin
    texto (escaneo puro → necesitará OCR) · D: sospechoso (incompleto, cifrado,
    sin páginas) · X: corrupto/vacío/ilegible."""
    if fp["problema"].startswith(("CORRUPTO", "VACIO", "ILEGIBLE")):
        return "X"
    if fp["problema"] or fp["cifrado"] or not fp["paginas"]:
        return "D"
    if fp["texto"] and fp["firma"]:
        return "A"
    if fp["texto"]:
        return "B"
    return "C"


def clasificar_con_confianza(nombre: str, factura: str) -> tuple[str, str, float]:
    """(codigo, clase legible, confianza). La confianza refleja la EVIDENCIA:
    token ADRES en el nombre 0.98 · reconocido por alias/prefijo 0.9 ·
    solo carpeta de factura 0.5 · nada 0.3."""
    codigo, descripcion, reconocido = rad.clasificar_soporte(nombre)
    base = nombre.rsplit(".", 1)[0].upper()
    tokens = set(re.split(r"[ _\-.]+", base))
    if codigo in tokens:
        conf = 0.98
    elif reconocido:
        conf = 0.9
    elif factura:
        conf = 0.5
    else:
        conf = 0.3
    return codigo, descripcion, conf


def perfilar_base(ruta_db: Path, solo_nuevos: bool = True, progreso=print) -> dict:
    """Perfila los archivos de UNA base del índice: fingerprint + clasificación
    + calidad + duplicados (exactos y funcionales). Guarda cada lote de
    inmediato. Con solo_nuevos, procesa únicamente lo aún sin perfil."""
    con = sqlite3.connect(str(ruta_db))
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA_PERFIL)
    filtro = " AND a.ruta NOT IN (SELECT ruta FROM document_profile)" if solo_nuevos else ""
    filas = con.execute(
        f"SELECT a.ruta, a.nombre, a.factura, a.tipo FROM archivos a"
        f" WHERE a.estado='ACTIVO'{filtro}"
    ).fetchall()
    ahora = _ahora()
    n = 0
    lote = []
    for f in filas:
        fp = fingerprint_pdf(Path(f["ruta"]))
        codigo, clase, conf = clasificar_con_confianza(f["nombre"], f["factura"])
        lote.append(
            (
                f["ruta"], fp["hash"], fp["paginas"], fp["autor"], fp["productor"],
                fp["fecha_creacion_doc"], fp["fecha_modificacion_doc"], fp["firma"],
                fp["texto"], fp["cifrado"], fp["rotacion"], calificar(fp), clase,
                codigo, conf, fp["problema"], ahora,
            )
        )  # fmt: skip
        n += 1
        if len(lote) >= 500:
            _volcar_perfiles(con, lote)
            lote = []
            progreso(f"  perfilados {n:,}/{len(filas):,} documentos…")
    _volcar_perfiles(con, lote)

    # Duplicados EXACTOS: mismo hash, distinta ruta → todos apuntan al primero.
    with con:
        con.execute("UPDATE document_profile SET dup_exacto_de=''")
        con.execute(
            "UPDATE document_profile SET dup_exacto_de="
            " (SELECT MIN(d2.ruta) FROM document_profile d2"
            "   WHERE d2.hash=document_profile.hash AND d2.ruta<document_profile.ruta"
            "   AND d2.hash<>'')"
            " WHERE hash<>'' AND EXISTS (SELECT 1 FROM document_profile d3"
            "   WHERE d3.hash=document_profile.hash AND d3.ruta<document_profile.ruta)"
        )
        # Duplicados FUNCIONALES: misma factura + mismo código de soporte en
        # archivos DISTINTOS (hash distinto). El nivel paciente/fecha llega con OCR.
        con.execute("UPDATE document_profile SET dup_funcional=0")
        con.execute(
            "UPDATE document_profile SET dup_funcional=1 WHERE ruta IN ("
            " SELECT d.ruta FROM document_profile d"
            " JOIN archivos a ON a.ruta=d.ruta"
            " WHERE a.factura<>'' AND d.codigo NOT IN ('ADM','VAL')"
            " AND (SELECT COUNT(DISTINCT d2.hash) FROM document_profile d2"
            "      JOIN archivos a2 ON a2.ruta=d2.ruta"
            "      WHERE a2.factura=a.factura AND d2.codigo=d.codigo) > 1)"
        )
    resumen = dict(
        con.execute(
            "SELECT COUNT(*) total,"
            " SUM(CASE WHEN calidad='X' THEN 1 ELSE 0 END) corruptos,"
            " SUM(CASE WHEN dup_exacto_de<>'' THEN 1 ELSE 0 END) dup_exactos,"
            " SUM(CASE WHEN dup_funcional=1 THEN 1 ELSE 0 END) dup_funcionales"
            " FROM document_profile"
        ).fetchone()
    )
    con.close()
    resumen["perfilados_ahora"] = n
    return resumen


def _volcar_perfiles(con: sqlite3.Connection, lote: list) -> None:
    if not lote:
        return
    with con:
        con.executemany(
            "INSERT INTO document_profile(ruta, hash, paginas, autor, productor,"
            " fecha_creacion_doc, fecha_modificacion_doc, firma, texto, cifrado,"
            " rotacion, calidad, clase, codigo, confianza, problema, perfilado_en)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(ruta) DO UPDATE SET hash=excluded.hash,"
            " paginas=excluded.paginas, calidad=excluded.calidad,"
            " clase=excluded.clase, codigo=excluded.codigo,"
            " confianza=excluded.confianza, problema=excluded.problema,"
            " perfilado_en=excluded.perfilado_en",
            lote,
        )


def perfil_factura(factura: str, dir_indices: Path | None = None,
                   db_expediente: Path | None = None) -> dict:  # fmt: skip
    """El objeto documental inteligente de una factura: cada documento con su
    fingerprint, clase, calidad, duplicados y timeline + el vínculo con el
    Expediente (decisiones y hallazgos). Criterio de aceptación de la fase."""
    clave = rad.normalizar_factura(factura)
    documentos = []
    for db in idx.bases_disponibles(dir_indices):
        con = sqlite3.connect(str(db))
        con.row_factory = sqlite3.Row
        con.executescript(ESQUEMA_PERFIL)
        for f in con.execute(
            "SELECT a.ruta, a.nombre, a.servidor, a.estado, a.ultima_modificacion,"
            " a.visto_primera, d.* FROM archivos a"
            " LEFT JOIN document_profile d ON d.ruta=a.ruta WHERE a.factura=?",
            (clave,),
        ):
            doc = dict(f)
            doc["creado"] = (
                datetime.fromtimestamp(f["ultima_modificacion"]).strftime("%Y-%m-%d")
                if f["ultima_modificacion"]
                else ""
            )
            documentos.append(doc)
        con.close()
    exped = {"decisiones": 0, "hallazgos": 0, "eventos": [], "dictamen": ""}
    dbe = db_expediente or DB_EXPEDIENTE
    if Path(dbe).is_file():
        con = hospiai_db.abrir(dbe)
        try:
            e = con.execute(
                "SELECT dictamen FROM expedientes WHERE factura_norm=?", (clave,)
            ).fetchone()
            exped["dictamen"] = e["dictamen"] if e else ""
            exped["decisiones"] = con.execute(
                "SELECT COUNT(*) FROM decisiones WHERE factura_norm=?", (clave,)
            ).fetchone()[0]
            exped["hallazgos"] = con.execute(
                "SELECT COUNT(*) FROM hallazgos WHERE factura_norm=? AND resuelto=0", (clave,)
            ).fetchone()[0]
            exped["eventos"] = [
                dict(r)
                for r in con.execute(
                    "SELECT fecha, tipo, resultado FROM eventos WHERE factura_norm=?"
                    " ORDER BY fecha DESC LIMIT 8",
                    (clave,),
                )
            ]
        finally:
            con.close()
    return {"factura": factura, "clave": clave, "documentos": documentos, "expediente": exped}


# ─── AG016 · Document Curator ────────────────────────────────────────────────


class AgenteDocumentCurator(Agente):
    """AG016 — Revisa DOCUMENTOS, nunca expedientes: corruptos, vacíos,
    incompletos, duplicados, sin texto (escaneo puro), cifrados — antes de que
    lleguen al OCR. Deja hallazgos DOCUMENTALES en el Expediente."""

    id = "AG016"
    nombre = "DocumentCurator"
    dominio = "D1"
    version = "1.0"
    salidas = ["problemas", "resumen"]
    depende_de = ["AG001"]
    capacidades = ["CURAR_DOCUMENTOS"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        dir_indices = contexto.get("dir_indices")
        problemas: list[dict] = []
        for db in idx.bases_disponibles(dir_indices):
            perfilar_base(db, solo_nuevos=True, progreso=lambda m: None)
            con = sqlite3.connect(str(db))
            con.row_factory = sqlite3.Row
            for f in con.execute(
                "SELECT d.ruta, d.calidad, d.problema, d.dup_exacto_de, d.codigo, d.texto,"
                " d.cifrado, a.factura FROM document_profile d JOIN archivos a ON a.ruta=d.ruta"
                " WHERE a.estado='ACTIVO' AND (d.calidad IN ('X','D')"
                "   OR d.dup_exacto_de<>'' OR d.texto=0)"
            ):
                tipo = (
                    "DOC_CORRUPTO" if f["calidad"] == "X"
                    else "DOC_DUPLICADO_EXACTO" if f["dup_exacto_de"]
                    else "DOC_SIN_TEXTO" if f["texto"] == 0
                    else "DOC_SOSPECHOSO"
                )  # fmt: skip
                problemas.append(
                    {
                        "tipo": tipo,
                        "ruta": f["ruta"],
                        "factura": f["factura"],
                        "detalle": f["problema"] or f"calidad {f['calidad']}",
                    }
                )
            con.close()
        res.salida = {"problemas": problemas[:500], "resumen": {"total": len(problemas)}}
        res.detalle = f"{len(problemas)} documento(s) con problemas detectados antes del OCR"
        for p in problemas[:200]:
            if p["factura"]:
                res.hallazgos.append(
                    {
                        "tipo": p["tipo"],
                        "criticidad": "ADVERTENCIA",
                        "detalle": f"{Path(p['ruta']).name}: {p['detalle']}",
                        "evidencia": p["ruta"],
                        "confianza": 0.9,
                    }
                )


# ─── AG017 · Storage Optimizer ───────────────────────────────────────────────


class AgenteStorageOptimizer(Agente):
    """AG017 — Responde en GB: cuánto ocupa cada servidor, qué crece, cuánto
    hay duplicado (recuperable), qué está ausente y qué es candidato a archivo.
    SOLO informa: mover/borrar es decisión humana."""

    id = "AG017"
    nombre = "StorageOptimizer"
    dominio = "D1"
    version = "1.0"
    salidas = ["almacenamiento"]
    depende_de = ["AG001"]
    capacidades = ["OPTIMIZAR_ALMACENAMIENTO"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        dir_indices = contexto.get("dir_indices")
        informe = []
        for db in idx.bases_disponibles(dir_indices):
            con = sqlite3.connect(str(db))
            con.row_factory = sqlite3.Row
            con.executescript(ESQUEMA_PERFIL)
            g = dict(
                con.execute(
                    "SELECT servidor, COUNT(*) archivos,"
                    " ROUND(SUM(tamano)/1e9, 2) gb,"
                    " SUM(CASE WHEN estado='AUSENTE' THEN 1 ELSE 0 END) ausentes"
                    " FROM archivos GROUP BY servidor"
                ).fetchone()
                or {}
            )
            dup = con.execute(
                "SELECT COUNT(*) n, COALESCE(SUM(a.tamano),0) bytes FROM document_profile d"
                " JOIN archivos a ON a.ruta=d.ruta WHERE d.dup_exacto_de<>''"
            ).fetchone()
            viejos = con.execute(
                "SELECT COUNT(*) n FROM archivos WHERE estado='ACTIVO'"
                " AND ultima_modificacion < strftime('%s','now','-2 years')"
            ).fetchone()
            g.update(
                {
                    "base": db.name,
                    "dup_exactos": dup["n"],
                    "gb_recuperables": round(dup["bytes"] / 1e9, 3),
                    "candidatos_archivar_2anios": viejos["n"],
                }
            )
            informe.append(g)
            con.close()
        res.salida = {"almacenamiento": informe}
        total_gb = sum(x.get("gb") or 0 for x in informe)
        rec = sum(x.get("gb_recuperables") or 0 for x in informe)
        res.detalle = f"{total_gb:.1f} GB indexados · {rec:.2f} GB recuperables en duplicados"


# ─── AG018 · Ingesta Inteligente ─────────────────────────────────────────────


class AgenteIngesta(Agente):
    """AG018 — Rescan incremental + perfilado inmediato de lo NUEVO + evento en
    el Expediente por cada factura tocada. Sin esperar la corrida nocturna."""

    id = "AG018"
    nombre = "IngestaInteligente"
    dominio = "D1"
    version = "1.0"
    entradas = ["raiz"]
    salidas = ["ingeridos"]
    depende_de = ["AG001"]
    capacidades = ["INGESTA"]

    def _trabajar(self, mision: Mision, contexto: dict, res: ResultadoAgente) -> None:
        raiz = mision.datos["raiz"]
        dir_indices = contexto.get("dir_indices")
        r = idx.indexar_raiz(raiz, dir_indices, progreso=lambda m: None)
        db = idx.db_de(raiz, dir_indices)
        perf = perfilar_base(db, solo_nuevos=True, progreso=lambda m: None)
        facturas_nuevas: list[str] = []
        if r["nuevos"]:
            con = sqlite3.connect(str(db))
            facturas_nuevas = [
                f[0]
                for f in con.execute(
                    "SELECT DISTINCT factura FROM archivos WHERE factura<>''"
                    " AND visto_primera=(SELECT MAX(visto_primera) FROM archivos)"
                )
            ]
            con.close()
            dbe = contexto.get("db_path") or DB_EXPEDIENTE
            if Path(dbe).is_file() and facturas_nuevas:
                cone = hospiai_db.abrir(dbe)
                with cone:
                    for fac in facturas_nuevas[:500]:
                        cone.execute(
                            "INSERT INTO eventos(factura_norm, fecha, agente, tipo,"
                            " resultado, corrida_id, detalle) VALUES(?,?,?,?,?,0,?)",
                            (
                                fac,
                                _ahora(),
                                f"{self.id} v{self.version}",
                                "DOCUMENTO_NUEVO",
                                "INGERIDO",
                                f"ingesta desde {raiz}",
                            ),
                        )
                cone.close()
        res.salida = {
            "ingeridos": {
                "nuevos": r["nuevos"],
                "perfilados": perf["perfilados_ahora"],
                "facturas_tocadas": len(facturas_nuevas),
            }
        }
        res.detalle = (
            f"{r['nuevos']} nuevo(s), {perf['perfilados_ahora']} perfilado(s), "
            f"{len(facturas_nuevas)} factura(s) con novedades"
        )


# ─── CLI ─────────────────────────────────────────────────────────────────────


def _imprimir_perfil(p: dict) -> None:
    print("=" * 74)
    print(f"OBJETO DOCUMENTAL · Factura {p['factura']} (clave {p['clave']})")
    e = p["expediente"]
    print(
        f"  Expediente: dictamen {e['dictamen'] or '—'} · "
        f"Decision Records: {e['decisiones']} · Hallazgos abiertos: {e['hallazgos']}"
    )
    if not p["documentos"]:
        print("  (sin documentos en el índice — ¿corrió la ingesta/indexación?)")
    for d in p["documentos"]:
        print("-" * 74)
        print(f"  Documento : {d['nombre']}   [{d['estado']}] ({d['servidor']})")
        print(f"  Clase     : {d['codigo'] or '—'} — {d['clase'] or 'sin perfilar'}")
        if d.get("perfilado_en"):
            dup = (
                "EXACTO de " + Path(d["dup_exacto_de"]).name
                if d["dup_exacto_de"]
                else ("FUNCIONAL (mismo tipo repetido)" if d["dup_funcional"] else "No")
            )
            print(
                f"  Calidad   : {d['calidad']}   Confianza: {d['confianza']:.0%}   "
                f"Páginas: {d['paginas'] or '?'}   Texto: {'Sí' if d['texto'] else 'No'}   "
                f"Firma: {'Sí' if d['firma'] else 'No'}"
            )
            print(f"  Hash      : {d['hash']}   Duplicado: {dup}")
            if d["problema"]:
                print(f"  ⚠ Problema: {d['problema']}")
            print(
                f"  Timeline  : creado {d['creado'] or '?'} → indexado {d['visto_primera'][:10]}"
                f" → perfilado {d['perfilado_en'][:10]}"
            )
        else:
            print("  (aún sin perfil — correr 'ingesta' o 'curar')")
    if e["eventos"]:
        print("-" * 74)
        print("  Historia del expediente:")
        for ev in e["eventos"]:
            print(f"    {ev['fecha']}  {ev['tipo']} → {ev['resultado']}")
    print("=" * 74)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Document Intelligence Service (DIS) — solo lee.")
    p.add_argument("--indices", type=Path, default=None)
    p.add_argument("--db", type=Path, default=DB_EXPEDIENTE)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("perfil", help="El objeto documental completo de una factura.")
    sp.add_argument("factura")
    sub.add_parser("curar", help="AG016: corruptos, vacíos, duplicados, sin texto.")
    sub.add_parser("almacenamiento", help="AG017: GB, duplicados recuperables, archivables.")
    si = sub.add_parser("ingesta", help="AG018: incremental + perfilado inmediato.")
    si.add_argument("raices", nargs="+")
    args = p.parse_args(argv)

    ctx = {"dir_indices": args.indices, "db_path": args.db}
    if args.cmd == "perfil":
        _imprimir_perfil(perfil_factura(args.factura, args.indices, args.db))
        return 0
    if args.cmd == "curar":
        r = AgenteDocumentCurator().ejecutar(Mision(codigo="M", tipo="CURAR_DOCUMENTOS"), ctx)
        print(f"AG016 DocumentCurator: {r.resultado} — {r.detalle}")
        for pr in r.salida.get("problemas", [])[:25]:
            print(f"  [{pr['tipo']}] {pr['ruta']}")
        return 0 if r.resultado == "OK" else 1
    if args.cmd == "almacenamiento":
        r = AgenteStorageOptimizer().ejecutar(
            Mision(codigo="M", tipo="OPTIMIZAR_ALMACENAMIENTO"), ctx
        )
        print(f"AG017 StorageOptimizer: {r.resultado} — {r.detalle}")
        for g in r.salida.get("almacenamiento", []):
            print(
                f"  {g.get('base'):<20} {g.get('archivos', 0):>9,} archivos · {g.get('gb', 0):>8} GB"
                f" · dup exactos: {g.get('dup_exactos', 0):,} ({g.get('gb_recuperables', 0)} GB)"
                f" · ausentes: {g.get('ausentes', 0):,}"
                f" · archivables (>2 años): {g.get('candidatos_archivar_2anios', 0):,}"
            )
        return 0 if r.resultado == "OK" else 1
    # ingesta
    for raiz in args.raices:
        r = AgenteIngesta().ejecutar(Mision(codigo="M", tipo="INGESTA", datos={"raiz": raiz}), ctx)
        print(f"AG018 Ingesta [{raiz}]: {r.resultado} — {r.detalle}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
