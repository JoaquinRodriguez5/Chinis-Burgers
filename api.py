from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
from database import init_db, get_db, InsumoModel, ProductoModel, RecetaModel, VentaModel, VentaDetalleModel, GastoModel

app = FastAPI(title="Chinis Burgers API")

# Habilitar CORS para permitir peticiones desde GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

init_db()

# Esquemas de entrada
class ItemVenta(BaseModel):
    producto_id: int
    cantidad: int

class VentaCreate(BaseModel):
    items: List[ItemVenta]

class InsumoCreate(BaseModel):
    nombre: str
    unidad_medida: str
    cantidad_stock: float
    costo_unitario: float
    stock_minimo: float = 0.0

# Endpoints
@app.get("/insumos")
def obtener_insumos(db: Session = Depends(get_db)):
    return db.query(InsumoModel).all()

@app.post("/insumos")
def crear_insumo(insumo: InsumoCreate, db: Session = Depends(get_db)):
    nuevo = InsumoModel(**insumo.dict())
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@app.get("/productos")
def obtener_productos(db: Session = Depends(get_db)):
    return db.query(ProductoModel).all()

@app.post("/ventas")
def registrar_venta(venta_in: VentaCreate, db: Session = Depends(get_db)):
    # 1. Verificar Stock
    for item in venta_in.items:
        recetas = db.query(RecetaModel).filter(RecetaModel.producto_id == item.producto_id).all()
        for r in recetas:
            insumo = db.query(InsumoModel).filter(InsumoModel.id == r.insumo_id).first()
            necesario = r.cantidad_utilizada * item.cantidad
            if insumo.cantidad_stock < necesario:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Stock insuficiente de '{insumo.nombre}'. Necesario: {necesario}, Disponible: {insumo.cantidad_stock}"
                )

    # 2. Registrar Venta y Descontar
    total_venta = 0.0
    detalles = []
    
    for item in venta_in.items:
        prod = db.query(ProductoModel).filter(ProductoModel.id == item.producto_id).first()
        subtotal = prod.precio_venta * item.cantidad
        total_venta += subtotal
        detalles.append((prod.id, item.cantidad, prod.precio_venta))

    nueva_venta = VentaModel(total=total_venta)
    db.add(nueva_venta)
    db.commit()
    db.refresh(nueva_venta)

    for prod_id, cant, precio in detalles:
        vd = VentaDetalleModel(venta_id=nueva_venta.id, producto_id=prod_id, cantidad=cant, precio_unitario=precio)
        db.add(vd)
        
        # Descuento de stock
        recetas = db.query(RecetaModel).filter(RecetaModel.producto_id == prod_id).all()
        for r in recetas:
            insumo = db.query(InsumoModel).filter(InsumoModel.id == r.insumo_id).first()
            insumo.cantidad_stock -= (r.cantidad_utilizada * cant)

    db.commit()
    return {"status": "ok", "venta_id": nueva_venta.id, "total": total_venta}

from sqlalchemy import func
from datetime import datetime, time

@app.get("/stats/dashboard")
def obtener_dashboard_stats(db: Session = Depends(get_db)):
    # 1. Balance Diario (Hoy)
    hoy_inicio = datetime.combine(datetime.utcnow().date(), time.min)
    hoy_fin = datetime.combine(datetime.utcnow().date(), time.max)
    
    ventas_hoy = db.query(func.coalesce(func.sum(VentaModel.total), 0.0))\
        .filter(VentaModel.fecha >= hoy_inicio, VentaModel.fecha <= hoy_fin).scalar()
        
    cant_ventas_hoy = db.query(func.count(VentaModel.id))\
        .filter(VentaModel.fecha >= hoy_inicio, VentaModel.fecha <= hoy_fin).scalar()

    # 2. Productos Más Vendidos (Top 5)
    top_productos = db.query(
        ProductoModel.nombre,
        func.sum(VentaDetalleModel.cantidad).label("total_vendido")
    ).join(VentaDetalleModel, ProductoModel.id == VentaDetalleModel.producto_id)\
     .group_by(ProductoModel.nombre)\
     .order_by(func.sum(VentaDetalleModel.cantidad).desc())\
     .limit(5).all()

    # 3. Categoría más vendida
    top_categorias = db.query(
        ProductoModel.categoria,
        func.sum(VentaDetalleModel.cantidad).label("total_vendido")
    ).join(VentaDetalleModel, ProductoModel.id == VentaDetalleModel.producto_id)\
     .group_by(ProductoModel.categoria)\
     .order_by(func.sum(VentaDetalleModel.cantidad).desc()).all()

    return {
        "ventas_hoy_monto": ventas_hoy,
        "ventas_hoy_cantidad": cant_ventas_hoy,
        "ticket_promedio": (ventas_hoy / cant_ventas_hoy) if cant_ventas_hoy > 0 else 0.0,
        "top_productos": [{"nombre": p[0], "cantidad": p[1]} for p in top_productos],
        "top_categorias": [{"categoria": c[0], "cantidad": c[1]} for c in top_categorias]
    }