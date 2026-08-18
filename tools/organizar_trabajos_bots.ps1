<#
    organizar_trabajos_bots.ps1  -  Ayudante del Motor Glosas HUS.

    Arma (o vuelve a poner al dia) la carpeta "D:\TRABAJOS BOTS": una
    carpeta por frente de trabajo (COOSALUD, SIMED, DGH, SIIFA, ADRES,
    Suite Cartera, etc.) con:
      - accesos directos a los bots de doble clic que ya existen,
      - un LEEME.txt en español sencillo explicando cuándo usar cada
        cosa y, si el bot no tiene doble clic, el comando listo para
        copiar y pegar,
      - accesos directos a la guía (docs\...) de ese frente.

    No copia ni mueve ningún archivo del repositorio: solo crea accesos
    directos, así que si el bot cambia, el acceso directo sigue
    funcionando sin volver a correr este script (aunque conviene
    correrlo de nuevo si se agregó un bot nuevo).

    USO: doble clic en ORGANIZAR_TRABAJOS_BOTS.cmd (misma carpeta).
    Se puede correr las veces que haga falta: es seguro, no borra nada
    que el auditor haya puesto a mano dentro de "D:\TRABAJOS BOTS".
#>

param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$Destino = "D:\TRABAJOS BOTS"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path (Join-Path $RepoRoot "tools"))) {
    Write-Host ""
    Write-Host "  [!] No encuentro la carpeta 'tools' dentro de $RepoRoot" -ForegroundColor Red
    Write-Host "      Este script debe vivir dentro de la carpeta tools\ del repositorio." -ForegroundColor Red
    Write-Host ""
    Read-Host "Presiona Enter para salir"
    exit 1
}

$Tools = Join-Path $RepoRoot "tools"
$Docs = Join-Path $RepoRoot "docs"

function Asegurar-Carpeta([string]$Ruta) {
    if (-not (Test-Path -LiteralPath $Ruta)) {
        New-Item -ItemType Directory -Path $Ruta -Force | Out-Null
    }
}

function Guardar-Texto([string]$Ruta, [string]$Texto) {
    Set-Content -LiteralPath $Ruta -Value $Texto -Encoding UTF8
}

$WshShell = New-Object -ComObject WScript.Shell

function Nuevo-Atajo {
    param(
        [string]$RutaLink,
        [string]$Objetivo,
        [string]$Argumentos = "",
        [string]$Descripcion = ""
    )
    if (-not (Test-Path -LiteralPath $Objetivo)) {
        Write-Host "      (aviso) no existe todavia: $Objetivo" -ForegroundColor DarkYellow
        return
    }
    $Acceso = $WshShell.CreateShortcut($RutaLink)
    $Acceso.TargetPath = $Objetivo
    if ($Argumentos) { $Acceso.Arguments = $Argumentos }
    $Acceso.WorkingDirectory = Split-Path -Parent $Objetivo
    if ($Descripcion) { $Acceso.Description = $Descripcion }
    $Acceso.Save()
}

function Atajo-Doc {
    param([string]$RutaLink, [string]$RutaDoc, [string]$Descripcion = "")
    if (-not (Test-Path -LiteralPath $RutaDoc)) { return }
    $Notepad = Join-Path $env:WINDIR "System32\notepad.exe"
    Nuevo-Atajo -RutaLink $RutaLink -Objetivo $Notepad -Argumentos ('"' + $RutaDoc + '"') -Descripcion $Descripcion
}

Write-Host ""
Write-Host "============================================================"
Write-Host "  ORGANIZAR TRABAJOS BOTS - Motor Glosas HUS"
Write-Host "============================================================"
Write-Host "  Repositorio : $RepoRoot"
Write-Host "  Destino     : $Destino"
Write-Host ""

Asegurar-Carpeta $Destino

# ---------------------------------------------------------------------
# 1) COOSALUD
# ---------------------------------------------------------------------
$c = Join-Path $Destino "1. COOSALUD"
Asegurar-Carpeta $c
Atajo-Doc (Join-Path $c "Guia COOSALUD.lnk") (Join-Path $Docs "CONTEXTO_COOSALUD.md") "Guia completa del frente COOSALUD"
Guardar-Texto (Join-Path $c "LEEME.txt") @"
COOSALUD (portal vco.ctamedicas.com)
=====================================
Los archivos de verdad estan en: $Tools

CUANDO VENIR A ESTA CARPETA
  - Te piden subir/cerrar las respuestas de glosas de COOSALUD.
  - Te piden revisar que factura quedo pendiente en COOSALUD.
  - Te piden armar el consolidado o las objeciones de un lote COOSALUD.

QUE BOT USAR
  - responder_glosas_coosalud.py  -> el robot que entra al portal y
    responde las glosas en grupo (deja pantallazo de cierre).
  - verificar_glosas_coosalud.py  -> auditoria rapida: que quedo
    pendiente de un lote ya cargado.
  - consolidar_coosalud.py        -> arma el consolidado de un lote.
  - organizar_cargue_masivo_coosalud.py / organizar_objeciones_vco.py
    -> organiza el ZIP del portal / arma el Excel de OBJECIONES.
  - coosalud_todo.py              -> encadena varios pasos del flujo.

