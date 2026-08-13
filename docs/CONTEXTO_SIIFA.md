# Contexto HUS SIIFA — Guía para iniciar un nuevo chat

> **Cómo usar este archivo:** pegá su contenido completo como primer mensaje en
> un nuevo chat de Claude Code y el asistente va a tener todo el contexto del
> proyecto para retomar el trabajo de SIIFA desde donde quedó.

---

## 1) Qué es SIIFA

**SIIFA** (Sistema Integral de Información Financiera y Asistencial) es la
plataforma **del Ministerio de Salud y Protección Social** (no del HUS, no de
una EPS) donde a partir de 2025-2026 se registran, de forma centralizada para
todo el sector salud:

- **Módulo 1 — Contratación:** contratos entre ERP (EPS) e IPS (prestadores).
- **Módulo 2 — FEV-RIPS:** facturación electrónica de venta y RIPS.
- **Módulo 3 — Seguimiento de facturas:** devoluciones, **glosas** y pagos.

**NO es lo mismo que COOSALUD (vco.ctamedicas.com), SIMED (Dispensario) ni
Dinámica Gerencial (DGH).** Esos son portales propios de cada pagador. SIIFA es
el sistema **del Ministerio**, obligatorio para todas las EPS/ERP y todos los
prestadores (IPS), donde las EPS reportan las glosas y el HUS (como IPS) debe
responderlas — además de lo que se responda en el portal propio de cada EPS.

El HUS entra como rol **IPS** (NIT 900006037-4).

## 2) La pantalla de la que parte este proyecto

`Seguimiento → Listar seguimientos` muestra una tabla paginada (25/página) de
todas las glosas del HUS: No. de seguimiento, tipo (GLOSA), valor, factura
HUS, NIT emisor (EPS), NIT adquiriente, fecha. **A julio de 2026 hay 2.579
registros y el portal no tiene botón de exportar** — de ahí nacen los dos
pedidos de este proyecto:

1. **Ver las 2.579 facturas/glosas en un informe masivo** (Excel), no de a 25
   en 25 → resuelto con `tools/siifa_reporte_seguimientos.py`.
2. **Un bot tipo COOSALUD que ayude a cargar las respuestas** → resuelto con
   `tools/responder_glosas_siifa.py`.

## 3) Diferencia clave con los bots COOSALUD/SIMED: SIIFA tiene API oficial

Los bots de COOSALUD y SIMED son robots de navegador (Playwright) porque esos
portales no ofrecen otra vía. **SIIFA sí publica una API REST oficial** para
el módulo de Seguimiento (interoperabilidad), documentada en los manuales que
el auditor subió (`siifa-api-modulo2y3-*.html`, colección Postman, manual de
interoperabilidad FEV-RIPS). Por eso **los dos scripts de SIIFA NO abren
navegador: hablan directo con la API por HTTPS.** Es más rápido, más
confiable (no depende de que cambie un botón en la pantalla) y es lo que el
Ministerio recomienda ("preferiblemente por interoperabilidad" aparece
repetido en el manual funcional del módulo 3, para cada paso del trámite de
glosa).

### 3.1 URL base y autenticación

Las tres URLs están **CONFIRMADAS** (verificadas contra la propia configuración
de la aplicación web de SIIFA, que declara `apiSeguridad`, `apiFactura` y
`apiContrato`, y comprobadas contra el servidor real):

| Servicio | URL base |
|---|---|
| Seguridad (login) | `https://siifa.sispro.gov.co/siifa-seguridad` |
| Factura / Seguimiento | `https://siifa.sispro.gov.co/siifa-factura` |
| Contratación | `https://siifa.sispro.gov.co/siifa-contrato` |

- **Login:** `POST {seguridad}/api/Auth/login` con body
  `{"userName": "...", "password": "..."}` devuelve
  `{"success": true, "token": "<JWT>", "errors": [...]}`. Ese JWT se manda en
  cada llamado como `Authorization: Bearer <token>`.
- Se pueden sobrescribir con `SIIFA_AUTH_URL` y `SIIFA_BASE_URL`, pero en
  condiciones normales **no hace falta tocar nada**.
