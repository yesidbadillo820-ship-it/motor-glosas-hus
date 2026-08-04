# Migrar el Motor de Glosas de Google Cloud a un PC del hospital

> **Por qué existe esta guía (03-08-2026):** la cuenta de facturación de
> Google Cloud quedó cerrada y Google apaga la máquina virtual cuando eso
> pasa. Como el PC de cartera permanece siempre encendido, el sistema se
> muda ahí: **misma página (iaglosassinac.help), mismos datos, mismos
> usuarios, mismo deploy automático — y sin pagar servidor.**
>
> El flujo de trabajo NO cambia: el código sigue en GitHub, los PR se
> fusionan igual, y el PC aplica los cambios solo (cada 5 minutos), igual
> que lo hacía la VM.

## Resumen de las 4 fases

| Fase | Qué se hace | Dónde | Tiempo |
|---|---|---|---|
| 0 | Reabrir la cuenta de facturación (una sola vez, ~$11 mil COP) | Navegador | 10 min |
| 1 | Rescatar los datos y la llave del túnel de la VM | Cloud Shell | 15 min |
| 2 | Preparar el PC (Docker Desktop + Git) | PC del hospital | 20 min |
| 3 | Instalar con doble clic y verificar | PC del hospital | 15 min |

Al final: se apaga la VM para siempre (fase 4, opcional pero recomendada).

---

## Fase 0 — Reabrir la facturación (prerequisito)

Sin esto no se puede entrar al disco de la VM apagada.

1. Entrar con la cuenta de Google del proyecto a
   <https://console.cloud.google.com/billing>.
2. Abrir **"Mi cuenta de facturación 2"** → botón **"Reabrir cuenta"** →
   poner una tarjeta válida y pagar el saldo pendiente (~$11.278 COP).
3. Volver a <https://console.developers.google.com/billing/enable?project=motor-glosas-hus>
   y vincular el proyecto a la cuenta reabierta.
4. Esperar ~5 minutos.

## Fase 1 — Rescatar los datos (en Cloud Shell)