REGLA DE ORO: antes de un cargue masivo, SIEMPRE un piloto de 1 factura.

COMANDO (PowerShell, parado en la carpeta del proyecto):

  `$env:COOSALUD_USER = "usuario_del_portal"
  `$env:COOSALUD_PASSWORD = "clave_del_portal"
  py tools\responder_glosas_coosalud.py --excel "<RUTA_DEL_EXCEL>" --solo HUS0000000000 --reporte reporte_coosalud.csv

  Si el piloto sale bien, repetir cambiando --solo por --todas
  (o --lista <archivo.txt> con una factura por linea).

  Para reanudar un cargue que se corto (luz, portal caido) SIN duplicar
  nada: agregar --saltar-csv reporte_coosalud.csv y un --reporte nuevo.

  Para responder tambien la pertinencia medica (si el Excel ya trae la
  respuesta tipificada): agregar --incluir-calidad.

MAS DETALLE: doble clic en "Guia COOSALUD.lnk" (arriba, en esta misma
carpeta) o pide en el chat de Claude Code "abre docs/CONTEXTO_COOSALUD.md".
"@

# ---------------------------------------------------------------------
# 2) SIMED - DISPENSARIO MEDICO
# ---------------------------------------------------------------------
$c = Join-Path $Destino "2. SIMED - DISPENSARIO MEDICO"
Asegurar-Carpeta $c
Atajo-Doc (Join-Path $c "Guia glosas Dispensario en SIMED.lnk") (Join-Path $Docs "CONTEXTO_DISPENSARIO_GLOSAS.md") "Como se responden las glosas del Dispensario en SIMED"
Atajo-Doc (Join-Path $c "Guia notas credito Dispensario.lnk") (Join-Path $Docs "CONTEXTO_DISPENSARIO_NOTAS.md") "Como se cargan las notas credito del Dispensario en SIMED"
Atajo-Doc (Join-Path $c "Guia plataforma de conciliacion.lnk") (Join-Path $Docs "MODULO_CONCILIACION_DISPENSARIO.md") "Expediente y acta de conciliacion del Dispensario"
Guardar-Texto (Join-Path $c "LEEME.txt") @"
SIMED - DISPENSARIO MEDICO (Sanidad Ejercito)
==============================================
Los archivos de verdad estan en: $Tools

CUANDO VENIR A ESTA CARPETA
  - Te piden responder o subir glosas del Dispensario en SIMED.
  - Te piden cargar notas credito o soportes del Dispensario.
  - Te piden armar el expediente/acta de conciliacion del Dispensario.

QUE BOT USAR - responder glosas
  - responder_glosas_simed.py  -> responde glosas item por item.
  - organizar_objeciones_dispensario.py -> arma el Excel de OBJECIONES
    desde el PDF de AUDITOOL que manda DGH.

QUE BOT USAR - notas credito y soportes
  - verificar_cuv_notas.py   -> SIEMPRE antes de subir una nota credito
    (el portal acepta CUV invalido pero queda mal radicada).
  - cargar_soportes_simed.py -> sube los soportes de la nota credito.
  - renombrar_y_organizar_notas.py / consolidar_carpetas_notas.py /
    extraer_notas_credito.py / dividir_notas_por_acta.py -> orden de
    los PDF de notas credito antes de cargarlas.

QUE BOT USAR - plataforma de conciliacion (expediente por factura)
  - indexar_soportes_dispensario.py   -> indexa el share una sola vez.
  - expediente_conciliacion.py        -> arma el expediente por factura.
  - motor_evidencia_dispensario.py, motor_verificacion_dispensario.py,
    motor_decision_dispensario.py     -> localizan la prueba, fijan los
    hechos y califican que tan defendible es cada glosa.
  - hoja_maestra_conciliacion.py      -> expediente en un solo Excel.
  - generar_acta_conciliacion_dispensario.py -> acta formato SINAC.
  - piloto_conciliacion_dispensario.py -> corre el piloto de 5 casos.

REGLA DE ORO: piloto de 1 factura antes de un cargue masivo.

COMANDO (PowerShell, parado en la carpeta del proyecto):

  `$env:SIMED_USER = "usuario_del_portal"
  `$env:SIMED_PASSWORD = "clave_del_portal"
  py tools\responder_glosas_simed.py --excel "<RUTA_DEL_EXCEL>" --solo HUS0000000000 --con-cabeza

  Si el piloto sale bien, repetir cambiando --solo por --todas.
  Para no re-subir lo ya contestado se omiten solas las objeciones ya
  respondidas (usar --rehacer solo si de verdad hay que repetirlas).

MAS DETALLE: los 3 accesos de arriba abren las guias completas.
"@

