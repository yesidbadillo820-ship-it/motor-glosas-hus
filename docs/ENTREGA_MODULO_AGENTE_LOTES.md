# ENTREGA TÉCNICA — Módulo "Lotes de Portal + Agente de Lotes"

**Documento oficial de entrega del módulo al equipo principal.**
Reconstruye TODO lo realizado en la conversación/rama `claude/repo-branch-analysis-xvsk1i`
(sesión del 17 al 22 de julio de 2026), sin omisiones.

- **Repositorio:** `yesidbadillo820-ship-it/motor-glosas-hus`
- **Rama principal:** `motor-glosas`
- **PRs de esta sesión:** #169, #170, #171, #172 (fusionados) y #178 (bitácora + fix de tests)
- **Commits clave:** `27f3e13`, `0795957`, `bec3cbc`, `49d7c2d`, `98426f9`, `b242ed3`, `0df7894`

---

## 1. Objetivo del desarrollo

**Problema:** el proyecto tenía dos mundos desconectados. Por un lado la app web
(FastAPI, `app/`) con el motor de dictámenes de glosas; por el otro, ~35 scripts
CLI en `tools/` (bots Playwright para portales COOSALUD/SIMED/DGH, pipeline de
notas crédito, evidencias, tableros) que se ejecutaban a mano en el PC del
hospital, con la terminal parada en la carpeta correcta y variables `setx`.
El trabajo real de cada lote era ejecutar 4–6 scripts en orden, manualmente.

**Necesidad expresada por el usuario:** *"un sistema tipo app que me una todo
este trabajo y me lo haga automáticamente"*. Y tras el primer piloto fallido
del CLI: *"dámelo que sea como aplicación de escritorio que se pueda usar como
los bots que hemos venido trabajando"*.

**Solución construida (Fase 1):** el auditor sube el Excel consolidado del
pagador a la app; la app lo parsea con el MISMO parser del bot, crea un
"semáforo" por factura y encola una tarea; un **agente local** (aplicación de
escritorio con ventana, doble clic) corre en el PC del hospital, reclama la
tarea por HTTP, ejecuta el bot Playwright y reporta el avance factura por
factura en vivo.

**Restricción que definió la arquitectura:** los bots NO pueden vivir en la
nube — necesitan el share de red del hospital (`\\172.16.32.83`), servicios
internos (`dockerrips.hus.gov.co`), credenciales de portales y manejan PHI
(datos de pacientes). Por eso: app central + agente local conectados por
HTTP saliente (el PC no abre puertos; hace polling).

---

## 2. Arquitectura

```
[App web FastAPI]  ←── HTTP polling ──  [Agente en el PC del hospital]
  /lotes (usuarios)                       tools/AgenteLotes.pyw  (ventana)
  /agente/lotes (agente, token)           tools/agente_lotes_gui.py
  cola de tareas EN LA BD                 tools/agente_lotes.py   (núcleo+CLI)
  semáforo por factura                    └── subprocess → tools/responder_glosas_coosalud.py
```

### Componentes y archivos del módulo

| Capa | Archivo | Rol |
|---|---|---|
| Modelos | `app/models/db.py` (ampliado) | `LoteRecord`, `FacturaLoteRecord`, `TareaLoteRecord` + constantes de estado |
| Servicio | `app/services/lotes_service.py` (nuevo) | parseo del Excel, creación del lote, claim atómico, aplicación de resultados, estado final |
| API | `app/api/routers/lotes.py` (nuevo) | router `/lotes` (usuarios) y `agente_router` `/agente/lotes` (agente) |
| Config | `app/core/config.py` (ampliado) | `agente_lotes_token: str = ""` en `Settings` |
| Registro | `app/main.py` (ampliado) | `include_router` de ambos routers al final del archivo |
| Agente núcleo | `tools/agente_lotes.py` (nuevo) | `ApiLotes` (cliente HTTP stdlib), `construir_comando`, config persistida, `leer_reporte`, CLI |
| Agente GUI | `tools/agente_lotes_gui.py` (nuevo) | ventana Tkinter (`VentanaAgente`) + hilo `AgenteWorker` |
| Launcher | `tools/AgenteLotes.pyw` (nuevo) | doble clic → abre la ventana sin consola (pythonw) |
| Docs | `tools/README_agente_lotes.md` (nuevo) | uso de escritorio, requisitos, flujo, problemas comunes |
| Deploy | `docker-compose.yml` (ampliado) | passthrough de `AGENTE_LOTES_TOKEN` al contenedor |
| Deploy | `.env.example` (corregido) | placeholder del token (se retiró un valor real committeado) |
| Tests | `tests/test_services/test_lotes_service.py` (12), `tests/test_api/test_lotes.py` (6), `tests/test_tools/test_agente_lotes.py` (10) | 28 tests del módulo |
| Memoria | `BITACORA.md`, `CLAUDE.md` (nuevos) | memoria común de chats + instrucciones de sesión |
| Entrega | `docs/ENTREGA_MODULO_AGENTE_LOTES.md` (este archivo) | documentación oficial |

### Dependencias y librerías

