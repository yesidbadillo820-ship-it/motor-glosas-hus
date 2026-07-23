# BITÁCORA DE TRABAJO — Motor de Glosas HUS

> **Qué es este archivo.** Es la *memoria común* del proyecto. Todos los chats
> de Claude Code (y cualquier persona) deben leerlo primero para saber qué se
> ha hecho, qué falta y qué sigue. Está escrito en lenguaje claro, para el
> área de Cartera / Auditoría de Cuentas Médicas del HUS (no para programadores).
>
> **Regla:** al empezar una sesión, lea esta bitácora. Al terminar, agregue
> arriba una entrada nueva con la fecha: qué se hizo, qué quedó pendiente y qué
> sigue mañana.

**Última actualización:** 23-jul-2026

---

## Entrada 23-jul-2026 — Consolidados de cartera de 5 entidades (formato FAMISANAR)

**Qué se hizo hoy:**
- Se generaron los **5 informes consolidados de estado de cartera** con corte
  30/06/2026, imitando tal cual el formato del ejemplo FAMISANAR (5 hojas:
  CARTERA detalle por factura · RESUMEN por vigencia · CARTERA POR EDADES ·
  RAD VS REC mensual · ACTAS DE GLOSAS), a partir de los 6 cortes mensuales
  DGH (enero a junio 2026) que envió el analista:
  - **DISPENSARIO MÉDICO** (Sanidad Ejército, 2 NIT): 5.571 facturas,
    saldo $13.621.817.612. Incluye actas SINAC 709 ($230,0 millones
    levantados a favor del HUS) y 720 ($15,6 millones), y el giro directo
    real de mayo ($83,0 M) y junio ($78,4 M) del libro de pagos SAP.
  - **PROTEGER EPS** (antes Cajacopi EPS, mismo NIT): 532 facturas,
    saldo $4.268.767.084. OJO: en los cortes de ENE-FEB aparece con el
    nombre viejo "CAJACOPI EPS S.A.S.".
  - **CAJACOPI (Caja de Compensación)**: 115 facturas, saldo $302.274.693 —
    cartera SIN MOVIMIENTO en los 6 meses (misma cifra desde enero).
  - **COMPENSAR**: 39 facturas, saldo $193.065.583.
  - **MESSER**: sin cartera al corte (su única factura, $1.554.000, salió
    del corte en abril: recaudada o depurada).
- Verificación: fórmulas recalculadas sin errores y 30 de 30 totales
  cuadrados contra los cortes originales.

**Pendiente:**
- No existe corte de JULIO 2026: la columna de recaudo de julio quedó en 0.
  Cuando el analista tenga el corte 31/07/2026, se actualizan los 5 informes.
- El recaudo mensual se derivó del cruce de saldos entre cortes (incluye
  pagos y depuraciones juntos); si Tesorería entrega el giro directo real por
  entidad, se puede discriminar como en el informe FAMISANAR.

**Sigue mañana:** lo del PR #160 (igual que antes) y, si llega el corte de
julio o los soportes de tesorería, actualizar estos consolidados.

---

## ¿Qué es el proyecto, en una frase?

Dos herramientas para el HUS:

1. **Motor de Glosas** — una aplicación web que, con inteligencia artificial,
   redacta la respuesta técnico-jurídica a cada glosa de las EPS, según la
   norma colombiana. Reemplaza el trabajo manual de argumentar glosa por glosa.
2. **Suite Cartera HUS** — un programa de escritorio para el analista, que
   organiza los archivos de los portales, consolida las glosas, cruza contra la
   base DGH y arma el archivo de OBJECIONES listo para cargar. Reemplaza el
   flujo manual de Power Query + BUSCARV. Incluye una **caja de herramientas PDF**.

---

## RESUMEN DE LO YA HECHO (por fecha)

### 12–19 de junio de 2026 — Arranque y afinación del Motor
- Se puso a punto el Motor de Glosas: analiza la glosa y genera la respuesta.
- **Muchas "rondas" de corrección** (rondas 2 a 11) para que los argumentos de
  la IA sean sólidos y reales, no textos genéricos: se corrigieron citas
  inventadas, confusión de normas, textos "de relleno" (placeholders), y el
  cálculo de glosas **extemporáneas** (fuera de los 20 días hábiles).
- **Publicación en la máquina del propio HUS**, gratis, con un túnel seguro de
  Cloudflare (sin costo mensual de servidor).
- **Paneles nuevos** en la aplicación: nota crédito (seguimiento de cartera),
  consulta normativa, pestaña única de reportes (Mando · Dashboard · Cartera ·
  Mes) y el **acta SINAC** de conciliación con su paso a paso de soportes.

### 22–26 de junio de 2026 — Despliegue propio + más calidad
- Auto-actualización del sistema desde Git (se despliega solo).
- Más rondas de calidad (12 a 18): se afinó el reconocimiento de medicamentos
  (CUM/INVIMA), la detección automática de la EPS, reglas para que la IA **no
  invente** valores ni normas, y el "enrutamiento" para que los casos difíciles
  los resuelva el modelo más potente.

### 30 de junio de 2026 — El gran salto: "de a ciegas a medido"
- **Homologador CUPS → SOAT**: para defender bien la tarifa de cada servicio.
- **Tablero de calidad**: un "marcador" de 0 a 10 que **califica cada respuesta**
  de la IA contra una rúbrica experta y **avisa si algo empeora**. Antes se
  corregía a ciegas; ahora todo se mide.