# ---------------------------------------------------------------------
# 3) DINAMICA GERENCIAL (DGH)
# ---------------------------------------------------------------------
$c = Join-Path $Destino "3. DINAMICA GERENCIAL (DGH)"
Asegurar-Carpeta $c
Guardar-Texto (Join-Path $c "LEEME.txt") @"
DINAMICA GERENCIAL - DGH (programa de escritorio del hospital)
================================================================
Los archivos de verdad estan en: $Tools

CUANDO VENIR A ESTA CARPETA
  - Te piden cargar el tramite de una glosa directo en DGH.
  - Te piden corregir un tramite que quedo mal en DGH.

OJO: DGH NO es un portal de internet, es un programa de escritorio.
La ventana de respuesta no se deja leer por dentro, asi que el bot la
opera por COORDENADAS de pantalla (como si moviera el mouse a mano).
Por eso es el mas delicado de calibrar: SIEMPRE probar primero sin
--grabar y con --solo una factura.

QUE BOT USAR
  - responder_glosas_dgh.py -> carga el tramite de objecion.
  - respuesta_tramites_dgh.py / completar_tramite_glosas_aceptadas.py /
    convertir_tramite_masivo.py -> variantes del cargue de tramites.
  - corregir_errores_dgh.py -> corrige tramites que quedaron mal.
  - login_dg.py / dump_dg.py -> herramientas de apoyo (entrar, revisar
    la ventana).

COMANDO (PowerShell, parado en la carpeta del proyecto):

  py tools\responder_glosas_dgh.py --excel "<RUTA_DEL_EXCEL>" --solo HUS0000000000 --calibrar

  Ese primer comando SOLO mueve el mouse a cada control (no hace clic,
  no graba nada: riesgo cero) para revisar que las coordenadas calcen
  con la pantalla de este equipo. Cuando calce, quitar --calibrar y
  correr sin --grabar para ver que llene bien el formulario, y solo al
  final agregar --grabar para que quede guardado de verdad:

  py tools\responder_glosas_dgh.py --excel "<RUTA_DEL_EXCEL>" --solo HUS0000000000 --grabar

  Cuando ya este probado con varias facturas sueltas, recien ahi usar
  --todas en vez de --solo.
"@

# ---------------------------------------------------------------------
# 4) SIIFA
# ---------------------------------------------------------------------
$c = Join-Path $Destino "4. SIIFA (Ministerio de Salud)"
Asegurar-Carpeta $c
Nuevo-Atajo (Join-Path $c "CARGAR SIIFA (doble clic).lnk") (Join-Path $Tools "CARGAR_SIIFA.cmd") "" "Menu unico de SIIFA: bajar informe, armar respuestas, piloto y cargue"
Atajo-Doc (Join-Path $c "Guia SIIFA.lnk") (Join-Path $Docs "CONTEXTO_SIIFA.md") "Que es SIIFA, roles, plazos y endpoints"
Atajo-Doc (Join-Path $c "Cargue SIIFA paso a paso.lnk") (Join-Path $Docs "CARGUE_SIIFA_PASO_A_PASO.md") "Guia operativa paso a paso del cargue SIIFA"
Guardar-Texto (Join-Path $c "LEEME.txt") @"
SIIFA (plataforma nacional del Ministerio de Salud)
====================================================
Los archivos de verdad estan en: $Tools

OJO: SIIFA NO es un portal de una EPS (no es COOSALUD ni SIMED). Es la
plataforma nacional de seguimiento de facturas, y a diferencia de las
otras tiene API oficial: los bots hablan directo con el servidor, sin
abrir navegador.

CUANDO VENIR A ESTA CARPETA
  - Te piden bajar el listado de seguimientos de SIIFA a Excel.
  - Te piden responder o cargar glosas/devoluciones en SIIFA.

COMO EMPEZAR (mas facil): doble clic en "CARGAR SIIFA (doble clic).lnk"
Ese menu ya trae las 4 opciones en orden: bajar el informe, armar los
archivos de respuestas, piloto de 1 glosa y cargue masivo con reporte.

Piezas por si hace falta usarlas sueltas:
  - siifa_client.py -> motor comun (login, paginacion, respuesta API).
  - siifa_reporte_seguimientos.py -> Excel masivo de TODOS los
    seguimientos del HUS.
  - responder_glosas_siifa.py -> lee un Excel tipificado y carga cada
    respuesta por API (mismo patron de piloto/reporte que COOSALUD).
  - siifa_preparar_respuestas.py / siifa_redactar_respuestas.py -> arman
    y redactan el Excel de respuestas.
  - siifa_cruzar_tramites_dgh.py -> cruza SIIFA contra lo ya respondido
    en DGH (para no redactar dos veces lo mismo).
  - siifa_corregir_rechazadas.py / siifa_verificar_cargue.py -> corrige
    lo rechazado y verifica que el cargue quedo bien.

MAS DETALLE: los dos accesos de arriba abren las guias completas.
"@

