# Guía: `indice_soportes_coosalud.py` — el índice de soportes de COOSALUD

El bot del portal (`responder_glosas_coosalud.py`) sabe adjuntar el PDF de
soporte, pero necesita que alguien le diga **en qué carpeta del share está
cada factura**. Eso es el índice. Esta herramienta lo arma y —más importante—
lo **revisa antes** de correr el portal.

## Por qué importa

Cuando el índice está viejo, el bot no halla el soporte, deja la factura en
`PENDIENTE_PDX` y uno se entera al final del cargue. Con `revisar` uno lo sabe
en treinta segundos y sin tocar el portal.

## El formato (no se negocia)

**Una ruta pelada por línea**, terminada en `\HUS<numero>`:

```
Y:\8. AGOSTO 2026 - SOPORTES RADICACION\COOSALUD\VANESSA\RIPS\ENV-231044-OK\HUS541781
```

Nada adelante de la ruta. El bot hace `Path(linea)` sobre la línea completa:
si le ponen `HUS541781<tab>` adelante, arma una ruta relativa que no existe y
la factura queda en `PENDIENTE_PDX` sin explicar por qué. Esta herramienta
escribe siempre el formato bueno, y al leer aguanta los índices viejos que
traían la tabulación (para no perderlos con `--actualizar`).

## 1) Revisar antes de subir (lo primero, siempre)

```cmd
py tools\indice_soportes_coosalud.py revisar ^
  --indice "D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt" ^
  --lista  "D:\...\FACTURAS_SOPORTES.txt"
```

Por cada factura dice qué PDF se va a adjuntar y cuánto pesa, o por qué no se
puede:

- **no está en el índice** → hay que armarlo (paso 2);
- **no se alcanza la carpeta** → ¿está conectada la unidad `Y:`?;
- **sin PDX/HAM/PDE** → el soporte no se ha armado todavía;
- **pesa más de 10 MB** → el portal no lo acepta; toca partir el PDF.

Avisa también cuando va a subir un `HAM` o un `PDE` porque no había `PDX`,
para que quede en el log qué se cerró con qué.

Sale con código 1 si algo falta, así que sirve dentro de otro `.bat`.

## 2) Armar o ampliar el índice

Recorre las carpetas de soportes buscando carpetas llamadas `HUS<numero>`:

```cmd
py tools\indice_soportes_coosalud.py armar ^
  --raiz "Y:\8. AGOSTO 2026 - SOPORTES RADICACION" ^
  --salida "D:\USUARIO CARTERA\Desktop\BUSCADOR_HUS\indice_facturas_HUS.txt" ^
  --actualizar
```

- `--raiz` se puede repetir para varios meses.
- **`--actualizar` conserva lo que ya estaba** y solo agrega lo nuevo. Es lo
  normal cuando llega un mes más: sin esa bandera el índice se rehace desde
  cero y se pierden los meses viejos.
- Si no encuentra ninguna carpeta de factura, **no escribe nada** y sale con
  código 1: así un `Y:` desconectado no le borra el índice bueno.

Indexe solo los meses que le hacen falta. Para saber cuáles: son los meses de
**radicación** de las facturas del lote, no los de la glosa.

### Por qué no se demora tanto como uno creería

El share está al otro lado de la red y ahí lo caro es cada ida y vuelta —la
lección del 11-09, cuando el indexador del motor puso lenta la plataforma—. El
recorrido lista cada carpeta **una sola vez** (con `os.scandir`, que ya dice
qué es carpeta sin volver a preguntar) y **no entra dentro de la carpeta de la
factura**: adentro están los PDF y los RIPS, y acá solo se quiere la ruta.

Medido sobre un árbol de 300 facturas con seis archivos cada una: **10 viajes
al servidor donde el recorrido completo gastaba 1.820**. 182 veces menos.

## Permisos

Se corre con la **sesión normal del auditor**, sin «ejecutar como
administrador». Lo único que hace falta es tener la unidad `Y:` conectada.

## Pruebas

`tests/test_tools/test_indice_soportes_coosalud.py` (26 casos), incluidos los
bordes que duelen: índice viejo con tabulación, unidad caída, carpeta borrada,
PDF pasado de peso, factura con ceros adelante y carpeta que solo empieza por
«HUS» sin ser una factura.