- **Cero dependencias nuevas.** Decisión deliberada:
  - Lado app: FastAPI, SQLAlchemy, pydantic, openpyxl — ya estaban en `requirements.txt`.
  - Lado agente: SOLO stdlib (`urllib.request`, `json`, `csv`, `subprocess`,
    `socket`, `argparse`, `logging`, `pathlib`, `tkinter`, `threading`,
    `queue`, `tempfile`, `time`, `os`, `sys`). Tkinter viene incluido con
    Python en Windows. Razón: en el PC del hospital no hay que instalar nada
    más de lo que ya usan los bots (Python + playwright + openpyxl).

---

## 3. Funciones implementadas

### `app/services/lotes_service.py`

- **`parsear_excel_coosalud(contenido: bytes, hoja, incluir_calidad) -> dict[str, dict]`**
  Escribe el upload a un archivo temporal (`tempfile.NamedTemporaryFile`,
  borrado en `finally`) y llama a `tools.responder_glosas_coosalud.leer_excel`.
  **Decisión clave:** NO se duplicó el parser — `leer_excel` del bot es la
  fuente de verdad (match de hoja tolerante a espacios/mayúsculas con
  `casefold`, exclusión de glosas `CALIDAD`, regla `CODIGOS_SIN_SOPORTE =
  {"RE9502"}`). Si la app parseara distinto de lo que después ejecuta el bot,
  el semáforo mentiría. Es viable porque el bot protege su import de
  Playwright con `try/except ImportError` y el `Dockerfile` ya copia
  `tools/` a la imagen. Lanza `ValueError` si falta la hoja o una columna.
- **`crear_lote(db, *, contenido, nombre_archivo, pagador, hoja, incluir_calidad, creado_por) -> LoteRecord`**
  Valida el pagador contra `PAGADORES_SOPORTADOS = {"COOSALUD"}` (ValueError
  "no soportado" si no); parsea; ValueError si no hay facturas; crea el
  `LoteRecord` (con el Excel original en `excel_archivo` BLOB — el agente lo
  descarga de la BD porque el PC no comparte disco con el servidor), una
  `FacturaLoteRecord` por factura (ordenadas) y una `TareaLoteRecord` tipo
  `RESPONDER_<PAGADOR>`; commit + refresh + log.
- **`reclamar_tarea(db, agente: str) -> TareaLoteRecord | None`**
  Claim **atómico**: busca la PENDIENTE más antigua y hace
  `UPDATE ... WHERE id=X AND estado='PENDIENTE'`; si `rowcount==0` (otro
  agente ganó la carrera) hace rollback y reintenta con la siguiente en un
  `while True`; si gana, pone el lote `EN_PROCESO` y devuelve la tarea; si no
  hay pendientes devuelve `None`. Evita corridas dobles del mismo lote.
- **`aplicar_resultados(db, lote_id, resultados: list[dict]) -> int`**
  Upsert del estado por factura desde filas `{factura, estado, detalle}` del
  CSV del bot. **Las facturas desconocidas se AGREGAN al lote** (residuales
  que el bot encontró en el portal pero no estaban en el Excel) en vez de
  perderse. Ignora filas sin factura o sin estado. No hace commit (lo hace el
  llamador).
- **`completar_tarea(db, tarea, *, exito, resultados, error=None) -> LoteRecord`**
  Aplica resultados, cierra la tarea (`COMPLETADA`/`ERROR` + `terminada_en` +
  `error`), cuenta estados por factura y calcula el estado final del lote:
  `ERROR` si `exito=False`; `COMPLETADO_CON_PENDIENTES` si alguna factura
  quedó fuera de `FACTURA_LOTE_ESTADOS_EXITO`; `COMPLETADO` si todas OK.
  Guarda `lote.resumen` y `tarea.resultado` como JSON.
- Constantes: `MAX_EXCEL_BYTES = 20 MB` (los consolidados reales pesan < 5 MB).

### `tools/agente_lotes.py` (núcleo compartido + CLI)

- **`ruta_config() / cargar_config() / guardar_config()`** — configuración
  persistida en `%APPDATA%\MotorGlosasHUS\agente_lotes.json` (o
  `~/.config/MotorGlosasHUS/` en Linux). `cargar_config` devuelve `{}` ante
  archivo inexistente o JSON corrupto. La escribe la ventana; el CLI también
  la lee como fallback.
- **`construir_comando(bot, tarea, carpeta, *, indice, cerrar_residuales, con_cabeza) -> list[str]`**
  Arma la línea del bot: `sys.executable <bot> --excel <carpeta>/<nombre>
  --hoja <hoja> --todas --reporte <carpeta>/reporte.csv --evidencias
  <carpeta>/EVIDENCIA --log <carpeta>/bot.log` + opcionales
  `--incluir-calidad`, `--indice`, `--cerrar-residuales`, `--con-cabeza`.
  Extraída para que CLI y ventana usen exactamente el mismo comando.
- **`ApiLotes`** — cliente HTTP stdlib. `_request()` manda SIEMPRE los headers
  `X-Agente-Token`, `Content-Type: application/json` y
  **`User-Agent: UA_AGENTE`** (ver §Cloudflare). Métodos: `reclamar()` (204 →
  `None`), `descargar_excel()`, `progreso()` (falla solo con warning, no
  aborta), `completar()`. Timeout 120 s.
