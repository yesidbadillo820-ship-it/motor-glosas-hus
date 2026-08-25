# Documentación oficial del módulo — Organizador y Extractor de Glosas

> **Módulo:** Recepción automática de glosas por correo (bot organizador) + Extractor de detalle / Excel de entrega para gestores.
> **Repositorio:** `motor-glosas-hus`
> **Rama de desarrollo:** `claude/archived-chats-view-au8nqp`
> **Ubicación en el repo:** `tools/` (herramientas autónomas) y `tests/test_tools/` (pruebas).
> **Estado:** Funcional, en pruebas controladas en el equipo de cartera; pendiente el paso a producción.
> **Naturaleza:** Dos herramientas de línea de comandos (scripts Python autónomos) que NO forman parte de la aplicación web FastAPI; se ejecutan en el equipo Windows del área de cartera. Se apoyan en el mismo repositorio pero son independientes del servidor.

Este documento reconstruye, sin resumir, todo lo desarrollado en la conversación que originó el módulo. Está pensado para que el equipo principal pueda mantenerlo, integrarlo y evolucionarlo sin haber participado en su construcción.

---

## 1. Objetivo del desarrollo

### Por qué se creó
El área de cartera del Hospital Universitario de Santander (HUS) recibe en la bandeja institucional **glosasydevoluciones@hus.gov.co** cientos de correos diarios de las entidades pagadoras (EPS, aseguradoras, ADRES, direcciones de sanidad militar/policial) con **glosas** (objeciones a las facturas) y **devoluciones**. La bandeja acumula decenas de miles de correos (en las capturas se observó "1–50 de 78.905").

Hasta este desarrollo, **todo el proceso era manual**: una persona abría cada correo uno por uno, lo imprimía a PDF, descargaba los adjuntos, decidía a criterio si era glosa inicial, ratificada o devolución, identificaba de qué entidad venía, y lo archivaba a mano en el servidor de glosas (unidad de red `Z:`) en una estructura de carpetas por año / mes / día / categoría / entidad. Después armaba a mano un Excel de entrega para repartir el trabajo entre los gestores.

### Qué problema resolvía
- **Carga operativa alta:** el procesamiento manual de la bandeja ocupaba varias horas de trabajo diarias.
- **Riesgo de error y omisión:** dependía por completo de la persona a cargo.
- **Riesgo de recaudo:** cada glosa tiene un plazo legal de respuesta (15 días hábiles las iniciales, 7 las ratificadas). Una glosa no respondida a tiempo es dinero que el hospital deja de recibir.
- **Falta de trazabilidad:** no había registro sistemático de qué se recibió, cuándo y dónde se archivó.

### Qué necesidad cubre
1. **Recibir y archivar** automáticamente cada correo de glosa en la estructura exacta del servidor, sin intervención humana, cada 15 minutos.
2. **Clasificar** cada correo por categoría (inicial / ratificada / devolución / conciliación) y por entidad pagadora.
3. **Preparar el archivo de entrega** para los gestores, con el responsable asignado por entidad y las fechas de vencimiento calculadas.
4. Hacerlo **sin alterar la bandeja** (que el equipo sigue usando) y con **registro auditable** de todo.

### Resultado medido (sobre la operación real)
- La revisión manual pasó del **72 % al 8 %** de los correos (89 % menos trabajo manual), medido re-clasificando un registro real de **904 correos** de julio.
- Se validó contra ~**2.600 correos** de una ventana de 3 días, **4 días reales de julio** (~**4.500 facturas** extraídas) y **683 PDF** de salida real del bot.
- **30+ entidades** pagadoras reconocidas automáticamente.
- **151 pruebas automatizadas** respaldan las reglas del módulo.

---

## 2. Arquitectura

### Estructura del módulo
El módulo son **dos herramientas de línea de comandos independientes**, más su instalación y documentación. Todo vive en `tools/` (convención del repo para scripts autónomos que corren fuera de la app web).

```
tools/
├── organizar_correos_glosas.py            # HERRAMIENTA 1 — bot organizador (1.617 líneas)
├── extraer_detalle_glosas.py              # HERRAMIENTA 2 — extractor / Excel de entrega (1.241 líneas)
├── organizar_correos_glosas_config.ejemplo.json   # Config editable de entidades/categorías (generado desde el código)
├── gestores_glosas.ejemplo.json           # Mapeo entidad → gestor (generado desde el código)
├── INSTALAR_BOT_GLOSAS.bat                 # Instalador interactivo de un clic
├── instalar_organizador_correos.bat        # Crea la tarea programada (cada 15 min)
├── organizador_tarea.bat                    # Runner que ejecuta la tarea y deja log
├── organizar_correos_glosas.bat             # Corrida manual (con pausa)
├── CAMBIAR_CARPETA_DESTINO.bat              # Cambia entre carpeta de pruebas y servidor
├── README_organizar_correos_glosas.md      # Manual del bot organizador
└── README_extraer_detalle_glosas.md        # Manual del extractor

tests/test_tools/
├── test_organizar_correos_glosas.py        # Pruebas del bot organizador
└── test_extraer_detalle_glosas.py          # Pruebas del extractor
```

### Componentes lógicos

**Herramienta 1 — `organizar_correos_glosas.py`** (bot organizador). Subsistemas internos:
- **Conexión IMAP** (Gmail): login, selección de carpeta, búsqueda por fecha, descarga de encabezados y de mensajes completos, etiquetado.
- **Clasificación**: por asunto, por nombres de adjuntos y por contenido de los adjuntos.
- **Detección de entidad**: por remitente, asunto y adjuntos, contra reglas configurables.
- **Extracción de partes del correo**: texto, HTML, imágenes en línea, adjuntos (incluye correos reenviados `.eml` y adjuntos sin nombre).
- **Generación del PDF del correo**: vía navegador headless (Edge/Chrome) o vía reportlab de respaldo.
- **Construcción de rutas de destino** en el servidor, con reutilización de carpetas marcadas a mano.
- **Estado persistente** (`Estado`): deduplicación por Message-ID, reintentos, consecutivos por día/entidad.
- **Registro CSV** mensual auditable.
- **Orquestación** (`main` / `_procesar_uid`): lock entre corridas, tope de reintentos, tope de correos por corrida.

**Herramienta 2 — `extraer_detalle_glosas.py`** (extractor). Subsistemas internos:
- **Conversores** (`a_fecha`, `a_numero`, `sumar_habiles`): normalizan fechas y montos colombianos y calculan vencimientos en días hábiles.
- **Parsers por formato**: nueve parsers distintos (AUDITOOL csv, Famisanar txt, Sura txt, Sanitas xlsx, Policía "objeciones" xlsx, Savia xlsx, Coosalud xlsx, Policía "GLOSA A RAD" xlsx, FACTRAMED xlsx) + parsers de PDF (AXA, Bolívar) + fallback por nombre.
- **Despacho por firma de columnas** (`_parser_xlsx_auto`): abre cada Excel una sola vez y enruta al parser correcto.
- **Recorrido de la carpeta de un día** (`recorrer_dia`, `extraer_de_archivo`): abre `.zip` recursivamente con tope de profundidad, tolera archivos corruptos.
- **Agrupación por factura** y **escritura del Excel de entrega** (`escribir_entrega`) con hojas INICIAL / RATIFICADA / DEVOLUCIONES + RESUMEN.
- **Mapeo de gestores** (`info_entidad`, `responsable_para`).

