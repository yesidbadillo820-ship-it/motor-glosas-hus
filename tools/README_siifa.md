# Guía: informe masivo y bot de respuestas SIIFA

Dos scripts nuevos para la plataforma **SIIFA** (Ministerio de Salud —
módulo de Seguimiento de facturas), distinta de COOSALUD/SIMED/DGH. Contexto
completo de la plataforma, roles y plazos en `docs/CONTEXTO_SIIFA.md`.

A diferencia de los bots COOSALUD/SIMED (Playwright, porque esos portales no
tienen API), **SIIFA sí publica una API oficial de interoperabilidad**, así
que estos dos scripts hablan HTTP directo — no abren navegador, no dependen
de que cambie un botón en la pantalla.

| Script | Para qué |
|---|---|
| `tools/siifa_reporte_seguimientos.py` | Trae **todas** las glosas/devoluciones del HUS registradas en SIIFA (los 2.579+ registros de `Listar seguimientos`) y arma un Excel — resuelve "verlas en un informe masivo". |
| `tools/responder_glosas_siifa.py` | Lee un Excel tipificado y carga cada respuesta en SIIFA por API — resuelve "un bot que ayude a cargar las respuestas". |

---

## 0) Antes de la primera corrida

### Instalar dependencias (una sola vez)

```powershell
py -m pip install httpx openpyxl
```

### Credenciales — SIEMPRE por variable de entorno, nunca en el código

```powershell
setx SIIFA_USER <tu_usuario_sispro>
setx SIIFA_PASSWORD <tu_password>
```

Cerrar y volver a abrir PowerShell para que las tome.

### ⚠️ La URL del servicio de autenticación NO está confirmada

Los manuales que tenemos documentan bien la API de Factura/Seguimiento
(`https://siifa.sispro.gov.co/siifa-factura`, confirmada), pero **no traen la
URL del servicio de login** (`POST /api/Auth/login`). El script usa por
default una hipótesis razonable
(`https://siifa.sispro.gov.co/siifa-seguridad`) basada en el mismo patrón de
nombres, pero **hay que verificarla** — si el primer comando (el piloto de
abajo) falla con un error de conexión, ese es el primer sospechoso, no las
credenciales. Si hace falta corregirla:

```powershell
setx SIIFA_AUTH_URL https://<url-correcta-que-confirme-mesa-de-ayuda-SIIFA>
```

Cómo confirmarla: mesa de ayuda SIIFA / soporte MinSalud, o el enlace de
autenticación del micrositio https://www.minsalud.gov.co/SIIFA.

### Ir a la carpeta del repo

```powershell
cd C:\temp-notas
git pull
```

---

## 1) Informe masivo de las glosas (`siifa_reporte_seguimientos.py`)

### Todo lo que haya (glosas + devoluciones)

```powershell
py tools\siifa_reporte_seguimientos.py `
  --salida "D:\USUARIO CARTERA\Documents\SIIFA\informe_seguimientos.xlsx"
```

### Solo lo pendiente por responder (para priorizar el trabajo del día)

```powershell
py tools\siifa_reporte_seguimientos.py `
  --tipo GLOSA --sin-respuesta `
  --salida "D:\USUARIO CARTERA\Documents\SIIFA\glosas_pendientes.xlsx"
```

### Una sola factura

```powershell
py tools\siifa_reporte_seguimientos.py `
  --factura HUS532426 `
  --salida "D:\USUARIO CARTERA\Documents\SIIFA\HUS532426.xlsx"
```

El Excel trae la hoja **SEGUIMIENTOS** (una fila por glosa, con
`id_seguimiento_factura_glosa` — ese id es el que necesita el bot de
respuestas más abajo) y una hoja **RESUMEN** con totales por EPS y valor
glosado. Las filas sin respuesta quedan resaltadas.

---

## 2) Bot de respuestas (`responder_glosas_siifa.py`)

### Paso 1 — ver los códigos de respuesta válidos

No necesita Excel, sirve para tipificar sabiendo qué códigos existen:

```powershell
py tools\responder_glosas_siifa.py --listar-catalogo
```

### Paso 2 — tipificar el Excel

Tomar el Excel de "pendientes" del paso anterior (o armar uno nuevo) y
completar dos columnas por cada glosa que se va a responder:

| Columna | Contenido |
|---|---|
| `ID_SEGUIMIENTO_FACTURA_GLOSA` | Viene del informe (columna `id_seguimiento_factura_glosa`). |
| `NUMERO_FACTURA` | Informativo, solo para el reporte. |
| `CODIGO_RESPUESTA` | Código de la tabla del paso 1 (ej. `RESP01`). |
| `OBSERVACION_RESPUESTA` | Texto de sustento. |
| `FECHA_RESPUESTA` | Opcional, AAAA-MM-DD (si se deja vacía usa la fecha de hoy). |

### Paso 3 — PILOTO de una sola glosa (regla del repo, obligatoria)

```powershell
py tools\responder_glosas_siifa.py `
  --excel "D:\USUARIO CARTERA\Downloads\respuestas_siifa.xlsx" `
  --solo-id 123456 `
  --reporte "D:\USUARIO CARTERA\Documents\SIIFA\piloto_siifa.csv"
```

Revisar el CSV: debe decir `OK`. Si dice `ERROR`, leer el detalle antes de
seguir (puede ser un código de respuesta que no está activo, o una fecha de
respuesta anterior a la fecha en que la EPS formuló la glosa — SIIFA lo
rechaza).

### Paso 4 — cargue completo

```powershell
py tools\responder_glosas_siifa.py `
  --excel "D:\USUARIO CARTERA\Downloads\respuestas_siifa.xlsx" `
  --reporte "D:\USUARIO CARTERA\Documents\SIIFA\reporte_siifa.csv"
```

### Paso 5 — si algo quedó en ERROR, reintentar solo eso

El bot **no duplica** lo que ya quedó OK:

```powershell
py tools\responder_glosas_siifa.py `
  --excel "D:\USUARIO CARTERA\Downloads\respuestas_siifa.xlsx" `
  --saltar-csv "D:\USUARIO CARTERA\Documents\SIIFA\reporte_siifa.csv" `
  --reporte "D:\USUARIO CARTERA\Documents\SIIFA\reporte_siifa_pass2.csv"
```

### Paso adicional — subsanación (glosa que la EPS reiteró, no levantó)

Mismo Excel/flujo, pero con `--accion reiteracion-respuesta`:

```powershell
py tools\responder_glosas_siifa.py `
  --excel "D:\USUARIO CARTERA\Downloads\subsanaciones_siifa.xlsx" `
  --accion reiteracion-respuesta `
  --reporte "D:\USUARIO CARTERA\Documents\SIIFA\reporte_subsanacion.csv"
```

---

## 3) Recordatorio importante — SIIFA no reemplaza el portal de la EPS

Responder en SIIFA **no es lo mismo** que responder en el portal propio de la
EPS (COOSALUD, etc.). Son trámites paralelos que hay que cumplir los dos:
según el manual funcional del módulo 3, cada actuación debe quedar en SIIFA
"preferiblemente por interoperabilidad o a más tardar durante las siguientes
48 horas hábiles". Ver los plazos completos del trámite de glosa en
`docs/CONTEXTO_SIIFA.md` §4.

## 4) Estados del reporte CSV

| Estado | Significado |
|---|---|
| `OK` | Respuesta registrada en SIIFA. |
| `ERROR` | La API rechazó la respuesta — ver columna `detalle` (código HTTP y mensaje). |
| `YA_OK_PREVIO` | Saltada porque ya estaba `OK` en un `--saltar-csv` anterior. |
