# BITÁCORA DE TRABAJO — Motor Glosas HUS

> **Qué es este archivo:** la *memoria común* de todos los chats de Claude Code
> sobre este proyecto. Aunque cada chat es una ventana aparte, todos comparten
> este repositorio; por eso todo lo que se trabaja queda anotado **aquí**, con
> su fecha. Así, en cualquier chat nuevo, se sabe qué se ha hecho, qué falta y
> qué sigue — sin depender de la memoria de la conversación.
>
> **Última actualización:** 2026-07-22

---

## ¿De qué se trata todo esto?

Es un conjunto de **bots** (pequeños programas de **doble clic**, que no
requieren instalar nada ni saber de sistemas) para el área de **auditoría de
cuentas del HUS**. Sirven para pelear y prevenir las **glosas y devoluciones**
de las EPS (sobre todo **Nueva EPS**): preparar la radicación, cruzar la
información, armar los paquetes de soportes, controlar los plazos y dejar todo
documentado.

Todos los bots viven en la carpeta **`tools/`** y se abren desde el menú
**`MOTOR_HUS.cmd`** (un solo doble clic muestra la lista numerada).

---

## RESUMEN RÁPIDO — ¿dónde vamos hoy?

- ✅ **16 bots** funcionando (menú `MOTOR_HUS.cmd`).
- ✅ El más reciente y potente: **`AUDITAR_DEV_EPS`** — audita las devoluciones
  de Nueva EPS cruzando la factura (DGH) con el RIPS (JSON) y los soportes
  (OPF/PDE), valida el trámite **SAT ("Proceso exitoso")** y lee hasta los PDF
  escaneados con **OCR**.
- 🟡 **Pendiente inmediato:** que `AUDITAR_DEV_EPS` también lea el Excel de
  **GLOSAS ACEPTADAS** (tiene otras columnas que el de devoluciones).

---

## LO QUE YA ESTÁ HECHO (de lo más nuevo a lo más viejo)

### 22 de julio de 2026 — Control central del trabajo
- Se creó **esta bitácora** (`BITACORA.md`) y se dejó configurado el `CLAUDE.md`
  para que **todos los chats** la lean al empezar y la actualicen al terminar.
- Se intentó correr `AUDITAR_DEV_EPS` con el Excel *ARCHIVO JUNIO 2026-GLOSAS
  ACEPTADAS.xlsx*: el bot se detuvo porque ese archivo tiene **otra estructura**
  (no es el formato de devoluciones). Queda pendiente adaptarlo — ver más abajo.
- **Se corrigió el CI** que fallaba en el PR: dos pruebas del aplicativo web
  (`test_por_dia_semana`, `test_heatmap_actividad`) **caducaban** por usar fechas
  fijas de abril fuera de la ventana de 90 días. Se anclaron a un lunes reciente.
- **Documento técnico de entrega** del módulo para el equipo principal:
  `docs/ENTREGA_MODULO_KIT_AUDITORIA.md` (arquitectura, funciones, flujos,
  riesgos, pendientes y cómo fusionarlo — reconstrucción completa de esta rama).

### 17 de julio de 2026 — `AUDITAR_DEV_EPS` más completo
- **Validación SAT en el PDE:** cuando la autorización se tramitó por *Mi
  Seguridad Social / SAT*, el bot abre el soporte que siempre se revisa (el
  **PDE**) y confirma que quedó **"Proceso exitoso"**, con su número de novedad.
- **OCR automático:** los PDF que son **solo imagen** (escaneados sin texto) se
  leen con OCR para sacarles la autorización, el documento y la validación SAT.
- **Instalación del OCR a prueba de fallos:** si el instalador rápido no sirve
  en el PC del hospital, el bot **descarga solo** el motor de OCR (Tesseract),
  sin necesidad de administrador.
- **Rutas en el Excel:** ahora agrega dos columnas con la **ruta del JSON** y la
  **ruta de los soportes** de cada factura, para encontrarlos fácil.
- Toma **cualquier PDF** de la carpeta como soporte y, si no halla ninguno,
  imprime un **diagnóstico** con ejemplos de lo que sí vio.

### 16 de julio de 2026 — Nace `AUDITAR_DEV_EPS` y todo el kit de auditoría
- Se creó el bot **`AUDITAR_DEV_EPS`**: por cada factura del Excel de
  devoluciones cruza el **RIPS (JSON)** con los **soportes (OPF/PDE)** y marca
  las diferencias (por ejemplo, el documento provisional de los **recién
  nacidos**). Llena el Excel + una hoja **DETALLE**.
  - Se corrigió que **se colgaba** recorriendo toda la red.
  - Se logró que extrajera **todas** las autorizaciones del soporte (solo los
    **últimos 9 dígitos**) y que reportara el **`null`** del JSON tal cual.
  - Se corrigió que **no hallaba los soportes**.