- **`detalle_http(accion, status, cuerpo) -> str`** — mensaje de error legible;
  si es `403` y el cuerpo contiene `1010`, agrega la explicación de que el
  bloqueo es de Cloudflare (no de la app) y cómo resolverlo.
- **`leer_reporte(ruta) -> list[dict]`** — lee el CSV `--reporte` del bot
  (encoding `utf-8-sig`, columnas `factura,grupos,glosas,estado,detalle`) y
  devuelve `{factura, estado, detalle}` saltando filas vacías.
- **`procesar_tarea(api, tarea, args)`** — descarga Excel → `Popen` del bot →
  cada `INTERVALO_PROGRESO = 30 s` relee el CSV (el bot escribe
  append-as-you-go) y postea progreso si hay filas nuevas → al terminar,
  `completar` con `exito = (returncode == 0)`.
- **`main()`** — CLI: `--url/--token` (fallback: env `MOTOR_GLOSAS_URL` /
  `AGENTE_LOTES_TOKEN` → config guardada), `--workdir` (default
  `lotes_agente`), `--intervalo` (60 s), `--una-vez`, `--indice`,
  `--cerrar-residuales`, `--con-cabeza`. Ante excepción procesando una tarea,
  intenta reportar `completar(exito=False)` para que el lote no quede colgado.

### `tools/agente_lotes_gui.py` (ventana) y `tools/AgenteLotes.pyw` (launcher)

- **`AgenteWorker(threading.Thread)`** — el loop del agente en un hilo daemon;
  le habla a la UI por una `queue.Queue` de eventos `("log"|"estado"|"fin",
  dato)`. `_esperar()` duerme en pasos de 0.5 s chequeando el `stop_event`
  (poll cada `INTERVALO_POLL = 60 s`). `_procesar()` replica el flujo del CLI
  con dos diferencias: lanza el bot con `subprocess.CREATE_NO_WINDOW` (bajo
  `pythonw` el bot no abre consola negra; sus logs quedan en `bot.log`) y si
  el usuario detiene a mitad de corrida hace `terminate()` → `wait(30)` →
  `kill()` si no muere, y reporta `completar(exito=False, error="Detenido por
  el usuario desde el agente.")` con las filas parciales del CSV.
- **`VentanaAgente`** — Tkinter/ttk. Campos: URL, token (`show="•"`), carpeta
  de trabajo (default `Path.home()/"lotes_agente"`, con Examinar…), índice de
  soportes opcional (Examinar…), checkboxes "Mostrar el navegador del bot
  (debug)" y "Cerrar glosas residuales del portal con RE9901". Botón único
  Iniciar/Detener (Detener pide confirmación y avisa que el lote quedará en
  ERROR reintentable), etiqueta de estado en vivo, log `ScrolledText`
  readonly con hora. Al Iniciar valida URL+token, **guarda la config**
  (por eso "se guarda sola") y lanza el worker. Bomba de eventos con
  `raiz.after(200, ...)`. Cierre de ventana con confirmación si el worker vive.
- **`AgenteLotes.pyw`** — 5 líneas: agrega `tools/` al `sys.path` e invoca
  `agente_lotes_gui.main()`. Se separó GUI (.py, lintable por ruff) del
  launcher (.pyw, doble clic) a propósito: ruff no formatea `.pyw`.

### Fixes a tests preexistentes (22-jul)

- **`_fecha_reciente(dia_semana, hora, minuto=0)`** (helper repetido en
  `tests/test_api/test_por_dia_semana.py`, `test_heatmap_actividad.py`,
  `test_audit_heatmap.py`): fecha UTC de hace 7–13 días que cae en el día de
  semana pedido — reemplaza fechas fijas de abril que caducaron (ver §15).

---

## 4. Flujo completo (paso a paso)

1. **El auditor sube el Excel** consolidado COOSALUD → `POST /lotes/`
   (multipart: `archivo`, `pagador=COOSALUD`, `hoja=BASE`,
   `incluir_calidad=false`). Requiere rol AUDITOR o superior (JWT).
2. La API valida extensión (`.xlsx`/`.xlsm` → 400 si no) y tamaño (≤20 MB →
   400). `crear_lote` parsea con el parser del bot: agrupa por factura en
   "grupos de respuesta" (código+observación), cuenta glosas, marca
   `requiere_soporte` solo si `tipo==SOPORTES` Y el código no es RE9502,
   separa las CALIDAD. Errores de parseo → 400 con el mensaje exacto
   ("El Excel no tiene la hoja…", "Falta la columna…").
3. Quedan en BD: 1 `lotes` (estado `EN_COLA`, Excel en BLOB), N
   `facturas_lote` (estado `PENDIENTE`), 1 `tareas_lote` (`PENDIENTE`,
   tipo `RESPONDER_COOSALUD`). Respuesta 201 con el resumen del lote.
4. **El agente** (ventana abierta en el PC de cartera, o CLI) hace polling:
   `POST /agente/lotes/tareas/reclamar {"agente": "<hostname>"}` con header
   `X-Agente-Token`. 204 = cola vacía (estado "En espera de lotes…"); 200 =
   entrega `{tarea_id, tipo, lote_id, pagador, nombre_archivo, hoja,
   incluir_calidad, total_facturas}`. El claim marca la tarea `RECLAMADA`
   (+agente+`reclamada_en`) y el lote `EN_PROCESO` de forma atómica.