- **Banco de defensa clínica** (evidencia médica de primer nivel: robot da
  Vinci, implante coclear, hemofilia, etc.) conectado a la generación.
- **Resultado medible** sobre 4 casos reales difíciles: pasaron de un promedio
  de **2,5/10 a ~9/10**.

### 1–2 de julio de 2026 — "El expediente": contratos + soportes + precedentes
- Se conectaron tres fuentes de datos que existían pero estaban "desenchufadas":
  - **Contratos**: 26 cláusulas reales de 11 pagadores (AURORA, COMPENSAR,
    COOSALUD, FOMAG, POLICÍA, etc.). Fin del falso "sin contrato pactado".
  - **Soportes**: la IA por fin **lee la historia clínica adjunta** (antes solo
    veía un pedacito) y avisa qué soportes faltan, sin inventar evidencia.
  - **Precedentes**: aprende de casos **ya ganados** parecidos al que está
    respondiendo.

### 3–10 de julio de 2026 — Ajustes y la Suite Cartera HUS
- Se integraron varios arreglos (PR #153, #155, #159).
- Nació la **Suite Cartera HUS** (programa de escritorio del analista):
  - Organiza el ZIP del portal en lotes, consolida las glosas, cruza contra la
    base DGH y arma las **OBJECIONES** listas para cargar.
  - Se corrigió un error grave: los **importes se dividían por mil** (leía
    "50.000" como "50"). Ya quedó bien.
  - **Seguridad**: las contraseñas de los portales salieron del repositorio a un
    archivo local que no se sube. La Suite las vuelve a unir al abrir.
  - Versión por **línea de comandos** para automatizar sin ventana.

### 16 de julio de 2026 — Caja de Herramientas PDF (el "bot" de PDF)
Se agregó a la Suite un botón **🧰 Herramientas PDF** con 26 utilidades, en 3 fases:
- **Fase 1 (sin internet):** unir, dividir, quitar/extraer/reordenar páginas,
  rotar, recortar, números de página, marca de agua, imágenes↔PDF, comprimir,
  reparar, **proteger/desbloquear** con clave y **censurar** (tachar datos, que
  además los borra de verdad).
- **Fase 2 (conversión Office):** Word/Excel/PowerPoint/HTML → PDF, y PDF →
  Word/Excel/PowerPoint, y PDF/A. (Las de Office usan LibreOffice, gratis.)
- **Fase 3 (inteligencia / IA):** **resumir**, **traducir**, **PDF → Markdown**
  y **OCR** (extraer el texto, hasta de escaneos), usando la misma IA (Gemini)
  del Motor.
- Se escribió la guía **PASO_A_PASO_HERRAMIENTAS_PDF.txt** para el analista.
- Todo con **pruebas automáticas** (128 en total, todas en verde).

### 22 de julio de 2026 (hoy) — Control central del trabajo
- Se creó esta **BITÁCORA.md** (memoria común de todos los chats) reconstruyendo
  todo lo anterior desde la historia de Git.
- Se creó **CLAUDE.md** con la instrucción de leer y actualizar esta bitácora en
  cada sesión.
- Se corrigió un **fallo de CI heredado** (ajeno al trabajo de Cartera/PDF): dos
  pruebas del Motor usaban fechas fijas de abril que se salieron de la ventana de
  90 días y empezaron a fallar solas el 19-jul. Se anclaron a "la semana pasada"
  para que no vuelvan a caducar. La funcionalidad real nunca estuvo mal.

---

## PENDIENTE (lo que falta)

- [ ] **Revisar y fusionar el PR #160** (la Suite Cartera + las Herramientas
      PDF). Hoy está en **borrador**; falta aprobarlo y pasarlo a la rama
      principal para que quede oficial.
- [ ] **4 herramientas PDF avanzadas** que aún no se hicieron: editar texto
      libre, formularios, firma digital y comparar dos PDF. (Serían una "fase 4".)
- [ ] **Validar el mapeo DGH** (los 16 encabezados del archivo de OBJECIONES)
      contra un cargue piloto pequeño **antes** del primer cargue masivo real.
- [ ] **Depurar la lista de entidades**: agregar un campo de estado de vigencia
      (vigente / en liquidación / liquidada / deshabilitada), que quedó propuesto.
- [ ] **Verificar los links de plataformas** marcados "sin respuesta": muchos
      podrían funcionar solo desde la **red / VPN del HUS**; validarlos allá.
- [ ] **Configurar en el equipo del analista**: LibreOffice (para Office→PDF) y
      la clave `GEMINI_API_KEY` (para las funciones de IA).

---

## PARA MAÑANA (lo próximo a trabajar)

1. **Revisar y fusionar el PR #160** para dejar oficial la Suite + Herramientas PDF.
2. **Decidir el siguiente paso del bot PDF:** ¿armamos la fase 4 (las 4
   herramientas avanzadas) o priorizamos otra cosa de Cartera?
3. **Dejar lista la lista de entidades** con el estado de vigencia y los links
   ya validados desde la red del HUS.

---

_Cómo mantener esta bitácora: agregue la entrada de cada día ARRIBA del todo en
"RESUMEN DE LO YA HECHO", mueva a "PENDIENTE" lo que no alcanzó, y deje en
"PARA MAÑANA" lo próximo. Siempre con la fecha._
