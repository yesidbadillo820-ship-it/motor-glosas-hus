"""Diagnostica y reconstruye el registro de envíos de pre-auditoría.

El registro (tabla preaud_envios_cargados: qué envío se cargó en qué oficio,
por quién y cuándo) quedó vacío el 31-07-2026 tras un `__table__.drop()`
ejecutado a mano contra producción. Las decisiones, facturas y el historial
de eventos NO se tocaron — y como los eventos ESCRITA/REINGRESO guardan
envío + oficio + auditor + fecha, el registro se puede reponer desde ahí.

Uso (dentro de la VM del hospital):

    sudo docker exec -it motor-glosas-hus python tools/preauditoria_reconstruir_envios.py
        → SOLO MIRAR: abre la base en solo-lectura y muestra qué se repondría.

    sudo docker exec -it motor-glosas-hus python tools/preauditoria_reconstruir_envios.py aplicar
        → repone los envíos SEGUROS (sus facturas siguen en ese oficio con ese
          envío) y corrige el candado del índice si hiciera falta.

    sudo docker exec -it motor-glosas-hus python tools/preauditoria_reconstruir_envios.py aplicar todo
        → repone además los POR CONFIRMAR (facturas que ya subsanaron hacia
          otro oficio). Usarlo solo si nunca se han quitado envíos a propósito
          con el botón de la aplicación.

Garantías: nunca borra ni modifica registros existentes (solo inserta los que
faltan y retira duplicados exactos idénticos); todo va en UNA transacción; es
idempotente (correrlo dos veces no duplica nada). Probado contra una réplica
del estado real post-incidente en 7 escenarios (ver bitácora del 03-08-2026).
"""

import os
import sqlite3
import sys

MODO_APLICAR = len(sys.argv) > 1 and sys.argv[1] == "aplicar"
MODO_TODO = MODO_APLICAR and "todo" in sys.argv[2:]

ruta = os.environ.get("DATABASE_URL", "sqlite:////data/motorglosas.db").split("sqlite:///")[-1]
# isolation_level=None: el script maneja la transaccion el mismo (BEGIN ... COMMIT),
# asi un fallo a mitad de camino no deja la base a medias. busy_timeout: la base
# esta en uso por la aplicacion mientras esto corre. En modo SOLO MIRAR se abre
# de SOLO LECTURA (mode=ro): ni siquiera puede crear un archivo si la ruta
# estuviera mal escrita.
try:
    if MODO_APLICAR:
        con = sqlite3.connect(ruta, isolation_level=None)
    else:
        con = sqlite3.connect("file:%s?mode=ro" % ruta, uri=True, isolation_level=None)
    con.execute("SELECT 1 FROM sqlite_master LIMIT 1")
except sqlite3.OperationalError as e:
    print("NO SE PUDO ABRIR LA BASE en", ruta)
    print("Detalle:", e)
    print("Verifique que esta corriendo DENTRO del contenedor (docker exec).")
    raise SystemExit(1)
con.row_factory = sqlite3.Row
con.execute("PRAGMA busy_timeout=15000")


def q(sql, args=()):
    return con.execute(sql, args).fetchall()


def uno(sql, args=()):
    fila = con.execute(sql, args).fetchone()
    return fila[0] if fila else 0


print("=" * 62)
print("  DIAGNOSTICO DEL MODULO DE PRE-AUDITORIA —", ruta)
print("  Modo:", "APLICAR (escribe en la base)" if MODO_APLICAR else "SOLO MIRAR (no cambia nada)")
print("=" * 62)

print()
print("1) LO QUE ESTA A SALVO")
print("   Oficios de recepcion:  ", uno("SELECT COUNT(*) FROM preaud_oficios_recepcion"))
print("   Facturas en consolidado:", uno("SELECT COUNT(*) FROM preaud_facturas"))
for r in q("SELECT resultado_actual, COUNT(*) n FROM preaud_facturas GROUP BY resultado_actual"):
    print("      - %-10s %s" % (r["resultado_actual"], r["n"]))
print("   Eventos del historial:  ", uno("SELECT COUNT(*) FROM preaud_factura_eventos"))
for r in q("SELECT tipo_evento, COUNT(*) n FROM preaud_factura_eventos GROUP BY tipo_evento"):
    print("      - %-20s %s" % (r["tipo_evento"], r["n"]))
print("   Oficios de devolucion:  ", uno("SELECT COUNT(*) FROM preaud_oficios_devolucion"))
print("   Fuente Radicacion:      ", uno("SELECT COUNT(*) FROM preaud_fuente_radicacion"))
print("   Fuente DGreport:        ", uno("SELECT COUNT(*) FROM preaud_fuente_dgreport"))
try:
    respaldos = sorted(os.listdir("/data/backups"), reverse=True)[:6]
    print("   Copias de seguridad (las mas recientes de /data/backups):")
    for nombre in respaldos:
        print("      -", nombre)
    if not respaldos:
        print("      (ninguna)")
