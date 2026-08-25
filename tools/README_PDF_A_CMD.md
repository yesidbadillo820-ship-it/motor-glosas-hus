# PDF_A_CMD — bot de doble clic para dejar cada PDF como archivo .cmd (sin unir)

Por cada PDF de la carpeta (y sus subcarpetas) deja **una copia idéntica con
extensión `.cmd`**, lista para subirla donde exigen ese formato — **de a uno,
sin unir nada**. Si una carpeta tiene un solo PDF, ese solo se convierte.

```
FACTURA.pdf   →  FACTURA.cmd
EPICRISIS.pdf →  EPICRISIS.cmd
```

El PDF original **nunca se toca**.

## Los tres bots de la familia

| Bot | Qué hace |
|---|---|
| `UNIR_PDFS.cmd` | **Une** los PDF de cada carpeta en un consolidado, lo comprime y deja su `.cmd` |
| `PDF_A_CMD.cmd` | Convierte **cada PDF individual** en su copia `.cmd` (este bot) |
| `EXCEL_A_CMD.cmd` | Convierte **cada Excel** en su copia `.cmd` |

## Cómo se usa

1. **Copia** `PDF_A_CMD.cmd` a la carpeta donde tienes tus PDF.
2. **Doble clic**.
3. Junto a cada PDF aparece su copia `.cmd`.

> ⚠️ Los `.cmd` generados **no son programas** — son el mismo PDF con otra
> extensión. **No les des doble clic.** Para ver uno como documento,
> renómbralo de vuelta a `.pdf`.

## Detalles útiles

- **No hay que instalar nada a mano**: si el PC no tiene Python, el bot lo
  instala solo la primera vez (winget o python.org, sin administrador, solo
  internet). No usa ningún componente adicional.
- **Se puede correr las veces que quieras**: si un PDF cambió, su copia `.cmd`
  se refresca; nunca queda una versión vieja.
- **Seguridad**: jamás pisa un `.cmd` que no sea un PDF (por ejemplo un script
  real, los propios bots, o la copia `.cmd` de un Excel con el mismo nombre) —
  lo omite con un aviso.
- **Convive con UNIR_PDFS**: si lo corres sobre carpetas ya procesadas, el
  `_UNIDO_*.cmd` simplemente se refresca (es contenido PDF).
- **Tolerante a fallos**: un archivo bloqueado no detiene el resto.

## Opciones avanzadas (línea de comandos)

```powershell
py tools\pdf_a_cmd.py "D:\USUARIO CARTERA\Documents\SOPORTES"
py tools\pdf_a_cmd.py . --simulacro      # muestra qué haría, sin escribir
py tools\pdf_a_cmd.py . --sin-recursion  # solo la carpeta raíz
```