### Carpetas
- **Origen (bot):** la bandeja IMAP de Gmail.
- **Destino (bot):** `Z:\SERVIDOR GLOSAS\F\RECEPCIÓN DE GLOSAS (NO ELIMINAR CARPETA)\03-GLOSAS ESCANEADAS 2.0 (NO ELIMINAR CARPETA )` con la estructura `AÑO\MM MES\DD\CATEGORÍA\ENTIDAD\`.
- **Control (bot):** subcarpeta `00-CONTROL AUTOMATICO` dentro del destino: guarda el estado (`estado_organizador.json`), el registro (`registro_AAAA-MM.csv`), el log (`organizador.log`) y el lock (`organizador.lock`).
- **Entrada (extractor):** la carpeta de un día ya archivada (la que produce el bot o el archivo manual).
- **Salida (extractor):** `ENTREGA_GLOSAS_<fecha>.xlsx` en la misma carpeta del día.

### Dependencias y librerías
- **Python 3.11+** (el equipo real corre 3.14).
- **Librería estándar** (sin instalación): `imaplib`, `email` (+ `email.header`, `email.message`, `email.utils`), `zipfile`, `csv`, `json`, `hashlib`, `logging` (+ `logging.handlers`), `subprocess`, `tempfile`, `unicodedata`, `re`, `os`, `sys`, `shutil`, `base64`, `contextlib`, `mimetypes`, `pathlib`, `datetime`, `html.parser`, `xml.sax.saxutils`.
- **Terceros (todas con importación perezosa / opcional):**
  - `reportlab` — respaldo para generar el PDF del correo cuando no hay navegador.
  - `openpyxl` — leer y escribir Excel (adjuntos `.xlsx` y el Excel de entrega).
  - `pdfplumber` — extraer texto de los PDF de AXA y del acta de Seguros Bolívar (opcional; si falta, esos PDF no se parsean pero el resto sigue).
- **Navegador (opcional):** Microsoft Edge o Google Chrome, usados en modo headless (`--headless --print-to-pdf`) para imprimir el correo a PDF con fidelidad. Si no hay navegador, se usa reportlab.

### APIs
- **IMAP de Gmail** (`imap.gmail.com`, SSL, puerto implícito 993) mediante `imaplib.IMAP4_SSL`. Comandos usados: `LOGIN`, `SELECT`, `UID SEARCH SINCE`, `UID FETCH (BODY.PEEK[...])`, `UID STORE +X-GM-LABELS`. Se usa la extensión de Gmail `X-GM-LABELS` para etiquetar.
- No hay APIs HTTP propias; el módulo no expone endpoints. (Existe en la app un endpoint `POST /bandeja/poll-ahora` que fue el punto de partida conceptual, ver sección 14.)

### Modelos, servicios, utilidades
- **No usa la base de datos ni los modelos de la app.** El "estado" persiste en un archivo JSON local, no en SQL.
- **Servicios:** cada herramienta es un servicio autónomo; no dependen entre sí en tiempo de ejecución (el extractor lee lo que el bot archivó, pero se ejecuta por separado).
- **Utilidades reutilizadas del repo (patrón, no importación):** el sanitizador de nombres de archivo Windows (`RE_INVALIDOS`), la tabla de meses en español y la lista de festivos colombianos (`FERIADOS_CO`, copiada de `app/services/glosa_service.py`).

---

## 3. Funciones implementadas

> Convención: **modifica archivos** = qué escribe en disco al ejecutarse. La mayoría de funciones son puras (no tocan disco); se indica explícitamente cuáles sí.

### Herramienta 1 — `tools/organizar_correos_glosas.py`

**Utilidades de texto y configuración**
- `setup_logging(log_file)` — Configura el log (consola + archivo rotativo de 2 MB × 3). Reconfigura stdout con `errors="replace"` para no abortar por caracteres raros en consolas cmd. *Escribe:* el archivo de log. *Existe porque:* toda corrida deja rastro.
- `sanitizar(nombre)` — Reemplaza caracteres inválidos de Windows (`<>:"/\|?*` y control) por `_`, colapsa espacios y quita punto/espacio final. *Existe porque:* los nombres de correo/entidad se usan como nombres de carpeta/archivo.
- `_quitar_diacriticos(texto)` — Quita tildes/ñ vía `unicodedata`. Base de la comparación insensible a acentos.
- `_normalizar(texto)` — MAYÚSCULAS sin tildes. Es la forma canónica contra la que se prueban todos los patrones (reglas de categoría, entidad, ignorados).
- `_acotar(texto, max_len)` — Recorta un texto a un largo máximo. Evita nombres/rutas demasiado largos.
- `_decodificar_bytes(texto, charset)` — Decodifica bytes probando el charset dado y luego utf-8/latin-1. *Existe porque:* `bytes.decode()` lanza `LookupError` con charsets inexistentes (`unknown-8bit`), lo que tumbaría la corrida.
- `decodificar_encabezado(valor)` — Decodifica encabezados MIME (`=?UTF-8?Q?...?=`). Nunca lanza: un charset corrupto en un solo correo no puede detener el proceso programado. *Depende de:* `_decodificar_bytes`.
- `cargar_config(ruta)` — Carga la configuración por defecto (`CONFIG_DEFECTO`) y le superpone el JSON del usuario: `plantillas` se fusiona clave por clave, `entidades_extra` se antepone a las de fábrica, el resto reemplaza. *Existe porque:* un config parcial no puede dejar al bot sin plantilla ni borrar las 30+ entidades de fábrica.

