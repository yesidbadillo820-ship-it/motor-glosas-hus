# TXT_A_EXCEL — bot de doble clic: cada .txt queda delimitado por comas (.csv) + Excel (.xlsx)

Por cada `.txt` de la carpeta (y sus subcarpetas, si quieres) deja **dos
archivos junto al original**:

```
FURIPS268001...txt  →  FURIPS268001...csv   (delimitado por comas, para la plataforma)
                    →  FURIPS268001...xlsx  (Excel con columnas, para revisarlo)
```

El `.txt` original **nunca se toca**. Sirve igual para **una sola carpeta** o
**masivamente** sobre carpetas compartidas de red con subcarpetas.

## Por qué el Excel no los abría en columnas

Los `.txt` tipo FURIPS **sí** vienen separados por comas por dentro, pero el
Excel de Colombia usa **punto y coma** como separador regional, así que al
abrirlos muestra todo corrido en una sola columna. Este bot hace la
separación bien y además protege los datos (abajo).

## Qué entiende

El bot mira cada archivo y decide solo:

1. **Ya delimitado**: comas (FURIPS), punto y coma `;`, TAB o barra `|`.
2. **Ancho fijo**: reportes con columnas alineadas con espacios — detecta las
   fronteras de columna por las posiciones que son espacio en *todas* las líneas.
3. Si nada de eso aplica: parte por tandas de 2+ espacios, o deja la línea
   como una sola celda.

Las líneas vacías y las de adorno (`------`, `======`) se descartan.

## Cómo se usa

1. **Copia** `TXT_A_EXCEL.cmd` a la carpeta con los `.txt` (puede ser la
   carpeta compartida de red).
2. **Doble clic**.
3. Te pregunta la carpeta (Enter = donde está el `.cmd`) y si incluye
   **subcarpetas** (Enter = sí).
4. Junto a cada `.txt` quedan su `.csv` y su `.xlsx`.

## Protección de los datos (importante en facturación)

- En el **.xlsx**: los códigos con ceros a la izquierda (`HUS0000533470`,
  `001`), los números de más de 15 dígitos (NIT, CUFE), las fechas
  (`06/03/1962`) y las horas (`02:00`) quedan como **texto** — Excel no los
  daña. Solo lo inequívoco se vuelve número (`480200.00` → 480200). Lo
  ambiguo tipo `480.200` **no se toca**.
- El **.csv** va **delimitado por comas tal cual** (si el archivo ya venía
  por comas, queda idéntico línea a línea), en ANSI, que es lo que esperan
  las plataformas.
- **Jamás pisa archivos ajenos**: si ya existe un `NOMBRE.xlsx` o
  `NOMBRE.csv` que no generó este bot, ese archivo se omite con aviso. Los
  que sí generó el bot se refrescan al volver a correr.

## Detalles útiles

- **No hay que instalar nada a mano**: si el PC no tiene Python, el bot lo
  instala solo la primera vez (winget o python.org, sin administrador), y
  asegura el componente de Excel (openpyxl).
- **Tolerante a fallos**: un archivo dañado o bloqueado no detiene el resto.
- Si un `.txt` gigante supera el millón de filas de Excel, el `.xlsx` se
  reparte en varias hojas (`Datos`, `Datos_2`, ...); el `.csv` no tiene límite.

## Opciones avanzadas (línea de comandos)

```powershell
py tools\txt_a_excel.py "\\servidor\carpeta_compartida\FURIPS"
py tools\txt_a_excel.py . --sin-recursion     # solo la carpeta raíz
py tools\txt_a_excel.py . --simulacro         # muestra qué haría, sin escribir
py tools\txt_a_excel.py . --delimitador ";"   # fuerza el separador de entrada
```
