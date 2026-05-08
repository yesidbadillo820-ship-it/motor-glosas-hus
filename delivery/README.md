# Panel de Domicilios — Centro de Operaciones

Aplicación independiente para administración de entregas y domicilios.
**Proyecto separado** del Motor de Glosas HUS — vive en su propia carpeta y no comparte código ni base de datos.

## Funcionalidades del MVP

- **Autenticación admin** con JWT.
- **Dashboard en vivo** con KPIs del día (pedidos por estado, ingresos, ticket promedio, top repartidores, pedidos por zona). Refresco automático cada 30 segundos.
- **Pedidos**: alta, edición, asignación de repartidor y avance de estado (`PENDIENTE → ASIGNADO → EN_RUTA → ENTREGADO`), cancelación con motivo, código autogenerado por día.
- **Repartidores**: alta/edición, vehículo, placa, toggle de disponibilidad.
- **Clientes**: directorio con búsqueda por nombre o teléfono.
- **Comercios / Restaurantes**: catálogo con categoría y dirección.
- **Zonas y tarifas**: tarifa base por zona, autocompletado al crear pedido.
- **API REST documentada** en `/docs` (Swagger).

## Arranque rápido

```bash
cd delivery
bash run.sh
```

La app queda en `http://localhost:8001`.
La API de la aplicación de domicilios usa el puerto **8001** para no chocar con el Motor de Glosas (8000).

### Credenciales por defecto

- **Correo**: `admin@delivery.app`
- **Contraseña**: `admin1234`

> Cambia `ADMIN_EMAIL` y `ADMIN_PASSWORD` en el `.env` antes de ir a producción.

## Estructura

```
delivery/
├── app/
│   ├── main.py            # FastAPI app + bootstrap + seed
│   ├── config.py          # Settings via pydantic-settings
│   ├── database.py        # SQLAlchemy engine
│   ├── models.py          # ORM (Pedido, Cliente, Repartidor, Comercio, Zona, Usuario)
│   ├── schemas.py         # Pydantic v2 schemas
│   ├── auth.py            # JWT + bcrypt
│   └── routers/
│       ├── auth.py
│       ├── pedidos.py
│       ├── repartidores.py
│       ├── clientes.py
│       ├── comercios.py
│       ├── zonas.py
│       └── dashboard.py
├── static/
│   ├── login.html
│   ├── index.html         # SPA
│   └── app.js
├── requirements.txt
├── .env.example
└── run.sh
```

## Endpoints principales

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/auth/login` | Inicia sesión, devuelve JWT |
| GET  | `/api/dashboard/metricas` | KPIs del día |
| GET / POST | `/api/pedidos` | Listar / crear pedidos |
| POST | `/api/pedidos/{id}/asignar` | Asigna repartidor |
| POST | `/api/pedidos/{id}/estado` | Cambia estado (con motivo si cancela) |
| GET / POST / PUT / DELETE | `/api/repartidores` | CRUD de repartidores |
| POST | `/api/repartidores/{id}/disponibilidad?disponible=true` | Toggle disponibilidad |
| GET / POST / PUT / DELETE | `/api/clientes` | CRUD de clientes |
| GET / POST / PUT / DELETE | `/api/comercios` | CRUD de comercios |
| GET / POST / PUT / DELETE | `/api/zonas` | CRUD de zonas y tarifas |

Documentación interactiva en `http://localhost:8001/docs`.

## Próximos pasos sugeridos

- App o vista para repartidores (tomar pedidos asignados, marcar en ruta/entregado).
- Vista pública para que el cliente consulte el estado de su pedido por código.
- Integración con WhatsApp / SMS para confirmar entrega.
- Mapa con ubicación en vivo del repartidor.
- Reportes históricos y exportación a Excel/CSV.
- Multi-tenant si vas a operar varios negocios desde el mismo panel.
