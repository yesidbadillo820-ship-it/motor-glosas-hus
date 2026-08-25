# DOCUMENTACIÓN OFICIAL DE ENTREGA — MÓDULO ADRES / FURIPS, INFORMES Y APP WEB

**Repositorio:** `yesidbadillo820-ship-it/motor-glosas-hus`
**Rama de desarrollo:** `claude/bot-validacion-campos-pdf-tgebvr`
**Conversación de origen:** "VALIDADOR ADRES — FURIPS, informes y app web"
**Período de desarrollo:** 17 – 23 de julio de 2026 (documento redactado el 27 de julio de 2026)
**Pull Requests:** #173, #174, #175 (fusionados) y #176 (abierto, contiene todo lo del 21–23 de julio)
**Destinatario:** equipo principal del proyecto consolidado

> Este documento reconstruye TODO lo desarrollado en esta rama/conversación:
> código, decisiones técnicas, cambios de enfoque, soluciones descartadas,
> errores encontrados y sus arreglos, y el conocimiento operativo necesario
> para mantener el módulo. Nada de lo aquí escrito es inventado: todo
> proviene del historial de la conversación, de los commits y de los
> archivos del repositorio.

---

## 1. OBJETIVO DEL DESARROLLO

### Por qué se creó este módulo

El dueño del repositorio es auditor de facturación de la E.S.E. Hospital
Universitario de Santander (HUS). El repositorio ya contenía la plataforma
**Motor Glosas** (`app/`), que responde glosas de EPS con IA. Esta rama nació
para un frente distinto: la **radicación y defensa de reclamaciones ante la
ADRES** (accidentes de tránsito / FURIPS) y trabajos conexos de auditoría de
facturación.

### Qué problemas resolvía (en orden cronológico de solicitud)

1. **Validación FURIPS masiva.** La ADRES devuelve reclamaciones por errores
   de forma en los archivos FURIPS 1 y 2 (TXT). Se necesitaba un bot que
   validara los TXT contra la malla de la **Circular 022 de 2023 de la
   ADRES** (102 campos del FURIPS1, 9 del FURIPS2) y además **cruzara cada
   factura contra sus soportes reales** (RIPS JSON, CUV JSON, factura
   electrónica XML DIAN, factura PDF, epicrisis PDF), de forma masiva, con
   un informe Excel detallado y profesional.
2. **Informe de baja de cartera.** El área de facturación debe presentar las
   facturas que no cumplen la Resolución 577 de 2019 (manual de cartera del
   HUS) para trámite de baja. Se necesitaba generar el documento Word de
   presentación Y un Excel de relación, leyendo los PDF unidos de cada
   factura.
3. **App web del validador.** Convertir el bot FURIPS en una aplicación web
   profesional e interactiva para usar desde el navegador (sin consola).
4. **Bots utilitarios Windows.** Conversión PDF→.cmd agrupada en una carpeta
   (para transportar PDFs por canales que bloquean esa extensión).
5. **Memoria común.** `BITACORA.md` + `CLAUDE.md` para que todas las
   sesiones de IA conserven contexto entre chats.
6. **Informe de devoluciones DE4401 de NUEVA EPS.** 411 facturas devueltas
   por "inconsistencias de la factura electrónica"; se necesitaba un bot que
   leyera el XML DIAN de cada factura y completara el Excel del informe con
   valor, contrato, cobertura, validación DIAN, conclusión (argumento de
   glosa) y respuesta lista para el portal DGH.

### Qué necesidad cubría

Reducir de días a minutos la revisión manual de cientos de facturas, con
criterio normativo (Circular 022/2023 ADRES, Res. 577/2019, Res. 506/2021 y
2275/2023 MinSalud) y entregables listos para radicar/presentar. Todo debía
funcionar con **doble clic en Windows** para auditores no programadores, y
con los datos sin salir de la red del hospital.

---

## 2. ARQUITECTURA

### 2.1 Estructura de carpetas y archivos del módulo

```
motor-glosas-hus/
├── BITACORA.md                     ← memoria común de todas las sesiones (nuevo)
├── CLAUDE.md                       ← instrucciones para sesiones de IA (nuevo)
├── .gitattributes                  ← regla `*.cmd text eol=crlf` (nuevo, crítico)
├── tools/
│   ├── adres/
│   │   ├── validar_furips.py       ← MOTOR del validador FURIPS (3.249 líneas)
│   │   ├── VALIDAR_FURIPS.cmd      ← lanzador de doble clic del motor
│   │   ├── README.md               ← estado del módulo ADRES (preexistente, fases)
│   │   ├── README_validar_furips.md← guía de uso del validador
│   │   ├── rips_lectura.py         ← parseo/normalización RIPS (compartido, preexistente)
│   │   ├── factura_lectura.py      ← lectura FEV DIAN (compartido, preexistente)
│   │   ├── inspeccionar_soportes.py← inventario de soportes (preexistente)
│   │   └── generar_fur_servicios.py← FUR SERVICIOS desde RIPS (preexistente)
│   ├── generar_informe_baja_cartera.py  ← informe de baja Word+Excel (922 líneas)
│   ├── INFORME_BAJA_CARTERA.cmd    ← lanzador de doble clic
│   ├── completar_informe_xml_dian.py    ← bot DE4401 (665 líneas, versión 2.1)
│   ├── COMPLETAR_INFORME_XML.cmd   ← lanzador de doble clic (ruta editable)
│   ├── UNIR_PDFS.cmd               ← bot original del usuario (conservado)
│   ├── PDF_A_CMD.cmd               ← bot original del usuario (conservado)
│   └── PDF_A_CMD_EN_CARPETA.cmd    ← nuevo bot (361 líneas, Python embebido)
└── validador-adres/                ← APP WEB independiente
    ├── app.py                      ← backend FastAPI (471 líneas)
    ├── static/
    │   ├── index.html              ← única página (235 líneas)
    │   ├── styles.css              ← temas claro/oscuro (371 líneas)
    │   └── app.js                  ← toda la lógica de interfaz (660 líneas)
    ├── VALIDADOR_ADRES_WEB.cmd     ← lanzador local (puerto 8010)
    ├── Dockerfile                  ← despliegue en contenedor
    ├── requirements.txt            ← dependencias de la app
    └── README.md                   ← guía de la app
```

### 2.2 Componentes y su relación