5. `GET /agente/lotes/tareas/{id}/excel` → bytes del Excel original →
   se guarda en `<workdir>/lote_<id>/<nombre_archivo>`.
6. El agente lanza el bot real (`responder_glosas_coosalud.py --todas
   --reporte …`). El bot hace el trabajo de portal de siempre (login con
   `COOSALUD_USER/PASSWORD` del entorno, responde grupo por grupo, adjunta
   PDX cuando corresponde, pantallazos en `EVIDENCIA/`) y escribe su CSV
   incremental.
7. Cada 30 s el agente relee el CSV; si hay filas nuevas →
   `POST /agente/lotes/tareas/{id}/progreso` → `aplicar_resultados` actualiza
   el semáforo (upsert por factura). El detalle del lote
   (`GET /lotes/{id}`) muestra el avance en vivo.
8. Al terminar el bot → `POST /agente/lotes/tareas/{id}/completar` con
   `exito`, todas las filas y `error` si lo hubo → estado final del lote:
   `COMPLETADO` / `COMPLETADO_CON_PENDIENTES` / `ERROR`, con `resumen` JSON
   de conteos. Reportar sobre una tarea no-RECLAMADA → 409 (idempotencia).
9. Estados de factura que cuentan como éxito (`FACTURA_LOTE_ESTADOS_EXITO`):
   `OK`, `OK_CALIDAD_ABIERTA`, `OK_SIN_DIALOGO`, `YA_PROCESADA`,
   `SOLO_CALIDAD`, `TERMINADA_SIN_CARTEL`. Cualquier otro (`PENDIENTE`,
   `PENDIENTE_PDX`, `RECHAZADA: …`, `ERROR`, `NO_EN_BOLSA`…) cuenta como
   pendiente para el estado del lote.

---

## 5. Base de datos

Tres tablas nuevas, registradas en `Base` y creadas por el
`Base.metadata.create_all` del lifespan de `app/main.py` (convención del
repo — existe una única migración Alembic inicial; NO se escribió migración
nueva a propósito, siguiendo el patrón vigente).

**`lotes` (`LoteRecord`)**
`id` PK · `creado_en` (server_default now, index) · `creado_por` str(200) NOT NULL ·
`pagador` str(50) NOT NULL index · `nombre_archivo` str(300) NOT NULL ·
`hoja` str(100) default "BASE" · `incluir_calidad` int 0/1 ·
`estado` str(50) index, default `EN_COLA` (valores: `EN_COLA`, `EN_PROCESO`,
`COMPLETADO`, `COMPLETADO_CON_PENDIENTES`, `ERROR`) · `total_facturas` int ·
`total_glosas` int · `total_calidad` int (glosas CALIDAD excluidas) ·
`excel_archivo` **LargeBinary NOT NULL** (el Excel tal como se subió) ·
`resumen` Text JSON nullable · `actualizado_en` (onupdate now).

**`facturas_lote` (`FacturaLoteRecord`)**
`id` PK · `lote_id` FK→`lotes.id` ON DELETE CASCADE, index, NOT NULL ·
`factura` str(50) NOT NULL index · `grupos` int · `glosas` int · `calidad` int ·
`requiere_soporte` int 0/1 · `estado` str(50) index default `PENDIENTE` ·
`detalle` Text nullable (motivo textual del bot) · `actualizado_en` (onupdate).
Índice único compuesto: `ix_facturas_lote_lote_factura (lote_id, factura)`.

**`tareas_lote` (`TareaLoteRecord`)**
`id` PK · `lote_id` FK→`lotes.id` ON DELETE CASCADE, index, NOT NULL ·
`tipo` str(50) NOT NULL default `RESPONDER_COOSALUD` · `estado` str(50) index
default `PENDIENTE` (valores: `PENDIENTE`, `RECLAMADA`, `COMPLETADA`,
`ERROR`) · `agente` str(200) nullable (hostname que reclamó) · `creado_en` ·
`reclamada_en` nullable · `terminada_en` nullable · `error` Text nullable ·
`resultado` Text JSON nullable.

Booleanos como `Integer` 0/1: convención existente del esquema
(`UsuarioRecord.activo == 1`).

**La cola de trabajos ES la BD** (polling del agente). Se descartó
Redis/Celery deliberadamente: volumen bajísimo (lotes por día, no por
segundo) y cero infraestructura nueva.

---

## 6. Backend

### Endpoints de usuario (`router`, prefix `/lotes`, tag `lotes`)

| Método/Ruta | Auth | Qué hace | Errores |
|---|---|---|---|
| `POST /lotes/` (201) | `get_auditor_o_superior` (JWT) | multipart `archivo` + Form `pagador/hoja/incluir_calidad`; crea el lote | 400 extensión, 400 tamaño >20MB, 400 ValueError de parseo/pagador |
| `GET /lotes/?limite=50` | `get_usuario_actual` | lista descendente por id; `limite` acotado a [1,200] | — |
| `GET /lotes/{id}` | `get_usuario_actual` | detalle: lote + `facturas[]` (semáforo) + `tareas[]` | 404 |

