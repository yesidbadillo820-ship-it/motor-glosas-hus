# Contexto HUS MUTUAL SER — Respuesta de Glosas (portal Zona Ser)

> **Cómo usar este archivo:** pegá su contenido como primer mensaje en un nuevo chat
> de Claude Code y el asistente tendrá el contexto del flujo de **RESPUESTA DE
> GLOSAS de MUTUAL SER** desde donde quedó.

---

## 1) Quién soy y qué hago

- Soy auditor de cartera del **Hospital Universitario de Santander** (HUS,
  NIT 900006037-4), Bucaramanga, Colombia.
- Tarea: **responder glosas** que la EPS **MUTUAL SER** impone a las facturas del
  HUS, en su portal web.
- Trabajo en Windows con PowerShell.

## 2) Plataforma

- MUTUAL SER usa el portal **Zona Ser**: `https://portalzonaser.mutualser.com`.
- Módulo: **AUDITORIA DE CUENTAS MEDICAS → GESTIÓN DE RESPUESTAS DE GLOSAS →
  CONSULTAR CUENTAS MÉDICAS GLOSADAS**.
- **NO confundir con COOSALUD (`vco.ctamedicas.com`) ni con SIMED/Dispensario
  (`auditool25.tool.com.co`) ni con DGH (escritorio).** Son plataformas distintas.
- ⚠ **El login tiene reCAPTCHA** ("No soy un robot"). Es la mayor diferencia con
  COOSALUD/SIMED (que no lo tenían) — ver §6.

## 3) Repositorio y credenciales

- **Repo:** `motor-glosas-hus`. Branch de trabajo: `claude/mutual-ser-glosa-responses-fa4k2g`.
- **Credenciales SIEMPRE en variables de entorno**, nunca en el código ni en el
  historial de comandos:

  ```cmd
  setx MUTUALSER_USER  <correo institucional de gerencia>
  setx MUTUALSER_PASSWORD  <contraseña>
  ```

  Después cerrar y reabrir la terminal para que las tome.

## 4) Pipeline de respuesta (2 pasos)

```
PDF "Trámite de Objeción" (CRRPTramiteObjecion, uno por factura, generado en DGH)
    │
    ├─ 1. extraer_respuestas_glosa_mutualser.py
    │       → lee el/los PDF y genera Excel con 1 fila por objeción/ítem
    │
    └─ 2. responder_glosas_mutual_ser.py
            → recorre cada factura en el portal y carga la respuesta
```

### Paso 1 — `tools/extraer_respuestas_glosa_mutualser.py`

Lee los PDF de Trámite de Objeción y produce un Excel con columnas:

| Columna | Uso |
|---|---|
| `Factura` | HUS0000XXXXXX |
| `# Objeción` | 1, 2, 3, … (orden de aparición) |
| `Código Glosa` | código de 6 chars del Manual Único de Glosas (ej. `CL0101`, `TA0201`, `FA0802`) |
| `Código Respuesta` | `RE9901` (código de respuesta del prestador) |
| `Servicio` | descripción del servicio glosado |
| `Valor Objetado` | valor que MUTUAL SER objetó |
| `Valor Aceptado` | valor que el HUS acepta (normalmente **$0** = rechazo total) |
| `Detalle Respuesta` | texto de la respuesta del HUS (campo "Observaciones:" del PDF) |

Detalles de parseo (verificados contra los totales oficiales de los PDF):
- El PDF trae la tabla `CONCEPTO OBJECIÓN | CONCEPTO RESPUESTA | SERVICIO |
  VALOR OBJETADO | VALOR ACEPTADO`. pdfplumber parte los códigos por el ancho de
  columna: el 6º dígito cae al inicio de la línea siguiente (`CL010`+`1` = `CL0101`;
  `RE990`+`1` = `RE9901`). El extractor reconstruye ambos.
- El texto de "Observaciones:" se limpia del pie/encabezado de página que se cuela
  cuando una objeción cruza un salto de página, así todos los ítems con la misma
  respuesta quedan **idénticos** (clave para la respuesta masiva).

```cmd
py tools\extraer_respuestas_glosa_mutualser.py ^
    --carpeta "D:\...\MUTUALSER\SOPORTES" ^
    --salida  "D:\...\respuestas_mutualser.xlsx"
```

### Paso 2 — `tools/responder_glosas_mutual_ser.py`

Bot Playwright (mismo patrón que COOSALUD/SIMED). Estado **v0 (andamiaje +
calibración)**:

- ✅ **Login con reCAPTCHA vía sesión persistida**: con `--con-cabeza` el humano
  resuelve el captcha UNA vez; el bot guarda la sesión (`--storage-state`, default
  `mutualser_session.json`) y la reutiliza sin captcha en las corridas siguientes.
- ✅ **Lector del Excel** (columnas del extractor) y **agrupación por
  (código respuesta + texto)** — en glosa ratificada TODOS los ítems comparten
  `RE9901` + el mismo texto → **1 solo grupo por factura** (respuesta masiva).
- ✅ **Modo `--explorar`**: navega al módulo y **vuelca el DOM** (inputs, botones,
  selects, cabeceras de la grilla) + screenshot, para calibrar los selectores reales
  (equivalente web del `dump_dg.py` de DGH).
