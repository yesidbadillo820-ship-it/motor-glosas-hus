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

- **Base de la API de Factura/Seguimiento (confirmada, producción):**
  `https://siifa.sispro.gov.co/siifa-factura`
- **Login:** `POST /api/Auth/login` con body `{"userName": "...", "password": "..."}`
  devuelve `{"success": true, "token": "<JWT>", "errors": [...]}`. Ese JWT se
  manda en cada llamado como `Authorization: Bearer <token>`.
- **⚠️ URL base del servicio de Auth/Seguridad: NO está confirmada en los
  manuales que tenemos.** Los scripts la piden por variable de entorno
  `SIIFA_AUTH_URL` — si no se conoce, hay que pedirla a la mesa de ayuda SIIFA
  o revisar el enlace de "Autenticación" del micrositio
  (https://www.minsalud.gov.co/SIIFA). Con la misma convención de nombres que
  usa `siifa-factura`, lo más probable es que sea `https://siifa.sispro.gov.co/siifa-seguridad`,
  pero **eso es una hipótesis, no un dato confirmado — probar primero con
  `--piloto` de una sola glosa antes de confiar en el resultado.**
- El **usuario y contraseña son los mismos con los que el auditor entra al
  portal SIIFA** (cuenta registrada en Mi Seguridad Social / SISPRO), según
  el flujo de autenticación descrito en el manual de interoperabilidad. Nunca
  se escriben en el código: siempre variables de entorno.

  ```powershell
  setx SIIFA_USER <usuario_sispro>
  setx SIIFA_PASSWORD <password>
  ```
  (cerrar y reabrir PowerShell para que las tome).

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
- Ver `tools/README_siifa.md` para los comandos PowerShell listos para
  copiar/pegar.

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
5. **La URL de autenticación (`SIIFA_AUTH_URL`) es una hipótesis, no un
   dato verificado** — si el login falla, lo primero es confirmar esa URL
   antes de sospechar de las credenciales.
6. **Claude Code no tiene acceso al portal SIIFA ni a la red del HUS:** para
   correr estos scripts, entregar el comando PowerShell listo y pedir la
   salida al auditor (igual que con los demás bots).
