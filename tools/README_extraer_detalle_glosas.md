# Extraer detalle de glosas y armar el Excel de entrega

Complementa al organizador de correos: toma una **carpeta de día** ya archivada
en el servidor de glosas, lee los adjuntos de cada entidad y produce el
**Excel de entrega** con el formato del consolidado de gestores.

## Qué hace

1. Recorre `<día>\<CATEGORÍA>\<ENTIDAD>\` (acepta las marcas manuales:
   `DEVOLUCIONES OK`, `DISPENSARIO SOFIA OK`, `RATIFICADAS`...).
2. Extrae el detalle **por factura** de los formatos conocidos, incluso dentro
   de `.zip`:

   | Fuente | Archivo | Cómo |
   |---|---|---|
   | AUDITOOL / DISPENSARIO | `AUDITORIA_GLOSA_*.csv` | por servicio, agrupa por factura |
   | FAMISANAR | `DEVYGLOSAS*.txt` | códigos `DE*` van a DEVOLUCIONES |
   | SURA | `*MASIVO*.TXT` | por glosa |
   | SANITAS | `.xlsx` hoja `Glosa` | por ítem, usa VALOR REAL GLOSA |
   | POLICÍA / GÉNESIS | `.xlsx` hoja `OBJECIONES` | CRNCXC / CROVALOBJ |
   | FACTRAMED / NUEVA EPS | `.xlsx` `Registro_Inforamcion...` | filtrado por ventana de fechas |
   | AXA | PDF de liquidación | factura + valor Glosado por línea |
   | SEGUROS BOLÍVAR | PDF de acta | factura + suma de Val. Glosado inicial |
   | PDF escaneado (`DEV*`) | — | fila mínima con el radicado, para completar a mano |

   La categoría del **contenido manda** sobre la carpeta: un código `DE*`
   (devolución) va a la hoja DEVOLUCIONES aunque el correo se haya guardado en
   INICIAL. Los correos impresos a PDF se ignoran (son evidencia, no datos).
3. Agrupa por (categoría, empresa, factura) sumando valores y genera
   `ENTREGA_GLOSAS_<fecha>.xlsx` con hojas **INICIAL / RATIFICADA /
   DEVOLUCIONES** (encabezados idénticos al consolidado, listos para copiar y
   pegar) y una hoja **RESUMEN** con totales y archivos sin parser.
4. Asigna **RESPONSABLE** según el mapeo entidad→gestor
   (`gestores_glosas.ejemplo.json`, derivado del consolidado histórico;
   editable) y calcula **FECHA DE VENCIMIENTO**: notificación + **15 días
   hábiles** (inicial) o **7** (ratificada), con festivos colombianos.

El consolidado maestro **nunca se toca**: la entrega es un archivo nuevo por
corrida (si ya existe, escribe uno con la hora en el nombre, no sobreescribe).

## Uso rápido

```bash
# Ver el resumen sin escribir nada
py extraer_detalle_glosas.py --carpeta "Z:\SERVIDOR GLOSAS\F\RECEPCIÓN DE GLOSAS (NO ELIMINAR CARPETA)\03-GLOSAS ESCANEADAS 2.0 (NO ELIMINAR CARPETA )\2026\07 JULIO\02" --dry-run

# Generar el Excel de entrega en la misma carpeta del día
py extraer_detalle_glosas.py --carpeta "...\2026\07 JULIO\02"

# Con mapeo propio de gestores y ventana FACTRAMED más amplia
py extraer_detalle_glosas.py --carpeta "...\02" --config mis_gestores.json --ventana-factramed 15
```

## Argumentos

| Argumento | Default | Descripción |
|---|---|---|
| `--carpeta` | (obligatorio) | Carpeta del día (`...\2026\07 JULIO\02`) |
| `--salida` | `ENTREGA_GLOSAS_<fecha>.xlsx` en la carpeta | Ruta del Excel |
| `--config` | mapeo interno | JSON de gestores por entidad |
| `--ventana-factramed` | `7` | Días hacia atrás de `Fecha_Hora_Glosa` a incluir del Excel de FACTRAMED (trae histórico acumulado) |
| `--dry-run` | — | Solo muestra el resumen |
| `--log` | — | Archivo de log opcional |

## Configurar gestores

Copia `gestores_glosas.ejemplo.json` y edítalo. Cada entidad (por el nombre de
su carpeta, con o sin marcas) define la EMPRESA formal y el gestor por
categoría:

```json
"COOSALUD": {
  "empresa": "COOSALUD ENTIDAD PROMOTORA DE SALUD S.A.",
  "INICIAL": "DIANEYDA QUINTERO",
  "RATIFICADA": "JORGE GUARIN",
  "DEVOLUCIONES": "ALBA PEREZ"
}
```

Si falta la categoría o la entidad, la fila sale con `POR ASIGNAR` para que la
coordinadora la reparta.

## Límites conocidos

- Los `DEV*.pdf` de AUDITOOL son escaneados (imagen): la fila sale con el
  radicado y la observación "completar a mano", sin valor.
- El Excel de FACTRAMED trae el acumulado histórico: la ventana de fechas evita
  duplicar, pero si procesas el mismo día dos veces con ventanas distintas
  pueden repetirse facturas entre entregas — el consolidado es la fuente de
  verdad para deduplicar.
- Las liquidaciones de SEGUROS MUNDIAL son notificaciones de pago: la factura
  sale con observación y sin valor de glosa.
