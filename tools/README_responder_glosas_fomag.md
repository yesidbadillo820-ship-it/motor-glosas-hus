# Guía: `responder_glosas_fomag.py` — Respuesta de glosas RATIFICADAS en FOMAG (Horus)

Bot Playwright que recorre el portal de FOMAG (`horus2.horus-health.com`,
administrado por Fiduprevisora) y carga la respuesta del prestador a las glosas
**ratificadas**, sin intervención manual salvo el login. Es el equivalente, para
FOMAG, de los bots `responder_glosas_coosalud.py` y `responder_glosas_simed.py`.

Reemplaza la operación manual de:

> *abrir cada factura, filtrar, dar RESPUESTA, elegir RE9901, escribir el texto
> de respuesta, subir el PDF, guardar la fila y dar GUARDAR RESPUESTA*

por una corrida con CSV de seguimiento y un pantallazo de evidencia por factura.

---

## 1) La gran diferencia con COOSALUD/SIMED: el reCAPTCHA

El login de Horus tiene un **reCAPTCHA "No soy un robot"** que **no se puede
automatizar**. La solución es un **perfil de navegador persistente**:

- La **primera** corrida del día se hace con `--con-cabeza`. El bot autollena
  email + contraseña y **vos resolvés el captcha y le das INGRESAR**. La sesión
  queda guardada en disco (carpeta `--perfil`, por defecto
  `%USERPROFILE%\.fomag_horus_profile`).
- Las corridas siguientes **reusan esa sesión** (mientras no expire) y ya no
  piden captcha; pueden ir headless.

> Si la sesión expiró, el bot vuelve a esperarte en el login: corré una vez con
> `--con-cabeza`, resolvé el captcha, y listo.

---

## 2) Credenciales (variables de entorno, nunca en el comando)

```cmd
setx FOMAG_USER 1098612385@fomag.com
setx FOMAG_PASSWORD <contraseña>
```

Una sola vez por máquina. Después se cierra y reabre la terminal para que las
tome. **Nunca pongas la contraseña en el comando** — queda en el historial.

---

## 3) Flujo por factura (lo que hace el bot)

1. **Auditoría** → cuadro naranja **"Facturas prestador"** → pestaña
   **RATIFICADAS**.
2. Escribe la factura en **"Número factura"** y da **FILTRAR**.
3. Click en el botón verde **RESPUESTA** de la fila.
4. Se abre el formulario "Respuesta — Factura # HUS…". Por **cada fila de
   servicio**, en este orden:
   1. **Cod Rta2 RAT** (dropdown) → elige **RE9901**.
   2. **Detalle Rta 2 prestador** (lápiz ✏️) → carga el texto fijo de ratificada.
   3. **Archivo** → sube `<factura>.pdf` desde `--pdf-dir` (se sube **antes** del
      ✓ porque al guardar la fila queda bloqueada y el botón de Archivo se apaga).
   4. **✓ (chulito) Guardar** de la fila → espera el cartel *"Respuesta guardada
      con exito!"*.
5. **Pantallazo de evidencia** en `--evidencias` (`<factura>_ratificada.png`),
   tomado **antes** de cerrar.
6. **GUARDAR RESPUESTA** (botón verde arriba a la derecha) → vuelve a la grilla.

### Respuesta estándar (igual para todas las ratificadas)

- **Código:** `RE9901` — *"la glosa siendo justificada ha podido ser subsanada
  totalmente"* (el HUS no acepta la ratificación y mantiene la objeción / pide
  conciliación). Cambiable con `--cod`.
