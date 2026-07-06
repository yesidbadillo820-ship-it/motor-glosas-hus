# Organizador de correos de glosas y devoluciones

Automatiza el proceso manual de la bandeja `glosasydevoluciones@hus.gov.co`:
abrir cada correo, imprimirlo a PDF, descargar los adjuntos y archivar todo en
el servidor de glosas (`Z:\SERVIDOR GLOSAS\...`), clasificado por fecha,
categoría y entidad pagadora.

## Qué hace

1. Se conecta por IMAP a la bandeja institucional (Gmail) y revisa los correos
   de los últimos N días (default: 3).
2. Clasifica cada correo por asunto y nombres de adjuntos en:
   `INICIAL`, `RATIFICADA`, `DEVOLUCIONES`, `CONCILIACIONES` o `0-REVISAR`
   (cuando no hay certeza — por ejemplo un correo que mezcla glosas y
   devoluciones — para que un humano decida; nada se pierde).
3. Detecta la entidad pagadora (DISPENSARIO/AUDITOOL, AXA, SEGUROS BOLIVAR,
   SALUD MIA, FACTRAMED, ...) por remitente, asunto o nombre de adjunto. Si no
   la reconoce, usa el dominio del remitente como carpeta.
4. Genera el PDF del correo (como la "impresión" manual de Gmail) y guarda
   los adjuntos renombrados con la misma convención del archivo manual:

       <base>\<AÑO>\<MM MES>\<DD>\<CATEGORÍA>\<ENTIDAD OK>\
           ├── <ENTIDAD> <h.mm> OK.pdf         (glosas: hora de llegada, ej. "AXA 7.21 OK.pdf")
           ├── <Asunto del correo> OK.pdf      (devoluciones: nombre por asunto)
           └── <ENTIDAD> <h.mm> OK.zip/.xlsx   (adjuntos, misma base + " (2)" si chocan)

   Ejemplo real:

       Z:\SERVIDOR GLOSAS\F\RECEPCIÓN DE GLOSAS (NO ELIMINAR CARPETA)\03-GLOSAS ESCANEADAS 2.0 (NO ELIMINAR CARPETA )\2026\07 JULIO\02\DEVOLUCIONES\DISPENSARIO OK\Devolución de Factura del Radicado No 100881 OK.pdf

   Si la carpeta del mes/día/categoría/entidad ya existe con marcas manuales
   (`07.JULIO`, `01 OK SOLO NUEVA`, `DEVOLUCIONES OK`, `DISPENSARIO SOFIA OK`),
   el script la **reutiliza** en vez de crear una duplicada. Los nombres
   originales de los adjuntos quedan en el registro CSV (columna `archivos`,
   formato `final <- original`); con `"renombrar_adjuntos": false` en el config
   conservan su nombre original.

5. Deja registro CSV mensual de todo lo archivado (abre directo en Excel) y le
   pone la etiqueta `Archivado-Glosas` al correo en Gmail.
6. La fecha de carpeta es la fecha de **llegada** del correo (hora Colombia),
   no la de ejecución.

**Lo que NUNCA hace:** borrar o mover correos, marcarlos como leídos (la
bandeja la siguen leyendo personas) ni sobreescribir archivos existentes (si
ya existe el nombre, agrega ` (2)`).

## Requisitos

- Python 3.11+ en el equipo que tenga mapeada la unidad `Z:`.
- `pip install reportlab` (para el PDF del correo). Si el equipo tiene
  Microsoft Edge o Chrome —cualquier Windows 10/11 lo tiene— el PDF se imprime
  con el navegador en modo oculto (mejor fidelidad) y reportlab queda de respaldo.
- Cuenta de Gmail con **verificación en dos pasos** activa y una
  **contraseña de aplicación** (ver abajo).

### Crear la contraseña de aplicación (una sola vez)

1. Entra a la cuenta `glosasydevoluciones@hus.gov.co` en el navegador.
2. Ve a <https://myaccount.google.com/security> y activa
   **Verificación en dos pasos** si no está activa.
3. Ve a <https://myaccount.google.com/apppasswords>, crea una contraseña de
   aplicación con nombre `Organizador Glosas` y copia el código de 16 letras.
4. En el equipo que va a ejecutar el organizador, abre `cmd` y ejecuta:

   ```bat
   setx GLOSAS_IMAP_USER glosasydevoluciones@hus.gov.co
   setx GLOSAS_IMAP_PASSWORD abcdabcdabcdabcd
   ```

   (sin espacios en la contraseña). Cierra y reabre la consola.

> **Nunca** compartas ni pegues esta contraseña en chats o correos. Si la
> opción "Contraseñas de aplicaciones" no aparece, el administrador de Google
> Workspace del hospital la tiene deshabilitada: pídele que la habilite para
> esta cuenta o que autorice el acceso IMAP.

## Uso rápido

```bash
# 1. SIEMPRE primero: simulacro. Muestra qué archivaría sin tocar nada.
py organizar_correos_glosas.py --dry-run

# 2. Corrida real (últimos 3 días; lo ya procesado no se repite)
py organizar_correos_glosas.py

# Backfill de un periodo (hasta 500 correos)
py organizar_correos_glosas.py --desde 2026-07-01 --max 500

# Probar en una carpeta local sin unidad Z:
py organizar_correos_glosas.py --base C:\pruebas\glosas --dry-run

# Con configuración propia de entidades/categorías
py organizar_correos_glosas.py --config organizar_correos_glosas_config.ejemplo.json
```

