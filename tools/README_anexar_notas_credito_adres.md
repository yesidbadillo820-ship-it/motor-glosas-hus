# Pegar la nota crédito al final de la factura (ADRES)

Para radicar en el ADRES, la nota crédito de cada factura tiene que quedar
**dentro del folio de la factura, como última hoja**. Este bot lo hace solo.

```
NC ADRES\HUS354116.pdf
          +
GI-XX-XXXXX-2026\680010079201_HUS354116_FACTURA.pdf
          ↓
GI-XX-XXXXX-2026\680010079201_HUS354116_FACTURA.pdf
    (las hojas de siempre + la nota crédito de última)
```

## Cómo se usa (el auditor)

1. Copia **`ANEXAR_NOTAS_CREDITO.cmd`** dentro de la carpeta **`NC ADRES`**
   (la que tiene `HUS354116.pdf`, `HUS354131.pdf`, …).
2. Dale **doble clic**.

El bot busca solo la carpeta de radicación: la carpeta hermana que empieza por
`GI-` (por ejemplo `GI-XX-XXXXX-2026`). Si no la encuentra, o hay varias, la
pide — se le arrastra la carpeta y listo.

**Primero simula**: muestra el cuadro de lo que haría y no toca nada. Solo
escribe si se contesta `SI`.

## Lo que cuida

- **Nada se pierde.** Antes de tocar una factura guarda el folio original en la
  subcarpeta `_FOLIOS_SIN_NOTA` de la carpeta de radicación.
- **No pega la nota dos veces.** Si el bot se corre otra vez, las facturas que ya
  tienen su nota se saltan. Con `--rehacer` parte del folio guardado y vuelve a
  pegar (sirve cuando llega una nota crédito corregida).
- **No adivina.** Si una nota no tiene su factura en la carpeta de radicación,
  no la pega en ninguna otra: la reporta. Y las facturas que quedaron sin nota
  también salen en el informe.
- **Los ceros no estorban.** `HUS354116` y `HUS0000354116` son la misma factura.
- **Solo toca los `_FACTURA.pdf`.** El folio clínico (`_EPICRIS.pdf`) no se
  modifica.
- **Si el disco de red se cae** a mitad de la escritura, el folio bueno no queda
  partido: se escribe a un temporal y solo al final se reemplaza.

## El informe

Deja `INFORME_NOTAS_CREDITO.csv` en la carpeta de las notas, con una fila por
factura: nota crédito, folio, hojas antes, hojas de la nota, hojas después y qué
pasó. Ese es el papel que queda para la auditoría.

## Desde la consola (opcional)

```
py tools\anexar_notas_credito_adres.py "Z:\...\NC ADRES" "Z:\...\GI-XX-XXXXX-2026"
py tools\anexar_notas_credito_adres.py "...\NC ADRES" "...\GI-XX-XXXXX-2026" --aplicar
py tools\anexar_notas_credito_adres.py "...\NC ADRES" "...\GI-XX-XXXXX-2026" --rehacer --aplicar
```

Sin `--aplicar` solo simula.

## Nota técnica

`ANEXAR_NOTAS_CREDITO.cmd` lleva el motor Python embebido, así que se puede
copiar solo al servidor de cartera. Si se edita
`tools/anexar_notas_credito_adres.py` hay que regenerar el `.cmd` (encabezado
batch + contenido del `.py`); hay una prueba que lo verifica.
