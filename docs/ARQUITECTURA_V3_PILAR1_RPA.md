# V3 · Pilar 1 — Radicación autónoma en los portales (RPA)

> **Qué es este documento.** La arquitectura acordada para que el motor radique
> por sí solo, en los portales de las EPS, las respuestas de glosa que un humano
> ya aprobó. Aprobada por el auditor el 03-09-2026 sin modificaciones.
>
> **Para quién.** La primera mitad se lee sin ser programador: explica dónde
> corre cada cosa y por qué. La segunda mitad tiene el detalle técnico
> (esquema de tabla, estados, protocolo).

---

## 0) Las dos decisiones que fijó el auditor

1. **El reloj.** `RADICADA_EN_EPS` **detiene definitivamente** el reloj interno
   de respuesta del hospital. La glosa sale de la semaforización de urgencia
   (las barras rojas y ámbar) y pasa a una bandeja **«En espera de EPS»**, con
   un reloj **pasivo** que cuenta los días legales que tiene el pagador para
   emitir su fallo.
2. **Matriz de portales.**
   - **Automatización total** (usuario y contraseña): **COOSALUD, SIMED,
     Mutual Ser** → van a la cola RPA de Playwright.
   - **Intervención humana** (captcha o token dinámico): **FOMAG, DGH,
     NUEVA EPS** → sus filas **nacen en `HUMANO_REQUERIDO`**. No se promete
     autonomía donde técnicamente no la hay.

---

## 1) Punto de partida: esto no se construye desde cero

Antes de diseñar se revisó el código existente. **La mitad del RPA ya está
construida** y se reutiliza tal cual:

| Pieza que ya existe | Dónde | Qué resuelve |
|---|---|---|
| Playwright sync + Chromium, **headless por defecto** | `tools/responder_glosas_coosalud.py` (`headless=not args.con_cabeza`), `..._simed.py` | El motor de navegación |
| `TrabajoBotRecord` — «cola **universal** de trabajos para los bots del PC» | `app/models/db.py` | Encolar / reclamar / reportar |
| Protocolo de despacho | `/bots/trabajos/reclamar`, `/progreso`, `/finalizar`, `/{bot}/ejecutar`, `/cancelar`, `/reintentar` | El servidor encola, el PC ejecuta |
| Agente local | `tools/agente_bots_hus.py` + `tools/AGENTE_BOTS.cmd` | Quien de verdad abre el navegador |
| Catálogo declarativo | `app/services/bots_hus.py` (`BotHUS`, `comando_pc=...`) | Registro de bots |

**Por eso el Pilar 1 es**: añadir un bot radicador al tejido de despacho que ya
existe, más un **libro de radicación por glosa**. Eso último es lo único
genuinamente nuevo.

---

## 2) Dependencias en Windows

**No entra ninguna librería nueva.** Se consolida la que ya se usa:

| Dependencia | Hoy | Acción |
|---|---|---|
| `playwright` | importado con `try/except`, instalado a mano por el auditor | **declararlo y fijarlo** en `requirements.txt` |
| Chromium de Playwright | `py -m playwright install chromium` manual | comprobación al arrancar el agente; si falta, mensaje claro. **No se instala solo** |
| `openpyxl`, `httpx` | ya declarados | sin cambio |

**Selenium queda descartado.** Añadiría un segundo motor de navegador, otro
driver que versionar contra Chrome, y partiría en dos el conocimiento de los
bots que ya funcionan.

**Privilegios** (regla de runbook del 03-09-2026):
- El agente radicador corre **con la sesión del auditor, sin elevación** —
  necesita el share `\\Prime\radicacion_2026` para adjuntar soportes.
- Si se quiere que sobreviva al reinicio nocturno, va por la misma tarea de
  Windows del motor, y **esa instalación sí exige «Ejecutar como
  administrador»**, una única vez.

---

## 3) Dónde corre cada cosa, y por qué

El servidor del motor **no puede** alcanzar los portales: no tiene las
credenciales y **no debe tenerlas**. El PC del auditor sí.

```
Motor (8080)                     Agente del PC              Portal de la EPS
  encola trabajo   ──────────▶  reclama
  (QUÉ radicar)                 abre Chromium headless ──▶  login + radica
  recibe evidencia ◀──────────  reporta radicado + PDF ◀──  comprobante
```

**La cola transporta QUÉ radicar, jamás CÓMO autenticarse.** Las claves siguen
en `config/entidades.credenciales.json` (local, no versionado), leídas solo por
el agente. Esa frontera es la que impide que una filtración de la base de datos
exponga los portales de la entidad.

---

## 4) La cola: qué se reutiliza y qué es nuevo