- **Motor de validación** (`tools/adres/validar_furips.py`): biblioteca +
  CLI. Es el ÚNICO lugar donde vive la lógica de validación. Lo consumen
  dos frentes: el `.cmd` de doble clic y la app web.
- **App web** (`validador-adres/app.py`): NO duplica lógica; importa el
  motor haciendo `sys.path.insert(0, str(_RAIZ_REPO / "tools" / "adres"))`
  (por eso `validador-adres/` debe vivir junto a `tools/` — acoplamiento
  estructural deliberado).
- **Bots independientes**: baja de cartera y DE4401 son scripts autónomos
  (solo comparten convenciones: normalización de números de factura,
  lectura dual de PDF, estilos de Excel).
- **Lanzadores `.cmd`**: cada bot tiene un `.cmd` Windows que autoinstala
  dependencias con pip y llama al `.py`. TODOS deben tener finales de línea
  CRLF (ver §13).

### 2.3 Dependencias y librerías

| Librería | Versión mínima | Usada por | Para qué |
|---|---|---|---|
| openpyxl | ≥3.1 | todos los bots + web | leer/escribir Excel |
| pypdf | ≥4.0 | validador, baja | extracción de texto PDF (motor 2) |
| pdfplumber | ≥0.11 | validador, baja | extracción de texto PDF (motor 1, mejor calidad; opcional) |
| python-docx | (última) | baja de cartera | generar el documento Word |
| fastapi | ≥0.110 | app web | framework HTTP |
| uvicorn | ≥0.29 | app web | servidor ASGI |
| python-multipart | ≥0.0.9 | app web | subida de archivos |

El bot DE4401 usa SOLO biblioteca estándar + openpyxl (zipfile, html, json,
re, unicodedata, collections.Counter, pathlib).

### 2.4 APIs, modelos y servicios

- No hay base de datos ni ORM en este módulo (ver §5).
- La única API es la REST de la app web (ver §6).
- No hay servicios externos: todo corre local / en la red del hospital.
- "Modelos" de datos: dataclasses internas del motor (resultado por
  factura, hallazgos) y diccionarios simples en los otros bots.

---

## 3. FUNCIONES IMPLEMENTADAS

### 3.1 Motor validador FURIPS (`tools/adres/validar_furips.py`)

Constantes/tabla de especificación:

- **E1**: tabla de los **102 campos del FURIPS1** (Tabla 1 de la Circular
  022/2023). Cada campo tiene: número, sección, concepto, longitud, formato
  (`fecha`, `hora`, `num`, `cie10`, `depto`, `mun`, `placa`, `dir`),
  valores permitidos y **código de obligatoriedad condicional**.
- **E2**: tabla de los **9 campos del FURIPS2** (Tabla 2).
- **TEXTO_OBLIG**: mapa código→texto legible de cada condición de
  obligatoriedad (p. ej. `C_UCI` = "Obligatorio si se prestó UCI (campo
  42=1 o UCI en FURIPS2)", `C_ESTANCIA`, `C_UCI_F2`, condiciones por
  estado de aseguramiento 1,2,3,4,6,7,8, naturaleza del evento, remisión,
  transporte, quirúrgicos).
- **MIN_TEXTO_PDF = 200**: umbral de caracteres para considerar legible un
  PDF (por debajo se trata como escaneado → "SIN TEXTO").
- Niveles de hallazgo: `ERROR`, `ADVERTENCIA`, `OK`, `INFO`.

Funciones principales (qué hace / por qué existe / de qué depende):

| Función | Qué hace |
|---|---|
| `norm_factura(valor)` | Normaliza números de factura: quita espacios, guiones y ceros a la izquierda (`HUS0000533650` → `HUS533650`). Existe porque cada sistema escribe el número distinto. Es la pieza que permite TODOS los cruces. |
| `factura_desde_nombre(nombre)` | Extrae el número de factura del nombre de un archivo (`680010079201_HUS374152_EPICRIS.pdf` → `HUS374152`). |
| `descubrir_soportes(base)` | Recorre recursivamente (`rglob`) la carpeta y agrupa soportes por factura usando `factura_desde_nombre(p.name) or factura_desde_nombre(p.parent.name)` — funciona con carpeta POR factura y con carpeta PLANA (todos los soportes juntos). |
| `leer/agrupar FURIPS1 y FURIPS2` | Localizan los TXT FURIPS1/FURIPS2 en raíz y subcarpetas, y agrupan registros/líneas por factura normalizada. |
| `validar_malla_f1(...)` | Valida los 102 campos del FURIPS1 contra E1: longitud, formato, permitidos, obligatoriedad condicional. |
| `_evaluar_condicion(...)` | Evalúa las condiciones de obligatoriedad (por estado de aseguramiento, evento, remisión, UCI, etc.). |
| `validar_furips2(...)` | Valida las líneas FURIPS2; **agrega hallazgos por patrón** (no repite el mismo error línea por línea, lo agrupa). |
| `_validar_sumatorias(...)` | Verifica las sumatorias de los campos 97–100 del FURIPS1 contra las líneas del FURIPS2 (reclamado ≤ facturado, coherencia de totales). |
| `observacion_direccion(valor)` | Valida NOMENCLATURA de dirección (campos 15, 50 y 60): marca ERROR si es solo dígitos (un código como `68780`) o si no tiene dígitos NI palabra de dirección (solo un municipio como `SURATA`). Acepta excepciones `SIN INFORMACION` / `NO REFIERE`. Usa el conjunto `_PALABRAS_DIRECCION` (CALLE, CARRERA, MANZANA, VEREDA, KM…). Se creó a petición expresa del usuario: "debe ir la nomenclatura completa ejemplo calle 51#15-20, manzana x casa y". |
| `parse_fecha_flexible(...)` | Interpreta fechas en los distintos formatos que aparecen en soportes. |
| `extraer_texto_pdf(ruta)` | Extracción de texto con DOBLE MOTOR: intenta pdfplumber y pypdf y se queda con el texto MÁS LARGO. Si el total < `MIN_TEXTO_PDF`, el PDF se declara "SIN TEXTO" (escaneado) y NO genera errores falsos, solo la sugerencia de OCR. |
| `extraer_montos(...)` | Localiza valores monetarios en el texto de los PDF. |
| `analizar_carpeta(...)` | Orquesta el análisis de los archivos de una factura. |
| `cruzar_soportes(...)` | Cruza FURIPS vs RIPS/CUV/FEV XML/factura PDF/epicrisis: identidad del paciente, documento, fechas de ingreso/egreso, montos, número de factura, CUV (rechazos y notificaciones del validador MSPS). **Detección de la "Representación Gráfica DIAN"**: si el texto de la factura PDF contiene `REPRESENTACION GRAFICA`, ese PDF no trae datos del paciente → los cruces de paciente se marcan `N/A (repr. gráfica DIAN sin datos de paciente)` y se validan contra la EPICRISIS. El número de factura se busca quitando espacios, guiones y puntos (`re.sub(r"[\s\-.]", "", txt)`) porque la DIAN lo imprime como `HUS-372720`. |
| `generar_excel(resultados, obs, salida)` | Informe de **7 hojas: RESUMEN, HALLAZGOS, FURIPS1 CAMPOS, FURIPS2 LINEAS, CRUCE SOPORTES, SOPORTES y LEYENDA**, con semáforo (colores §3.6), paneles congelados, filtros y saneo de caracteres de control ilegales para openpyxl (`re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", v)`) porque algunos TXT reales venían truncados/binarios. |

