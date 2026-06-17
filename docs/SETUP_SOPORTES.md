# Conectar el servidor de soportes del HUS al motor de glosas

**Estado actual (17-jun-2026):** `iaglosassinac.help` corre en Fly.io (cloud). El servidor de archivos del HUS `\\Prime\radicacion_2026` está en la red local del hospital. El panel **Soportes** muestra `Facturas indexadas: 0` porque no hay puente entre ambos. Mientras eso no se conecte, el **Auditor Forense IA** siempre dirá `N/A` en cada glosa.

Esta guía es **paso a paso** para que un técnico del HUS (no de SINAC) lo levante. Hay dos planes — elige el que mejor encaje con la infraestructura del HUS.

---

## Plan B — Jump-box agent (recomendado · 1 día)

**Por qué este primero:** no expone `\\Prime` a Internet, funciona detrás del firewall del HUS sin cambios de red, y se puede revertir apagando un servicio.

### Arquitectura

```
┌─────────────────┐      HTTPS cada N min      ┌──────────────────┐
│  Jump-box HUS   │ ────────────────────────►  │  motor-glosas    │
│  (PC dedicada)  │   sube índice + archivos   │  (Fly.io cloud)  │
│                 │                            │                  │
│  Y:\ → mapeo    │                            │  /data/soportes  │
│  \\Prime\radica │                            │  indexado        │
└─────────────────┘                            └──────────────────┘
```

