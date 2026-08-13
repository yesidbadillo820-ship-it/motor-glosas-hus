# Centro Documental

**Qué es.** Dentro de cada **Expediente** (menú → Expediente → buscar la
glosa) aparece la sección **📁 Centro Documental**: todos los documentos de
esa glosa, organizados solos, cada uno con su forma de obtenerlo. Sin
búsquedas manuales.

## Qué agrupa

| Grupo | Documentos | Cómo se obtiene |
|---|---|---|
| Respuesta del hospital | PDF radicable del dictamen · dictamen en texto · historial de versiones | Botón **Abrir** (descarga con la sesión) |
| Conciliación | El acta imprimible de cada mesa de esa glosa, con su resultado | Botón **Abrir** |
| Evidencia legal | El paquete de evidencia (dictamen con huella digital, versiones, auditoría y línea de tiempo) para jurídica o disputas | Botón **Abrir** |
| Soportes de la factura | HEV, RIPS, FEV y demás archivos que el indexador encontró en el share | **Ruta** del share (son historia clínica: se abren desde el equipo del hospital, no por la web) |

## Fuente única

La carpeta se arma leyendo lo que ya existe — cero tablas nuevas, cero
copias. La misma carpeta la devuelven:

- la pantalla **Expediente**,
- la API: `GET /glosas/{id}/documentos` (o dentro de `GET /glosas/{id}/expediente`),
- el **chat IA**: «¿qué documentos hay de la factura HUS…?».

Agregar una fuente documental nueva (por ejemplo, correos radicados) es
agregar una función en `app/services/centro_documental.py` — aparece en
pantalla, API y chat a la vez.
