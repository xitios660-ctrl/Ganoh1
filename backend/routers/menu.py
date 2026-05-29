"""Menu and Adicionais Routes"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime, timezone
import uuid
import logging

router = APIRouter(tags=["Menu"])
logger = logging.getLogger(__name__)

# Will be set by main app
db = None
verify_gestor = None

def set_dependencies(database, gestor_verifier=None):
    global db, verify_gestor
    db = database
    verify_gestor = gestor_verifier

# ==================== MODELS ====================

class MenuItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    price: float
    category: str
    store: Optional[str] = None
    prep_time: int = 15
    available: bool = True
    codigo: Optional[str] = None
    codigo_externo: Optional[str] = None
    unidade: str = "UN"
    valor_custo: float = 0.0
    codigo_barras: Optional[str] = None
    grupo: Optional[str] = None
    ncm: Optional[str] = None
    cst: Optional[str] = None
    csosn: Optional[str] = None
    cfop: Optional[str] = None
    cest: Optional[str] = None
    icms_aliquota: Optional[float] = None
    icms_tipo: Optional[str] = None
    pis_cst: Optional[str] = None
    pis_aliquota: Optional[float] = None
    cofins_cst: Optional[str] = None
    cofins_aliquota: Optional[float] = None
    estoque_minimo: float = 0.0
    estoque_producao: bool = False

class MenuItemCreate(BaseModel):
    name: str
    description: str = ""
    price: float
    category: str
    store: Optional[str] = None
    prep_time: int = 15
    available: bool = True

class MenuItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    store: Optional[str] = None
    prep_time: Optional[int] = None
    available: Optional[bool] = None

class AdicionalCreate(BaseModel):
    name: str
    price: float

class AdicionalUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None

# ==================== MENU ROUTES (GESTOR) ====================

@router.get("/gestor/menu/{store}")
async def get_store_menu(store: str):
    """Get menu items for a specific store (gestor view)"""
    items = await db.menu.find(
        {"$or": [{"store": store}, {"store": None}, {"store": {"$exists": False}}]},
        {"_id": 0}
    ).to_list(200)
    return {"items": items}

@router.post("/gestor/menu")
async def create_menu_item(item: MenuItemCreate):
    """Create a new menu item"""
    new_item = {
        "id": str(uuid.uuid4()),
        "name": item.name,
        "description": item.description,
        "price": item.price,
        "category": item.category,
        "store": item.store,
        "prep_time": item.prep_time,
        "available": item.available,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.menu.insert_one(new_item)
    return {**new_item, "_id": None}

@router.put("/gestor/menu/{item_id}")
async def update_menu_item(item_id: str, update: MenuItemUpdate):
    """Update a menu item"""
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar")
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.menu.update_one(
        {"id": item_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    
    return {"success": True, "message": "Item atualizado"}

@router.delete("/gestor/menu/{item_id}")
async def delete_menu_item(item_id: str):
    """Delete a menu item"""
    result = await db.menu.delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    
    await db.stock.delete_many({"menu_item_id": item_id})
    
    return {"success": True, "message": "Item removido"}

# ==================== MENU ROUTES (KITCHEN) ====================

@router.get("/kitchen/menu/{store}")
async def get_menu_kitchen(store: str):
    """Get menu items for kitchen view"""
    items = await db.menu.find(
        {"$or": [{"store": store}, {"store": None}, {"store": {"$exists": False}}]},
        {"_id": 0}
    ).to_list(200)
    return {"items": items}

@router.post("/kitchen/menu")
async def create_menu_item_kitchen(item: MenuItem):
    """Create a menu item from kitchen"""
    item_dict = item.model_dump()
    item_dict["id"] = str(uuid.uuid4())
    item_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.menu.insert_one(item_dict)
    return {**item_dict, "_id": None}

@router.put("/kitchen/menu/{item_id}")
async def update_menu_item_kitchen(item_id: str, item: MenuItem):
    """Update a menu item from kitchen"""
    item_dict = item.model_dump()
    item_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.menu.update_one({"id": item_id}, {"$set": item_dict})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return {"success": True}

@router.delete("/kitchen/menu/{item_id}")
async def delete_menu_item_kitchen(item_id: str):
    """Delete a menu item from kitchen"""
    await db.menu.delete_one({"id": item_id})
    await db.stock.delete_many({"menu_item_id": item_id})
    return {"success": True}

# ==================== ADICIONAIS ROUTES (GESTOR) ====================

@router.get("/gestor/adicionais")
async def get_adicionais():
    """Get all adicionais"""
    adicionais = await db.adicionais.find({}, {"_id": 0}).to_list(100)
    return {"adicionais": adicionais}

@router.post("/gestor/adicionais")
async def create_adicional(adicional: AdicionalCreate):
    """Create a new adicional"""
    new_adicional = {
        "id": str(uuid.uuid4()),
        "name": adicional.name,
        "price": adicional.price,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.adicionais.insert_one(new_adicional)
    return {**new_adicional, "_id": None}

@router.put("/gestor/adicionais/{adicional_id}")
async def update_adicional(adicional_id: str, update: AdicionalUpdate):
    """Update an adicional"""
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    result = await db.adicionais.update_one({"id": adicional_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Adicional não encontrado")
    return {"success": True}

@router.delete("/gestor/adicionais/{adicional_id}")
async def delete_adicional(adicional_id: str):
    """Delete an adicional"""
    await db.adicionais.delete_one({"id": adicional_id})
    return {"success": True}

# ==================== ADICIONAIS ROUTES (KITCHEN) ====================

@router.get("/kitchen/adicionais")
async def get_adicionais_kitchen():
    """Get all adicionais for kitchen"""
    adicionais = await db.adicionais.find({}, {"_id": 0}).to_list(100)
    return {"adicionais": adicionais}

@router.post("/kitchen/adicionais")
async def create_adicional_kitchen(adicional: AdicionalCreate):
    """Create adicional from kitchen"""
    new_adicional = {
        "id": str(uuid.uuid4()),
        "name": adicional.name,
        "price": adicional.price,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.adicionais.insert_one(new_adicional)
    return {**new_adicional, "_id": None}

@router.put("/kitchen/adicionais/{adicional_id}")
async def update_adicional_kitchen(adicional_id: str, update: AdicionalUpdate):
    """Update adicional from kitchen"""
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    await db.adicionais.update_one({"id": adicional_id}, {"$set": update_data})
    return {"success": True}

@router.delete("/kitchen/adicionais/{adicional_id}")
async def delete_adicional_kitchen(adicional_id: str):
    """Delete adicional from kitchen"""
    await db.adicionais.delete_one({"id": adicional_id})
    return {"success": True}