Pegar estos comandos **uno por uno** en Cloud Shell
(<https://console.cloud.google.com>, ícono `>_` arriba a la derecha):

```bash
# 1. Encender la VM
gcloud compute instances start motor-glosas --zone=us-west1-a
```

Esperar ~2 minutos a que arranque, y luego:

```bash
# 2. Hacer una copia fresca de la base y empaquetar TODO lo que se necesita
gcloud compute ssh motor-glosas --zone=us-west1-a --command 'sudo bash -c "
cd /opt/motor-glosas
docker exec motor-glosas-hus python -c \"from app.services.backup_sqlite import crear_backup; print(crear_backup())\"
ULTIMO=\$(ls -t data/backups/*.db | head -1)
tar czf /tmp/rescate-motor-glosas.tgz .env deploy/cloudflared \"\$ULTIMO\"
chmod 644 /tmp/rescate-motor-glosas.tgz
ls -lh /tmp/rescate-motor-glosas.tgz
"'
```

```bash
# 3. Traer el paquete a Cloud Shell y descargarlo al PC
gcloud compute scp motor-glosas:/tmp/rescate-motor-glosas.tgz . --zone=us-west1-a
cloudshell download rescate-motor-glosas.tgz
```

El navegador descargará `rescate-motor-glosas.tgz` (queda en Descargas).
**Ese archivo contiene las llaves y la base: guardarlo con cuidado y no
compartirlo.**

## Fase 2 — Preparar el PC del hospital

Una sola vez, con permisos de administrador del PC:

1. **Docker Desktop**: descargar de <https://www.docker.com/products/docker-desktop/>
   e instalar (aceptar la opción de WSL 2 si la pregunta; puede pedir
   reiniciar). Al abrirlo por primera vez, verificar en Configuración →
   General que esté marcada **"Start Docker Desktop when you sign in"**.
2. **Git**: si al abrir un cmd `git --version` no responde, instalarlo de
   <https://git-scm.com/download/win> (todo con "Siguiente").
3. El PC debe quedar **siempre encendido y con la sesión iniciada**
   (bloqueada con Windows+L está bien). En Configuración de Windows →
   Energía: pantalla puede apagarse, pero el equipo **nunca suspender**.

## Fase 3 — Instalar con doble clic

1. Descargar del repositorio el instalador
   `tools/MONTAR_SERVIDOR_MOTOR_GLOSAS.cmd` (o clonar el repo y abrirlo
   desde ahí) y ejecutarlo con **doble clic**.
2. El instalador:
   - verifica Docker y Git,
   - clona el repositorio en `C:\motor-glosas\repo`,
   - pide la ruta del `rescate-motor-glosas.tgz` y restaura la base, el
     `.env` y la llave del túnel,
   - construye y levanta los contenedores (motor + túnel),
   - deja programadas dos tareas de Windows:
     - **Autodeploy** cada 5 minutos (igual que en la VM: si hay código
       nuevo fusionado, lo aplica solo), y
     - **Copia de seguridad** diaria 9:00 a. m. hacia la carpeta que se
       indique (ideal: el share del hospital o una carpeta de Drive/OneDrive
       sincronizada — así la base y su copia NO viven en el mismo disco).
3. Al terminar, esperar 1-2 minutos y abrir <https://iaglosassinac.help>:
   debe cargar la página con todos los datos.

> Si algo falla, el instalador dice en pantalla exactamente qué faltó.
> Se puede volver a ejecutar las veces que sea: no daña nada.

## Arranque exprés SIN rescate (mientras Google desbloquea la cuenta)

> **Cuándo usar esto (04-08-2026):** la deuda ya se pagó pero Google exige
> que su equipo de soporte reabra la cuenta (caso #74044918, 24-48 horas).
> Para no tener al equipo parado, el sistema se levanta YA en el PC con una
> **base de datos nueva provisional**. La página, los usuarios y todas las
> pantallas funcionan de inmediato; la historia (oficios, envíos,
> dictámenes, soportes) vuelve cuando Google entregue el disco y se haga el
> rescate de la fase 1.

### A. Sacar el token del túnel de Cloudflare (5 minutos, una vez)

1. Entrar a <https://one.dash.cloudflare.com> con la cuenta de Cloudflare
   del dominio iaglosassinac.help.
2. Menú izquierdo: **Networks → Tunnels** (Redes → Túneles) → botón
   **Create a tunnel** → tipo **Cloudflared** → nombre `motor-glosas-pc` →
   **Save tunnel**.
3. Aparece la pantalla "Install and run a connector" con un comando largo
   que incluye una tira que empieza por `eyJ…` — ese es el token. Copiar
   el comando completo (el instalador saca el token solo).
4. Botón **Next** → pestaña **Public hostname** → **Add a public
   hostname**: Subdomain: *vacío*; Domain: `iaglosassinac.help`; Type:
   `HTTP`; URL: **`motor:8080` si se instala con Docker**, o
   **`localhost:8080` si se instala en modo SIN Docker** (ver B-bis) →
   **Save**.
5. **Si sale un error de que ya existe un registro DNS con ese nombre**
   (es el del túnel viejo de la VM): ir a <https://dash.cloudflare.com> →
   dominio `iaglosassinac.help` → **DNS → Records** → borrar el registro
   **CNAME** llamado `iaglosassinac.help` cuyo destino termina en
   `.cfargotunnel.com` → repetir el paso 4.

### B. Instalar con doble clic

1. Verificar la fase 2 (Docker Desktop corriendo + Git instalados).
2. Doble clic a `tools\REVIVIR_EXPRESS_SIN_RESCATE.cmd`. El instalador
   pide: la contraseña que tendrá `admin@hus.gov.co`, las llaves de IA
   (opcionales — la de Groq es gratis en <https://console.groq.com/keys>;
   Enter para saltarlas y ponerlas después) y el token del túnel.
3. Esperar 1-2 minutos y abrir <https://iaglosassinac.help>.

### B-bis. Si Docker Desktop no se puede instalar: modo SIN Docker

Para cuando el PC no permite Docker Desktop (sin permisos de
administrador, Windows sin virtualización, o bloqueado por sistemas).
El sistema corre igual, directo con **Python** (el mismo que ya usan los
otros bots del repositorio):

1. Requisitos: **Python 3.11+** (de <https://www.python.org/downloads/>,
   marcando la casilla **"Add python.exe to PATH"**) y **Git** — ninguno
   necesita permisos de administrador.
2. En Cloudflare (paso A), la URL del Public hostname es
   **`localhost:8080`** (no `motor:8080`).
3. Doble clic a `tools\REVIVIR_EXPRESS_SIN_DOCKER.cmd`. Pide lo mismo
   que el modo Docker (contraseña de admin, llaves de IA opcionales y el
   token del túnel) y además:
   - prepara el entorno de Python e instala las dependencias solo,
   - descarga `cloudflared.exe` (el programa oficial del túnel),
   - deja el **servidor** y el **túnel** corriendo con vigilantes que
     los reviven si se caen (`tools\servidor_motor_local.cmd` y
     `tools\tunel_motor_local.cmd`, registros en `data\servidor.log` y
     `data\tunel.log`),
   - deja el arranque automático al iniciar sesión (carpeta Inicio de
     Windows), el **autodeploy** cada 5 minutos
     (`tools\autodeploy_motor_local.cmd`) y la **copia de seguridad**
     diaria de las 9:00 a. m.
4. Verificar: en el propio PC abre <http://localhost:8080> y desde
   internet <https://iaglosassinac.help>.

> Los dos modos son equivalentes para el día a día (misma página, mismo
> autodeploy, mismas copias). Si algún día se instala Docker Desktop, se
> puede pasar al modo Docker corriendo el otro instalador.

### C. Cómo entra el equipo (base provisional)

- **Administrador:** `admin@hus.gov.co` con la contraseña inventada en el
  instalador.
- **Cada auditor:** su correo de siempre; contraseña inicial = la parte
  del correo antes del arroba (ej. `glosashus04`). El sistema obliga a
  cambiarla en el primer ingreso. Se siembran solos los 25 usuarios del
  equipo (incluidos YESID y ELIAS como administradores).

### D. Cuando Google reabra la cuenta

1. Hacer el rescate de la **fase 1** (los 3 bloques de Cloud Shell).
2. **Avisar al chat ANTES de restaurar nada:** se saca copia de la base
   provisional y se pasa la historia vieja al PC, fusionando lo que se
   haya trabajado en estos días donde sea posible.
3. Seguir con la **fase 4** (apagar la VM).

## Fase 4 — Apagar la VM (cuando la página ya funcione desde el PC)

**Importante:** primero verificar que la página carga y que los datos están
(consolidado, oficios, envíos). Luego, en Cloud Shell:

```bash
gcloud compute instances stop motor-glosas --zone=us-west1-a
```

Con la VM detenida el cobro baja casi a cero (solo el disco, ~US$1/mes).
Si se quiere costo CERO absoluto, eliminar la VM — pero solo cuando el PC
lleve unos días operando bien:

```bash
gcloud compute instances delete motor-glosas --zone=us-west1-a
```

## Cómo queda el día a día

- **Nada cambia para los auditores**: misma dirección, mismos usuarios.
- **Nada cambia para el desarrollo**: los PR se fusionan en GitHub y el PC
  los aplica solo en ≤5 minutos (tarea Autodeploy).
- **La copia de seguridad** sale a diario del PC hacia la carpeta elegida.
  El sistema además guarda sus copias internas a las 3:00 a. m. como
  siempre (retiene 14).
- **Si el PC se reinicia**, Docker y los contenedores arrancan solos al
  iniciar sesión; el túnel se reconecta solo.

## Si algo se daña

- La página no carga → verificar que Docker Desktop esté corriendo (ícono
  de la ballena en la bandeja) y que el PC tenga internet. Reinicio suave:
  abrir cmd en `C:\motor-glosas\repo` y correr `docker compose up -d`.
- Ver el estado: `docker compose ps` y
  `docker logs --tail 20 motor-glosas-cloudflared`.
- Restaurar una copia: las copias diarias están en la carpeta destino y en
  `C:\motor-glosas\repo\data\backups`.