- El **usuario y contraseña son los mismos con los que el auditor entra al
  portal SIIFA** (cuenta registrada en Mi Seguridad Social / SISPRO). Nunca
  se escriben en el código: siempre variables de entorno.

  ```powershell
  setx SIIFA_USER <usuario_sispro>
  setx SIIFA_PASSWORD <password>
  ```
  (cerrar y reabrir PowerShell para que las tome).

### ⚠️ El token VENCE — y ese es el error que más tiempo cuesta

El JWT dura pocos minutos. Un programa que pida el token **una sola vez al
arrancar** funciona las primeras páginas y después falla TODO con 401, sin
recuperarse nunca. El síntoma es inconfundible: *"las primeras 7 páginas bien,
de la 8 en adelante todas mal"*.

Reintentar no arregla nada (el token ya está muerto) y encima hace perder
muchísimo tiempo si el programa duerme entre reintentos. `tools/siifa_client.py`
**detecta el 401 y se vuelve a autenticar solo**, y sólo reintenta lo que tiene
sentido reintentar (caídas de red, 429, 5xx); un error definitivo lo informa de
una, sin dormir.

### 3.2 Roles y alcance de los datos

El JWT trae el rol y el NIT de la entidad (`NitEntidad`). Con rol
**SIIFA_IPS** o **SIIFA_IPS_Gestor** (el del HUS), la API **filtra
automáticamente** por el NIT del HUS — no hace falta (ni se puede) pedir
datos de otra entidad. Con ese rol se puede: **consultar** todos los
seguimientos donde el HUS es el emisor, y **responder** glosas
(`SIIFA_IPS_Consulta` solo puede leer, no responder).

### 3.3 Endpoints que usan los dos scripts

| Endpoint | Uso |
|---|---|
| `POST /api/Auth/login` | Login, devuelve el JWT. |
| `GET /api/SeguimientoFactura/List` | Lista paginada y consolidada de **todos** los seguimientos (glosas y devoluciones) del HUS — hasta 1.500 registros por página. Es la que arma el informe masivo. |
| `GET /api/SeguimientoTipoCodigo/ByGrupo?Grupo=RESPUESTA` | Catálogo oficial de códigos de respuesta válidos (Tabla 1.4, Anexo Técnico 3, Res. 2284/2023) — el bot valida contra esto antes de mandar nada. |
| `GET /api/SeguimientoTipoCodigo/ByGrupo?Grupo=GLOSA` | Catálogo de causales de glosa (para entender qué te están glosando). |
| `PUT /api/SeguimientoFacturaGlosa/Respuesta` | **Responde una glosa.** Body: `idSeguimientoFacturaGlosa`, `idSeguimientoTipoCodigoRespuesta`, `fechaRespuesta`, `observacionRespuesta` (opcional). Roles permitidos: `SIIFA_Admin`, `SIIFA_IPS`, `SIIFA_IPS_Gestor`, `SIIFA_FITS`, `SIIFA_FITS_Gestor`. |
| `PUT /api/SeguimientoFacturaGlosa/Reiteracion` | Reitera una glosa (lo usa la ERP, no el HUS — se deja documentado por completitud). |
| `PUT /api/SeguimientoFacturaGlosa/ReiteracionRespuesta` | Responde la reiteración de una glosa no levantada (subsanación) — **este sí lo usa el HUS**, mismo flujo que `Respuesta` pero un paso más adelante del trámite. |
| `GET /api/SeguimientoFacturaGlosa/Resumen/ByIdFactura/{IdFactura}` | Resumen (conteos) de glosas de una factura puntual — útil para verificar antes/después de un cargue. |

Las validaciones automáticas del `PUT .../Respuesta` que hay que respetar:
- El `idSeguimientoTipoCodigoRespuesta` debe existir en el catálogo, estar
  **activo** y pertenecer al grupo **RESPUESTA**.
- `fechaRespuesta` debe ser **posterior** a la fecha de formulación de la
  glosa (no se puede responder "antes" de que la EPS la formuló).

## 4) Plazos del trámite de glosa en SIIFA (Res. 1962/2025 y Ley 1438/2011, Art. 57)