Además valida el **nombre de archivo FURIPS**:
`FURIPS<n><CODHABILITACION(12 dígitos)><DDMMAAAA>.txt`.

### 3.2 Informe de baja de cartera (`tools/generar_informe_baja_cartera.py`)

- Insumo: el PDF UNIDO por factura que deja `UNIR_PDFS.cmd`
  (`_UNIDO_<carpeta>.pdf` o su copia `.cmd`, que es el mismo PDF renombrado).
- Extrae: número de factura, paciente, documento, fechas de atención,
  **valor de la factura** y el **informe de trabajo social** (localiza sus
  páginas y transcribe el concepto).
- Genera **DOS entregables en la misma corrida** (pedido expreso del
  usuario): el documento **Word** (python-docx) con introducción del área
  de facturación, marco normativo (Res. 577/2019), relación de facturas
  ordenadas de MAYOR a MENOR valor y análisis individual por factura
  (la justificación se AJUSTA a lo que trabajo social dejó escrito: sin
  capacidad de pago, no localizable, sin red de apoyo, fallecido,
  extranjero no afiliado, etc.); y el **Excel** con la hoja RELACION DE
  FACTURAS (semáforo), EXTRACTOS TRABAJO SOCIAL y LEYENDA.
  Decisión documentada en el propio docstring: NO se incluye la fórmula
  "agotadas las acciones administrativas de cobro persuasivo (Art. 15)"
  porque esas facturas nunca se remitieron a cartera.
- `analizar_carpeta(carpeta, pdfs=None, numero_hint="")`: acepta lista
  explícita de PDFs y una pista del número (para el modo carpeta plana).
- **Modo carpeta plana** (segunda iteración): si en una sola carpeta hay
  PDFs de ≥2 facturas identificables por nombre, se agrupan por número y se
  procesa factura por factura; si hay >25 PDFs no identificables, se omite
  esa carpeta con mensaje (evita "colgarse" leyendo cientos de PDF de red).
- Registro de progreso por factura (antes parecía congelado leyendo ~100
  PDFs de red en silencio; eso se corrigió).
- Las facturas cuyo informe de trabajo social no se pudo extraer quedan con
  "NOTA DE REVISIÓN" en el Word para completar a mano.

### 3.3 Bot DE4401 (`tools/completar_informe_xml_dian.py`, versión 2.1)

Completa 7 columnas del Excel del informe de devoluciones (hoja `DE4401`,
411 facturas): `VALOR (XML)`, `NUMERO_CONTRATO`, `COBERTURA_PLAN_BENEFICIOS`,
`VALIDACIÓN DIAN`, `CONCLUSIÓN (ARGUMENTO GLOSA)`, `ARCHIVO XML`,
`RESPUESTA DGH`.

