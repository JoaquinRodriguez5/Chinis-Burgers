import os
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel

from database import (
    get_db,
    init_db,
    InsumoModel,
    ProductoModel,
    RecetaModel,
    VentaModel,
    VentaDetalleModel,
    GastoModel
)

app = FastAPI(title="Chinis Burgers API")

# Configuración de CORS para permitir peticiones desde GitHub Pages
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    init_db()

# --- ESQUEMAS PYDANTIC ---

class InsumoCreateSchema(BaseModel):
    nombre: str
    unidad_medida: str
    cantidad_stock: float
    costo_unitario: float

class ProductoCreateSchema(BaseModel):
    nombre: str
    precio_venta: float

class RecetaItemSchema(BaseModel):
    insumo_id: int
    cantidad_utilizada: float

class RecetaCreateSchema(BaseModel):
    producto_id: int
    items: List[RecetaItemSchema]

class ItemVentaSchema(BaseModel):
    producto_id: int
    cantidad: int

class VentaCreateSchema(BaseModel):
    items: List[ItemVentaSchema]
    metodo_pago: Optional[str] = "Efectivo"

class GastoCreateSchema(BaseModel):
    descripcion: str
    monto: float
    categoria: Optional[str] = "General"


# --- RUTAS DE LA API ---

@app.get("/")
def home():
    return {"mensaje": "API Chinis Burgers Funcionando correctamente"}

# --- INSUMOS ---
@app.get("/insumos")
def listar_insumos(db: Session = Depends(get_db)):
    return db.query(InsumoModel).all()

@app.post("/insumos")
def crear_insumo(insumo: InsumoCreateSchema, db: Session = Depends(get_db)):
    nuevo_insumo = InsumoModel(
        nombre=insumo.nombre,
        unidad_medida=insumo.unidad_medida,
        cantidad_stock=insumo.cantidad_stock,
        costo_unitario=insumo.costo_unitario
    )
    db.add(nuevo_insumo)
    db.commit()
    db.refresh(nuevo_insumo)
    return nuevo_insumo

@app.put("/insumos/{insumo_id}")
def actualizar_insumo(insumo_id: int, datos: InsumoCreateSchema, db: Session = Depends(get_db)):
    insumo = db.query(InsumoModel).filter(InsumoModel.id == insumo_id).first()
    if not insumo:
        raise HTTPException(status_code=404, detail="Insumo no encontrado")
    
    insumo.nombre = datos.nombre
    insumo.unidad_medida = datos.unidad_medida
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
    return {"mensaje": "Insumo eliminado con éxito"}

# --- PRODUCTOS ---
@app.get("/productos")
def listar_productos(db: Session = Depends(get_db)):
    return db.query(ProductoModel).all()

@app.post("/productos")
def crear_producto(prod: ProductoCreateSchema, db: Session = Depends(get_db)):
    nuevo_prod = ProductoModel(
        nombre=prod.nombre,
        precio_venta=prod.precio_venta
    )
    db.add(nuevo_prod)
    db.commit()
    db.refresh(nuevo_prod)
    return nuevo_prod

# --- RECETAS ---
@app.post("/recetas")
def guardar_receta(receta_data: RecetaCreateSchema, db: Session = Depends(get_db)):
    db.query(RecetaModel).filter(RecetaModel.producto_id == receta_data.producto_id).delete()
    
    nuevos_items = []
    for item in receta_data.items:
        nuevo_item = RecetaModel(
            producto_id=receta_data.producto_id,
            insumo_id=item.insumo_id,
            cantidad_utilizada=item.cantidad_utilizada
        )
        db.add(nuevo_item)
        nuevos_items.append(nuevo_item)
        
    db.commit()
    return {"mensaje": "Receta actualizada con éxito", "items_guardados": len(nuevos_items)}

@app.get("/recetas/{producto_id}")
def obtener_receta(producto_id: int, db: Session = Depends(get_db)):
    return db.query(RecetaModel).filter(RecetaModel.producto_id == producto_id).all()

# --- VENTAS ---
@app.get("/ventas")
def listar_ventas(db: Session = Depends(get_db)):
    return db.query(VentaModel).all()

@app.post("/ventas")
def registrar_venta(venta_data: VentaCreateSchema, db: Session = Depends(get_db)):
    try:
        nueva_venta = VentaModel()
        nueva_venta.total = 0.0
        nueva_venta.metodo_pago = getattr(venta_data, 'metodo_pago', 'Efectivo')
        
        db.add(nueva_venta)
        db.flush()

        total_venta = 0.0

        for item in venta_data.items:
            producto = db.query(ProductoModel).filter(ProductoModel.id == item.producto_id).first()
            if not producto:
                raise HTTPException(status_code=404, detail=f"Producto ID {item.producto_id} no encontrado")

            subtotal = producto.precio_venta * item.cantidad
            total_venta += subtotal

            receta_items = db.query(RecetaModel).filter(RecetaModel.producto_id == producto.id).all()
            for rec in receta_items:
                insumo = db.query(InsumoModel).filter(InsumoModel.id == rec.insumo_id).first()
                if insumo:
                    descuento = rec.cantidad_utilizada * item.cantidad
                    insumo.cantidad_stock -= descuento

            detalle = VentaDetalleModel(
                venta_id=nueva_venta.id,
                producto_id=producto.id,
                cantidad=item.cantidad,
                precio_unitario=producto.precio_venta,
                subtotal=subtotal
            )
            db.add(detalle)

        nueva_venta.total = total_venta
        db.commit()
        db.refresh(nueva_venta)

        return {"mensaje": "Venta registrada con éxito", "id": nueva_venta.id, "total": nueva_venta.total}

    except Exception as e:
        db.rollback()
        print("ERROR EN REGISTRAR VENTA:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# --- GASTOS ---
@app.get("/gastos")
def listar_gastos(db: Session = Depends(get_db)):
    return db.query(GastoModel).all()

@app.post("/gastos")
def crear_gasto(gasto: GastoCreateSchema, db: Session = Depends(get_db)):
    nuevo_gasto = GastoModel(
        descripcion=gasto.descripcion,
        monto=gasto.monto,
        categoria=gasto.categoria
    )
    db.add(nuevo_gasto)
    db.commit()
    db.refresh(nuevo_gasto)
    return nuevo_gasto

# --- BALANCE Y ESTADÍSTICAS ---
@app.get("/balance")
def obtener_balance(db: Session = Depends(get_db)):
    total_ventas = db.query(func.sum(VentaModel.total)).scalar() or 0.0
    total_gastos = db.query(func.sum(GastoModel.monto)).scalar() or 0.0
    
    ventas_efectivo = db.query(func.sum(VentaModel.total)).filter(VentaModel.metodo_pago == "Efectivo").scalar() or 0.0
    ventas_mp = db.query(func.sum(VentaModel.total)).filter(VentaModel.metodo_pago == "MP / Transf.").scalar() or 0.0
    ventas_tarjeta = db.query(func.sum(VentaModel.total)).filter(VentaModel.metodo_pago == "Tarjeta").scalar() or 0.0

    return {
        "total_ventas": total_ventas,
        "total_gastos": total_gastos,
        "balance_neto": total_ventas - total_gastos,
        "desglose_ventas": {
            "efectivo": ventas_efectivo,
            "mp_transferencia": ventas_mp,
            "tarjeta": ventas_tarjeta
        }
    }