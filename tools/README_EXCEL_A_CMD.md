# EXCEL_A_CMD — bot de doble clic para dejar cada Excel como archivo .cmd

Por cada Excel de la carpeta (y sus subcarpetas) deja **una copia idéntica con
extensión `.cmd`**, lista para subirla donde exigen ese formato. El Excel
original **nunca se toca**.

```
INFORME.xlsx   →  INFORME.cmd
RIPS_2026.xlsm →  RIPS_2026.cmd
VIEJO.xls      →  VIEJO.cmd
```

Es el hermano del bot `UNIR_PDFS.cmd` (que une PDFs): misma experiencia, solo
que este convierte Excel. Reconoce `.xlsx`, `.xlsm`, `.xlsb` y `.xls`.

## Cómo se usa

1. **Copia** `EXCEL_A_CMD.cmd` a la carpeta donde tienes tus Excel.
2. **Doble clic**.
3. Junto a cada Excel aparece su copia `.cmd`.

> ⚠️ Los `.cmd` generados **no son programas** — son el mismo Excel con otra
> extensión. **No les des doble clic.** Para abrir uno en Excel, renómbralo de
> vuelta a `.xlsx` (o su extensión original).

## Detalles útiles

- **No hay que instalar nada a mano**: si el PC no tiene Python, el bot lo
  instala solo la primera vez (winget o python.org, sin administrador, solo
  internet). No usa ningún componente adicional.
- **Se puede correr las veces que quieras**: si el Excel cambió, la copia
  `.cmd` se refresca; nunca queda una versión vieja.
- **Seguridad**: jamás pisa un `.cmd` que no sea un Excel (por ejemplo un
  script real o los propios bots) — lo omite con un aviso. Los temporales de
  Office (`~$...`) se ignoran.
- **Tolerante a fallos**: un archivo bloqueado o con error no detiene el
  resto; se reporta y se sigue.

## Opciones avanzadas (línea de comandos)

```powershell
py tools\excel_a_cmd.py "D:\USUARIO CARTERA\Documents\SOPORTES"
py tools\excel_a_cmd.py . --simulacro      # muestra qué haría, sin escribir
py tools\excel_a_cmd.py . --sin-recursion  # solo la carpeta raíz
```
