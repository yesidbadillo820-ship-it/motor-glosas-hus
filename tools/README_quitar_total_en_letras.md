# Dejar el detallado listo para radicar (`quitar_total_en_letras.py`)

El detallado que imprime el sistema del hospital cierra con **dos** totales: el
número («VALOR TOTAL ORDEN DE SERVICIO  $130.400») y el mismo valor **en
letras** («CIENTO TREINTA MIL CUATROCIENTOS PESOS CON CERO CTVS M/Cte.»).

Este bot **borra el renglón en letras y deja ese espacio vacío**. La etiqueta
`TOTAL:` se queda; lo que desaparece es el importe escrito en palabras. Todo lo
demás queda igual: los números, el formato, las celdas combinadas y los anchos.

Con `--quitar-pie` saca además el **pie legal del final del archivo** — la
autorización de la DIAN, el aviso de la letra de cambio, los intereses
moratorios, «Nombre reporte» y «LICENCIADO A» —, de modo que la hoja **termine
en la firma del auditor**. Ese bloque lo imprime el sistema una sola vez al
final y no es parte de la factura.

---

## Cómo se usa

```
py tools\quitar_total_en_letras.py ^
    --origen "D:\...\POR_FACTURA_31068" ^
    --salida "D:\...\POR_FACTURA_31068_SIN_LETRAS" ^
    --reporte-csv "D:\...\LETRAS_QUITADAS.csv"
```

Requiere una sola vez: `py -m pip install openpyxl`

| Opción | Para qué |
|---|---|
| `--origen` | Carpeta(s) o archivo(s) Excel. Acepta varias. |
| `--salida` | Carpeta donde deja las copias. **Los originales no se tocan.** |
| `--patron` | Qué archivos tomar (por defecto `*.xlsx`). |
| `--recursivo` | Entrar también en las subcarpetas. |
| `--quitar-pie` | Sacar también el pie legal del final. |
| `--reporte-csv` | Listado de qué se quitó en cada archivo. |
| `--dry-run` | Ver qué haría, sin escribir nada. |

### Y después, a PDF

```
py tools\excel_a_pdf.py ^
    --origen "D:\...\POR_FACTURA_31068_SIN_LETRAS" ^
    --salida "D:\...\PDF_31068"
```

---

## Lo que NO hace

**No borra a ciegas.** Solo vacía las celdas que de verdad traen un importe
escrito en palabras — las que dicen PESOS … CTVS — y solo en el renglón que
empieza por `TOTAL:`. Si en ese renglón hay otro texto, se queda donde está.

**Y no se pasa de la firma.** El pie se busca de abajo hacia arriba, y se corta
en el primer renglón que no sea del pie: la firma (`ELABORO`, `AUDITOR`), las
notas finales y los totales nunca se tocan.

Si en algún archivo no encuentra el renglón, **lo dice** (estado `SIN_LETRAS`)
en vez de callarlo, y ese archivo se entrega igual, sin tocar.

Una hoja con **varias facturas apiladas** queda con todas vacías, no solo la
primera. Un Excel dañado no tumba el lote: queda en `ERROR` y los demás siguen.
Pasarlo dos veces sobre la misma carpeta no rompe nada.

---

## Corrida del paquete 31068 (19-08-2026)

320 facturas: las 320 con el total en letras quitado y las 320 sin el pie legal,
y de ahí **320 PDF** (340 páginas, 11 menos que con el pie). Comprobado sobre
los PDF ya generados:

- **0** muestran un importe en palabras;
- **0** traen algo del pie legal;
- **320/320** conservan el `VALOR TOTAL ORDEN DE SERVICIO` en número y la firma
  del auditor;
- la suma de los subtotales sigue en **$625.461.616,95**, la misma de antes.
