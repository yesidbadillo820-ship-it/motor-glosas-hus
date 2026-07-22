# Especificaciones de imprenta — Hijos del Firmamento (Libro I)

## Archivos

| Archivo | Contenido |
|---|---|
| `IMPRENTA_interior_sangrado_3mm.pdf` | Interior completo: 178 páginas a color, con sangrado |
| `IMPRENTA_caratula_extendida_lomo10mm.pdf` | Carátula extendida: contraportada + lomo + portada, con sangrado |

## Interior

- **Tamaño final (corte)**: 14,0 × 23,4 cm (396,75 × 663 pt)
- **Tamaño del archivo**: 14,6 × 24,0 cm — incluye **sangrado de 3 mm** por los cuatro lados
- **Páginas**: 178, **a color** (fondo pergamino en todas las páginas)
- El TrimBox del PDF marca la línea de corte; las fuentes van incrustadas
- Papel sugerido: bond 90 g o esmaltado mate 115 g
- Encuadernación: rústica pegada (hot-melt)

## Carátula

- **Tamaño del archivo**: 29,6 × 24,0 cm (contraportada 14,0 + lomo 1,0 + portada 14,0,
  más 3 mm de sangrado por los cuatro lados)
- **Lomo: 10 mm**, calculado para 178 páginas en bond 90 g (~0,11 mm/hoja).
  ⚠️ **Confirmar el calibre del papel con la imprenta**: si el lomo real difiere,
  regenerar con `herramientas/preparar_imprenta.py` pasando el lomo en mm como
  último argumento.
- Material sugerido: propalcote 250–300 g, **plastificado mate**
- La contraportada reserva espacio libre abajo a la derecha para código de barras/ISBN

## Regenerar (si cambia el lomo o el contenido)

```bash
python3 edicion-coleccionista/herramientas/preparar_imprenta.py \
  <interior_sin_fondo.pdf> \
  edicion-coleccionista/fuente/diseno/portada.pdf \
  edicion-coleccionista/fuente/diseno/formato_de_fondo.pdf \
  IMPRENTA_interior_sangrado_3mm.pdf IMPRENTA_caratula_extendida.pdf <lomo_mm>
```
