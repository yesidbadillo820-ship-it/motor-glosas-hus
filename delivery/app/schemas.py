from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    nombre: str
    rol: str
    email: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UsuarioOut(BaseModel):
    id: int
    nombre: str
    email: EmailStr
    rol: str
    activo: int
    creado_en: datetime

    class Config:
        from_attributes = True


class ComercioIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    direccion: Optional[str] = None
    telefono: Optional[str] = None
    categoria: Optional[str] = None
    activo: int = 1


class ComercioOut(ComercioIn):
    id: int
    creado_en: datetime

    class Config:
        from_attributes = True


class ClienteIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=160)
    telefono: str = Field(min_length=1, max_length=40)
    direccion: Optional[str] = None
    notas: Optional[str] = None


class ClienteOut(ClienteIn):
    id: int
    creado_en: datetime

    class Config:
        from_attributes = True


class RepartidorIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    telefono: str = Field(min_length=1, max_length=40)
    documento: Optional[str] = None
    vehiculo: str = "MOTO"
    placa: Optional[str] = None
    disponible: int = 1
    activo: int = 1


class RepartidorOut(RepartidorIn):
    id: int
    creado_en: datetime

    class Config:
        from_attributes = True


class ZonaIn(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    tarifa_base: float = 0.0
    descripcion: Optional[str] = None
    activa: int = 1


class ZonaOut(ZonaIn):
    id: int

    class Config:
        from_attributes = True


class PedidoIn(BaseModel):
    cliente_id: int
    comercio_id: Optional[int] = None
    zona_id: Optional[int] = None
    descripcion: str = Field(min_length=1)
    direccion_entrega: str = Field(min_length=1, max_length=240)
    telefono_entrega: Optional[str] = None
    notas: Optional[str] = None
    valor_productos: float = 0.0
    costo_envio: float = 0.0
    metodo_pago: str = "EFECTIVO"


class PedidoUpdate(BaseModel):
    descripcion: Optional[str] = None
    direccion_entrega: Optional[str] = None
    telefono_entrega: Optional[str] = None
    notas: Optional[str] = None
    valor_productos: Optional[float] = None
    costo_envio: Optional[float] = None
    metodo_pago: Optional[str] = None
    zona_id: Optional[int] = None
    comercio_id: Optional[int] = None


class AsignarRepartidorIn(BaseModel):
    repartidor_id: int


class CambiarEstadoIn(BaseModel):
    estado: str
    motivo: Optional[str] = None


class PedidoOut(BaseModel):
    id: int
    codigo: str
    cliente_id: int
    comercio_id: Optional[int] = None
    repartidor_id: Optional[int] = None
    zona_id: Optional[int] = None
    descripcion: str
    direccion_entrega: str
    telefono_entrega: Optional[str] = None
    notas: Optional[str] = None
    valor_productos: float
    costo_envio: float
    total: float
    metodo_pago: str
    estado: str
    creado_en: datetime
    asignado_en: Optional[datetime] = None
    en_ruta_en: Optional[datetime] = None
    entregado_en: Optional[datetime] = None
    cancelado_en: Optional[datetime] = None
    motivo_cancelacion: Optional[str] = None

    cliente_nombre: Optional[str] = None
    cliente_telefono: Optional[str] = None
    comercio_nombre: Optional[str] = None
    repartidor_nombre: Optional[str] = None
    zona_nombre: Optional[str] = None

    class Config:
        from_attributes = True


class DashboardMetricas(BaseModel):
    pedidos_hoy: int
    pendientes: int
    asignados: int
    en_ruta: int
    entregados_hoy: int
    cancelados_hoy: int
    repartidores_disponibles: int
    repartidores_total: int
    ingresos_hoy: float
    ticket_promedio_hoy: float
    pedidos_por_estado: dict
    pedidos_por_zona: list
    top_repartidores_hoy: list