# ---------------------------------------------------------------------
# 5) ADRES - FURIPS
# ---------------------------------------------------------------------
$c = Join-Path $Destino "5. ADRES - FURIPS"
Asegurar-Carpeta $c
Nuevo-Atajo (Join-Path $c "VALIDAR FURIPS (doble clic).lnk") (Join-Path $Tools "adres\VALIDAR_FURIPS.cmd") "" "Valida FURIPS 1 y 2 contra la Circular 022-2023 y los soportes"
Nuevo-Atajo (Join-Path $c "VALIDADOR ADRES WEB (doble clic).lnk") (Join-Path $RepoRoot "validador-adres\VALIDADOR_ADRES_WEB.cmd") "" "La misma validacion FURIPS pero desde el navegador"
Nuevo-Atajo (Join-Path $c "INFORME BAJA DE CARTERA (doble clic).lnk") (Join-Path $Tools "INFORME_BAJA_CARTERA.cmd") "" "Informe Word+Excel de facturas que no cumplen la Res. 577-2019"
Nuevo-Atajo (Join-Path $c "COMPLETAR INFORME XML DIAN (doble clic).lnk") (Join-Path $Tools "COMPLETAR_INFORME_XML.cmd") "" "Completa el informe de devoluciones DE4401 (NUEVA EPS) desde los XML DIAN"
Atajo-Doc (Join-Path $c "Guia ADRES FURIPS.lnk") (Join-Path $Docs "ENTREGA_MODULO_ADRES_FURIPS.md") "Entrega tecnica completa del modulo ADRES-FURIPS"
Atajo-Doc (Join-Path $c "Guia RIPS-CUV.lnk") (Join-Path $Docs "CONTEXTO_FEV_RIPS_CUV.md") "Contexto de facturacion electronica, RIPS y CUV"
Guardar-Texto (Join-Path $c "LEEME.txt") @"
ADRES - FURIPS (validacion de reclamaciones, Circular 022 de 2023)
====================================================================
Los archivos de verdad estan en: $Tools\adres  y  $RepoRoot\validador-adres

CUANDO VENIR A ESTA CARPETA
  - Te piden validar los FURIPS 1/2 de un lote de facturas ADRES.
  - Te piden el informe de baja de cartera (Res. 577/2019).
  - Te piden completar el informe de devoluciones DE4401 de NUEVA EPS.

COMO EMPEZAR (mas facil, los 4 son de doble clic - arriba en esta
carpeta): "VALIDAR FURIPS", "VALIDADOR ADRES WEB" (lo mismo pero desde
el navegador con tablero y graficas), "INFORME BAJA DE CARTERA" y
"COMPLETAR INFORME XML DIAN". Cada uno se instala solo la primera vez
(Python, OCR) y despues pregunta la carpeta con los archivos.

Otras piezas sueltas:
  - validar_json_rips.py -> valida RIPS en formato JSON.
  - REVISAR_XML.cmd / VERIFICAR_RADICACION.cmd / AUTORIZACIONES_RIPS.cmd
    (doble clic, tambien estan en "10. HERRAMIENTAS GENERALES").

MAS DETALLE: los dos accesos de guia (arriba) explican todo el modulo.
"@

# ---------------------------------------------------------------------
# 6) GLOSAS ADRES Y DETALLADOS
# ---------------------------------------------------------------------
$c = Join-Path $Destino "6. GLOSAS ADRES Y DETALLADOS"
Asegurar-Carpeta $c
Atajo-Doc (Join-Path $c "Guia Glosas ADRES (pagina web).lnk") (Join-Path $Docs "GLOSAS_ADRES_WEB.md") "Modulo Glosas ADRES dentro de la aplicacion web"
Guardar-Texto (Join-Path $c "LEEME.txt") @"
GLOSAS ADRES Y DETALLADOS DE FACTURA (paquete de un envio ADRES)
==================================================================
Los archivos de verdad estan en: $Tools

CUANDO VENIR A ESTA CARPETA
  - Llego un paquete de glosas del ADRES (ej. "31068") con el reporte
    ReporteGlosasReclamPAQUETE y la macro de respuesta.
  - Te piden dejar el detallado de una factura SOLO con lo que sigue
    glosado (quitar lo ya aprobado por el ADRES).

MEJOR OPCION HOY: la pantalla web "Glosas ADRES" (menu -> Glosas ADRES)
hace esto mismo sin tocar la linea de comandos: se sube el reporte una
sola vez y el gestor solo escribe el numero de factura. Ver el acceso
de arriba para la guia completa.

Herramientas de linea de comandos (para lotes grandes o pasos previos):
  - preauditar_glosas_adres.py -> llena lo mecanico del Excel de la
    macro (mismo motor que usa la pagina web).
  - glosas_adres_por_factura.py -> el detalle de una sola factura.
  - ajustar_detallado_glosas.py -> deja el detallado de factura SOLO
    con lo que la entidad sigue glosando (quita lo aprobado, ajusta lo
    aprobado a medias, recalcula subtotal/total en letras). Tiene modo
    --diagnostico para ver que haria antes de escribir nada.
  - verificar_detallado_ajustado.py -> relee el Excel ajustado y lo
    contrasta contra el original y el reporte del ADRES.
  - dividir_detallado_por_factura.py -> separa el detallado en un Excel
    por factura, formato intacto.
  - excel_a_pdf.py -> convierte esos Excel a PDF en masa.

