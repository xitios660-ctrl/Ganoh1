"""Stock Management Routes"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid
import logging

router = APIRouter(prefix="/stock", tags=["Stock"])
logger = logging.getLogger(__name__)

# Will be set by main app
db = None

def set_dependencies(database):
    global db
    db = database

# ==================== MODELS ====================

class StockUpdate(BaseModel):
    quantity: int

class StockItemCreate(BaseModel):
    menu_item_id: str
    quantity: int = 0
    min_quantity: int = 5
    item_name: Optional[str] = None

# ==================== ROUTES ====================

@router.get("/{store}")
async def get_stock(store: str):
    """Get stock for a store"""
    stock_items = await db.stock.find({"store": store}, {"_id": 0}).to_list(500)
    
    result = []
    for item in stock_items:
        menu_item = await db.menu.find_one({"id": item.get("menu_item_id")})
        if menu_item:
            result.append({
                **item,
                "name": menu_item.get("name", ""),
                "category": menu_item.get("category", ""),
                "price": menu_item.get("price", 0)
            })
        else:
            result.append(item)
    
    return {"items": result}

@router.put("/{store}/{menu_item_id}")
async def update_stock(store: str, menu_item_id: str, stock_update: StockUpdate):
    """Update stock quantity"""
    await db.stock.update_one(
        {"store": store, "menu_item_id": menu_item_id},
        {"$set": {
            "quantity": stock_update.quantity,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }},
        upsert=True
    )
    return {"success": True, "message": "Estoque atualizado"}

@router.post("/{store}")
async def add_stock_item(store: str, item: StockItemCreate):
    """Add a new stock item"""
    existing = await db.stock.find_one({"store": store, "menu_item_id": item.menu_item_id})
    if existing:
        raise HTTPException(status_code=400, detail="Item já existe no estoque desta loja")
    
    new_stock = {
        "id": str(uuid.uuid4()),
        "store": store,
        "menu_item_id": item.menu_item_id,
        "quantity": item.quantity,
        "min_quantity": item.min_quantity,
        "item_name": item.item_name,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.stock.insert_one(new_stock)
    return {**new_stock, "_id": None}

@router.delete("/{store}/{menu_item_id}")
async def delete_stock_item(store: str, menu_item_id: str):
    """Delete a stock item"""
    result = await db.stock.delete_one({"store": store, "menu_item_id": menu_item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado no estoque")
    return {"success": True, "message": "Item removido do estoque"}

@router.post("/{store}/initialize")
async def initialize_stock(store: str, default_quantity: int = 50):
    """Initialize stock for all menu items"""
    menu_items = await db.menu.find(
        {"$or": [{"store": store}, {"store": None}, {"store": {"$exists": False}}]},
        {"_id": 0}
    ).to_list(200)
    
    added = 0
    for item in menu_items:
        existing = await db.stock.find_one({"store": store, "menu_item_id": item["id"]})
        if not existing:
            await db.stock.insert_one({
                "id": str(uuid.uuid4()),
                "store": store,
                "menu_item_id": item["id"],
                "item_name": item.get("name", ""),
                "quantity": default_quantity,
                "min_quantity": 5,
                "created_at": datetime.now(timezone.utc).isoformat()
            })
            added += 1
    
    return {"success": True, "message": f"Estoque inicializado. {added} itens adicionados."}

@router.get("/{store}/debug")
async def debug_stock(store: str):
    """Debug stock - find problematic items"""
    all_stock = await db.stock.find({"store": store}, {"_id": 0}).to_list(500)
    
    problematic = []
    for item in all_stock:
        qty = item.get("quantity", 0)
        if qty <= 0:
            problematic.append({
                "menu_item_id": item.get("menu_item_id"),
                "item_name": item.get("item_name", "Unknown"),
                "quantity": qty,
                "issue": "zero_or_negative"
            })
    
    return {
        "total_items": len(all_stock),
        "problematic_count": len(problematic),
        "problematic_items": problematic
    }

@router.post("/{store}/fix-zero")
async def fix_zero_stock(store: str):
    """Fix zero stock records by removing them"""
    result = await db.stock.delete_many({
        "store": store,
        "quantity": {"$lte": 0}
    })
    
    return {
        "success": True,
        "message": f"Removidos {result.deleted_count} registros de estoque zerado/negativo",
        "deleted_count": result.deleted_count
    }

@router.get("/{store}/check-issues")
async def check_stock_issues(store: str):
    """Check for stock issues that might block orders"""
    issues = []
    
    all_stock = await db.stock.find({"store": store}, {"_id": 0}).to_list(500)
    for item in all_stock:
        qty = item.get("quantity", 0)
        menu_item_id = item.get("menu_item_id")
        item_name = item.get("item_name", "Unknown")
        
        if qty == 0:
            menu_item = await db.menu.find_one({"id": menu_item_id})
            if menu_item:
                issues.append({
                    "type": "ghost_zero_stock",
                    "menu_item_id": menu_item_id,
                    "name": menu_item.get("name", item_name),
                    "quantity": qty,
                    "recommendation": "Delete this stock record or set quantity > 0"
                })
    
    return {
        "store": store,
        "issues_found": len(issues),
        "issues": issues,
        "recommendation": "Use POST /api/admin/fix-zero-stock/{store} to remove ghost records"
    }
