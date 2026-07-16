# Kit de bots de auditoría HUS — guía para gestores

**Todo se usa igual:** copia los `.cmd` a una carpeta (puede ser la compartida),
dale **doble clic a `MOTOR_HUS.cmd`** y elige el número del bot. La primera vez
el bot instala solo lo que necesita (Python, sin administrador). Ninguno toca
los archivos originales.

## El menú (`MOTOR_HUS.cmd`)

Un solo doble clic muestra los 12 bots numerados y deja constancia de cada uso
en **`REGISTRO_BOTS.csv`** (fecha, usuario, equipo y bot) — de ahí sale el
informe de gestión para gerencia sin trabajo manual.

## Los bots del ciclo de glosas

| # | Bot | Qué hace |
|---|-----|----------|
| 9 | **VERIFICAR_RADICACION** | **Antes de radicar**: revisa que cada XML traiga `NUMERO_CONTRATO` y validación DIAN, que los FURIPS tengan todas sus líneas completas y que cada factura tenga soportes. Previene la glosa en vez de pelearla. |
| 10 | **CRUZAR_GLOSAS** | Cuando llega el Excel de glosas de la EPS: lo cruza con los XML radicados y arma `CRUCE_GLOSAS.xlsx` + `BORRADORES_RESPUESTA.txt` con el borrador por causal (sin contrato, tarifas, soportes, autorización...) citando la evidencia real del XML. Los `[COMPLETAR: ...]` son del auditor. |
| 11 | **SEMAFORO_GLOSAS** | Plazos de respuesta en **días hábiles** (festivos de Colombia incluidos): NEGRO vencida, ROJO 1-4, AMARILLO 5-10, VERDE 11+. Para no perder una glosa por extemporaneidad. |
| 12 | **BUSCAR_FACTURA** | Con `facturas.txt` al lado, rastrea la carpeta compartida y copia TODOS los archivos de esas facturas a `SOPORTES_ENCONTRADOS\<factura>\`. Arma el paquete de respuesta en minutos. |
| 8 | **REVISAR_XML** | Saca a un Excel la información de contrato de los XML (el anexo de prueba de la glosa "sin contrato"). |
| 13 | **INFORME_GERENCIA** | Genera el informe de gestión para gerencia desde la bitácora `REGISTRO_BOTS.csv`: usos por bot, por persona y por semana, en HTML listo para imprimir. Se abre solo al terminar. |
| 14 | **VIGILANTE_NOCTURNO** | Deja programada una tarea de Windows que **todas las noches** convierte los `.txt` nuevos de la carpeta que elijas (sin doble clic de nadie). Instalar/probar/desinstalar desde su menú; todo queda en `VIGILANTE_LOG.txt`. |

## Los bots de archivos

| # | Bot | Qué hace |
|---|-----|----------|
| 1 | UNIR_PDFS | Une los PDF de cada carpeta en un consolidado (y deja copia `.cmd`). |
| 2 | PDF_A_CMD | Copia `.cmd` de cada PDF individual. |
| 3 | EXCEL_A_CMD | Copia `.cmd` de cada Excel. |
| 4 | COMPRIMIR_ZIP | Baja el peso de los `.zip`. |
| 5 | PARTIR_ZIP_30MB | Parte un `.zip` en pedazos de menos de 30 MB. |
| 6 | TXT_A_EXCEL | Cada `.txt` (FURIPS, reportes) queda como `.csv` por comas + Excel. |
| 7 | EXCEL_A_CSV | El reverso: cada Excel queda como `.csv` por comas para plataformas. |

## Reglas que cumplen todos

- **Nunca tocan el archivo original** ni pisan archivos que no generaron ellos.
- Los datos de facturación van protegidos: códigos con ceros a la izquierda,
  NIT largos, fechas y horas quedan como texto en los Excel.
- Un archivo dañado no detiene el resto: se reporta y se sigue.
- Cada bot deja su resultado **junto al `.cmd`** con nombre claro
  (`VERIFICACION_RADICACION.xlsx`, `CRUCE_GLOSAS.xlsx`, `SEMAFORO_GLOSAS.xlsx`...).

## El flujo recomendado

1. **Antes de radicar** → `VERIFICAR_RADICACION` (corrige lo que salga en amarillo).
2. **Llegó una glosa** → `SEMAFORO_GLOSAS` (¿cuánto plazo queda?) y
   `CRUZAR_GLOSAS` (evidencia + borrador por causal).
3. **Armar el paquete** → `BUSCAR_FACTURA` (recolecta los soportes) y
   `UNIR_PDFS` / `COMPRIMIR_ZIP` / `PARTIR_ZIP_30MB` para dejarlo listo.
4. Los borradores siempre los **revisa y firma el auditor** — el bot pone la
   evidencia, el criterio lo pone el humano.
