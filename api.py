from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, time

# Importamos la configuración y modelos creados en database.py
from database import (
    get_db, init_db, 
    InsumoModel, ProductoModel, RecetaModel, 
    VentaModel, VentaDetalleModel, GastoModel
)

app = FastAPI(title="Chinis Burgers API")

# Inicializar las tablas de la base de datos al arrancar
init_db()

# Configuración de CORS para permitir peticiones desde GitHub Pages y local
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# ESQUEMAS PYDANTIC (Entrada / Salida)
# ==========================================

class InsumoCreate(BaseModel):
    nombre: str
    unidad_medida: str
    cantidad_comprada: float  # Ej: 25 (kg) o 100 (unidades)
    precio_total: float      # Ej: 18000
    stock_minimo: float = 0.0

class InsumoUpdate(BaseModel):
    cantidad_stock: float
    costo_unitario: float

class RecetaItem(BaseModel):
    insumo_id: int
    cantidad_utilizada: float

class ProductoConRecetaCreate(BaseModel):
    nombre: str
    categoria: str
    precio_venta: float
    receta: List[RecetaItem]

class ItemVenta(BaseModel):
    producto_id: int
    cantidad: int = 1

class RegistrarVenta(BaseModel):
    items: List[ItemVenta]


# ==========================================
# ENDPOINTS - INSUMOS (INVENTARIO)
# ==========================================

@app.get("/insumos")
def listar_insumos(db: Session = Depends(get_db)):
    """Devuelve la lista de todos los insumos y su stock actual."""
    return db.query(InsumoModel).order_by(InsumoModel.nombre).all()

