from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, time, date

from database import (
    get_db, init_db, 
    InsumoModel, ProductoModel, RecetaModel, 
    VentaModel, VentaDetalleModel, GastoModel
)

app = FastAPI(title="Chinis Burgers API")

init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# ESQUEMAS PYDANTIC
# ==========================================

class InsumoCreate(BaseModel):
    nombre: str
    unidad_medida: str
    cantidad_comprada: float
    precio_total: float
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
    fecha_custom: Optional[str] = None  # Formato YYYY-MM-DD THH:MM por si cargás venta pasada


# ==========================================
# ENDPOINTS - INSUMOS (INVENTARIO)
# ==========================================

@app.get("/insumos")
def listar_insumos(db: Session = Depends(get_db)):
    return db.query(InsumoModel).order_by(InsumoModel.nombre).all()

@app.post("/insumos")
def crear_o_actualizar_insumo(insumo: InsumoCreate, db: Session = Depends(get_db)):
    if insumo.cantidad_comprada <= 0:
        raise HTTPException(status_code=400, detail="La cantidad comprada debe ser mayor a 0")
    
    costo_unitario = insumo.precio_total / insumo.cantidad_comprada

    existente = db.query(InsumoModel).filter(InsumoModel.nombre == insumo.nombre).first()
    if existente:
        existente.cantidad_stock += insumo.cantidad_comprada
        existente.costo_unitario = costo_unitario
        db.commit()
        db.refresh(existente)
        return existente

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
    productos = db.query(ProductoModel).order_by(ProductoModel.nombre).all()
    resultado = []
    for p in productos:
        receta_items = db.query(RecetaModel, InsumoModel)\
            .join(InsumoModel, RecetaModel.insumo_id == InsumoModel.id)\
            .filter(RecetaModel.producto_id == p.id).all()
        
        receta_lista = []
        for r, ins in receta_items:
            receta_lista.append({
                "insumo_id": r.insumo_id,
                "insumo_nombre": ins.nombre,
                "unidad_medida": ins.unidad_medida,
                "cantidad_utilizada": r.cantidad_utilizada
            })

        resultado.append({
            "id": p.id,
            "nombre": p.nombre,
            "categoria": p.categoria,
            "precio_venta": p.precio_venta,
            "receta": receta_lista
        })
    return resultado

@app.post("/productos/con-receta")
def crear_producto_con_receta(producto_data: ProductoConRecetaCreate, db: Session = Depends(get_db)):
    nuevo_producto = ProductoModel(
        nombre=producto_data.nombre,
        categoria=producto_data.categoria,
        precio_venta=producto_data.precio_venta
    )
    db.add(nuevo_producto)
    db.commit()
    db.refresh(nuevo_producto)

    for item in producto_data.receta:
        nueva_receta = RecetaModel(
            producto_id=nuevo_producto.id,
            insumo_id=item.insumo_id,
            cantidad_utilizada=item.cantidad_utilizada
        )
        db.add(nueva_receta)
    
    db.commit()
    return {"status": "ok", "producto_id": nuevo_producto.id}