| Función | Qué hace |
|---|---|
| `normalizar` / `norm_factura` / `facturas_en_nombre` | Normalización idéntica en espíritu a la del validador. `facturas_en_nombre` usa el regex `([A-Z]{2,}0*\d{4,})` sobre el nombre normalizado. |
| `_texto_xml(ruta)` | Lee el XML y des-escapa el Invoice embebido del AttachedDocument DIAN (quita `<![CDATA[`/`]]>` y aplica `html.unescape` si hay `&lt;`). |
| `analizar_xml(ruta)` | Extrae: número de factura (regex con lookahead `<(?:\w+:)?Invoice[\s>].*?<(?:\w+:)?ID(?=[\s>])[^>]*>` — el lookahead evita que `IGNORECASE` capture `<cbc:IdentificationCode>`, error real que devolvía "CO"), fecha, CUFE (`UUID schemeName="CUFE-SHA384"`), firma (`<ds:Signature`), autorización de numeración (`sts:InvoiceAuthorization`), NITs, total (`LegalMonetaryTotal > PayableAmount`), acuse DIAN (`ApplicationResponse > ResponseCode`, 02 = validado) y los campos del **sector salud** (`Interoperabilidad > AdditionalInformation`: NUMERO_CONTRATO, COBERTURA_PLAN_BENEFICIOS, MODALIDAD_PAGO, NUMERO_POLIZA, COPAGO, CUOTA_MODERADORA, con su schemeID). |
| `validar_dian(x)` | Redacta la columna VALIDACIÓN DIAN ("VÁLIDA — …" / "CON OBSERVACIONES — …") y devuelve si quedó todo en regla. |
| `construir_conclusion(...)` | Redacta el argumento de glosa citando Res. 506/2021 y Res. 2275/2023. Estados: `NO PROCEDE DEVOLUCIÓN` (verde), `REVISAR` (amarillo), `SIN XML` (rojo). Detecta: XML de OTRA factura, contrato `SIN CONTRATO`/vacío, cobertura vacía, diferencia de valor XML vs Excel (con el ayudante `_pesos()` para formato $ con puntos — ver lección §13.7). |
| `ArchivoEnZip` | (v2.1) Clase que imita lo mínimo de `Path` (`name`, `stem`, `suffix`, `read_text`, `stat`) para leer un `.xml`/`.json` que viene DENTRO de un `.zip` (paquete DIAN) sin extraerlo a disco. Relanza errores de zip como `OSError` para que el manejo de errores existente lo cubra. |
| `indexar_archivos(raiz)` | Recorre `rglob` e indexa `{factura: [xmls]}` y `{factura: [jsons]}`. Las claves se obtienen del **nombre del archivo Y de TODA la cadena de carpetas contenedoras** hasta la raíz (v2.0, porque el servidor real guarda cada factura en subcarpeta `FACTURAS_SALUD\HUS533650\` con archivos de nombre genérico DIAN `ad0901…xml`), y también de los miembros de los `.zip` (v2.1). Devuelve además un diccionario `diag` de diagnóstico (conteo de archivos por extensión, subcarpetas de primer nivel, muestras de nombres, zips dañados). |
| `ordenar_xmls(candidatos, factura)` | Ordena candidatos: primero el que trae el número de ESTA factura en el nombre, luego el que dice FACTURA (no FACOSTE/nota), luego el más reciente. `elegir_xml` quedó como envoltorio de compatibilidad. |
| Reintento por contenido (dentro de `completar`) | Si el candidato elegido no trae el número correcto POR DENTRO, se abren los demás candidatos hasta dar con el que sí (una carpeta puede traer factura + notas + acuses con nombres genéricos). |
| `revisar_json(candidatos, factura)` | Nota corta sobre el RIPS/CUV JSON (CUV presente y válido/rechazado; número del RIPS coincide o no). |
| `completar(excel, raiz, salida, hoja)` | Llena las 7 columnas con semáforo en CONCLUSIÓN, congela paneles, aplica autofiltro, escribe la hoja **RESUMEN** (totales + ruta + criterios + versión del bot) y la hoja **DIAGNOSTICO** (v2.1: versión, ruta, subcarpetas, archivos por tipo, XML dentro de ZIP, muestras de nombres — diseñada para diagnóstico remoto cuando una corrida sale mal). Salida por defecto: `<informe>_COMPLETO.xlsx`. |
| `VERSION = "2.1 (23 de julio de 2026)"` | Se imprime en consola y queda en RESUMEN y DIAGNOSTICO, para poder saber SIEMPRE qué versión produjo un Excel (nació de no poder distinguir si el usuario corrió la versión vieja o la nueva). |

### 3.4 Bot `PDF_A_CMD_EN_CARPETA.cmd`

Archivo `.cmd` autocontenido: la mitad superior es batch y tras el marcador
`#PYSTART#` va el motor Python embebido (el batch se extrae a sí mismo esa
sección y la ejecuta). Qué hace: busca PDFs en la carpeta y TODAS sus
subcarpetas, crea la carpeta `CMD_CONVERTIDOS/` y deja DENTRO una copia de
cada PDF con extensión `.cmd`. Reglas: nombra las colisiones como
`<carpeta>_<nombre>.cmd` y luego `_2`, `_3`…; EXCLUYE la carpeta destino del
recorrido (no se reconvierte a sí misma); NUNCA sobrescribe un `.cmd` que no
sea PDF. Se creó a partir del `PDF_A_CMD.cmd` original del usuario, que
dejaba las copias regadas junto a cada PDF.

### 3.5 App web Validador ADRES (`validador-adres/`)

Backend en §6, frontend en §7.

### 3.6 Convención de estilos Excel (compartida por todos los informes)

- Encabezados: fondo azul `#1F4E79`, letra blanca negrita.
- ERROR: fondo `#FFC7CE`, letra `#9C0006` (negrita).
- ADVERTENCIA: fondo `#FFEB9C`, letra `#9C6500`.
- OK: fondo `#C6EFCE`, letra `#006100`.
- INFO: fondo `#DDEBF7`, letra `#1F4E79`.
- Bordes finos `#D9D9D9`, paneles congelados en A2, autofiltro.

---

## 4. FLUJO COMPLETO

### 4.1 Validador FURIPS por doble clic

1. El auditor copia `VALIDAR_FURIPS.cmd` + los `.py` de `tools/adres/` a la
   carpeta raíz de las facturas (o arrastra una carpeta sobre el `.cmd`).
2. El `.cmd`: fija consola UTF-8 (`chcp 65001`), localiza Python probando
   `py -3`, `python`, `python3` **ejecutándolos** (no solo `where`), e
   instala si faltan: openpyxl (obligatorio), pypdf (obligatorio),
   pdfplumber (best-effort, si falla se sigue sin él).
3. `validar_furips.py --raiz <carpeta>`:
   a. localiza los TXT `FURIPS1*/FURIPS2*` (raíz y subcarpetas) y valida el
      patrón del nombre;
   b. agrupa registros por factura normalizada;
   c. `descubrir_soportes` agrupa los soportes por número de factura leído
      del NOMBRE de archivo (o de su carpeta) — sirve carpeta por factura y
      carpeta plana;
   d. por cada factura: malla E1 (102 campos, obligatoriedad condicional),
      FURIPS2 (9 campos, hallazgos agregados por patrón), sumatorias 97–100;
   e. cruces contra soportes: RIPS (identidad, fechas, servicios), CUV
      (ResultState, rechazos, notificaciones), FEV XML, factura PDF (o
      epicrisis si la factura es representación gráfica DIAN), epicrisis;
      los PDF escaneados quedan "SIN TEXTO" sin producir errores falsos;
   f. `generar_excel` escribe `INFORME_VALIDACION_FURIPS_AAAAMMDD.xlsx`
      (7 hojas) en la carpeta procesada.
4. La ventana queda abierta (`pause`) mostrando el resumen.

### 4.2 App web (usuario final)

1. Doble clic a `VALIDADOR_ADRES_WEB.cmd` → instala dependencias si faltan,
   levanta uvicorn en `0.0.0.0:8010` y abre `http://localhost:8010`.
   Otros PC de la red entran por `http://<nombre-del-pc>:8010`.
2. Pantalla de carga: arrastrar los TXT FURIPS y un ZIP de soportes.
3. `POST /api/validar` guarda los archivos (límite 500 MB c/u), extrae el
   ZIP con protección zip-slip, crea el trabajo en memoria y lanza un HILO
   con el mismo motor `validar_furips`.
4. El navegador sondea `GET /api/validaciones/{id}/estado` y muestra la
   bitácora de avance en vivo.
5. Al terminar: tablero con KPIs animados, gráficas SVG apiladas por origen
   y por concepto (con tooltip y clic para navegar), tabla de facturas con
   semáforo ordenable, vista de hallazgos con filtros, detalle por factura
   en cajón lateral con navegación ←/→, modo claro/oscuro, y botón de
   descarga del Excel (`GET /api/validaciones/{id}/excel`).