- **Capa de despacho → `TrabajoBotRecord`, sin tocar.** Un trabajo = una
  corrida del radicador para una EPS. Ya trae `estado`, `progreso`, `equipo`,
  `error`, cancelación y reintento.
- **Capa de evidencia → tabla nueva `radicaciones_eps`.** `TrabajoBotRecord` es
  por *corrida*; la radicación necesita estado y prueba **por glosa**. Meter eso
  en el JSON de `resultado` haría imposible responder «¿esta factura quedó
  radicada?» sin parsear texto libre.

---

## 5) Tabla nueva: `radicaciones_eps` (el libro de radicación)

Una fila por glosa a radicar. Se **inserta y se le cambia el estado**; la
evidencia, una vez escrita, **no se edita** (misma doctrina que la bitácora del
Auto-Pilot).

| Campo | Tipo | Propósito |
|---|---|---|
| `id` | int PK | — |
| `creado_en` | timestamp | — |
| `glosa_id` | int, índice | la glosa que se radica |
| `clave_idempotencia` | str(200), **único** | `eps\|factura\|codigo\|etapa` — reconoce el mismo trabajo aunque cambie el id |
| `trabajo_bot_id` | int, índice | qué corrida la ejecutó (`trabajos_bot.id`) |
| `eps`, `portal` | str | destino |
| `estado` | str(40), índice | ver máquina de estados |
| `intentos` | int | diagnóstico sin adivinar |
| `ultimo_error` | text | el último fallo, en palabras |
| `radicado_numero` | str(120) | **la evidencia** que devuelve el portal |
| `comprobante_ruta` | str(500) | PDF o captura del comprobante |
| `comprobante_sha256` | str(64) | hash del comprobante (engancha con el Pilar 6) |
| `radicado_en` | timestamp | cuándo quedó radicada |
| `verificado_en`, `verificado_por` | timestamp, str | quién confirmó una dudosa |
| `actor` | str(120) | `radicador-rpa`, o el correo de quien confirmó |

**El índice único sobre `clave_idempotencia` es la barrera anti-duplicado**: la
base impide físicamente dos radicaciones vivas de la misma glosa, aunque falle
toda la lógica de arriba.

---

## 6) Máquina de estados

```
PENDIENTE ─▶ RECLAMADA ─▶ EN_PORTAL_SIN_CONFIRMAR ─▶ RADICADA
                  │                 │
                  │                 └─▶ VERIFICAR_MANUAL ─▶ RADICADA
                  │                                      └─▶ PENDIENTE
                  ├─▶ FALLIDA            (reintentable)
                  └─▶ HUMANO_REQUERIDO   (captcha, token, portal cambiado,
                                          dictamen obsoleto)
```

| Estado | Significa |
|---|---|
| `PENDIENTE` | encolada, nadie la ha tomado |
| `RECLAMADA` | un agente la tomó (reclamo atómico) |
| `EN_PORTAL_SIN_CONFIRMAR` | **se pulsó radicar y no se leyó el comprobante** |
| `RADICADA` | hay número de radicado y comprobante guardado |
| `VERIFICAR_MANUAL` | hay que mirar el portal antes de decidir |
| `FALLIDA` | falló limpio (no llegó a enviar): se puede reintentar |
| `HUMANO_REQUERIDO` | no es automatizable: lo hace una persona |

---

## 7) El punto crítico: idempotencia

Radicar dos veces es un daño real ante la EPS. El riesgo **no** es el reintento
normal — es **el corte a mitad del envío**: el bot pulsó «Radicar» y se cayó la
red antes de leer el comprobante. No se sabe si quedó.

**Regla:** ese caso entra a `EN_PORTAL_SIN_CONFIRMAR` y **está prohibido el
reintento automático desde ahí**. Solo sale por una pasada de *verificación* que
consulta el portal por número de factura antes de decidir. Es la misma doctrina
del cortacircuito OCR de la V2: **ante la duda, no se actúa a ciegas**.

Refuerzos:
- **Reclamo atómico** de la fila (`UPDATE ... WHERE estado='PENDIENTE'`): dos
  agentes no pueden tomar la misma.
- **Índice único** por `clave_idempotencia`.
- **Piloto obligatorio de 1 factura** por EPS antes del masivo — regla del
  `CLAUDE.md`, codificada en el bot, no confiada a la memoria del auditor.

---

## 8) El reloj: `RADICADA_EN_EPS` y la bandeja «En espera de EPS»

Al confirmarse la radicación, la glosa pasa a `RADICADA_EN_EPS`. Eso:

1. **La saca del semáforo de urgencia.** El estado entra a `ESTADOS_CERRADOS`
   de `motor_vencimientos`: ya no compite contra el reloj del hospital, no sale
   en rojo ni en ámbar, y el Auto-Pilot deja de considerarla.
