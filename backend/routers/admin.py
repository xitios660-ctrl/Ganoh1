"""Admin Routes for Data Management and Low Stock Alerts"""
from fastapi import APIRouter, HTTPException
from datetime import datetime
import pytz
import logging

router = APIRouter(prefix="/admin", tags=["Admin"])

logger = logging.getLogger(__name__)

# Will be set by main app
db = None
BRAZIL_TZ = pytz.timezone("America/Sao_Paulo")

# Import WhatsApp helper (will be set by main app)
send_whatsapp_message = None

def set_dependencies(database, whatsapp_func, brazil_tz):
    global db, send_whatsapp_message, BRAZIL_TZ
    db = database
    send_whatsapp_message = whatsapp_func
    BRAZIL_TZ = brazil_tz

# ==================== LOW STOCK FUNCTIONS ====================

async def check_and_save_low_stock_items():
    """Check stock and save items with quantity <= 2 to low_stock_list collection"""
    try:
        # Find all items with low stock
        low_stock_items = await db.stock.find({
            "quantity": {"$lte": 2}
        }, {"_id": 0}).to_list(100)
        
        for item in low_stock_items:
            menu_item_id = item.get("menu_item_id")
            store = item.get("store")
            
            # Get item name from stock or menu
            item_name = item.get("item_name", item.get("name", ""))
            if not item_name:
                menu_item = await db.menu.find_one({"id": menu_item_id})
                if menu_item:
                    item_name = menu_item.get("name", f"Item {menu_item_id}")
            
            # Check if already in low_stock_list
            existing = await db.low_stock_list.find_one({
                "menu_item_id": menu_item_id,
                "store": store
            })
            
            if not existing:
                await db.low_stock_list.insert_one({
                    "menu_item_id": menu_item_id,
                    "name": item_name,
                    "store": store,
                    "quantity": item.get("quantity", 0),
                    "added_at": datetime.now(BRAZIL_TZ).isoformat()
                })
            else:
                # Update quantity
                await db.low_stock_list.update_one(
                    {"menu_item_id": menu_item_id, "store": store},
                    {"$set": {"quantity": item.get("quantity", 0)}}
                )
        
        # Also check default menu items that might be low
        for store_key in ["runner", "gym-londres"]:
            stock_item = await db.stock.find_one({"store": store_key, "quantity": {"$lte": 2}})
            if stock_item:
                existing = await db.low_stock_list.find_one({
                    "menu_item_id": stock_item.get("menu_item_id"),
                    "store": store_key
                })
                if not existing:
                    await db.low_stock_list.insert_one({
                        "menu_item_id": stock_item.get("menu_item_id"),
                        "name": stock_item.get("item_name", stock_item.get("name", "")),
                        "store": store_key,
                        "quantity": stock_item.get("quantity", 0),
                        "added_at": datetime.now(BRAZIL_TZ).isoformat()
                    })
        
        logger.info(f"Low stock check completed. Found {len(low_stock_items)} items.")
        
    except Exception as e:
        logger.error(f"Error in check_and_save_low_stock_items: {e}")

