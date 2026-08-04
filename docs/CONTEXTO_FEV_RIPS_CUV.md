# Validación de RIPS ante MinSalud (el CUV)

**Para qué sirve esta guía:** cuando cuentas médicas sube una factura al
validador del Ministerio y este no entrega el **CUV** (Código Único de
Validación), la factura no se puede radicar. Aquí está qué revisar y con qué
herramienta, para no descubrir el error después de haber enviado el paquete.

> Ojo: esto es **distinto** de las notas crédito del Dispensario/SIMED
> (ver `CONTEXTO_DISPENSARIO_NOTAS.md`). Allá se verifica el CUV de una nota
> ya generada con `tools/verificar_cuv_notas.py`. Aquí se revisa el paquete
> **antes** de subirlo, para que el CUV salga a la primera.

---

## 1) Qué es el paquete y qué revisa el Ministerio

Un paquete son **dos archivos en la misma carpeta**:

| Archivo | Qué es |
|---|---|
| `ad<NIT><consecutivo>.xml` | La factura electrónica firmada (viene del facturador). |
| `RP_<fecha>.json` | Los RIPS: usuario, servicios, diagnósticos, valores. |

El validador de escritorio (*Sistema de Validación y Envío de FEV RIPS*) hace
dos pasadas y **no son iguales**:

1. **Pre-validación (en el computador).** Solo mira la estructura del JSON.
   Es la que muestra la pantalla de "Resultados de Validación del Paquete"
   con las filas en rojo (`RECHAZADO`). Si sale un `RVG01 | Dato requerido`,
   quiere decir que un campo obligatorio del JSON viene vacío (`null`).
2. **Envío al Ministerio (en línea).** Además de la estructura, **cruza el
   JSON contra la factura**: número de factura, NIT, documento del paciente,
   valores y fechas. Aquí es donde se pierde tiempo: la pre-validación puede
   pasar limpia y aun así el Ministerio no entrega el CUV.

Por eso conviene correr el revisor propio, que hace las **dos** revisiones
antes de tocar el validador del Ministerio.

---

## 2) Cómo revisar antes de subir

```powershell
py D:\ruta\al\repo\tools\validar_json_rips.py "C:\Users\casa\Desktop\FV737"
```

Para revisar un mes completo (una carpeta por factura) y dejar el reporte en
Excel:

```powershell
py D:\ruta\al\repo\tools\validar_json_rips.py "D:\FEV\AGOSTO" --recursivo `
   --reporte "D:\FEV\AGOSTO\hallazgos.csv"
```

Lo que dice el resultado:

- **SIN HALLAZGOS** → el paquete se puede subir.
- **ERROR** → el Ministerio no va a generar el CUV. Hay que corregir.
- **AVISO** → no bloquea el CUV, pero suele terminar en glosa o en devolución
  de la EPS. Vale la pena revisarlo.

---

## 3) Los errores que más se repiten

### `RVG01 | Dato requerido` en `modalidadGrupoServicioTecSal`

El campo dice **cómo se prestó el servicio** y no puede ir en `null`.
Tabla oficial (Resolución 2275 de 2023):

| Código | Modalidad |
|---|---|
| `01` | Intramural (el paciente vino a la sede) |
| `02` | Extramural — unidad móvil |
| `03` | Extramural — domiciliaria |
| `04` | Extramural — jornada de salud |
| `05` | Extramural — atención prehospitalaria o transporte asistencial |
| `06` | Telemedicina interactiva |
| `07` | Telemedicina no interactiva |
| `08` | Telemedicina telexperticia |
| `09` | Telemedicina telemonitoreo |

Para una consulta presencial en consultorio va **`01`**.

### El número de factura sin el prefijo

En el JSON, `numFactura` tiene que ser **el mismo número con el que la
factura quedó radicada en la DIAN**, prefijo incluido. Si la factura es
`MED737`, el JSON no puede decir `"737"`: el Ministerio no la encuentra y no
genera el CUV.

El número real está en el XML, en la etiqueta `<cbc:ID>`.

### `tipoNota` y `numNota` mal diligenciados

- En una **factura de venta**, los dos van en `null`.
- En una **nota**, van los dos: `tipoNota` (`NC`, `ND`, `NA`, `RS`) y
  `numNota` con el número de la nota.

Poner un `numNota` con el `tipoNota` vacío es la mezcla que más se ve cuando
el software de facturación exporta mal.

### La atención quedó fuera del período de la factura

La fecha de `fechaInicioAtencion` **debe caer dentro del período de
facturación** que trae el XML (`<cac:InvoicePeriod>`, campos `StartDate` y
`EndDate`).

Si la atención fue el 27 de julio y la factura se expidió por el período del
31 de julio, hay que decidir cuál de los dos está mal:

- Si la fecha real de la atención es otra → se corrige el JSON.
- Si la fecha de la atención es correcta → **facturación tiene que reexpedir
  la factura** con el período real. La factura ya está firmada y radicada en
  la DIAN: no se puede editar el XML.

Nunca se cambia la fecha clínica solo para que el validador pase.

### Formato de las fechas

- Con hora: `AAAA-MM-DD HH:MM` → `2026-07-31 16:00`
- Sin hora (fecha de nacimiento): `AAAA-MM-DD` → `1976-03-31`

---

## 4) Cómo corregir el JSON sin dañarlo

Editar a mano es riesgoso (una coma de más y el archivo deja de servir).
Plantilla de PowerShell — se cambia la ruta y los valores:

```powershell
$ruta = "C:\Users\casa\Desktop\FV737\RP_20260801145548.json"

# 1) Copia de seguridad
Copy-Item $ruta "$ruta.bak" -Force

# 2) Correcciones
$j = Get-Content $ruta -Raw -Encoding UTF8 | ConvertFrom-Json
$j.numFactura = "MED737"          # el número con prefijo, igual que en la DIAN
$j.tipoNota   = $null             # es factura de venta, no nota
$j.numNota    = $null
foreach ($u in $j.usuarios) {
  foreach ($c in $u.servicios.consultas) {
    $c.modalidadGrupoServicioTecSal = "01"   # atención presencial
  }
}

# 3) Guardar en UTF-8
[System.IO.File]::WriteAllText(
  $ruta, ($j | ConvertTo-Json -Depth 12), (New-Object System.Text.UTF8Encoding($true)))
```

`UTF8Encoding($true)` conserva el BOM, que es como el facturador genera los
archivos y como el validador del Ministerio los viene aceptando. Si alguna vez
el JSON se rechaza por codificación, se cambia a `$false` para guardarlo sin
BOM.

Después de corregir, **volver a correr el revisor** y solo entonces abrir el
validador del Ministerio.

---

## 5) Orden de trabajo recomendado

1. Armar la carpeta con el XML y el JSON juntos.
2. Correr `tools/validar_json_rips.py` sobre la carpeta.
3. Corregir lo que salga en ERROR y volver a correr hasta que quede limpio.
4. Abrir el validador del Ministerio → *Seleccionar Carpeta* → debe quedar en
   **Pre-Validación Exitosa**.
5. *Enviar Paquetes* y confirmar que llegó el CUV.
6. Con el CUV en mano, radicar en la plataforma de la EPS.

En cargues masivos, primero un **piloto de una factura**; si el CUV sale bien,
se corre el resto.
