# ¿Están todas las facturas del paquete? (`cruzar_detallados_con_macro.py`)

Compara la **carpeta de detallados por factura** contra la **macro de respuesta**
del paquete y responde dos preguntas:

1. ¿Es la misma cantidad de facturas de un lado y del otro?
2. Si no, **cuáles faltan** y **cuánta plata** representan.

Las que están en la macro y **no** tienen detallado son las importantes: el
hospital las está reclamando pero no tiene el papel que lo sustenta.

---

## Cómo se usa

```
py tools\cruzar_detallados_con_macro.py ^
    --detallados "D:\...\EXCEL_POR_FACTURA" ^
    --macro      "D:\...\RTA GLOSA ADRES PAQ 31068.xlsx" ^
    --salida     "D:\...\CONSOLIDADO_31068.xlsx"
```

Requiere una sola vez: `py -m pip install openpyxl`

| Opción | Para qué |
|---|---|
| `--detallados` | La carpeta con un Excel por factura. |
| `--macro` | El Excel de la macro de respuesta del paquete. |
| `--salida` | El Excel del consolidado. |
| `--patron` | Qué archivos tomar de la carpeta (por defecto `*.xlsx`). |
| `--paquete` | Filtrar por número de paquete, si la macro trae varios. |

---

## Lo que deja

Un Excel con **tres hojas**:

- **RESUMEN** — cuántas hay de cada lado, cuántas cuadran, cuántas faltan y
  cuánta plata está en juego.
- **FACTURAS** — todas, una por línea, con su estado, el archivo del detallado,
  el radicado, cuántas glosas trae y sus valores.
- **SIN DETALLADO** — solo las que faltan, con **el radicado** (que es lo que
  hay que llevarle a facturación para pedir la impresión), cuántas glosas hay
  que responder y **cómo quedó respondida cada una** (SE ACEPTA / SE OBJETA /
  SE SUBSANA).

### Los tres estados

| Estado | Qué significa |
|---|---|
| **CON DETALLADO** | Está en los dos lados. Todo bien. |
| **SIN DETALLADO** | La macro la tiene glosada pero no hay detallado. **Hay que pedir la impresión.** |
| **SIN GLOSAS EN LA MACRO** | Hay detallado pero la macro no le trae glosas. Revisar si sobra en la carpeta. |

---

## Detalles que evitan errores

- **La factura se lee de adentro del archivo, no del nombre.** Si alguien
  renombró un archivo, el consolidado igual lo ubica bien.
- **Los ceros de relleno no separan la misma factura:** `HUS0000352890` y
  `HUS352890` son la misma.
- **Las glosas totales no cuentan como «por responder».** En el reporte del
  ADRES hay filas con la «Descripción Glosa» vacía: son el desglose de una
  reclamación glosada entera y no se responden una por una. Por eso la columna
  *GLOSAS POR RESPONDER* suele ser menor que *FILAS EN LA MACRO*.
- Un Excel dañado no tumba el cruce: se avisa y las demás siguen.

---

## Corrida del paquete 31068 (19-08-2026)

**324 facturas en la macro contra 320 detallados: faltan 4**, por
**$43.518.600** glosados.

| Factura | Radicado | Glosas | Valor glosado | Ya aceptado |
|---|---|---:|---:|---:|
| HUS311371 | 14345108 | 150 (21 por responder) | $39.722.100 | $0 |
| HUS394817 | 14383060 | 12 | $3.646.700 | $2.400 |
| HUS380246 | 14351110 | 2 | $139.400 | $0 |
| HUS367368 | 14344771 | 1 | $10.400 | $10.400 |

No es un fallo de ningún bot: **el sistema del hospital nunca exportó esos
cuatro detallados**. Se buscaron archivo por archivo en los siete lotes y no
están en ninguno. Hay que pedirle a facturación esa impresión.
