"""WhatsApp Green API Integration Routes"""
from fastapi import APIRouter
from pydantic import BaseModel
import httpx
import os
import logging

router = APIRouter(prefix="/whatsapp", tags=["WhatsApp"])

logger = logging.getLogger(__name__)

# Green API Configuration
GREEN_API_URL = os.environ.get("GREEN_API_URL", "https://7107.api.greenapi.com")
GREEN_API_INSTANCE = os.environ.get("GREEN_API_INSTANCE", "")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN", "")
WHATSAPP_GROUP_ID = os.environ.get("WHATSAPP_GROUP_ID", "")

def get_green_api_url(method: str) -> str:
    return f"{GREEN_API_URL}/waInstance{GREEN_API_INSTANCE}/{method}/{GREEN_API_TOKEN}"

# ==================== HELPER FUNCTIONS ====================

async def send_whatsapp_message(message: str, group_id: str = None) -> dict:
    """Send a message via Green API"""
    target = group_id or WHATSAPP_GROUP_ID
    if not target:
        return {"success": False, "error": "No WhatsApp target configured"}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                get_green_api_url("sendMessage"),
                json={"chatId": target, "message": message}
            )
            return {"success": response.status_code == 200, "response": response.json()}
    except Exception as e:
        logging.error(f"Error sending WhatsApp message: {e}")
        return {"success": False, "error": str(e)}

async def send_whatsapp_notification(
    store: str,
    customer_name: str,
    total: float,
    payment_method: str,
    items: list,
    order_id: str = None,
    time: str = None,
    date: str = None,
    pix_proof: str = None,
    payer_name: str = None,
    target: str = None
) -> dict:
    """Send a notification about a new order"""
    target = target or WHATSAPP_GROUP_ID
    
    store_emoji = "🏃" if store == "runner" else "🏋️"
    store_name = "Runner" if store == "runner" else "GYM Londres"
    
    items_text = "\n".join([f"  • {item.get('name', '')} x{item.get('quantity', 1)}" for item in items])
    
    payer_info = f"\n👤 *Pagador:* {payer_name}" if payer_name else ""
    
    message = f"""✅ *PAGAMENTO APROVADO*

{store_emoji} *{store_name}*
📋 *Pedido:* {order_id or 'N/A'}
👤 *Cliente:* {customer_name}{payer_info}
💰 *Total:* R$ {total:.2f}
💳 *Pagamento:* {payment_method.upper()}
🕐 *Horário:* {time or 'N/A'} - {date or 'N/A'}

*Itens:*
{items_text}"""

    # If we have a PIX proof image, send it with the message
    if pix_proof and pix_proof.startswith("data:image"):
        try:
            import base64
            # Extract base64 data
            base64_data = pix_proof.split(",")[1] if "," in pix_proof else pix_proof
            image_bytes = base64.b64decode(base64_data)
            
            async with httpx.AsyncClient() as client:
                files = {"file": ("comprovante.jpg", image_bytes, "image/jpeg")}
                data = {"chatId": target, "caption": message}
                response = await client.post(
                    get_green_api_url("sendFileByUpload"),
                    files=files,
                    data=data
                )
                if response.status_code == 200:
                    return {"success": True, "response": response.json()}
        except Exception as e:
            logger.error(f"Error sending image: {e}")
    
    # Fallback: send text message only
    return await send_whatsapp_message(message, target)

# ==================== MODELS ====================

class WhatsAppTargetUpdate(BaseModel):
    target: str

class WhatsAppJoinGroup(BaseModel):
    invite_link: str

# ==================== ROUTES ====================

@router.get("/status")
async def get_whatsapp_status():
    """Get WhatsApp connection status"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(get_green_api_url("getStateInstance"))
            data = response.json()
            return {
                "connected": data.get("stateInstance") == "authorized",
                "state": data.get("stateInstance"),
                "details": data
            }
    except Exception as e:
        return {"connected": False, "error": str(e)}

@router.get("/qr")
async def get_whatsapp_qr():
    """Get QR code for WhatsApp connection"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(get_green_api_url("qr"))
            return response.json()
    except Exception as e:
        return {"error": str(e)}

@router.get("/groups")
async def get_whatsapp_groups():
    """Get list of WhatsApp groups"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(get_green_api_url("getContacts"))
            contacts = response.json()
            groups = [c for c in contacts if c.get("id", "").endswith("@g.us")]
            return {"groups": groups}
    except Exception as e:
        return {"error": str(e)}

@router.post("/set-target")
async def set_whatsapp_target(data: WhatsAppTargetUpdate):
    """Set WhatsApp notification target (group or number)"""
    global WHATSAPP_GROUP_ID
    WHATSAPP_GROUP_ID = data.target
    return {"success": True, "target": data.target}

@router.post("/join-group")
async def join_whatsapp_group(data: WhatsAppJoinGroup):
    """Join a WhatsApp group via invite link"""
    try:
        # Extract group code from link
        invite_code = data.invite_link.split("/")[-1]
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                get_green_api_url("joinGroupByInviteCode"),
                json={"inviteCode": invite_code}
            )
            result = response.json()
            
            if "groupId" in result:
                global WHATSAPP_GROUP_ID
                WHATSAPP_GROUP_ID = result["groupId"]
                return {"success": True, "groupId": result["groupId"]}
            
            return {"success": False, "error": result}
    except Exception as e:
        return {"success": False, "error": str(e)}

@router.post("/send-test")
async def send_test_message(message: str = "Teste de conexão"):
    """Send a test message to the configured target"""
    result = await send_whatsapp_message(f"🧪 *TESTE*\n\n{message}")
    return result