- ✅ Reporte CSV incremental, logging, screenshots.
- ⏳ **Falta calibrar (marcado `# TODO(portal)`):** selectores de la grilla,
  apertura de factura, formulario de respuesta por glosa y botón de finalizar.

```cmd
REM 1) Calibrar el portal (browser visible, resolver captcha a mano):
py tools\responder_glosas_mutual_ser.py --explorar --con-cabeza

REM 2) Piloto de una factura (reutiliza la sesión guardada):
py tools\responder_glosas_mutual_ser.py --excel respuestas_mutualser.xlsx ^
    --solo HUS0000492542 --con-cabeza

REM 3) Masivo:
py tools\responder_glosas_mutual_ser.py --excel respuestas_mutualser.xlsx --todas ^
    --reporte reporte_mutualser.csv
```

## 5) Conceptos de negocio observados en los PDF de muestra

- **Glosa ratificada:** MUTUAL SER insistió tras la respuesta inicial del HUS. El
  HUS **mantiene su respuesta** y **solicita conciliación** (mesa de auditoría
  médica/técnica; si no hay acuerdo, Supersalud — Art. 57 y 126 Ley 1438/2011).
- **Respuesta uniforme:** en las dos facturas de muestra, TODOS los ítems se
  responden con `Código Respuesta = RE9901`, `Valor Aceptado = $0` (rechazo total) y
  el mismo texto:
  > "ESE HUS NO ACEPTA GLOSA RATIFICADA; SE MANTIENE LA RESPUESTA DADA EN TRÁMITE DE
  > LA GLOSA INICIAL Y SE DA CONTINUACIÓN AL PROCESO… SE SOLICITA LA PROGRAMACIÓN DE
  > LA FECHA DE CONCILIACIÓN… SE DARÁ POR LEVANTADA LA RESPECTIVA OBJECIÓN."
- **Familias de código de glosa** vistas (Manual Único de Glosas): **TA** (tarifas),
  **FA** (facturación), **CL** (pertinencia/calidad). Concuerdan con el banco de
  objeciones del HUS (`scripts/banco_objeciones_glosas_hus.py`).
- **Columnas de la grilla del portal** (a nivel de factura): `FACTURA`,
  `FECHA DE RADICACIÓN`, `VALOR FACTURADO`, `FECHA DE GLOSA`, `VALOR GLOSADO`,
  `CONTRATO`, `FECHA DE RESPUESTA IPS`, `FECHA DE VALIDACIÓN`,
  `FECHA RESPUESTA SUBSANACIÓN`. → El portal modela **dos rondas** (respuesta
  inicial + subsanación). `FECHA DE RESPUESTA IPS` vacía = factura **pendiente**;
  con fecha = **ya respondida** (señal de idempotencia legible desde la grilla).
- **Contratos vistos:** `U22025 - MUTUAL SER EPS` y
  `U22062 - MUTUAL SER ESS EPSS CONTRIBUTIVO` (tercero 806008394).

### Facturas de muestra procesadas (extracción verificada)

| Factura | Objeciones | Valor objetado | Valor aceptado |
|---|---|---|---|
| HUS0000492542 (Trámite 179474, contrato U22025) | 185 | $37.379.742 ✅ | $0 |
| HUS0000510639 (Trámite 179481, contrato U22062) | 18 | $2.482.335 ✅ | $0 |

(✅ = la suma de ítems coincide exactamente con el TOTAL del PDF.)

## 6) Riesgos / decisiones abiertas

1. **reCAPTCHA en el login** (riesgo #1): se maneja con **sesión persistida** +
   login asistido a mano la primera vez. No se usan servicios de resolución de
   captcha de terceros.
2. **Formulario de respuesta:** falta confirmar en el portal si la respuesta se
   carga **glosa por glosa** o **masiva por factura**, qué **códigos de respuesta**
   ofrece el dropdown (¿acepta `RE9901`?), si valida caracteres (tildes/ñ — hay
   `sanitizar()` listo por si acaso) y si permite/exige **adjuntar soportes**.
3. **Doble ronda (respuesta / subsanación):** `FECHA RESPUESTA SUBSANACIÓN` sugiere
   un segundo flujo; confirmar cómo se accede a las facturas en subsanación.
4. **Idempotencia:** leer el estado real de la grilla (`FECHA RESPUESTA IPS`), nunca
   un flag propio; `--saltar-csv`/estados terminales como en COOSALUD (pendiente de
   sumar cuando se calibre el flujo).

## 7) Reglas que el asistente NO debe romper

1. **Nunca confundir MUTUAL SER con COOSALUD / SIMED / DGH.** Plataformas distintas.
2. **Nunca commitear passwords ni usuarios.** Solo en variables de entorno.
3. **Nunca incluir el identificador del modelo** en commits, PRs o código pusheado.
4. **Antes de un masivo, SIEMPRE un piloto** (`--solo HUS<n> --con-cabeza`).
5. **Cuando el usuario diga "SUBE / RESPONDE",** verificar primero que el asistente
   pueda (no tiene acceso al portal ni a Windows); si no, dar el comando para que lo
   corra el usuario.