COMANDO tipico del ajustador (PowerShell):

  py tools\ajustar_detallado_glosas.py --detallado "<RUTA_EXCEL_DETALLADO>" --reporte "<RUTA_ReporteGlosasReclamPAQUETE>" --diagnostico

  Revisar el diagnostico y, si esta bien, repetir SIN --diagnostico
  para que escriba de verdad.
"@

# ---------------------------------------------------------------------
# 7) PRE-AUDITORIA SINAC
# ---------------------------------------------------------------------
$c = Join-Path $Destino "7. PRE-AUDITORIA SINAC (radicacion)"
Asegurar-Carpeta $c
Atajo-Doc (Join-Path $c "Guia tecnica Pre-auditoria.lnk") (Join-Path $Docs "PREAUDITORIA_DOCUMENTACION_TECNICA.md") "Documentacion tecnica completa del modulo de Pre-auditoria"
Guardar-Texto (Join-Path $c "LEEME.txt") @"
PRE-AUDITORIA SINAC (radicacion de facturas, plazo de 3 dias habiles)
========================================================================
ESTO NO ES UN BOT DE ESCRITORIO: vive dentro de la pagina web del Motor
de Glosas (menu -> 📄 Pre-auditoria, o la direccion .../preauditoria).

CUANDO VENIR A ESTA CARPETA
  - Te piden registrar un oficio radicado por Facturacion.
  - Te piden auditar facturas: soportes OK (radicar) o devolver con
    motivo, y sacar el oficio de devolucion en PDF.
  - Te piden el Excel de seguimiento para ADRES.

COMO EMPEZAR: entrar a la pagina del Motor de Glosas con tu usuario y
usar el menu Pre-auditoria. Si la pagina no responde, ver la carpeta
"11. MOTOR DE GLOSAS - SERVIDOR WEB" (ESTADO_MOTOR.cmd / REINICIAR_MOTOR.cmd).

Herramientas de apoyo en linea de comandos (para preparar los Excel que
se suben a la pagina, poco usadas dia a dia):
  - preauditoria_importar_consolidado.py
  - preauditoria_importar_oficios_devolucion.py
  - preauditoria_reconstruir_envios.py

MAS DETALLE: el acceso de arriba abre la guia tecnica completa del
modulo (que hace, como se usa, decisiones tomadas).
"@

# ---------------------------------------------------------------------
# 8) SUITE CARTERA HUS
# ---------------------------------------------------------------------
$c = Join-Path $Destino "8. SUITE CARTERA HUS"
Asegurar-Carpeta $c
Nuevo-Atajo (Join-Path $c "INICIAR SUITE CARTERA (doble clic).lnk") (Join-Path $Tools "suite_cartera_hus\INICIAR_SUITE.bat") "" "Programa de escritorio del analista de Cartera"
Nuevo-Atajo (Join-Path $c "Carpeta de la Suite (todo).lnk") (Join-Path $Tools "suite_cartera_hus") "" "Carpeta completa de la Suite Cartera HUS"
Guardar-Texto (Join-Path $c "LEEME.txt") @"
SUITE CARTERA HUS (programa de escritorio del analista de Cartera)
======================================================================
Los archivos de verdad estan en: $Tools\suite_cartera_hus

CUANDO VENIR A ESTA CARPETA
  - Cualquier trabajo del dia a dia de Cartera: organizar el ZIP de un
    portal, consolidar glosas, cruzar contra la base DGH, armar las
    OBJECIONES listas para cargar.
  - Herramientas PDF (unir, dividir, rotar, proteger, convertir
    Office<->PDF, resumir/traducir/OCR con IA): boton 🧰 dentro de la
    Suite.
  - Correos de pagos (.msg) a Excel: boton 📧 dentro de la Suite.
  - Unir varios Exceles en uno: boton 📊 dentro de la Suite.

COMO EMPEZAR: doble clic en "INICIAR SUITE CARTERA" (arriba, en esta
misma carpeta). Se abre la ventana completa del programa.

Si el equipo no tiene pantalla (servidor): version de consola,
suite_cli.py, dentro de la carpeta de la Suite.

Credenciales de los portales (COOSALUD, SIMED, DGH, etc.) para la Suite
van en tools\suite_cartera_hus\config\entidades.credenciales.json
- ese archivo es LOCAL de cada equipo, nunca se sube al repositorio.

Otras herramientas de Cartera (fuera de la Suite):
  - tablero_cartera.py -> Tablero de Radicacion y Cartera (HTML, alertas
    de mora +90 dias, exportar a Excel).
  - informe_gerencia.py -> informe de gestion para gerencia.
  - semaforo_vencimientos.py -> plazos de respuesta en dias habiles
    (tambien como SEMAFORO_GLOSAS.cmd en "10. HERRAMIENTAS GENERALES").
  - scoreboard.py / scoreboard_live.py -> marcador de avance.

