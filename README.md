# Motor de Glosas HUS

**Sistema de defensa automatizada de glosas médicas para la ESE Hospital Universitario de Santander**

![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)

## Descripción

El Motor de Glosas HUS es una aplicación web que automatiza la generación de respuestas técnico-jurídicas a glosas de facturación hospitalaria, conforme a la normativa colombiana de salud.

### Características Principales

- **Análisis automático de glosas** mediante IA (Groq/Anthropic) con retry inteligente
- **Detección de glosas extemporáneas** (20 días hábiles - Art. 56 Ley 1438/2011)
- **Plantillas especializadas** por tipo de glosa (tarifa, soportes, autorización, cobertura, pertinencia)
- **Cálculo de días hábiles** con calendario de festivos colombianos (2025-2028)
- **Gestión de contratos EPS** con tarifas específicas
- **Workflow completo** de estados (RADICADA → RESPONDIDA → RATIFICADA → CONCILIADA/LEVANTADA)
- **Exportación Excel** con formato institucional HUS
- **Alertas por correo** de glosas próximas a vencer
- **Marco normativo completo** con 17 referencias (Leyes, Decretos, Resoluciones, Sentencias)
- **Score dinámico** basado en calidad del argumento generado por IA
- **Glosas ADRES**: el coordinador carga el `ReporteGlosasReclamPAQUETE` una
  vez y el gestor **solo escribe el número de factura** para que la pantalla le
  traiga las glosas clasificadas, el centro de costos, la sugerencia de
  respuesta con su motivo, el detallado cruzado y el texto consolidado
  ([docs/GLOSAS_ADRES_WEB.md](docs/GLOSAS_ADRES_WEB.md))

## Módulo aparte: preparación ICFES Saber 11

La carpeta `icfes/` contiene un sistema **independiente** de preparación para el
examen Saber 11 del ICFES: banco de preguntas con explicaciones, plan de estudio
por fases, repaso espaciado, simulacros cronometrados y cuaderno de errores.

No depende de `app/` ni de librerías externas (solo Python 3.11 estándar).

En Windows, doble clic en `tools\ICFES.cmd` (menú) o `tools\ICFES_APP.cmd`
(genera la app web). Desde la consola, **hay que estar dentro de la carpeta del
repositorio** o Python responde `No module named icfes`:

```bash
cd C:\temp-notas                                   # la carpeta del repositorio
python -m icfes iniciar --examen 2027-08-08 --meta 400 --horas 12
python -m icfes hoy
python -m icfes exportar-web --salida ICFES.html   # app que funciona sin internet
```

Guía completa: [`docs/GUIA_SISTEMA_ICFES.md`](docs/GUIA_SISTEMA_ICFES.md).

## Módulo aparte: curso de noruego

La carpeta `noruego/` contiene una aplicación web para aprender **noruego
(bokmål)** desde cero, pensada para hispanohablantes y para usarse desde el
celular: se instala como aplicación (PWA) y funciona sin internet.

Independiente de `app/` y sin librerías externas (solo Python 3.11 estándar).

En Windows, doble clic en `tools\NORUEGO.cmd`. Desde la consola:

```bash
cd C:\temp-notas
python -m noruego revisar          # valida el contenido del curso
python -m noruego exportar         # genera la app en static/noruego/
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
# En el celular, mismo wifi: http://LA-IP:8000/static/noruego/index.html
```

Guía completa: [`docs/GUIA_CURSO_NORUEGO.md`](docs/GUIA_CURSO_NORUEGO.md).

## Requisitos

- Python 3.10+
- API Key de Groq (gratuita) o Anthropic (opcional)
- SQLite (desarrollo) o PostgreSQL (producción)

## Instalación

```bash
# Clonar repositorio
git clone https://github.com/usuario/motor-glosas-hus.git
cd motor-glosas-hus

# Crear entorno virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Instalar dependencias
pip install -r requirements.txt

# Configurar variables de entorno
cp .env.example .env
# Editar .env con tus API keys

# Ejecutar aplicación
uvicorn app.main:app --reload
```

## Configuración

Editar el archivo `.env`:

```env
# API Keys (requerido al menos una)
GROQ_API_KEY=tu_clave_groq_aqui

# Seguridad
SECRET_KEY=genera_una_clave_segura_con_python
ADMIN_PASSWORD=tu_password_admin

# Base de datos
DATABASE_URL=sqlite:///./glosas.db

# CORS (orígenes permitidos)
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

## Uso

### Interfaz Web

1. Abrir `http://localhost:8000` en el navegador
2. Ingresar datos de la glosa:
   - Nombre de la EPS
   - Fechas de radicación y recepción
   - Texto de la glosa
   - Número de factura y radicado (opcional)
