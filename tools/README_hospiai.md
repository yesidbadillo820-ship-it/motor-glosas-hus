# HOSPIAI Fase 1 — Guía de instalación y operación

**Expediente Digital de Cuentas Médicas · ESE HUS.** Con la Fase 1, cada corrida
del radicador queda guardada en una base de datos local (`data/hospiai.db`):
expedientes, documentos, hallazgos con su regla y eventos con fecha y versión.
Aunque mañana cambie el código, **el historial no se pierde**.

> **Seguro:** todo es **solo lectura** sobre los shares del hospital. Lo único
> que se escribe es la base local del repo, los reportes y el panel.

---

## Requisitos

- Windows con Python 3.11+ (`py --version`).
- `openpyxl` solo si se quiere el XLSX (`py -m pip install openpyxl`).
- El repo clonado (p. ej. `C:\Users\cartera\motor-glosas-hus`).

## Uso diario (manual)

```powershell
cd C:\Users\cartera\motor-glosas-hus

# 1) Auditar el lote — igual que siempre, ahora también escribe el Expediente
py tools\radicar_facturacion.py --origen "\\172.16.32.83\factura_electronica_net22\202606\FACTURAS_SALUD" --soportes-indice "data\idx_soportes_2026.txt" --reporte "$env:USERPROFILE\Desktop\radicacion_fe.csv" --xlsx "$env:USERPROFILE\Desktop\radicacion_fe.xlsx"

# 2) Ver el estado del Expediente Digital
py tools\hospiai.py resumen

# 3) Panel HTML (se abre con doble clic, sin internet)
py tools\hospiai.py panel --salida "$env:USERPROFILE\Desktop\panel_hospiai.html"
```

Al final de la corrida del radicador aparece la línea que confirma la
persistencia:

```
Expediente Digital: 12,523 expediente(s), 98,412 documento(s), 8,900 hallazgo(s)
  → data\hospiai.db (corrida #3, reglas v1.0)
```

- `--db otra\ruta.db` cambia dónde se guarda; `--sin-db` omite la base.
- El reporte ahora trae dos columnas nuevas: **responsable** (funcionario leído
  de la ruta del share) y **lote** (envío `ENV-…`).

## Corrida automática diaria

El script `tools\corrida_diaria.ps1` hace todo (auditoría + expediente + panel).
Programarlo una sola vez:

```powershell
schtasks /Create /TN "HOSPIAI corrida diaria" /SC DAILY /ST 06:00 /TR "powershell -ExecutionPolicy Bypass -File C:\Users\cartera\motor-glosas-hus\tools\corrida_diaria.ps1"
```

(La ruta del lote y del índice se editan al inicio del `.ps1`. Para quitarla:
`schtasks /Delete /TN "HOSPIAI corrida diaria"`.)

## Las reglas ahora son datos

`data\reglas_radicacion.json` define qué soporte exige cada tipo de atención,
con su **fuente normativa** (Res. 2284/2023…). El área puede editarlas sin
programar; el radicador registra en cada corrida **qué versión** usó. Los
perfiles por entidad (`data\perfiles_radicacion.json`) siguen aplicando por
encima (extras y excepciones por pagador).

## Qué guarda la base (para el auditor)

| Tabla | Qué contiene |
|---|---|
| `expedientes` | Una fila por factura: pagador, responsable, lote, valor, dictamen |
| `documentos` | Cada archivo visto (nombre, ruta, tipo, primera/última vez) |
| `hallazgos` | Cada error detectado, con criticidad y la **regla** que lo sustenta |
| `eventos` | La línea de tiempo: cada auditoría, con fecha y versión de reglas |
| `corridas` | Cada ejecución del motor (cuándo, sobre qué, con qué versión) |
| `radicaciones`, `glosas`, `pagos`, `contratos` | Listas para las fases siguientes |

Consultas rápidas sin herramientas extra:

```powershell
py -c "import sqlite3; c=sqlite3.connect('data/hospiai.db'); [print(r) for r in c.execute('SELECT dictamen, COUNT(*) FROM expedientes GROUP BY dictamen')]"
```

## Respaldo

La base es un solo archivo: copiar `data\hospiai.db` a la carpeta de respaldo
del área (idealmente después de cada corrida diaria). Con eso se conserva TODO
el historial.