MAS DETALLE: dentro de la carpeta de la Suite hay un LEEME.txt propio y
PASO_A_PASO_HERRAMIENTAS_PDF.txt con la guia de la caja de herramientas.
"@

# ---------------------------------------------------------------------
# 9) OTRAS EPS
# ---------------------------------------------------------------------
$c = Join-Path $Destino "9. OTRAS EPS (Mutual Ser, FOMAG, SAVIA, EMSSANAR, Famisanar)"
Asegurar-Carpeta $c
Atajo-Doc (Join-Path $c "Guia bot SAVIA.lnk") (Join-Path $Docs "ENTREGA_TECNICA_BOT_SAVIA.md") "Entrega tecnica del bot de objeciones SAVIA"
Guardar-Texto (Join-Path $c "LEEME.txt") @"
OTRAS EPS (pagadores mas chicos, un bot o script por cada uno)
==================================================================
Los archivos de verdad estan en: $Tools

CUANDO VENIR A ESTA CARPETA
  - Te piden algo de Mutual Ser, FOMAG, SAVIA, EMSSANAR o Famisanar.

MUTUAL SER
  - responder_glosas_mutual_ser.py -> responde glosas en el portal
    (mismo patron que COOSALUD: --solo primero, luego --facturas /
    --lista / --todas).
  - extraer_respuestas_glosa_mutualser.py -> saca las respuestas ya
    dadas a un formato de trabajo.
  Credenciales: `$env:MUTUALSER_USER / `$env:MUTUALSER_PASSWORD

FOMAG
  - responder_glosas_fomag.py -> responde glosas en el portal FOMAG
    (mismo patron: --solo / --facturas / --lista).
  Credenciales: `$env:FOMAG_USER / `$env:FOMAG_PASSWORD

SAVIA / EMSSANAR / FAMISANAR
  - organizar_objeciones_savia.py / organizar_objeciones_emssanar.py /
    organizar_objeciones_famisanar.py -> arman el Excel de OBJECIONES
    en el formato que pide cada una desde lo que manda el portal.

COMANDO tipico (ejemplo Mutual Ser, PowerShell):

  `$env:MUTUALSER_USER = "usuario_del_portal"
  `$env:MUTUALSER_PASSWORD = "clave_del_portal"
  py tools\responder_glosas_mutual_ser.py --excel "<RUTA_DEL_EXCEL>" --solo HUS0000000000

REGLA DE ORO: piloto de 1 factura antes de un cargue masivo, igual que
en COOSALUD.
"@

# ---------------------------------------------------------------------
# 10) HERRAMIENTAS GENERALES
# ---------------------------------------------------------------------
$c = Join-Path $Destino "10. HERRAMIENTAS GENERALES (PDF, Excel, ZIP)"
Asegurar-Carpeta $c
Nuevo-Atajo (Join-Path $c "MENU DE BOTS - MOTOR_HUS (doble clic).lnk") (Join-Path $Tools "MOTOR_HUS.cmd") "" "Menu unico: elige el numero del bot que necesitas"
$otrosCmd = @(
    "BUSCAR_FACTURA.cmd", "AUDITAR_DEV_EPS.cmd", "AUTORIZACIONES_RIPS.cmd",
    "CRUZAR_GLOSAS.cmd", "VERIFICAR_RADICACION.cmd", "SEMAFORO_GLOSAS.cmd",
    "UNIR_PDFS.cmd", "PDF_A_CMD.cmd", "PDF_A_CMD_EN_CARPETA.cmd",
    "EXCEL_A_CMD.cmd", "EXCEL_A_CSV.cmd", "TXT_A_EXCEL.cmd",
    "COMPRIMIR_ZIP.cmd", "PARTIR_ZIP_30MB.cmd", "REVISAR_XML.cmd",
    "VIGILANTE_NOCTURNO.cmd", "INFORME_GERENCIA.cmd"
)
foreach ($bot in $otrosCmd) {
    $nombreLink = ($bot -replace "\.cmd$", "") + ".lnk"
    Nuevo-Atajo (Join-Path $c $nombreLink) (Join-Path $Tools $bot)
}
Guardar-Texto (Join-Path $c "LEEME.txt") @"
HERRAMIENTAS GENERALES (PDF, Excel, ZIP, XML, radicacion)
=============================================================
Los archivos de verdad estan en: $Tools

CUANDO VENIR A ESTA CARPETA
  - No es un bot de un portal especifico: es unir/dividir PDF,
    convertir Excel/TXT/PDF a .cmd, comprimir o partir ZIP, revisar
    XML de factura electronica, verificar un lote antes de radicar,
    cruzar glosas de la EPS contra los XML, ver el semaforo de plazos,
    buscar los soportes de una lista de facturas, o sacar el informe
    de gerencia.

SI NO SABES CUAL BOT USAR: doble clic en "MENU DE BOTS - MOTOR_HUS"
(arriba, en esta misma carpeta). Es un menu numerado de las 17
herramientas mas usadas; cada uso queda anotado solo (quien, cuando,
que bot) para el informe de gerencia.

