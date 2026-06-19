# Documentación API - Motor Glosas HUS

## Autenticación

### Login
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "admin",
  "password": "tu_password"
}
```

**Respuesta:**
```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

---

## Análisis de Glosas

### Analizar Glosa
```http
POST /analizar
Authorization: Bearer $TOKEN
Content-Type: multipart/form-data

eps=EPS SANITAS
etapa=RESPUESTA A GLOSA
fecha_radicacion=2026-03-01
fecha_recepcion=2026-03-25
tabla_excel=TA0201 $1,500,000 Diferencia en consulta
numero_factura=FAC-12345
numero_radicado=RAD-67890
```

**Respuesta:**
```json
{
  "tipo": "RESPUESTA RE9502",
  "resumen": "DEFENSA TÉCNICA: EXTEMPORÁNEA",
  "codigo_glosa": "TA0201",
  "valor_objetado": "$ 1,500,000",
  "mensaje_tiempo": "EXTEMPORÁNEA (25 DÍAS HÁBILES - LÍMITE: 20)",
  "color_tiempo": "bg-red-600",
  "score": 99.0,
  "dias_restantes": 0,
  "paciente": "N/A",
  "dictamen": "<table>...</table>",
  "modelo_ia": "groq/llama-3.3"
}
```

---

## Historial

### Listar Historial
```http
GET /api/glosas/historial?limit=50&eps=EPS%20SANITAS
Authorization: Bearer $TOKEN
```

**Respuesta:**
```json
[
  {
    "id": 1,
    "eps": "EPS SANITAS",
    "paciente": "Juan Pérez",
    "codigo_glosa": "TA0201",
    "valor_objetado": "$ 1,500,000",
    "estado": "RESPONDIDA",
    "creado_en": "2026-04-08T10:30:00"
  }
]
```

### Historial Paginado
```http
GET /api/glosas/historial-paginado?page=1&per_page=20&eps=EPS%20SURA&estado=RESPONDIDA
Authorization: Bearer $TOKEN
```

**Respuesta:**
```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "per_page": 20,
  "pages": 8
}
```

---

## Alertas

### Obtener Alertas
```http
GET /api/glosas/alertas?dias=5
Authorization: Bearer $TOKEN
```

**Respuesta:**
```json
[
  {
    "id": 45,
    "eps": "EPS NUEVA EPS",
    "paciente": "María García",
    "codigo_glosa": "SO0101",
    "valor_objetado": "$ 500,000",
    "dias_restantes": 3,
    "estado": "RESPONDIDA"
  }
]
```

---

## Contratos

### Listar Todos
```http
GET /api/contratos
Authorization: Bearer $TOKEN
```

### Obtener por EPS
```http
GET /api/contratos/EPS%20SANITAS
Authorization: Bearer $TOKEN
```

---

## Plantillas

### Listar Plantillas
```http
GET /api/plantillas
Authorization: Bearer $TOKEN
```

### Obtener por Código
```http
GET /api/plantillas/TA0201
Authorization: Bearer $TOKEN
```

---

## Métricas

### Dashboard Metrics
```http
GET /api/glosas/metrics
Authorization: Bearer $TOKEN
```

**Respuesta:**
```json
{
  "total": 1250,
  "respondidas": 890,
  "aceptadas": 150,
  "levantadas": 50,
  "ratio_exito": 71.2,
  "valor_total_obj": 850000000,
  "valor_recuperado": 620000000,
  "por_eps": {...}
}
```

---

## Códigos de Respuesta

| Código | Significado | Score Base |
|--------|-------------|------------|
| RE9502 | Glosa Extemporánea - Improcedente | 99% |
| RE9901 | Glosa Ratificada - No aceptada | 92% |
| RE9602 | Glosa Injustificada | 85% |
| RE9601 | Devolución Injustificada | 85% |

---

## Tipos de Glosa

| Prefijo | Tipo | Estrategia |
|---------|------|------------|
| TA | Tarifaria | Contrato y tarifas pactadas |
| SO | Soportes | Historia clínica como prueba |
| AU | Autorización | Urgencias (Art. 168 Ley 100) |
| CO | Cobertura | Plan de Beneficios en Salud |
| PE | Pertinencia | Autonomía médica |
| FA | Facturación | Errores formales subsanables |
| IN | Insumos | Costos inherentes al acto médico |
| ME | Medicamentos | Plan de Beneficios |