**Clasificación**
- `debe_ignorarse(asunto, remitente, config)` — Devuelve True si el asunto o el remitente coinciden con las listas de ignorados (certificados de radicación, comunicaciones internas del hospital, alertas de Google, etc.).
- `clasificar_categoria(asunto, nombres_adjuntos, config)` — Devuelve `(categoría, motivo)`. Orden: (1) reglas directas por asunto (`categorias_por_asunto`); (2) patrones generales por categoría; (3) si el asunto contiene señales de glosa **y** de devolución a la vez → categoría de revisión (`0-REVISAR`), salvo que el contenido lo resuelva después.
- `_codigos_de_bytes(contenido, nombre)` — Extrae texto plano de un adjunto tabular (csv/txt/xlsx, incluso dentro de zip) para contar códigos. Best-effort, nunca lanza. *Depende de:* `openpyxl` (perezoso) para xlsx.
- `categoria_por_contenido(adjuntos, texto, config)` — Determina INICIAL vs DEVOLUCIONES leyendo los códigos del detalle: prefijo `DE` = devolución, resto = glosa. Devuelve la categoría dominante o None si no hay códigos legibles. *Depende de:* `_codigos_de_bytes`, `RE_CODIGO_DEV`, `RE_CODIGO_GLOSA`. *Existe porque:* el área pidió que el bot **lea el contenido** y decida, en vez de mandar a revisión.
- `detectar_entidad(remitente, asunto, nombres_adjuntos, config)` — Devuelve `(carpeta_entidad, identificada)`. Prueba las reglas de cada entidad contra remitente, asunto y **cada** nombre de adjunto. Si nada coincide, devuelve `"SIN IDENTIFICAR"` (nunca el dominio del correo). *Existe porque:* usar el dominio producía carpetas basura (HUS.GOV.CO, GMAIL.COM).
- `extraer_radicado(asunto)` — Extrae el número de radicado del asunto con `RE_RADICADO`.

**Extracción de partes del correo**
- `class _ExtractorTextoHtml(HTMLParser)` + `extraer_texto_html(html)` — Convierte HTML a texto plano legible (para el PDF de respaldo y para leer el cuerpo).
- `_texto_de_parte(part)` — Decodifica el cuerpo de una parte MIME. *Depende de:* `_decodificar_bytes`.
- `_extension_por_mime(ctype)` — Adivina la extensión de un adjunto sin nombre a partir de su tipo MIME.
- `extraer_partes(msg, config)` — Devuelve `(texto_plano, html, imágenes_inline, adjuntos)`. Serializa correos reenviados (`message/rfc822`) como `.eml` sin contaminar el cuerpo principal; da nombre a los adjuntos sin nombre; omite logos de firma pequeños y firmas S/MIME (`.p7s`, `.asc`). *Existe porque:* ningún documento debe perderse.
- `fecha_local_correo(msg)` — Fecha de llegada en hora Colombia (UTC-5), acotada a un rango sano (año ≥ 2020, ≤ hoy+2 días). *Existe porque:* un remitente con el reloj dañado no debe archivar en un año equivocado.
- `id_mensaje(msg)` — Identificador único del correo: el `Message-ID`, o un hash SHA-1 de Date|From|To|Subject si falta. Base de la deduplicación.

**Generación del PDF del correo**
- `buscar_navegador()` — Localiza Edge/Chrome (rutas conocidas o variable `ORGANIZADOR_NAVEGADOR`). Devuelve None si no hay (se usa reportlab).
- `armar_html_correo(meta, html, texto, inlines)` — Arma el HTML autocontenido del correo (encabezado tipo "impresión de Gmail" + cuerpo), incrustando las imágenes en línea como data-URI.
- `generar_pdf_navegador(html_final, destino, navegador)` — Imprime a PDF con el navegador headless. **Aislado de red** (`--proxy-server=127.0.0.1:9`) para que el HTML del remitente no cargue recursos remotos. *Escribe:* el PDF. Devuelve False si falla (fallback a reportlab).
- `generar_pdf_reportlab(meta, texto, destino)` — Respaldo: genera el PDF con reportlab. *Escribe:* el PDF. *Depende de:* `reportlab` (perezoso).
- `generar_pdf_correo(...)` — Orquesta: intenta navegador, si no, reportlab. Devuelve el motor usado.

**Rutas de destino**
- `_clave_carpeta(nombre)` — Normaliza un nombre de carpeta para comparar (`07.JULIO` == `07 JULIO`).
- `carpeta_equivalente(padre, objetivo, nombre_nuevo)` — Reutiliza una carpeta existente aunque tenga marcas manuales (`DISPENSARIO SOFIA OK`, `01 OK SOLO NUEVA`); si no hay, crea `nombre_nuevo`. *Existe porque:* el personal renombra carpetas a mano y no se deben duplicar.
- `construir_carpeta_destino(base, fecha, categoria, entidad, config)` — Arma `base\AÑO\MM MES\DD\CATEGORÍA\ENTIDAD` reutilizando cada nivel con `carpeta_equivalente`.
- `nombre_archivo_seguro(nombre, max_tallo)` — Sanitiza conservando la extensión y evitando nombres reservados de Windows (CON, PRN, LPT1…).
- `nombre_disponible(carpeta, nombre)` — Nunca sobrescribe: agrega ` (2)`, ` (3)`… Recorta si la ruta supera el MAX_PATH de Windows (`MAX_RUTA_WINDOWS = 255`). *Existe porque:* jamás se debe pisar un archivo del equipo.
- `hora_correo(fecha)` — Formatea la hora de llegada al estilo del archivo manual (`7.21`, `1.30`, 12 horas).
- `nombre_pdf_correo(categoria, entidad, asunto, fecha, consecutivo_fn, config)` — Nombre del PDF según plantilla por categoría (devoluciones = por asunto; resto = `{entidad} {hora}`). Tolera plantillas mal escritas sin frenar el archivado.

**Estado persistente — `class Estado`**
- `__init__` / `cargar(ruta, respaldar_corrupto)` — Carga el estado desde JSON; si está corrupto lo respalda y sigue. *Escribe:* respaldo `.corrupto.json`.
- `ya_procesado(mid)` / `marcar(mid)` — Deduplicación por Message-ID; al marcar procesado, limpia el contador de fallos.
- `registrar_fallo(mid)` / `fallos(mid)` — Cuenta reintentos de un correo. *Existe porque:* un correo venenoso no debe reintentarse para siempre (tope `MAX_REINTENTOS_CORREO = 3`).
- `siguiente_consecutivo(fecha, entidad)` — Contador por día y entidad (para nombres que usan `{consecutivo}`).
- `depurar(dias=180)` — Poda procesados y consecutivos viejos para que el estado no crezca sin límite.
- `guardar()` — Escribe el estado de forma atómica (`.tmp` + `os.replace`). *Escribe:* `estado_organizador.json`.

**Registro**
- `registrar_fila(control, fila)` — Agrega una fila al `registro_AAAA-MM.csv` (UTF-8 con BOM para Excel). Si el CSV está abierto en Excel, cae a un `_pendiente.csv` en vez de perder la fila o abortar. *Escribe:* el CSV de registro.