6. `sessionStorage` permite recuperar la última validación al recargar.

### 4.3 Informe de baja de cartera

1. Preparación: `UNIR_PDFS.cmd` deja el PDF unido por factura.
2. Doble clic a `INFORME_BAJA_CARTERA.cmd` (autoinstala python-docx y
   pypdf) → recorre las carpetas; si detecta carpeta PLANA agrupa por número
   de factura en el nombre; lee cada PDF unido (pdfplumber→pypdf), extrae
   valor/paciente/fechas + páginas del informe de trabajo social, registra
   avance por factura.
3. Salida: Word de presentación (facturas ordenadas de mayor a menor valor,
   análisis individual, "NOTA DE REVISIÓN" donde faltó trabajo social) +
   Excel de relación con semáforo.

### 4.4 Bot DE4401

1. El auditor deja `COMPLETAR_INFORME_XML.cmd` + `completar_informe_xml_dian.py`
   juntos; el `.cmd` trae editable en su línea 23:
   `set "RUTA_FACTURAS=\\172.16.32.83\factura_electronica_net22\202607\FACTURAS_SALUD"`.
2. Doble clic: detecta el Excel (`INFORME*XML*.xlsx`, o cualquier `.xlsx`,
   o el arrastrado encima), instala openpyxl si falta, ejecuta el bot.
3. El bot: carga la hoja (por defecto la primera), ubica columnas por
   encabezado, indexa TODOS los `.xml`/`.json`/`.zip` de la ruta
   (nombre + cadena de carpetas + miembros de zip), y por cada fila:
   normaliza el número, ordena candidatos, analiza el XML (con reintento
   por contenido), revisa el JSON RIPS/CUV, redacta validación DIAN,
   conclusión y respuesta DGH, y pinta el semáforo.
4. Salida: `<informe>_COMPLETO.xlsx` con hojas DE4401 (completada), RESUMEN
   y DIAGNOSTICO.

---

## 5. BASE DE DATOS

**Este módulo NO usa base de datos.** Decisión deliberada: los bots son
herramientas de lectura/escritura de archivos y la app web guarda los
trabajos en un **diccionario en memoria** (máx. 20 trabajos; los viejos se
purgan con `_limpiar_trabajos_viejos`). No hay tablas, migraciones ni
Alembic en este frente (el Alembic del repo pertenece a la plataforma Motor
Glosas, que no se tocó en esta rama). Consecuencia conocida: al reiniciar
la app web se pierden los resultados no descargados; el entregable
persistente es siempre el Excel.

---

## 6. BACKEND (app web `validador-adres/app.py`)

**Endpoints:**

| Método y ruta | Qué hace |
|---|---|
| `POST /api/validar` | Multipart: TXT FURIPS + ZIP/archivos de soportes. Valida extensión contra lista blanca y tamaño (≤500 MB por archivo, HTTP 413). Extrae ZIP con `_extraer_zip_seguro` (rechaza rutas que escapen del directorio — zip-slip). Crea trabajo y lanza hilo de validación. Devuelve `{id}`. |
| `GET /api/validaciones/{id}/estado` | Progreso: estado + mensaje de bitácora; HTTP 202 mientras corre. |
| `GET /api/validaciones/{id}` | Resultado: KPIs y datos de gráficas (contadores `por_origen`, `por_concepto`, `top_facturas`). |
| `GET /api/validaciones/{id}/hallazgos` | Lista global de hallazgos (para filtros del frontend). |
| `GET /api/validaciones/{id}/facturas/{factura}` | Detalle de una factura. |
| `GET /api/validaciones/{id}/excel` | Descarga del informe Excel generado por el MISMO `generar_excel` del motor. |
| `GET /api/salud` | Chequeo de vida. |

**Servicios/estructura interna:** diccionario global `jobs` {id → estado,
mensaje, resultados}; un hilo `threading.Thread` por validación; el motor se
importa una vez vía `sys.path`. `StaticFiles` sirve `static/` como frontend.

**Manejo de errores:** excepciones del hilo quedan en el estado del trabajo
y el frontend las muestra; HTTPException 404 para IDs inexistentes, 413 para
tamaño, 400 para cargas inválidas.

**Permisos/seguridad:** sin autenticación (decisión consciente: red interna
del hospital; "usuarios y contraseñas" quedó en mejoras futuras, ver §15).
La protección implementada es de integridad: lista blanca de extensiones,
límite de tamaño y extracción segura de ZIP.

---

## 7. FRONTEND (`validador-adres/static/`)

Una sola página (`index.html`) con vistas conmutadas por JS puro — **sin
frameworks ni CDN** (funciona sin internet, requisito de red hospitalaria):

1. **Carga**: zona drag&drop para TXT y ZIP, validación de extensión en
   cliente, botón "Validar".
2. **Progreso**: bitácora en vivo (sondeo del estado), animación de avance.
3. **Tablero**: KPIs animados (conteo ascendente); tarjeta de valor en
   dinero con ajuste tipográfico específico (`.kpi.dinero .valor
   { font-size: 1.14rem }` + nowrap, tras dos intentos de arreglo por
   desbordamiento); gráficas de barras apiladas en SVG generado a mano con
   tooltips y clic-para-navegar (por origen y por concepto; top facturas).
4. **Facturas**: tabla con semáforo por severidad, ordenable por columnas.
5. **Hallazgos**: lista global con filtros por severidad/origen/texto.
6. **Detalle**: cajón (drawer) lateral por factura con navegación ←/→ entre
   facturas sin cerrar.
7. **Extras**: modo claro/oscuro (variables CSS + `html[data-tema="oscuro"]`),
   toasts de aviso, `sessionStorage` para retomar la última validación,
   estados vacíos ilustrados.

La interfaz se rehízo COMPLETA en una segunda pasada (commit 8791fdc)
cuando el usuario pidió "más interactiva, más dinámica, más pulida, más
estética, más profesional, más pulcra, más funcional e intuitiva"; se
verificó con Playwright (capturas claro/oscuro de todas las vistas, sin
errores de consola JS).

---

## 8. IA

**En tiempo de ejecución este módulo NO usa IA.** Toda la validación es
determinística (reglas de la Circular 022/2023, regex, cruces). No hay
prompts, proveedores, modelos ni temperatura que documentar en el producto.
(La plataforma Motor Glosas de `app/` sí usa IA, pero NO se modificó en
esta rama.)

**IA en el proceso de desarrollo** (para trazabilidad):