3. Adjuntar PDF con soportes (opcional)
4. Hacer clic en "Analizar Glosa"
5. Copiar la respuesta generada o exportarla

### API REST

#### Analizar Glosa

```bash
curl -X POST http://localhost:8000/api/glosas/analizar \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "eps": "EPS SANITAS",
    "fecha_radicacion": "2026-03-01",
    "fecha_recepcion": "2026-04-01",
    "numero_factura": "FAC-12345",
    "numero_radicado": "RAD-67890",
    "tabla_excel": "TA0201 $1,500,000 Diferencia en consulta"
  }'
```

**Respuesta:**

```json
{
  "tipo": "RESPUESTA RE9502",
  "resumen": "DEFENSA TÉCNICA: EXTEMPORÁNEA",
  "codigo_glosa": "TA0201",
  "valor_objetado": "$ 1,500,000",
  "mensaje_tiempo": "EXTEMPORÁNEA (25 DÍAS HÁBILES - LÍMITE: 20)",
  "score": 99.0,
  "modelo_ia": "groq/llama-3.3"
}
```

#### Listar Contratos

```bash
curl http://localhost:8000/api/contratos \
  -H "Authorization: Bearer $TOKEN"
```

#### Listar Plantillas

```bash
curl http://localhost:8000/api/plantillas \
  -H "Authorization: Bearer $TOKEN"
```

## Tipos de Glosas Soportadas

| Código | Tipo | Descripción |
|--------|------|-------------|
| TA | Tarifaria | Diferencia en valores facturados |
| SO | Soportes | Documentación incompleta |
| AU | Autorización | Falta de autorización previa |
| CO | Cobertura | Servicio no cubierto por el PBS |
| PE | Pertinencia | Cuestionamiento médico |
| FA | Facturación | Errores formales |
| IN | Insumos | Materiales no reconocidos |
| ME | Medicamentos | Fármacos no cubiertos |

## Normativa Aplicable

- **Ley 100 de 1993** - Sistema de Seguridad Social Integral
- **Ley 1438 de 2011** - Art. 56: Plazo de 20 días hábiles para glosas
- **Ley 1751 de 2015** - Derecho fundamental a la salud
- **Decreto 4747 de 2007** - Glosas y devoluciones
- **Resolución 5269 de 2017** - Plan de Beneficios en Salud
- **Resolución 054 de 2026** - Tarifas SOAT plenas

## Testing

```bash
# Instalar pytest si no está
pip install pytest

# Ejecutar todos los tests
pytest

# Ejecutar con coverage
pytest --cov=app --cov-report=html

# Ejecutar tests específicos
pytest tests/test_services/
```

## Estructura del Proyecto

```
motor-glosas-hus/
├── app/
│   ├── api/
│   │   ├── deps.py           # Dependencias FastAPI
│   │   └── routers/
│   │       ├── auth_router.py
│   │       ├── glosas.py
│   │       ├── glosas_adres.py   # Paquete de glosas del ADRES
│   │       ├── contratos.py
│   │       ├── plantillas.py
│   │       └── analytics.py
│   ├── core/
│   │   └── config.py         # Configuración
│   ├── models/
│   │   ├── db.py             # Modelos SQLAlchemy
│   │   └── schemas.py        # Schemas Pydantic
│   ├── repositories/         # Acceso a datos
│   ├── services/             # Lógica de negocio
│   │   ├── glosa_service.py
│   │   ├── pdf_service.py
│   │   ├── preauditoria_adres.py  # Pre-auditoría del paquete ADRES
│   │   └── glosa_ia_prompts.py
│   └── main.py               # Punto de entrada
├── tools/                    # Bots de escritorio (detallados, PDF, macro)
├── tests/                    # Suite de pruebas
├── static/                   # Frontend SPA
├── requirements.txt
├── pytest.ini
└── README.md
```

## Documentación API

La documentación interactiva está disponible en:

- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Despliegue

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Producción con Gunicorn

```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
```

## Licencia

MIT License - ESE Hospital Universitario de Santander

## Contacto

- **Cartera**: cartera@hus.gov.co
- **Glosas**: glosasydevoluciones@hus.gov.co
- **Ventanilla Única**: Cra 33 No. 28-126, Bucaramanga, Santander
