#!/usr/bin/env python3
"""
Serviço de sincronização que monitora pedidos PIX do Deploy (produção)
e faz a verificação automática com IA, enviando notificações para o WhatsApp.
"""

import asyncio
import httpx
import json
import os
import logging
from datetime import datetime, timezone

# Configuração de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# URLs
DEPLOY_URL = os.environ.get("DEPLOY_URL", "https://prazo-payment-sys.emergent.host")
PREVIEW_URL = os.environ.get("PREVIEW_URL", "http://localhost:8001")
WHATSAPP_BOT_URL = os.environ.get("WHATSAPP_BOT_URL", "http://localhost:8002")

# Lojas para monitorar
STORES = ["runner", "gym-londres"]

# Intervalo de polling (segundos)
POLL_INTERVAL = 5

# Rastrear pedidos já processados
processed_orders = set()

async def get_pending_pix_orders(store: str) -> list:
    """Busca pedidos PIX pendentes do deploy"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{DEPLOY_URL}/api/orders/{store}/pending-pix")
            if response.status_code == 200:
                data = response.json()
                return data.get("orders", [])
    except Exception as e:
        logger.error(f"Erro ao buscar pedidos de {store}: {e}")
    return []

async def verify_pix_with_ai(order: dict, store: str) -> dict:
    """Envia comprovante para verificação com IA no preview"""
    try:
        order_id = order.get("id")
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{PREVIEW_URL}/api/orders/{store}/{order_id}/auto-verify-pix-external",
                json={
                    "pix_proof": order.get("pix_proof"),
                    "expected_amount": order.get("total", 0),
                    "customer_name": order.get("customer_name", "Cliente")
                }
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Erro na verificação IA para pedido {order.get('id')}: {e}")
    return {"success": False, "error": str(e)}

async def update_order_in_deploy(order_id: str, store: str, analysis: dict, auto_approved: bool):
    """Atualiza o pedido no deploy com o resultado da análise"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Atualizar análise PIX
            await client.patch(
                f"{DEPLOY_URL}/api/orders/{store}/{order_id}/pix-analysis",
                json={
                    "pix_analysis": analysis,
                    "pix_payer_name": analysis.get("payer_name", "Desconhecido"),
                    "pix_transaction_time": analysis.get("transaction_time", ""),
                    "auto_approved": auto_approved
                }
            )
            
            # Se auto-aprovado, mudar status para "received"
            if auto_approved:
                await client.patch(
                    f"{DEPLOY_URL}/api/orders/{store}/{order_id}/status",
                    json={"status": "received"}
                )
                logger.info(f"✅ Pedido {order_id} auto-aprovado no deploy!")
            else:
                logger.info(f"⚠️ Pedido {order_id} precisa de aprovação manual")
                
    except Exception as e:
        logger.error(f"Erro ao atualizar pedido {order_id} no deploy: {e}")

async def send_whatsapp_notification(order: dict, store: str, analysis: dict, auto_approved: bool):
    """Envia notificação para o WhatsApp"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(
                f"{WHATSAPP_BOT_URL}/send-notification",
                json={
                    "customerName": order.get("customer_name", "Cliente"),
                    "payerName": analysis.get("payer_name", "Desconhecido"),
                    "amount": order.get("total", 0),
                    "store": store,
                    "time": analysis.get("transaction_time", datetime.now().strftime("%H:%M")),
                    "date": datetime.now().strftime("%d/%m/%Y"),
                    "orderNumber": order.get("order_number", order.get("id", "")[:8]),
                    "items": order.get("items", []),
                    "autoApproved": auto_approved,
                    "proofImage": order.get("pix_proof")
                }
            )
            logger.info(f"📱 Notificação WhatsApp enviada para pedido {order.get('id')}")
    except Exception as e:
        logger.error(f"Erro ao enviar notificação WhatsApp: {e}")

async def process_order(order: dict, store: str):
    """Processa um pedido PIX pendente"""
    order_id = order.get("id")
    
    # Verificar se já foi processado
    if order_id in processed_orders:
        return
    
    # Verificar se tem comprovante e não tem análise
    if not order.get("pix_proof"):
        return
    
    if order.get("pix_analysis"):
        processed_orders.add(order_id)
        return
    
    logger.info(f"🔍 Processando pedido {order_id} de {order.get('customer_name')} - {store}")
    
    # Marcar como em processamento
    processed_orders.add(order_id)
    
    # Verificar com IA
    result = await verify_pix_with_ai(order, store)
    
    if result.get("success"):
        analysis = result.get("analysis", {})
        auto_approved = result.get("auto_approved", False)
        
        # Atualizar no deploy
        await update_order_in_deploy(order_id, store, analysis, auto_approved)
        
        # Enviar notificação WhatsApp
        await send_whatsapp_notification(order, store, analysis, auto_approved)
    else:
        logger.error(f"❌ Falha na verificação do pedido {order_id}: {result.get('error')}")
        # Remover do processados para tentar novamente
        processed_orders.discard(order_id)

async def poll_orders():
    """Loop principal de polling"""
    logger.info("🚀 Iniciando serviço de sincronização Deploy ↔ Preview")
    logger.info(f"📍 Deploy URL: {DEPLOY_URL}")
    logger.info(f"📍 Preview URL: {PREVIEW_URL}")
    logger.info(f"📍 WhatsApp Bot: {WHATSAPP_BOT_URL}")
    
    while True:
        try:
            for store in STORES:
                orders = await get_pending_pix_orders(store)
                for order in orders:
                    await process_order(order, store)
        except Exception as e:
            logger.error(f"Erro no loop de polling: {e}")
        
        await asyncio.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    asyncio.run(poll_orders())