**IMAP**
- `_codificar_carpeta_imap(carpeta)` — Codifica el nombre de carpeta IMAP en UTF-7 modificado (RFC 3501) si trae no-ASCII, y escapa `&`.
- `etiqueta_segura(etiqueta)` — Normaliza la etiqueta Gmail a ASCII sin comillas.
- `cargar_credenciales()` — Lee `GLOSAS_IMAP_HOST/USER/PASSWORD` (con respaldo `IMAP_USER/PASSWORD`). Si faltan, imprime instrucciones `setx` y sale con código 2.
- `conectar_imap(host, user, password, carpeta)` — Conecta con **timeout de 60 s** (para que un socket colgado no congele la tarea), hace login y selecciona la carpeta. Mensajes de error claros para login rechazado.
- `buscar_uids(conexion, desde)` — `UID SEARCH SINCE <fecha>` para traer solo los correos recientes.
- `_mensaje_de_fetch(data)` — Extrae el mensaje del resultado de un FETCH.
- `obtener_encabezados(conexion, uid)` — Descarga **solo los encabezados** (Message-ID, Date, From, To, Subject) para deduplicar sin bajar cuerpos completos. *Existe porque:* re-descargar todos los cuerpos cada 15 min agotaría el límite de ancho de banda IMAP de Gmail.
- `obtener_mensaje(conexion, uid)` — Descarga el mensaje completo con `BODY.PEEK[]` (no marca como leído).
- `etiquetar_procesado(conexion, uid, etiqueta)` — Aplica la etiqueta Gmail `Archivado-Glosas`.

**Procesamiento y orquestación**
- `procesar_mensaje(msg, *, base, config, estado, dry_run, sin_pdf_correo, navegador)` — Pipeline de un correo: ignora si aplica → extrae partes → clasifica (con decisión por contenido en caso ambiguo) → detecta entidad → construye carpeta → genera PDF y guarda adjuntos (renombrados) → devuelve la fila de registro. *Escribe:* el PDF del correo y los adjuntos en la carpeta destino.
- `base_por_defecto()` — Devuelve `GLOSAS_BASE` (carpeta de pruebas) o el servidor por defecto.
- `_parsear_fecha(valor)` — Parsea `--desde` (AAAA-MM-DD o DD/MM/AAAA).
- `_adquirir_lock(ruta)` / `_liberar_lock(ruta)` — Lock entre procesos (crea el archivo con `O_EXCL`) para que la tarea de 15 min y una corrida manual no se solapen. Un lock más viejo que `LOCK_VIEJO_MINUTOS = 90` se considera huérfano. *Escribe:* `organizador.lock`.
- `_fila_error(...)` — Construye una fila de registro para un correo que falló.
- `_procesar_uid(conexion, uid, estado, config, args, navegador, control, resumen)` — Orquesta un UID: salta los ya procesados/descartados → dedup por encabezados → descarta el venenoso tras 3 intentos → descarga completa y procesa → marca, guarda estado, registra y etiqueta. *Escribe:* estado, registro y (en Gmail) la etiqueta.
- `main()` — Punto de entrada: parsea argumentos, valida la base, adquiere el lock, conecta IMAP, recorre los UID (respetando `--max`), imprime el resumen final y devuelve el código de salida (0 = sin errores). *Escribe:* todo lo anterior a través de las funciones que llama.

### Herramienta 2 — `tools/extraer_detalle_glosas.py`

**Conversores**
- `setup_logging(log_file)` — Igual patrón que el bot.
- `_normalizar(texto)` — MAYÚSCULAS sin tildes, para comparar encabezados de columnas.
- `a_fecha(valor)` — Convierte lo que venga (datetime de openpyxl, `18/06/26`, `2026/06/25`, `01/07/2026 00:00`, ISO con `T`) a `date`. Descarta `1900/01/01` (marca de "sin fecha" de SURA).
- `a_numero(valor)` — Convierte montos colombianos (`$9.576.693,00` → 9576693.0; `2,800` → 2800.0) detectando el separador decimal correcto.
- `sumar_habiles(desde, habiles)` — Suma días hábiles saltando fines de semana y festivos colombianos (`FERIADOS_CO`, 2025–2028). Base del cálculo de vencimientos.
- `cargar_gestores(ruta)` — Carga el mapeo entidad → gestor por defecto (`GESTORES_DEFECTO`) y le superpone el JSON del usuario.
- `info_entidad(carpeta_entidad, gestores)` — De una carpeta como `DISPENSARIO SOFIA OK` devuelve la EMPRESA formal y las reglas de gestor.
- `responsable_para(reglas, categoria, gestores)` — Gestor asignado según la categoría, o `POR ASIGNAR`.

**Parsers de detalle** (cada uno devuelve `list[dict]` con una fila por servicio/ítem)
- `_categoria_por_codigo(codigo)` — `DE*` = devolución; resto = None (usa la categoría de la carpeta).
- `parser_auditool_csv(contenido, nombre)` — CSV de AUDITOOL/Dispensario (`;`, latin-1, con preámbulo variable). Detecta la fila de encabezados y las columnas por nombre.
- `_celda(fila, idx, clave)` — Acceso seguro a una celda por nombre de columna (evita leer la última columna cuando falta el encabezado, y evita IndexError con filas cortas).
- `parser_famisanar_txt(contenido, nombre)` — TXT `DEVYGLOSAS*` de Famisanar (`|`); separa glosa de devolución por el código.
- `parser_sura_txt(contenido, nombre)` — TXT `*MASIVO*` de SURA (`;`).
- `_filas_xlsx(contenido)` — Itera las filas de la primera hoja de un Excel en modo lectura.
- `parser_sanitas_xlsx` — Excel de Sanitas (hoja "Glosa").
- `parser_objeciones_xlsx` — Excel de Policía/Génesis (hoja "OBJECIONES", columnas `CRNCXC` / `CROVALOBJ`).
- `parser_factramed_xlsx(contenido, nombre, desde, hasta)` — Excel de FACTRAMED/Nueva EPS (`Registro_Inforamcion...`), **filtrado por ventana de fechas** porque trae el acumulado histórico.
- `parser_savia_xlsx` — Excel de Savia Salud.
- `parser_coosalud_xlsx` — Excel `GLOSAS HUS*.xlsx` de Coosalud (dentro de zips anidados).
- `parser_policia_rad_xlsx` — Certificación `GLOSA A RAD NNNN.xlsx` de Policía, con el encabezado enterrado en una fila intermedia (~14).
- `_fila_minima_por_nombre(nombre)` — Último recurso: la factura viene en el nombre del archivo (formularios de MUTUAL de una sola columna). Marca "completar a mano".
- `_texto_pdf(contenido)` — Extrae texto de un PDF con pdfplumber (opcional).
- `parser_pdf(contenido, nombre)` — Enruta a AXA/Bolívar o genera fila mínima; ignora los PDF que son correos impresos.
- `_parser_axa(texto)` — Liquidación tabular de AXA (el último número de la línea es el "Glosado").
- `_parser_bolivar(texto)` — Acta de Seguros Bolívar (RGC Activa).
- `elegir_parser(nombre)` — Elige el parser por extensión/nombre; ignora `*_LIGERO`, manuales y temporales `~$`.
- `_parser_xlsx_auto(contenido, nombre, **kwargs)` — **Despacho por firma de columnas**: lee el encabezado UNA vez y enruta al parser correcto (un lunes trae 20+ zips de Coosalud; probar todos los parsers reabriendo cada Excel multiplicaba el tiempo por 7).