- Todo el módulo fue desarrollado en sesiones de Claude Code sobre esta
  rama, guiado por el auditor en español.
- Se ejecutó una **revisión adversarial automatizada de 28 agentes** sobre
  `validar_furips.py` (run `wf_d111dff9-71c`): 4 lentes de revisión
  (corrección, seguridad, rendimiento, cobertura) + verificación por
  refutación de cada hallazgo; **22 hallazgos confirmados y corregidos** el
  mismo día (commit 39449d8). Los hallazgos "plausibles pero refutados" se
  descartaron documentadamente.
- La memoria entre sesiones se institucionalizó con `BITACORA.md` (qué se
  hizo, pendiente, para mañana, en lenguaje de auditor) y `CLAUDE.md`
  (obligación de leerla al iniciar y actualizarla al terminar cada sesión).

---

## 9. AUTOMATIZACIONES

| Automatización | Cuándo | Cómo |
|---|---|---|
| Autoinstalación de dependencias | Al doble clic de cualquier `.cmd` | `%PYEXE% -c "import X"` y si falla `pip install --quiet --user X`; pdfplumber es best-effort |
| Detección de Python | Ídem | prueba `py -3` → `python` → `python3` ejecutando `-c "import sys"` |
| Autodetección del Excel a completar | `COMPLETAR_INFORME_XML.cmd` | patrón `INFORME*XML*.xlsx` en la carpeta, luego cualquier `.xlsx`, o el arrastrado |
| Arrastrar y soltar carpetas/archivos sobre el `.cmd` | Todos los lanzadores | `%~1` como parámetro |
| Apertura del navegador | App web | `start "" http://localhost:8010` |
| Normalización CRLF | En cada commit | `.gitattributes` con `*.cmd text eol=crlf` |
| Purga de trabajos web | En cada nueva validación | `_limpiar_trabajos_viejos(max_trabajos=20)` |
| CI del repo (pytest + ruff) | En cada push del PR | preexistente; esta rama arregló dos fallas que ya venían rotas (ver §10) |

No se dejaron tareas programadas (cron/Routines): el usuario rechazó
explícitamente la programación de auto-chequeos, y esa preferencia se
respeta como norma de la sesión.

---

## 10. ARCHIVOS MODIFICADOS (lista completa con su cambio)

**Nuevos:**

| Archivo | Qué contiene |
|---|---|
| `tools/adres/validar_furips.py` | Motor validador FURIPS completo (creado en 6763491; endurecido en 39449d8 con los 22 arreglos; agrupación por nombre de archivo en 4212095; direcciones + PDFs escaneados en d332b66; representación gráfica DIAN en c70102d; ruff en 122ac13). |
| `tools/adres/VALIDAR_FURIPS.cmd` | Lanzador de doble clic. |
| `tools/adres/README_validar_furips.md` | Guía de uso del validador. |
| `tools/generar_informe_baja_cartera.py` | Informe de baja (creado en eddfec0; Excel+Word juntos en 840b1c1; carpeta plana + progreso en f0c3c45). |
| `tools/INFORME_BAJA_CARTERA.cmd` | Lanzador. |
| `tools/README_informe_baja_cartera.md` | Guía. |
| `tools/UNIR_PDFS.cmd`, `tools/PDF_A_CMD.cmd` | Bots originales del usuario, incorporados al repo sin modificar (217c91b). |
| `tools/PDF_A_CMD_EN_CARPETA.cmd` | Nuevo bot carpeta CMD_CONVERTIDOS (1f031de; el arreglo CRLF llegó en 9559dd2). |
| `validador-adres/` completo (`app.py`, `static/index.html`, `static/styles.css`, `static/app.js`, `VALIDADOR_ADRES_WEB.cmd`, `Dockerfile`, `requirements.txt`, `README.md`) | App web (91c0b99) + interfaz v2 (8791fdc). |
| `tools/completar_informe_xml_dian.py` | Bot DE4401 (9900fd1; subcarpetas por factura en 8b422d7; v2.1 ZIP+DIAGNOSTICO en daf3a6d). |
| `tools/COMPLETAR_INFORME_XML.cmd` | Lanzador con `RUTA_FACTURAS` editable. |
| `BITACORA.md` | Memoria común (083ba37, actualizada en cada sesión). |
| `CLAUDE.md` | Instrucciones de sesión (leer/actualizar bitácora, responder en español, regla CRLF, flujo de entrega). |
| `.gitattributes` | `*.cmd text eol=crlf` (9559dd2 + renormalización 0079d76). |
| `docs/ENTREGA_MODULO_ADRES_FURIPS.md` | Este documento. |

**Modificados (preexistentes):**

| Archivo | Qué cambió |
|---|---|
| `tests/test_api/test_heatmap_actividad.py` | La semilla usaba fechas fijas (2026-04-20) contra un endpoint con ventana móvil de 90 días → los tests caducaban solos ("podredumbre de fechas"). Se creó el ayudante `_lunes_reciente()` (lunes de la semana pasada) (24de86a). |
| `tests/test_api/test_por_dia_semana.py` | Mismo arreglo `_lunes_reciente()`. |
| `tests/test_api/test_lotes.py` | Comparaba byte a byte dos Excel generados por openpyxl (que SIEMPRE difieren por marcas de tiempo internas) → flaky. Ahora compara contra los bytes realmente subidos. |
| `tests/test_core/test_settings_env_vacias.py` | Se añadió `AGENTE_LOTES_TOKEN` a la lista de variables permitidas con default vacío. |

Ambas fallas de CI eran preexistentes, no causadas por esta rama; se
arreglaron para dejar el PR #176 en verde.

---

## 11. DEPENDENCIAS NUEVAS

Instalables por pip (las versiones mínimas están en
`validador-adres/requirements.txt`; los `.cmd` instalan la última):

- `openpyxl >= 3.1` — todos los Excel.
- `pypdf >= 4.0` — lectura de PDF (motor de respaldo).
- `pdfplumber >= 0.11` — lectura de PDF (motor preferido; OPCIONAL, todo
  funciona sin él).
- `python-docx` — solo el informe de baja (Word).
- `fastapi >= 0.110`, `uvicorn >= 0.29`, `python-multipart >= 0.0.9` — solo
  la app web.

Nota de entorno: en Linux, pdfplumber puede fallar al importar por
`_cffi_backend`; se resuelve con `pip install --upgrade cffi cryptography`
(ocurrió en el entorno de desarrollo).