2. **Arranca el reloj pasivo del pagador.** Se cuentan los días hábiles que la
   EPS tiene para emitir su fallo desde `radicado_en` (Art. 57 de la Ley 1438 de
   2011, el mismo artículo que ya rige los plazos del trámite en este motor).
   Ese contador es **informativo**: mide a la EPS, no al hospital.

> El plazo exacto del pagador se toma del artículo citado, nunca de la memoria
> del modelo — la regla 1.bis del prompt aplica también aquí.

---

## 9) Enganche con los 12 escudos de la V2 — ninguno se toca

| Escudo | Cómo lo respeta el radicador |
|---|---|
| 2 · cuarentena | Solo consume `workflow_state == RESPONDIDA`. **Jamás** `PENDIENTE_APROBACION_HUMANA` |
| 2 + 3 | Si la glosa vino del Auto-Pilot, exige una fila `LIBERADA_POR_HUMANO` en `auto_pilot_bitacora`. **Sin clic humano, no se radica** |
| 3 · bitácora inmutable | `radicaciones_eps` es su equivalente: se inserta, no se edita la evidencia |
| 9 · botón condicionado | Se replica en el servidor: un dictamen con hallazgo grave o confianza bajo umbral **no entra a la cola** |
| 11 · una sola puerta | El radicador se despacha solo por `bots_hus` + agente; nunca a lo crudo |

**Escudo nuevo (nº 13) — no radicar un dictamen obsoleto.** Si se cargaron
tarifas o contratos después de `dictamen_generado_en`, la fila va a
`HUMANO_REQUERIDO` en vez de radicarse.

---

## 10) Alcance de la primera entrega

**Dentro:** la tabla `radicaciones_eps` con su migración, el router de despacho,
el estado `RADICADA_EN_EPS` con sus transiciones, y el primer script headless
**exclusivo para COOSALUD** como prueba de concepto, con el piloto de 1 factura.

**Entregado en la segunda fase (04-09-2026):** la bandeja «En espera de EPS»
con sus botones de resolución, y los radicadores de SIMED y Mutual Ser sobre
un módulo común (`tools/radicador_comun.py`).

---

## 11) Dos correcciones que salieron al construir

**1. Mutual Ser SÍ pide reCAPTCHA.** La matriz lo clasificó como «usuario y
contraseña», pero el bot de respuestas que ya existía entra con
`login_interactivo(...timeout_captcha_s=240)`: una persona resuelve el captcha
y la sesión queda guardada. Un radicador headless **no puede** pasar eso en
frío. Se implementó de la forma honesta:

- con **sesión sembrada válida** → radica solo, escondido;
- **sin ella** → marca `HUMANO_REQUERIDO` con el motivo y dice cómo entrar.

No se promete autonomía donde no la hay, ni siquiera cuando la matriz lo dijo.

**Corrección del 04-09-2026 (tarde).** La primera versión solo sabía leer una
sesión guardada (`storage_state`), y ese es justamente el camino que el propio
repositorio advierte como poco fiable: al lanzar el navegador desde Playwright,
reCAPTCHA lo detecta como automatizado y **se niega a validar**. Es decir, el
radicador quedaba colgando del único camino que suele fallar.

Ahora el camino preferente es **`--cdp`**: el auditor abre SU Chrome con el
puerto de depuración, entra al portal a mano —resolviendo el captcha como una
persona— y el bot se engancha a esa pestaña. reCAPTCHA nunca ve un robot porque
nunca lo hubo en el login.

```
chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\temp-notas\zonaser-chrome"
py tools/radicar_glosas_mutual_ser.py --cdp http://127.0.0.1:9222
```

Dos detalles que no son adorno:

- **Ese Chrome es del auditor y no se cierra** al terminar (`cerrar` es un
  no-op en modo CDP). Cerrarle el navegador a alguien a mitad de su trabajo
  sería inaceptable.
- **Enganchado pero sin sesión, no se pulsa nada.** Si la pestaña no tiene el
  portal abierto, el radicador levanta `SesionNoDisponible` en vez de empezar a
  hacer clics a ciegas — la misma doctrina del cortacircuito OCR.
- En Windows «localhost» resuelve a IPv6 y Chrome escucha en IPv4: el helper
  prueba `127.0.0.1` solo. Ese tropiezo ya costó tiempo una vez.

**2. «Radicar» aquí significa CERRAR, no redactar.** Los tres bots reutilizan
el paso final del portal —`terminar_respuesta` en COOSALUD, `enviar_finalizar`
en SIMED, `solo_finalizar` en Mutual Ser—, que **cierra una respuesta ya
cargada**. Escribir la respuesta en el portal sigue siendo trabajo de los bots
`responder_glosas_*`. El libro de radicación cubre el cierre y su evidencia.
