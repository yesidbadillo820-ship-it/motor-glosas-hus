"""Fusiona la base vieja de la VM de Google con la base viva del PC de cartera.

POR QUÉ EXISTE. El 03-08-2026 la VM de Google quedó congelada (facturación
suspendida) y el sistema se mudó al PC de cartera con una base provisional.
El 13-08 Google reabrió la cuenta y se rescató la base vieja
(motorglosas-rescate.db, dentro de rescate-motor-glosas.tgz). Pero el PC ya
lleva días siendo el sistema real: tiene la pre-auditoría completa (importada
del Excel del equipo, MÁS completa que la vieja) y trabajo nuevo de todos los
días. Por eso NO se restaura la base vieja encima: se FUSIONA — se trae de la
vieja solo lo que a la viva le falta, sin pisar nada.

QUÉ TRAE DE LA BASE VIEJA (solo lo que falte en la viva):
  - Glosas con sus dictámenes (tabla historial) + toda su historia:
    conceptos, versiones del dictamen, comentarios, conciliaciones con sus
    adjuntos, notas privadas e hilos de comentarios.
  - Precedentes ganados (plantillas_gold) y plantillas de respuesta.
  - Usuarios que no existan en la viva (con su clave vieja). Los que ya
    existen en el PC NO se tocan (conservan la clave que usan hoy).
  - Contratos por EPS que falten (con sus cláusulas) y tarifas contratadas
    de EPS/CUPS que la viva no tenga.
  - Vault de credenciales de entidades — SOLO si la viva está vacía, porque
    van cifradas con la CRED_VAULT_KEY del .env viejo (hay que copiar esa
    clave al .env del PC para poder leerlas).
  - Rutas de soportes por factura y atajos (snippets) de los gestores.

QUÉ NO TOCA NUNCA:
  - Nada de pre-auditoría (preaud_*): la del PC es la buena.
  - Ninguna fila que ya exista en la viva: el sistema del PC manda.
  - Tablas de trabajo interno (logs, caché de IA, chat, noticias...).

REGLAS DE SEGURIDAD:
  - Sin argumento de modo: SOLO MIRAR (no escribe; muestra qué haría).
    Con "aplicar": escribe, en una sola transacción, y ANTES de escribir
    deja una copia de seguridad de la base viva en data/backups/.
  - Idempotente: correrlo dos veces no duplica nada.
  - La base vieja se abre SOLO LECTURA siempre: jamás se modifica.
  - Si la vieja tiene tablas o columnas que la viva no conoce (o al revés),
    se copia solo lo que ambas comparten — no truena.

USO EN EL PC DE CARTERA (PowerShell o cmd, desde C:\\motor-glosas\\repo):
  venv\\Scripts\\python.exe tools\\fusionar_base_vieja.py "C:\\motor-glosas\\rescate\\data\\backups\\motorglosas-rescate.db"
  venv\\Scripts\\python.exe tools\\fusionar_base_vieja.py "C:\\motor-glosas\\rescate\\data\\backups\\motorglosas-rescate.db" aplicar
"""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

MARCA = "fusion-base-vieja"

# La llave con la que decidimos si una glosa de la vieja "ya está" en la viva.
CLAVE_GLOSA = ("factura", "codigo_glosa", "eps", "valor_objetado", "creado_en")

# Hijas directas de una glosa (historial.id) que viajan con ella.
HIJAS_DE_GLOSA = (
    "conceptos_glosa",
    "dictamen_versiones",
    "comentarios_glosa",
    "notas_privadas",
)


def _existe_tabla(con: sqlite3.Connection, tabla: str) -> bool:
    fila = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tabla,)
    ).fetchone()
    return fila is not None