**Recorrido y salida**
- `_categoria_de_carpeta(nombre)` — De `DEVOLUCIONES OK` / `RATIFICADAS` deduce la categoría.
- `extraer_de_archivo(ruta, contenido, ventana, profundidad)` — Abre `.zip` recursivamente (tope `MAX_PROFUNDIDAD_ZIP`), tolera archivos corruptos (los reporta y sigue).
- `fecha_de_carpeta(carpeta)` — De `...\2026\07 JULIO\02` deduce la fecha `2026-07-02`.
- `recorrer_dia(carpeta_dia, gestores, ventana_factramed)` — Recorre categoría → entidad → archivos, aplica el parser, asigna categoría/empresa/gestor y devuelve las filas agrupadas + la lista de archivos sin parser.
- `agrupar_por_factura(crudas)` — Una fila por (categoría, empresa, factura): suma valores, toma las primeras fechas, une códigos de glosa.
- `_fila_para_hoja(fila, categoria, fecha_entrega, gestores)` — Arma la fila con el layout exacto de columnas de cada hoja; marca "OJO: VENCIDA" si el plazo ya pasó.
- `escribir_entrega(filas, sin_parser, salida, fecha_entrega, gestores)` — Escribe el Excel de entrega (hojas INICIAL/RATIFICADA/DEVOLUCIONES + RESUMEN). *Escribe:* el `.xlsx`. *Depende de:* `openpyxl`.
- `main()` — Punto de entrada: recorre el día, imprime el resumen por categoría, y escribe el Excel (salvo `--dry-run`).

---

## 4. Flujo completo

### Flujo del bot organizador (cada 15 minutos, automático)
1. **Disparo:** el Programador de tareas de Windows ejecuta `organizador_tarea.bat`, que llama a `organizar_correos_glosas.py`. (También puede lanzarse a mano con `organizar_correos_glosas.bat`.)
2. **Validación de entorno** (`main`): valida que exista la carpeta base; si no, sale con mensaje claro (no crea árboles fantasma).
3. **Lock:** adquiere `organizador.lock`. Si ya hay una corrida en curso, sale sin hacer nada (evita solapamiento).
4. **Estado:** carga `estado_organizador.json` (deduplicación, reintentos, consecutivos).
5. **Credenciales y conexión:** lee `GLOSAS_IMAP_USER/PASSWORD`, conecta a `imap.gmail.com` con timeout, selecciona `INBOX`.
6. **Búsqueda:** `UID SEARCH SINCE <hoy − 3 días>` (configurable con `--dias`/`--desde`).
7. **Por cada correo (`_procesar_uid`), hasta `--max` (200):**
   a. Si el UID ya fue descartado antes, se salta.
   b. Descarga **solo encabezados** y calcula el Message-ID; si ya se procesó, se salta.
   c. Si ese correo ya falló 3 veces, se descarta con rastro en el CSV.
   d. Descarga el **mensaje completo** (`BODY.PEEK[]`, sin marcar leído).
   e. **`procesar_mensaje`:** si el asunto/remitente está en ignorados → IGNORADO. Si no: extrae partes; clasifica por asunto/adjuntos; si es ambiguo ("glosas y/o devoluciones"), **lee los códigos del contenido** y decide; detecta la entidad (o SIN IDENTIFICAR); construye la carpeta `AÑO\MM MES\DD\CATEGORÍA\ENTIDAD` reutilizando carpetas marcadas a mano; genera el **PDF del correo** (navegador o reportlab) con nombre `ENTIDAD hora` (o el asunto en devoluciones) **sin la marca "OK"**; guarda los adjuntos renombrados igual, sin sobrescribir.
   f. **Persistencia:** marca el Message-ID como procesado, depura y guarda el estado, agrega la fila al `registro_AAAA-MM.csv`, y aplica la etiqueta Gmail `Archivado-Glosas`.
8. **Cierre:** logout de IMAP, libera el lock, imprime el RESUMEN FINAL, devuelve 0 (o 1 si hubo errores).

### Flujo del extractor (bajo demanda, una vez por día)
1. **Disparo:** el usuario ejecuta `extraer_detalle_glosas.py --carpeta "...\07 JULIO\02"`.
2. **`recorrer_dia`:** deduce la fecha del día; recorre cada carpeta de categoría → cada carpeta de entidad → cada archivo. Abre zips recursivamente. Para cada adjunto elige el parser por nombre/firma de columnas y extrae una fila por servicio/ítem. Asigna categoría (la del contenido manda sobre la de la carpeta), empresa formal y gestor por entidad.
3. **`agrupar_por_factura`:** consolida a una fila por factura (suma valores, primeras fechas).
4. **`escribir_entrega`:** para cada categoría calcula el vencimiento (15/7 días hábiles con festivos), marca las vencidas, y escribe el Excel de entrega con hojas INICIAL/RATIFICADA/DEVOLUCIONES + RESUMEN (totales por entidad y lista de archivos sin parser).
5. **Salida:** `ENTREGA_GLOSAS_<fecha>.xlsx` en la carpeta del día.

---

## 5. Base de datos
**El módulo NO usa base de datos.** No define tablas, columnas, relaciones, índices ni migraciones. Toda la persistencia es en archivos planos, por decisión de diseño (herramienta autónoma que corre en el equipo del área, no en el servidor):
- **`estado_organizador.json`** — objeto JSON con tres claves: `procesados` (Message-ID → fecha de proceso), `fallidos` (Message-ID → número de intentos) y `consecutivos` (`AAAA-MM-DD|ENTIDAD` → contador).
- **`registro_AAAA-MM.csv`** — un archivo por mes. Columnas: `fecha_proceso, fecha_correo, remitente, asunto, categoria, entidad, estado, carpeta, pdf_correo, archivos, motivo, detalle, mensaje_id`.
- **`organizador.lock`** — archivo vacío con el PID, para el lock entre procesos.
- **`ENTREGA_GLOSAS_<fecha>.xlsx`** — salida del extractor (no es base de datos, es entregable).

Datos necesarios previos: la lista de **festivos colombianos** (`FERIADOS_CO`, embebida) y los **mapeos de entidades y gestores** (embebidos, sobreescribibles por JSON).

---

## 6. Backend
El módulo **no tiene backend propio** (no expone endpoints, servicios web, controladores, middleware ni sistema de permisos). Es un par de programas de línea de comandos.