### Endpoints del agente (`agente_router`, prefix `/agente/lotes`, tag `agente-lotes`)

| Método/Ruta | Qué hace | Errores |
|---|---|---|
| `POST /tareas/reclamar` body `{agente}` | claim atómico; 200 con la tarea o **204** vacío | 401/503 auth |
| `GET /tareas/{id}/excel` | bytes del Excel (media type xlsx, Content-Disposition attachment) | 404 tarea, 409 no RECLAMADA |
| `POST /tareas/{id}/progreso` body `CompletarBody` | upsert incremental del semáforo; devuelve `{aplicadas}` | 404/409 |
| `POST /tareas/{id}/completar` body `CompletarBody` | cierra tarea + estado final del lote; devuelve el lote | 404/409 |

### Autenticación del agente — decisión de diseño

`verificar_token_agente` (dependencia FastAPI): compara el header
`X-Agente-Token` contra `Settings.agente_lotes_token` con
`secrets.compare_digest` (anti timing-attack). **Sin la variable
configurada → 503** "Agente de lotes deshabilitado" (un deploy sin
configurar no expone la cola). Token inválido → 401. **Por qué no JWT:** el
agente es headless y los JWT de usuario expiran a las 8 h
(`access_token_expire_minutes=480`); un token estático compartido
servidor↔PC es el trade-off correcto para la Fase 1.

### Modelos pydantic (en el router)

`ReclamarBody {agente: str 1..200}` · `ResultadoFactura {factura, estado,
detalle=""}` · `CompletarBody {exito: bool, resultados: [ResultadoFactura]=[],
error: str|None}`. Respuestas como dicts (convención del repo,
p.ej. `adjuntos.py`).

### Middleware/validaciones

No se agregó middleware nuevo; los routers se registran al final de
`app/main.py` con un comentario de sección. La validación de tamaño/extensión
vive en el endpoint; la de contenido, en el parser del bot.

---

## 7. Frontend

- **NO se construyó pantalla web** para este módulo — hallazgo documentado:
  las 8 menciones de "lotes" en `static/index.html` pertenecen a otra función
  preexistente (historial de importación masiva,
  `/glosas/importar-masiva/lotes`), NO a los lotes de portal. La pantalla
  "Lotes" del navegador es el **pendiente #2** (ver §15).
