# Guía: `organizar_cargue_masivo_coosalud.py` — Extraer, organizar y lotear el ZIP de COOSALUD

Bot que toma el `.zip` que descarga cartera (miles de Excel sueltos) y los reparte
automáticamente en tres carpetas dentro del Escritorio, **divididas en lotes de
máximo 300 archivos** para poder subirlas al portal de cargue (que solo deja subir
300 a la vez).

Reemplaza el trabajo manual de descomprimir el ZIP, ordenar archivo por archivo y
armar los grupos de 300.

---

## 1) Qué produce

A partir de un ZIP con archivos como:

```
DETALLE HUS507721.xlsx
GLOSAS HUS507721.xlsx
HUS507721.xlsx
... (miles más)
```

crea en el Escritorio esta estructura, con **lotes de máximo 300 archivos**:

```
D:\USUARIO CARTERA\Desktop\
└── CARGUE MASIVO COOSALUD\
    ├── DETALLES\
    │   ├── LOTE 01\   (300 archivos)
    │   ├── LOTE 02\   (300 archivos)
    │   └── LOTE 07\   (los que sobren)
    ├── FACTURAS\
    │   ├── LOTE 01\   (300 archivos)
    │   └── ...
    ├── GLOSAS\
    │   ├── LOTE 01\   (300 archivos)
    │   └── ...
    └── SIN_CLASIFICAR\  ← lo que no encaje (normalmente vacío, sin lotear)
```

Los lotes se arman **ordenando por número de factura**, así el `LOTE 01` de
FACTURAS, DETALLES y GLOSAS corresponde al **mismo grupo de facturas**. Al subir,
abres `FACTURAS\LOTE 01`, seleccionas los 300, los subes; luego `LOTE 02`, y así.

> Con **2.000 facturas** → 6 lotes de 300 + 1 de 200, en cada una de las tres carpetas.

## 2) Cómo clasifica (regla exacta)

Mira el **nombre de cada archivo** (sin importar mayúsculas ni acentos):

| Empieza por…        | Va a la carpeta |
|---------------------|-----------------|
| `DETALLE`           | `DETALLES`      |
| `GLOSA` / `GLOSAS`  | `GLOSAS`        |
| `HUS` + número      | `FACTURAS`      |
| cualquier otra cosa | `SIN_CLASIFICAR` (se reporta, no se pierde) |

Nada se borra: si un archivo no coincide con ningún patrón, queda en
`SIN_CLASIFICAR` para que lo revises a mano.

> **ZIP dentro de ZIP:** si el archivo es un ZIP que a su vez contiene varios
> ZIP (el masivo de COOSALUD viene como un ZIP con `COOSALUD 1.zip` …
> `COOSALUD 22.zip` adentro), el bot **entra en todos** y junta las 2.000+
> facturas en un solo `CARGUE MASIVO COOSALUD` con sus lotes de 300.

---

## 3) Forma fácil (sin terminal) — el `.bat`

1. Deja juntos en la misma carpeta estos dos archivos:
   - `organizar_cargue_masivo_coosalud.py`
   - `ORGANIZAR CARGUE COOSALUD.bat`
2. **Arrastra el ZIP encima** de `ORGANIZAR CARGUE COOSALUD.bat`
   (o haz doble clic y pega la ruta del ZIP cuando lo pida).
3. Se crea `CARGUE MASIVO COOSALUD` en `D:\USUARIO CARTERA\Desktop`, ya loteada.

> Requiere tener **Python 3** instalado. Si no lo tienes, descárgalo de
> [python.org](https://www.python.org/downloads/) y marca la casilla
> *"Add Python to PATH"* al instalar.

---

## 4) Forma por terminal (más opciones)

```bat
REM Lo normal: extrae el ZIP al Escritorio por defecto, en lotes de 300
py organizar_cargue_masivo_coosalud.py --zip "C:\Users\brayan\Downloads\COOSALUD 1.zip"

REM Ensayo: muestra qué haría sin escribir nada
py organizar_cargue_masivo_coosalud.py --zip "...\COOSALUD 1.zip" --dry-run

REM Cambiar tamaño de lote / Escritorio / nombre / guardar reporte CSV
py organizar_cargue_masivo_coosalud.py ^
    --zip          "...\COOSALUD 1.zip" ^
    --destino      "D:\USUARIO CARTERA\Desktop" ^
    --nombre       "CARGUE MASIVO COOSALUD" ^
    --max-por-lote 300 ^
    --reporte      "D:\USUARIO CARTERA\Desktop\reporte_cargue.csv"
```

### Parámetros

| Parámetro        | Para qué sirve                                              | Por defecto |
|------------------|------------------------------------------------------------|-------------|
| `--zip`          | Ruta del `.zip` a procesar (**obligatorio**)               | —           |
| `--destino`      | Carpeta base (Escritorio) donde se crea la carpeta         | `D:\USUARIO CARTERA\Desktop` |
| `--nombre`       | Nombre de la carpeta que se crea                           | `CARGUE MASIVO COOSALUD` |
| `--max-por-lote` | Máximo de archivos por lote                                | `300`       |
| `--reporte`      | Guarda un CSV con lo hecho por cada archivo (incluye lote) | (no se guarda) |
| `--dry-run`      | Ensayo: no escribe nada, solo informa                      | —           |
| `--sobrescribir` | Reemplaza archivos que ya existan en el destino            | (los conserva) |
| `-v`, `--verbose`| Log detallado                                              | —           |

---

## 5) Detalles útiles

- **Lotes de 300**: cada carpeta se divide en `LOTE 01`, `LOTE 02`, … con máximo
  300 archivos, para respetar el límite del portal. Se cambia con `--max-por-lote`.
- **Lotes alineados**: el `LOTE 01` de las tres carpetas cubre las mismas facturas
  (se ordena por número `HUS######`).
- **Idempotente**: si lo corres dos veces con el mismo ZIP, los archivos que ya
  están **no se vuelven a escribir** (aparecen como `YA_EXISTIA`). Usa
  `--sobrescribir` para forzar el reemplazo.
- **Sin dependencias**: usa solo la librería estándar de Python 3.
- Al terminar imprime un **resumen** con el conteo y la cantidad de lotes por
  carpeta.

---

## 6) Ejemplo de salida (ZIP grande, 2.000 facturas)

```
ZIP     : C:\...\COOSALUD MASIVO.zip
Destino : D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD
Lote    : máximo 300 archivos por carpeta
Archivos dentro del ZIP: 6000

===== RESUMEN =====
  DETALLES:        2000 archivos en 7 lote(s)
  FACTURAS:        2000 archivos en 7 lote(s)
  GLOSAS:          2000 archivos en 7 lote(s)
  TOTAL:           6000 archivos

Listo. Carpetas y lotes creados.
```