Equivalencias funcionales relevantes:
- **"Endpoints":** los dos puntos de entrada `main()` de cada script, invocables por CLI.
- **Validaciones:** existencia de la carpeta base; credenciales presentes; carpeta IMAP abrible; formato de fechas de `--desde`; config JSON válido.
- **Errores:** salida con código 2 y mensaje a stderr para errores fatales (faltan credenciales, no hay reportlab ni navegador, base inexistente, login IMAP rechazado, config inválido). Errores por correo se aíslan (no frenan el lote) y se registran como `ERROR`/`ERROR_DESCARTADO`.
- **Permisos:** los del sistema operativo — el bot corre con el usuario del equipo de cartera, que tiene acceso a la unidad `Z:` y a la cuenta de correo (vía contraseña de aplicación).
- **Contexto en la app:** existe `app/api/routers/bandeja.py` con `POST /bandeja/poll-ahora` (esqueleto que inspiró el proyecto), pero el módulo no lo usa (ver sección 14).

---

## 7. Frontend
El módulo **no tiene interfaz gráfica ni pantallas**. La única "interfaz de usuario" son:
- **Los archivos `.bat`** (interacción por consola): `INSTALAR_BOT_GLOSAS.bat` hace preguntas por teclado (correo, contraseña, ¿programar?, ¿reemplazar contraseña?), muestra el resultado de una prueba en simulacro, y valida que no se ejecute desde dentro del ZIP. `CAMBIAR_CARPETA_DESTINO.bat` pide la carpeta destino.
- **El resultado visible** para el usuario son **las carpetas en el servidor** (PDF del correo + adjuntos) y **el registro CSV** que abre en Excel.
- **Informes visuales** (fuera del código, entregados como Artifacts HTML): un informe "antes vs ahora" para gerencia y una bitácora del proyecto. No forman parte del módulo ejecutable.

No hay componentes, formularios web, botones, tablas HTML, modales, animaciones ni validaciones de frontend.

---

## 8. IA
Este módulo **no utiliza inteligencia artificial**: no hay prompts, proveedores, modelos, temperatura, fallback de modelos ni manejo de respuestas de IA. La clasificación es **determinística**, basada en expresiones regulares y conteo de códigos.

Aclaración importante para evitar confusión: la **aplicación principal** (`app/`) del repositorio sí usa IA (Groq/Anthropic/Gemini para dictámenes de glosas), pero **eso es otro módulo**, ajeno a este desarrollo. La "decisión por contenido" del bot (glosa vs devolución) **no es IA**: es un conteo de prefijos de código (`DE` = devolución) con expresiones regulares (`RE_CODIGO_DEV`, `RE_CODIGO_GLOSA`).

---

## 9. Automatizaciones

- **Recepción y archivo de correos (el bot):**
  - *Qué hace:* lee la bandeja, clasifica, archiva y registra (ver secciones 3 y 4).
  - *Cuándo se ejecuta:* cada **15 minutos**, de forma desatendida, todo el día.
  - *Cómo se ejecuta:* una tarea del **Programador de tareas de Windows** llamada `HUS Organizador Correos Glosas`, creada por `instalar_organizador_correos.bat` (`schtasks /create ... /sc minute /mo 15`), que ejecuta `organizador_tarea.bat`. Ese runner rota su propio log si supera 5 MB.
- **Etiquetado en Gmail:** cada correo procesado recibe la etiqueta `Archivado-Glosas` (no se marca leído, no se mueve, no se borra).
- **Depuración del estado:** en cada corrida se podan del estado los registros de más de 180 días.
- **Generación del Excel de entrega (el extractor):** *no* está programado; se ejecuta **bajo demanda** una vez por día sobre la carpeta del día.
- **Instalación:** `INSTALAR_BOT_GLOSAS.bat` automatiza la puesta a punto (verifica Python, instala dependencias con pip, guarda credenciales con `setx`, corre simulacro y ofrece programar la tarea).

---

## 10. Archivos creados/modificados (por este desarrollo)

> Todos son **archivos nuevos** creados por este módulo (no se modificó código de la app existente). El desarrollo se hizo en 23 commits sobre la rama.

| Archivo | Qué es / qué contiene |
|---|---|
| `tools/organizar_correos_glosas.py` | **Nuevo.** Bot organizador completo (1.617 líneas). |
| `tools/extraer_detalle_glosas.py` | **Nuevo.** Extractor / Excel de entrega (1.241 líneas). |
| `tools/organizar_correos_glosas_config.ejemplo.json` | **Nuevo.** Config de entidades/categorías/ignorados (generado desde `CONFIG_DEFECTO`; hay un test que garantiza que coinciden). |
| `tools/gestores_glosas.ejemplo.json` | **Nuevo.** Mapeo entidad→gestor (generado desde `GESTORES_DEFECTO`). |
| `tools/INSTALAR_BOT_GLOSAS.bat` | **Nuevo.** Instalador de un clic (verifica ZIP extraído, Python, deps, credenciales, simulacro, tarea). |
| `tools/instalar_organizador_correos.bat` | **Nuevo.** Crea la tarea programada cada 15 min apuntando a `organizador_tarea.bat`. |
| `tools/organizador_tarea.bat` | **Nuevo.** Runner de la tarea, con rotación de log. |
| `tools/organizar_correos_glosas.bat` | **Nuevo.** Corrida manual con pausa. |
| `tools/CAMBIAR_CARPETA_DESTINO.bat` | **Nuevo.** Cambia `GLOSAS_BASE` entre carpeta de pruebas y servidor (con `setx` / `reg delete`). |
| `tools/README_organizar_correos_glosas.md` | **Nuevo.** Manual del bot. |
| `tools/README_extraer_detalle_glosas.md` | **Nuevo.** Manual del extractor. |
| `tests/test_tools/__init__.py` | **Nuevo.** Paquete de pruebas de herramientas. |
| `tests/test_tools/test_organizar_correos_glosas.py` | **Nuevo.** Pruebas del bot. |
| `tests/test_tools/test_extraer_detalle_glosas.py` | **Nuevo.** Pruebas del extractor. |
| `BITACORA.md` | **Nuevo.** Memoria común del proyecto (registro por fecha, PENDIENTE, PARA MAÑANA). |
| `CLAUDE.md` | **Nuevo.** Instruye leer/actualizar `BITACORA.md` en cada sesión. |
| `docs/MODULO_ORGANIZADOR_GLOSAS.md` | **Nuevo.** Este documento. |
| `tests/test_api/test_fecha_objecion_mensual.py` | **Modificado (arreglo de prueba caduca por fechas fijas).** No es del módulo; se corrigió para desbloquear el CI. |
| `tests/test_api/test_por_dia_semana.py` | **Modificado (arreglo de prueba caduca por fechas fijas de abril fuera de la ventana de 90 días).** |
| `tests/test_api/test_heatmap_actividad.py` | **Modificado (mismo arreglo de fechas caducas).** |
| `tests/test_api/test_import_history.py` | **Modificado (resuelto en merge; arreglo de fechas del lado de la rama base).** |
| `tools/evidencias_a_word.py` | **Modificado (resuelto en merge con la rama base).** No es del módulo. |

