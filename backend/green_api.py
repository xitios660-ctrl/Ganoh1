"""
Green API Integration for WhatsApp
Replaces the local Baileys bot with cloud-based Green API
Works in production (deploy) environment
"""

import httpx
import os
import logging

logger = logging.getLogger(__name__)

# Green API Configuration
GREEN_API_URL = os.environ.get("GREEN_API_URL", "https://7107.api.greenapi.com")
GREEN_API_INSTANCE = os.environ.get("GREEN_API_INSTANCE", "7107550497")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN", "ddbec57064a544909aecfbebe1e4d95faa1677ff39b04f68b2")

# Target group for notifications
WHATSAPP_GROUP_ID = os.environ.get("WHATSAPP_GROUP_ID", "")  # Will be set after joining group


def get_api_url(method: str) -> str:
    """Build the Green API URL for a specific method"""
    return f"{GREEN_API_URL}/waInstance{GREEN_API_INSTANCE}/{method}/{GREEN_API_TOKEN}"


async def check_status() -> dict:
    """Check Green API connection status"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(get_api_url("getStateInstance"))
            data = response.json()
            return {
                "connected": data.get("stateInstance") == "authorized",
                "status": data.get("stateInstance", "unknown"),
                "raw": data
            }
    except Exception as e:
        logger.error(f"Error checking Green API status: {e}")
        return {"connected": False, "status": "error", "error": str(e)}


async def send_message(chat_id: str, message: str) -> dict:
    """Send a text message via Green API"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                get_api_url("sendMessage"),
                json={
                    "chatId": chat_id,
                    "message": message
                }
            )
            data = response.json()
            logger.info(f"Message sent to {chat_id}: {data}")
            return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        return {"success": False, "error": str(e)}


async def send_file_by_url(chat_id: str, url: str, caption: str = "", filename: str = "image.jpg") -> dict:
    """Send a file/image via URL"""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                get_api_url("sendFileByUrl"),
                json={
                    "chatId": chat_id,
                    "urlFile": url,
                    "fileName": filename,
                    "caption": caption
                }
            )
            data = response.json()
            return {"success": True, "data": data}
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        return {"success": False, "error": str(e)}


async def get_groups() -> dict:
    """Get list of groups the account is part of"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(get_api_url("getChats"))
            data = response.json()
            groups = [chat for chat in data if chat.get("id", "").endswith("@g.us")]
            return {"success": True, "groups": groups}
    except Exception as e:
        logger.error(f"Error getting groups: {e}")
        return {"success": False, "error": str(e)}


async def join_group_by_link(invite_link: str) -> dict:
    """Join a WhatsApp group using invite link"""
    try:
        # Extract invite code from link
        # Link format: https://chat.whatsapp.com/INVITE_CODE
        if "chat.whatsapp.com/" in invite_link:
            invite_code = invite_link.split("chat.whatsapp.com/")[1].split("?")[0]
        else:
            invite_code = invite_link
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            # First, get group info by invite code
            response = await client.post(
                get_api_url("getGroupDataByInviteLink"),
                json={"inviteLink": f"https://chat.whatsapp.com/{invite_code}"}
            )
            group_data = response.json()
            
            if "groupJid" in group_data or "id" in group_data:
                group_id = group_data.get("groupJid") or group_data.get("id")
                logger.info(f"Group found: {group_id}")
                return {"success": True, "groupId": group_id, "data": group_data}
            
            # Try to join the group
            response = await client.post(
                get_api_url("addGroupParticipant"),
                json={"inviteLink": f"https://chat.whatsapp.com/{invite_code}"}
            )
            join_data = response.json()
            
            return {"success": True, "data": join_data}
    except Exception as e:
        logger.error(f"Error joining group: {e}")
        return {"success": False, "error": str(e)}


async def send_pix_notification(
    group_id: str,
    customer_name: str,
    payer_name: str,
    amount: float,
    store: str,
    time: str,
    date: str,
    order_number: str,
    items: list,
    auto_approved: bool = False
) -> dict:
    """Send PIX payment notification to WhatsApp group"""
    
    store_emoji = "🏃" if store == "runner" else "🏋️"
    store_name = "Runner" if store == "runner" else "GYM Londres"
    
    status = "✅ APROVADO AUTOMATICAMENTE" if auto_approved else "⚠️ AGUARDANDO APROVAÇÃO"
    
    items_text = "\n".join([f"  • {item.get('quantity', 1)}x {item.get('name', 'Item')}" for item in items[:5]])
    if len(items) > 5:
        items_text += f"\n  ... +{len(items) - 5} itens"
    
    message = f"""
{store_emoji} *NOVO PEDIDO PIX - {store_name}*

👤 *Cliente:* {customer_name}
💳 *Pagador:* {payer_name}
💰 *Valor:* R$ {amount:.2f}
🕐 *Horário:* {time}
📅 *Data:* {date}
🔢 *Pedido:* #{order_number}

📦 *Itens:*
{items_text}

{status}
""".strip()
    
    return await send_message(group_id, message)


async def send_low_stock_report(group_id: str, items: list) -> dict:
    """Send daily low stock report to WhatsApp group"""
    from datetime import datetime
    import pytz
    
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brazil_tz)
    
    message_lines = [
        f"📦 *LISTA DE COMPRAS - {now.strftime('%d/%m/%Y')}*",
        "",
        "Itens com estoque baixo (≤ 2 unidades):",
        ""
    ]
    
    runner_items = [i for i in items if i.get("store") == "runner"]
    gym_items = [i for i in items if i.get("store") == "gym-londres"]
    
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
    
    message_lines.append(f"_Total: {len(items)} itens_")
    
    message = "\n".join(message_lines)
    return await send_message(group_id, message)