def _cols(con: sqlite3.Connection, tabla: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({tabla})")]


def _comunes(cv, cn, tabla: str, quitar: tuple = ("id",)) -> list[str]:
    """Columnas que existen en AMBAS bases (la vieja puede ser más antigua)."""
    if not (_existe_tabla(cv, tabla) and _existe_tabla(cn, tabla)):
        return []
    de_viva = set(_cols(cn, tabla))
    return [c for c in _cols(cv, tabla) if c in de_viva and c not in quitar]


def _ins(cur, tabla: str, cols: list[str], fila) -> int:
    marcas = ", ".join("?" * len(cols))
    cur.execute(f"INSERT INTO {tabla} ({', '.join(cols)}) VALUES ({marcas})", tuple(fila))
    return cur.lastrowid


def _filas(cv, tabla: str, cols: list[str], con_id: bool = False):
    sel = ("id, " if con_id else "") + ", ".join(cols)
    for r in cv.execute(f"SELECT {sel} FROM {tabla} ORDER BY rowid"):
        if con_id:
            yield r[0], list(r[1:])
        else:
            yield list(r)


def fusionar(cv, cn, escribir: bool, ruta_viva: str) -> dict:
    """cv = base vieja (solo lectura), cn = base viva del PC."""
    cur = cn.cursor()
    res = {
        "usuarios_nuevos": [],
        "usuarios_ya": 0,
        "glosas_nuevas": 0,
        "glosas_ya": 0,
        "hijas": dict.fromkeys(HIJAS_DE_GLOSA, 0),
        "conciliaciones": 0,
        "adjuntos": 0,
        "hilos": 0,
        "gold_nuevas": 0,
        "gold_ya": 0,
        "plantillas_nuevas": 0,
        "plantillas_ya": 0,
        "contratos_nuevos": [],
        "contratos_ya": 0,
        "clausulas": 0,
        "tarifas_nuevas": 0,
        "tarifas_ya": 0,
        "credenciales": 0,
        "rutas": 0,
        "snippets": 0,
        "avisos": [],
    }

    # ── Usuarios: solo los que falten; los del PC conservan su clave ─────────
    cols_u = _comunes(cv, cn, "usuarios")
    if cols_u:
        emails_viva = {
            (r[0] or "").strip().lower() for r in cn.execute("SELECT email FROM usuarios")
        }
        i_email = cols_u.index("email")
        for fila in _filas(cv, "usuarios", cols_u):
            em = (fila[i_email] or "").strip().lower()
            if not em or em in emails_viva:
                res["usuarios_ya"] += 1
                continue
            emails_viva.add(em)
            res["usuarios_nuevos"].append(em)
            if escribir:
                _ins(cur, "usuarios", cols_u, fila)

    # ── Glosas (historial) con dedup exacto y mapa id vieja → id viva ────────
    mapa_glosas: dict[int, int] = {}
    glosas_traidas: set[int] = set()  # ids VIEJOS de las glosas que sí viajan
    cols_h = _comunes(cv, cn, "historial")
    if cols_h:
        idx_clave = [cols_h.index(c) for c in CLAVE_GLOSA if c in cols_h]
        sql_ya = "SELECT id FROM historial WHERE " + " AND ".join(
            f"{c} IS ?" for c in CLAVE_GLOSA if c in cols_h
        )
        for viejo_id, fila in _filas(cv, "historial", cols_h, con_id=True):
            ya = cn.execute(sql_ya, [fila[i] for i in idx_clave]).fetchone()
            if ya:
                mapa_glosas[viejo_id] = ya[0]
                res["glosas_ya"] += 1
                continue
            res["glosas_nuevas"] += 1
            glosas_traidas.add(viejo_id)
            if escribir:
                mapa_glosas[viejo_id] = _ins(cur, "historial", cols_h, fila)

    # ── Hijas simples de la glosa (viajan solo con glosas traídas) ───────────
    for tabla in HIJAS_DE_GLOSA:
        cols_t = _comunes(cv, cn, tabla)
        if not cols_t or "glosa_id" not in cols_t:
            continue
        i_g = cols_t.index("glosa_id")
        for fila in _filas(cv, tabla, cols_t):
            if fila[i_g] not in glosas_traidas:
                continue
            res["hijas"][tabla] += 1
            if escribir:
                fila[i_g] = mapa_glosas[fila[i_g]]
                _ins(cur, tabla, cols_t, fila)

    # ── Conciliaciones y sus adjuntos (dos niveles de id) ────────────────────
    mapa_conc: dict[int, int] = {}
    conc_traidas: set[int] = set()
    cols_c = _comunes(cv, cn, "conciliaciones")
    if cols_c and "glosa_id" in cols_c:
        i_g = cols_c.index("glosa_id")
        for viejo_id, fila in _filas(cv, "conciliaciones", cols_c, con_id=True):
            if fila[i_g] not in glosas_traidas:
                continue
            res["conciliaciones"] += 1
            conc_traidas.add(viejo_id)
            if escribir:
                fila[i_g] = mapa_glosas[fila[i_g]]
                mapa_conc[viejo_id] = _ins(cur, "conciliaciones", cols_c, fila)
    cols_a = _comunes(cv, cn, "adjuntos_conciliacion")
    if cols_a and "conciliacion_id" in cols_a:
        i_c = cols_a.index("conciliacion_id")
        for fila in _filas(cv, "adjuntos_conciliacion", cols_a):
            if fila[i_c] not in conc_traidas:
                continue
            res["adjuntos"] += 1
            if escribir:
                fila[i_c] = mapa_conc[fila[i_c]]
                _ins(cur, "adjuntos_conciliacion", cols_a, fila)

    # ── Hilos de comentarios (parent_id apunta a la misma tabla) ─────────────
    mapa_hilo: dict[int, int] = {}
    cols_th = _comunes(cv, cn, "comentarios_thread")
    if cols_th and "glosa_id" in cols_th:
        i_g = cols_th.index("glosa_id")
        i_p = cols_th.index("parent_id") if "parent_id" in cols_th else None
        for viejo_id, fila in _filas(cv, "comentarios_thread", cols_th, con_id=True):
            if fila[i_g] not in glosas_traidas:
                continue
            res["hilos"] += 1
            if escribir:
                fila[i_g] = mapa_glosas[fila[i_g]]
                if i_p is not None and fila[i_p]:
                    fila[i_p] = mapa_hilo.get(fila[i_p])
                mapa_hilo[viejo_id] = _ins(cur, "comentarios_thread", cols_th, fila)

    # ── Precedentes ganados (plantillas_gold) y plantillas ───────────────────
    cols_g = _comunes(cv, cn, "plantillas_gold")
    if cols_g:
        i_eps = cols_g.index("eps")
        i_cod = cols_g.index("codigo_glosa")
        i_arg = cols_g.index("argumento")
        i_ori = cols_g.index("glosa_origen_id") if "glosa_origen_id" in cols_g else None
        for fila in _filas(cv, "plantillas_gold", cols_g):
            ya = cn.execute(
                "SELECT 1 FROM plantillas_gold WHERE eps IS ? AND codigo_glosa IS ? "
                "AND argumento IS ?",
                (fila[i_eps], fila[i_cod], fila[i_arg]),
            ).fetchone()
            if ya:
                res["gold_ya"] += 1
                continue
            res["gold_nuevas"] += 1
            if escribir:
                if i_ori is not None and fila[i_ori]:
                    fila[i_ori] = mapa_glosas.get(fila[i_ori])
                _ins(cur, "plantillas_gold", cols_g, fila)

    cols_p = _comunes(cv, cn, "plantillas")
    if cols_p:
        i_nom = cols_p.index("nombre")
        i_txt = cols_p.index("plantilla")
        for fila in _filas(cv, "plantillas", cols_p):
            ya = cn.execute(
                "SELECT 1 FROM plantillas WHERE nombre IS ? AND plantilla IS ?",
                (fila[i_nom], fila[i_txt]),
            ).fetchone()
            if ya:
                res["plantillas_ya"] += 1
                continue
            res["plantillas_nuevas"] += 1
            if escribir:
                _ins(cur, "plantillas", cols_p, fila)

    # ── Contratos (PK = eps) + cláusulas + tarifas ───────────────────────────
    dir_datos = Path(ruta_viva).resolve().parent
    eps_traidas: set[str] = set()
    cols_ct = _comunes(cv, cn, "contratos", quitar=())
    if cols_ct:
        eps_viva = {r[0] for r in cn.execute("SELECT eps FROM contratos")}
        i_eps = cols_ct.index("eps")
        i_pdf = cols_ct.index("pdf_path") if "pdf_path" in cols_ct else None
        for fila in _filas(cv, "contratos", cols_ct):
            if fila[i_eps] in eps_viva:
                res["contratos_ya"] += 1
                continue
            eps_traidas.add(fila[i_eps])
            res["contratos_nuevos"].append(fila[i_eps])
            if escribir:
                if i_pdf is not None and fila[i_pdf]:
                    # El PDF vivía en la VM; en el PC quedará en data\contratos.
                    nombre = Path(str(fila[i_pdf]).replace("\\", "/")).name
                    fila[i_pdf] = str(dir_datos / "contratos" / nombre)
                _ins(cur, "contratos", cols_ct, fila)
        if res["contratos_nuevos"]:
            res["avisos"].append(
                "Los PDF de los contratos traídos hay que copiarlos del rescate "
                "(data/contratos del tgz) a C:\\motor-glosas\\repo\\data\\contratos"
            )

    cols_cl = _comunes(cv, cn, "clausulas_contrato")
    if cols_cl and "eps" in cols_cl:
        i_eps = cols_cl.index("eps")
        eps_con_clausulas_viva = {
            r[0] for r in cn.execute("SELECT DISTINCT eps FROM clausulas_contrato")
        }
        eps_conocidas_viva = {r[0] for r in cn.execute("SELECT eps FROM contratos")}
        for fila in _filas(cv, "clausulas_contrato", cols_cl):
            eps = fila[i_eps]
            # Solo si la viva NO tiene cláusulas de esa EPS y el contrato existe
            # (venía de antes o lo acabamos de traer).
            if eps in eps_con_clausulas_viva:
                continue
            if eps not in eps_conocidas_viva and eps not in eps_traidas:
                continue
            res["clausulas"] += 1
            if escribir:
                _ins(cur, "clausulas_contrato", cols_cl, fila)

    cols_ta = _comunes(cv, cn, "tarifas_contratadas")
    if cols_ta:
        i_eps = cols_ta.index("eps")
        i_cups = cols_ta.index("codigo_cups")
        pares_viva = {
            (r[0], r[1]) for r in cn.execute("SELECT eps, codigo_cups FROM tarifas_contratadas")
        }
        for fila in _filas(cv, "tarifas_contratadas", cols_ta):
            if (fila[i_eps], fila[i_cups]) in pares_viva:
                res["tarifas_ya"] += 1
                continue
            res["tarifas_nuevas"] += 1
            if escribir:
                _ins(cur, "tarifas_contratadas", cols_ta, fila)

    # ── Vault de credenciales: solo si la viva está vacía ────────────────────
    cols_cr = _comunes(cv, cn, "entidad_credenciales")
    if cols_cr:
        n_viva = cn.execute("SELECT COUNT(*) FROM entidad_credenciales").fetchone()[0]
        n_vieja = cv.execute("SELECT COUNT(*) FROM entidad_credenciales").fetchone()[0]
        if n_vieja and n_viva:
            res["avisos"].append(
                f"El vault de credenciales del PC ya tiene {n_viva} registros: "
                f"NO se mezclan los {n_vieja} de la base vieja (cifrados con otra clave)"
            )
        elif n_vieja:
            for fila in _filas(cv, "entidad_credenciales", cols_cr):
                res["credenciales"] += 1
                if escribir:
                    _ins(cur, "entidad_credenciales", cols_cr, fila)
            res["avisos"].append(
                "Las credenciales van cifradas con la CRED_VAULT_KEY del .env "
                "VIEJO: copie esa línea del .env del rescate al .env del PC"
            )

    # ── Rutas de soportes por factura y snippets ─────────────────────────────
    cols_r = _comunes(cv, cn, "rutas_factura", quitar=())
    if cols_r and "factura_hus" in cols_r:
        i_f = cols_r.index("factura_hus")
        facturas_viva = {r[0] for r in cn.execute("SELECT factura_hus FROM rutas_factura")}
        for fila in _filas(cv, "rutas_factura", cols_r):
            if fila[i_f] in facturas_viva:
                continue
            facturas_viva.add(fila[i_f])
            res["rutas"] += 1
            if escribir:
                _ins(cur, "rutas_factura", cols_r, fila)

    cols_s = _comunes(cv, cn, "snippets")
    if cols_s and "atajo" in cols_s and "usuario_email" in cols_s:
        i_u = cols_s.index("usuario_email")
        i_a = cols_s.index("atajo")
        llaves_viva = {
            (r[0], r[1]) for r in cn.execute("SELECT usuario_email, atajo FROM snippets")
        }
        for fila in _filas(cv, "snippets", cols_s):
            if (fila[i_u], fila[i_a]) in llaves_viva:
                continue
            llaves_viva.add((fila[i_u], fila[i_a]))
            res["snippets"] += 1
            if escribir:
                _ins(cur, "snippets", cols_s, fila)

    # ── Huella en el audit_log para saber qué pasó y cuándo ──────────────────
    if escribir and _existe_tabla(cn, "audit_log"):
        detalle = {k: v for k, v in res.items() if k != "avisos"}
        detalle["usuarios_nuevos"] = len(res["usuarios_nuevos"])
        detalle["contratos_nuevos"] = len(res["contratos_nuevos"])
        cur.execute(
            "INSERT INTO audit_log (usuario_email, usuario_rol, accion, tabla, detalle) "
            "VALUES (?, 'SISTEMA', 'FUSION_BASE_VIEJA', 'varias', ?)",
            (MARCA, json.dumps(detalle, ensure_ascii=False)),
        )

    return res


def _respaldar(cn: sqlite3.Connection, ruta_viva: str) -> str:
    """Copia de seguridad de la base viva ANTES de escribirle nada."""
    dir_b = Path(ruta_viva).resolve().parent / "backups"
    dir_b.mkdir(parents=True, exist_ok=True)
    destino = dir_b / f"motorglosas-antes-fusion-{datetime.now():%Y%m%d-%H%M%S}.db"
    con_b = sqlite3.connect(str(destino))
    with con_b:
        cn.backup(con_b)
    con_b.close()
    return str(destino)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    ruta_vieja = sys.argv[1]
    modo_aplicar = any(a.lower() == "aplicar" for a in sys.argv[2:])
    ruta_viva = None
    for arg in sys.argv[2:]:
        if arg.lower().endswith(".db"):
            ruta_viva = arg
    if not ruta_viva:
        ruta_viva = str(Path(__file__).resolve().parent.parent / "data" / "motorglosas.db")

    if not Path(ruta_vieja).exists():
        print(f"No se encontró la base vieja: {ruta_vieja}")
        return 1
    if not Path(ruta_viva).exists():
        print(f"No se encontró la base viva del PC: {ruta_viva}")
        return 1
    if Path(ruta_vieja).resolve() == Path(ruta_viva).resolve():
        print("La base vieja y la viva son el MISMO archivo — eso no es una fusión.")
        return 1

    print("=" * 70)
    print("  FUSIONAR LA BASE VIEJA DE LA VM CON LA BASE VIVA DEL PC")
    print(f"  Base vieja (solo lectura): {ruta_vieja}")
    print(f"  Base viva del PC:          {ruta_viva}")
    print(f"  Modo: {'APLICAR (escribe)' if modo_aplicar else 'SOLO MIRAR (no escribe nada)'}")
    print("=" * 70)

    cv = sqlite3.connect(f"file:{ruta_vieja}?mode=ro", uri=True, timeout=30)
    for t in ("historial", "usuarios"):
        if not _existe_tabla(cv, t):
            print(f"\nEse archivo no parece la base del motor (no tiene la tabla '{t}').")
            cv.close()
            return 1

    if modo_aplicar:
        cn = sqlite3.connect(ruta_viva, timeout=30)
        cn.execute("PRAGMA busy_timeout=15000")
        respaldo = _respaldar(cn, ruta_viva)
        print(f"\nCopia de seguridad de la base viva: {respaldo}")
        cn.execute("BEGIN IMMEDIATE")
    else:
        cn = sqlite3.connect(f"file:{ruta_viva}?mode=ro", uri=True, timeout=30)
        cn.execute("PRAGMA busy_timeout=15000")

    try:
        res = fusionar(cv, cn, modo_aplicar, ruta_viva)
        if modo_aplicar:
            cn.commit()
    except Exception:
        if modo_aplicar:
            cn.rollback()
        raise
    finally:
        cv.close()
        cn.close()

    verbo = "traídos" if modo_aplicar else "por traer"
    print(f"\nGlosas con su historia ({verbo}):")
    print(f"   Glosas nuevas:        {res['glosas_nuevas']}")
    print(f"   Ya estaban (se saltan): {res['glosas_ya']}")
    for tabla, n in res["hijas"].items():
        print(f"   {tabla}: {n}")
    print(f"   conciliaciones: {res['conciliaciones']} (adjuntos: {res['adjuntos']})")
    print(f"   hilos de comentarios: {res['hilos']}")
    print(f"\nPrecedentes ganados: {res['gold_nuevas']} nuevos, {res['gold_ya']} ya estaban")
    print(f"Plantillas: {res['plantillas_nuevas']} nuevas, {res['plantillas_ya']} ya estaban")
    print(
        f"Usuarios: {len(res['usuarios_nuevos'])} nuevos, "
        f"{res['usuarios_ya']} ya estaban (conservan su clave del PC)"
    )
    if res["usuarios_nuevos"]:
        print(f"   nuevos: {', '.join(res['usuarios_nuevos'][:10])}")
    print(
        f"Contratos: {len(res['contratos_nuevos'])} nuevos, {res['contratos_ya']} ya estaban; "
        f"cláusulas: {res['clausulas']}"
    )
    if res["contratos_nuevos"]:
        print(f"   nuevos: {', '.join(str(e) for e in res['contratos_nuevos'][:10])}")
    print(f"Tarifas contratadas: {res['tarifas_nuevas']} nuevas, {res['tarifas_ya']} ya estaban")
    print(f"Credenciales de entidades: {res['credenciales']}")
    print(f"Rutas de soportes: {res['rutas']}   Atajos (snippets): {res['snippets']}")

    for aviso in res["avisos"]:
        print(f"\nOJO: {aviso}")

    if not modo_aplicar:
        print("\nNada se escribió (SOLO MIRAR). Para aplicar de verdad, agregue: aplicar")
    else:
        print("\nLISTO — la historia del módulo de glosas quedó fusionada en la base del PC.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