---

## 11. Dependencias nuevas
No se agregó ninguna dependencia al `requirements.txt` de la app. Todas las librerías de terceros que usa el módulo **ya estaban** en el proyecto y se importan de forma perezosa:

| Paquete | Versión (en `requirements.txt`) | Para qué lo usa el módulo |
|---|---|---|
| `openpyxl` | 3.1.5 | Leer adjuntos `.xlsx` y escribir el Excel de entrega. |
| `reportlab` | 4.2.5 | Generar el PDF del correo cuando no hay navegador. |
| `pdfplumber` | 0.11.5 | Extraer texto de los PDF de AXA y del acta de Bolívar (opcional). |

En el equipo real, `INSTALAR_BOT_GLOSAS.bat` ejecuta `py -m pip install reportlab openpyxl pdfplumber`. No requiere el resto de dependencias de la app (FastAPI, SQLAlchemy, etc.), porque el módulo no toca la app.

---

## 12. Configuración

### Variables de entorno (se guardan en el equipo con `setx`)
| Variable | Obligatoria | Para qué |
|---|---|---|
| `GLOSAS_IMAP_USER` | Sí | Cuenta de correo (`glosasydevoluciones@hus.gov.co`). Respaldo: `IMAP_USER`. |
| `GLOSAS_IMAP_PASSWORD` | Sí | **Contraseña de aplicación** de Gmail (16 letras), NO la clave normal. Respaldo: `IMAP_PASSWORD`. |
| `GLOSAS_IMAP_HOST` | No | Host IMAP (por defecto `imap.gmail.com`). |
| `GLOSAS_BASE` | No | Carpeta destino. Si está definida (ej. `D:\USUARIO CARTERA\Documents\PRUEBAS MAIL`) archiva ahí; vacía = servidor de producción. Es el "modo pruebas". |
| `ORGANIZADOR_NAVEGADOR` | No | Ruta a un `.exe` de Edge/Chrome si no está en las rutas conocidas. |

### Archivos de configuración
- `organizar_correos_glosas_config.ejemplo.json` — entidades, categorías, ignorados, plantillas de nombres. Se pasa con `--config`. Las claves del usuario se superponen a las de fábrica (fusión inteligente de `plantillas` y `entidades_extra`).
- `gestores_glosas.ejemplo.json` — mapeo entidad → empresa formal → gestor por categoría. Se pasa con `--config` al extractor.

### Parámetros (argumentos CLI)
**Bot organizador:** `--base`, `--control`, `--config`, `--carpeta-imap` (INBOX), `--dias` (3), `--desde`, `--max` (200), `--dry-run`, `--no-marcar`, `--sin-pdf-correo`, `--log`.
**Extractor:** `--carpeta` (obligatorio), `--salida`, `--config`, `--ventana-factramed` (7), `--dry-run`, `--log`.

### Constantes clave
`DEFAULT_BASE` (ruta del servidor), `DEFAULT_CONTROL = "00-CONTROL AUTOMATICO"`, `DEFAULT_DIAS = 3`, `DEFAULT_MAX = 200`, `TZ_COLOMBIA = UTC-5`, `MAX_REINTENTOS_CORREO = 3`, `MAX_RUTA_WINDOWS = 255`, `LOCK_VIEJO_MINUTOS = 90`, `ENTIDAD_SIN_IDENTIFICAR = "SIN IDENTIFICAR"`, etiqueta Gmail `Archivado-Glosas`.

### Tokens / rutas
- **No hay tokens de API.** La única credencial es la contraseña de aplicación de Gmail, guardada solo en el equipo (nunca en el código).
- **Ruta destino real:** `Z:\SERVIDOR GLOSAS\F\RECEPCIÓN DE GLOSAS (NO ELIMINAR CARPETA)\03-GLOSAS ESCANEADAS 2.0 (NO ELIMINAR CARPETA )`.

> **Advertencia de seguridad (documentada):** durante las pruebas, la contraseña de aplicación quedó visible en el canal de trabajo en varias ocasiones. **Debe rotarse** (crear una nueva, actualizarla en el equipo, eliminar la anterior).

---

## 13. Riesgos al integrar

| Riesgo | Detalle | Mitigación |
|---|---|---|
| **Unidad `Z:` no mapeada** | Las tareas programadas a veces no ven unidades mapeadas. | El bot valida la base y sale con mensaje claro; se puede usar la ruta UNC (`\\servidor\...`) en vez de `Z:`. |
| **Contraseña de aplicación deshabilitada** | Si el admin de Google Workspace las bloquea, el login falla. | Alternativa prevista: migrar a Gmail API con OAuth (no implementado). |
| **Pruebas caducas en el CI** | Algunas pruebas de la **app** (no del módulo) usan fechas fijas y fallan al pasar los días. Se corrigieron 3 (`test_fecha_objecion_mensual`, `test_por_dia_semana`, `test_heatmap_actividad`). | Anclarlas a fechas relativas. Pueden aparecer más con el tiempo. |
| **Conflictos de merge en pruebas** | La rama base (`motor-glosas`) también corrige pruebas de fechas; hubo conflictos ya resueltos. | Al fusionar, revisar `tests/test_api/` por conflictos en pruebas de fechas. |
| **Excel de FACTRAMED acumulado** | Trae histórico; sin ventana de fechas duplicaría facturas. | `--ventana-factramed` (7 días por defecto) — calibrar según frecuencia real del correo. |
| **Dependencia de `openpyxl`/`reportlab`/`pdfplumber`** | Si el equipo no las tiene, ciertas funciones fallan. | El instalador las instala; las importaciones son perezosas y con mensaje de error claro. |
| **Doble corrida solapada** | La tarea de 15 min + una corrida manual. | Lock entre procesos (`organizador.lock`). |
| **Duplicados al cambiar de destino** | Cada destino lleva su propia memoria; el modo pruebas re-archiva la ventana completa. | Es el comportamiento esperado; documentado. |

---

## 14. Dependencias con otros módulos

- **No depende en tiempo de ejecución de ningún otro módulo del repo.** Es autónomo.
- **Reutiliza por copia (no por importación):** la lista de festivos `FERIADOS_CO` y el patrón de meses en español provienen de `app/services/glosa_service.py`; el sanitizador Windows sigue el patrón de otros `tools/` (`renombrar_y_organizar_notas.py`, `organizar_por_gestor.py`).
- **Punto de partida conceptual:** `app/api/routers/bandeja.py` (endpoint `POST /bandeja/poll-ahora`, esqueleto de ingesta IMAP) y la clase de config `app/core/config.py` (variables SMTP/IMAP). El módulo NO importa ese router; usa sus propias variables `GLOSAS_IMAP_*`.
- **Módulo hermano (mismo repositorio, otra conversación):** `tools/responder_glosas_dgh.py` automatiza *responder* las glosas dentro del sistema Dinámica Gerencial Hospitalaria. Es independiente de este módulo, pero forma parte del mismo flujo de negocio (este recibe y organiza; aquel responde). No comparten código.
- **Lo usa (indirectamente):** el extractor consume lo que el bot archiva (la carpeta del día), pero se ejecutan por separado; no hay acoplamiento en código.

