import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- MODELOS DE LA BASE DE DATOS ---

class InsumoModel(Base):
    __tablename__ = "insumos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    unidad_medida = Column(String, nullable=False)
    cantidad_stock = Column(Float, default=0.0)
    costo_unitario = Column(Float, default=0.0)

class ProductoModel(Base):
    __tablename__ = "productos"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String, nullable=False)
    precio_venta = Column(Float, nullable=False)

    recetas = relationship("RecetaModel", back_populates="producto", cascade="all, delete-orphan")

class RecetaModel(Base):
    __tablename__ = "recetas"

    id = Column(Integer, primary_key=True, index=True)
    producto_id = Column(Integer, ForeignKey("productos.id", ondelete="CASCADE"), nullable=False)
    insumo_id = Column(Integer, ForeignKey("insumos.id", ondelete="CASCADE"), nullable=False)
    cantidad_utilizada = Column(Float, nullable=False)

    producto = relationship("ProductoModel", back_populates="recetas")
    insumo = relationship("InsumoModel")

class VentaModel(Base):
    __tablename__ = "ventas"

    id = Column(Integer, primary_key=True, index=True)
    fecha = Column(DateTime, default=datetime.utcnow)
    total = Column(Float, default=0.0)
    metodo_pago = Column(String, default="Efectivo")

    detalles = relationship("VentaDetalleModel", back_populates="venta", cascade="all, delete-orphan")

class VentaDetalleModel(Base):
    __tablename__ = "detalle_ventas"

    id = Column(Integer, primary_key=True, index=True)
    venta_id = Column(Integer, ForeignKey("ventas.id", ondelete="CASCADE"), nullable=False)
    producto_id = Column(Integer, ForeignKey("productos.id"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario = Column(Float, nullable=False)
    subtotal = Column(Float, nullable=False)

    venta = relationship("VentaModel", back_populates="detalles")
    producto = relationship("ProductoModel")

class GastoModel(Base):
    __tablename__ = "gastos"

    id = Column(Integer, primary_key=True, index=True)
    descripcion = Column(String, nullable=False)
    monto = Column(Float, nullable=False)
    categoria = Column(String, default="General")
    fecha = Column(DateTime, default=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE ventas ADD COLUMN IF NOT EXISTS metodo_pago VARCHAR DEFAULT 'Efectivo';"))
            conn.commit()
        except Exception as e:
            print("Verificación de columna metodo_pago:", e)