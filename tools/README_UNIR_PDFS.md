# UNIR_PDFS — bot de doble clic para unir PDF por carpeta (y dejarlos como .cmd)

Une (combina) **todos los PDF de cada carpeta en un solo PDF consolidado** y
deja además **una copia idéntica con extensión `.cmd`**, lista para subirla
donde pidan ese formato. Pensado para armar el soporte único por factura / NE
cuando cada carpeta tiene varios PDF sueltos (factura, epicrisis, notas,
autorizaciones…).

Son dos archivos, pero para el día a día **solo necesitas el `.cmd`**:

| Archivo | Para qué sirve |
|---|---|
| `UNIR_PDFS.cmd` | El **bot**. Lo copias a tu carpeta y le das doble clic. Ya lleva el motor adentro. |
| `unir_pdfs_carpetas.py` | El motor (Python). Solo lo usan quienes quieran correrlo por línea de comandos. |

---

## Cómo se usa (lo normal)

1. **Copia** `UNIR_PDFS.cmd` a la carpeta donde tienes tus PDF.
   Por ejemplo, dentro de `SOPORTES\`, que a su vez tiene una subcarpeta por NE:

   ```
   SOPORTES\
   ├── UNIR_PDFS.cmd      <-- pegas el bot aquí
   ├── 311131\
   │   ├── factura.pdf
   │   ├── epicrisis.pdf
   │   └── autorizacion.pdf
   └── 311136\
       ├── factura.pdf
       └── soporte.pdf
   ```

2. **Doble clic** en `UNIR_PDFS.cmd`.

3. En cada carpeta aparecen **dos archivos** con el mismo contenido:

   ```
   SOPORTES\
   ├── 311131\
   │   ├── _UNIDO_311131.pdf   <-- factura + epicrisis + autorizacion, en un solo PDF
   │   ├── _UNIDO_311131.cmd   <-- copia identica en formato .cmd (para subir)
   │   └── ...
   └── 311136\
       ├── _UNIDO_311136.pdf   <-- factura + soporte
       ├── _UNIDO_311136.cmd
       └── ...
   ```

   - El **`.pdf`** es para abrirlo y revisarlo.
   - El **`.cmd`** es el mismo PDF con la extensión cambiada, para subirlo donde
     exigen archivos `.cmd`.

> ⚠️ **Importante:** los `_UNIDO_*.cmd` generados **no son programas** — son el
> PDF con otra extensión. **No les des doble clic** (Windows intentaría
> ejecutarlos como script y mostraría errores sin sentido). Si necesitas ver uno
> como documento, renómbralo de vuelta a `.pdf`.

El bot recorre la carpeta donde lo pusiste **y todas sus subcarpetas**, así que
puedes ponerlo en la carpeta madre y procesa todos los NE de una sola pasada.

---

## Detalles útiles

- **Orden de las páginas:** los PDF se ordenan por nombre de archivo de forma
  natural (2 antes que 10). Si necesitas un orden exacto, ponle un número
  adelante al nombre: `01_factura.pdf`, `02_epicrisis.pdf`, `03_autorizacion.pdf`.
- **Se puede correr las veces que quieras:** el `_UNIDO_...pdf` que genera nunca
  se vuelve a incluir como entrada, así que no se aniña ni se duplica.
- **Carpetas con un solo PDF** se omiten (no hay nada que unir). Si igual quieres
  generarlas, ver "Opciones avanzadas".
- **PDF dañados** se saltan con un aviso y el resto se une igual (no se cae).
- **Requisitos: ninguno que instalar a mano.** Si el equipo no tiene Python, el
  bot **lo instala solo** la primera vez (usa `winget` o descarga el instalador
  oficial de python.org; no pide permisos de administrador, solo internet y unos
  minutos). Los componentes de PDF (PyPDF2) y de compresión (pymupdf) también los
  instala él solo. Únicamente si las políticas del equipo bloquean instalaciones,
  muestra las instrucciones para hacerlo a mano o pedirlo a SISTEMAS.

---

## Opciones avanzadas (línea de comandos)

Puedes arrastrar opciones al `.cmd` desde una terminal, o correr el motor directo:

```powershell
py tools\unir_pdfs_carpetas.py "D:\USUARIO CARTERA\Documents\SOPORTES"
py tools\unir_pdfs_carpetas.py .  --simulacro     # muestra qué haría, sin escribir
py tools\unir_pdfs_carpetas.py .  --minimo 1      # une aunque haya un solo PDF
py tools\unir_pdfs_carpetas.py .  --sin-recursion # solo la carpeta raíz, sin subcarpetas
```

| Opción | Efecto |
|---|---|
| `--simulacro` | Lista lo que uniría sin crear ningún archivo. |
| `--minimo N` | Mínimo de PDF por carpeta para unirla (por defecto 2). |
| `--prefijo TEXTO` | Cambia el prefijo del resultado (por defecto `_UNIDO_`). |
| `--sin-recursion` | No baja a las subcarpetas; solo procesa la carpeta indicada. |
| `--tambien-cmd` | Deja además la copia `.cmd` del consolidado. El bot `UNIR_PDFS.cmd` ya lo pasa solo. |
| `--comprimir` | Reduce el peso del consolidado (y por lo tanto del `.cmd`). El bot ya lo pasa solo. Requiere `pymupdf` (el bot lo instala). |

Nota: si una carpeta ya tiene su copia `_UNIDO_*.cmd` de una corrida anterior, el
motor la refresca **siempre** al regenerar el consolidado, aunque no le pases
`--tambien-cmd` — así el `.cmd` nunca queda desactualizado respecto al `.pdf`.

### Sobre la compresión

- Los **escaneos a color o en grises de alta resolución** (epicrisis, soportes
  con sellos, fotos) son los que más bajan: la resolución se ajusta a 150 dpi
  (de sobra para leer e imprimir) y se recomprimen como JPEG de buena calidad.
  Ahí el ahorro típico es del 40–80%.
- Los **escaneos en blanco y negro puro** (tipo fax, formato CCITT) ya vienen en
  su mínimo físico: en esos el ahorro es de apenas 2–5% y es normal — no es que
  la compresión "no funcione", es que no hay nada que quitar sin dañar el texto.
- **Red de seguridad**: el archivo solo se reemplaza si de verdad queda más
  liviano, abre bien y conserva todas sus páginas. Ante cualquier duda, el
  consolidado queda tal cual. La compresión **nunca** agranda un archivo.