> En PowerShell la continuación de línea es `` ` `` y en cmd es `^`.

## Argumentos

| Argumento | Default | Descripción |
|---|---|---|
| `--base` | `Z:\SERVIDOR GLOSAS\...\03-GLOSAS ESCANEADAS 2.0 (NO ELIMINAR CARPETA )` | Carpeta raíz donde se archiva |
| `--control` | `<base>\00-CONTROL AUTOMATICO` | Carpeta de estado, registro CSV y logs |
| `--config` | (defaults internos) | JSON de entidades/categorías/plantillas |
| `--carpeta-imap` | `INBOX` | Carpeta IMAP a leer |
| `--dias` | `3` | Revisar correos de los últimos N días |
| `--desde` | — | Revisar desde una fecha (`AAAA-MM-DD`); reemplaza `--dias` |
| `--max` | `200` | Máximo de correos por corrida |
| `--dry-run` | — | No escribe ni etiqueta nada; solo muestra |
| `--no-marcar` | — | No poner la etiqueta de Gmail |
| `--sin-pdf-correo` | — | Guardar solo adjuntos, sin el PDF del correo |
| `--log` | `<control>\organizador.log` | Archivo de log (rotativo, 2 MB × 3) |

## Configurar entidades y categorías

Copia `organizar_correos_glosas_config.ejemplo.json`, edítalo y pásalo con
`--config`. Las claves que definas **reemplazan** a las de fábrica. Los
patrones son expresiones regulares que se comparan contra el texto en
MAYÚSCULAS y sin tildes.

Agregar una entidad nueva es agregar un bloque:

```json
{
  "carpeta": "NUEVA EPS",
  "remitente": ["NUEVAEPS", "@nuevaeps\\.com\\.co"],
  "asunto": ["NUEVA EPS"],
  "adjuntos": []
}
```

Las plantillas de nombres también se configuran ahí:

```json
"plantillas": {
  "carpeta_entidad": "{entidad} OK",
  "pdf_correo": {
    "DEVOLUCIONES": "{asunto} OK",
    "*": "{entidad} {hora} OK"
  }
}
```

Variables disponibles: `{entidad}`, `{hora}` (hora de llegada del correo en
formato 12 horas, ej. `7.21` o `1.30`), `{asunto}`, `{consecutivo}` (contador
por día y entidad) y `{radicado}` (número extraído del asunto, si hay).

## Registro CSV y carpeta de control

En `<base>\00-CONTROL AUTOMATICO` quedan:

| Archivo | Contenido |
|---|---|
| `registro_2026-07.csv` | Una fila por correo procesado (abre en Excel): fecha, remitente, asunto, categoría, entidad, carpeta destino, archivos, estado |
| `estado_organizador.json` | Message-ID ya procesados + consecutivos (la memoria del organizador — **no borrar**) |
| `organizador.log` | Log rotativo de las corridas |

Valores de `estado` en el registro: `ARCHIVADO`, `REVISAR` (quedó en
`0-REVISAR`), `IGNORADO` (notificaciones tipo "Cargue exitoso"), `DRY_RUN`,
`ERROR`.

## Programarlo cada 15 minutos (Programador de tareas)

Ejecuta una vez `instalar_organizador_correos.bat` como el usuario que tiene
la unidad `Z:` y las variables `GLOSAS_IMAP_*` configuradas. Crea la tarea
`HUS Organizador Correos Glosas` que corre cada 15 minutos. Para desinstalar:

```bat
schtasks /delete /tn "HUS Organizador Correos Glosas" /f
```

Para una corrida manual en cualquier momento: doble clic a
`organizar_correos_glosas.bat`.

> Las unidades mapeadas (`Z:`) a veces no existen para tareas programadas "al
> iniciar sesión no interactiva". Si el log muestra que no encuentra `Z:`,
> cambia `--base` por la ruta UNC directa (`\\servidor\recurso\SERVIDOR
> GLOSAS\...`) en el `.bat`.

## Re-ejecución segura

- Cada correo se procesa **una sola vez**: el Message-ID queda en
  `estado_organizador.json`. Re-ejecutar no duplica.
- Si una corrida se corta a mitad de un correo (por ejemplo se cayó la red),
  ese correo se reintenta en la próxima; los archivos que hayan quedado a
  medias aparecen con ` (2)` y el caso queda con estado `ERROR` en el log.
- `--dry-run` no consume consecutivos, no etiqueta y no guarda estado.

## Diagnóstico de problemas comunes

| Síntoma | Causa probable | Fix |
|---|---|---|
| `ERROR: faltan credenciales IMAP` | Variables sin configurar | `setx GLOSAS_IMAP_USER ...` y `setx GLOSAS_IMAP_PASSWORD ...`, reabrir consola |
| `login IMAP rechazado` | Se usó la clave normal, no la de aplicación | Generar contraseña de aplicación (ver arriba) |
| `no pude crear la carpeta de control` | Unidad `Z:` no mapeada en esa sesión | Mapear `Z:` o usar ruta UNC en `--base` |
| Todo cae en `0-REVISAR` | Asuntos con formato nuevo | Agregar patrones en `--config` |
| Entidad = dominio (ej. `SINACSC.COM`) | Remitente sin regla | Agregar bloque en `entidades` del config |
| El PDF del correo se ve plano/sin logos | No hay Edge/Chrome; usó reportlab | Instalar Edge/Chrome o definir `ORGANIZADOR_NAVEGADOR` con la ruta al .exe |
| No aparece "Contraseñas de aplicaciones" en Google | Deshabilitado por el admin de Workspace | Pedir al admin habilitarla para la cuenta |
