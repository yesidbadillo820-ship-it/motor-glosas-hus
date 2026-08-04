# COMPRIMIR_ZIP — bot de doble clic para bajar el peso de los .zip

Reduce el tamaño de los archivos `.zip` **recomprimiendo su contenido**: los
PDF (escaneos a 150 dpi, como `UNIR_PDFS`) y las imágenes `.jpg`/`.png`. Word,
Excel y lo demás se dejan igual, y el zip se vuelve a armar al máximo nivel de
compresión.

> **Por qué así:** un `.zip` ya está comprimido, así que "recomprimir el zip"
> no baja casi nada. El peso se baja achicando los archivos de adentro (sobre
> todo los PDF con escaneos). Por eso este bot los recomprime y re-arma el zip.

```
ENVIO_HUS.zip  (20 MB)  →  ENVIO_HUS_LIGERO.zip  (10 MB)
```

## Cómo se usa

1. **Copia** `COMPRIMIR_ZIP.cmd` a la carpeta donde tienes tus `.zip`.
2. **Doble clic**.
3. Al lado de cada zip aparece su versión `<nombre>_LIGERO.zip`.

## Detalles útiles

- **El zip original nunca se toca.** El resultado es un archivo nuevo
  `_LIGERO.zip`. (Si prefieres sobrescribir el original, corre el motor con
  `--reemplazar`.)
- **Solo lo reemplaza si de verdad baja**: si el contenido ya estaba comprimido,
  te avisa "sin margen" y no crea el `_LIGERO`.
- **Red de seguridad**: cada PDF/imagen solo se recomprime si queda más liviano;
  el zip nuevo se verifica (abre bien y conserva el mismo número de archivos)
  antes de guardarse. Word/Excel salen idénticos.
- **No hay que instalar nada a mano**: si el PC no tiene Python, el bot lo
  instala solo la primera vez; también instala los componentes de compresión
  (pymupdf y Pillow). Solo necesita internet la primera vez.
- **Se puede correr las veces que quieras**: los `_LIGERO.zip` que genera se
  ignoran en corridas siguientes.
- **Tolerante a fallos**: un zip cifrado o dañado se omite con aviso; el resto
  se procesa igual.

## La familia de bots

| Bot | Qué hace |
|---|---|
| `UNIR_PDFS.cmd` | Une los PDF de cada carpeta en uno, lo comprime y deja su `.cmd` |
| `PDF_A_CMD.cmd` | Convierte cada PDF individual en su copia `.cmd` |
| `EXCEL_A_CMD.cmd` | Convierte cada Excel en su copia `.cmd` |
| `COMPRIMIR_ZIP.cmd` | Baja el peso de los `.zip` recomprimiendo su contenido (este bot) |

## Opciones avanzadas (línea de comandos)

```powershell
py tools\comprimir_zip.py "D:\USUARIO CARTERA\Documents\ENVIOS"
py tools\comprimir_zip.py . --simulacro      # muestra qué haría, sin escribir
py tools\comprimir_zip.py . --reemplazar     # sobrescribe el zip original
py tools\comprimir_zip.py . --sin-recursion  # solo la carpeta raíz
```