---

## 15. Pendientes

### Sin terminar / próximos pasos
- **Rotar la contraseña** de aplicación (expuesta en el canal de trabajo).
- **Afinar las últimas entidades** que caen en `SIN IDENTIFICAR` (revisar el registro y agregar reglas).
- **Validar un día completo:** comparar lo que archiva el bot en un día contra el archivo hecho a mano.
- **Paso a producción:** apuntar el bot al servidor `Z:` definitivo (hoy en carpeta de pruebas vía `GLOSAS_BASE`).
- **Integrar al proyecto principal:** el trabajo está en la rama `claude/archived-chats-view-au8nqp`; hay un PR abierto (#157, en borrador).

### Mejoras previstas (no implementadas)
- **Gmail API con OAuth** como alternativa si bloquean las contraseñas de aplicación.
- **Calibrar `--ventana-factramed`** según con qué frecuencia llega el correo de FACTRAMED.
- Posible **programación del extractor** (hoy es manual).

### Errores conocidos / limitaciones
- Los `DEV*.pdf` de AUDITOOL son **escaneados** (imagen): salen con el radicado y "completar a mano", sin valor.
- Las liquidaciones de SEGUROS MUNDIAL son notificaciones de pago: salen con observación, sin valor de glosa.
- Los formularios de MUTUAL vienen mal exportados (una sola columna): la factura se toma del nombre del archivo.
- El Excel de FACTRAMED trae acumulado histórico: la ventana de fechas evita duplicar, pero procesar el mismo día con ventanas distintas puede repetir facturas entre entregas (el consolidado maestro es la fuente de verdad para deduplicar).

---

## 16. Recomendaciones para fusionarlo al proyecto principal

1. **Traer la rama:** el módulo vive íntegro en `claude/archived-chats-view-au8nqp`. Todo el código nuevo está bajo `tools/` y `tests/test_tools/`, más `BITACORA.md`, `CLAUDE.md` y este `docs/`.
2. **Merge limpio de código de producción:** el módulo **no toca `app/`**, así que no hay riesgo de romper la aplicación web. El único punto de fricción son las **pruebas de fechas** en `tests/test_api/` (`test_fecha_objecion_mensual`, `test_por_dia_semana`, `test_heatmap_actividad`, `test_import_history`): tanto esta rama como la base las corrigen; al fusionar, resolver quedándose con la versión de fechas relativas (cualquiera de las dos sirve, no combinarlas a medias).
3. **Verificar los gates:** `ruff check` + `ruff format --check` sobre `tools/` y `tests/test_tools/`; `pytest tests/test_tools/` (151 pruebas). El CI del repo corre lint (`ruff check . --select F,W6`), format y `pytest`.
4. **Regenerar los JSON de ejemplo si se cambian los defaults:** hay pruebas que exigen que `organizar_correos_glosas_config.ejemplo.json == CONFIG_DEFECTO` y `gestores_glosas.ejemplo.json == GESTORES_DEFECTO`. Si se editan las entidades/categorías en el código, regenerar los JSON (los tests lo detectan).
5. **No mover los `tools/` a `app/`:** el módulo está pensado para correr en el equipo Windows del área, fuera del servidor. Mantenerlo en `tools/` (convención del repo para scripts autónomos).
6. **Conservar `CLAUDE.md` y `BITACORA.md`:** son la memoria común del proyecto. Si el proyecto principal ya tiene un `CLAUDE.md`, **fusionar** la sección de la bitácora en vez de sobrescribir.
7. **Despliegue en el equipo real:** entregar el paquete (los archivos de `tools/`), extraerlo en una carpeta fija, correr `INSTALAR_BOT_GLOSAS.bat`, validar en `GLOSAS_BASE` (pruebas) y, cuando esté conforme, vaciar `GLOSAS_BASE` para apuntar a `Z:`.
8. **No romper la convención de nombres:** el bot crea carpetas y archivos **sin la marca "OK"** (esa la ponen los gestores al responder). Cualquier cambio debe respetarlo.

---

## 17. Resumen ejecutivo (qué debe saber quien lo mantenga)

- **Son dos scripts Python autónomos** en `tools/`, que corren en el equipo Windows del área de cartera, **no en el servidor**. No usan base de datos, no exponen API, no usan IA.
- **El bot (`organizar_correos_glosas.py`)** lee la bandeja Gmail por IMAP cada 15 minutos, clasifica cada correo (inicial/ratificada/devolución/conciliación, o revisión), detecta la entidad, imprime el correo a PDF, guarda los adjuntos y archiva todo en `AÑO\MM MES\DD\CATEGORÍA\ENTIDAD` del servidor. Deduplica por Message-ID en un JSON local, no marca leídos, no borra, no mueve, no sobrescribe, y deja un CSV auditable. La configuración (30+ entidades, categorías, ignorados) es JSON editable.
- **El extractor (`extraer_detalle_glosas.py`)** recorre la carpeta de un día, lee nueve formatos de adjunto distintos (incluso dentro de zips) y arma el Excel de entrega para los gestores, con responsable por entidad y vencimiento en días hábiles.
- **La decisión clave de diseño** fue: reglas **deterministas** (regex + conteo de códigos `DE`), no IA; **robustez ante fallos** (nada tumba el lote, tope de reintentos, lock, tolerancia a correos y archivos dañados); y **respeto absoluto por el trabajo manual del equipo** (reutilizar carpetas marcadas, no poner "OK", no tocar la bandeja).
- **Para mantenerlo:** casi todos los ajustes se hacen en los JSON de config (agregar una entidad, un ignorado, una plantilla) **sin tocar código**. Si se toca el código de las reglas por defecto, regenerar los JSON de ejemplo (hay pruebas que lo exigen). Las 151 pruebas en `tests/test_tools/` son la red de seguridad.
- **Lo pendiente crítico:** rotar la contraseña expuesta, afinar `SIN IDENTIFICAR`, validar un día completo y pasar de la carpeta de pruebas (`GLOSAS_BASE`) al servidor `Z:`.
- **Historia y decisiones:** todo el recorrido (23 commits, dos revisiones adversariales con 46 hallazgos corregidos, la afinación con 904 correos reales, el cambio a decisión por contenido) está documentado en `BITACORA.md`.

---

*Documento generado como entrega oficial del módulo. Fuente: la conversación de desarrollo y el código real del repositorio. Última actualización: 22 de julio de 2026.*
