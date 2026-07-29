# PARTIR_ZIP_30MB — bot de doble clic para partir .zip en pedazos < 30 MB

Parte cada `.zip` en **pedazos independientes de menos de 30 MB cada uno**, para
poder subirlos a un chat o portal con tope de tamaño. Primero recomprime el
contenido (para que hagan falta menos partes) y luego reparte los archivos.

```
JULIO.zip  (102 MB)  →  JULIO_parte1_de4.zip  (29 MB)
                        JULIO_parte2_de4.zip  (29 MB)
                        JULIO_parte3_de4.zip  (29 MB)
                        JULIO_parte4_de4.zip  (15 MB)
```

Cada parte es un zip **normal que se abre por sí solo** (no es un zip
multivolumen). Subes **todas** las partes al chat; quien las reciba abre cada
una por separado.

## Cómo se usa

1. **Copia** `PARTIR_ZIP_30MB.cmd` a la carpeta donde tienes tus `.zip`.
2. **Doble clic**.
3. Al lado de cada zip aparecen sus partes `<nombre>_parteN_deM.zip`.

## Detalles útiles

- **El zip original nunca se toca.** Solo se crean las partes nuevas.
- **Recomprime primero**: los PDF (150 dpi) e imágenes se achican antes de
  partir, así salen menos partes. (Con `--sin-comprimir` solo parte, sin tocar
  la calidad.)
- **Un PDF que solo ya pesa más de 30 MB** se divide por páginas
  (`FACTURA.pdf` → `FACTURA_p1.pdf`, `FACTURA_p2.pdf`) para que quepa.
- **No pierde nada**: todos los archivos y páginas quedan repartidos entre las
  partes; cada parte se verifica antes de guardarse.
- **No hay que instalar nada a mano**: si el PC no tiene Python, el bot lo
  instala solo, junto con los componentes de compresión (pymupdf y Pillow).
- **Se puede correr las veces que quieras**: las partes que genera se ignoran
  en corridas siguientes.

## La familia de bots

| Bot | Qué hace |
|---|---|
| `UNIR_PDFS.cmd` | Une los PDF de cada carpeta en uno (comprimido) + su `.cmd` |
| `PDF_A_CMD.cmd` | Cada PDF individual → su `.cmd` |
| `EXCEL_A_CMD.cmd` | Cada Excel → su `.cmd` |
| `COMPRIMIR_ZIP.cmd` | Baja el peso de un `.zip` (recomprime el contenido) |
| `PARTIR_ZIP_30MB.cmd` | Parte un `.zip` en pedazos < 30 MB (este bot) |

## Opciones avanzadas (línea de comandos)

```powershell
py tools\partir_zip.py "D:\USUARIO CARTERA\Documents\07 JULIO"
py tools\partir_zip.py . --max-mb 30      # tope por parte (por defecto 29)
py tools\partir_zip.py . --sin-comprimir  # solo partir, sin recomprimir
py tools\partir_zip.py . --simulacro      # muestra cuántas partes saldrían
```