Los demas accesos de esta carpeta son cada bot suelto (por si ya sabes
cual necesitas y quieres ir directo, sin pasar por el menu):
  - BUSCAR_FACTURA         -> recolecta los soportes de una lista de
                               facturas desde cualquier carpeta.
  - AUDITAR_DEV_EPS         -> audita devoluciones EPS (RIPS vs soportes).
  - AUTORIZACIONES_RIPS     -> saca que autorizacion trae cada factura.
  - CRUZAR_GLOSAS           -> cruza el Excel de la EPS con los XML
                               radicados y arma borradores de respuesta.
  - VERIFICAR_RADICACION    -> revisa el lote ANTES de radicarlo.
  - SEMAFORO_GLOSAS         -> plazos de respuesta en dias habiles.
  - UNIR_PDFS               -> une los PDF de cada carpeta en uno solo.
  - PDF_A_CMD / PDF_A_CMD_EN_CARPETA -> copia identica en .cmd (para
                               subir donde solo aceptan ese formato).
  - EXCEL_A_CMD / EXCEL_A_CSV -> lo mismo, para Excel.
  - TXT_A_EXCEL             -> cada .txt queda como .csv + Excel.
  - COMPRIMIR_ZIP / PARTIR_ZIP_30MB -> bajar peso / partir en pedazos.
  - REVISAR_XML             -> saca la info de contrato de los XML.
  - VIGILANTE_NOCTURNO      -> deja programada la tarea nocturna de
                               convertir los .txt nuevos solos.
  - INFORME_GERENCIA        -> informe de gestion para gerencia.

REGLA: casi todos se usan poniendo el archivo/carpeta a trabajar junto
al .cmd (o soltando la carpeta encima del icono) y dando doble clic.
"@

# ---------------------------------------------------------------------
# 11) MOTOR DE GLOSAS - SERVIDOR WEB
# ---------------------------------------------------------------------
$c = Join-Path $Destino "11. MOTOR DE GLOSAS - SERVIDOR WEB"
Asegurar-Carpeta $c
Nuevo-Atajo (Join-Path $c "ESTADO DEL MOTOR (doble clic).lnk") (Join-Path $Tools "ESTADO_MOTOR.cmd") "" "Esta bien la pagina? doble clic y listo"
Nuevo-Atajo (Join-Path $c "REINICIAR MOTOR (doble clic).lnk") (Join-Path $Tools "REINICIAR_MOTOR.cmd") "" "Apaga todo y prende un motor limpio"
Nuevo-Atajo (Join-Path $c "Montar servidor (doble clic).lnk") (Join-Path $Tools "MONTAR_SERVIDOR_MOTOR_GLOSAS.cmd")
Nuevo-Atajo (Join-Path $c "Servidor motor local (doble clic).lnk") (Join-Path $Tools "servidor_motor_local.cmd")
Nuevo-Atajo (Join-Path $c "Tunel motor local (doble clic).lnk") (Join-Path $Tools "tunel_motor_local.cmd")
Nuevo-Atajo (Join-Path $c "Copiar backup motor (doble clic).lnk") (Join-Path $Tools "copiar_backup_motor_glosas.cmd")
Guardar-Texto (Join-Path $c "LEEME.txt") @"
MOTOR DE GLOSAS - SERVIDOR WEB (control de la pagina)
=========================================================
Los archivos de verdad estan en: $Tools

CUANDO VENIR A ESTA CARPETA
  - La pagina del Motor de Glosas no responde, va lenta, o quieres
    saber quien la esta atendiendo por internet en este momento.
  - Hay que reiniciarla despues de cambiar una clave (.env).

COMO EMPEZAR
  1. Doble clic en "ESTADO DEL MOTOR" -> te dice en una pantalla si
     esta bien, con que clave de IA, si el tunel publica, etc.
  2. Si algo esta mal: doble clic en "REINICIAR MOTOR" -> apaga todo lo
     que haya quedado prendido y levanta un solo motor limpio.

Los demas accesos son para montar o probar el motor en un equipo nuevo
(Montar servidor, Servidor motor local, Tunel motor local) o para sacar
una copia de respaldo (Copiar backup motor). Uso poco frecuente, casi
siempre en coordinacion con quien administra el servidor.

Recordatorio (de la bitacora): en el servidor de la nube el repositorio
vive en /opt/motor-glosas y corre en Docker, no como servicio de
Windows - eso se administra por otra via, no con estos .cmd.
"@

