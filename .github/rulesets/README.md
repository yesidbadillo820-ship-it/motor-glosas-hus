# Proteger la rama `motor-glosas`

`motor-glosas` es la rama de la que el PC de cartera baja el código cada
5 minutos. Lo que entre ahí llega al hospital. Hoy se puede fusionar aunque
las pruebas estén corriendo o hayan fallado — de hecho ya pasó: la PR #649
se fusionó 38 segundos después de abrirse, con `pytest` todavía en marcha.

Este archivo deja la protección lista para aplicarla en un clic. **Esa parte
la tiene que hacer usted**: cambiar la configuración del repositorio necesita
permisos de dueño y Claude no los tiene.

## Cómo se aplica (2 minutos, una sola vez)

1. Abra
   <https://github.com/yesidbadillo820-ship-it/motor-glosas-hus/settings/rules>
2. **New ruleset → Import a ruleset**
3. Suba el archivo `motor-glosas-protegida.json` de esta carpeta
4. **Create**
5. **IMPORTANTE — este paso no lo hace la importación.** Abra la regla
   «Require status checks to pass»: la lista de chequeos llega **vacía**.
   Hay que agregar los cuatro a mano, buscándolos por su nombre exacto:
   `Lint (ruff)`, `Tests (pytest)`, `Security scan (pip-audit)` y `CI OK`.
   Sin esto la regla queda puesta pero no exige nada — que es peor que no
   tenerla, porque uno cree que está protegido y no lo está.
   (Ya pasó el 08-09-2026, al aplicarla por primera vez.)

**Aplicada el 08-09-2026.** Estas instrucciones quedan por si hay que
rehacerla o replicarla en otro repositorio.

## Qué queda exigido

| Regla | Qué impide |
|---|---|
| `Lint (ruff)` en verde | Que entre código sin formatear o con errores de sintaxis |
| `Tests (pytest)` en verde | Que entre un cambio con la suite rota |
| `Security scan (pip-audit)` en verde | Que entre una vulnerabilidad nueva |
| `CI OK` en verde | Que se olvide de exigir un paso nuevo el día que se agregue |
| Pull request obligatorio | Empujar directo a `motor-glosas` sin pasar por CI |
| Sin borrar la rama | Borrar por accidente la rama que corre en el hospital |
| Sin reescribir la historia | Un `--force` que se lleve por delante trabajo ya fusionado |

**No exige aprobación de otra persona** (`required_approving_review_count: 0`):
usted es el único que trabaja en este repositorio, y pedir un revisor
bloquearía todo. Lo que se exige es que el CI termine, que es lo que faltaba.

`strict_required_status_checks_policy: true` significa que la rama tiene que
estar al día con `motor-glosas` antes de fusionar. Sin eso, dos cambios que
cada uno pasa por separado pueden romper el motor al juntarse.

## Cómo comprobar que quedó puesta

Abra cualquier PR nueva: el botón verde de fusionar debe aparecer **gris**
hasta que los cuatro chequeos terminen.

## Si algún día hay que fusionar con el CI rojo

Es una decisión suya, no un descuido: en la página de la PR aparece
«Merge without waiting for requirements to be met», y solo lo ve el dueño
del repositorio. Queda registrado.