@app.post("/insumos")
def crear_o_actualizar_insumo(insumo: InsumoCreate, db: Session = Depends(get_db)):
    """Carga un insumo por paquete/bolsa y calcula automáticamente el costo unitario."""
    if insumo.cantidad_comprada <= 0:
        raise HTTPException(status_code=400, detail="La cantidad comprada debe ser mayor a 0")
    
    costo_unitario = insumo.precio_total / insumo.cantidad_comprada

    # Si el insumo ya existe, sumamos el stock y actualizamos el costo unitario
    existente = db.query(InsumoModel).filter(InsumoModel.nombre == insumo.nombre).first()
    if existente:
        existente.cantidad_stock += insumo.cantidad_comprada
        existente.costo_unitario = costo_unitario
        db.commit()
        db.refresh(existente)
        return existente

    # Si no existe, creamos uno nuevo
    nuevo = InsumoModel(
        nombre=insumo.nombre,
        unidad_medida=insumo.unidad_medida,
        cantidad_stock=insumo.cantidad_comprada,
        costo_unitario=costo_unitario,
        stock_minimo=insumo.stock_minimo
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo

@app.put("/insumos/{insumo_id}")
def actualizar_insumo(insumo_id: int, datos: InsumoUpdate, db: Session = Depends(get_db)):
    """Actualiza manualmente el stock real o el costo unitario de un insumo."""
    insumo = db.query(InsumoModel).filter(InsumoModel.id == insumo_id).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")
    
    insumo.cantidad_stock = datos.cantidad_stock
    insumo.costo_unitario = datos.costo_unitario
    db.commit()
    db.refresh(insumo)
    return insumo

@app.delete("/insumos/{insumo_id}")
def eliminar_insumo(insumo_id: int, db: Session = Depends(get_db)):
    """Elimina un insumo del inventario."""
    insumo = db.query(InsumoModel).filter(InsumoModel.id == insumo_id).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")
    
    db.delete(insumo)
    db.commit()
    return {"status": "ok", "message": f"Insumo '{insumo.nombre}' eliminado"}


# ==========================================
# ENDPOINTS - PRODUCTOS Y RECETAS
# ==========================================

@app.get("/productos")
def listar_productos(db: Session = Depends(get_db)):
    """Devuelve la lista de productos disponibles para la venta."""
    return db.query(ProductoModel).order_by(ProductoModel.nombre).all()

@app.post("/productos/con-receta")
def crear_producto_con_receta(producto_data: ProductoConRecetaCreate, db: Session = Depends(get_db)):
    """Crea un producto nuevo en el menú vinculando sus insumos correspondientes."""
    nuevo_producto = ProductoModel(
        nombre=producto_data.nombre,
        categoria=producto_data.categoria,
        precio_venta=producto_data.precio_venta
    )
    db.add(nuevo_producto)
    db.commit()
    db.refresh(nuevo_producto)

    # Vinculamos la receta de insumos
    for item in producto_data.receta:
        nueva_receta = RecetaModel(
            producto_id=nuevo_producto.id,
            insumo_id=item.insumo_id,
            cantidad_utilizada=item.cantidad_utilizada
        )
        db.add(nueva_receta)
    
    db.commit()
    return {"status": "ok", "producto_id": nuevo_producto.id}


# ==========================================
# ENDPOINTS - VENTAS Y DESCUENTO DE STOCK
# ==========================================

@app.post("/ventas")
def registrar_venta(venta_data: RegistrarVenta, db: Session = Depends(get_db)):
    """Registra la venta de uno o más productos y descuenta sus recetas del inventario."""
    if not venta_data.items:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos un producto")

    total_venta = 0.0
    nueva_venta = VentaModel(fecha=datetime.utcnow(), total=0.0)
    db.add(nueva_venta)
    db.commit()
    db.refresh(nueva_venta)

    for item in venta_data.items:
        producto = db.query(ProductoModel).filter(ProductoModel.id == item.producto_id).first()
        if not producto:
            continue
        
        subtotal = producto.precio_venta * item.cantidad
        total_venta += subtotal

        # Guardar detalle de producto vendido
        detalle = VentaDetalleModel(
            venta_id=nueva_venta.id,
            producto_id=producto.id,
            cantidad=item.cantidad,
            precio_unitario=producto.precio_venta
        )
        db.add(detalle)

        # Buscar la receta del producto y descontar del inventario
        recetas = db.query(RecetaModel).filter(RecetaModel.producto_id == producto.id).all()
        for r in recetas:
            insumo = db.query(InsumoModel).filter(InsumoModel.id == r.insumo_id).first()
            if insumo:
                insumo.cantidad_stock -= (r.cantidad_utilizada * item.cantidad)

    nueva_venta.total = total_venta
    db.commit()
    return {"status": "ok", "venta_id": nueva_venta.id, "total": total_venta}


# ==========================================
# ENDPOINTS - METRICAS Y DASHBOARD
# ==========================================

@app.get("/stats/dashboard")
def obtener_dashboard_stats(db: Session = Depends(get_db)):
    """Retorna las métricas del día (ventas, pedidos, top productos y categorías)."""
    hoy_inicio = datetime.combine(datetime.utcnow().date(), time.min)
    hoy_fin = datetime.combine(datetime.utcnow().date(), time.max)
    
    # 1. Total ventas acumuladas hoy
    ventas_hoy = db.query(func.coalesce(func.sum(VentaModel.total), 0.0))\
        .filter(VentaModel.fecha >= hoy_inicio, VentaModel.fecha <= hoy_fin).scalar()
        
    # 2. Cantidad de tickets/pedidos hoy
    cant_ventas_hoy = db.query(func.count(VentaModel.id))\
        .filter(VentaModel.fecha >= hoy_inicio, VentaModel.fecha <= hoy_fin).scalar()

    # 3. Top 5 Productos más vendidos
    top_productos = db.query(
        ProductoModel.nombre,
        func.sum(VentaDetalleModel.cantidad).label("total_vendido")
    ).join(VentaDetalleModel, ProductoModel.id == VentaDetalleModel.producto_id)\
     .group_by(ProductoModel.nombre)\
     .order_by(func.sum(VentaDetalleModel.cantidad).desc())\
     .limit(5).all()

    # 4. Distribución por Categorías
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