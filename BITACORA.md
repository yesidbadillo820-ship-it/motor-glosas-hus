# BITÁCORA DE TRABAJO — Automatización de Glosas HUS

> **Qué es este archivo.** Es la *memoria común* del trabajo. Cualquier chat de Claude
> Code debe **leer esto primero** para saber en qué vamos, y al terminar el día debe
> **anotar acá** lo que se hizo, lo que quedó pendiente y lo que sigue. Está escrito en
> lenguaje sencillo, pensado para el área de Cartera / Auditoría de Cuentas Médicas.

**Entidad de trabajo actual:** MUTUAL SER EPS — portal Zona Ser
(`portalzonaser.mutualser.com`), módulo *Auditoría de Cuentas Médicas → Gestión de
Respuestas de Glosas*.
**Rama de git donde vive el trabajo:** `claude/mutual-ser-glosa-responses-fa4k2g`
(Pull Request #154, en borrador).

---

## ¿Qué hace esta herramienta, en pocas palabras?

Responder las glosas de una factura a mano es lento: por **cada** ítem hay que entrar al
portal, escribir el valor, pegar un texto largo, subir el PDF y enviar. Construimos dos
ayudas que hacen ese trabajo casi solo:

1. **Extractor** — lee el PDF de "Trámite de Objeción" y arma un Excel con la respuesta
   lista.
2. **Robot de carga** — toma ese Excel y **diligencia y envía** la subsanación en el
   portal, dejando evidencia (foto) de cada envío.
3. **Conversor a formato interno** — convierte el Excel de objeciones del portal al
   formato que pide el sistema interno de cartera del HUS (columnas "CRO*").

---

## RESUMEN DE LO YA HECHO (por fecha)

### 01/07/2026 — Se construyó el robot de MUTUAL SER
- Se estudió el portal Zona Ser y se documentó el flujo real de subsanación.
- Se creó el **extractor de PDF** (`extraer_respuestas_glosa_mutualser.py`): lee el
  "Trámite de Objeción" y arma el Excel de respuestas. Se verificó que los totales
  cuadran **al peso** contra los PDF oficiales:
  - HUS0000492542 → 185 objeciones / **$37.379.742** (exacto).
  - HUS0000510639 → 18 objeciones / **$2.482.335** (exacto).
- Se creó el **robot de carga** (`responder_glosas_mutual_ser.py`). Para no chocar con
  el reCAPTCHA, el robot se conecta al Chrome que la persona ya tiene abierto y con
  sesión iniciada.
- Se resolvieron los detalles del portal: la ventana de observación, las sub-filas de
  cada ítem, y el caso de los insumos (tecnología 799) que traen **dos glosas por ítem**.
- **Primer envío real exitoso:** la factura **HUS0000510639** quedó subsanada y
  **enviada por el robot** (21 glosas, en ~5 minutos), con su evidencia.
- La factura **HUS0000492542** (la grande, 185 objeciones) quedó **llenada** en el
  portal.

### 02/07/2026 — Se optimizó y se agregó seguridad
- Revisión de código: el robot quedó **más rápido** (menos esperas muertas) y **más
  robusto** para procesar muchas facturas seguidas.
- Controles de seguridad nuevos:
  - **Verifica el código de subsanación (RE9901) antes de enviar** y se detiene si no
    coincide (evita mandar un código equivocado).
  - Toma una **foto justo antes de enviar** como prueba de lo que se mandó.
  - **No envía** una factura si detecta datos inconsistentes.
  - Deja un **reporte** del estado de cada factura.

### 21/07/2026 — Formato interno y presentación a gerencia
- Se creó el **conversor a formato interno** (`objeciones_a_formato_interno.py`): toma
  el Excel de "Objeciones de glosa" bajado del portal y lo pasa al formato del sistema
  interno (columnas CRO*). Se generó **OBJECIONES_HUS520567** (84 objeciones).
- Se armó un **informe para gerencia** (antes vs. ahora) mostrando la efectividad:
  ~9× más rápido, extracción exacta al peso, evidencia automática.
- Se revisó una falla de las pruebas automáticas (CI): son **pruebas viejas de otra
  parte del sistema con fechas fijas**, ajenas a este trabajo; no requieren acción de
  nuestro lado.

### 22/07/2026 — Memoria común y entrega técnica
- Se creó la **BITÁCORA** (este archivo) y el **CLAUDE.md** para que cualquier chat lea
  primero la memoria común y la actualice al terminar.
- Se redactó la **documentación técnica oficial del módulo**
  (`docs/MODULO_GLOSAS_MUTUAL_SER.md`): 17 secciones con objetivo, arquitectura,
  funciones, flujo, riesgos, decisiones y recomendaciones para fusionarlo al proyecto
  principal sin perder trabajo.

---

## PENDIENTE (lo que falta)

- **Cerrar HUS0000492542:** ya está llena en el portal; falta darle el **envío final**.
  Se hace con la opción `--solo-finalizar` (no vuelve a llenar, solo elige el código y
  envía).
- **Confirmar el formato interno (CRO*):** revisar con el sistema interno si el campo de
  observación (`CRDOBSERV`) necesita el `$valor` al final, y poner la **fecha real** de
  la objeción (hoy se usó una fecha de ejemplo).
- **Lote masivo de MUTUAL SER:** correr el resto de las facturas glosadas de una sola
  vez (opción `--todas`, con los soportes).
- **(Opcional)** Generar el "formato del bot" para HUS520567 si se va a responder esa
  factura en el portal.

---

## PARA MAÑANA (lo próximo a trabajar)

1. **Enviar HUS0000492542** con `--solo-finalizar` y guardar la evidencia
   (`HUS0000492542_pre_envio.png` debe mostrar **RE9901 SUBSANADA TOTAL**).
2. **Convertir a formato interno** las facturas nuevas de objeciones que lleguen, con el
   conversor, ajustando la fecha real.
3. **Arrancar el lote masivo** de MUTUAL SER una vez confirmadas 1 o 2 facturas más.

---

## Archivos clave (dónde está cada cosa)

| Archivo | Para qué sirve |
|---|---|
| `tools/extraer_respuestas_glosa_mutualser.py` | PDF Trámite de Objeción → Excel de respuestas |
| `tools/responder_glosas_mutual_ser.py` | Robot que llena y envía la subsanación en el portal |
| `tools/objeciones_a_formato_interno.py` | Excel de objeciones del portal → formato interno CRO* |
| `docs/CONTEXTO_MUTUAL_SER.md` | Notas técnicas del flujo del portal de MUTUAL SER |

> El repo también tiene herramientas para otras EPS ya trabajadas antes: **Coosalud**,
> **Simed** y **Dispensario (DGH)**.

## Reglas que no se deben romper
- **Nunca** guardar usuarios ni contraseñas en el código (solo en variables de entorno).
- **Siempre** hacer una prueba pequeña (piloto) antes de un envío masivo.
- Antes de enviar, verificar que el código sea **RE9901 SUBSANADA TOTAL** (rechazo total).
