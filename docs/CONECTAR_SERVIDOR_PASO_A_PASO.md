# Conectar el servidor de archivos del HUS al motor — paso a paso

> **Para Yesid** — sin presupuesto Render, sin tocar Infra.
> Esta guía hace que el motor en Render vea los PDFs del servidor
> `\\Prime\radicacion_2026` (drive `Y:\`) usando una PC del HUS como
> "puente". Tarda 15 minutos la primera vez. Después corre solo.

## Cómo funciona

```
┌──────────────────┐   HTTP POST    ┌─────────────────────┐
│ PC del HUS (Y:\) │  ─────────►   │ motor en Render     │
│ jumpbox_sync.py  │   PDFs        │ /soportes-auto/...  │
└──────────────────┘                └─────────────────────┘
        │                                     │
        ▼                                     ▼
   \\Prime\radicacion_2026             SOPORTES_LOCAL_ROOT
   (servidor HUS - red local)          (disco Render)
```

La PC del HUS lee el share, hace **diff** (solo manda lo nuevo/cambiado)
y empuja los archivos al motor por HTTP. El motor los guarda en su disco
local y los indexa. **Cero cambios en Infra**.

---

## Lo que necesitás antes de empezar

| Recurso | Cómo conseguirlo |
|---------|------------------|
| Una PC del HUS con Windows | Cualquier PC tuya o de cartera con acceso a `Y:\` |
| Que esa PC pueda ver `Y:\` | Abrí Explorador → drive `Y:` debe mostrar las carpetas `ABRIL 2026...`, `MAYO 2026...` |
| Acceso a internet de esa PC | Tiene que poder abrir `https://motor-glosas-hus.onrender.com` |
| Python 3.9+ instalado | Si no lo tenés: descargá de https://www.python.org/downloads/ — tildá **"Add Python to PATH"** durante la instalación |
| Tu token de SUPER_ADMIN del motor | Cómo sacarlo: ver paso 4 |

---

## Paso 1 — Verificar que la PC ve `Y:\`

Abrí **Explorador de archivos** y andá a `Y:\`. Tenés que ver:

```
ABRIL 2026 - SOPORTES RADICACION
FEBRERO 2026 - SOPORTES RADICACION
MARZO 2026 - SOPORTES RADICACION
MAYO 2026 - SOPORTES RADICACION
Radicacion Digital - Carpeta 2
```

Si **NO** ves esto, entrá con tus credenciales: `\\Prime\radicacion_2026`
(probablemente ya está mapeado).

---

## Paso 2 — Descargar el agente

1. Abrí `https://github.com/yesidbadillo820-ship-it/motor-glosas-hus/tree/motor-glosas/tools`
2. Click en **`jumpbox_sync.py`**
3. Click en el botón **"Raw"** (arriba a la derecha)
4. Click derecho en la página → **"Guardar como..."** → guardalo como
   `C:\motor-glosas\jumpbox_sync.py`

(Si no existe la carpeta `C:\motor-glosas`, creala primero.)

---

## Paso 3 — Instalar dependencias

Abrí **PowerShell** (Windows + R → escribí `powershell` → Enter):

```powershell
cd C:\motor-glosas
pip install requests
```

Si Python no está instalado, ahora es el momento. Bajalo de
https://www.python.org/downloads/ y al instalarlo, **tildá la casilla
"Add Python to PATH"** (es crítico).

---

## Paso 4 — Sacar tu token del motor

1. Abrí `https://motor-glosas-hus.onrender.com` y entrá con tu usuario
2. Apretá `F12` para abrir las herramientas de desarrollador
3. Click en pestaña **"Network"** (o "Red")
4. Refrescá la página con `F5`
5. En la lista de la izquierda, click en cualquier request (por ejemplo `mis-asignaciones`)
6. En el panel derecho, scrolleá a **"Request Headers"**
7. Buscá la línea `Authorization: Bearer eyJhbGciOi...` (es muy larga)
8. Copiá **todo lo que va después de "Bearer "** (el `eyJhbG...` hasta el final)
9. Pegalo en un Bloc de notas — lo vas a usar en el siguiente paso

---

## Paso 5 — Configurar variables de entorno

En la misma PowerShell, ejecutá estos tres comandos (uno a la vez,
**reemplazando** el token por el que copiaste):

```powershell
[Environment]::SetEnvironmentVariable("MOTOR_URL", "https://motor-glosas-hus.onrender.com", "User")
[Environment]::SetEnvironmentVariable("MOTOR_TOKEN", "eyJhbGciOiJ...PEGAR_TU_TOKEN_AQUI...", "User")
[Environment]::SetEnvironmentVariable("SHARE_ROOT", "Y:\", "User")
```

**Cerrá la PowerShell y volvé a abrirla** para que tome las variables.

Verificá que se guardaron:
```powershell
echo $env:MOTOR_URL
echo $env:SHARE_ROOT
```

(El token NO lo imprimas — es secreto.)

---

## Paso 6 — Primera prueba: una pasada manual

```powershell
cd C:\motor-glosas
python jumpbox_sync.py --once
```

Vas a ver algo así:
```
[INFO] Conectando a https://motor-glosas-hus.onrender.com...
[INFO] Manifest descargado: 0 archivos en el motor
[INFO] Escaneando Y:\ ...
[INFO] Encontré 8.432 archivos en el share
[INFO] Diff: 8.432 archivos para subir (0 nuevos, 8.432 cambiados/faltantes)
[INFO] Subiendo lote 1/169 (50 archivos)...
...
[INFO] Pasada completa. 8.432 archivos subidos en 12 min.
[INFO] Llamando a /soportes-auto/reindex...
[INFO] OK: 8.432 archivos / 1.247 facturas indexadas.
```

La **primera pasada** sube TODO (puede tardar 10-30 min según volumen).
Las siguientes solo suben lo nuevo (segundos).

---

## Paso 7 — Verificar en el motor

Andá al motor → sidebar **"Soportes"**. Vas a ver:
- **Estado: ✓ Raíz accesible** (verde)
- **Facturas indexadas: 1.247**
- **Archivos indexados: 8.432**

En **"Buscar soportes por factura"**, pegá `HUS0000487175` → tabla con
los PDFs de esa factura.

En **"Mis glosas pendientes"**, las facturas que tienen soportes ahora
muestran un badge verde **`📁 4`** al lado del número de radicado. Si
hacés click en una glosa con ese badge, el motor va a usar esos PDFs
en el dictamen automáticamente.

---

## Paso 8 — Dejar el agente corriendo permanente

Para que sincronice cada 30 minutos automáticamente:

```powershell
python C:\motor-glosas\jumpbox_sync.py --loop --interval-min 30
```

Dejá la PowerShell abierta. Mientras esté abierta, sincroniza.

### Para que sobreviva reinicios — Tarea programada

Abrí PowerShell **como administrador** y ejecutá:

```powershell
$accion = New-ScheduledTaskAction -Execute "python.exe" `
  -Argument "C:\motor-glosas\jumpbox_sync.py --loop --interval-min 30" `
  -WorkingDirectory "C:\motor-glosas"
$disparador = New-ScheduledTaskTrigger -AtLogOn
$config = New-ScheduledTaskSettingsSet -StartWhenAvailable `
  -DontStopOnIdleEnd -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "MotorGlosasJumpbox" `
  -Action $accion -Trigger $disparador -Settings $config `
  -Description "Sincroniza Y:\ con el motor de glosas en Render"
```

Listo. Cuando reinicies la PC, el agente arranca solo al loguearte.

---

## Apagar el agente (cuando ya no lo necesités)

```powershell
Unregister-ScheduledTask -TaskName "MotorGlosasJumpbox" -Confirm:$false
```

Y quitar las variables:
```powershell
[Environment]::SetEnvironmentVariable("MOTOR_TOKEN", $null, "User")
```

---

## Problemas comunes

| Síntoma | Causa probable | Solución |
|---------|----------------|----------|
| `python: command not found` | Python no está en PATH | Reinstalá Python tildando "Add to PATH" |
| `401 Unauthorized` | Token expiró o mal copiado | Sacá el token de nuevo (paso 4) — duran 24h |
| `403 Forbidden` | Tu usuario no es auditor+ | Pedile al admin que te suba a SUPER_ADMIN |
| `Connection refused` | El motor está caído (OOM) | Esperá 2 minutos y reintentá |
| `Share Y:\ no accesible` | Sesión SMB caducada | Logout/login Windows o `net use Y: /delete` y mapear de nuevo |
| Sube TODO cada vez | El motor borró su disco (deploy nuevo) | Es normal — la próxima pasada vuelve a estado normal |

---

## ¿Cuánta plata se ahorra vs Render Standard?

- Render Standard 2 GB: **$25 USD/mes** (~$110.000 COP)
- Esta solución: **$0** (usás una PC que ya existe en el HUS)
- Ahorro anual: **~$1.300.000 COP**

---

## Siguiente paso (cuando ya esté funcionando)

Pedirle a Sistemas/Infra que en algún momento monte el share
directamente en Render (Plan A) — eso elimina la necesidad del agente
y pasa a tiempo real (vs sync cada 30 min). Pero mientras tanto,
**este Plan B funciona perfecto y resuelve el 100% del caso de uso**.
