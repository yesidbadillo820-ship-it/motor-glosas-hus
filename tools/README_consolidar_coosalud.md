# Guía: `consolidar_coosalud.py` — Consolidados + archivo de OBJECIONES (DGH)

Bot que automatiza los pasos 2 a 5 de la guía de cartera de COOSALUD. Parte de la
carpeta **CARGUE MASIVO COOSALUD** (la que arma `organizar_cargue_masivo_coosalud.py`)
y produce, en un solo paso, los consolidados y el archivo de cargue de objeciones
para DGH.

Reemplaza el proceso manual de: consolidar con Power Query, crear la columna
OBSERVACIÓN FINAL, agrupar por `id_detalle` con `Text.Combine`, hacer el BUSCARV
al detalle, filtrar/arreglar la base DGH y diligenciar el archivo de objeciones.

---

## 1) Uso

**Forma fácil (sin terminal):** deja `CONSOLIDAR COOSALUD.bat` junto a
`consolidar_coosalud.py`, arrastra la carpeta "CARGUE MASIVO COOSALUD" encima
del `.bat` (o doble clic) y responde: fecha y, si la tienes, la ruta de la
base DGH. Instala `openpyxl` solo la primera vez.

**Por terminal** (los comandos van en UNA sola línea — el separador `^` solo
funciona en CMD, no en PowerShell):

```bat
REM Básico (sin base DGH: SLNSERPRO sale del codigo_servicio del detalle)
py consolidar_coosalud.py --carpeta "D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD" --fecha 04/07/2026

REM Completo, con la base DGH para el cruce
py consolidar_coosalud.py --carpeta "D:\USUARIO CARTERA\Desktop\CARGUE MASIVO COOSALUD" --fecha 04/07/2026 --servicios "D:\...\SERVICIOS FACTURADOS COOSALUD DGH.xlsx"
```

| Parámetro     | Para qué sirve                                                | Por defecto |
|---------------|---------------------------------------------------------------|-------------|
| `--carpeta`   | Carpeta organizada con GLOSAS/DETALLES/FACTURAS (**obligatorio**) | — |
| `--fecha`     | Día de la carpeta que se revisa, `DD/MM/AAAA` (**obligatorio**). Va en CDFECDOC y CROFECOBJ | — |
| `--servicios` | Base DGH de servicios facturados (xlsx/csv/txt), tal cual se descarga | (sin cruce) |
| `--salida`    | Dónde dejar los resultados                                    | `<carpeta>\CONSOLIDADOS` |

Requiere Python 3 con `openpyxl` (`py -m pip install openpyxl`).

## 2) Qué produce (en `<carpeta>\CONSOLIDADOS`)

1. **CONSOLIDADO GLOSAS.xlsx**
   - Hoja `GLOSAS`: todas las glosas + columna **OBSERVACION FINAL**
     (`codigo_glosa + " " + justificacion_glosa + "$" + valor`).
   - Hoja `AGRUPADO`: una fila por `id_detalle` con las observaciones combinadas
     por saltos de línea (lo que hacía el Agrupar por de Power Query).
2. **CONSOLIDADO DETALLE.xlsx** — todos los detalles + OBSERVACION FINAL pegada
   por `id_detalle` (lo que hacía el BUSCARV).
3. **CONSOLIDADO FACTURAS.xlsx** — cabeceras de factura unidas.
4. **SERVICIOS FACTURADOS COOSALUD.xlsx** (solo con `--servicios`) — la base DGH:
   - filtrada a **solo las facturas trabajadas**,
   - **"arreglada"**: en los medicamentos (SLNSERPRO_SERVICIO vacío) se rellenan
     SERVICIO/CUPS y descripciones con el código y nombre del medicamento,
   - con solo las 10 columnas del proceso.