- **Kit de auditoría con menú `MOTOR_HUS.cmd`** + 5 bots nuevos del ciclo de
  glosas: `VERIFICAR_RADICACION`, `CRUZAR_GLOSAS`, `SEMAFORO_GLOSAS`,
  `BUSCAR_FACTURA`, `EXCEL_A_CSV`.
- **`INFORME_GERENCIA`** (tablero de gestión desde la bitácora de uso de los
  bots) y **`VIGILANTE_NOCTURNO`** (tarea programada de Windows).
- **`TXT_A_EXCEL`**: cada `.txt` (FURIPS, reportes) queda como `.csv` por comas
  y como Excel. Revisado a fondo.

### 15 de julio de 2026 — `REVISAR_XML`
- Bot que extrae de los XML radicados la **información de contrato** — el anexo
  de prueba para responder la glosa *"factura sin contrato"*.

### 6 de julio de 2026 — Bots de archivos (parte 2)
- **`PARTIR_ZIP_30MB`** (parte un `.zip` en pedazos de menos de 30 MB),
  **`COMPRIMIR_ZIP`** (baja el peso de los `.zip`) y **`PDF_A_CMD`** (copia
  `.cmd` de cada PDF, para plataformas que exigen ese formato).

### 2 y 3 de julio de 2026 — Bots de archivos (parte 1)
- **`UNIR_PDFS`**: une los PDF de cada carpeta en un consolidado, lo comprime e
  instala Python solo si falta. **`EXCEL_A_CMD`**: copia `.cmd` de cada Excel.

### 30 de junio – 1 de julio de 2026 — Robot que carga respuestas en DGH
- **`responder_glosas_dgh`**: automatiza el cargue de respuestas de glosas en
  **Dinámica Gerencial (DGH)**, llenando el formulario por coordenadas y con
  modo de calibración. Fue un trabajo largo de ajuste fino contra la pantalla.

### 22 – 26 de junio de 2026 — Portales COOSALUD y SIMED, notas crédito
- Bots para responder glosas en el **portal de COOSALUD** y cargar soportes en
  **SIMED**, armar **evidencias** en Word/PDF, y el **diagnóstico del Lote V2**
  del Dispensario (se halló que 6 facturas tenían el CUV inválido).

### 17 – 19 de junio de 2026 — Arranque
- Conexión al servidor (`login_dg`) y organización de las notas crédito.

---

## PENDIENTE (lo que falta)

- [ ] **`AUDITAR_DEV_EPS` con el Excel de GLOSAS ACEPTADAS.** Hoy solo lee el
      formato de *devoluciones* (`NUEVA_EPS_DEV.xlsx`, que tiene las columnas
      `FACTURA` y `FAC`). El de *glosas aceptadas* tiene otras columnas, por eso
      se detiene. **Falta:** hacer que detecte sola la columna de la factura
      (aunque se llame distinto) y que **agregue las columnas de auditoría al
      final, sin pisar los datos existentes**. → *Esperando que se suba ese
      Excel o una foto de sus encabezados para hacerlo bien.*
- [ ] **Probar el OCR (Tesseract) en el PC del hospital.** Ya se dejó la
      descarga automática; falta confirmar que instala bien allá.
- [ ] La rama de trabajo (`claude/powershell-pdf-cmd-bot-3iaihn`, PR #156) sigue
      en **borrador**. Revisar si se quiere pasar a definitiva / fusionar.

---

## PARA MAÑANA (lo próximo a trabajar)

1. Adaptar **`AUDITAR_DEV_EPS`** para que lea **cualquier Excel** con facturas
   (detectar la columna de factura + agregar las columnas de auditoría al final
   sin dañar lo que ya trae). *Requiere ver el archivo de glosas aceptadas.*
2. Correr el bot con el Excel real de glosas aceptadas y verificar que llena
   bien la observación, la validación SAT y las rutas.
3. Confirmar que el OCR queda instalado en el equipo del hospital.

---

> **Cómo se mantiene esto:** al terminar de trabajar, basta pedirle a Claude:
> *"Actualiza mi BITACORA.md con lo de hoy, lo pendiente y lo de mañana, y haz
> commit y push."* Y para revisar la semana: *"Con la bitácora y el git log,
> dame el resumen de lo que hice esta semana."*