| Etapa | Responsable | Plazo |
|---|---|---|
| Formulación y comunicación de todas las glosas de la factura | ERP (EPS) | 20 días hábiles desde la radicación |
| **Respuesta del HUS a la glosa** | **HUS** | **15 días hábiles** después de formulada/comunicada |
| Decisión inicial (levanta o reitera) | ERP | 10 días hábiles después de la respuesta |
| **Subsanación de glosa no levantada** (si el HUS insiste) | **HUS** | **7 días hábiles** después de la decisión inicial |
| Decisión/respuesta final y pago de lo aceptado | ERP | 5 días hábiles después de la subsanación |

En todos los pasos: **"preferiblemente por interoperabilidad o a más tardar
durante las siguientes 48 horas hábiles"** hay que registrar la actuación en
SIIFA — es decir, aunque el HUS ya haya respondido la glosa en el portal
propio de la EPS (COOSALUD, etc.), **hay que registrar esa misma respuesta en
SIIFA también, dentro de esas 48 horas**. Son trámites paralelos, no
sustitutos uno del otro.

Si la glosa queda reiterada (la EPS no la levanta) y el HUS reconoce que
tiene razón, el trámite es: nota crédito por el valor de la glosa, validada
por el mecanismo único de validación FEV-RIPS — no se responde en SIIFA como
"aceptada", se corrige por nota crédito.

## 5) Herramientas de este repo

- **`tools/siifa_client.py`** — cliente compartido (login + JWT + llamadas a
  la API). No se usa solo; lo importan los otros dos scripts.
- **`tools/siifa_reporte_seguimientos.py`** — trae **todos** los seguimientos
  del HUS (paginando automáticamente) y arma un Excel con una fila por
  glosa/devolución: factura, EPS, valor, código y descripción de la glosa,
  fecha de formulación, si tiene respuesta o no, código/observación/fecha de
  la respuesta si ya existe. Incluye una hoja de resumen (totales por EPS, por
  "con/sin respuesta", valor total glosado).
- **`tools/responder_glosas_siifa.py`** — lee un Excel tipificado por el
  auditor (mismo criterio de columnas que el bot COOSALUD) y llama a la API
  para registrar la respuesta de cada glosa. Genera un CSV de reporte
  (OK/ERROR por fila) para poder reintentar solo lo que falló, igual que el
  bot COOSALUD.
- **`tools/siifa_novedades.py`** — compara el informe recién bajado contra el
  de la revisión pasada y dice **qué llegó nuevo**: entidad, factura, si es
  glosa o devolución, valor y causal. El portal muestra el total («2.620
  registros») pero no cuáles son nuevos, y buscarlos a mano son 175 páginas.
  Sin informe anterior a la mano, lista lo que está sin responder.
- **`tools/siifa_estado_tramite.py`** — en qué etapa va cada glosa de las
  cinco del panel «Avance de auditoría», y **a quién le toca mover**. Separa
  lo ganado (glosa levantada), lo que espera a la EPS, lo que espera al
  hospital y lo que ya se venció. El portal muestra ese panel de a una
  factura; esto lo hace para las 2.600 de una vez.
- Ver `tools/README_siifa.md` para los comandos PowerShell listos para
  copiar/pegar.

### La etapa 4 es la trampa: 7 días hábiles para subsanar

Cuando la EPS **reitera** una glosa (no la levanta), al hospital le quedan
**7 días hábiles** para subsanar — menos de la mitad que los 15 de la primera
respuesta— y **nadie avisa**: hay que ir a mirar el portal. Una glosa
reiterada que no se subsana queda en firme. Por eso `siifa_estado_tramite.py`
saca de primero lo que le toca al hospital, con su fecha de vencimiento.

Los códigos de decisión vistos en la API (05 y 13-08-2026):

| Código | Significa | Quién sigue |
|---|---|---|
| `GTL002` | Glosa totalmente levantada | nadie — **ganada** |
| `GRE003` | Glosa reiterada | **el hospital**, 7 días hábiles |
| `DRE003` | Devolución reiterada | **el hospital**, 7 días hábiles |

La clasificación se hace por la **descripción** («levantada» / «reiterada»),
no por el código: esa lista puede crecer y el texto es lo estable. Una glosa
levantada **parcialmente** no se da por ganada — el resto sigue vivo y hay que
subsanarlo.

