from datetime import datetime

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Usuario(Base):
    __tablename__ = "usuarios"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(120), nullable=False)
    email = Column(String(160), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    rol = Column(String(40), default="ADMIN", nullable=False)
    activo = Column(Integer, default=1, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)


class Comercio(Base):
    __tablename__ = "comercios"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(160), nullable=False, index=True)
    direccion = Column(String(240))
    telefono = Column(String(40))
    categoria = Column(String(60))
    activo = Column(Integer, default=1, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)


class Cliente(Base):
    __tablename__ = "clientes"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(160), nullable=False, index=True)
    telefono = Column(String(40), nullable=False, index=True)
    direccion = Column(String(240))
    notas = Column(Text)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)


class Repartidor(Base):
    __tablename__ = "repartidores"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(120), nullable=False, index=True)
    telefono = Column(String(40), nullable=False)
    documento = Column(String(40))
    vehiculo = Column(String(40), default="MOTO", nullable=False)
    placa = Column(String(20))
    disponible = Column(Integer, default=1, nullable=False)
    activo = Column(Integer, default=1, nullable=False)
    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)


class Zona(Base):
    __tablename__ = "zonas"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(120), unique=True, nullable=False)
    tarifa_base = Column(Float, default=0.0, nullable=False)
    descripcion = Column(String(240))
    activa = Column(Integer, default=1, nullable=False)


ESTADOS_PEDIDO = (
    "PENDIENTE",
    "ASIGNADO",
    "EN_RUTA",
    "ENTREGADO",
    "CANCELADO",
)


class Pedido(Base):
    __tablename__ = "pedidos"
    id = Column(Integer, primary_key=True)
    codigo = Column(String(20), unique=True, nullable=False, index=True)

    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False)
    comercio_id = Column(Integer, ForeignKey("comercios.id"))
    repartidor_id = Column(Integer, ForeignKey("repartidores.id"))
    zona_id = Column(Integer, ForeignKey("zonas.id"))

    descripcion = Column(Text, nullable=False)
    direccion_entrega = Column(String(240), nullable=False)
    telefono_entrega = Column(String(40))
    notas = Column(Text)

    valor_productos = Column(Float, default=0.0, nullable=False)
    costo_envio = Column(Float, default=0.0, nullable=False)
    metodo_pago = Column(String(40), default="EFECTIVO", nullable=False)

    estado = Column(String(20), default="PENDIENTE", nullable=False, index=True)

    creado_en = Column(DateTime, default=datetime.utcnow, nullable=False)
    asignado_en = Column(DateTime)
    en_ruta_en = Column(DateTime)
    entregado_en = Column(DateTime)
    cancelado_en = Column(DateTime)
    motivo_cancelacion = Column(String(240))

    cliente = relationship("Cliente", lazy="joined")
    comercio = relationship("Comercio", lazy="joined")
    repartidor = relationship("Repartidor", lazy="joined")
    zona = relationship("Zona", lazy="joined")

    @property
    def total(self) -> float:
        return float(self.valor_productos or 0) + float(self.costo_envio or 0)
