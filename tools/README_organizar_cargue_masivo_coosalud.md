# Guía: `organizar_cargue_masivo_coosalud.py` — Extraer y organizar el ZIP de COOSALUD

Bot que toma el `.zip` que descarga cartera (p. ej. `COOSALUD 1.zip`), con cientos
de Excel sueltos, y los reparte automáticamente en tres carpetas dentro del
Escritorio, dejando todo listo para el **cargue masivo**.

Reemplaza el trabajo manual de descomprimir el ZIP y ordenar archivo por archivo.

---

## 1) Qué produce

A partir de un ZIP con archivos como:

```
DETALLE HUS507721.xlsx
GLOSAS HUS507721.xlsx
HUS507721.xlsx
... (cientos más)
```

crea en el Escritorio esta estructura:

```
D:\USUARIO CARTERA\Desktop\
└── CARGUE MASIVO COOSALUD\
    ├── DETALLES\        ← DETALLE HUS######.xlsx
    ├── FACTURAS\        ← HUS######.xlsx   (la factura, sin prefijo)
    ├── GLOSAS\          ← GLOSAS HUS######.xlsx
    └── SIN_CLASIFICAR\  ← lo que no encaje (normalmente vacío)
```

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

---

## 3) Forma fácil (sin terminal) — el `.bat`

1. Deja juntos en la misma carpeta estos dos archivos:
   - `organizar_cargue_masivo_coosalud.py`
   - `ORGANIZAR CARGUE COOSALUD.bat`
2. **Arrastra el ZIP encima** de `ORGANIZAR CARGUE COOSALUD.bat`
   (o haz doble clic y pega la ruta del ZIP cuando lo pida).
3. Se crea `CARGUE MASIVO COOSALUD` en `D:\USUARIO CARTERA\Desktop`.

> Requiere tener **Python 3** instalado. Si no lo tienes, descárgalo de
> [python.org](https://www.python.org/downloads/) y marca la casilla
> *"Add Python to PATH"* al instalar.

---

## 4) Forma por terminal (más opciones)

```bat
REM Lo normal: extrae el ZIP al Escritorio por defecto
py organizar_cargue_masivo_coosalud.py --zip "C:\Users\brayan\Downloads\COOSALUD 1.zip"

REM Ensayo: muestra qué haría sin escribir nada
py organizar_cargue_masivo_coosalud.py --zip "...\COOSALUD 1.zip" --dry-run

REM Cambiar Escritorio / nombre de carpeta / guardar reporte CSV
py organizar_cargue_masivo_coosalud.py ^
    --zip     "...\COOSALUD 1.zip" ^
    --destino "D:\USUARIO CARTERA\Desktop" ^
    --nombre  "CARGUE MASIVO COOSALUD" ^
    --reporte "D:\USUARIO CARTERA\Desktop\reporte_cargue.csv"
```

### Parámetros

| Parámetro        | Para qué sirve                                              | Por defecto |
|------------------|------------------------------------------------------------|-------------|
| `--zip`          | Ruta del `.zip` a procesar (**obligatorio**)               | —           |
| `--destino`      | Carpeta base (Escritorio) donde se crea la carpeta         | `D:\USUARIO CARTERA\Desktop` |
| `--nombre`       | Nombre de la carpeta que se crea                           | `CARGUE MASIVO COOSALUD` |
| `--reporte`      | Guarda un CSV con lo hecho por cada archivo                | (no se guarda) |
| `--dry-run`      | Ensayo: no escribe nada, solo informa                      | —           |
| `--sobrescribir` | Reemplaza archivos que ya existan en el destino            | (los conserva) |
| `-v`, `--verbose`| Log detallado                                              | —           |

---

## 5) Detalles útiles

- **Idempotente**: si lo corres dos veces, los archivos que ya están **no se
  vuelven a escribir** (aparecen como `YA_EXISTIA`). Usa `--sobrescribir` para
  forzar el reemplazo.
- **Sin dependencias**: usa solo la librería estándar de Python 3 (nada que
  instalar con `pip`).
- **No requiere descomprimir a mano**: el script lee el ZIP directamente.
- Al terminar imprime un **resumen** con el conteo por carpeta. Con el ejemplo
  `COOSALUD 1.zip` (300 archivos) da 100 / 100 / 100.

---

## 6) Ejemplo de salida

```
ZIP     : C:\...\COOSALUD 1.zip
Destino : D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD
Archivos dentro del ZIP: 300

===== RESUMEN =====
  DETALLES:        100
  FACTURAS:        100
  GLOSAS:          100
  TOTAL:           300

Listo. Carpetas creadas.
```