### El valor de una devolución NO se suma línea por línea

Una **glosa** objeta un ítem y trae el valor de ese ítem: los ítems se suman.
Una **devolución** rechaza la factura entera, y SIIFA **repite el valor de la
factura en cada una de sus líneas**. Sumar esas líneas multiplica la plata:
las 1.340 líneas de SANITAS dan **$24.917 millones** cuando esas 9 facturas
valen **$111 millones** —224 veces más—. En cualquier informe, el valor de una
devolución se cuenta **una sola vez por factura**.

## 5.quater) Glosas y devoluciones NO se responden por el mismo lado

Confirmado contra la API el 05-08-2026, después de que SIIFA rechazara 495
respuestas diciendo «el código no existe, no está activo o no pertenece al
grupo RESPUESTA»:

| | Glosa | Devolución |
|---|---|---|
| Endpoint | `PUT /api/SeguimientoFacturaGlosa/Respuesta` | `PUT /api/SeguimientoFacturaDevolucion/Respuesta` |
| Campo del id en el cuerpo | `idSeguimientoFacturaGlosa` | `idSeguimientoFacturaDevolucion` |
| Causales (catálogo) | grupo `GLOSA`, 339 códigos | grupo `DEVOLUCION`, 11 códigos (DE1601, DE5601…) |

**El identificador es EL MISMO.** El listado devuelve un solo campo,
`idSeguimientoFactura`, tanto para glosas como para devoluciones; cada
controlador lo nombra a su manera en el cuerpo de la petición. Lo verificado
en el volcado crudo de la factura HUS494196: un seguimiento tipo DEVOLUCION
trae `idSeguimientoFactura`, `tipoSeguimiento` y `idSeguimientoTipoCodigo`
(DE5601), y ningún `idSeguimientoFacturaDevolucion`.

El bot elige la puerta por la columna TIPO del Excel de cargue. Para ver los
campos tal cual los manda la plataforma:

```powershell
py tools\siifa_sondear_endpoints.py --factura HUS494196
```

### Los códigos de respuesta a una DEVOLUCIÓN

El grupo del catálogo se llama **`RESPUESTA_DEV_PTS_PSS`** —lo dijo la propia
API al rechazar una respuesta con un código de glosa—. Son tres:

| Código | Qué dice |
|---|---|
| `RE9501` | La devolución **no procede** por haber sido generada fuera de los términos establecidos por la norma, configurándose la **aceptación tácita** de la factura de venta. |
| `RE9601` | El PSS o PTS aporta a la ERP la evidencia que demuestra que la devolución es **injustificada al 100%**. |
| `RE9701` | El PSS o PTS informa a la ERP que la devolución ha sido **aceptada al 100%**. |

Para verlos:

```powershell
py tools\responder_glosas_siifa.py --listar-catalogo RESPUESTA_DEV_PTS_PSS
```

Cuál usar, según lo que diga el texto de la respuesta:

- el hospital **acepta** la devolución (nota crédito) → `RE9701`;
- el hospital **no acepta** y aporta la evidencia → `RE9601`;
- la EPS devolvió **fuera de su propio plazo** → `RE9501`, que es el más
  fuerte porque implica aceptación tácita de la factura. Exige comparar
  fechas caso a caso, así que el motor no lo pone solo.

**Un código de glosa NO sirve para una devolución.** RE9901 —el que usa el
motor para no aceptar una glosa— hace que SIIFA rechace la respuesta con
«no pertenece al grupo RESPUESTA_DEV_PTS_PSS».

## 5.ter) Cómo se responde A MANO en el portal (guía del auditor, 03-08-2026)

Es el procedimiento que el bot replica por API. Sirve para el piloto, para
reponer una glosa suelta y para entender qué campos exige la plataforma.

1. Entrar a <https://siifa.sispro.gov.co/auth/login> con usuario y contraseña.
2. Menú **Seguimiento → Listar seguimientos**.
3. En **Filtros**, escribir el número de factura y dar **Filtrar**.
4. Revisar que los datos de la fila (factura, valor, tipo) sean los de la
   glosa que se va a responder. Todo lo que se digite debe concordar.