- **Texto:** el fijo `TEXTO_RATIFICADA_DEFAULT` del script (*"ESE HUS NO ACEPTA
  GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE…"*). Cambiable con
  `--texto-archivo <txt>`.

---

## 4) Insumos

| Insumo | Flag | Detalle |
|---|---|---|
| Credenciales | env vars | `FOMAG_USER`, `FOMAG_PASSWORD` |
| Lista de facturas | `--solo` / `--facturas` / `--lista` | qué ratificadas responder |
| PDFs de respuesta | `--pdf-dir` | carpeta con `<factura>.pdf` (ej. `HUS511575.pdf`) |
| Texto (opcional) | `--texto-archivo` | si querés otro texto que el fijo |
| Carpeta evidencias | `--evidencias` | default `EVIDENCIA_FOMAG` |
| Reporte CSV | `--reporte` | estado por factura |

---

## 5) Modos

| Modo | Qué hace |
|---|---|
| `--listar` | Login + navega a la pestaña + vuelca **toda la grilla** (todas las páginas) a un CSV de inventario. **Read-only.** |
| `--diagnostico --solo HUS…` | Abre el formulario de RESPUESTA y vuelca su estructura (encabezados + HTML + screenshot) en `debug_screenshots/`. Para depurar selectores. No escribe nada. |
| `--responder --solo/--facturas/--lista` | Responde de verdad. Con `--sin-guardar` hace todo menos el ✓ y el GUARDAR RESPUESTA (piloto seguro). |

---

## 6) Recetas

### Primera corrida del día — iniciar sesión

```cmd
py tools\responder_glosas_fomag.py --listar --con-cabeza
```

Resolvé el captcha cuando el browser lo pida. Además te deja el inventario de
las RATIFICADAS en `reporte_fomag.csv`.

### Piloto seguro de una factura (no guarda nada)

```cmd
py tools\responder_glosas_fomag.py --responder --solo HUS511575 ^
    --pdf-dir "D:\...\FOMAG\GLOSAS\2026\5-JUNIO\PDF" ^
    --con-cabeza --sin-guardar
```

Mirá que elija RE9901, escriba el detalle y adjunte el PDF. Si todo se ve bien,
sacá `--sin-guardar`.

### Responder una factura de verdad

```cmd
py tools\responder_glosas_fomag.py --responder --solo HUS511575 ^
    --pdf-dir "D:\...\FOMAG\GLOSAS\2026\5-JUNIO\PDF" --con-cabeza
```

### Lote completo

```cmd
py tools\responder_glosas_fomag.py --responder ^
    --lista "D:\FOMAG\ratificadas.txt" ^
    --pdf-dir "D:\...\FOMAG\GLOSAS\2026\5-JUNIO\PDF" ^
    --reporte "D:\FOMAG\reporte_ratificadas.csv"
```

---

## 7) Estados del reporte (`--responder`)

| Estado | Significado |
|---|---|
| `OK` | todas las filas respondidas, guardadas y evidencia capturada |
| `PARCIAL` | algunas filas no se pudieron cargar (revisar evidencia) |
| `PILOTO_SIN_GUARDAR` | `--sin-guardar`: cargó sin commit |
| `SIN_FORMULARIO` | no abrió el formulario de RESPUESTA (¿factura no está en la pestaña?) |
| `SIN_FILAS` | el formulario no mostró filas de servicio |
| `SIN_BOTON_GUARDAR` | no apareció "GUARDAR RESPUESTA" |
| `ERROR` | excepción no clasificada (ver `debug_screenshots/`) |

---

## 8) Notas / pendientes a verificar en el primer piloto

El formulario de RESPUESTA es una grilla Angular ancha; los selectores del
**dropdown "Cod Rta2 RAT"** y del **editor del lápiz "Detalle Rta 2 prestador"**
se programaron a partir de los pantallazos. Si en el piloto headed algún paso
no entra:

- Corré `--diagnostico --solo HUS… --con-cabeza`: deja el HTML del formulario en
  `debug_screenshots/respuesta_form_HUS….html` y los índices de columna en el
  log. Con eso se afina el selector exacto en una línea.

Instalación (una vez):

```cmd
py -m pip install playwright openpyxl
py -m playwright install chromium
```
