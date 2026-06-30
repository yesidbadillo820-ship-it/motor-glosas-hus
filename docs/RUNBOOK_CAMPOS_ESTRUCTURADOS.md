# Runbook — Activar la Mejora #3 (salida estructurada) en la VM

Mejora #3: la IA confirma los campos críticos (EPS, servicio, contrato,
cláusulas, sanción, sub-conceptos) en un bloque JSON que el motor cruza
contra los valores **deterministas** y registra divergencias. Está
**OFF por defecto** y es **100% reversible** (basta volver el flag a `0`).

> Recordatorio: hay una sola VM (producción). Activar el flag cambia el
> prompt para TODAS las glosas que se procesen mientras esté en ON. Por eso
> se activa, se prueban los 3 casos conocidos, se vigilan los logs, y se
> deja en OFF si algo se ve raro.

---

## Parte 0 — Merge del PR #153

Revisar y mergear el PR #153 a `motor-glosas` en GitHub. El flag viene en
OFF, así que el merge **no cambia el comportamiento** en producción.

---

## Parte 1 — Desplegar el código (con el flag aún en OFF)

Esto valida que el deploy funciona sin tocar el comportamiento todavía.

```bash
cd /opt/motor-glosas
# Si git se queja de "dubious ownership":
sudo git config --global --add safe.directory /opt/motor-glosas
sudo git fetch origin
sudo git checkout motor-glosas
sudo git pull origin motor-glosas
# Rebuild: el código va HORNEADO en la imagen (COPY app/), por eso --build
sudo docker compose up -d --build
```

Verificar que la app sigue arriba:

```bash
sudo docker compose ps          # motor: Up (healthy)
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/health   # 200
```

Refrescar `iaglosassinac.help` (Ctrl+Shift+R) → debe cargar normal.

---

## Parte 2 — Activar el flag y probar

**1. Agregar el flag al `.env`:**

```bash
cd /opt/motor-glosas
echo 'GLOSA_CAMPOS_ESTRUCTURADOS=true' | sudo tee -a .env
# Verificar que quedó (debe aparecer una sola vez):
grep GLOSA_CAMPOS_ESTRUCTURADOS .env
```

**2. Recrear el contenedor para que tome la variable:**

```bash
sudo docker compose up -d --build
```

**3. Vigilar la telemetría en vivo (deja esta terminal abierta):**

```bash
sudo docker compose logs motor -f | grep --line-buffered CAMPOS-EST
```

**4. En otra pestaña del navegador**, reanalizar los 3 casos difíciles
(SALUD TOTAL TMS, ECOOPSOS implante coclear, MEDIMÁS da Vinci). En los
logs deberías ver, por cada análisis:

- `[CAMPOS-EST] bloque parseado: eps=... contrato=... clausulas=...`
  → la IA emitió el bloque y se parseó.
- `[CAMPOS-EST] divergencias ...` → **solo** si la IA contradijo al
  determinista. Lo ideal es que NO aparezca (o muy poco). Cada divergencia
  es un caso a revisar.

**5. Revisar los dictámenes** de los 3 casos: que detecten bien la EPS, que
no peguen placeholders al servicio, que respondan cada sub-concepto.

---

## Parte 3 — Decidir

- **Si todo se ve bien y casi no hay divergencias:** dejar el flag ON.
  Tras unos días de telemetría limpia, se puede evaluar jubilar más
  sanitizers (otro PR, con evidencia).
- **Si hay divergencias frecuentes o algo se ve raro:** apagar de inmediato.

### Rollback (instantáneo)

```bash
cd /opt/motor-glosas
sudo sed -i 's/^GLOSA_CAMPOS_ESTRUCTURADOS=.*/GLOSA_CAMPOS_ESTRUCTURADOS=0/' .env
sudo docker compose up -d --build
```

Con el flag en `0`, el pipeline vuelve a ser **idéntico** al de antes de la
mejora (degradación elegante total). No se pierde nada.

---

## Notas

- **No hace falta limpiar caché.** La clave de caché incluye el texto
  completo del prompt; con el flag ON el prompt es más largo y obtiene
  claves nuevas automáticamente. Apagar el flag vuelve a las claves viejas.
- **Multi-código:** con varias secciones por glosa, los skips se desactivan
  solos (un bloque no representa N contratos).
- **El bloque `<CAMPOS_ESTRUCTURADOS>` nunca aparece en el dictamen
  radicable** — se borra siempre, con el flag ON u OFF.
