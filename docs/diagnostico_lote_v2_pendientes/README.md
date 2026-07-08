# Diagnóstico — 12 facturas pendientes del Lote V2 (Dispensario)

> **ACTUALIZADO 2026-06-25** tras inspección real de los `CUV_*.json` en disco.
> El cuadro inicial decía que 5 facturas estaban subidas OK y otras necesitaban
> simplemente re-correr el bot — **eso era falso positivo**. La verdad: 9 de
> las 12 están bloqueadas por SISTEMAS (CUV inválido o rechazado).

## Listado analizado

```
HUS0000404136  HUS0000411234  HUS0000410675  HUS0000413266
HUS0000417459  HUS0000420099  HUS0000421733  HUS0000418576
HUS0000420160  HUS0000422238  HUS0000435485  HUS0000440328
```

## Causa raíz por factura (resumen ejecutivo)

| Causa raíz | Conteo | Facturas | Quién resuelve |
|---|---|---|---|
| RIPS rechazado MinSalud — RVC086 | 3 | HUS404136, HUS410675, HUS435485 | **SISTEMAS/RIPS** |
| RIPS nunca validado — `dockerrips.hus.gov.co:9443` caído | 6 | HUS411234, 420099, 421733, 418576, 420160, 422238 | **SISTEMAS** |
| Sin PDF CRRP en disco | 2 | HUS413266, HUS417459 | **Auditor** (descargar DIAN) |
| Sin NE V2 asignado | 1 | HUS440328 | **Facturación** |
| **TOTAL** | **12** | | |

**9 de las 12 quedan en manos de SISTEMAS.** Un solo correo destraba el bloque
más grande.

## Archivos en esta carpeta

| Archivo | Para qué sirve |
|---|---|
| `README.md` | este resumen |
| `estado_facturas.md` | ficha detallada por factura (NEs + causa real + acción) |
| `resumen.csv` | la misma info en formato tabla (Excel) |
| `correo_sistemas.md` | **plantilla del correo a SISTEMAS** con las 9 NEs y la captura del error |
| `diagnosticar_local.ps1` | script PowerShell para re-validar el estado real (corrió ya — el resultado está en `reporte_diagnostico.csv`) |
| `reporte_diagnostico.csv` | salida del script (generado localmente, no se commitea) |

## Cómo usar

1. Mandar el correo de `correo_sistemas.md` al área de SISTEMAS/RIPS.
2. Mientras esperás respuesta, bajar los 2 PDFs CRRP del DIAN (HUS413266 y
   HUS417459) — eso destraba 2 facturas más sin depender de nadie.
3. Mandar mensaje corto a Facturación por HUS440328.
4. Cuando SISTEMAS confirme que ya regeneraron los CUVs, **revalidar**:

   ```powershell
   cd C:\temp-notas
   git pull
   py tools\verificar_cuv_notas.py `
     --facturas "HUS404136,HUS411234,HUS410675,HUS420099,HUS421733,HUS418576,HUS420160,HUS422238,HUS435485" `
     --reporte  "D:\USUARIO CARTERA\Documents\NOTAS ANTIGUAS\reporte_cuv_pendientes.csv"
   ```

   Si las 9 salen `OK`, recién ahí re-correr `cargar_soportes_simed.py` para
   subirlas.

## Cómo se llegó a esto

`diagnosticar_local.ps1` (versión final) lee cada `CUV_*.json` y:

- Si tiene `ResultState:true` → CUV válido.
- Si tiene `ResultState:false` → rechazo MinSalud (lee `ResultadosValidacion[].Codigo`
  donde `Clase=RECHAZADO`).
- Si no es JSON parseable → CUV inválido (texto plano con error de red).

Los `CUV_*.json` de las 6 facturas DOCKERRIPS contienen literalmente:

```
Se ha generado un error en el consumo
Se ha generado un error en el proceso de login
One or more errors occurred. (No connection could be made because the target
machine actively refused it. (dockerrips.hus.gov.co:9443))
```

Eso es el mensaje que devolvió el servicio interno del HUS cuando intentó
validar los RIPS contra MinSalud — el container `dockerrips` estaba caído /
rechazó conexiones / dio timeout. El sistema guardó el error como si fuera el
resultado, y `consolidar_carpetas_notas.py` lo movió a `CUV_*.json` sin saber
que era basura.