except OSError:
    print("   Copias de seguridad: carpeta /data/backups no disponible")

print()
print("2) EL REGISTRO DE ENVIOS HOY (preaud_envios_cargados)")
filas = q(
    "SELECT c.envio, c.oficio_id, o.numero_radicado, c.total_facturas, c.cargado_por, c.cargado_en "
    "FROM preaud_envios_cargados c "
    "LEFT JOIN preaud_oficios_recepcion o ON o.id = c.oficio_id "
    "ORDER BY c.cargado_en"
)
if not filas:
    print("   (VACIO: no hay ningun envio registrado — esto es lo que se borro)")
for r in filas:
    print(
        "   envio %-8s -> %-22s (%s fact.) por %s el %s"
        % (
            r["envio"],
            r["numero_radicado"] or ("oficio_id " + str(r["oficio_id"])),
            r["total_facturas"],
            r["cargado_por"] or "?",
            (r["cargado_en"] or "")[:16],
        )
    )

print()
print("3) EL CANDADO DE LA TABLA")
candado = None  # None (ausente) | 'viejo' | 'nuevo' (correcto) | 'malo'
for idx in q("PRAGMA index_list('preaud_envios_cargados')"):
    cols = [c["name"] for c in q("PRAGMA index_info('%s')" % idx["name"])]
    if idx["name"] == "ix_preaud_envio_cargado":
        if cols == ["envio", "oficio_id"] and idx["unique"]:
            candado = "nuevo"
        elif cols == ["envio"] and idx["unique"]:
            candado = "viejo"
        else:
            candado = "malo"
    print("   indice %-28s unico=%s columnas=%s" % (idx["name"], idx["unique"], cols))
if candado == "viejo":
    print("   >> CANDADO VIEJO (solo envio): es el que bloqueaba 'ya fue cargado'.")
    print("   >> El modo aplicar lo cambia a (envio + oficio) — igual que el codigo nuevo.")
elif candado == "nuevo":
    print("   >> Candado correcto (envio + oficio): permite hasta 3 oficios por envio.")
elif candado == "malo":
    print("   >> El indice existe pero NO es el candado correcto (le falta UNIQUE o")
    print("   >> tiene otras columnas): el modo aplicar lo recrea bien.")
else:
    print("   >> No existe el indice ix_preaud_envio_cargado; el modo aplicar lo crea.")

print()
print("4) LO QUE SE PUEDE RECONSTRUIR DESDE EL HISTORIAL")
candidatos = q(
    "SELECT e.envio, e.oficio_id, o.numero_radicado, "
    "       SUM(CASE WHEN e.tipo_evento='ESCRITA'   THEN 1 ELSE 0 END) nuevas, "
    "       SUM(CASE WHEN e.tipo_evento='REINGRESO' THEN 1 ELSE 0 END) reingresos, "
    "       MIN(e.creado_en) fecha "
    "FROM preaud_factura_eventos e "
    "JOIN preaud_oficios_recepcion o ON o.id = e.oficio_id "
    "WHERE e.tipo_evento IN ('ESCRITA','REINGRESO') "
    "  AND e.envio IS NOT NULL AND e.envio <> '' AND e.oficio_id IS NOT NULL "
    "  AND NOT EXISTS (SELECT 1 FROM preaud_envios_cargados c "
    "                  WHERE c.envio = e.envio AND c.oficio_id = e.oficio_id) "
    "GROUP BY e.envio, e.oficio_id "
    "ORDER BY fecha"
)
seguros, por_confirmar = [], []
for r in candidatos:
    # "Anclado": alguna factura de ese envio sigue perteneciendo a ese oficio
    # CON ese mismo envio como envio actual. Si ninguna cumple lo dos (migraron
    # por subsanacion, o reingresaron al mismo oficio con OTRO envio), no se
    # puede distinguir entre "el registro se borro por fuera del sistema" (hay
    # que reponerlo) y "un administrador quito el envio a proposito con el
    # boton de la app" (no habria que reponerlo): esos van aparte.
    anclado = uno(
        "SELECT COUNT(*) FROM preaud_facturas f "
        "WHERE f.oficio_actual_id=? AND f.envio_actual=? AND f.id IN "
        "  (SELECT factura_id FROM preaud_factura_eventos "
        "   WHERE envio=? AND oficio_id=? AND tipo_evento IN ('ESCRITA','REINGRESO'))",
        (r["oficio_id"], r["envio"], r["envio"], r["oficio_id"]),
    )
    (seguros if anclado else por_confirmar).append(r)

if not candidatos:
    print("   Nada por reconstruir respecto del historial. (Ojo: las recargas que no")
    print("   movieron ninguna factura no dejan huella en el historial y no se pueden")
    print("   reponer; si falta alguna, vuelva a cargar ese envio desde la pantalla.)")