async def send_low_stock_report():
    """Send daily low stock report to WhatsApp group at 22:00"""
    try:
        # Get all items in the low stock list
        low_stock_items = await db.low_stock_list.find({}).to_list(100)
        
        if not low_stock_items:
            logger.info("No low stock items to report")
            return
        
        # Build the message
        now = datetime.now(BRAZIL_TZ)
        message_lines = [
            f"📦 *LISTA DE COMPRAS - {now.strftime('%d/%m/%Y')}*",
            "",
            "Itens com estoque baixo (≤ 2 unidades):",
            ""
        ]
        
        # Group by store
        runner_items = [i for i in low_stock_items if i.get("store") == "runner"]
        gym_items = [i for i in low_stock_items if i.get("store") == "gym-londres"]
        
        if runner_items:
            message_lines.append("*🏃 RUNNER:*")
            for item in runner_items:
                qty = item.get("quantity", 0)
                status = "🔴 ZERADO" if qty == 0 else f"⚠️ {qty} un"
                message_lines.append(f"  • {item.get('name')}: {status}")
            message_lines.append("")
        
        if gym_items:
            message_lines.append("*🏋️ GYM LONDRES:*")
            for item in gym_items:
                qty = item.get("quantity", 0)
                status = "🔴 ZERADO" if qty == 0 else f"⚠️ {qty} un"
                message_lines.append(f"  • {item.get('name')}: {status}")
            message_lines.append("")
        
        message_lines.append(f"_Total: {len(low_stock_items)} itens_")
        
        message = "\n".join(message_lines)
        
        # Send to WhatsApp via Green API
        try:
            if send_whatsapp_message:
                result = await send_whatsapp_message(message)
                if result.get("success"):
                    logger.info(f"Low stock report sent successfully! {len(low_stock_items)} items")
                    
                    # Clear the list after sending
                    await db.low_stock_list.delete_many({})
                    logger.info("Low stock list cleared")
                else:
                    logger.error(f"Failed to send low stock report: {result.get('error')}")
        except Exception as e:
            logger.error(f"Error sending WhatsApp message: {e}")
            
    except Exception as e:
        logger.error(f"Error in send_low_stock_report: {e}")

# ==================== ROUTES ====================

@router.get("/low-stock-list")
async def get_low_stock_list():
    """Get current low stock list"""
    items = await db.low_stock_list.find({}, {"_id": 0}).to_list(100)
    return {"items": items, "count": len(items)}

@router.post("/check-low-stock")
async def trigger_low_stock_check():
    """Manually trigger low stock check"""
    await check_and_save_low_stock_items()
    items = await db.low_stock_list.find({}, {"_id": 0}).to_list(100)
    return {"success": True, "items": items, "message": f"Encontrados {len(items)} itens com estoque baixo"}

@router.post("/send-low-stock-report")
async def trigger_send_report():
    """Manually trigger sending the low stock report"""
    await send_low_stock_report()
    return {"success": True, "message": "Relatório enviado (se havia itens na lista)"}

@router.post("/clear-data")
async def clear_all_data(password: str):
    """Clear all data from the system"""
    if password != "152637":
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    # Clear all collections
    await db.orders.delete_many({})
    await db.order_history.delete_many({})
    await db.expenses.delete_many({})
    await db.prazo_customers.delete_many({})
    await db.low_stock_list.delete_many({})
    
    # Reset stock to default values
    await db.stock.update_many({}, {"$set": {"quantity": 10}})
    
    return {"success": True, "message": "Todos os dados foram limpos"}

@router.post("/clear-store/{store}")
async def clear_store_data(store: str, password: str):
    """Clear data for a specific store"""
    if password != "152637":
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    if store not in ["runner", "gym-londres"]:
        raise HTTPException(status_code=400, detail="Loja inválida")
    
    # Clear store-specific data
    await db.orders.delete_many({"store": store})
    await db.order_history.delete_many({"store": store})
    await db.stock.update_many({"store": store}, {"$set": {"quantity": 10}})
    await db.low_stock_list.delete_many({"store": store})
    
    return {"success": True, "message": f"Dados da loja {store} foram limpos"}

@router.post("/clear-all-data-extended")
async def clear_all_data_extended(password: str):
    """Clear ALL data including charts and expenses"""
    if password != "152637":
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    # Clear all data collections
    collections_to_clear = [
        "orders", "order_history", "expenses", "prazo_customers",
        "low_stock_list", "expense_chats"
    ]
    
    for collection in collections_to_clear:
        await db[collection].delete_many({})
    
    # Reset all stock
    await db.stock.update_many({}, {"$set": {"quantity": 10}})
    
    return {
        "success": True, 
        "message": "Todos os dados foram limpos (pedidos, histórico, gastos, prazo, estoque baixo)",
        "collections_cleared": collections_to_clear
    }
