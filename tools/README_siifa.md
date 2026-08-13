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

> **La forma fácil, sin escribir comandos:** doble clic en
> `tools\CARGAR_SIIFA.cmd`. Hace todo el flujo desde un menú (bajar el
> informe, armar los archivos, piloto de 1 glosa, cargue y reintentos), e
> instala solo lo que falte. El paso a paso escrito está en
> `docs/CARGUE_SIIFA_PASO_A_PASO.md`. Lo de abajo son los comandos sueltos.

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

### Direcciones de SIIFA (ya vienen configuradas, no hay que tocar nada)

| Servicio | URL |
|---|---|
| Seguridad (login) | `https://siifa.sispro.gov.co/siifa-seguridad` |
| Factura / Seguimiento | `https://siifa.sispro.gov.co/siifa-factura` |

Están confirmadas contra el servidor real de SIIFA. Sólo si algún día el
Ministerio las cambia habría que sobrescribirlas con `setx SIIFA_AUTH_URL ...`
y `setx SIIFA_BASE_URL ...`.

### Si algo no funciona: primero el diagnóstico

```powershell
py tools\siifa_reporte_seguimientos.py --diagnostico
```

Revisa en orden: (1) si hay conexión con SIIFA, (2) si el usuario y la
contraseña sirven, (3) si la consulta responde y cuántos registros hay. Dice
exactamente en qué paso está el problema, sin bajar nada.

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

### Qué llegó NUEVO desde la última revisión (`siifa_novedades.py`)

El portal muestra el total («Mostrando 2611 a 2620 de **2620** registros») pero
no dice cuáles son nuevos: buscarlos a mano son 175 páginas de a diez. Esto lo
responde de una: **qué entidad, qué factura, glosa o devolución, por cuánto y
con qué causal.**

```powershell
# 1) Guardar el informe que ya se tenía y bajar el de hoy
Move-Item "D:\USUARIO CARTERA\Documents\SIIFA\informe_seguimientos.xlsx" `
          "D:\USUARIO CARTERA\Documents\SIIFA\informe_ANTERIOR.xlsx" -Force

py tools\siifa_reporte_seguimientos.py `
  --salida "D:\USUARIO CARTERA\Documents\SIIFA\informe_seguimientos.xlsx"

# 2) Comparar los dos
py tools\siifa_novedades.py `
  --nuevo    "D:\USUARIO CARTERA\Documents\SIIFA\informe_seguimientos.xlsx" `
  --anterior "D:\USUARIO CARTERA\Documents\SIIFA\informe_ANTERIOR.xlsx"
```

Muestra el resumen en pantalla y deja `NOVEDADES_SIIFA.xlsx` al lado, con las
devoluciones resaltadas (se responden por otra puerta). En el bot de doble
clic es la **opción [N]**, que hace los dos pasos sola.

Si no se tiene el informe anterior a la mano, se corre solo con `--nuevo`: en
ese caso lista lo que está **sin responder**, que —estando el corte anterior
cargado al 100%— es justamente lo que acaba de entrar.

> **Ojo con el valor de las devoluciones:** SIIFA repite el valor de la
> factura en cada línea de la devolución. Este informe lo cuenta **una sola
> vez por factura**; sumarlas daría $24.917 millones donde hay $111 millones.

### En qué va cada glosa y qué se vence (`siifa_estado_tramite.py`)

El panel «Avance de auditoría» del portal muestra las cinco etapas del trámite
para **una** factura. Esto las muestra para todas, y sobre todo dice **qué
tiene que hacer el hospital y cuándo se vence**.

```powershell
py tools\siifa_estado_tramite.py `
  --informe "D:\USUARIO CARTERA\Documents\SIIFA\informe_seguimientos.xlsx" `
  --salida  "D:\USUARIO CARTERA\Documents\SIIFA\ESTADO_TRAMITE.xlsx"
```

En el bot de doble clic es la **opción [E]**. Muestra en pantalla:

- el conteo y el valor de cada etapa,
- **lo que le toca al hospital**, de mayor a menor valor, con su vencimiento,
- **las glosas levantadas** (lo que la EPS le dio al hospital: plata recuperada),
- **la EPS en mora**, cuando respondimos y no ha decidido dentro de su plazo.

> **Lo más importante: la etapa 4.** Cuando la EPS reitera una glosa, al
> hospital le quedan **7 días hábiles** para subsanar y nadie avisa. Una
> glosa reiterada que no se subsana queda en firme.

Los días hábiles se cuentan de lunes a viernes sin descontar festivos, así que
el aviso llega un poco antes de lo estricto — nunca después.

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

## 3.bis) Si "se queda pensando" y no saca la información

| Lo que se ve | Qué pasa realmente | Estado |
|---|---|---|
| Arranca bien y de golpe **fallan todas** las páginas | El token de SIIFA venció (dura pocos minutos) | **Resuelto**: el cliente se re-autentica solo y sigue |
| Tarda muchísimo sin mostrar nada | Se reintentaba, con esperas largas, un error que nunca se iba a arreglar | **Resuelto**: sólo se reintenta lo reintentable |
| Trae filas pero **todas vacías** | La API devolvió los campos con otra capitalización | **Resuelto**: se aceptan las dos formas |
| Nunca termina | La API ignoraba el número de página → daba vueltas para siempre | **Resuelto**: se detecta y se corta |
| Falla al instante | Sin internet o el proxy del hospital bloquea | Revisar la red — el mensaje ahora lo dice claro |

**El error de eficiencia más caro:** `SeguimientoFactura/List` **ya trae** el
número de factura, el valor y la EPS de cada glosa. Pedir además
`/api/Factura/{id}` por cada seguimiento convierte 13 llamadas en más de
2.500 — es lo que hace que un proceso tarde horas en vez de un minuto. Estas
herramientas no lo hacen.

## 4) Estados del reporte CSV

| Estado | Significado |
|---|---|
| `OK` | Respuesta registrada en SIIFA. |
| `ERROR` | La API rechazó la respuesta — ver columna `detalle` (código HTTP y mensaje). |
| `YA_OK_PREVIO` | Saltada porque ya estaba `OK` en un `--saltar-csv` anterior. |