# ---------------------------------------------------------------------
# 12) DOCUMENTACION Y BITACORA
# ---------------------------------------------------------------------
$c = Join-Path $Destino "12. DOCUMENTACION Y BITACORA"
Asegurar-Carpeta $c
Atajo-Doc (Join-Path $c "BITACORA (todo lo que se ha hecho).lnk") (Join-Path $RepoRoot "BITACORA.md") "Memoria completa de todas las sesiones de trabajo"
Atajo-Doc (Join-Path $c "Mapa de Capacidades (que sabe hacer el sistema).lnk") (Join-Path $Docs "MAPA_CAPACIDADES.md") "Vista de negocio: que sabe hacer SINAC OS, por familia"
Nuevo-Atajo (Join-Path $c "Carpeta docs (todas las guias).lnk") $Docs "" "Todas las guias del proyecto"
Guardar-Texto (Join-Path $c "LEEME.txt") @"
DOCUMENTACION Y BITACORA
===========================
CUANDO VENIR A ESTA CARPETA
  - Quieres saber que se hizo, cuando, y que quedo pendiente: abre
    "BITACORA" (arriba). Esta escrita en español sencillo, sin
    tecnicismos, pensada para el area de Cartera/Auditoria.
  - Quieres una vista general de todo lo que el sistema sabe hacer
    (por tema, no archivo por archivo): abre "Mapa de Capacidades".
  - Necesitas la guia de un frente puntual (COOSALUD, SIMED, SIIFA,
    ADRES, Pre-auditoria, etc.): esas guias ya tienen su propio acceso
    directo dentro de la carpeta de ese frente (1 a 9). Aqui esta la
    carpeta docs completa por si hace falta buscar otra.
"@

# ---------------------------------------------------------------------
# Indice maestro (raiz de D:\TRABAJOS BOTS)
# ---------------------------------------------------------------------
Guardar-Texto (Join-Path $Destino "0. LEEME PRIMERO - INDICE.txt") @"
MOTOR GLOSAS HUS - INDICE DE TRABAJOS Y BOTS
================================================
Actualizado por ultima vez: se regenera cada vez que se corre
ORGANIZAR_TRABAJOS_BOTS.cmd (carpeta tools\ del repositorio).

SI TE PIDEN...                                    -> VE A LA CARPETA...
--------------------------------------------------------------------------
Responder/subir glosas en COOSALUD                -> 1. COOSALUD
Glosas o notas credito del Dispensario en SIMED    -> 2. SIMED - DISPENSARIO MEDICO
Expediente/acta de conciliacion del Dispensario    -> 2. SIMED - DISPENSARIO MEDICO
Cargar un tramite en Dinamica Gerencial (DGH)      -> 3. DINAMICA GERENCIAL (DGH)
Bajar/responder seguimientos en SIIFA              -> 4. SIIFA (Ministerio de Salud)
Validar FURIPS / informe de baja de cartera        -> 5. ADRES - FURIPS
Informe de devoluciones XML DIAN (NUEVA EPS)       -> 5. ADRES - FURIPS
Paquete de glosas ADRES (ej. "31068") / detallados -> 6. GLOSAS ADRES Y DETALLADOS
Radicar/devolver facturas por soportes (SINAC)     -> 7. PRE-AUDITORIA SINAC (radicacion)
Cualquier cosa del dia a dia de Cartera            -> 8. SUITE CARTERA HUS
Herramientas PDF / correos de pagos / unir Exceles -> 8. SUITE CARTERA HUS (botones dentro)
Mutual Ser, FOMAG, SAVIA, EMSSANAR o Famisanar     -> 9. OTRAS EPS
Unir/dividir PDF, Excel<->CSV, ZIP, buscar factura -> 10. HERRAMIENTAS GENERALES
La pagina web no responde o hay que reiniciarla    -> 11. MOTOR DE GLOSAS - SERVIDOR WEB
Que se ha hecho / que falta / guias completas      -> 12. DOCUMENTACION Y BITACORA

CADA CARPETA TIENE
  - Accesos directos (doble clic) a los bots que ya lo permiten.
  - Un archivo LEEME.txt con: cuando venir aqui, que bot usar, y si el
    bot no tiene doble clic, el COMANDO listo para copiar y pegar en
    PowerShell (solo hay que cambiar lo que va entre < >).

REGLAS QUE SIEMPRE APLICAN (sin importar la carpeta)
  - Antes de un cargue masivo con un robot: SIEMPRE un piloto de 1
    factura primero (--solo <factura>).
  - Las claves de los portales NUNCA se escriben en un archivo: se
    ponen como variable de PowerShell antes de correr el bot (ejemplo
    en el LEEME de cada carpeta) o, en la Suite Cartera, en el archivo
    local de credenciales que no se sube al repositorio.
  - Si un cargue se corta (luz, portal caido), no se pierde nada: se
    relanza con --saltar-csv <reporte anterior> y un --reporte nuevo.

ESTA CARPETA SE PUEDE VOLVER A ARMAR CUANDO QUIERAS
  Vuelve a dar doble clic en tools\ORGANIZAR_TRABAJOS_BOTS.cmd (dentro
  del repositorio) cada vez que se agregue un bot nuevo o cambie algo:
  no borra nada que hayas puesto a mano dentro de "D:\TRABAJOS BOTS",
  solo actualiza los accesos directos y los LEEME.txt.
"@

Write-Host ""
Write-Host "  Listo. Carpetas creadas/actualizadas en: $Destino" -ForegroundColor Green
Write-Host "  Empieza por: 0. LEEME PRIMERO - INDICE.txt" -ForegroundColor Green
Write-Host ""