---

## 12. CONFIGURACIÓN

- **`tools/COMPLETAR_INFORME_XML.cmd` línea 23**:
  `set "RUTA_FACTURAS=\\172.16.32.83\factura_electronica_net22\202607\FACTURAS_SALUD"`
  — ÚNICA ruta de servidor grabada en un archivo; editable por el auditor;
  cambia cada período (`202607` = julio 2026).
- **Puerto de la app web**: 8010 (en `VALIDADOR_ADRES_WEB.cmd` y en
  `app.py`).
- **`MAX_MB_ARCHIVO = 500`** (app web, por archivo subido).
- **`max_trabajos = 20`** (trabajos retenidos en memoria).
- **`MIN_TEXTO_PDF = 200`** (umbral PDF legible del validador).
- **`VERSION = "2.1 (23 de julio de 2026)"`** (bot DE4401).
- **`.gitattributes`**: `*.cmd text eol=crlf`.
- **No hay tokens, contraseñas ni variables de entorno nuevas.** (El
  `AGENTE_LOTES_TOKEN` que aparece en tests es de otro frente del repo; aquí
  solo se permitió su default vacío en un test.)
- Docker: `validador-adres/Dockerfile` se construye desde la RAÍZ del repo
  (necesita copiar `tools/adres/`).

---

## 13. RIESGOS Y LECCIONES (qué puede romperse y cómo resolverlo)

1. **CRLF en los `.cmd` (el riesgo #1).** `cmd.exe` NO encuentra las
   etiquetas `goto`/`call` si el archivo tiene finales LF: la ventana se
   cierra sin hacer NADA (así falló la primera versión de
   PDF_A_CMD_EN_CARPETA: "NO ME GENERA NADA"). Cualquier editor/herramienta
   que escriba LF rompe los bots. Protección: `.gitattributes` ya fuerza
   CRLF; al crear un `.cmd` nuevo, verificar con `file` que diga "CRLF".
2. **Acoplamiento app web ↔ motor.** `validador-adres/app.py` importa el
   motor por ruta relativa (`../tools/adres`). Si al consolidar se mueve
   una carpeta sin la otra, la app no arranca. Mantener la estructura o
   convertir el motor en paquete instalable.
3. **Asociación por número en el nombre.** Todo el cruce de soportes
   depende de que el número de factura aparezca en el nombre del archivo o
   de su carpeta. Un repositorio con nombres 100% genéricos y SIN carpetas
   por factura no es asociable por nombre (el bot DE4401 lo mitiga leyendo
   el número por dentro del XML; el validador FURIPS no tiene ese
   fallback).
4. **Extracción XML por regex.** `analizar_xml` no usa un parser XML
   completo sino regex sobre el texto des-escapado. Es robusto ante los
   AttachedDocument reales de la DIAN (CDATA/entidades) pero un cambio
   fuerte de esquema requeriría revisión.
5. **Excel de openpyxl nunca es byte-idéntico** entre corridas (marcas de
   tiempo internas). NO comparar por bytes en tests ni en scripts (falla
   real corregida en `test_lotes.py`).
6. **Tests con fechas fijas caducan.** Endpoints con ventanas móviles deben
   probarse con fechas relativas (`_lunes_reciente()`), no con semillas
   fijas.
7. **Formato de miles vs prosa.** Aplicar `.replace(",", ".")` a un texto
   completo corrompe las comas de la prosa (error real). Usar ayudantes
   puntuales tipo `_pesos()` solo sobre el número.
8. **Regex de ID de factura DIAN.** `<(?:\w+:)?ID[^>]*>` con IGNORECASE
   captura `<cbc:IdentificationCode>` (devolvía "CO"). El lookahead
   `ID(?=[\s>])` es obligatorio si se copia este patrón.
9. **PDF escaneados.** Sin OCR no hay cruce automático (quedan "SIN
   TEXTO"). Si se necesita cruce completo, aplicar OCR antes (pendiente 6).
10. **Representación gráfica DIAN.** La factura PDF "bonita" de la DIAN no
    trae datos del paciente y escribe el número con guion (`HUS-372720`);
    sin el manejo especial implementado, genera falsos "NO ENCONTRADO".
11. **Carpetas de red lentas.** Leer cientos de PDF/XML por SMB tarda; los
    bots registran progreso y el informe de baja omite carpetas con >25 PDF
    no identificables para no parecer colgados.
12. **App web sin autenticación.** Aceptable en red interna; NO exponerla a
    internet sin agregar login (mejora futura ya identificada).
13. **`pkill` devuelve 144 en cadenas `&&`** y aborta el resto de la cadena
    (lección del entorno de desarrollo: ejecutarlo por separado).
14. **Falsos tokens de factura.** El regex `[A-Z]{2,}0*\d{4,}` también
    "reconoce" nombres DIAN (`AD0901…`) como claves; son inofensivas (nunca
    se consultan) pero inflan el conteo del índice del bot DE4401.

---

## 14. DEPENDENCIAS CON OTROS MÓDULOS

- **`validador-adres/` → `tools/adres/validar_furips.py`**: la app web usa
  el motor tal cual (misma lógica, mismo Excel).
- **`validar_furips.py` → `rips_lectura.py` / `factura_lectura.py`**:
  módulos compartidos preexistentes del paquete ADRES.
- **`generar_informe_baja_cartera.py` → salida de `UNIR_PDFS.cmd`**: el
  informe de baja se alimenta del PDF unido que genera ese bot.
- **`completar_informe_xml_dian.py` → repositorio de facturación**
  (`\\172.16.32.83\factura_electronica_net22\<período>\FACTURAS_SALUD`,
  subcarpeta por factura) y → formato del Excel de devoluciones de NUEVA
  EPS (encabezados exactos: FACTURA, FAC, VALOR FACTURA, FECHA DE FACTURA,
  FECHA DE RADICIAION [sic, así viene], COD DEVOLUCION + las 7 columnas a
  llenar).
- **Ningún componente de esta rama modifica ni depende de `app/`** (la
  plataforma Motor Glosas) más allá de convivir en el mismo repo. Los tests
  arreglados sí pertenecen a la plataforma, pero el arreglo es neutro.

---

## 15. PENDIENTES (estado al 27 de julio de 2026)

1. **Fusionar el PR #176** (contiene TODO lo del 21–23 de julio: direcciones,
   PDFs escaneados/DIAN, app web, bot de carpeta, arreglos CRLF, bot DE4401
   v2.1). Hasta que no se fusione, la rama principal no tiene nada de eso.
2. **Validar la corrida v2.1 del bot DE4401 con datos reales.** Historial
   completo del caso: 1.ª corrida del usuario = 411/411 "SIN XML" (causa:
   subcarpetas por factura con nombres genéricos); se corrigió (v2.0);
   2.ª corrida = mismo resultado, sin poder distinguir a distancia si corrió
   la versión vieja o qué había en la ruta; se creó la v2.1 (lee XML dentro
   de ZIP + hoja DIAGNOSTICO + versión visible). **La corrida del usuario
   con v2.1 aún no se ha confirmado** — es el hilo abierto más importante.
   Si vuelve a salir "SIN XML", la hoja DIAGNOSTICO del Excel dirá la causa.
3. Confirmar en el servidor que `PDF_A_CMD_EN_CARPETA.cmd` corregido genera
   la carpeta `CMD_CONVERTIDOS`.
4. Corregir los datos de las **27 facturas con errores** (de la corrida real
   de 50 facturas ADRES: 27 con errores, 18 por revisar, 5 cumplen) antes de
   radicar.
5. Completar soportes faltantes: a **HUS410606 y HUS472103** les faltan RIPS
   y CUV.
6. Completar los informes de trabajo social de las facturas de baja marcadas
   "NOTA DE REVISIÓN".
7. OCR para PDF escaneados si se quiere cruce automático completo.
8. Mejoras futuras de la app web SOLO si se piden: usuarios/contraseñas,
   historial persistente de validaciones, exportar hallazgos filtrados.
9. Del README del módulo ADRES quedan sin construir (ya estaban planeados
   antes de esta rama): `generar_fur.py`, `generar_json_zip.py`,
   `cargar_masivo_adres.py`.

**Soluciones descartadas / cambios de enfoque documentados:**

- **Descubrimiento de soportes por carpeta** (versión inicial del
  validador): descartado cuando se comprobó que el servidor de cartera
  guarda TODO en una carpeta plana → se reemplazó por agrupación por número
  de factura en el nombre (4212095).
- **Índice del bot DE4401 solo por nombre de archivo** (v1): descartado al
  comprobar la estructura real de subcarpetas → v2.0 por cadena de
  carpetas, v2.1 además por dentro de los ZIP.
- **Elegir el XML solo por mtime**: descartado; ahora se prioriza número en
  el nombre y se verifica el número POR DENTRO con reintento.
- **Auto-chequeos programados del PR**: el usuario los rechazó; no
  programar tareas de seguimiento automático en este proyecto.

---

## 16. RECOMENDACIONES PARA FUSIONARLO EN EL PROYECTO PRINCIPAL

1. **Fusionar primero el PR #176 en `motor-glosas`** (rama principal de
   este repo) para que el punto de partida sea único y verde en CI.