5. **OBJECIONES.xlsx** — el archivo de cargue DGH, con el formato exacto de la
   plantilla real:

   | Campo | Valor |
   |---|---|
   | CDCONSEC | consecutivo por factura, texto (1,1,1… 2,2,2…) |
   | CDFECDOC / CROFECOBJ | `--fecha` como fecha Excel |
   | CRNCXC | factura con ceros: `HUS0000496207` |
   | CROCLAOBJ | 0 · GENUSUARIO4: `999` |
   | CRNCONOBJ | código completo de la glosa del servicio. **Una glosa CL (médica) manda por encima de todo**: si el servicio tiene alguna CL, va la CL (la de mayor valor entre las CL); si no hay CL, va la de mayor valor (TA2901, …) |
   | SLNSERPRO | Código DGH del servicio. Se cruza en varios niveles (todos dentro de la factura): **1)** código exacto · **2)** **nombre de medicamento inequívoco** — evita que dos medicamentos distintos que comparten base y un cero a la izquierda se lleven el mismo código (portal `20048691-1` KETAMINA vs `20048691-01` SALBUTAMOL; DGH los tiene como `20048691-1` y `20083667-1`, y el nombre los separa) · **3)** mismo código con el sufijo sin ceros (`19931216-05` = `19931216-5`) · **4)** misma base de medicamento, otra presentación (`20055559-1` → `20055559-14`) · **5)** por descripción (ej. *DERECHOS DE SALA PARA CURACIONES*). Si DGH **no tiene** ese servicio en la factura, se deja el código del portal y la fila va a `NO_CRUZADOS` |
   | CROVALOBJ | valor_glosado del servicio (número) |
   | CRDOBSERV | OBSERVACIÓN FINAL combinada |
   | CROTIPOBJ | **por factura completa**: 0=administrativa (sin CL) · 1=médica (solo CL) · 2=mixta — si la factura es mixta, TODAS sus filas llevan 2 |

   - El `OBJECIONES.xlsx` queda con **una sola hoja** (como la guía), ya limpio
     para el cargue. Lo que DGH rechazaría se deja **FUERA** y se guarda en un
     archivo aparte **`REVISAR (no van en el cargue).xlsx`**:
     - `NO_INCLUIDOS`: servicios que DGH no tiene en la factura, o cuyo valor no
       cabía (motivo explicado en cada fila).
     - `VALOR_AJUSTADO`: objeciones que se **caparon** al máximo que DGH acepta
       (no se pierde la objeción, solo se ajusta el valor). Ej: se glosó 117.300
       pero el saldo era 112.300 → se objeta 112.300.

   El cargue evita así los tres errores de DGH: *servicio no asociado a la
   cuenta*, *valor objeción mayor al del servicio* y *valor objetado mayor al
   saldo*. Con `--incluir-no-cruzados` los no cruzados vuelven al OBJECIONES
   (marcarían error).

## 3) Defensas incluidas (validadas con revisión adversarial)

- **Valores colombianos**: `1.234.567,89`, `26,140`, `$ 1.500` se leen bien.
- **Archivos `~$` de Excel** (libro abierto) se ignoran; un xlsx corrupto aborta
  con el nombre del archivo.
- **Duplicados**: archivos o filas repetidas (mismo `id_glosa` / `id_detalle`)
  se saltan con aviso — nunca se duplica el valor objetado.
- **Encabezados en otro orden** entre lotes: las filas se reordenan por nombre.
- **Códigos/id tipados como número** (`890466.0`) cruzan igual y salen limpios.
- **xlsx con `dimension` mentirosa** (portales) se leen completos.
- **Base DGH en streaming**: 80MB+ sin agotar la memoria.
- Facturas fuera del patrón HUS y glosas sin detalle se reportan con OJO.

## 4) Flujo completo del día

```
1. ORGANIZAR CARGUE COOSALUD.bat  <- arrastrar el ZIP del portal
2. py consolidar_coosalud.py --carpeta ... --fecha DD/MM/AAAA --servicios BASE_DGH.xlsx
3. Revisar la hoja NO_CRUZADOS de OBJECIONES.xlsx
4. Subir OBJECIONES.xlsx a DGH
```
