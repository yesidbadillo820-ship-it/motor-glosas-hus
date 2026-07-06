# Migración Neon Postgres → SQLite en volumen Fly

**Contexto (17-jun-2026):** el free tier de Neon agotó la cuota de
transferencia de datos y tumbó producción (`Your project has exceeded the
data transfer quota`). La solución definitiva y **gratis**: mover la base
de datos a un archivo SQLite en el disco persistente `/data` de Fly. Cero
egress, cero cuota, sin proveedor externo.

El código ya está listo (este cambio). Solo falta **activar el secret** y,
opcionalmente, **migrar los datos** que están en Neon.

---

## Por qué SQLite aguanta esta app

- **1 sola máquina** en Fly (`min_machines_running = 1`, `auto_stop = off`).
- **1 worker** uvicorn + schedulers asyncio en threadpool.
- Modo **WAL** activado (lectores no bloquean al escritor) + `busy_timeout`
  de 30s (las escrituras esperan en vez de fallar con "database locked").
- Volumen **persistente** `/data` que sobrevive deploys y reinicios.
- Volumen de datos actual (cientos de glosas) → SQLite lo maneja de sobra.

El schema se crea solo en el **startup** de la app (lifespan en
`app/main.py`), que corre en la máquina con `/data` montado. Ya no hay
`release_command` que falle por la DB.

---

## Paso 1 — Migrar los datos de Neon (opcional, si quieres conservarlos)

Los datos (glosas, usuarios, contratos…) están en Neon. Para traerlos
necesitas acceso temporal a Neon: espera el reset mensual de la cuota o
haz un upgrade de 1 mes (cancelable). Con acceso:

```bash
# Desde la raíz del repo, con el entorno del proyecto activo:
PG_URL="postgresql://neondb_owner:TU_PASSWORD@ep-...neon.tech/neondb?sslmode=require" \
SQLITE_URL="sqlite:///./motorglosas.db" \
python scripts/migrar_neon_a_sqlite.py --dry-run     # primero en seco

# Si el conteo se ve bien, corre la migración real (quita --dry-run):
PG_URL="postgresql://..." SQLITE_URL="sqlite:///./motorglosas.db" \
python scripts/migrar_neon_a_sqlite.py
```

Esto genera `motorglosas.db` con TODAS las tablas copiadas en orden de
dependencias. Luego súbelo al volumen `/data` de Fly:

```bash
# Opción A: subir el archivo al volumen vía SFTP de Fly
fly ssh sftp shell -a motor-glosas-hus
# put motorglosas.db /data/motorglosas.db

# Opción B: si prefieres, corre el script DENTRO de la máquina Fly
# (con la máquina conectada a Neon) escribiendo directo a /data:
fly ssh console -a motor-glosas-hus
#   PG_URL="postgresql://..." SQLITE_URL="sqlite:////data/motorglosas.db" \
#   python scripts/migrar_neon_a_sqlite.py
```

> Si **no** necesitas conservar los datos de Neon, salta este paso: la app
> crea el schema vacío en el primer arranque y empiezas de cero.

---

## Paso 2 — Activar SQLite en producción

Cambia el secret `DATABASE_URL` para que apunte al archivo del volumen:

```bash
flyctl secrets set DATABASE_URL="sqlite:////data/motorglosas.db" -a motor-glosas-hus
```

> Ojo a las 4 barras: `sqlite:////data/...` = `sqlite:///` (prefijo) + `/data/...`
> (ruta absoluta). Con 3 barras sería una ruta relativa y NO usaría el volumen.

El cambio de secret dispara un redeploy. En el arranque verás en los logs:
```
Base de datos inicializada (intento 1)
```
y la app responde normal. **Producción revivida, sin Neon.**

---

## Paso 3 — Verificar

- Entra a la web: el login funciona, el Historial lista las glosas.
- Logs: `fly logs -a motor-glosas-hus` → sin errores de conexión a Neon.
- Backup: el scheduler de mantenimiento (3 AM) crea
  `/data/backups/motorglosas-YYYYMMDD-HHMMSS.db` y conserva los últimos 14.

---

## Rollback

Si algo sale mal, vuelve a Neon cambiando el secret de regreso:
```bash
flyctl secrets set DATABASE_URL="postgresql://...neon.tech/neondb?sslmode=require" -a motor-glosas-hus
```
(válido solo mientras Neon tenga cuota disponible).

---

## Mantenimiento de SQLite

- **Backups**: automáticos cada día a las 3 AM en `/data/backups/`
  (`app/services/backup_sqlite.py`, copia consistente con la API oficial
  de SQLite, rota 14). Descárgalos con `fly ssh sftp`.
- **Tamaño**: el volumen es de 3 GB. La DB + backups + soportes caben de
  sobra; si crece, sube el volumen con `fly volumes extend`.
- **WAL**: SQLite crea `motorglosas.db-wal` y `-shm` junto al archivo —
  es normal, no los borres.