- **El frontend de este módulo es la ventana de escritorio** (Tkinter):
  - Sección "Conexión (se guarda sola)": Entry URL + Entry token oculto (•).
  - Sección "Opciones": Entry+botón "Examinar…" para carpeta de trabajo,
    Entry+"Examinar…" para índice TXT de soportes, 2 Checkbutton
    (navegador visible / cerrar residuales RE9901).
  - Botón `▶ Iniciar agente` ⟷ `■ Detener agente` (con `messagebox.askyesno`
    de confirmación al detener y al cerrar la ventana con el worker vivo).
  - `Estado:` etiqueta en negrilla actualizada en vivo ("Detenido",
    "Iniciando…", "En espera de lotes… (la cola está vacía)", "Sin conexión —
    reintentando…", "Lote N: descargando Excel…", "Lote N: X/Y facturas
    procesadas…").
  - Log `ScrolledText` de solo lectura con hora `HH:MM:SS` por línea.
  - Ventana mínima 640×520, título "Agente de Lotes — Motor Glosas HUS".
- **Historia del cambio de enfoque:** la Fase 1 entregó primero un CLI
  (`py tools\agente_lotes.py`). El piloto real falló por fricción: el usuario
  ejecutó desde `C:\Users\cartera` (fuera de la carpeta del repo →
  `can't open file`) y el flujo `setx` resultaba hostil. Se pivoteó a la
  ventana de doble clic; el CLI se conservó para automatización/avanzados.

---

## 8. IA

**Este módulo NO invoca IA en runtime.** Es orquestación determinista
(parseo de Excel, cola en BD, subprocess del bot Playwright, HTTP).

Contexto del sistema anfitrión (relevante solo como entorno, ya existía): el
motor de dictámenes usa Groq como primario (`meta-llama/llama-4-scout-17b-16e-instruct`
con fallbacks `openai/gpt-oss-120b`, `qwen/qwen3-32b`, `llama-3.3-70b-versatile`),
Anthropic `claude-sonnet-4-5` para casos complejos y Gemini `gemini-2.0-flash`
solo para OCR de PDFs. Nada de esto se modificó en esta sesión.

(El desarrollo en sí fue asistido por Claude Code, con revisión adversarial
de código en los PRs, pero eso es proceso, no runtime del módulo.)

---

## 9. Automatizaciones

1. **Cola automática:** cada Excel subido crea su tarea; cualquier agente
   encendido la toma sin intervención (polling cada 60 s).
2. **Progreso automático:** el agente relee el CSV del bot cada 30 s y
   actualiza el semáforo sin que nadie lo pida.
3. **Configuración persistente:** URL/token/opciones se guardan solos en
   `%APPDATA%\MotorGlosasHUS\agente_lotes.json` al presionar Iniciar.
4. **Recuperación ante fallos:** excepción procesando una tarea → el agente
   reporta `completar(exito=False)` para que el lote quede en `ERROR` visible
   (no colgado en `EN_PROCESO`); si ni eso puede, lo loguea.
5. **Auto-deploy preexistente que integra el módulo:** el servidor
   (`/opt/motor-glosas`, VM Linux e2-micro 1GB) corre por cron
   `deploy/auto_update.sh`: `git fetch/pull --ff-only` de `motor-glosas` +
   `docker compose up -d --build` (con lock por flock, guarda de memoria
   ≥500MB libres, y prune de imágenes). Cada merge a `motor-glosas` llega
   solo a producción.

---

## 10. Archivos modificados/creados (lista exhaustiva de la sesión)

**PR #169 — `27f3e13` "feat(lotes): Fase 1 app unificada" (+1.283/−9, 10 archivos)**
- `app/models/db.py` — import ampliado con `LargeBinary`; +3 modelos y
  constantes de estado al final (sección "Lotes de portal").
- `app/core/config.py` — +campo `agente_lotes_token: str = ""` con comentario
  de por qué token estático y por qué vacío=deshabilitado.
- `app/main.py` — +imports y `include_router(lotes_router)` /
  `include_router(agente_lotes_router)` al final.
- `app/services/lotes_service.py` — NUEVO (todo el servicio).
- `app/api/routers/lotes.py` — NUEVO (ambos routers).
- `tools/agente_lotes.py` — NUEVO (agente CLI v1).
- `tools/README_agente_lotes.md` — NUEVO.
- `tests/test_services/test_lotes_service.py` — NUEVO (12 tests).
- `tests/test_api/test_lotes.py` — NUEVO (6 tests).
- `tests/test_api/test_import_history.py` — solo re-formato ruff (rompía
  `ruff format --check .` de CI; preexistente).
- (El PR arrastró además 4 commits previos de la rama que no estaban en
  `motor-glosas`: fix RE9502 COOSALUD, `--hoja` tolerante, marcadores de
  conflicto en `evidencias_a_word.py`, informe de gerencia Lote V2.)

**PR #170 — `0795957` "feat(agente-lotes): versión de escritorio" (+599/−71, 5 archivos)**
- `tools/agente_lotes.py` — refactor: `construir_comando()` extraído;
  `ruta_config/cargar_config/guardar_config`; CLI resuelve URL/token también
  desde la config; docstring reescrito (escritorio primero).
- `tools/agente_lotes_gui.py` — NUEVO (ventana + worker).
- `tools/AgenteLotes.pyw` — NUEVO (launcher).
- `tools/README_agente_lotes.md` — reescrito (escritorio primero + problemas
  comunes, incluido el `can't open file` del piloto).
- `tests/test_tools/test_agente_lotes.py` — NUEVO (7 tests).

**PR #171 — `bec3cbc` "fix(agente-lotes): pasar el firewall de Cloudflare" (3 archivos)**
- `tools/agente_lotes.py` — +`UA_AGENTE`, +`detalle_http()`, header
  `User-Agent` en `_request`, mensajes de error vía `detalle_http`.
- `tools/README_agente_lotes.md` — +caso 403/1010 en problemas comunes.
- `tests/test_tools/test_agente_lotes.py` — +3 tests (UA+token en el request
  con `urlopen` falso; hint Cloudflare en 403+1010; sin hint en otros).

**PR #172 — `49d7c2d` "fix(deploy): pasar AGENTE_LOTES_TOKEN al contenedor" (2 archivos)**
- `docker-compose.yml` — +`AGENTE_LOTES_TOKEN: ${AGENTE_LOTES_TOKEN:-}` en la
  sección de secretos del servicio `motor`, con comentario del porqué.
- `.env.example` — el token real committeado (`08027f8`, hecho por el usuario
  desde otro flujo) se reemplazó por placeholder
  `CAMBIAR_POR_UNA_CADENA_LARGA_ALEATORIA` + instrucciones.

**PR #178 (abierto) — 3 commits**
- `98426f9` — `BITACORA.md` NUEVO (memoria común: proyecto, hecho por fecha
  12-jun→22-jul, PENDIENTE, PARA MAÑANA, mantenimiento) y `CLAUDE.md` NUEVO
  (leer bitácora al iniciar / actualizarla al terminar + datos clave).
- `b242ed3` — fix de 3 bombas de tiempo:
  `tests/test_api/test_por_dia_semana.py`,
  `tests/test_api/test_heatmap_actividad.py` (rotas el 22-jul) y
  `tests/test_api/test_audit_heatmap.py` (habría explotado ~18-ago) — helper
  `_fecha_reciente` + fechas relativas; imports ajustados; `timezone.utc` →
  `datetime.UTC` (autofix UP017).
- `0df7894` — registro del fix en la propia `BITACORA.md`.
- Este documento (`docs/ENTREGA_MODULO_AGENTE_LOTES.md`).

---

## 11. Dependencias nuevas

**Ninguna.** No se agregó ningún paquete a `requirements.txt` ni
`requirements-dev.txt`. (En el contenedor de desarrollo se instalaron las
dependencias YA declaradas del proyecto para correr la suite; hubo que
`pip install --ignore-installed` por conflictos con paquetes Debian del
sistema — dato de entorno de desarrollo, no del proyecto.)

---

## 12. Configuración

| Variable / archivo | Dónde | Para qué |
|---|---|---|
| `AGENTE_LOTES_TOKEN` | `.env` del servidor **+ declarada en `environment:` de `docker-compose.yml`** | habilita `/agente/lotes`; vacía/ausente = 503. ⚠️ Regla del repo: una variable solo en `.env` NO llega al contenedor si el compose no la referencia (patrón "knobs que no llegaban", auditoría jul-2026). El default vacío `${AGENTE_LOTES_TOKEN:-}` es seguro AQUÍ porque el campo es `str` (no rompe Settings como el incidente `SMTP_PORT=""` del 3-jul); no replicar con campos tipados. |
| `AGENTE_LOTES_TOKEN` (PC) | env del PC o campo de la ventana | debe ser IDÉNTICO al del servidor |
| `MOTOR_GLOSAS_URL` (PC) | env del PC o campo de la ventana | URL de la app (producción: `https://iaglosassinac.help`) |
| `COOSALUD_USER` / `COOSALUD_PASSWORD` | env del PC (preexistentes) | credenciales del bot; el agente NO las toca, las hereda el subprocess |
| `%APPDATA%\MotorGlosasHUS\agente_lotes.json` | PC | config de la ventana: `url, token, workdir, indice, con_cabeza, cerrar_residuales` (token en claro — mismo nivel de exposición que el `setx` de los bots) |
| `<workdir>/lote_<id>/` | PC | por corrida: Excel descargado, `reporte.csv`, `bot.log`, `EVIDENCIA/` |
| `UA_AGENTE` | constante en `agente_lotes.py` | `"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AgenteLotesHUS/1.0"` — necesario para atravesar Cloudflare |

**⚠️ Token quemado:** el valor `A7F9D2C8E1B6K4M3P5Q8R2T9V6X1Y4Z7` quedó en el
historial de git (`.env.example`, commit `08027f8`). NO usarlo jamás en
producción; generar una cadena nueva (p. ej. `openssl rand -hex 32`).

---

## 13. Riesgos al integrarlo

1. **Cloudflare:** producción está detrás de un túnel de Cloudflare con Bot
   Fight Mode. El UA del agente atraviesa hoy el filtro (verificado contra el
   dominio real: se pasó de `403 error code: 1010` al JSON de FastAPI); si
   Cloudflare endurece reglas (JS challenge), el plan B documentado es
   Security → Bots → desactivar Bot Fight Mode, o regla WAF skip para
   `/agente/*`, o subdominio DNS-only.
2. **Var de compose:** si el proyecto principal usa otro compose/orquestador,
   replicar el passthrough del token o el módulo devolverá 503 eternamente.
3. **Excel en BLOB (SQLite):** aceptable a este volumen (<5MB por lote, tope
   20MB); a gran escala migrar a filesystem/objeto y guardar solo la ruta.
4. **Concurrencia del claim:** el UPDATE condicionado es correcto en
   SQLite/Postgres para este volumen; con muchos agentes simultáneos en
   Postgres considerar `SELECT ... FOR UPDATE SKIP LOCKED`.
5. **PHI:** el Excel y las evidencias contienen datos de pacientes; viajan
   por HTTPS al servidor propio del hospital — no llevar a servicios de
   terceros sin evaluarlo.
6. **`create_all` vs migraciones:** las tablas nacen del lifespan; si el
   proyecto principal exige Alembic estricto, generar la migración de las 3
   tablas antes de integrar.
7. **Tests con fechas:** patrón detectado y corregido (bombas de tiempo);
   revisar que el proyecto principal no siembre fechas fijas contra ventanas
   móviles (`tests/test_api/test_serie_mensual_cantidad.py` usa meses fijos
   de 2026 — vigilar en 2027).
8. **404 tras integrar:** hasta que el servidor corra el build con estos
   routers, el agente logueará `HTTP 404 {"detail":"Not Found"}` — es la
   firma de "código viejo desplegado", no un bug del agente.

---

## 14. Dependencias con otros módulos

**Este módulo NECESITA:**
- `tools/responder_glosas_coosalud.py` — el bot ejecutado Y la fuente del
  parser (`leer_excel`, `CODIGOS_SIN_SOPORTE`) y del formato del CSV de
  reporte (`factura,grupos,glosas,estado,detalle`, utf-8-sig, estados
  terminales). **Contrato crítico:** cambios en `leer_excel`, en los flags
  CLI (`--excel --hoja --todas --reporte --evidencias --log
  --incluir-calidad --indice --cerrar-residuales --con-cabeza`) o en el CSV
  rompen agente y/o semáforo.
- `app/api/deps.py` (`get_usuario_actual`, `get_auditor_o_superior`),
  `app/core/config.py` (`get_settings`), `app/database.py`
  (`Base`, `get_db`), `app/models/db.py` (`UsuarioRecord`, roles).
- Dockerfile que copie `tools/` a la imagen (ya lo hace, línea `COPY tools/`).
- Infra: docker compose + cloudflared + `deploy/auto_update.sh` (cron).

**A este módulo lo USAN:** nadie todavía dentro del código (la futura
pantalla web "Lotes" consumirá `GET /lotes` y `GET /lotes/{id}`; la Fase 2
agregará `RESPONDER_SIMED` a `BOTS_POR_TIPO` y a `PAGADORES_SOPORTADOS`).

---

## 15. Pendientes, mejoras previstas y errores conocidos

1. **Piloto en producción sin cerrar.** Verificado en vivo: el agente del PC
   (`PCSINAC07`) atraviesa Cloudflare pero el servidor respondía 404 (build
   anterior a #169). Falta: en la VM `cd /opt/motor-glosas && sudo bash
   deploy/auto_update.sh`; agregar `AGENTE_LOTES_TOKEN=<cadena NUEVA>` al
   `.env`; `sudo docker compose up -d`; token nuevo en la ventana; éxito =
   "En espera de lotes…" / `curl` de reclamar devuelve 204.
2. **Pantalla "Lotes" en la app web** (subir Excel y ver el semáforo desde el
   navegador). Hoy solo existe la API.
3. **Fase 2 prevista:** bot SIMED (notas crédito) en la misma cola; agente
   como servicio de Windows (arranque automático); botón "reintentar" por
   lote/factura (hoy el reintento es re-subir el lote con `--saltar-csv`
   implícito vía estados).
4. **Mejoras identificadas no implementadas:** watchers (carpeta/correo) para
   ingesta automática del Excel; generación automática del Word de evidencias
   y del informe de gerencia al cerrar el lote (plantillas ya existen:
   `evidencias_a_word.py`, `INFORME_GERENCIA.md`).
5. **Errores conocidos:** ninguno abierto en el módulo. El `progreso` que
   falla solo deja warning (el `completar` final trae todas las filas —
   pérdida tolerada de granularidad, por diseño). PR #178 quedó con CI
   re-corriendo tras el fix de las bombas de tiempo.

---

## 16. Recomendaciones para fusionarlo al proyecto principal

1. **Traer el código en este orden lógico** (o como un solo merge de
   `motor-glosas`, que ya lo contiene todo): modelos+constantes →
   `lotes_service` → router+registro en main → settings → compose →
   `tools/agente_lotes*.{py,pyw}` + README → tests.
2. **No traducir el parser:** mantener la importación desde
   `tools.responder_glosas_coosalud`. Si el proyecto principal reorganiza
   `tools/`, mover el import y el `BOTS_POR_TIPO` juntos.
3. **Verificación mínima post-merge (los mismos gates de esta entrega):**
   `ruff check . --select F,W6` + `ruff format --check .` +
   `pytest tests/test_services/test_lotes_service.py tests/test_api/test_lotes.py
   tests/test_tools/test_agente_lotes.py` (28 en verde) + suite completa.
4. **Smoke end-to-end reproducible** (así se validó aquí): levantar uvicorn
   con `AGENTE_LOTES_TOKEN` seteado; sembrar un lote con
   `lotes_service.crear_lote` sobre la misma BD; correr
   `python tools/agente_lotes.py --una-vez --url http://127.0.0.1:8000
   --token <t>`; sin Playwright instalado el bot sale con código 2 y el lote
   DEBE quedar `ERROR` con "El bot terminó con código 2 (ver bot.log)." —
   eso prueba el circuito completo incluida la ruta de error.
5. **Configurar producción:** token NUEVO en `.env` + compose passthrough +
   recrear contenedor; confirmar con
   `curl -X POST …/agente/lotes/tareas/reclamar -H "X-Agente-Token: <t>"
   -H "User-Agent: AgenteLotesHUS/1.0" -d '{"agente":"prueba"}'` → 204.
6. **En el PC:** carpeta del proyecto clonada con git (no ZIP — lección del
   piloto: el ZIP renombra la carpeta y no permite `git pull`), doble clic en
   `tools\AgenteLotes.pyw`, token nuevo, Iniciar.
7. **No fusionar el token de ejemplo:** cualquier valor visto en el historial
   está quemado.

---

## 17. Resumen ejecutivo para el mantenedor

Recibes un módulo de **orquestación de bots por cola** con tres piezas:
(1) API en la app (`/lotes` para humanos con JWT, `/agente/lotes` para el
agente con token estático `X-Agente-Token`; cola = tabla `tareas_lote`,
claim atómico por UPDATE condicionado); (2) un **servicio** cuya única regla
de oro es *parsear con el mismo código que ejecuta* (importa `leer_excel`
del bot — si tocas el bot, corre los tests del módulo); (3) un **agente de
escritorio** stdlib-only (ventana Tkinter + hilo worker + cliente urllib)
que vive en el PC del hospital, se configura una sola vez
(`%APPDATA%\MotorGlosasHUS\agente_lotes.json`) y lanza el bot como
subprocess leyendo su CSV incremental cada 30 s.

Las cuatro cosas que muerden y ya están resueltas — no las des-resuelvas:
**Cloudflare** exige el `User-Agent` custom (`UA_AGENTE`); las variables del
`.env` del servidor **deben declararse también en el compose**; el token de
ejemplo del historial está **quemado**; y los tests de estadísticas usan
fechas **relativas** (`_fecha_reciente`) porque las fijas explotan al salir
de la ventana. El estado vivo del proyecto se lleva en `BITACORA.md`
(léela al empezar, actualízala al terminar — `CLAUDE.md` lo exige).
Todo lo demás son 28 tests que te cuentan el contrato completo.