2. Al copiar al proyecto consolidado, **mover las carpetas en bloque**:
   `tools/adres/` + `validador-adres/` deben conservar su posición relativa
   (o refactorizar el `sys.path.insert` de `app.py` a un import de paquete).
3. **Llevar `.gitattributes`** (o añadir la regla `*.cmd text eol=crlf` al
   del proyecto principal) ANTES de commitear cualquier `.cmd`, y
   renormalizar (`git add --renormalize .`).
4. Conservar los `README_*.md` y `BITACORA.md`: son parte del conocimiento
   operativo, no adornos.
5. Si el proyecto principal tiene su propio CI: incluir `ruff check` y
   `ruff format --check` (el código cumple ruff 0.15.22) y NO escribir
   tests que comparen Excel por bytes ni usen fechas fijas contra ventanas
   móviles.
6. Verificación post-fusión mínima (checklist):
   - `VALIDAR_FURIPS.cmd` sobre una carpeta con 2–3 facturas de muestra →
     produce el Excel de 7 hojas;
   - `VALIDADOR_ADRES_WEB.cmd` → abre el navegador, valida un ZIP de
     muestra y descarga el Excel;
   - `INFORME_BAJA_CARTERA.cmd` sobre una carpeta con PDF unidos → Word +
     Excel;
   - `COMPLETAR_INFORME_XML.cmd` con el Excel de devoluciones → hoja
     DIAGNOSTICO presente y versión v2.1 en consola;
   - `file *.cmd` → todos "with CRLF line terminators".
7. Los entregables al auditor siempre son ARCHIVOS listos para copiar al
   servidor (no instrucciones de git): mantener ese flujo de entrega.
8. No renombrar los `.cmd`: los auditores ya los conocen por esos nombres.

---

## 17. RESUMEN EJECUTIVO (para el desarrollador que lo mantenga)

Este módulo es un **paquete de auditoría de facturación en salud para el
HUS** con cuatro productos: (1) un **validador masivo FURIPS** contra la
Circular 022/2023 de la ADRES que además cruza cada factura con sus
soportes reales y entrega un Excel semaforizado de 7 hojas; (2) una **app
web** (FastAPI + JS puro, sin internet) que expone ese mismo motor con
tablero interactivo; (3) un **generador del informe de baja de cartera**
(Word + Excel, Res. 577/2019) que lee los PDF unidos y transcribe trabajo
social; y (4) un **bot de devoluciones DE4401** que lee los XML DIAN del
repositorio de facturación (incluso dentro de ZIP y en subcarpetas por
factura) y redacta el argumento de glosa listo para el portal DGH.

Lo que hay que saber para no romperlo: los `.cmd` viven o mueren por el
CRLF; la app web importa el motor por ruta relativa; TODOS los cruces
dependen de la normalización del número de factura (`norm_factura`) y de
que ese número aparezca en el nombre del archivo, de su carpeta, o dentro
del XML; los PDF escaneados no se cruzan (quedan "SIN TEXTO"); y los Excel
de openpyxl nunca son byte-idénticos. El usuario final es un auditor no
programador: todo se entrega como archivos de doble clic, en español, y la
memoria del proyecto vive en `BITACORA.md` — léela al empezar y actualízala
al terminar, como ordena `CLAUDE.md`.

El hilo abierto al momento de esta entrega: confirmar con la corrida real
del usuario que la v2.1 del bot DE4401 encuentra los XML del servidor; la
hoja DIAGNOSTICO del Excel resultante fue diseñada precisamente para
resolver ese caso a distancia.