@app.put("/productos/{producto_id}")
def actualizar_producto_con_receta(producto_id: int, producto_data: ProductoConRecetaCreate, db: Session = Depends(get_db)):
    producto = db.query(ProductoModel).filter(ProductoModel.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    producto.nombre = producto_data.nombre
    producto.categoria = producto_data.categoria
    producto.precio_venta = producto_data.precio_venta

    db.query(RecetaModel).filter(RecetaModel.producto_id == producto_id).delete()

    for item in producto_data.receta:
        nueva_receta = RecetaModel(
            producto_id=producto_id,
            insumo_id=item.insumo_id,
            cantidad_utilizada=item.cantidad_utilizada
        )
        db.add(nueva_receta)

    db.commit()
    return {"status": "ok", "message": f"Producto {producto_id} actualizado"}

@app.delete("/productos/{producto_id}")
def eliminar_producto(producto_id: int, db: Session = Depends(get_db)):
    producto = db.query(ProductoModel).filter(ProductoModel.id == producto_id).first()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    db.query(RecetaModel).filter(RecetaModel.producto_id == producto_id).delete()
    db.delete(producto)
    db.commit()
    return {"status": "ok", "message": f"Producto {producto_id} eliminado"}


# ==========================================
# ENDPOINTS - VENTAS, CALENDARIO Y HISTORIAL
# ==========================================

@app.post("/ventas")
def registrar_venta(venta_data: RegistrarVenta, db: Session = Depends(get_db)):
    if not venta_data.items:
        raise HTTPException(status_code=400, detail="Debe seleccionar al menos un producto")

    fecha_venta = datetime.utcnow()
    if venta_data.fecha_custom:
        try:
            fecha_venta = datetime.fromisoformat(venta_data.fecha_custom)
        except Exception:
            pass

    total_venta = 0.0
    nueva_venta = VentaModel(fecha=fecha_venta, total=0.0)
    db.add(nueva_venta)
    db.commit()
    db.refresh(nueva_venta)

    for item in venta_data.items:
        producto = db.query(ProductoModel).filter(ProductoModel.id == item.producto_id).first()
        if not producto:
            continue
        
        subtotal = producto.precio_venta * item.cantidad
        total_venta += subtotal

        detalle = VentaDetalleModel(
            venta_id=nueva_venta.id,
            producto_id=producto.id,
            cantidad=item.cantidad,
            precio_unitario=producto.precio_venta
        )
        db.add(detalle)

        # Descontar stock
        recetas = db.query(RecetaModel).filter(RecetaModel.producto_id == producto.id).all()
        for r in recetas:
            insumo = db.query(InsumoModel).filter(InsumoModel.id == r.insumo_id).first()
            if insumo:
                insumo.cantidad_stock -= (r.cantidad_utilizada * item.cantidad)

    nueva_venta.total = total_venta
    db.commit()
    return {"status": "ok", "venta_id": nueva_venta.id, "total": total_venta}

@app.get("/ventas/dia/{fecha_str}")
def obtener_ventas_por_fecha(fecha_str: str, db: Session = Depends(get_db)):
    """Obtiene el desglose de ventas para una fecha específica (YYYY-MM-DD)."""
    try:
        fecha_target = datetime.strptime(fecha_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usar YYYY-MM-DD")

    inicio_dia = datetime.combine(fecha_target, time.min)
    fin_dia = datetime.combine(fecha_target, time.max)

    ventas = db.query(VentaModel).filter(VentaModel.fecha >= inicio_dia, VentaModel.fecha <= fin_dia).order_by(VentaModel.fecha.desc()).all()
    
    resultado = []
    total_dia = 0.0

    for v in ventas:
        detalles = db.query(VentaDetalleModel, ProductoModel)\
            .join(ProductoModel, VentaDetalleModel.producto_id == ProductoModel.id)\
            .filter(VentaDetalleModel.venta_id == v.id).all()

        items_list = []
        for d, p in detalles:
            items_list.append({
                "producto_nombre": p.nombre,
                "cantidad": d.cantidad,
                "precio_unitario": d.precio_unitario,
                "subtotal": d.cantidad * d.precio_unitario
            })

        total_dia += v.total
        resultado.append({
            "id": v.id,
            "fecha_hora": v.fecha.strftime("%H:%M"),
            "total": v.total,
            "items": items_list
        })

    return {
        "fecha": fecha_str,
        "total_dia": total_dia,
        "cantidad_ventas": len(ventas),
        "ventas": resultado
    }

@app.delete("/ventas/{venta_id}")
def eliminar_venta(venta_id: int, devolver_stock: bool = True, db: Session = Depends(get_db)):
    """Elimina una venta registrada y opcionalmente devuelve los ingredientes al stock."""
    venta = db.query(VentaModel).filter(VentaModel.id == venta_id).first()
    if not venta:
        raise HTTPException(status_code=404, detail="Venta no encontrada")

    if devolver_stock:
        detalles = db.query(VentaDetalleModel).filter(VentaDetalleModel.venta_id == venta_id).all()
        for d in detalles:
            recetas = db.query(RecetaModel).filter(RecetaModel.producto_id == d.producto_id).all()
            for r in recetas:
                insumo = db.query(InsumoModel).filter(InsumoModel.id == r.insumo_id).first()
                if insumo:
                    insumo.cantidad_stock += (r.cantidad_utilizada * d.cantidad)

    db.query(VentaDetalleModel).filter(VentaDetalleModel.venta_id == venta_id).delete()
    db.delete(venta)
    db.commit()
    return {"status": "ok", "message": f"Venta {venta_id} eliminada"}


# ==========================================
# ENDPOINTS - METRICAS Y DASHBOARD
# ==========================================

@app.get("/stats/dashboard")
def obtener_dashboard_stats(db: Session = Depends(get_db)):
    hoy_inicio = datetime.combine(datetime.utcnow().date(), time.min)
    hoy_fin = datetime.combine(datetime.utcnow().date(), time.max)
    
    ventas_hoy = db.query(func.coalesce(func.sum(VentaModel.total), 0.0))\
        .filter(VentaModel.fecha >= hoy_inicio, VentaModel.fecha <= hoy_fin).scalar()
        
    cant_ventas_hoy = db.query(func.count(VentaModel.id))\
        .filter(VentaModel.fecha >= hoy_inicio, VentaModel.fecha <= hoy_fin).scalar()

    top_productos = db.query(
        ProductoModel.nombre,
        func.sum(VentaDetalleModel.cantidad).label("total_vendido")
    ).join(VentaDetalleModel, ProductoModel.id == VentaDetalleModel.producto_id)\
     .group_by(ProductoModel.nombre)\
     .order_by(func.sum(VentaDetalleModel.cantidad).desc())\
     .limit(5).all()

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