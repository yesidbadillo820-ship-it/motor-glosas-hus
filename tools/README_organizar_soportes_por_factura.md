# Cada soporte en la carpeta de su factura (`organizar_soportes_por_factura.py`)

En la carpeta del gestor los soportes se van acumulando sueltos, mezclados con
las carpetas de las facturas que ya están armadas:

```
CAROLINA\
    HUS352904\                              ← carpetas que ya existen
    HUS383781\
    HUS392861-MEDICAMENTOS.pdf              ← sueltos, sin carpeta
    HUS400387 ANGIOTOMOGRAFIA.pdf
    HUS382278- INTERCONSULTAS, FOLIO 17.pdf
```

Este bot **mete cada uno en la carpeta de su factura** y **crea la carpeta si no
existe**. El número lo toma del comienzo del nombre del archivo (`HUS` y los
dígitos), que es como los nombra el equipo.

---

## Cómo se usa

**Lo más fácil: doble clic en `ORGANIZAR_SOPORTES.cmd`.** Pide la carpeta,
muestra primero qué haría y solo mueve si usted escribe **SI**.

Por línea de comandos:

```
REM 1) PRIMERO en simulación: muestra qué haría y no toca nada.
py tools\organizar_soportes_por_factura.py --carpeta "Z:\...\CAROLINA"

REM 2) Si el listado se ve bien, con --aplicar sí mueve.
py tools\organizar_soportes_por_factura.py --carpeta "Z:\...\CAROLINA" --aplicar ^
    --reporte-csv "Z:\...\CAROLINA\SOPORTES_ORGANIZADOS.csv"
```

| Opción | Para qué |
|---|---|
| `--carpeta` | La carpeta del gestor. |
| `--aplicar` | Mover de verdad. **Sin esto solo simula.** |
| `--patron` | Qué archivos mover. Por defecto `*.pdf`; con `*` mueve todo. |
| `--reporte-csv` | Listado de lo que se movió y a dónde. |

---

## Las tres reglas de seguridad

Mover archivos **no se deshace**, así que el bot:

1. **Simula por defecto.** Hay que pedirle `--aplicar` a propósito.
2. **Nunca pisa un archivo.** Si en la carpeta destino ya hay uno con el mismo
   nombre, al que llega le pone ` (2)`, ` (3)`… y lo avisa. Lo que ya estaba
   archivado no se pierde.
3. **Solo toca lo que está suelto.** Lo que ya está dentro de una carpeta se
   queda quieto, y los archivos cuyo nombre no empieza por un número de factura
   también: salen listados al final para que usted decida.

Además, al terminar **dice qué carpetas creó**. Vale la pena mirar esa lista: si
alguien escribió mal un número, ahí aparece una carpeta que no debería existir.

---

## Ejemplo de lo que muestra

```
Se moverían 35 archivo(s) a 23 carpeta(s).

Carpetas que se crearían (18) — revise que sean facturas de verdad:
   HUS376265
   HUS380267
   ...

*** SIMULACIÓN: no se movió nada. Agregue --aplicar para hacerlo. ***
```

---

## Corrida de la carpeta CAROLINA (paquete 31068)

35 PDF sueltos, de **23 facturas distintas**. Cinco ya tenían carpeta
(HUS382278, HUS383781, HUS388262, HUS390152 y HUS390610); las otras **18 se
crean**. Ningún PDF queda suelto y ninguno pisa a otro.