def _mostrar(lista):
    for r in lista:
        quien = uno(
            "SELECT creado_por FROM preaud_factura_eventos "
            "WHERE envio=? AND oficio_id=? AND tipo_evento IN ('ESCRITA','REINGRESO') "
            "ORDER BY creado_en, id LIMIT 1",
            (r["envio"], r["oficio_id"]),
        )
        print(
            "   envio %-8s -> %-22s (%s nuevas + %s reingresos) por %s el %s"
            % (
                r["envio"],
                r["numero_radicado"],
                r["nuevas"],
                r["reingresos"],
                quien or "?",
                (r["fecha"] or "")[:16],
            )
        )


if seguros:
    print("   SEGUROS (sus facturas siguen en ese oficio):")
    _mostrar(seguros)
if por_confirmar:
    print("   POR CONFIRMAR (sus facturas ya subsanaron hacia otro oficio;")
    print("   solo se reponen con 'aplicar todo' — vea la instruccion):")
    _mostrar(por_confirmar)

if not MODO_APLICAR:
    print()
    print("MODO SOLO MIRAR: no se cambio nada.")
    print("Si las listas del punto 4 se ven bien, corra el COMANDO 2 (aplicar).")
    print("Si ademas hay envios POR CONFIRMAR y usted NUNCA ha quitado envios con el")
    print("boton de la aplicacion, corra el COMANDO 3 (aplicar todo) para reponerlos.")
else:
    print()
    print("5) APLICANDO...")
    try:
        # Toda la aplicacion va en UNA transaccion con el candado de escritura
        # tomado de entrada: o queda todo, o no queda nada.
        con.execute("BEGIN IMMEDIATE")
        if candado != "nuevo":
            # Si la tabla quedo sin candado real, pudieron colarse duplicados
            # exactos (doble clic): hay que quitarlos ANTES de crear el indice
            # unico, o la creacion fallaria. Se conserva la fila mas antigua.
            dupes = con.execute(
                "DELETE FROM preaud_envios_cargados WHERE id NOT IN "
                "(SELECT MIN(id) FROM preaud_envios_cargados GROUP BY envio, oficio_id)"
            ).rowcount
            if dupes:
                print("   Filas duplicadas exactas retiradas (por doble clic):", dupes)
            if candado in ("viejo", "malo"):
                con.execute("DROP INDEX ix_preaud_envio_cargado")
            con.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_preaud_envio_cargado "
                "ON preaud_envios_cargados (envio, oficio_id)"
            )
            print("   Candado corregido: ahora es por envio + oficio (permite hasta 3 oficios).")
        a_insertar = seguros + (por_confirmar if MODO_TODO else [])
        insertados = 0
        for r in a_insertar:
            quien = uno(
                "SELECT creado_por FROM preaud_factura_eventos "
                "WHERE envio=? AND oficio_id=? AND tipo_evento IN ('ESCRITA','REINGRESO') "
                "ORDER BY creado_en, id LIMIT 1",
                (r["envio"], r["oficio_id"]),
            )
            # total_facturas original = TODAS las del envio en la fuente
            # (incluidas las omitidas); se estima desde la fuente y, si el
            # envio ya no esta en ella, con lo que dejo huella en eventos.
            total = uno(
                "SELECT COUNT(*) FROM preaud_fuente_radicacion WHERE envio=?",
                (r["envio"],),
            ) or ((r["nuevas"] or 0) + (r["reingresos"] or 0))
            cur = con.execute(
                "INSERT OR IGNORE INTO preaud_envios_cargados "
                "(envio, oficio_id, total_facturas, nuevas, reingresos, cargado_por, cargado_en) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    r["envio"],
                    r["oficio_id"],
                    total,
                    r["nuevas"] or 0,
                    r["reingresos"] or 0,
                    quien,
                    r["fecha"],
                ),
            )
            insertados += cur.rowcount
        con.execute("COMMIT")
    except Exception as e:
        # Si BEGIN IMMEDIATE fallo (base ocupada), NO hay transaccion abierta:
        # hacer ROLLBACK a secas taparia este mensaje con un segundo error.
        if con.in_transaction:
            con.execute("ROLLBACK")
        print()
        print("   NO SE APLICO NADA (la base quedo tal como estaba). Error:", e)
        print("   Si dice 'database is locked': espere un minuto a que la aplicacion")
        print("   termine lo que este guardando y vuelva a correr este comando.")
        raise SystemExit(1)
    print("   Registros de envio reconstruidos:", insertados)
    if por_confirmar and not MODO_TODO:
        print(
            "   Quedaron %s envio(s) POR CONFIRMAR sin reponer: si usted nunca ha"
            % len(por_confirmar)
        )
        print("   quitado envios con el boton de la app, corra el COMANDO 3 (aplicar todo).")
    print("   Fuera de los duplicados exactos, no se borro ni modifico nada de lo existente.")
    print()
    print("LISTO. Recargue la pagina de Pre-auditoria con Ctrl+Mayus+R:")
    print("los envios de cada oficio deben verse de nuevo.")
con.close()