5. En los **tres puntos** de la fila → **Responder**.
6. Se llenan **tres** campos y se da **Guardar**:
   - **Código de respuesta** (lista desplegable),
   - **Observación** (el texto de la respuesta),
   - **Fecha de respuesta**.
7. Sale el aviso «Se guardó exitosamente» — esa es la evidencia de que quedó.
8. Otra vez los tres puntos → **Ver Histórico**: muestra la formulación de la
   glosa y debajo la respuesta con su código y su fecha. Pantallazo de esa
   pantalla: es la evidencia que se anexa al PDF de soportes.

**La fecha de respuesta es la del día en que el hospital respondió de verdad
(la que trae DGH), NO la de hoy.** Es el punto más delicado de todo el cargue:
si una respuesta que el HUS dio en mayo se sube con la fecha de hoy, en el
histórico de SIIFA queda registrada meses después de la glosa —es decir, fuera
del término del artículo 57 de la Ley 1438 de 2011— y eso es lo primero que
mira la EPS en la conciliación. Por eso los archivos de cargue llevan la
columna `FECHA_RESPUESTA`, que el bot manda tal cual: viene llena con la fecha
de DGH en las respuestas que el hospital ya había dado, y vacía en las que se
están respondiendo hoy (ahí el bot pone la de hoy, que es la correcta).

Del piloto manual del 03-08-2026 (factura HUS497119, seguimiento 3852611,
glosa TA2301 por $308.905): quedó registrada con código **RE9702** y fecha
**11/05/2026**, que es la que traía DGH. Al digitar la hora a mano quedó
23:17 en vez de 12:17 — la fecha del día, que es lo que cuenta para el
término, quedó bien.

## 5.bis) Si "se queda pensando" y no saca la información

Corré primero el diagnóstico, que revisa paso a paso conexión, credenciales y
consulta:

```powershell
py tools\siifa_reporte_seguimientos.py --diagnostico
```

Causas conocidas, en orden de frecuencia:

| Síntoma | Causa | Solución |
|---|---|---|
| Anda un rato y después **fallan todas** las páginas | El token venció | Ya resuelto: el cliente se re-autentica solo. Si usás otro programa, hacelo re-autenticar ante un 401. |
| Tarda muchísimo y no muestra nada | Reintentos con esperas largas sobre un error permanente | Ya resuelto: sólo se reintenta lo reintentable. |
| Trae filas pero **todas vacías** | La API devolvió los campos con otra capitalización | Ya resuelto: `buscar_clave()` acepta ambas formas. |
| Nunca termina | La API ignora el número de página → bucle infinito | Ya resuelto: se detecta la página repetida y se corta. |
| Falla al instante sin conectar | Sin internet / proxy del hospital bloqueando | Revisar red; el error ahora lo dice explícito. |

**Regla de eficiencia importante:** `GET /api/SeguimientoFactura/List` ya trae
anidados el número de factura, el valor y los datos de emisor y adquiriente
(la EPS). **No hace falta consultar `/api/Factura/{id}` por cada seguimiento** —
eso convierte 13 llamadas en más de 2.500 y es la causa típica de que un
proceso tarde horas. Todo lo que necesita el informe ya viene en el listado.

## 6) Reglas que el asistente NO debe romper

1. **Nunca confundir SIIFA con COOSALUD/SIMED/DGH.** SIIFA es del Ministerio,
   aplica a todas las EPS a la vez; los otros son portales propios de cada
   pagador. Responder en uno no reemplaza responder en el otro.
2. **Nunca commitear usuario ni contraseña.** Siempre `SIIFA_USER` /
   `SIIFA_PASSWORD` por variable de entorno.
3. **Nunca incluir el identificador del modelo** en commits, PRs o código.
4. **Antes de un cargue masivo, correr `--piloto` (1 sola glosa)** — la
   regla general del repo aplica también acá, y con más razón porque la URL
   del servicio de Auth no está 100% confirmada.
5. **Antes de dar por roto el acceso, correr `--diagnostico`** — dice en qué
   paso exacto falla (conexión, credenciales o consulta).
6. **Claude Code no tiene acceso al portal SIIFA ni a la red del HUS:** para
   correr estos scripts, entregar el comando PowerShell listo y pedir la
   salida al auditor (igual que con los demás bots).