### Requisitos en el HUS
1. Una PC Windows o Linux con:
   - Acceso al share `\\Prime\radicacion_2026` (montado como `Y:\` por ejemplo)
   - Salida a Internet vía HTTPS (puerto 443)
   - Python 3.10+ instalado
   - Que pueda quedar encendida 24/7 (puede ser una VM o un mini-PC dedicado)
2. Un usuario de servicio en SINAC con rol `INTEGRACION` para emitir el token (lo gestiona Yesid).

### Pasos

#### 1. Crear el usuario y token de integración (lo hace Yesid o SUPER_ADMIN en el panel)
- Panel **Usuarios** → "Crear Usuario"
- Email: `jumpbox.hus@sinacsc.com`
- Rol: `INTEGRACION` (acceso solo a `/soportes/upload-batch`, sin login UI)
- Marcar "Generar token API"
- Copiar el token largo (se muestra una sola vez) — esto es el `MOTOR_TOKEN`.

#### 2. Instalar el agente en la jump-box
```powershell
# Windows PowerShell (admin)
mkdir C:\sinac-jumpbox
cd C:\sinac-jumpbox
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install requests watchdog

# Descargar el script jumpbox_sync.py desde el panel admin del motor
# (Panel Soportes → "Plan B - Setup paso a paso" → botón Descargar agente)
```

#### 3. Configurar variables de entorno (Windows)
Crea `C:\sinac-jumpbox\.env`:
```
MOTOR_URL=https://motor-glosas-hus.fly.dev
MOTOR_TOKEN=<el token largo del paso 1>
SHARE_ROOT=Y:\
INTERVALO_MINUTOS=15
```

#### 4. Hacer que arranque solo (Windows Service)
```powershell
# Instalar NSSM
choco install nssm -y

# Registrar el servicio
nssm install SinacJumpbox "C:\sinac-jumpbox\venv\Scripts\python.exe" "C:\sinac-jumpbox\jumpbox_sync.py"
nssm set SinacJumpbox AppDirectory C:\sinac-jumpbox
nssm set SinacJumpbox AppStdout C:\sinac-jumpbox\stdout.log
nssm set SinacJumpbox AppStderr C:\sinac-jumpbox\stderr.log
nssm start SinacJumpbox
```

#### 5. Verificar
- En la jump-box: `Get-Content C:\sinac-jumpbox\stdout.log -Tail 50` → ver líneas tipo `[INFO] Subidos 124 archivos a motor-glosas-hus.fly.dev`
- En el motor (web): **Soportes** → "Facturas indexadas" debe pasar de 0 a la cifra real (puede tardar la primera vez 30-60 min).
- Probar **Analizar glosa** → "Auditor Forense IA" debe responder con citas reales de los soportes.

---

## Plan A — Mount CIFS directo (alternativa · requiere VPN)

**Por qué NO es el plan principal:** requiere abrir un túnel desde Fly.io hasta `\\Prime`, lo cual exige VPN site-to-site o un proxy de archivos. Más complejo, más superficie de ataque, más caro.

### Arquitectura

```
Fly.io (motor) ──VPN──► HUS network ──CIFS──► \\Prime\radicacion_2026
                                              (montado como /mnt/radicacion_2026)
```

### Pasos resumidos
1. Levantar VPN site-to-site entre Fly.io (WireGuard) y el firewall del HUS — coordinarlo con el equipo de redes del HUS.
2. En la app de Fly.io, configurar variable `SOPORTES_ROOT=/mnt/radicacion_2026`.
3. En el `Dockerfile`, montar el CIFS con `cifs-utils`:
   ```
   mount -t cifs //prime/radicacion_2026 /mnt/radicacion_2026 \
     -o username=svc-motorglosas,password=$CIFS_PWD,vers=3.0,ro
   ```
4. Reiniciar la app y verificar que `Soportes` indexe.

### Riesgos
- Si cae la VPN → todas las consultas a Auditor Forense IA fallan.
- Latencia 5-10x mayor que Plan B (cada lectura de archivo va a la red).
- Las credenciales del share quedan en el container de Fly.io (debe rotarse trimestral).

---

## Estructura de carpetas esperada en `\\Prime\radicacion_2026`

El indexador del motor lee la siguiente convención. Si las carpetas del HUS no la siguen, hay que renombrar o adaptar el regex en `app/services/soportes_service.py`.

```
\\Prime\radicacion_2026\
├── ENERO 2026\
│   ├── SOPORTES RADICACION\
│   │   ├── FAMISANAR\
│   │   │   ├── FVS_900006037_HUS0000506597.pdf      ← Factura Venta
│   │   │   ├── HC_HUS0000506597.pdf                  ← Historia Clínica
│   │   │   ├── RIPS_HUS0000506597.xml                ← RIPS
│   │   │   └── ORDEN_MED_HUS0000506597.pdf
│   │   ├── FOMAG\
│   │   ├── COMPENSAR\
│   │   └── ...
│   └── DEVOLUCIONES\
├── FEBRERO 2026\
├── ...
└── JUNIO 2026\
```

- `{MES} {AÑO}` — carpeta raíz por mes
- `SOPORTES RADICACION / {EPS}` — segundo nivel por entidad pagadora
- Archivos nombrados con el número de factura HUS (`HUS0000XXXXXX`) para que el indexador los empareje

Si el HUS ya tiene otra convención (ej. carpetas por radicado en lugar de mes), avisar a Yesid para ajustar el parser.

---

## Costos

| Plan | Hardware | Licencias | Setup | Mensual |
|------|----------|-----------|-------|---------|
| B (jump-box) | mini-PC ~$300 USD (una vez) | gratis | 1 día técnico HUS | $0 |
| A (CIFS+VPN) | usa servidor existente | WireGuard cloud ~$20/mes | 3-5 días redes | $20 |

---

## ¿Qué pasa mientras no se conecte?

- El panel **Soportes** sigue mostrando 0/0.
- El **Auditor Forense IA** dice "N/A" en cada glosa.
- Los dictámenes **siguen funcionando** — solo pierden la capacidad de citar folios y fechas exactas de los soportes.
- El motor sigue generando respuestas válidas usando la información que el gestor pegue en el texto de la glosa y los datos clínicos.

**Recomendación inmediata:** levantar Plan B esta semana. Es la pieza que falta para que el sistema entregue el 100% del valor prometido.
