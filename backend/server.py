from fastapi import FastAPI, APIRouter, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
import uuid
import re
from datetime import datetime, timezone, timedelta
from enum import Enum
import secrets
import httpx
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import resend

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Green API Configuration (Cloud WhatsApp)
GREEN_API_URL = os.environ.get("GREEN_API_URL", "https://7107.api.greenapi.com")
GREEN_API_INSTANCE = os.environ.get("GREEN_API_INSTANCE", "7107550497")
GREEN_API_TOKEN = os.environ.get("GREEN_API_TOKEN", "ddbec57064a544909aecfbebe1e4d95faa1677ff39b04f68b2")
WHATSAPP_GROUP_ID = os.environ.get("WHATSAPP_GROUP_ID", "120363424613813278@g.us")  # GYM Londres
WHATSAPP_GROUP_RUNNER = os.environ.get("WHATSAPP_GROUP_RUNNER", "5511974449533-1572969909@g.us")  # Runner

# Map stores to their WhatsApp groups
STORE_WHATSAPP_GROUPS = {
    "runner": WHATSAPP_GROUP_RUNNER,
    "gym-londres": WHATSAPP_GROUP_ID
}

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# Security
security = HTTPBasic()

# ==================== GREEN API HELPER FUNCTIONS ====================
def get_green_api_url(method: str) -> str:
    """Build the Green API URL for a specific method"""
    return f"{GREEN_API_URL}/waInstance{GREEN_API_INSTANCE}/{method}/{GREEN_API_TOKEN}"

async def send_whatsapp_message(message: str, group_id: str = None) -> dict:
    """Send a text message via Green API"""
    target = group_id or WHATSAPP_GROUP_ID
    try:
        async with httpx.AsyncClient(timeout=15.0) as client_http:
            response = await client_http.post(
                get_green_api_url("sendMessage"),
                json={
                    "chatId": target,
                    "message": message
                }
            )
            data = response.json()
            return {"success": True, "data": data}
    except Exception as e:
        logging.error(f"Error sending WhatsApp message: {e}")
        return {"success": False, "error": str(e)}

async def send_whatsapp_notification(
    customer_name: str,
    payer_name: str,
    amount: float,
    store: str,
    time: str,
    date: str,
    order_number: str,
    items: list,
    auto_approved: bool = False,
    group_id: str = None,
    pix_proof_image: str = None,
    order_id: str = None
) -> dict:
    """Send PIX payment notification to WhatsApp group via Green API - ONLY if approved"""
    
    # Only send notification if auto_approved
    if not auto_approved:
        return {"success": False, "reason": "Not auto-approved, notification not sent"}
    
    # Check if already notified (prevent duplicates)
    if order_id:
        existing = await db.orders.find_one({"id": order_id, "whatsapp_notified": True})
        if existing:
            logger.info(f"WhatsApp already sent for order {order_id}, skipping duplicate")
            return {"success": False, "reason": "Already notified"}
    
    # Select the correct group based on store (Runner or GYM Londres)
    # IMPORTANT: Use exact store value to select group
    logger.info(f"WhatsApp notification for store: '{store}' - Groups mapping: {STORE_WHATSAPP_GROUPS}")
    
    if store == "runner":
        target = WHATSAPP_GROUP_RUNNER
        logger.info(f"Using RUNNER group: {target}")
    elif store == "gym-londres":
        target = WHATSAPP_GROUP_ID
        logger.info(f"Using GYM LONDRES group: {target}")
    else:
        target = group_id or WHATSAPP_GROUP_ID
        logger.warning(f"Unknown store '{store}', using default group: {target}")
    
    store_emoji = "🏃" if store == "runner" else "🏋️"
    store_name = "Runner" if store == "runner" else "GYM Londres"
    
    items_text = "\n".join([f"  • {item.get('quantity', 1)}x {item.get('name', 'Item')}" for item in items[:5]])
    if len(items) > 5:
        items_text += f"\n  ... +{len(items) - 5} itens"
    
    message = f"""{store_emoji} *NOVO PEDIDO PIX - {store_name}*

👤 *Cliente:* {customer_name}
💳 *Pagador:* {payer_name}
💰 *Valor:* R$ {amount:.2f}
🕐 *Horário:* {time}
📅 *Data:* {date}
🔢 *Pedido:* #{order_number}

📦 *Itens:*
{items_text}

✅ APROVADO AUTOMATICAMENTE"""
    
    result = None
    
    # If we have a PIX proof image, send it with the message
    if pix_proof_image and pix_proof_image.startswith("data:"):
        try:
            # Extract base64 from data URL
            image_data = pix_proof_image.split(",")[1] if "," in pix_proof_image else pix_proof_image
            
            # Send image with caption via Green API
            async with httpx.AsyncClient(timeout=30.0) as client_http:
                response = await client_http.post(
                    get_green_api_url("sendFileByUpload"),
                    data={
                        "chatId": target,
                        "caption": message
                    },
                    files={
                        "file": ("comprovante.jpg", __import__('base64').b64decode(image_data), "image/jpeg")
                    }
                )
                if response.status_code == 200:
                    result = {"success": True, "data": response.json(), "with_image": True}
        except Exception as e:
            logging.warning(f"Could not send image, sending text only: {e}")
    
    # Fallback: send text message only
    if not result:
        result = await send_whatsapp_message(message, target)
    
    # Mark as notified to prevent duplicates
    if result.get("success") and order_id:
        await db.orders.update_one(
            {"id": order_id},
            {"$set": {"whatsapp_notified": True, "whatsapp_notified_at": datetime.now(timezone.utc).isoformat()}}
        )
        logger.info(f"Marked order {order_id} as WhatsApp notified")
    
    return result

# ==================== MULTI-TENANT SYSTEM ====================
# Maximum 2 accounts allowed
MAX_ACCOUNTS = 2

class TenantCreate(BaseModel):
    username: str
    password: str
    display_name: str = ""

class TenantLogin(BaseModel):
    username: str
    password: str

class TenantResponse(BaseModel):
    id: str
    username: str
    display_name: str
    created_at: str

async def get_tenant_by_credentials(username: str, password: str):
    """Get tenant by username and password"""
    import hashlib
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    tenant = await db.tenants.find_one({
        "username": username,
        "password_hash": password_hash
    })
    return tenant

async def get_tenant_by_id(tenant_id: str):
    """Get tenant by ID"""
    return await db.tenants.find_one({"id": tenant_id})

async def ensure_default_tenant():
    """Create default Gestor tenant if it doesn't exist"""
    import hashlib
    existing = await db.tenants.find_one({"username": "gestor"})
    # Allow override via env, otherwise use a strong default
    default_password = os.environ.get('GESTOR_PASSWORD', 'Gan0h#G3st0r@2026')
    if not existing:
        password_hash = hashlib.sha256(default_password.encode()).hexdigest()
        await db.tenants.insert_one({
            "id": "tenant_gestor",
            "username": "gestor",
            "password_hash": password_hash,
            "display_name": "GANOH Café Bistrô",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "is_default": True
        })
        logging.info("Default tenant 'gestor' created")
    else:
        # Always sync the default tenant's password to the configured default,
        # so previously seeded weak passwords are auto-rotated on startup.
        new_hash = hashlib.sha256(default_password.encode()).hexdigest()
        if existing.get("password_hash") != new_hash:
            await db.tenants.update_one(
                {"username": "gestor"},
                {"$set": {"password_hash": new_hash}}
            )
            logging.info("Default tenant 'gestor' password rotated to configured value")

# Legacy support - will be replaced by tenant system
GESTOR_USERNAME = os.environ.get('GESTOR_USERNAME', 'gestor')
GESTOR_PASSWORD = os.environ.get('GESTOR_PASSWORD', 'Gan0h#G3st0r@2026')

def verify_gestor(credentials: HTTPBasicCredentials = Depends(security)):
    # Trim whitespace and lowercase username to fix intermittent login bugs
    # (common on mobile keyboards that add space or capitalize first letter)
    incoming_user = (credentials.username or "").strip().lower()
    incoming_pass = (credentials.password or "").strip()
    expected_user = (GESTOR_USERNAME or "").strip().lower()
    expected_pass = (GESTOR_PASSWORD or "").strip()
    correct_username = secrets.compare_digest(incoming_user, expected_user)
    correct_password = secrets.compare_digest(incoming_pass, expected_pass)
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# Enums
class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"  # Waiting for PIX proof
    PAYMENT_REJECTED = "payment_rejected"  # PIX rejected
    RECEIVED = "received"
    PREPARING = "preparing"
    READY = "ready"
    DELIVERED = "delivered"

class PaymentMethod(str, Enum):
    PIX = "pix"
    DEBIT = "debit"
    CREDIT = "credit"
    CASH = "cash"
    PRAZO = "prazo"  # Credit/Tab - pay later
    VOUCHER = "voucher"  # Meal voucher (VR, VA, etc)

# PIX Configuration (same for both stores)
PIX_CONFIG = {
    "key": "",  # Will be set by store owner
    "key_type": "cpf",  # cpf, cnpj, email, phone, random
    "beneficiary_name": "GANOH Café Bistrô",
    "city": "São Paulo"
}

class StoreLocation(str, Enum):
    RUNNER = "runner"
    GYM_LONDRES = "gym-londres"

# Models
class MenuItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str
    price: float
    category: str
    store: Optional[str] = None  # Store location (runner, gym-londres, or all)
    prep_time: int = 15
    available: bool = True
    # Fiscal fields for NF-e (Nota Fiscal)
    codigo: Optional[str] = None  # Product code
    codigo_externo: Optional[str] = None  # External code
    unidade: str = "UN"  # UN, KG, LT
    valor_custo: float = 0.0  # Cost value
    codigo_barras: Optional[str] = None  # Barcode
    grupo: Optional[str] = None  # Product group
    # Fiscal/Tax fields
    ncm: Optional[str] = None  # NCM code (Nomenclatura Comum do Mercosul)
    cst: Optional[str] = None  # CST (Código de Situação Tributária)
    csosn: Optional[str] = None  # CSOSN (Código de Situação da Operação - Simples Nacional)
    cfop: Optional[str] = None  # CFOP (Código Fiscal de Operações e Prestações)
    cest: Optional[str] = None  # CEST (Código Especificador da Substituição Tributária)
    icms_aliquota: Optional[float] = None  # ICMS rate
    icms_tipo: Optional[str] = None  # isento, substituicao, nao_incidencia, or percentage
    pis_cst: Optional[str] = None  # PIS CST
    pis_aliquota: Optional[float] = None  # PIS rate
    cofins_cst: Optional[str] = None  # COFINS CST
    cofins_aliquota: Optional[float] = None  # COFINS rate
    estoque_minimo: float = 0.0  # Minimum stock
    estoque_producao: bool = False  # Production stock

class StockItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    menu_item_id: str
    store: StoreLocation
    quantity: int = 0
    min_quantity: int = 5  # Alert when below this
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class StockUpdate(BaseModel):
    quantity: int

class OrderItem(BaseModel):
    menu_item_id: str
    name: str
    price: float
    quantity: int

class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    store: StoreLocation
    customer_name: str
    items: List[OrderItem]
    total: float
    payment_method: PaymentMethod
    status: OrderStatus = OrderStatus.RECEIVED
    prep_time: int = 15
    pickup_time: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    synced: bool = True  # For offline support

class OrderCreate(BaseModel):
    store: StoreLocation
    customer_name: str
    items: List[OrderItem]
    total: float
    payment_method: PaymentMethod
    pickup_time: Optional[str] = None
    offline_id: Optional[str] = None  # For offline sync
    pix_proof: Optional[str] = None  # Base64 image of PIX proof

class OrderStatusUpdate(BaseModel):
    status: OrderStatus

class PixProofUpload(BaseModel):
    proof_image: str  # Base64 encoded image

class PaymentApproval(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None

class SalesReport(BaseModel):
    total_sales: float
    order_count: int
    by_payment_method: dict
    top_products: List[dict]
    low_products: List[dict]

class CashWithdrawal(BaseModel):
    amount: float
    category: str  # "vt" (vale transporte) or "outros"
    description: Optional[str] = None

class CashWithdrawalResponse(BaseModel):
    id: str
    store: str
    amount: float
    category: str
    description: str
    created_at: str

# Menu Data - GANOH Café Bistrô (same for both stores)
MENU_DATA = [
    # Omeletes, Tapiocas e Crepiocas
    {"id": "1", "name": "Frango com Requeijão", "description": "Omelete/Tapioca com frango desfiado e requeijão cremoso", "price": 25.50, "category": "Omeletes, Tapiocas e Crepiocas", "prep_time": 15},
    {"id": "2", "name": "Frango, Mussarela, Tomate e Orégano", "description": "Combinação clássica com frango, queijo mussarela, tomate fresco e orégano", "price": 26.00, "category": "Omeletes, Tapiocas e Crepiocas", "prep_time": 15},
    {"id": "3", "name": "Queijo Branco, Tomate e Orégano", "description": "Opção leve com queijo branco, tomate e orégano", "price": 23.50, "category": "Omeletes, Tapiocas e Crepiocas", "prep_time": 15},
    {"id": "4", "name": "Queijo Branco, Peito de Peru e Orégano", "description": "Queijo branco com peito de peru e orégano", "price": 24.00, "category": "Omeletes, Tapiocas e Crepiocas", "prep_time": 15},
    {"id": "5", "name": "Mussarela, Peito de Peru, Tomate e Orégano", "description": "Mussarela derretida com peito de peru, tomate e orégano", "price": 23.50, "category": "Omeletes, Tapiocas e Crepiocas", "prep_time": 15},
    {"id": "6", "name": "Atum com Requeijão", "description": "Atum em lascas com requeijão cremoso", "price": 26.50, "category": "Omeletes, Tapiocas e Crepiocas", "prep_time": 15},
    {"id": "7", "name": "Atum, Mussarela e Tomate", "description": "Atum com mussarela e tomate fresco", "price": 26.50, "category": "Omeletes, Tapiocas e Crepiocas", "prep_time": 15},
    {"id": "8", "name": "Especial", "description": "Frango, mussarela, peito de peru, tomate e orégano - nossa combinação mais completa", "price": 27.50, "category": "Omeletes, Tapiocas e Crepiocas", "prep_time": 15},
    
    # Brunchs
    {"id": "9", "name": "Saudável", "description": "3 ovos mexidos, pão integral, café, fruta (mamão ou banana), aveia e mel", "price": 21.00, "category": "Brunchs", "prep_time": 15},
    {"id": "10", "name": "Café Egg", "description": "2 ovos mexidos, café pequeno e pão integral", "price": 19.00, "category": "Brunchs", "prep_time": 15},
    {"id": "11", "name": "Mineirinho", "description": "2 ovos fritos, queijo minas, duas fatias de pão integral e café com leite", "price": 23.00, "category": "Brunchs", "prep_time": 15},
    {"id": "12", "name": "Honey", "description": "2 ovos mexidos, banana, granola e mel", "price": 18.00, "category": "Brunchs", "prep_time": 15},
    {"id": "13", "name": "Banana Bliss", "description": "Banana, aveia, canela e mel", "price": 10.00, "category": "Brunchs", "prep_time": 15},
    {"id": "14", "name": "Banana Power", "description": "Banana, proteína, aveia, canela e mel", "price": 15.00, "category": "Brunchs", "prep_time": 15},
    {"id": "15", "name": "Pão de Queijo", "description": "Tradicional pão de queijo mineiro quentinho", "price": 8.00, "category": "Brunchs", "prep_time": 15},
    {"id": "16", "name": "Salgado", "description": "Salgado assado do dia", "price": 9.00, "category": "Brunchs", "prep_time": 15},
    
    # Toasts
    {"id": "17", "name": "Pão com Ovos", "description": "Pão integral, requeijão, ovos, mussarela e tomate", "price": 15.00, "category": "Toasts", "prep_time": 15},
    {"id": "18", "name": "Queijo Quente", "description": "Pão integral, mussarela, orégano e tomate", "price": 14.00, "category": "Toasts", "prep_time": 15},
    {"id": "19", "name": "Peito de Peru", "description": "Requeijão, peito de peru, mussarela, tomate e orégano", "price": 15.00, "category": "Toasts", "prep_time": 15},
    {"id": "20", "name": "Queijo Branco", "description": "Requeijão, queijo branco, tomate e orégano", "price": 16.00, "category": "Toasts", "prep_time": 15},
    {"id": "21", "name": "Queijo Branco e Peito de Peru", "description": "Requeijão, peito de peru, queijo branco, tomate e orégano", "price": 17.00, "category": "Toasts", "prep_time": 15},
    {"id": "22", "name": "Proteico Frango", "description": "Requeijão, frango, mussarela, tomate e orégano", "price": 18.00, "category": "Toasts", "prep_time": 15},
    {"id": "23", "name": "Proteico Atum", "description": "Requeijão, atum, mussarela, tomate e orégano", "price": 19.00, "category": "Toasts", "prep_time": 15},
    
    # Shakes Proteicos
    {"id": "24", "name": "Whey Morango com Água e Banana", "description": "Shake de whey sabor morango com água e banana", "price": 19.00, "category": "Shakes Proteicos", "prep_time": 15},
    {"id": "25", "name": "Whey Baunilha, Água, Mamão e Aveia", "description": "Shake de whey baunilha com mamão e aveia", "price": 23.00, "category": "Shakes Proteicos", "prep_time": 15},
    {"id": "26", "name": "Whey Baunilha, Água, Abacaxi e Mel", "description": "Shake de whey baunilha com abacaxi e mel", "price": 23.00, "category": "Shakes Proteicos", "prep_time": 15},
    {"id": "27", "name": "Whey Chocolate, Água, Banana e Paçoca", "description": "Shake de whey chocolate com banana e paçoca", "price": 22.00, "category": "Shakes Proteicos", "prep_time": 15},
    {"id": "28", "name": "Whey Morango, Leite e Banana", "description": "Shake cremoso de whey morango com leite e banana", "price": 22.00, "category": "Shakes Proteicos", "prep_time": 15},
    {"id": "29", "name": "Whey Baunilha, Leite, Banana e Mamão", "description": "Shake de whey baunilha com leite, banana e mamão", "price": 24.00, "category": "Shakes Proteicos", "prep_time": 15},
    {"id": "30", "name": "Whey Chocolate, Leite e Morango", "description": "Shake de whey chocolate com leite e morango", "price": 22.00, "category": "Shakes Proteicos", "prep_time": 15},
    {"id": "31", "name": "Whey Baunilha, Açaí, Morango e Banana", "description": "Shake especial com açaí, morango e banana", "price": 26.00, "category": "Shakes Proteicos", "prep_time": 15},
    
    # Açaí
    {"id": "32", "name": "Açaí Batido com Água", "description": "Açaí puro batido com água", "price": 16.00, "category": "Açaí", "prep_time": 15},
    {"id": "33", "name": "Açaí Batido com Leite", "description": "Açaí cremoso batido com leite", "price": 18.00, "category": "Açaí", "prep_time": 15},
    {"id": "34", "name": "Açaí Batido com Laranja", "description": "Açaí refrescante batido com suco de laranja", "price": 19.00, "category": "Açaí", "prep_time": 15},
    {"id": "35", "name": "Açaí Batido com Leite, Banana e Morango", "description": "Açaí cremoso com leite, banana e morango", "price": 21.00, "category": "Açaí", "prep_time": 15},
    {"id": "36", "name": "Açaí na Tigela 500ml", "description": "1 fruta + 3 adicionais (aveia, mel, granola, leite em pó ou leite condensado)", "price": 22.00, "category": "Açaí", "prep_time": 15},
    
    # Sucos e Vitaminas
    {"id": "37", "name": "Suco Natural de Laranja", "description": "Suco de laranja 100% natural", "price": 15.00, "category": "Sucos e Vitaminas", "prep_time": 15},
    {"id": "38", "name": "Suco Natural de Abacaxi", "description": "Suco de abacaxi fresco", "price": 14.00, "category": "Sucos e Vitaminas", "prep_time": 15},
    {"id": "39", "name": "Suco Natural de Manga", "description": "Suco de manga natural", "price": 14.00, "category": "Sucos e Vitaminas", "prep_time": 15},
    {"id": "40", "name": "Suco Natural de Morango e Laranja", "description": "Mix refrescante de morango com laranja", "price": 16.00, "category": "Sucos e Vitaminas", "prep_time": 15},
    {"id": "41", "name": "Suco Natural de Maracujá com Manga", "description": "Combinação tropical de maracujá com manga", "price": 16.00, "category": "Sucos e Vitaminas", "prep_time": 15},
    {"id": "42", "name": "Suco Detox", "description": "Abacaxi, hortelã, couve, gengibre e maçã", "price": 15.00, "category": "Sucos e Vitaminas", "prep_time": 15},
    {"id": "43", "name": "Vitamina com Uma Fruta", "description": "Vitamina cremosa com a fruta de sua escolha", "price": 15.00, "category": "Sucos e Vitaminas", "prep_time": 15},
    {"id": "44", "name": "Vitamina com Duas Frutas", "description": "Vitamina cremosa com duas frutas de sua escolha", "price": 18.00, "category": "Sucos e Vitaminas", "prep_time": 15},
    
    # Saladas
    {"id": "45", "name": "Salada de Frutas", "description": "Mix de frutas frescas do dia", "price": 14.00, "category": "Saladas", "prep_time": 15},
    {"id": "46", "name": "Salada Simples", "description": "Alface, tomate e cenoura - acompanhamento perfeito", "price": 7.00, "category": "Saladas", "prep_time": 15},
    {"id": "47", "name": "Salada Ganoh", "description": "Alface, tomate, cenoura, queijo branco, frango ou atum, molho da casa e torradinhas", "price": 19.00, "category": "Saladas", "prep_time": 15},
    
    # Bebidas Quentes
    {"id": "48", "name": "Café Pequeno", "description": "Café coado tradicional", "price": 4.50, "category": "Bebidas Quentes", "prep_time": 15},
    {"id": "49", "name": "Café Grande", "description": "Café coado em porção generosa", "price": 6.00, "category": "Bebidas Quentes", "prep_time": 15},
    {"id": "50", "name": "Café com Leite", "description": "Café coado com leite vaporizado", "price": 7.00, "category": "Bebidas Quentes", "prep_time": 15},
    {"id": "51", "name": "Expresso", "description": "Café expresso encorpado", "price": 8.00, "category": "Bebidas Quentes", "prep_time": 15},
    {"id": "52", "name": "Chá", "description": "Chá quente - consulte sabores disponíveis", "price": 6.00, "category": "Bebidas Quentes", "prep_time": 15},
    {"id": "53", "name": "Capuccino / Mocaccino", "description": "Bebida cremosa com espuma de leite", "price": 9.00, "category": "Bebidas Quentes", "prep_time": 15},
    {"id": "54", "name": "Chocolate Quente", "description": "Chocolate cremoso e reconfortante", "price": 9.00, "category": "Bebidas Quentes", "prep_time": 15},
    
    # Bebidas Geladas
    {"id": "55", "name": "Água Pequena", "description": "Água mineral 300ml", "price": 5.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "56", "name": "Água Grande", "description": "Água mineral 500ml", "price": 8.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "57", "name": "H2O", "description": "Água saborizada", "price": 8.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "58", "name": "Gatorade", "description": "Isotônico para reposição", "price": 9.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "59", "name": "Energético Red Bull", "description": "Bebida energética", "price": 15.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "60", "name": "Energético Monster", "description": "Bebida energética", "price": 15.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "61", "name": "Mupy", "description": "Bebida láctea infantil", "price": 6.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "62", "name": "Kapo", "description": "Suco de caixinha", "price": 6.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "63", "name": "Toddynho", "description": "Achocolatado", "price": 6.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "64", "name": "Água de Coco Grande", "description": "Água de coco natural 500ml", "price": 8.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "65", "name": "Água de Coco Pequena", "description": "Água de coco natural 300ml", "price": 6.00, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "66", "name": "Coca-Cola Mini", "description": "Coca-Cola 200ml", "price": 3.50, "category": "Bebidas Geladas", "prep_time": 15},
    {"id": "67", "name": "Coca-Cola Lata", "description": "Coca-Cola 350ml", "price": 6.60, "category": "Bebidas Geladas", "prep_time": 15},
    
    # Suplementos
    {"id": "68", "name": "Creatina (1 dose)", "description": "Dose de creatina monohidratada", "price": 8.00, "category": "Suplementos", "prep_time": 15},
    {"id": "69", "name": "Pré Treino (1 dose)", "description": "Dose de pré-treino para energia", "price": 9.00, "category": "Suplementos", "prep_time": 15},
    {"id": "70", "name": "Dose de Whey (2 scoops)", "description": "Proteína whey isolada", "price": 13.00, "category": "Suplementos", "prep_time": 15},
    {"id": "71", "name": "Carb Up", "description": "Carboidrato de rápida absorção", "price": 9.00, "category": "Suplementos", "prep_time": 15},
]

CATEGORIES = [
    "Omeletes, Tapiocas e Crepiocas",
    "Brunchs",
    "Toasts",
    "Shakes Proteicos",
    "Açaí",
    "Sucos e Vitaminas",
    "Saladas",
    "Bebidas Quentes",
    "Bebidas Geladas",
    "Suplementos",
    "Doces",
    "Pão Doce"
]

ADICIONAIS = [
    {"id": "72", "name": "Ovos", "price": 3.50},
    {"id": "73", "name": "Atum", "price": 7.00},
    {"id": "74", "name": "Queijo Branco", "price": 8.00},
    {"id": "75", "name": "Mussarela", "price": 3.00},
    {"id": "76", "name": "Frango", "price": 7.00},
    {"id": "77", "name": "Mel", "price": 3.50},
    {"id": "78", "name": "Granola", "price": 3.50},
    {"id": "79", "name": "Nutella", "price": 5.00},
]

# Opções de tipo de leite (sem custo adicional)
MILK_OPTIONS = [
    {"id": "milk_integral", "name": "Integral", "price": 0},
    {"id": "milk_desnatado", "name": "Desnatado", "price": 0},
    {"id": "milk_semi", "name": "Semi Desnatado", "price": 0},
    {"id": "milk_zero", "name": "Zero Lactose", "price": 0},
]

STORES = {
    "runner": {"name": "GANOH Café Bistrô - Runner", "address": "Runner"},
    "gym-londres": {"name": "GANOH Café Bistrô - GYM Londres", "address": "GYM Londres"}
}

# ==================== MENU ROUTES ====================

@api_router.get("/")
async def root():
    return {"message": "GANOH Café Bistrô API"}

# ==================== TENANT AUTH ROUTES ====================

@api_router.post("/auth/register")
async def register_tenant(tenant: TenantCreate):
    """Register a new tenant account (max 2 accounts)"""
    import hashlib
    
    # Check max accounts
    count = await db.tenants.count_documents({})
    if count >= MAX_ACCOUNTS:
        raise HTTPException(status_code=400, detail=f"Limite máximo de {MAX_ACCOUNTS} contas atingido")
    
    # Check if username exists
    existing = await db.tenants.find_one({"username": tenant.username.lower()})
    if existing:
        raise HTTPException(status_code=400, detail="Nome de usuário já existe")
    
    # Create tenant
    password_hash = hashlib.sha256(tenant.password.encode()).hexdigest()
    tenant_id = f"tenant_{str(uuid.uuid4())[:8]}"
    
    await db.tenants.insert_one({
        "id": tenant_id,
        "username": tenant.username.lower(),
        "password_hash": password_hash,
        "display_name": tenant.display_name or tenant.username,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_default": False
    })
    
    return {
        "success": True,
        "tenant_id": tenant_id,
        "username": tenant.username.lower(),
        "message": "Conta criada com sucesso!"
    }

@api_router.post("/auth/login")
async def login_tenant(credentials: TenantLogin):
    """Login with tenant credentials"""
    # Trim whitespace from username and password to handle mobile keyboard issues
    clean_username = (credentials.username or "").strip().lower()
    clean_password = (credentials.password or "").strip()
    tenant = await get_tenant_by_credentials(clean_username, clean_password)
    if not tenant:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    return {
        "success": True,
        "tenant_id": tenant["id"],
        "username": tenant["username"],
        "display_name": tenant.get("display_name", tenant["username"]),
        "message": "Login realizado com sucesso!"
    }

@api_router.get("/auth/accounts")
async def list_accounts():
    """Return only account count and creation status - no usernames/display names
    exposed publicly to prevent user enumeration."""
    count = await db.tenants.count_documents({})
    return {
        "accounts": [],  # Never expose account details publicly
        "count": count,
        "max_accounts": MAX_ACCOUNTS,
        "can_create": count < MAX_ACCOUNTS
    }

@api_router.get("/auth/check/{tenant_id}")
async def check_tenant(tenant_id: str):
    """Check if tenant exists"""
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    return {
        "exists": True,
        "username": tenant["username"],
        "display_name": tenant.get("display_name", tenant["username"])
    }

@api_router.get("/stores")
async def get_stores():
    return {"stores": STORES}

@api_router.get("/categories")
async def get_categories():
    """Return all menu categories"""
    return {"categories": CATEGORIES}

def _normalize_category(cat: str) -> str:
    """Normalize a category string: trim, fix common variants, title-case.
    Used to consolidate duplicates like 'bebidas'/'Bebidas Geladas', 'doces'/'Doces',
    'cafes' etc. into a single canonical name.
    """
    if not cat:
        return ""
    c = str(cat).strip()
    if not c:
        return ""
    low = c.lower()
    # Match against canonical CATEGORIES list (case-insensitive) first.
    for canonical in CATEGORIES:
        if canonical.lower() == low:
            return canonical
    # Known canonical mappings (lowercase → canonical)
    canonical_map = {
        "bebidas": "Bebidas Geladas",
        "bebidas geladas": "Bebidas Geladas",
        "bebidas quentes": "Bebidas Quentes",
        "doces": "Doces",
        "cafes": "Bebidas Quentes",
        "cafés": "Bebidas Quentes",
        "outros": "Outros",
    }
    if low in canonical_map:
        return canonical_map[low]
    # Title case fallback that preserves Portuguese connectors (e, de, da, do, etc.)
    connectors = {"e", "de", "da", "do", "das", "dos", "a", "o", "com", "ou"}
    words = c.split()
    out = []
    for i, w in enumerate(words):
        wl = w.lower()
        if i > 0 and wl in connectors:
            out.append(wl)
        elif w.isupper() and len(w) > 1:
            out.append(w)  # keep acronyms uppercase
        else:
            out.append(w[:1].upper() + w[1:].lower())
    return " ".join(out)

def _normalize_name(name: str) -> str:
    """Normalize product/adicional name for case/whitespace dedup."""
    return (name or "").strip().lower()

# Test-data / promotional items that should be hidden from the public menu
# Only filter by explicit name tokens. Do NOT filter by price - small items like
# candies (chiclete R$0.50) are legitimate products.
TEST_ITEM_NAME_TOKENS = ("placeholder",)

def _is_test_item(item: dict) -> bool:
    """Identify likely test/placeholder items so they can be hidden in production.
    Conservative: matches only explicit name tokens. Low-price legitimate items
    (e.g. candies) must remain visible.
    """
    name_low = (item.get("name") or "").lower()
    if any(tok in name_low for tok in TEST_ITEM_NAME_TOKENS):
        return True
    return False

@api_router.get("/menu/{store}")
async def get_menu(store: StoreLocation):
    # Get stock for bebidas only (other items don't need stock control)
    stock_docs = await db.stock.find({"store": store.value}, {"_id": 0}).to_list(1000)
    stock_map = {s["menu_item_id"]: s["quantity"] for s in stock_docs}
    
    # Get custom menu items added by gestor for this store
    custom_items = await db.menu.find({
        "$or": [
            {"store": store.value},
            {"store": "all"},
            {"store": {"$exists": False}}  # Items without store filter apply to all
        ]
    }, {"_id": 0}).to_list(1000)
    
    # Add availability based on stock (only for bebidas)
    items_with_stock = []
    seen_ids = set()
    seen_names = {}  # normalized name -> index in items_with_stock (dedup)
    
    # First add default menu items
    for item in MENU_DATA:
        item_copy = item.copy()
        # Normalize the category
        item_copy["category"] = _normalize_category(item_copy.get("category", ""))
        if item["category"] in STOCK_CATEGORIES:
            stock_qty = stock_map.get(item["id"], 0)
            item_copy["stock"] = stock_qty
            # Items are ALWAYS available - stock is just for information
            item_copy["available"] = True
        else:
            # Non-beverage items are always available
            item_copy["stock"] = None
            item_copy["available"] = True
        items_with_stock.append(item_copy)
        seen_ids.add(item["id"])
        seen_names[_normalize_name(item_copy["name"])] = len(items_with_stock) - 1
    
    # Then add custom items from gestor (avoid duplicates by id AND by normalized name)
    for custom_item in custom_items:
        if custom_item.get("id") in seen_ids:
            continue
        item_copy = custom_item.copy()
        # Normalize the category
        item_copy["category"] = _normalize_category(item_copy.get("category", ""))
        norm_name = _normalize_name(item_copy.get("name", ""))
        # Skip duplicate by normalized name (e.g., "Coca-Cola Lata" vs "coca lata normal")
        if norm_name and norm_name in seen_names:
            continue
        # Skip test/placeholder items in production (price < R$1, "PROMOÇÃO" etc.)
        if _is_test_item(item_copy):
            continue
        # Check if this category needs stock control
        if custom_item.get("category") in STOCK_CATEGORIES:
            stock_qty = stock_map.get(custom_item.get("id"), 0)
            item_copy["stock"] = stock_qty
            # Items are ALWAYS available - stock is just for information
            item_copy["available"] = True
        else:
            item_copy["stock"] = None
            item_copy["available"] = True
        items_with_stock.append(item_copy)
        seen_ids.add(custom_item.get("id"))
        if norm_name:
            seen_names[norm_name] = len(items_with_stock) - 1
    
    # Build category list from items actually present (preserves canonical order)
    # Dedupe case-insensitively to avoid 'Bebidas Geladas' vs 'bebidas geladas'.
    all_categories = []
    seen_cats_lower = set()
    for cat in CATEGORIES:
        low = cat.lower()
        if low not in seen_cats_lower:
            seen_cats_lower.add(low)
            all_categories.append(cat)
    for it in items_with_stock:
        cat = it.get("category")
        if cat:
            low = cat.lower()
            if low not in seen_cats_lower:
                seen_cats_lower.add(low)
                all_categories.append(cat)
    
    # Get adicionais from database (merged with defaults, deduplicated by normalized name)
    custom_adicionais = await db.adicionais.find({}, {"_id": 0}).to_list(100)
    merged_adicionais = []
    seen_adicional_names = {}
    for source in (ADICIONAIS, custom_adicionais):
        for a in source:
            norm = _normalize_name(a.get("name", ""))
            if not norm:
                continue
            # Standardize known typos
            if norm in ("2 fruta", "duas fruta"):
                a = {**a, "name": "2 Frutas"}
                norm = "2 frutas"
            if norm in seen_adicional_names:
                # Overwrite earlier entry with the more recent / db version
                merged_adicionais[seen_adicional_names[norm]] = a
            else:
                seen_adicional_names[norm] = len(merged_adicionais)
                merged_adicionais.append(a)
    
    return {
        "items": items_with_stock,
        "categories": all_categories,
        "adicionais": merged_adicionais,
        "milk_options": MILK_OPTIONS,
        "store": STORES.get(store.value)
    }

# ==================== ORDER ROUTES ====================

@api_router.post("/orders")
async def create_order(order_input: OrderCreate):
    # Check stock availability
    for item in order_input.items:
        stock = await db.stock.find_one({
            "menu_item_id": item.menu_item_id.split("-")[0],  # Handle adicionais
            "store": order_input.store.value
        })
        # Only check stock if item has a POSITIVE stock record
        # If stock is 0 or negative, we ignore it (item doesn't have controlled stock)
        if stock and stock.get("quantity", 0) > 0 and stock.get("quantity", 0) < item.quantity:
            raise HTTPException(
                status_code=400, 
                detail=f"Estoque insuficiente para {item.name}"
            )
    
    # Check if customer has credit when using prazo
    credit_used = 0
    previous_credit = 0
    new_credit = 0
    final_total = order_input.total
    is_paid_by_credit = False
    
    if order_input.payment_method == PaymentMethod.PRAZO and order_input.customer_name:
        # Look for customer with credit
        customer = await db.prazo_customers.find_one({
            "name": {"$regex": f"^{re.escape(order_input.customer_name)}$", "$options": "i"}
        })
        
        if customer and customer.get("credit", 0) > 0:
            previous_credit = customer.get("credit", 0)
            
            if previous_credit >= order_input.total:
                # Full payment from credit
                credit_used = order_input.total
                new_credit = previous_credit - credit_used
                is_paid_by_credit = True
            else:
                # Partial payment from credit
                credit_used = previous_credit
                new_credit = 0
                final_total = order_input.total - credit_used
            
            # Update customer credit
            await db.prazo_customers.update_one(
                {"id": customer["id"]},
                {"$set": {"credit": new_credit}}
            )
    
    # Determine initial status based on payment method
    initial_status = OrderStatus.PENDING_PAYMENT if order_input.payment_method == PaymentMethod.PIX else OrderStatus.RECEIVED
    
    # If fully paid by credit, mark as ready
    if is_paid_by_credit:
        initial_status = OrderStatus.RECEIVED
    
    order = Order(
        store=order_input.store,
        customer_name=order_input.customer_name,
        items=order_input.items,
        total=order_input.total,
        payment_method=order_input.payment_method,
        status=initial_status,
        prep_time=15,
        pickup_time=order_input.pickup_time
    )
    
    doc = order.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    doc['store'] = doc['store'].value
    doc['payment_method'] = doc['payment_method'].value
    doc['status'] = doc['status'].value
    
    # Add credit payment info
    if credit_used > 0:
        doc['credit_used'] = credit_used
        doc['previous_credit'] = previous_credit
        doc['new_credit'] = new_credit
        if is_paid_by_credit:
            doc['paid_by_credit'] = True
            doc['prazo_paid'] = True  # Mark as paid since credit covered it
            doc['prazo_paid_at'] = datetime.now(timezone.utc).isoformat()
        else:
            # Partial credit, remaining goes to prazo debt
            doc['partial_paid'] = credit_used
    
    # Add PIX proof if provided
    if order_input.pix_proof:
        doc['pix_proof'] = order_input.pix_proof
    
    await db.orders.insert_one(doc)
    
    # Update stock (only for non-PIX or after PIX approval)
    if order_input.payment_method != PaymentMethod.PIX:
        for item in order_input.items:
            await db.stock.update_one(
                {"menu_item_id": item.menu_item_id.split("-")[0], "store": order_input.store.value},
                {"$inc": {"quantity": -item.quantity}},
                upsert=False
            )
    
    response = {**doc, "_id": None}
    
    # Add credit info to response
    if credit_used > 0:
        response['credit_message'] = f"Crédito usado: R$ {credit_used:.2f} (Saldo: R$ {new_credit:.2f})"
    
    return response

@api_router.post("/orders/sync")
async def sync_offline_orders(orders: List[OrderCreate]):
    """Sync offline orders when connection is restored"""
    synced = []
    for order_input in orders:
        try:
            result = await create_order(order_input)
            synced.append({"offline_id": order_input.offline_id, "synced": True, "order": result})
        except Exception as e:
            synced.append({"offline_id": order_input.offline_id, "synced": False, "error": str(e)})
    return {"synced_orders": synced}

@api_router.get("/orders/{store}")
async def get_orders(store: StoreLocation, status: Optional[str] = None):
    query = {"store": store.value}
    if status:
        query["status"] = status

    # Auto-archive: ready orders older than 12 hours are considered stale and
    # should not pollute the operational kitchen view. They are moved to history
    # so they still appear under "Histórico" but disappear from the live screen.
    if status == "ready":
        stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=12)
        stale_iso = stale_cutoff.isoformat()
        stale_query = {
            "store": store.value,
            "status": "ready",
            "$or": [
                {"updated_at": {"$lt": stale_iso}},
                {"updated_at": {"$exists": False}, "created_at": {"$lt": stale_iso}},
            ],
        }
        stale_orders = await db.orders.find(stale_query).to_list(500)
        for old in stale_orders:
            doc = {k: v for k, v in old.items() if k != "_id"}
            doc["status"] = "delivered"
            doc["delivered_at"] = doc.get("updated_at") or doc.get("created_at") or datetime.now(timezone.utc).isoformat()
            doc["auto_archived"] = True
            try:
                await db.order_history.insert_one(doc)
            except Exception:
                pass
        if stale_orders:
            await db.orders.delete_many({"id": {"$in": [o.get("id") for o in stale_orders if o.get("id")]}})

    orders = await db.orders.find(query, {"_id": 0}).sort("created_at", -1).to_list(100)
    return {"orders": orders}

@api_router.get("/orders/{store}/pending-pix")
async def get_pending_pix_orders(store: StoreLocation):
    """Get orders pending PIX approval"""
    orders = await db.orders.find({
        "store": store.value,
        "payment_method": "pix",
        "status": "pending_payment",
        "pix_proof": {"$exists": True}
    }, {"_id": 0}).sort("created_at", 1).to_list(100)
    
    # Auto-trigger verification for orders that have proof but no analysis (30+ seconds old)
    # Only trigger once per order (check verification_triggered flag)
    for order in orders:
        order_id = order.get("id")
        if order.get("pix_proof") and not order.get("pix_analysis") and not order.get("verification_triggered"):
            proof_at = order.get("pix_proof_at")
            should_verify = False
            
            if proof_at:
                try:
                    proof_time = datetime.fromisoformat(proof_at.replace('Z', '+00:00'))
                    seconds_since = (datetime.now(timezone.utc) - proof_time).total_seconds()
                    # If more than 30 seconds old and no analysis, trigger background verification
                    if seconds_since > 30:
                        should_verify = True
                except Exception:
                    should_verify = True
            else:
                # Legacy order without pix_proof_at - trigger verification
                should_verify = True
            
            if should_verify:
                # Mark as verification triggered to avoid duplicate triggers
                await db.orders.update_one(
                    {"id": order_id},
                    {"$set": {"verification_triggered": True, "verification_triggered_at": datetime.now(timezone.utc).isoformat()}}
                )
                import asyncio
                asyncio.create_task(auto_verify_pix_background(
                    store, 
                    order_id, 
                    order.get("pix_proof"), 
                    order.get("total", 0)
                ))
    
    return {"orders": orders}

@api_router.get("/orders/{store}/history")
async def get_order_history(store: StoreLocation):
    """Get ready and delivered orders from the last 24 hours"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    
    # Get from order_history (delivered orders)
    history_orders = await db.order_history.find({
        "store": store.value,
        "delivered_at": {"$gte": cutoff.isoformat()}
    }, {"_id": 0}).sort("delivered_at", -1).to_list(500)
    
    # Get ready orders from main orders collection
    ready_orders = await db.orders.find({
        "store": store.value,
        "status": "ready",
        "created_at": {"$gte": cutoff.isoformat()}
    }, {"_id": 0}).sort("created_at", -1).to_list(500)
    
    # Combine and sort by most recent
    all_orders = history_orders + ready_orders
    all_orders.sort(key=lambda x: x.get('delivered_at', x.get('updated_at', x.get('created_at', ''))), reverse=True)
    
    return {"orders": all_orders, "count": len(all_orders)}

@api_router.get("/orders/{store}/{order_id}")
async def get_order(store: StoreLocation, order_id: str):
    order = await db.orders.find_one({"id": order_id, "store": store.value}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    return order

@api_router.patch("/orders/{store}/{order_id}/status")
async def update_order_status(store: StoreLocation, order_id: str, status_update: OrderStatusUpdate):
    # Get current order
    order = await db.orders.find_one({"id": order_id, "store": store.value})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    # If moving to delivered, save to history
    if status_update.status == OrderStatus.DELIVERED:
        order_copy = {k: v for k, v in order.items() if k != '_id'}
        order_copy['status'] = 'delivered'
        order_copy['delivered_at'] = datetime.now(timezone.utc).isoformat()
        await db.order_history.insert_one(order_copy)
    
    await db.orders.update_one(
        {"id": order_id, "store": store.value},
        {"$set": {"status": status_update.status.value, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    return order

# ==================== PIX PAYMENT ROUTES ====================

@api_router.get("/pix/config")
async def get_pix_config():
    """Get PIX configuration for QR code generation"""
    return {
        "key": PIX_CONFIG["key"],
        "key_type": PIX_CONFIG["key_type"],
        "beneficiary_name": PIX_CONFIG["beneficiary_name"],
        "city": PIX_CONFIG["city"],
        "has_key": bool(PIX_CONFIG["key"])
    }

@api_router.post("/orders/{store}/{order_id}/pix-proof")
async def upload_pix_proof(store: StoreLocation, order_id: str, proof: PixProofUpload):
    """Upload PIX payment proof and auto-verify with AI"""
    order = await db.orders.find_one({"id": order_id, "store": store.value})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if order.get("payment_method") != "pix":
        raise HTTPException(status_code=400, detail="Este pedido não é PIX")
    
    await db.orders.update_one(
        {"id": order_id, "store": store.value},
        {
            "$set": {
                "pix_proof": proof.proof_image,
                "pix_proof_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    # Auto-verify the PIX proof with AI in the background
    import asyncio
    asyncio.create_task(auto_verify_pix_background(store, order_id, proof.proof_image, order.get("total", 0)))
    
    return {"success": True, "message": "Comprovante enviado! Verificando automaticamente..."}

async def auto_verify_pix_background(store: StoreLocation, order_id: str, pix_proof: str, expected_amount: float):
    """Background task to auto-verify PIX proof with AI"""
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        
        # Extract base64 from data URL if present
        image_base64 = pix_proof
        if pix_proof.startswith("data:"):
            image_base64 = pix_proof.split(",")[1]
        
        system_prompt = f"""Você é um assistente de OCR especializado em extrair texto de recibos de transação PIX.
Sua função é apenas ler e extrair informações textuais de comprovantes.

O valor esperado do pagamento é R$ {expected_amount:.2f}.
O destinatário esperado deve conter "saudavelmente" ou "ganoh" ou "49289019000199".

IMPORTANTE: O nome do pagador NÃO precisa ser verificado - apenas extraia o nome que aparece no comprovante.
A validação deve considerar APENAS:
1. Se o valor é >= {expected_amount:.2f}
2. Se o destinatário contém "saudavelmente", "ganoh" ou "49289019000199"

Responda APENAS em formato JSON:
{{
    "payer_name": "nome COMPLETO do remetente/pagador encontrado na imagem (extraia exatamente como aparece)",
    "amount": valor numérico encontrado (float),
    "recipient": "nome do destinatário/beneficiário encontrado",
    "transaction_time": "horário da transação encontrado (formato HH:MM)",
    "transaction_date": "data da transação (formato DD/MM/YYYY)",
    "is_valid": true se (valor >= {expected_amount:.2f}) E (destinatário contém saudavelmente/ganoh/49289019000199), false caso contrário,
    "reason": "motivo da validação (NÃO mencione o nome do pagador na validação)"
}}"""
        
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"pix-verify-{order_id}",
            system_message=system_prompt
        ).with_model("openai", "gpt-4o")
        
        image_content = ImageContent(image_base64=image_base64)
        user_message = UserMessage(
            text="Por favor, extraia as informações deste recibo de transação PIX.",
            file_contents=[image_content]
        )
        
        response = await chat.send_message(user_message)
        
        # Parse AI response
        import json
        import re
        
        response_text = response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            analysis = {"is_valid": False, "reason": "Não foi possível analisar o comprovante"}
        
        payer_name = analysis.get("payer_name", "Desconhecido")
        extracted_amount = analysis.get("amount", 0)
        transaction_time = analysis.get("transaction_time", datetime.now().strftime("%H:%M"))
        transaction_date = analysis.get("transaction_date", datetime.now().strftime("%d/%m/%Y"))
        is_valid = analysis.get("is_valid", False)
        
        # Save analysis to order
        await db.orders.update_one(
            {"id": order_id, "store": store.value},
            {
                "$set": {
                    "pix_analysis": analysis,
                    "pix_payer_name": payer_name,
                    "pix_extracted_amount": extracted_amount,
                    "pix_transaction_time": transaction_time,
                    "pix_transaction_date": transaction_date,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        if is_valid:
            # Get order for stock update
            order = await db.orders.find_one({"id": order_id, "store": store.value})
            
            # Update stock
            for item in order.get("items", []):
                await db.stock.update_one(
                    {"menu_item_id": item["menu_item_id"].split("-")[0], "store": store.value},
                    {"$inc": {"quantity": -item["quantity"]}},
                    upsert=False
                )
            
            # Update order status - AUTO APPROVED!
            await db.orders.update_one(
                {"id": order_id, "store": store.value},
                {
                    "$set": {
                        "status": "received",
                        "payment_approved_at": datetime.now(timezone.utc).isoformat(),
                        "auto_approved": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            # Send WhatsApp notification via Green API (only if approved)
            try:
                await send_whatsapp_notification(
                    customer_name=order.get("customer_name", "Cliente"),
                    payer_name=payer_name,
                    amount=order.get("total", 0),
                    store=store.value,
                    time=transaction_time,
                    date=transaction_date,
                    order_number=order.get("order_number", order_id[:8]),
                    items=order.get("items", []),
                    auto_approved=True,
                    pix_proof_image=pix_proof,
                    order_id=order_id
                )
            except Exception as e:
                logger.warning(f"Could not send WhatsApp notification: {e}")
            
            logger.info(f"PIX auto-approved for order {order_id}")
        else:
            logger.info(f"PIX verification failed for order {order_id}: {analysis.get('reason')}")
            
    except Exception as e:
        logger.error(f"Error in background PIX verification: {e}")

@api_router.post("/orders/{store}/{order_id}/auto-verify-pix")
async def auto_verify_pix_payment(store: StoreLocation, order_id: str):
    """Use AI to analyze PIX proof and auto-approve if valid"""
    order = await db.orders.find_one({"id": order_id, "store": store.value})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if order.get("status") != "pending_payment":
        raise HTTPException(status_code=400, detail="Pedido não está aguardando aprovação")
    
    pix_proof = order.get("pix_proof")
    if not pix_proof:
        raise HTTPException(status_code=400, detail="Comprovante PIX não encontrado")
    
    expected_amount = order.get("total", 0)
    
    # Analyze the PIX proof with AI
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        
        # Extract base64 from data URL if present
        image_base64 = pix_proof
        if pix_proof.startswith("data:"):
            image_base64 = pix_proof.split(",")[1]
        
        system_prompt = f"""Você é um assistente de OCR especializado em extrair texto de recibos de transação PIX.
Sua função é apenas ler e extrair informações textuais de comprovantes.

O valor esperado do pagamento é R$ {expected_amount:.2f}.
O destinatário esperado deve conter "saudavelmente" ou "ganoh" ou "49289019000199".

IMPORTANTE: O nome do pagador NÃO precisa ser verificado - apenas extraia o nome que aparece no comprovante.
A validação deve considerar APENAS:
1. Se o valor é >= {expected_amount:.2f}
2. Se o destinatário contém "saudavelmente", "ganoh" ou "49289019000199"

Responda APENAS em formato JSON:
{{
    "payer_name": "nome COMPLETO do remetente/pagador encontrado na imagem (extraia exatamente como aparece)",
    "amount": valor numérico encontrado (float),
    "recipient": "nome do destinatário/beneficiário encontrado",
    "transaction_time": "horário da transação (formato HH:MM)",
    "is_valid": true se (valor >= {expected_amount:.2f}) E (destinatário contém saudavelmente/ganoh/49289019000199), false caso contrário,
    "reason": "motivo da validação (NÃO mencione o nome do pagador)"
}}"""
        
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"pix-verify-{order_id}",
            system_message=system_prompt
        ).with_model("openai", "gpt-4o")
        
        image_content = ImageContent(image_base64=image_base64)
        user_message = UserMessage(
            text="Por favor, extraia as informações deste recibo de transação PIX.",
            file_contents=[image_content]
        )
        
        response = await chat.send_message(user_message)
        
        # Parse AI response
        import json
        import re
        
        response_text = response  # send_message returns string directly
        # Extract JSON from response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            analysis = {"is_valid": False, "reason": "Não foi possível analisar o comprovante"}
        
        payer_name = analysis.get("payer_name", "Desconhecido")
        extracted_amount = analysis.get("amount", 0)
        transaction_time = analysis.get("transaction_time", datetime.now().strftime("%H:%M"))
        transaction_date = analysis.get("transaction_date", datetime.now().strftime("%d/%m/%Y"))
        is_valid = analysis.get("is_valid", False)
        
        # Save analysis to order
        await db.orders.update_one(
            {"id": order_id, "store": store.value},
            {
                "$set": {
                    "pix_analysis": analysis,
                    "pix_payer_name": payer_name,
                    "pix_extracted_amount": extracted_amount,
                    "pix_transaction_time": transaction_time,
                    "pix_transaction_date": transaction_date,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        if is_valid:
            # Auto-approve the payment
            # Update stock
            for item in order.get("items", []):
                await db.stock.update_one(
                    {"menu_item_id": item["menu_item_id"].split("-")[0], "store": store.value},
                    {"$inc": {"quantity": -item["quantity"]}},
                    upsert=False
                )
            
            # Update order status
            await db.orders.update_one(
                {"id": order_id, "store": store.value},
                {
                    "$set": {
                        "status": "received",
                        "payment_approved_at": datetime.now(timezone.utc).isoformat(),
                        "auto_approved": True,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            # Send WhatsApp notification via Green API (only if not already notified)
            if not order.get("whatsapp_notified"):
                try:
                    await send_whatsapp_notification(
                        customer_name=order.get("customer_name", "Cliente"),
                        payer_name=payer_name,
                        amount=order.get("total", 0),
                        store=store.value,
                        time=transaction_time,
                        date=transaction_date,
                        order_number=order.get("order_number", order_id[:8]),
                        items=order.get("items", []),
                        auto_approved=True,
                        pix_proof_image=pix_proof,
                        order_id=order_id
                    )
                except Exception as e:
                    logger.warning(f"Could not send WhatsApp notification: {e}")
            else:
                logger.info(f"Skipping WhatsApp notification for order {order_id} - already notified")
            
            return {
                "success": True,
                "auto_approved": True,
                "payer_name": payer_name,
                "extracted_amount": extracted_amount,
                "analysis": analysis,
                "message": "Pagamento verificado e aprovado automaticamente!"
            }
        else:
            # NOT APPROVED - do not send notification
            return {
                "success": True,
                "auto_approved": False,
                "payer_name": payer_name,
                "extracted_amount": extracted_amount,
                "analysis": analysis,
                "message": f"Verificação falhou: {analysis.get('reason', 'Dados não correspondem')}"
            }
            
    except Exception as e:
        logger.error(f"Error analyzing PIX proof: {e}")
        return {
            "success": False,
            "auto_approved": False,
            "error": str(e),
            "message": "Erro ao analisar comprovante. Aprovação manual necessária."
        }

# ==================== ENDPOINTS PARA SINCRONIZAÇÃO DEPLOY ↔ PREVIEW ====================

class ExternalPixVerifyRequest(BaseModel):
    pix_proof: str
    expected_amount: float
    customer_name: str = "Cliente"

@api_router.post("/orders/{store}/{order_id}/auto-verify-pix-external")
async def auto_verify_pix_external(store: StoreLocation, order_id: str, request: ExternalPixVerifyRequest):
    """Verify PIX proof from external source (deploy) using local AI"""
    pix_proof = request.pix_proof
    expected_amount = request.expected_amount
    
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        
        # Extract base64 from data URL if present
        image_base64 = pix_proof
        if pix_proof.startswith("data:"):
            image_base64 = pix_proof.split(",")[1]
        
        system_prompt = f"""Você é um assistente de OCR especializado em extrair texto de recibos de transação PIX.
Sua função é apenas ler e extrair informações textuais de comprovantes.

O valor esperado do pagamento é R$ {expected_amount:.2f}.
O destinatário esperado deve conter "saudavelmente" ou "ganoh" ou "49289019000199".

IMPORTANTE: O nome do pagador NÃO precisa ser verificado - apenas extraia o nome que aparece no comprovante.
A validação deve considerar APENAS:
1. Se o valor é >= {expected_amount:.2f}
2. Se o destinatário contém "saudavelmente", "ganoh" ou "49289019000199"

Responda APENAS em formato JSON:
{{
    "payer_name": "nome COMPLETO do remetente/pagador encontrado na imagem (extraia exatamente como aparece)",
    "amount": valor numérico encontrado (float),
    "recipient": "nome do destinatário/beneficiário encontrado",
    "transaction_time": "horário da transação no formato HH:MM",
    "transaction_date": "data da transação no formato DD/MM/YYYY",
    "is_valid": true se (valor >= {expected_amount:.2f}) E (destinatário contém saudavelmente/ganoh/49289019000199), false caso contrário,
    "reason": "motivo da validação (NÃO mencione o nome do pagador)"
}}"""
        
        chat = LlmChat(
            api_key=os.environ.get("EMERGENT_LLM_KEY"),
            session_id=f"pix-external-{order_id}",
            system_message=system_prompt
        ).with_model("openai", "gpt-4o")
        
        image_content = ImageContent(image_base64=image_base64)
        user_message = UserMessage(
            text="Por favor, extraia as informações deste recibo de transação PIX.",
            file_contents=[image_content]
        )
        
        response = await chat.send_message(user_message)
        
        # Parse AI response
        import json
        import re
        
        response_text = response
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            analysis = {"is_valid": False, "reason": "Não foi possível analisar o comprovante"}
        
        is_valid = analysis.get("is_valid", False)
        
        return {
            "success": True,
            "auto_approved": is_valid,
            "analysis": analysis
        }
        
    except Exception as e:
        logger.error(f"Error in external PIX verification: {e}")
        return {
            "success": False,
            "auto_approved": False,
            "error": str(e)
        }

class PixAnalysisUpdate(BaseModel):
    pix_analysis: dict
    pix_payer_name: str = "Desconhecido"
    pix_transaction_time: str = ""
    auto_approved: bool = False

@api_router.patch("/orders/{store}/{order_id}/pix-analysis")
async def update_pix_analysis(store: StoreLocation, order_id: str, update: PixAnalysisUpdate):
    """Update PIX analysis result from external verification"""
    result = await db.orders.update_one(
        {"id": order_id, "store": store.value},
        {
            "$set": {
                "pix_analysis": update.pix_analysis,
                "pix_payer_name": update.pix_payer_name,
                "pix_transaction_time": update.pix_transaction_time,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    return {"success": True, "message": "Análise PIX atualizada"}

# ==================== FIM DOS ENDPOINTS DE SINCRONIZAÇÃO ====================

@api_router.post("/orders/{store}/{order_id}/approve-payment")
async def approve_or_reject_payment(store: StoreLocation, order_id: str, approval: PaymentApproval):
    """Approve or reject PIX payment"""
    order = await db.orders.find_one({"id": order_id, "store": store.value})
    if not order:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    if order.get("status") != "pending_payment":
        raise HTTPException(status_code=400, detail="Pedido não está aguardando aprovação")
    
    if approval.approved:
        # Update stock on approval
        for item in order.get("items", []):
            await db.stock.update_one(
                {"menu_item_id": item["menu_item_id"].split("-")[0], "store": store.value},
                {"$inc": {"quantity": -item["quantity"]}},
                upsert=False
            )
        
        await db.orders.update_one(
            {"id": order_id, "store": store.value},
            {
                "$set": {
                    "status": "received",
                    "payment_approved_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # Send WhatsApp notification via Green API (only if not already notified)
        if not order.get("whatsapp_notified"):
            try:
                pix_proof = order.get("pix_proof")
                payer_name = order.get("pix_payer_name", order.get("customer_name", "Cliente"))
                
                await send_whatsapp_notification(
                    customer_name=order.get("customer_name", "Cliente"),
                    payer_name=payer_name,
                    amount=order.get("total", 0),
                    store=store.value,
                    time=datetime.now().strftime("%H:%M"),
                    date=datetime.now().strftime("%d/%m/%Y"),
                    order_number=order.get("order_number", order_id[:8]),
                    items=order.get("items", []),
                    auto_approved=True,
                    pix_proof_image=pix_proof,
                    order_id=order_id
                )
            except Exception as e:
                logger.warning(f"Could not send WhatsApp notification: {e}")
        else:
            logger.info(f"Skipping WhatsApp notification for order {order_id} - already notified")
        
        return {"success": True, "message": "Pagamento aprovado", "new_status": "received"}
    else:
        await db.orders.update_one(
            {"id": order_id, "store": store.value},
            {
                "$set": {
                    "status": "payment_rejected",
                    "rejection_reason": approval.rejection_reason,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        return {"success": True, "message": "Pagamento rejeitado", "new_status": "payment_rejected"}

@api_router.delete("/orders/{store}/{order_id}")
async def delete_order_permanently(store: StoreLocation, order_id: str):
    """Delete an order permanently - it won't appear in history or gestor"""
    result = await db.orders.delete_one({"id": order_id, "store": store.value})
    # Also delete from history if exists
    await db.order_history.delete_one({"id": order_id, "store": store.value})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    return {"success": True, "message": "Pedido apagado permanentemente"}

@api_router.delete("/orders/history/cleanup")
async def cleanup_old_history():
    """Clean up order history older than 24 hours (can be called by cron)"""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    result = await db.order_history.delete_many({
        "delivered_at": {"$lt": cutoff.isoformat()}
    })
    return {"deleted": result.deleted_count}

# ==================== STOCK ROUTES ====================

# Categorias que precisam de controle de estoque
STOCK_CATEGORIES = ["Bebidas Quentes", "Bebidas Geladas"]

# Ingredientes para estoque
INGREDIENTES_ESTOQUE = [
    {"id": "ing_1", "name": "Ovos (unidade)", "category": "Ingredientes"},
    {"id": "ing_2", "name": "Atum (porção)", "category": "Ingredientes"},
    {"id": "ing_3", "name": "Queijo Branco (porção)", "category": "Ingredientes"},
    {"id": "ing_4", "name": "Mussarela (porção)", "category": "Ingredientes"},
    {"id": "ing_5", "name": "Frango Desfiado (porção)", "category": "Ingredientes"},
    {"id": "ing_6", "name": "Peito de Peru (porção)", "category": "Ingredientes"},
    {"id": "ing_7", "name": "Mel (porção)", "category": "Ingredientes"},
    {"id": "ing_8", "name": "Granola (porção)", "category": "Ingredientes"},
    {"id": "ing_9", "name": "Nutella (porção)", "category": "Ingredientes"},
    {"id": "ing_10", "name": "Pão Integral (unidade)", "category": "Ingredientes"},
    {"id": "ing_11", "name": "Requeijão (porção)", "category": "Ingredientes"},
    {"id": "ing_12", "name": "Whey Protein (dose)", "category": "Ingredientes"},
    {"id": "ing_13", "name": "Açaí (litro)", "category": "Ingredientes"},
    {"id": "ing_14", "name": "Leite (litro)", "category": "Ingredientes"},
    {"id": "ing_15", "name": "Café (kg)", "category": "Ingredientes"},
]

class StockItemCreate(BaseModel):
    name: str
    category: str = "Ingredientes"
    quantity: int = 0
    min_quantity: int = 5

@api_router.get("/stock/{store}")
async def get_stock(store: StoreLocation):
    stock_items = await db.stock.find({"store": store.value}, {"_id": 0}).to_list(1000)
    
    # Get bebidas from menu
    bebidas = [item for item in MENU_DATA if item["category"] in STOCK_CATEGORIES]
    menu_map = {item["id"]: item for item in bebidas}
    
    result = []
    for stock in stock_items:
        menu_item = menu_map.get(stock["menu_item_id"])
        ingrediente = next((i for i in INGREDIENTES_ESTOQUE if i["id"] == stock["menu_item_id"]), None)
        
        if menu_item:
            result.append({
                **stock,
                "name": menu_item["name"],
                "category": menu_item["category"],
                "low_stock": stock["quantity"] <= stock.get("min_quantity", 2),
                "type": "bebida"
            })
        elif ingrediente:
            result.append({
                **stock,
                "name": ingrediente["name"],
                "category": ingrediente["category"],
                "low_stock": stock["quantity"] <= stock.get("min_quantity", 2),
                "type": "ingrediente"
            })
        elif stock.get("name"):
            # Custom item added by user
            result.append({
                **stock,
                "low_stock": stock["quantity"] <= stock.get("min_quantity", 2),
                "type": "custom"
            })
    
    return {"stock": result}

@api_router.put("/stock/{store}/{menu_item_id}")
async def update_stock(store: StoreLocation, menu_item_id: str, stock_update: StockUpdate):
    await db.stock.update_one(
        {"menu_item_id": menu_item_id, "store": store.value},
        {
            "$set": {
                "quantity": stock_update.quantity,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        },
        upsert=True
    )
    
    stock = await db.stock.find_one({"menu_item_id": menu_item_id, "store": store.value}, {"_id": 0})
    return stock

@api_router.post("/stock/{store}/add")
async def add_stock_item(store: StoreLocation, item: StockItemCreate):
    """Add a new custom item to stock"""
    new_id = f"custom_{str(uuid.uuid4())[:8]}"
    
    doc = {
        "id": str(uuid.uuid4()),
        "menu_item_id": new_id,
        "store": store.value,
        "name": item.name,
        "category": item.category,
        "quantity": item.quantity,
        "min_quantity": item.min_quantity,
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.stock.insert_one(doc)
    return {**doc, "_id": None}

@api_router.delete("/stock/{store}/{menu_item_id}")
async def delete_stock_item(store: StoreLocation, menu_item_id: str):
    """Delete a custom stock item"""
    if not menu_item_id.startswith("custom_"):
        raise HTTPException(status_code=400, detail="Só é possível deletar itens personalizados")
    
    result = await db.stock.delete_one({"menu_item_id": menu_item_id, "store": store.value})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return {"message": "Item removido"}

@api_router.post("/stock/{store}/initialize")
async def initialize_stock(store: StoreLocation, default_quantity: int = 50):
    """Initialize stock for bebidas and ingredientes only"""
    # Bebidas
    bebidas = [item for item in MENU_DATA if item["category"] in STOCK_CATEGORIES]
    for item in bebidas:
        await db.stock.update_one(
            {"menu_item_id": item["id"], "store": store.value},
            {
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "menu_item_id": item["id"],
                    "store": store.value,
                    "quantity": default_quantity,
                    "min_quantity": 5,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
    
    # Ingredientes
    for item in INGREDIENTES_ESTOQUE:
        await db.stock.update_one(
            {"menu_item_id": item["id"], "store": store.value},
            {
                "$setOnInsert": {
                    "id": str(uuid.uuid4()),
                    "menu_item_id": item["id"],
                    "store": store.value,
                    "quantity": default_quantity,
                    "min_quantity": 10,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            },
            upsert=True
        )
    
    return {"message": f"Estoque inicializado para {store.value}"}

# ==================== KITCHEN ROUTES ====================

@api_router.get("/kitchen/{store}/stats")
async def get_kitchen_stats(store: StoreLocation):
    pending = await db.orders.count_documents({"store": store.value, "status": "received"})
    preparing = await db.orders.count_documents({"store": store.value, "status": "preparing"})
    # Only count "fresh" ready orders (last 12h) - matches the auto-archive policy
    # so the textual badge stays in sync with the visual list.
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(hours=12)).isoformat()
    ready = await db.orders.count_documents({
        "store": store.value,
        "status": "ready",
        "$or": [
            {"updated_at": {"$gte": stale_cutoff}},
            {"updated_at": {"$exists": False}, "created_at": {"$gte": stale_cutoff}},
        ],
    })

    return {"pending": pending, "preparing": preparing, "ready": ready}

# ==================== CASH REGISTER ROUTES ====================

@api_router.get("/cash/{store}/today")
async def get_today_cash(store: StoreLocation):
    # Use Brazil timezone for correct day calculation
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    # Convert to UTC for database query
    today_utc = today_brazil.astimezone(pytz.UTC)
    
    orders = await db.orders.find({
        "store": store.value,
        "status": {"$in": ["ready", "delivered"]},  # Conta pedidos prontos E entregues
        "created_at": {"$gte": today_utc.isoformat()}
    }, {"_id": 0}).to_list(1000)
    
    # Get manual PIX adjustments for today
    pix_adjustments = await db.pix_adjustments.find({
        "store": store.value,
        "removed": {"$ne": True},
        "created_at": {"$gte": today_utc.isoformat()}
    }, {"_id": 0}).to_list(1000)
    pix_manual_total = sum(a.get("amount", 0) for a in pix_adjustments)
    
    # Separate PIX adjustments by shift
    pix_manual_morning = 0
    pix_manual_afternoon = 0
    for adj in pix_adjustments:
        try:
            adj_time = datetime.fromisoformat(adj.get("created_at", "").replace("Z", "+00:00"))
            adj_time_brazil = adj_time.astimezone(brazil_tz)
            adj_hour = adj_time_brazil.hour
            if 6 <= adj_hour < 14:
                pix_manual_morning += adj.get("amount", 0)
            else:
                pix_manual_afternoon += adj.get("amount", 0)
        except:
            pix_manual_afternoon += adj.get("amount", 0)
    
    # Total VALUE by payment method (in R$)
    by_payment_value = {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "prazo": 0, "voucher": 0}
    total = 0
    
    # By shift (06:00-14:00 and 14:00-22:00)
    shift_morning = {"total": 0, "count": 0, "by_payment": {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "voucher": 0}}
    shift_afternoon = {"total": 0, "count": 0, "by_payment": {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "voucher": 0}}
    
    for order in orders:
        payment = order.get("payment_method", "cash")
        amount = order.get("total", 0)
        
        # Prazo não soma no total de vendas
        if payment != "prazo":
            by_payment_value[payment] = by_payment_value.get(payment, 0) + amount
            total += amount
        
        # Determine shift based on order time in Brazil timezone
        created_at = order.get("created_at", "")
        try:
            if isinstance(created_at, str):
                order_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            else:
                order_time = created_at
            
            # Convert to Brazil timezone
            order_time_brazil = order_time.astimezone(brazil_tz)
            brazil_hour = order_time_brazil.hour
            
            # Prazo não soma no total dos turnos
            if payment != "prazo":
                if 6 <= brazil_hour < 14:
                    shift_morning["total"] += amount
                    shift_morning["count"] += 1
                    shift_morning["by_payment"][payment] += amount
                else:
                    shift_afternoon["total"] += amount
                    shift_afternoon["count"] += 1
                    shift_afternoon["by_payment"][payment] += amount
        except Exception:
            if payment != "prazo":
                shift_afternoon["total"] += amount
                shift_afternoon["count"] += 1
                shift_afternoon["by_payment"][payment] += amount
    
    # Add manual PIX adjustments to PIX total and overall total
    by_payment_value["pix"] += pix_manual_total
    total += pix_manual_total
    
    # Add manual PIX to shifts
    shift_morning["by_payment"]["pix"] += pix_manual_morning
    shift_morning["total"] += pix_manual_morning
    shift_afternoon["by_payment"]["pix"] += pix_manual_afternoon
    shift_afternoon["total"] += pix_manual_afternoon
    
    return {
        "date": today_brazil.strftime("%Y-%m-%d"),
        "total": total,
        "by_payment_method": by_payment_value,
        "order_count": len(orders),
        "pix_manual_adjustments": round(pix_manual_total, 2),
        "pix_manual_morning": round(pix_manual_morning, 2),
        "pix_manual_afternoon": round(pix_manual_afternoon, 2),
        "shifts": {
            "morning": {
                "label": "06:00 - 14:00",
                **shift_morning
            },
            "afternoon": {
                "label": "14:00 - 22:00",
                **shift_afternoon
            }
        }
    }

# ==================== CASH DRAWER / CAIXA ROUTES ====================

class CashBalanceAdjust(BaseModel):
    balance: float
    notes: Optional[str] = None

@api_router.get("/cash/{store}/drawer")
async def get_cash_drawer(store: StoreLocation):
    """Get current cash drawer status - persistent balance that only resets manually"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    today_utc = today_brazil.astimezone(pytz.UTC)
    
    # Get the drawer config (stores last_reset_at and initial_balance)
    drawer_config = await db.cash_drawer_config.find_one({"store": store.value}, {"_id": 0})
    initial_balance = drawer_config.get("balance", 0) if drawer_config else 0
    last_reset_at = drawer_config.get("last_reset_at") if drawer_config else None
    
    # Build query for cash orders SINCE last reset (not just today)
    cash_query = {
        "store": store.value,
        "status": {"$in": ["ready", "delivered"]},
        "payment_method": "cash",
        "synthetic": {"$ne": True},
    }
    if last_reset_at:
        cash_query["created_at"] = {"$gte": last_reset_at}
    
    # Get all cash orders since last reset
    cash_orders = await db.orders.find(cash_query, {"_id": 0, "total": 1, "created_at": 1}).to_list(100000)
    total_cash_sales = sum(o.get("total", 0) for o in cash_orders)
    
    # Get prazo payments made in CASH since last reset
    prazo_cash_query = {
        "store": store.value,
        "payment_method": "cash"
    }
    if last_reset_at:
        prazo_cash_query["created_at"] = {"$gte": last_reset_at}
    
    prazo_full_payments = await db.prazo_payments.find(prazo_cash_query, {"_id": 0, "amount": 1, "created_at": 1}).to_list(10000)
    prazo_partial_payments = await db.prazo_partial_payments.find(prazo_cash_query, {"_id": 0, "amount": 1, "created_at": 1}).to_list(10000)
    
    total_prazo_cash = sum(p.get("amount", 0) for p in prazo_full_payments) + sum(p.get("amount", 0) for p in prazo_partial_payments)
    
    # Build query for withdrawals SINCE last reset
    withdrawal_query = {"store": store.value}
    if last_reset_at:
        withdrawal_query["created_at"] = {"$gte": last_reset_at}
    
    # Get all withdrawals since last reset
    all_withdrawals = await db.cash_withdrawals.find(withdrawal_query, {"_id": 0}).to_list(10000)
    total_withdrawn = sum(w.get("amount", 0) for w in all_withdrawals)
    
    # Today's data for display only
    today_cash_orders = [o for o in cash_orders if o.get("created_at", "") >= today_utc.isoformat()]
    today_cash_in = sum(o.get("total", 0) for o in today_cash_orders)
    
    # Today's prazo cash payments (use UTC consistently since DB stores UTC)
    today_prazo_full = [p for p in prazo_full_payments if p.get("created_at", "") >= today_utc.isoformat()]
    today_prazo_partial = [p for p in prazo_partial_payments if p.get("created_at", "") >= today_utc.isoformat()]
    today_prazo_cash = sum(p.get("amount", 0) for p in today_prazo_full) + sum(p.get("amount", 0) for p in today_prazo_partial)
    
    today_withdrawals = [w for w in all_withdrawals if w.get("created_at", "") >= today_utc.isoformat()]
    today_withdrawn = sum(w.get("amount", 0) for w in today_withdrawals)
    
    # Current balance = initial + all sales since reset + prazo cash payments - all withdrawals since reset
    current_balance = initial_balance + total_cash_sales + total_prazo_cash - total_withdrawn
    
    return {
        "store": store.value,
        "date": now_brazil.strftime("%d/%m/%Y"),
        "initial_balance": round(initial_balance, 2),
        "total_cash_sales": round(total_cash_sales, 2),
        "total_prazo_cash": round(total_prazo_cash, 2),  # Prazo payments made in cash
        "total_withdrawals": round(total_withdrawn, 2),
        "current_balance": round(current_balance, 2),
        # Today's data (for reference)
        "today_cash_in": round(today_cash_in, 2),
        "today_prazo_cash": round(today_prazo_cash, 2),  # Today's prazo cash payments
        "today_withdrawals": round(today_withdrawn, 2),
        "withdrawal_history": today_withdrawals,
        # Last reset info
        "last_reset_at": last_reset_at
    }

@api_router.get("/cash/{store}/drawer-debug")
async def get_cash_drawer_debug(store: StoreLocation):
    """Debug endpoint - shows all cash orders being counted in the drawer"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    
    # Get the drawer config
    drawer_config = await db.cash_drawer_config.find_one({"store": store.value}, {"_id": 0})
    initial_balance = drawer_config.get("balance", 0) if drawer_config else 0
    last_reset_at = drawer_config.get("last_reset_at") if drawer_config else None
    
    # Build query for cash orders SINCE last reset
    cash_query = {
        "store": store.value,
        "status": {"$in": ["ready", "delivered"]},
        "payment_method": "cash"
    }
    if last_reset_at:
        cash_query["created_at"] = {"$gte": last_reset_at}
    
    # Get all cash orders with details
    cash_orders = await db.orders.find(cash_query, {"_id": 0, "customer_name": 1, "total": 1, "created_at": 1, "status": 1}).to_list(1000)
    total_cash_sales = sum(o.get("total", 0) for o in cash_orders)
    
    # Get prazo payments made in CASH
    prazo_cash_query = {
        "store": store.value,
        "payment_method": "cash"
    }
    if last_reset_at:
        prazo_cash_query["created_at"] = {"$gte": last_reset_at}
    
    prazo_full_payments = await db.prazo_payments.find(prazo_cash_query, {"_id": 0}).to_list(1000)
    prazo_partial_payments = await db.prazo_partial_payments.find(prazo_cash_query, {"_id": 0}).to_list(1000)
    total_prazo_cash = sum(p.get("amount", 0) for p in prazo_full_payments) + sum(p.get("amount", 0) for p in prazo_partial_payments)
    
    # Get withdrawals
    withdrawal_query = {"store": store.value}
    if last_reset_at:
        withdrawal_query["created_at"] = {"$gte": last_reset_at}
    all_withdrawals = await db.cash_withdrawals.find(withdrawal_query, {"_id": 0}).to_list(1000)
    total_withdrawn = sum(w.get("amount", 0) for w in all_withdrawals)
    
    current_balance = initial_balance + total_cash_sales + total_prazo_cash - total_withdrawn
    
    return {
        "store": store.value,
        "drawer_config": drawer_config,
        "last_reset_at": last_reset_at,
        "initial_balance": initial_balance,
        "cash_orders": cash_orders,
        "cash_orders_count": len(cash_orders),
        "total_cash_sales": round(total_cash_sales, 2),
        "prazo_cash_payments": prazo_full_payments + prazo_partial_payments,
        "prazo_cash_count": len(prazo_full_payments) + len(prazo_partial_payments),
        "total_prazo_cash": round(total_prazo_cash, 2),
        "withdrawals": all_withdrawals,
        "total_withdrawn": round(total_withdrawn, 2),
        "current_balance": round(current_balance, 2),
        "formula": f"{initial_balance} + {total_cash_sales} (vendas) + {total_prazo_cash} (prazo em dinheiro) - {total_withdrawn} = {current_balance}"
    }

@api_router.post("/cash/{store}/set-balance")
async def set_cash_balance(store: StoreLocation, data: CashBalanceAdjust):
    """Set/adjust the initial cash drawer balance (money already in the drawer)"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    
    # Get current config
    existing = await db.cash_drawer_config.find_one({"store": store.value})
    
    if existing:
        await db.cash_drawer_config.update_one(
            {"store": store.value},
            {"$set": {
                "balance": data.balance,
                "notes": data.notes or "Ajuste de saldo",
                "updated_at": now_brazil.isoformat()
            }}
        )
    else:
        await db.cash_drawer_config.insert_one({
            "store": store.value,
            "balance": data.balance,
            "notes": data.notes or "Saldo inicial",
            "created_at": now_brazil.isoformat(),
            "updated_at": now_brazil.isoformat()
        })
    
    # Return updated drawer status
    return await get_cash_drawer(store)

@api_router.post("/cash/{store}/reset")
async def reset_cash_drawer(store: StoreLocation):
    """Reset the cash drawer - sets last_reset_at to now, so only future orders count"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    
    # Set last_reset_at to now - this makes all previous orders/withdrawals not count
    await db.cash_drawer_config.update_one(
        {"store": store.value},
        {"$set": {
            "balance": 0,
            "last_reset_at": now_brazil.isoformat(),
            "notes": f"Caixa zerado em {now_brazil.strftime('%d/%m/%Y %H:%M')}",
            "updated_at": now_brazil.isoformat()
        }},
        upsert=True
    )
    
    # Return updated drawer status
    return await get_cash_drawer(store)

@api_router.post("/cash/{store}/fix-cleared")
async def fix_cash_cleared_orders(store: StoreLocation):
    """Remove the cash_cleared flag from all orders (one-time fix)"""
    result = await db.orders.update_many(
        {"store": store.value, "cash_cleared": True},
        {"$unset": {"cash_cleared": "", "cash_cleared_at": ""}}
    )
    return {
        "success": True,
        "fixed_count": result.modified_count,
        "message": f"{result.modified_count} pedidos corrigidos"
    }

@api_router.post("/cash/{store}/withdraw")
async def withdraw_cash(store: StoreLocation, withdrawal: CashWithdrawal):
    """Withdraw cash from the drawer and optionally register as expense"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    
    # Check if there's enough balance
    current_drawer = await get_cash_drawer(store)
    if withdrawal.amount > current_drawer["current_balance"]:
        raise HTTPException(status_code=400, detail="Saldo insuficiente no caixa")
    
    # Create withdrawal record
    withdrawal_record = {
        "id": str(uuid.uuid4()),
        "store": store.value,
        "amount": withdrawal.amount,
        "category": withdrawal.category,
        "description": withdrawal.description or ("Vale Transporte" if withdrawal.category == "vt" else "Retirada de caixa"),
        "created_at": now_brazil.isoformat()
    }
    
    await db.cash_withdrawals.insert_one({**withdrawal_record})
    
    # If VT, also register as expense
    if withdrawal.category == "vt":
        expense = {
            "id": str(uuid.uuid4()),
            "description": "Vale Transporte (VT)",
            "amount": withdrawal.amount,
            "category": "vt",
            "store": store.value,
            "notes": f"Retirado do caixa em {now_brazil.strftime('%d/%m/%Y %H:%M')}",
            "created_at": now_brazil.isoformat(),
            "image_url": ""
        }
        await db.expenses.insert_one({**expense})
    
    # Get updated drawer status
    updated_drawer = await get_cash_drawer(store)
    
    return {
        "success": True,
        "withdrawal": withdrawal_record,
        "expense_created": withdrawal.category == "vt",
        "current_balance": updated_drawer["current_balance"]
    }

# ==================== PIX MANUAL ADJUSTMENTS ====================

class PixAdjustment(BaseModel):
    amount: float
    description: str = ""
    store: str

@api_router.get("/pix-adjustments/{store}")
async def get_pix_adjustments(store: str):
    """Get all manual PIX adjustments for a store"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Get all adjustments for this store (today) that are not removed
    adjustments = await db.pix_adjustments.find({
        "store": store,
        "removed": {"$ne": True},
        "created_at": {"$gte": today_brazil.isoformat()}
    }, {"_id": 0}).to_list(1000)
    
    total_added = sum(a.get("amount", 0) for a in adjustments)
    
    return {
        "store": store,
        "adjustments": adjustments,
        "total_added": round(total_added, 2)
    }

@api_router.post("/pix-adjustments/add")
async def add_pix_adjustment(adjustment: PixAdjustment):
    """Add a manual PIX value (not from sales)"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    
    new_adjustment = {
        "id": str(uuid.uuid4()),
        "store": adjustment.store,
        "amount": adjustment.amount,
        "description": adjustment.description or "Ajuste manual PIX",
        "removed": False,
        "created_at": now_brazil.isoformat()
    }
    
    await db.pix_adjustments.insert_one({**new_adjustment})
    
    return {"success": True, "adjustment": new_adjustment}

@api_router.delete("/pix-adjustments/{adjustment_id}")
async def remove_pix_adjustment(adjustment_id: str):
    """Remove a manual PIX adjustment (mark as removed)"""
    result = await db.pix_adjustments.update_one(
        {"id": adjustment_id},
        {"$set": {"removed": True, "removed_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Ajuste não encontrado")
    
    return {"success": True, "message": "Ajuste removido"}

# ==================== GESTOR ROUTES (Protected) ====================

@api_router.get("/gestor/dashboard")
async def get_gestor_dashboard(username: str = Depends(verify_gestor)):
    # Use Brazil timezone for correct day calculation
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start_brazil = today_brazil.replace(day=1)
    
    # Convert to UTC for database query
    today_utc = today_brazil.astimezone(pytz.UTC)
    month_start_utc = month_start_brazil.astimezone(pytz.UTC)
    
    result = {"stores": {}}
    
    for store_key in STORES.keys():
        # Today's orders
        today_orders = await db.orders.find({
            "store": store_key,
            "created_at": {"$gte": today_utc.isoformat()}
        }, {"_id": 0}).to_list(1000)
        
        # Month's orders
        month_orders = await db.orders.find({
            "store": store_key,
            "created_at": {"$gte": month_start_utc.isoformat()}
        }, {"_id": 0}).to_list(10000)
        
        # Calculate totals - inclui pedidos prontos e entregues
        today_total = sum(o.get("total", 0) for o in today_orders if o.get("status") in ["ready", "delivered"])
        month_total = sum(o.get("total", 0) for o in month_orders if o.get("status") in ["ready", "delivered"])
        
        # By payment method (today)
        today_by_payment = {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "prazo": 0, "voucher": 0}
        for order in today_orders:
            if order.get("status") in ["ready", "delivered"]:
                pm = order.get("payment_method", "cash")
                today_by_payment[pm] = today_by_payment.get(pm, 0) + order.get("total", 0)
        
        # Product sales count
        product_sales = {}
        for order in month_orders:
            if order.get("status") in ["ready", "delivered"]:
                for item in order.get("items", []):
                    name = item.get("name", "").split(" + ")[0]  # Remove adicionais from name
                    if name not in product_sales:
                        product_sales[name] = {"count": 0, "revenue": 0}
                    product_sales[name]["count"] += item.get("quantity", 1)
                    product_sales[name]["revenue"] += item.get("price", 0) * item.get("quantity", 1)
        
        # Top and low products
        sorted_products = sorted(product_sales.items(), key=lambda x: x[1]["count"], reverse=True)
        top_products = [{"name": k, **v} for k, v in sorted_products[:5]]
        low_products = [{"name": k, **v} for k, v in sorted_products[-5:] if v["count"] > 0]
        
        # Stock alerts
        low_stock = await db.stock.find({
            "store": store_key,
            "quantity": {"$lte": 5}
        }, {"_id": 0}).to_list(100)
        
        result["stores"][store_key] = {
            "name": STORES[store_key]["name"],
            "today": {
                "total": today_total,
                "order_count": len([o for o in today_orders if o.get("status") in ["ready", "delivered"]]),
                "by_payment_method": today_by_payment
            },
            "month": {
                "total": month_total,
                "order_count": len([o for o in month_orders if o.get("status") in ["ready", "delivered"]])
            },
            "top_products": top_products,
            "low_products": low_products,
            "low_stock_alerts": len(low_stock)
        }
    
    # Combined totals
    result["combined"] = {
        "today_total": sum(s["today"]["total"] for s in result["stores"].values()),
        "month_total": sum(s["month"]["total"] for s in result["stores"].values()),
        "today_orders": sum(s["today"]["order_count"] for s in result["stores"].values()),
        "month_orders": sum(s["month"]["order_count"] for s in result["stores"].values())
    }
    
    return result

@api_router.get("/gestor/sales/{store}")
async def get_store_sales(store: StoreLocation, days: int = 30, username: str = Depends(verify_gestor)):
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    
    orders = await db.orders.find({
        "store": store.value,
        "status": "delivered",
        "created_at": {"$gte": start_date.isoformat()}
    }, {"_id": 0}).to_list(10000)
    
    # Group by day
    daily_sales = {}
    for order in orders:
        date = order.get("created_at", "")[:10]
        if date not in daily_sales:
            daily_sales[date] = {"total": 0, "count": 0}
        daily_sales[date]["total"] += order.get("total", 0)
        daily_sales[date]["count"] += 1
    
    return {
        "store": store.value,
        "period_days": days,
        "daily_sales": daily_sales,
        "total": sum(d["total"] for d in daily_sales.values()),
        "order_count": sum(d["count"] for d in daily_sales.values())
    }

@api_router.get("/gestor/stock/{store}")
async def get_gestor_stock(store: StoreLocation, username: str = Depends(verify_gestor)):
    return await get_stock(store)

@api_router.put("/gestor/stock/{store}/{menu_item_id}")
async def update_gestor_stock(store: StoreLocation, menu_item_id: str, stock_update: StockUpdate, username: str = Depends(verify_gestor)):
    return await update_stock(store, menu_item_id, stock_update)

# ==================== MONTHLY CHART DATA ====================

@api_router.get("/gestor/chart/monthly")
async def get_monthly_chart_data(month: int = None, year: int = None, store: str = None, username: str = Depends(verify_gestor)):
    """Get daily sales data for a specific month for chart visualization.
    Optionally filtered by `store` (runner / gym-londres). When `store` is
    omitted or 'all', sums both stores."""
    # Use Brazil timezone (Mogi das Cruzes, SP)
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)

    # Use provided month/year or current
    target_month = month if month else now_brazil.month
    target_year = year if year else now_brazil.year

    # Create month start/end in Brazil timezone
    month_start_brazil = brazil_tz.localize(datetime(target_year, target_month, 1))

    # Calculate month end
    if target_month == 12:
        month_end_brazil = brazil_tz.localize(datetime(target_year + 1, 1, 1))
    else:
        month_end_brazil = brazil_tz.localize(datetime(target_year, target_month + 1, 1))

    # Convert to UTC for database query
    month_start_utc = month_start_brazil.astimezone(pytz.UTC)
    month_end_utc = month_end_brazil.astimezone(pytz.UTC)

    # Build orders query
    orders_query = {
        "status": {"$in": ["ready", "delivered", "received"]},
        "created_at": {"$gte": month_start_utc.isoformat(), "$lt": month_end_utc.isoformat()},
    }
    if store and store != "all":
        orders_query["store"] = store

    # Get all completed orders this month
    orders = await db.orders.find(orders_query, {"_id": 0, "created_at": 1, "total": 1, "store": 1, "payment_method": 1}).to_list(10000)
    
    # Get number of days in month
    import calendar
    days_in_month = calendar.monthrange(target_year, target_month)[1]
    
    # Payment methods breakdown (sem prazo)
    by_payment = {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "voucher": 0}

    # PIX adjustment / Prazo payment queries use UTC range for safety since
    # records were stored with mixed timezone formats over time.
    pix_query = {
        "removed": {"$ne": True},
        "created_at": {"$gte": month_start_utc.isoformat(), "$lt": month_end_utc.isoformat()}
    }
    if store and store != "all":
        pix_query["store"] = store
    pix_adjustments = await db.pix_adjustments.find(pix_query, {"_id": 0}).to_list(10000)

    prazo_query = {
        "created_at": {"$gte": month_start_utc.isoformat(), "$lt": month_end_utc.isoformat()}
    }
    if store and store != "all":
        prazo_query["store"] = store
    prazo_payments = await db.prazo_payments.find(prazo_query, {"_id": 0}).to_list(10000)
    prazo_partial_payments = await db.prazo_partial_payments.find(prazo_query, {"_id": 0}).to_list(10000)
    
    # Combine prazo payments
    all_prazo_payments = prazo_payments + prazo_partial_payments
    
    # Group PIX adjustments by day and store (use Brazil timezone to align days)
    pix_by_day = {}
    pix_total_runner = 0
    pix_total_gym = 0
    for adj in pix_adjustments:
        try:
            adj_time = datetime.fromisoformat(adj.get("created_at", "").replace("Z", "+00:00"))
            adj_time_brazil = adj_time.astimezone(brazil_tz)
            adj_date = adj_time_brazil.strftime("%Y-%m-%d")
            adj_store = adj.get("store", "")
            adj_amount = adj.get("amount", 0)

            if adj_date not in pix_by_day:
                pix_by_day[adj_date] = {"total": 0, "runner": 0, "gym_londres": 0}
            pix_by_day[adj_date]["total"] += adj_amount

            if adj_store == "runner":
                pix_by_day[adj_date]["runner"] += adj_amount
                pix_total_runner += adj_amount
            elif adj_store == "gym-londres":
                pix_by_day[adj_date]["gym_londres"] += adj_amount
                pix_total_gym += adj_amount

            by_payment["pix"] += adj_amount
        except Exception:
            pass
    
    # Group by day (in Brazil timezone) - with store separation
    daily_data = {}
    for i in range(days_in_month):
        day_date = month_start_brazil + timedelta(days=i)
        day_str = day_date.strftime("%Y-%m-%d")
        daily_data[day_str] = {
            "date": day_str, 
            "day": i + 1, 
            "total": 0, 
            "count": 0,
            "runner": 0,
            "runner_count": 0,
            "gym_londres": 0,
            "gym_londres_count": 0
        }
    
    for order in orders:
        try:
            order_time = datetime.fromisoformat(order.get("created_at", "").replace("Z", "+00:00"))
            # Convert to Brazil timezone to get correct day
            order_time_brazil = order_time.astimezone(brazil_tz)
            date = order_time_brazil.strftime("%Y-%m-%d")
            store = order.get("store", "")
            order_total = order.get("total", 0)
            payment_method = order.get("payment_method", "cash")
            
            # Prazo não soma nas vendas/gráficos
            if payment_method == "prazo":
                continue
            
            # Count by payment method
            by_payment[payment_method] = by_payment.get(payment_method, 0) + order_total
            
            if date in daily_data:
                daily_data[date]["total"] += order_total
                daily_data[date]["count"] += 1
                
                # Separate by store
                if store == "runner":
                    daily_data[date]["runner"] += order_total
                    daily_data[date]["runner_count"] += 1
                elif store == "gym-londres":
                    daily_data[date]["gym_londres"] += order_total
                    daily_data[date]["gym_londres_count"] += 1
        except:
            pass
    
    # Add PIX adjustments to daily totals
    for day_str, pix_data in pix_by_day.items():
        if day_str in daily_data:
            daily_data[day_str]["total"] += pix_data["total"]
            daily_data[day_str]["runner"] += pix_data["runner"]
            daily_data[day_str]["gym_londres"] += pix_data["gym_londres"]
    
    # Add prazo payments to daily totals and payment method breakdown
    for payment in all_prazo_payments:
        try:
            payment_time = datetime.fromisoformat(payment.get("created_at", "").replace("Z", "+00:00"))
            payment_time_brazil = payment_time.astimezone(brazil_tz)
            date = payment_time_brazil.strftime("%Y-%m-%d")
            store = payment.get("store", "runner")
            amount = payment.get("amount", 0)
            payment_method = payment.get("payment_method", "cash")
            
            # Add to payment method totals
            by_payment[payment_method] = by_payment.get(payment_method, 0) + amount
            
            if date in daily_data:
                daily_data[date]["total"] += amount
                daily_data[date]["count"] += 1  # Count as a transaction
                
                if store == "runner":
                    daily_data[date]["runner"] += amount
                    daily_data[date]["runner_count"] += 1
                elif store == "gym-londres":
                    daily_data[date]["gym_londres"] += amount
                    daily_data[date]["gym_londres_count"] += 1
        except:
            pass
    
    # Convert to sorted list
    chart_data = sorted(daily_data.values(), key=lambda x: x["date"])
    
    month_names = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
                   "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    # Calculate totals by store (including PIX adjustments)
    total_runner = sum(d["runner"] for d in chart_data)
    total_gym = sum(d["gym_londres"] for d in chart_data)
    
    return {
        "month": f"{month_names[target_month]} {target_year}",
        "month_num": target_month,
        "year": target_year,
        "store_filter": store or "all",
        "data": chart_data,
        "total_month": sum(d["total"] for d in chart_data),
        "total_orders": sum(d["count"] for d in chart_data),
        "by_store": {
            "runner": {"total": total_runner, "orders": sum(d["runner_count"] for d in chart_data)},
            "gym_londres": {"total": total_gym, "orders": sum(d["gym_londres_count"] for d in chart_data)}
        },
        "by_payment": {
            "pix": round(by_payment.get("pix", 0), 2),
            "debito": round(by_payment.get("debit", 0), 2),
            "credito": round(by_payment.get("credit", 0), 2),
            "dinheiro": round(by_payment.get("cash", 0), 2),
            "voucher": round(by_payment.get("voucher", 0), 2)
        }
    }

@api_router.get("/gestor/chart/daily")
async def get_daily_chart_data(date: str = None, store: str = None, username: str = Depends(verify_gestor)):
    """Get hourly sales data for a specific day, optionally filtered by store"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    
    # Parse date or use today (in Brazil timezone)
    if date:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
            target_date = brazil_tz.localize(target_date)
        except:
            target_date = now_brazil
    else:
        target_date = now_brazil
    
    day_str = target_date.strftime("%Y-%m-%d")
    day_start_brazil = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_brazil = day_start_brazil + timedelta(days=1)
    
    # Build base query
    query = {
        "status": {"$in": ["ready", "delivered", "received"]},
        "payment_method": {"$ne": "prazo"}
    }
    if store and store != "all":
        query["store"] = store
    
    # Get ALL orders and filter in memory by Brazil timezone date
    all_orders = await db.orders.find(query, {"_id": 0}).to_list(50000)
    
    orders = []
    for order in all_orders:
        try:
            created_at = order.get("created_at", "")
            if not created_at:
                continue
            order_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            order_time_brazil = order_time.astimezone(brazil_tz)
            if order_time_brazil.strftime("%Y-%m-%d") == day_str:
                order["_brazil_hour"] = order_time_brazil.hour
                orders.append(order)
        except Exception as e:
            pass
    
    # Get PIX adjustments for this day
    all_pix = await db.pix_adjustments.find({"removed": {"$ne": True}}, {"_id": 0}).to_list(10000)
    pix_adjustments = []
    for p in all_pix:
        try:
            created_at = p.get("created_at", "")
            if not created_at:
                continue
            p_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            p_time_brazil = p_time.astimezone(brazil_tz)
            if p_time_brazil.strftime("%Y-%m-%d") == day_str:
                if not store or store == "all" or p.get("store") == store:
                    pix_adjustments.append(p)
        except:
            pass
    
    pix_manual_total = sum(a.get("amount", 0) for a in pix_adjustments)
    pix_manual_runner = sum(a.get("amount", 0) for a in pix_adjustments if a.get("store") == "runner")
    pix_manual_gym = sum(a.get("amount", 0) for a in pix_adjustments if a.get("store") == "gym-londres")
    
    # Get prazo payments for this day
    all_prazo_full = await db.prazo_payments.find({}, {"_id": 0}).to_list(10000)
    all_prazo_partial = await db.prazo_partial_payments.find({}, {"_id": 0}).to_list(10000)
    
    prazo_payments = []
    for p in all_prazo_full + all_prazo_partial:
        try:
            created_at = p.get("created_at", "")
            if not created_at:
                continue
            p_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            p_time_brazil = p_time.astimezone(brazil_tz)
            if p_time_brazil.strftime("%Y-%m-%d") == day_str:
                if not store or store == "all" or p.get("store") == store:
                    p["_brazil_hour"] = p_time_brazil.hour
                    prazo_payments.append(p)
        except:
            pass
    
    # Initialize hourly data
    hourly_data = {}
    for hour in range(24):
        hourly_data[hour] = {"hour": f"{hour:02d}:00", "total": 0, "count": 0, "runner": 0, "gym_londres": 0}
    
    # Payment breakdown
    by_payment = {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "voucher": 0}
    
    # Process orders
    for order in orders:
        brazil_hour = order.get("_brazil_hour", 12)
        order_total = order.get("total", 0)
        order_store = order.get("store", "")
        payment_method = order.get("payment_method", "cash")
        
        hourly_data[brazil_hour]["total"] += order_total
        hourly_data[brazil_hour]["count"] += 1
        
        if order_store == "runner":
            hourly_data[brazil_hour]["runner"] += order_total
        elif order_store == "gym-londres":
            hourly_data[brazil_hour]["gym_londres"] += order_total
        
        by_payment[payment_method] = by_payment.get(payment_method, 0) + order_total
    
    # Add PIX manual adjustments
    by_payment["pix"] += pix_manual_total
    
    # Process prazo payments
    prazo_total = 0
    prazo_total_runner = 0
    prazo_total_gym = 0
    
    for p in prazo_payments:
        brazil_hour = p.get("_brazil_hour", 12)
        amount = p.get("amount", 0)
        p_store = p.get("store", "runner")
        p_method = p.get("payment_method", "cash")
        
        prazo_total += amount
        by_payment[p_method] = by_payment.get(p_method, 0) + amount
        
        hourly_data[brazil_hour]["total"] += amount
        hourly_data[brazil_hour]["count"] += 1
        
        if p_store == "runner":
            hourly_data[brazil_hour]["runner"] += amount
            prazo_total_runner += amount
        elif p_store == "gym-londres":
            hourly_data[brazil_hour]["gym_londres"] += amount
            prazo_total_gym += amount
    
    # Convert to sorted list
    chart_data = sorted(hourly_data.values(), key=lambda x: x["hour"])
    
    total_runner = sum(d["runner"] for d in chart_data) + pix_manual_runner
    total_gym = sum(d["gym_londres"] for d in chart_data) + pix_manual_gym
    
    return {
        "date": target_date.strftime("%d/%m/%Y"),
        "date_iso": day_str,
        "store_filter": store or "all",
        "data": chart_data,
        "total_day": sum(d["total"] for d in chart_data) + pix_manual_total,
        "total_orders": sum(d["count"] for d in chart_data),
        "pix_manual_adjustments": round(pix_manual_total, 2),
        "prazo_payments_total": round(prazo_total, 2),
        "by_store": {
            "runner": {"total": round(total_runner, 2), "orders": len([o for o in orders if o.get("store") == "runner"])},
            "gym_londres": {"total": round(total_gym, 2), "orders": len([o for o in orders if o.get("store") == "gym-londres"])}
        },
        "by_payment": {
            "pix": round(by_payment.get("pix", 0), 2),
            "debito": round(by_payment.get("debit", 0), 2),
            "credito": round(by_payment.get("credit", 0), 2),
            "dinheiro": round(by_payment.get("cash", 0), 2),
            "voucher": round(by_payment.get("voucher", 0), 2)
        },
        "orders": [{"time": o.get("created_at", "")[-14:-9] if o.get("created_at") else "", "total": o.get("total", 0), "store": o.get("store", "")} for o in orders[:50]]
    }

@api_router.get("/gestor/chart/yearly")
async def get_yearly_chart_data(year: int = None, store: str = None, username: str = Depends(verify_gestor)):
    """Get monthly sales data for a specific year, optionally filtered by store."""
    # Use Brazil timezone (Mogi das Cruzes, SP)
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    target_year = year if year else now_brazil.year

    # Create year start/end in Brazil timezone
    year_start_brazil = brazil_tz.localize(datetime(target_year, 1, 1))
    year_end_brazil = brazil_tz.localize(datetime(target_year + 1, 1, 1))

    # Convert to UTC for database query
    year_start_utc = year_start_brazil.astimezone(pytz.UTC)
    year_end_utc = year_end_brazil.astimezone(pytz.UTC)

    # Build query
    orders_query = {
        "status": {"$in": ["ready", "delivered", "received"]},
        "created_at": {"$gte": year_start_utc.isoformat(), "$lt": year_end_utc.isoformat()}
    }
    if store and store != "all":
        orders_query["store"] = store

    # Get all completed orders this year
    orders = await db.orders.find(orders_query, {"_id": 0, "created_at": 1, "total": 1, "store": 1}).to_list(100000)
    
    # Group by month (in Brazil timezone)
    month_names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    monthly_data = {}
    for month in range(1, 13):
        monthly_data[month] = {"month": month, "month_name": month_names[month-1], "total": 0, "count": 0}
    
    for order in orders:
        try:
            order_time = datetime.fromisoformat(order.get("created_at", "").replace("Z", "+00:00"))
            # Convert to Brazil timezone to get correct month
            order_time_brazil = order_time.astimezone(brazil_tz)
            month = order_time_brazil.month
            monthly_data[month]["total"] += order.get("total", 0)
            monthly_data[month]["count"] += 1
        except:
            pass
    
    # Convert to sorted list
    chart_data = sorted(monthly_data.values(), key=lambda x: x["month"])
    
    return {
        "year": target_year,
        "data": chart_data,
        "total_year": sum(d["total"] for d in chart_data),
        "total_orders": sum(d["count"] for d in chart_data)
    }

@api_router.get("/gestor/chart/weekly")
async def get_weekly_chart_data(date: str = None, store: str = None, username: str = Depends(verify_gestor)):
    """Get daily sales data for the 7 days ending on `date` (or today). Each bar = one day."""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)

    # Parse date or use today (in Brazil timezone)
    if date:
        try:
            ref = datetime.strptime(date, "%Y-%m-%d")
            ref = brazil_tz.localize(ref)
        except Exception:
            ref = now_brazil
    else:
        ref = now_brazil

    # Define 7-day window ending on `ref` (inclusive)
    end_day = ref.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    start_day = end_day - timedelta(days=7)

    start_utc = start_day.astimezone(pytz.UTC)
    end_utc = end_day.astimezone(pytz.UTC)

    # Build base query (status + exclude prazo, optionally filter store)
    query = {
        "status": {"$in": ["ready", "delivered", "received"]},
        "payment_method": {"$ne": "prazo"},
        "created_at": {"$gte": start_utc.isoformat(), "$lt": end_utc.isoformat()},
    }
    if store and store != "all":
        query["store"] = store

    orders = await db.orders.find(query, {"_id": 0, "created_at": 1, "total": 1, "store": 1, "payment_method": 1}).to_list(50000)

    # PIX manual adjustments within the window (use UTC for safety since
    # records may have been stored with mixed timezone formats over time)
    pix_query = {
        "removed": {"$ne": True},
        "created_at": {"$gte": start_utc.isoformat(), "$lt": end_utc.isoformat()},
    }
    if store and store != "all":
        pix_query["store"] = store
    pix_adjustments = await db.pix_adjustments.find(pix_query, {"_id": 0}).to_list(10000)

    # Prazo payments (counted as cash flow on the day they were paid)
    prazo_query = {"created_at": {"$gte": start_utc.isoformat(), "$lt": end_utc.isoformat()}}
    if store and store != "all":
        prazo_query["store"] = store
    prazo_full = await db.prazo_payments.find(prazo_query, {"_id": 0}).to_list(10000)
    prazo_partial = await db.prazo_partial_payments.find(prazo_query, {"_id": 0}).to_list(10000)

    # Init day buckets — keep order from oldest to most recent (left → right in chart)
    weekday_short = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    daily_data = {}
    for i in range(7):
        d = start_day + timedelta(days=i)
        key = d.strftime("%Y-%m-%d")
        daily_data[key] = {
            "date": key,
            "day": d.day,
            "day_name": weekday_short[d.weekday()],
            "label": f"{weekday_short[d.weekday()]} {d.day:02d}/{d.month:02d}",
            "total": 0,
            "count": 0,
            "runner": 0,
            "runner_count": 0,
            "gym_londres": 0,
            "gym_londres_count": 0,
        }

    by_payment = {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "voucher": 0}

    for order in orders:
        try:
            ot = datetime.fromisoformat(order.get("created_at", "").replace("Z", "+00:00")).astimezone(brazil_tz)
            key = ot.strftime("%Y-%m-%d")
            if key not in daily_data:
                continue
            t = order.get("total", 0)
            st = order.get("store", "")
            pm = order.get("payment_method", "cash")
            daily_data[key]["total"] += t
            daily_data[key]["count"] += 1
            if st == "runner":
                daily_data[key]["runner"] += t
                daily_data[key]["runner_count"] += 1
            elif st == "gym-londres":
                daily_data[key]["gym_londres"] += t
                daily_data[key]["gym_londres_count"] += 1
            by_payment[pm] = by_payment.get(pm, 0) + t
        except Exception:
            pass

    for adj in pix_adjustments:
        try:
            at = datetime.fromisoformat(adj.get("created_at", "").replace("Z", "+00:00")).astimezone(brazil_tz)
            key = at.strftime("%Y-%m-%d")
            if key not in daily_data:
                continue
            amt = adj.get("amount", 0)
            st = adj.get("store", "")
            daily_data[key]["total"] += amt
            if st == "runner":
                daily_data[key]["runner"] += amt
            elif st == "gym-londres":
                daily_data[key]["gym_londres"] += amt
            by_payment["pix"] += amt
        except Exception:
            pass

    for p in prazo_full + prazo_partial:
        try:
            pt = datetime.fromisoformat(p.get("created_at", "").replace("Z", "+00:00")).astimezone(brazil_tz)
            key = pt.strftime("%Y-%m-%d")
            if key not in daily_data:
                continue
            amt = p.get("amount", 0)
            st = p.get("store", "runner")
            pm = p.get("payment_method", "cash")
            daily_data[key]["total"] += amt
            daily_data[key]["count"] += 1
            if st == "runner":
                daily_data[key]["runner"] += amt
                daily_data[key]["runner_count"] += 1
            elif st == "gym-londres":
                daily_data[key]["gym_londres"] += amt
                daily_data[key]["gym_londres_count"] += 1
            by_payment[pm] = by_payment.get(pm, 0) + amt
        except Exception:
            pass

    chart_data = sorted(daily_data.values(), key=lambda x: x["date"])
    total_runner = sum(d["runner"] for d in chart_data)
    total_gym = sum(d["gym_londres"] for d in chart_data)

    return {
        "start": start_day.strftime("%d/%m/%Y"),
        "end": (end_day - timedelta(days=1)).strftime("%d/%m/%Y"),
        "data": chart_data,
        "total_week": round(sum(d["total"] for d in chart_data), 2),
        "total_orders": sum(d["count"] for d in chart_data),
        "by_store": {
            "runner": {"total": round(total_runner, 2), "orders": sum(d["runner_count"] for d in chart_data)},
            "gym_londres": {"total": round(total_gym, 2), "orders": sum(d["gym_londres_count"] for d in chart_data)},
        },
        "by_payment": {
            "pix": round(by_payment.get("pix", 0), 2),
            "debito": round(by_payment.get("debit", 0), 2),
            "credito": round(by_payment.get("credit", 0), 2),
            "dinheiro": round(by_payment.get("cash", 0), 2),
            "voucher": round(by_payment.get("voucher", 0), 2),
        },
    }

# ==================== MANUAL SALES ENDPOINTS ====================
class ManualSalePayload(BaseModel):
    store: str
    payment_method: str
    amount: float
    period: str = "manha"
    description: str = ""
    date: Optional[str] = None  # YYYY-MM-DD

@api_router.post("/gestor/manual-sale")
async def create_manual_sale(payload: ManualSalePayload, username: str = Depends(verify_gestor)):
    """Register a manual sale (shift/morning totals not entered as individual orders).
    Stored as a regular order with status=delivered + flag manual_sale=True so the gestor
    can later list/delete it. Counts in dashboard KPIs and cash drawer like any real order.
    """
    if payload.store not in ("runner", "gym-londres"):
        raise HTTPException(400, "Loja inválida")
    if payload.payment_method not in ("cash", "pix", "credit", "debit", "voucher"):
        raise HTTPException(400, "Forma de pagamento inválida")
    if payload.amount is None or payload.amount <= 0:
        raise HTTPException(400, "O valor deve ser maior que zero")
    if payload.period not in ("manha", "tarde", "noite"):
        raise HTTPException(400, "Turno inválido")

    period_hours = {"manha": 9, "tarde": 14, "noite": 20}
    hour = period_hours[payload.period]

    brazil_tz = pytz.timezone("America/Sao_Paulo")
    if payload.date:
        try:
            base = datetime.strptime(payload.date, "%Y-%m-%d")
            base = brazil_tz.localize(base.replace(hour=hour))
        except Exception:
            raise HTTPException(400, "Data inválida — use AAAA-MM-DD")
    else:
        base = datetime.now(brazil_tz).replace(hour=hour, minute=0, second=0, microsecond=0)
    created_utc = base.astimezone(timezone.utc)

    payment_labels = {"cash": "Dinheiro", "pix": "PIX", "credit": "Crédito", "debit": "Débito", "voucher": "Voucher"}
    period_labels = {"manha": "Manhã", "tarde": "Tarde", "noite": "Noite"}
    label = f"Venda manual ({period_labels[payload.period]} – {payment_labels[payload.payment_method]})"

    order = {
        "id": str(uuid.uuid4()),
        "store": payload.store,
        "customer_name": payload.description.strip() or label,
        "items": [{
            "menu_item_id": "manual-sale",
            "name": label,
            "category": "Outros",
            "price": float(payload.amount),
            "quantity": 1,
        }],
        "total": float(payload.amount),
        "original_total": float(payload.amount),
        "payment_method": payload.payment_method,
        "pickup_time": payload.period,
        "status": "delivered",
        "created_at": created_utc.isoformat(),
        "delivered_at": created_utc.isoformat(),
        "manual_sale": True,
        "created_by_gestor": username,
    }
    await db.orders.insert_one(order)
    return {"success": True, "order_id": order["id"], "amount": order["total"], "store": order["store"]}


@api_router.get("/gestor/manual-sales")
async def list_manual_sales(limit: int = 100, username: str = Depends(verify_gestor)):
    """List manual sales registered via /gestor/manual-sale (most recent first)."""
    sales = await db.orders.find(
        {"manual_sale": True},
        {"_id": 0, "id": 1, "store": 1, "customer_name": 1, "total": 1,
         "payment_method": 1, "pickup_time": 1, "created_at": 1}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"sales": sales}


@api_router.delete("/gestor/manual-sale/{order_id}")
async def delete_manual_sale(order_id: str, username: str = Depends(verify_gestor)):
    """Delete a manual sale by id (only if flagged manual_sale=True — protects real orders)."""
    r = await db.orders.delete_one({"id": order_id, "manual_sale": True})
    if r.deleted_count == 0:
        raise HTTPException(404, "Venda manual não encontrada")
    return {"success": True}


# ==================== SALES BY CATEGORY ====================

@api_router.get("/gestor/sales-by-category")
async def get_sales_by_category(username: str = Depends(verify_gestor)):
    """Get sales data grouped by product category for the current month"""
    # Use Brazil timezone
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now_brazil = datetime.now(brazil_tz)
    month_start_brazil = now_brazil.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_start_utc = month_start_brazil.astimezone(pytz.UTC)
    
    # Get all completed orders this month
    orders = await db.orders.find({
        "status": {"$in": ["ready", "delivered"]},
        "created_at": {"$gte": month_start_utc.isoformat()}
    }, {"_id": 0, "items": 1, "total": 1, "store": 1}).to_list(10000)
    
    # Group by category
    category_sales = {}
    
    # Build a map of item IDs to categories from MENU_DATA
    item_category_map = {item["id"]: item["category"] for item in MENU_DATA}
    
    for order in orders:
        for item in order.get("items", []):
            # Get category from item or lookup
            item_id = item.get("menu_item_id", "").split("-")[0]  # Remove adicional suffix
            category = item.get("category") or item_category_map.get(item_id, "Outros")
            
            if category not in category_sales:
                category_sales[category] = {
                    "category": category,
                    "count": 0,
                    "revenue": 0,
                    "items": {}
                }
            
            qty = item.get("quantity", 1)
            item_total = item.get("price", 0) * qty
            
            category_sales[category]["count"] += qty
            category_sales[category]["revenue"] += item_total
            
            # Track individual items
            item_name = item.get("name", "Desconhecido")
            if item_name not in category_sales[category]["items"]:
                category_sales[category]["items"][item_name] = {"count": 0, "revenue": 0}
            category_sales[category]["items"][item_name]["count"] += qty
            category_sales[category]["items"][item_name]["revenue"] += item_total
    
    # Convert to sorted list
    categories_list = sorted(category_sales.values(), key=lambda x: x["count"], reverse=True)
    
    # Convert items dict to sorted list for each category
    for cat in categories_list:
        cat["top_items"] = sorted(
            [{"name": k, **v} for k, v in cat["items"].items()],
            key=lambda x: x["count"],
            reverse=True
        )[:10]  # Top 10 items per category
        del cat["items"]  # Remove the dict version
    
    return {
        "month": now_brazil.strftime("%B %Y"),
        "categories": categories_list,
        "total_items_sold": sum(c["count"] for c in categories_list),
        "total_revenue": sum(c["revenue"] for c in categories_list)
    }

# ==================== MENU MANAGEMENT ====================

class MenuItemCreate(BaseModel):
    name: str
    description: str = ""
    price: float
    category: str
    store: str
    image_url: str = ""

class MenuItemUpdate(BaseModel):
    name: str = None
    description: str = None
    price: float = None
    category: str = None
    image_url: str = None
    available: bool = None

@api_router.get("/gestor/menu/{store}")
async def get_store_menu(store: StoreLocation, username: str = Depends(verify_gestor)):
    """Get menu items for a store"""
    menu = await db.menu.find({"store": store.value}, {"_id": 0}).to_list(500)
    return {"menu": menu, "count": len(menu)}

@api_router.post("/gestor/menu")
async def create_menu_item(item: MenuItemCreate, username: str = Depends(verify_gestor)):
    """Create a new menu item in BOTH stores"""
    base_id = str(uuid.uuid4())
    stores = ["runner", "gym-londres"]
    created_items = []
    
    for store in stores:
        menu_item = {
            "id": f"{base_id}-{store}",
            "name": item.name,
            "description": item.description,
            "price": item.price,
            "category": item.category,
            "store": store,
            "image_url": item.image_url,
            "available": True,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.menu.insert_one(menu_item)
        
        # Also add to stock with default quantity
        await db.stock.insert_one({
            "store": store,
            "menu_item_id": menu_item["id"],
            "name": item.name,
            "category": item.category,
            "quantity": 50,
            "low_stock": False
        })
        created_items.append(menu_item)
    
    return {"success": True, "items": [{**i, "_id": None} for i in created_items], "message": "Item adicionado em ambas as lojas!"}

@api_router.put("/gestor/menu/{item_id}")
async def update_menu_item(item_id: str, update: MenuItemUpdate, username: str = Depends(verify_gestor)):
    """Update a menu item"""
    update_data = {k: v for k, v in update.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar")
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.menu.update_one({"id": item_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    
    # Update stock name if name changed
    if "name" in update_data:
        await db.stock.update_many({"menu_item_id": item_id}, {"$set": {"name": update_data["name"]}})
    
    return {"success": True, "message": "Item atualizado"}

@api_router.delete("/gestor/menu/{item_id}")
async def delete_menu_item(item_id: str, username: str = Depends(verify_gestor)):
    """Delete a menu item"""
    result = await db.menu.delete_one({"id": item_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    
    # Also remove from stock
    await db.stock.delete_many({"menu_item_id": item_id})
    
    return {"success": True, "message": "Item removido"}

# ==================== ADICIONAIS ROUTES ====================

class AdicionalCreate(BaseModel):
    name: str
    price: float

class AdicionalUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[float] = None

@api_router.get("/gestor/adicionais")
async def get_adicionais(username: str = Depends(verify_gestor)):
    """Get all adicionais (custom + default)"""
    custom_adicionais = await db.adicionais.find({}, {"_id": 0}).to_list(100)
    # Merge with default, custom ones override defaults with same id
    all_adicionais = list(ADICIONAIS)
    for custom in custom_adicionais:
        # Check if it's an update to an existing adicional
        existing_idx = next((i for i, a in enumerate(all_adicionais) if a["id"] == custom.get("id")), None)
        if existing_idx is not None:
            all_adicionais[existing_idx] = custom
        else:
            all_adicionais.append(custom)
    return {"adicionais": all_adicionais}

@api_router.post("/gestor/adicionais")
async def create_adicional(adicional: AdicionalCreate, username: str = Depends(verify_gestor)):
    """Create a new adicional"""
    import uuid
    new_adicional = {
        "id": str(uuid.uuid4())[:8],
        "name": adicional.name,
        "price": adicional.price,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.adicionais.insert_one(new_adicional)
    return {"success": True, "adicional": {**new_adicional, "_id": None}, "message": "Adicional criado!"}

@api_router.put("/gestor/adicionais/{adicional_id}")
async def update_adicional(adicional_id: str, update: AdicionalUpdate, username: str = Depends(verify_gestor)):
    """Update an adicional"""
    update_data = {k: v for k, v in update.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar")
    
    result = await db.adicionais.update_one({"id": adicional_id}, {"$set": update_data}, upsert=True)
    return {"success": True, "message": "Adicional atualizado"}

@api_router.delete("/gestor/adicionais/{adicional_id}")
async def delete_adicional(adicional_id: str, username: str = Depends(verify_gestor)):
    """Delete an adicional"""
    result = await db.adicionais.delete_one({"id": adicional_id})
    return {"success": True, "message": "Adicional removido"}

# ==================== PRAZO (CREDIT/TAB) MANAGEMENT ====================
# Configurable via env var so the default can be rotated easily.
PRAZO_PASSWORD = os.environ.get("PRAZO_PASSWORD", "1234")

class PrazoCustomerCreate(BaseModel):
    name: str
    phone: str = ""
    notes: str = ""
    credit: float = 0.0  # Crédito na casa (valor adiantado)
    store: str = ""  # Loja onde o cliente foi cadastrado

class PrazoPayment(BaseModel):
    amount: float
    password: str
    payment_method: str = "cash"  # cash, debit, credit, pix

class PrazoCreditAdd(BaseModel):
    amount: float  # Valor a adicionar ao crédito
    notes: Optional[str] = ""

class PrazoAbaterRequest(BaseModel):
    amount: float  # Valor a abater da dívida
    password: str  # Senha de confirmação
    payment_method: str = "cash"  # cash, debit, credit, pix

# ==================== KITCHEN MANAGEMENT ENDPOINTS (No auth required) ====================
# These endpoints allow the kitchen to manage adicionais, menu items, and prazo

@api_router.get("/kitchen/adicionais")
async def get_adicionais_kitchen():
    """Get all adicionais for kitchen view"""
    adicionais = await db.adicionais.find({}, {"_id": 0}).to_list(500)
    return {"adicionais": adicionais}

@api_router.post("/kitchen/adicionais")
async def create_adicional_kitchen(adicional: AdicionalCreate):
    """Create new adicional from kitchen"""
    new_adicional = {
        "id": str(uuid.uuid4()),
        "name": adicional.name,
        "price": adicional.price,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.adicionais.insert_one(new_adicional)
    return {**new_adicional, "_id": None}

@api_router.put("/kitchen/adicionais/{adicional_id}")
async def update_adicional_kitchen(adicional_id: str, update: AdicionalUpdate):
    """Update adicional from kitchen"""
    await db.adicionais.update_one({"id": adicional_id}, {"$set": {"name": update.name, "price": update.price}})
    return {"success": True}

@api_router.delete("/kitchen/adicionais/{adicional_id}")
async def delete_adicional_kitchen(adicional_id: str):
    """Delete adicional from kitchen"""
    await db.adicionais.delete_one({"id": adicional_id})
    return {"success": True, "message": "Adicional removido"}

@api_router.get("/kitchen/menu/{store}")
async def get_menu_kitchen(store: StoreLocation):
    """Get all menu items for kitchen management"""
    custom_items = await db.menu.find({"store": store.value}, {"_id": 0}).to_list(500)
    return {"items": custom_items}

@api_router.post("/kitchen/menu")
async def create_menu_item_kitchen(item: MenuItem):
    """Create new menu item from kitchen"""
    item_dict = item.model_dump()
    item_dict["created_at"] = datetime.now(timezone.utc).isoformat()
    await db.menu.insert_one(item_dict)
    return {**item_dict, "_id": None}

@api_router.put("/kitchen/menu/{item_id}")
async def update_menu_item_kitchen(item_id: str, item: MenuItem):
    """Update menu item from kitchen"""
    update_data = item.model_dump(exclude_unset=True)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.menu.update_one({"id": item_id}, {"$set": update_data})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Item não encontrado")
    return {"success": True}

@api_router.delete("/kitchen/menu/{item_id}")
async def delete_menu_item_kitchen(item_id: str):
    """Delete menu item from kitchen"""
    result = await db.menu.delete_one({"id": item_id})
    return {"success": True, "message": "Item removido"}

@api_router.post("/kitchen/prazo/customers")
async def create_prazo_customer_kitchen(customer: PrazoCustomerCreate):
    """Register a new prazo customer from kitchen"""
    # Verificar por nome E loja
    existing = await db.prazo_customers.find_one({
        "name": {"$regex": f"^{re.escape(customer.name)}$", "$options": "i"},
        "store": customer.store
    })
    if existing:
        raise HTTPException(status_code=400, detail="Cliente já cadastrado nesta loja")
    
    new_customer = {
        "id": str(uuid.uuid4()),
        "name": customer.name,
        "phone": customer.phone,
        "notes": customer.notes,
        "store": customer.store,
        "credit": customer.credit,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.prazo_customers.insert_one(new_customer)
    return {**new_customer, "_id": None}

@api_router.delete("/kitchen/prazo/customers/{customer_id}")
async def delete_prazo_customer_kitchen(customer_id: str):
    """Delete prazo customer from kitchen"""
    result = await db.prazo_customers.delete_one({"id": customer_id})
    return {"success": True, "message": "Cliente removido"}

@api_router.put("/kitchen/prazo/customers/{customer_id}")
async def update_prazo_customer(customer_id: str, data: dict):
    """Update prazo customer information"""
    update_data = {}
    if "name" in data and data["name"]:
        update_data["name"] = data["name"]
    if "phone" in data:
        update_data["phone"] = data["phone"]
    if "notes" in data:
        update_data["notes"] = data["notes"]
    
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum dado para atualizar")
    
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    result = await db.prazo_customers.update_one(
        {"id": customer_id},
        {"$set": update_data}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    return {"success": True, "message": "Cliente atualizado"}

@api_router.get("/prazo/customers")
async def get_prazo_customers(store: str = None):
    """Get all registered prazo customers, optionally filtered by store"""
    query = {}
    if store:
        query["store"] = store
    customers = await db.prazo_customers.find(query, {"_id": 0}).to_list(500)
    return {"customers": customers}

@api_router.post("/prazo/customers")
async def create_prazo_customer(customer: PrazoCustomerCreate, username: str = Depends(verify_gestor)):
    """Register a new prazo customer"""
    # Check if customer already exists IN THIS STORE
    # (Same name allowed in different stores - e.g. "Paulão" can exist in both Runner and GYM Londres)
    existing = await db.prazo_customers.find_one({
        "name": {"$regex": f"^{re.escape(customer.name)}$", "$options": "i"},
        "store": customer.store
    })
    if existing:
        raise HTTPException(status_code=400, detail="Cliente já cadastrado nesta loja")
    
    new_customer = {
        "id": str(uuid.uuid4()),
        "name": customer.name,
        "phone": customer.phone,
        "notes": customer.notes,
        "credit": customer.credit,
        "store": customer.store,
        "total_debt": 0,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.prazo_customers.insert_one(new_customer)
    return {**new_customer, "_id": None}

@api_router.delete("/prazo/customers/{customer_id}")
async def delete_prazo_customer(customer_id: str, username: str = Depends(verify_gestor)):
    """Delete a prazo customer"""
    result = await db.prazo_customers.delete_one({"id": customer_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return {"success": True, "message": "Cliente removido"}

@api_router.get("/prazo/debts")
async def get_prazo_debts(store: Optional[str] = None):
    """Get prazo debts summary - optionally filtered by store"""
    # Build query
    query = {
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True}
    }
    if store:
        query["store"] = store
    
    # Get unpaid prazo orders
    prazo_orders = await db.orders.find(query, {"_id": 0}).to_list(1000)
    
    # Get all prazo customers to lookup phones
    prazo_customers = await db.prazo_customers.find({}, {"_id": 0, "name": 1, "phone": 1}).to_list(1000)
    customer_phones = {c.get("name", "").lower(): c.get("phone", "") for c in prazo_customers}
    
    # Group by customer name
    debts_by_customer = {}
    for order in prazo_orders:
        name = order.get("customer_name", "Desconhecido")
        order_store = order.get("store", "")
        order_total = order.get("total", 0)
        partial_paid = order.get("partial_paid", 0)  # Consider partial payments
        remaining = order_total - partial_paid
        
        if remaining <= 0:
            continue  # Skip fully paid orders
        
        if name not in debts_by_customer:
            # Look up phone by customer name (case insensitive)
            phone = customer_phones.get(name.lower(), "")
            debts_by_customer[name] = {"name": name, "total": 0, "orders": [], "order_count": 0, "store": order_store, "phone": phone}
        debts_by_customer[name]["total"] += remaining  # Use remaining amount
        debts_by_customer[name]["order_count"] += 1
        debts_by_customer[name]["orders"].append({
            "id": order.get("id"),
            "total": order_total,
            "partial_paid": partial_paid,
            "remaining": remaining,
            "date": order.get("created_at"),
            "items": order.get("items", []),
            "store": order_store
        })
    
    # Sort by total debt descending
    debts = sorted(debts_by_customer.values(), key=lambda x: x["total"], reverse=True)
    total_prazo = sum(d["total"] for d in debts)
    
    return {
        "debts": debts,
        "total_prazo": total_prazo,
        "customer_count": len(debts),
        "store_filter": store or "all"
    }

@api_router.post("/prazo/pay/{order_id}")
async def pay_prazo_order(order_id: str, payment: PrazoPayment):
    """Mark a prazo order as paid (requires password)"""
    if payment.password != PRAZO_PASSWORD:
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    result = await db.orders.update_one(
        {"id": order_id, "payment_method": "prazo"},
        {"$set": {"prazo_paid": True, "prazo_paid_at": datetime.now(timezone.utc).isoformat(), "prazo_paid_amount": payment.amount}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido não encontrado")
    
    return {"success": True, "message": "Pagamento registrado"}

@api_router.post("/prazo/pay-all/{customer_name}")
async def pay_all_prazo_customer(customer_name: str, payment: PrazoPayment):
    """Mark all prazo orders for a customer as paid (requires password)"""
    if payment.password != PRAZO_PASSWORD:
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    # Get the store from the first unpaid order
    first_order = await db.orders.find_one(
        {"customer_name": customer_name, "payment_method": "prazo", "prazo_paid": {"$ne": True}},
        {"store": 1}
    )
    customer_store = first_order.get("store", "runner") if first_order else "runner"
    
    result = await db.orders.update_many(
        {"customer_name": customer_name, "payment_method": "prazo", "prazo_paid": {"$ne": True}},
        {"$set": {
            "prazo_paid": True, 
            "prazo_paid_at": datetime.now(timezone.utc).isoformat(),
            "prazo_paid_method": payment.payment_method  # How the prazo was paid
        }}
    )
    
    # Log the payment
    payment_record = {
        "id": str(uuid.uuid4()),
        "customer_name": customer_name,
        "amount": payment.amount,
        "payment_method": payment.payment_method,
        "type": "full_payment",
        "store": customer_store,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.prazo_payments.insert_one(payment_record)
    
    return {"success": True, "message": f"Todos os débitos de {customer_name} foram quitados ({payment.payment_method})", "orders_paid": result.modified_count}

@api_router.delete("/prazo/debt/{customer_name}")
async def delete_prazo_debt(customer_name: str, password: str = None):
    """Delete/clear all prazo debts for a customer (marks as paid without recording payment)"""
    if password != PRAZO_PASSWORD:
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    # Mark all unpaid prazo orders for this customer as paid (zeroing the debt)
    result = await db.orders.update_many(
        {"customer_name": customer_name, "payment_method": "prazo", "prazo_paid": {"$ne": True}},
        {"$set": {"prazo_paid": True, "prazo_paid_at": datetime.now(timezone.utc).isoformat(), "prazo_cleared": True}}
    )
    
    return {
        "success": True,
        "message": f"Dívida de {customer_name} zerada",
        "orders_cleared": result.modified_count
    }

@api_router.get("/prazo/payments-history")
async def get_prazo_payments_history(store: str = None, limit: int = 100):
    """Get history of prazo payments (full and partial)"""
    query = {}
    if store:
        query["store"] = store
    
    # Get full payments
    full_payments = await db.prazo_payments.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    
    # Get partial payments
    partial_payments = await db.prazo_partial_payments.find(query, {"_id": 0}).sort("created_at", -1).to_list(limit)
    
    # Combine and sort by date
    all_payments = full_payments + partial_payments
    all_payments.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    
    # Calculate totals by payment method
    totals = {"cash": 0, "pix": 0, "debit": 0, "credit": 0}
    for p in all_payments:
        method = p.get("payment_method", "cash")
        if method in totals:
            totals[method] += p.get("amount", 0)
    
    return {
        "payments": all_payments[:limit],
        "total_count": len(all_payments),
        "totals_by_method": totals,
        "grand_total": sum(totals.values())
    }

@api_router.delete("/prazo/debt-order/{order_id}")
async def delete_single_prazo_debt(order_id: str, password: str = None):
    """Delete/clear a single prazo debt order"""
    if password != PRAZO_PASSWORD:
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    result = await db.orders.update_one(
        {"id": order_id, "payment_method": "prazo", "prazo_paid": {"$ne": True}},
        {"$set": {"prazo_paid": True, "prazo_paid_at": datetime.now(timezone.utc).isoformat(), "prazo_cleared": True}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Pedido não encontrado ou já pago")
    
    return {"success": True, "message": "Dívida apagada"}

@api_router.post("/prazo/customers/{customer_id}/add-credit")
async def add_prazo_credit(customer_id: str, credit_data: PrazoCreditAdd):
    """Add credit to a prazo customer's account.
    AUTO-APPLY behaviour:
      1. The amount first settles UNPAID prazo orders (FIFO — oldest first).
         Each order has its `partial_paid` increased; when fully covered it
         is marked `prazo_paid=True`.
      2. Whatever is left over goes to the customer's `credit` balance.
      3. Result: customer never has BOTH a debt AND a positive credit at once.
    """
    customer = await db.prazo_customers.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")

    amount = float(credit_data.amount or 0)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Valor deve ser maior que zero")

    name = customer["name"]
    previous_credit = float(customer.get("credit", 0) or 0)

    unpaid_orders = await db.orders.find(
        {
            "customer_name": {"$regex": f"^{re.escape(name)}$", "$options": "i"},
            "payment_method": "prazo",
            "prazo_paid": {"$ne": True},
        },
        {"_id": 0, "id": 1, "total": 1, "partial_paid": 1, "created_at": 1, "store": 1},
    ).sort("created_at", 1).to_list(1000)

    remaining = amount
    applied_to_debt = 0.0
    orders_paid_off = 0
    payment_records = []

    for order in unpaid_orders:
        if remaining <= 0:
            break
        already_paid = float(order.get("partial_paid", 0) or 0)
        order_total = float(order.get("total", 0) or 0)
        debt = round(order_total - already_paid, 2)
        if debt <= 0:
            continue
        apply = round(min(remaining, debt), 2)
        new_partial = round(already_paid + apply, 2)
        is_paid = new_partial >= round(order_total - 0.005, 2)

        update_set = {"partial_paid": new_partial}
        if is_paid:
            update_set["prazo_paid"] = True
            update_set["paid_at"] = datetime.now(timezone.utc).isoformat()
            orders_paid_off += 1

        await db.orders.update_one({"id": order["id"]}, {"$set": update_set})

        payment_records.append({
            "id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "customer_name": name,
            "store": order.get("store", customer.get("store", "")),
            "order_id": order["id"],
            "amount": apply,
            "type": "partial_payment",
            "source": "credit_auto_apply",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "notes": credit_data.notes or "Abate automático ao adicionar crédito",
        })

        remaining = round(remaining - apply, 2)
        applied_to_debt = round(applied_to_debt + apply, 2)

    if payment_records:
        await db.prazo_partial_payments.insert_many(payment_records)

    new_credit = round(previous_credit + remaining, 2)
    await db.prazo_customers.update_one(
        {"id": customer_id},
        {"$set": {"credit": new_credit}},
    )

    # Audit log entry (mirrors routers/prazo.py _log_prazo_event)
    try:
        notes_parts = []
        if applied_to_debt > 0:
            notes_parts.append(
                f"Abatido R$ {applied_to_debt:.2f} de {orders_paid_off} pedido(s) liquidados"
                if orders_paid_off
                else f"Abatido R$ {applied_to_debt:.2f} em pedido(s) pendente(s)"
            )
        if remaining > 0:
            notes_parts.append(f"R$ {remaining:.2f} para o saldo de crédito")
        if credit_data.notes:
            notes_parts.append(credit_data.notes)
        await db.prazo_history.insert_one({
            "id": str(uuid.uuid4()),
            "customer_id": customer_id,
            "customer_name": name,
            "store": customer.get("store", ""),
            "event_type": "credit_added",
            "amount": float(amount),
            "previous_credit": float(previous_credit),
            "new_credit": float(new_credit),
            "credit_generated": float(remaining),
            "notes": " | ".join(notes_parts) if notes_parts else None,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as _e:
        logger.warning(f"prazo_history insert failed: {_e}")

    if applied_to_debt > 0 and remaining > 0:
        msg = (
            f"R$ {amount:.2f} adicionados! Abatido R$ {applied_to_debt:.2f} da dívida "
            f"e R$ {remaining:.2f} foi para o saldo (atual: R$ {new_credit:.2f})."
        )
    elif applied_to_debt > 0:
        msg = (
            f"R$ {amount:.2f} adicionados — abateu R$ {applied_to_debt:.2f} da dívida"
            + (f" ({orders_paid_off} pedido(s) quitado(s))" if orders_paid_off else "")
            + f". Saldo de crédito: R$ {new_credit:.2f}"
        )
    else:
        msg = f"Crédito adicionado! Saldo: R$ {new_credit:.2f}"

    return {
        "success": True,
        "message": msg,
        "previous_credit": previous_credit,
        "added": amount,
        "applied_to_debt": applied_to_debt,
        "orders_paid_off": orders_paid_off,
        "remaining_credit_added": remaining,
        "new_credit": new_credit,
    }

@api_router.post("/prazo/customers/{customer_id}/use-credit")
async def use_prazo_credit(customer_id: str, credit_data: PrazoCreditAdd):
    """Use credit from a prazo customer's account"""
    customer = await db.prazo_customers.find_one({"id": customer_id})
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    current_credit = customer.get("credit", 0)
    if credit_data.amount > current_credit:
        raise HTTPException(status_code=400, detail=f"Crédito insuficiente. Saldo: R$ {current_credit:.2f}")
    
    new_credit = current_credit - credit_data.amount
    
    await db.prazo_customers.update_one(
        {"id": customer_id},
        {"$set": {"credit": new_credit}}
    )
    
    return {
        "success": True, 
        "message": f"Crédito utilizado! Novo saldo: R$ {new_credit:.2f}",
        "previous_credit": current_credit,
        "used": credit_data.amount,
        "new_credit": new_credit
    }

@api_router.post("/prazo/abater/{customer_name}")
async def abater_prazo_debt(customer_name: str, abater_data: PrazoAbaterRequest):
    """
    Abater (partial payment) on a prazo customer's debt.
    This reduces the total debt by the specified amount.
    If the customer has credit, it will be reduced by the payment amount.
    The partial payment is recorded as a payment applied to the oldest orders first.
    """
    if abater_data.password != PRAZO_PASSWORD:
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    # Get unpaid prazo orders for this customer
    prazo_orders = await db.orders.find({
        "customer_name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"},
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True}
    }, {"_id": 0}).sort("created_at", 1).to_list(1000)  # Oldest first
    
    if not prazo_orders:
        raise HTTPException(status_code=404, detail="Cliente não tem dívidas no prazo")
    
    # Calculate total debt
    total_debt = sum(o.get("total", 0) - o.get("partial_paid", 0) for o in prazo_orders)
    
    if abater_data.amount <= 0:
        raise HTTPException(status_code=400, detail="Valor deve ser maior que zero")
    
    if abater_data.amount > total_debt:
        raise HTTPException(status_code=400, detail=f"Valor maior que a dívida total (R$ {total_debt:.2f})")
    
    # Check if customer has credit (only consume when payment_method == 'saldo')
    customer = await db.prazo_customers.find_one({
        "name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"}
    })
    
    previous_credit = 0
    new_credit = 0
    credit_used = 0
    
    # FIX: Credit balance is the customer's pre-paid money. It should ONLY be reduced
    # when payment_method == 'saldo' (explicit choice to pay using customer credit).
    # For cash/pix/debit/credit-card, the credit balance must NOT be touched -
    # the customer is paying with REAL money.
    if abater_data.payment_method == "saldo" and customer and customer.get("credit", 0) > 0:
        previous_credit = customer.get("credit", 0)
        credit_used = min(abater_data.amount, previous_credit)
        new_credit = previous_credit - credit_used
        
        if credit_used < abater_data.amount:
            raise HTTPException(
                status_code=400,
                detail=f"Saldo a favor insuficiente. Disponível: R$ {previous_credit:.2f}, solicitado: R$ {abater_data.amount:.2f}"
            )
        
        await db.prazo_customers.update_one(
            {"id": customer["id"]},
            {"$set": {"credit": new_credit}}
        )
    
    # Apply payment to orders, oldest first
    remaining_payment = abater_data.amount
    orders_updated = 0
    orders_paid_off = 0
    
    for order in prazo_orders:
        if remaining_payment <= 0:
            break
            
        order_id = order.get("id")
        order_total = order.get("total", 0)
        already_paid = order.get("partial_paid", 0)
        order_remaining = order_total - already_paid
        
        if order_remaining <= 0:
            continue
        
        if remaining_payment >= order_remaining:
            # Pay off this order completely
            await db.orders.update_one(
                {"id": order_id},
                {"$set": {
                    "prazo_paid": True,
                    "prazo_paid_at": datetime.now(timezone.utc).isoformat(),
                    "prazo_paid_amount": order_total,
                    "partial_paid": order_total
                }}
            )
            remaining_payment -= order_remaining
            orders_paid_off += 1
        else:
            # Partial payment on this order
            new_partial = already_paid + remaining_payment
            await db.orders.update_one(
                {"id": order_id},
                {"$set": {"partial_paid": new_partial}}
            )
            remaining_payment = 0
        
        orders_updated += 1
    
    # Get the store from the first order
    customer_store = prazo_orders[0].get("store", "runner") if prazo_orders else "runner"
    
    # Log the partial payment
    payment_record = {
        "id": str(uuid.uuid4()),
        "customer_name": customer_name,
        "amount": abater_data.amount,
        "payment_method": abater_data.payment_method,
        "type": "partial_payment",
        "store": customer_store,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "orders_updated": orders_updated,
        "orders_paid_off": orders_paid_off,
        "credit_used": credit_used
    }
    await db.prazo_partial_payments.insert_one(payment_record)
    
    new_debt = total_debt - abater_data.amount
    
    response = {
        "success": True,
        "message": f"Pagamento de R$ {abater_data.amount:.2f} registrado!",
        "previous_debt": total_debt,
        "paid": abater_data.amount,
        "new_debt": new_debt,
        "orders_updated": orders_updated,
        "orders_paid_off": orders_paid_off
    }
    
    # Add credit info if customer had credit (only happens for payment_method='saldo')
    if credit_used > 0:
        response["credit_used"] = credit_used
        response["previous_credit"] = previous_credit
        response["new_credit"] = new_credit
        response["message"] = f"Pagamento de R$ {abater_data.amount:.2f} usando Saldo a Favor. Saldo restante: R$ {new_credit:.2f}"
    
    return response

@api_router.post("/prazo/charge-all-whatsapp")
async def charge_all_prazo_via_whatsapp(store: Optional[str] = None):
    """Send WhatsApp messages to all prazo customers with pending debts - sends to their phone number"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brazil_tz)
    
    # Build query
    query = {
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True}
    }
    if store:
        query["store"] = store
    
    # Get unpaid prazo orders
    prazo_orders = await db.orders.find(query, {"_id": 0}).to_list(10000)
    
    # Group by customer
    debts_by_customer = {}
    for order in prazo_orders:
        customer = order.get("customer_name", "")
        if customer not in debts_by_customer:
            debts_by_customer[customer] = {"total": 0, "orders": [], "phone": ""}
        debts_by_customer[customer]["total"] += order.get("total", 0)
        debts_by_customer[customer]["orders"].append(order)
    
    # Get customer phones
    customers = await db.prazo_customers.find({}, {"_id": 0}).to_list(500)
    customer_phones = {c.get("name"): c.get("phone", "") for c in customers}
    
    messages_sent = 0
    failed = []
    no_phone = []
    
    for customer_name, debt_info in debts_by_customer.items():
        if debt_info["total"] <= 0:
            continue
            
        phone = customer_phones.get(customer_name, "")
        
        # Skip if no phone
        if not phone:
            no_phone.append(customer_name)
            continue
        
        # Format phone for WhatsApp (remove non-digits, add country code if needed)
        phone_clean = ''.join(filter(str.isdigit, phone))
        if len(phone_clean) == 11:  # Brazilian mobile without country code
            phone_clean = "55" + phone_clean
        elif len(phone_clean) == 10:  # Brazilian landline without country code
            phone_clean = "55" + phone_clean
        
        phone_id = f"{phone_clean}@c.us"
        
        # Build nice message
        message = f"""━━━━━━━━━━━━━━━━━━
☕ *GANOH Café Bistrô*
━━━━━━━━━━━━━━━━━━

Olá, *{customer_name}*! 👋

Esperamos que esteja tudo bem!

Passando para lembrar do seu *saldo em aberto*:

┌─────────────────────
│ 💰 *Total: R$ {debt_info['total']:.2f}*
│ 📦 {len(debt_info['orders'])} pedido(s)
└─────────────────────

━━━━━━━━━━━━━━━━━━

✅ *Formas de pagamento:*
• PIX 📱
• Cartão (débito/crédito) 💳
• Dinheiro 💵

Quando puder, passe aqui! 😊🙏

_Mensagem automática - {now.strftime('%d/%m/%Y às %H:%M')}_"""

        # Send to customer's phone number
        try:
            result = await send_whatsapp_message(message, phone_id)
            if result.get("success"):
                messages_sent += 1
            else:
                failed.append(customer_name)
        except Exception as e:
            logger.error(f"Failed to send WhatsApp to {customer_name}: {e}")
            failed.append(customer_name)
    
    return {
        "success": True,
        "messages_sent": messages_sent,
        "failed": failed,
        "no_phone": no_phone,
        "total_customers": len(debts_by_customer),
        "message": f"Cobrança enviada para {messages_sent} cliente(s)" + (f" ({len(no_phone)} sem telefone)" if no_phone else "")
    }

@api_router.post("/prazo/charge-customer/{customer_name}")
async def charge_single_prazo_customer(customer_name: str):
    """Send WhatsApp message to a single prazo customer's phone number"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brazil_tz)
    
    # Get customer's unpaid orders
    prazo_orders = await db.orders.find({
        "customer_name": customer_name,
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True}
    }, {"_id": 0}).to_list(1000)
    
    if not prazo_orders:
        return {"success": False, "message": "Cliente não tem débitos pendentes"}
    
    total = sum(o.get("total", 0) for o in prazo_orders)
    
    # Get customer info
    customer = await db.prazo_customers.find_one({"name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"}})
    credit = customer.get("credit", 0) if customer else 0
    phone = customer.get("phone", "") if customer else ""
    
    # Check if customer has phone
    if not phone:
        return {"success": False, "message": "Cliente não tem telefone cadastrado"}
    
    # Format phone for WhatsApp
    phone_clean = ''.join(filter(str.isdigit, phone))
    if len(phone_clean) == 11:
        phone_clean = "55" + phone_clean
    elif len(phone_clean) == 10:
        phone_clean = "55" + phone_clean
    
    phone_id = f"{phone_clean}@c.us"
    
    # Build message
    items_detail = []
    for order in prazo_orders[-5:]:
        order_date = order.get("created_at", "")[:10]
        items_detail.append(f"  • {order_date}: R$ {order.get('total', 0):.2f}")
    
    if len(prazo_orders) > 5:
        items_detail.append(f"  ... e mais {len(prazo_orders) - 5} pedido(s)")
    
    credit_info = f"\n💳 *Crédito disponível: R$ {credit:.2f}*" if credit > 0 else ""
    net_debt = max(0, total - credit)
    
    message = f"""━━━━━━━━━━━━━━━━━━
☕ *GANOH Café Bistrô*
━━━━━━━━━━━━━━━━━━

Olá, *{customer_name}*! 👋

Esperamos que esteja tudo bem com você! 

Passando para enviar seu *extrato de consumo*:

┌─────────────────────
│ 💰 *Total: R$ {total:.2f}*{credit_info}
│ {'🔵 *A Pagar: R$ ' + f'{net_debt:.2f}*' if credit > 0 else ''}
└─────────────────────

📋 *Histórico de pedidos:*
{chr(10).join(items_detail)}

━━━━━━━━━━━━━━━━━━

✅ *Formas de pagamento:*
• PIX 📱
• Cartão (débito/crédito) 💳
• Dinheiro 💵

Aguardamos você! 😊🙏

_Mensagem automática - {now.strftime('%d/%m/%Y às %H:%M')}_"""

    # Send to customer's phone number
    result = await send_whatsapp_message(message, phone_id)
    
    return {
        "success": result.get("success", False),
        "message": f"Cobrança enviada para {customer_name}" if result.get("success") else "Falha ao enviar",
        "total_debt": total,
        "credit": credit,
        "net_debt": net_debt,
        "phone": phone
    }

@api_router.get("/prazo/charge-message/{customer_name}")
async def get_prazo_charge_message(customer_name: str):
    """Generate WhatsApp URL with pre-filled message for a single prazo customer"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brazil_tz)
    
    # Get customer's unpaid orders
    prazo_orders = await db.orders.find({
        "customer_name": customer_name,
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True}
    }, {"_id": 0}).to_list(1000)
    
    if not prazo_orders:
        raise HTTPException(status_code=404, detail="Cliente não tem débitos pendentes")
    
    total = sum(o.get("total", 0) for o in prazo_orders)
    
    # Get customer info
    customer = await db.prazo_customers.find_one({"name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"}})
    credit = customer.get("credit", 0) if customer else 0
    phone = customer.get("phone", "") if customer else ""
    
    if not phone:
        raise HTTPException(status_code=400, detail="Cliente não tem telefone cadastrado")
    
    # Format phone for WhatsApp
    phone_clean = ''.join(filter(str.isdigit, phone))
    if len(phone_clean) == 11:
        phone_clean = "55" + phone_clean
    elif len(phone_clean) == 10:
        phone_clean = "55" + phone_clean
    
    # Build message
    items_detail = []
    for order in prazo_orders[-5:]:
        order_date = order.get("created_at", "")[:10]
        items_detail.append(f"  • {order_date}: R$ {order.get('total', 0):.2f}")
    
    if len(prazo_orders) > 5:
        items_detail.append(f"  ... e mais {len(prazo_orders) - 5} pedido(s)")
    
    credit_info = f"\n💳 Crédito disponível: R$ {credit:.2f}" if credit > 0 else ""
    net_debt = max(0, total - credit)
    
    # Simple message for WhatsApp URL (no special chars that break URL)
    message = f"""☕ GANOH Café Bistrô

Olá, {customer_name}! 👋

Passando para enviar seu extrato:

💰 Total: R$ {total:.2f}{credit_info}
{'🔵 A Pagar: R$ ' + f'{net_debt:.2f}' if credit > 0 else ''}

📋 Últimos pedidos:
{chr(10).join(items_detail)}

✅ Formas de pagamento:
• PIX 📱
• Cartão 💳
• Dinheiro 💵

Aguardamos você! 😊"""

    # URL encode the message
    import urllib.parse
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{phone_clean}?text={encoded_message}"
    
    return {
        "success": True,
        "customer_name": customer_name,
        "phone": phone,
        "total_debt": total,
        "credit": credit,
        "net_debt": net_debt,
        "message": message,
        "whatsapp_url": whatsapp_url
    }

@api_router.get("/prazo/charge-messages")
async def get_prazo_charge_messages(store: Optional[str] = None):
    """Generate WhatsApp URLs with pre-filled messages for all prazo customers"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brazil_tz)
    
    # Build query for prazo orders
    query = {
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True}
    }
    if store:
        query["store"] = store
    
    # Get all unpaid prazo orders
    prazo_orders = await db.orders.find(query, {"_id": 0}).to_list(10000)
    
    if not prazo_orders:
        return {"success": True, "customers": [], "no_phone": [], "message": "Nenhum débito pendente"}
    
    # Group by customer
    debts_by_customer = {}
    for order in prazo_orders:
        name = order.get("customer_name", "Desconhecido")
        if name not in debts_by_customer:
            debts_by_customer[name] = {"total": 0, "orders": []}
        debts_by_customer[name]["total"] += order.get("total", 0)
        debts_by_customer[name]["orders"].append(order)
    
    customers_with_url = []
    no_phone = []
    
    for customer_name, debt_info in debts_by_customer.items():
        # Get customer info
        customer = await db.prazo_customers.find_one({"name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"}})
        phone = customer.get("phone", "") if customer else ""
        
        if not phone:
            no_phone.append(customer_name)
            continue
        
        # Format phone
        phone_clean = ''.join(filter(str.isdigit, phone))
        if len(phone_clean) == 11:
            phone_clean = "55" + phone_clean
        elif len(phone_clean) == 10:
            phone_clean = "55" + phone_clean
        
        # Build simple message
        message = f"""☕ GANOH Café Bistrô

Olá, {customer_name}! 👋

Passando para lembrar do seu saldo em aberto:

💰 Total: R$ {debt_info['total']:.2f}
📦 {len(debt_info['orders'])} pedido(s)

✅ Formas de pagamento:
• PIX 📱
• Cartão 💳
• Dinheiro 💵

Quando puder, passe aqui! 😊"""

        import urllib.parse
        encoded_message = urllib.parse.quote(message)
        whatsapp_url = f"https://wa.me/{phone_clean}?text={encoded_message}"
        
        customers_with_url.append({
            "name": customer_name,
            "phone": phone,
            "total": debt_info["total"],
            "order_count": len(debt_info["orders"]),
            "whatsapp_url": whatsapp_url
        })
    
    return {
        "success": True,
        "customers": customers_with_url,
        "no_phone": no_phone,
        "message": f"{len(customers_with_url)} cliente(s) com telefone, {len(no_phone)} sem telefone"
    }

# ==================== EXPENSES (GASTOS) MANAGEMENT ====================
from emergentintegrations.llm.openai import LlmChat, ImageContent
from emergentintegrations.llm.chat import UserMessage

EXPENSE_CATEGORIES = [
    "contador",
    "fornecedor", 
    "mercado",
    "suplementos",
    "VT",
    "Vivo",
    "sistema",
    "salário",
    "outros"
]

class ExpenseCreate(BaseModel):
    description: str
    amount: float
    category: str
    store: str = "all"  # "runner", "gym-londres", or "all"
    image_url: str = ""
    notes: str = ""

class ExpenseAnalysis(BaseModel):
    image_base64: str

@api_router.get("/expenses")
async def get_expenses(store: Optional[str] = None, category: Optional[str] = None, username: str = Depends(verify_gestor)):
    """Get all expenses with optional filters"""
    query = {}
    if store and store != "all":
        query["$or"] = [{"store": store}, {"store": "all"}]
    if category:
        query["category"] = category
    
    expenses = await db.expenses.find(query, {"_id": 0}).sort("created_at", -1).to_list(1000)
    
    # Calculate totals by category
    totals_by_category = {}
    for exp in expenses:
        cat = exp.get("category", "outros")
        totals_by_category[cat] = totals_by_category.get(cat, 0) + exp.get("amount", 0)
    
    total = sum(e.get("amount", 0) for e in expenses)
    
    return {
        "expenses": expenses,
        "total": total,
        "by_category": totals_by_category,
        "categories": EXPENSE_CATEGORIES
    }

@api_router.get("/expenses/monthly")
async def get_monthly_expenses(username: str = Depends(verify_gestor)):
    """Get expenses for current month with daily breakdown"""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    expenses = await db.expenses.find({
        "created_at": {"$gte": month_start.isoformat()}
    }, {"_id": 0}).to_list(1000)
    
    # Group by day
    daily_data = {}
    for i in range(now.day):
        day = (month_start + timedelta(days=i)).strftime("%Y-%m-%d")
        daily_data[day] = {"date": day, "day": i + 1, "total": 0, "by_category": {}}
    
    for exp in expenses:
        date = exp.get("created_at", "")[:10]
        if date in daily_data:
            daily_data[date]["total"] += exp.get("amount", 0)
            cat = exp.get("category", "outros")
            daily_data[date]["by_category"][cat] = daily_data[date]["by_category"].get(cat, 0) + exp.get("amount", 0)
    
    # Totals by category for the month
    totals_by_category = {}
    for exp in expenses:
        cat = exp.get("category", "outros")
        totals_by_category[cat] = totals_by_category.get(cat, 0) + exp.get("amount", 0)
    
    chart_data = sorted(daily_data.values(), key=lambda x: x["date"])
    
    return {
        "month": now.strftime("%B %Y"),
        "data": chart_data,
        "total_expenses": sum(d["total"] for d in chart_data),
        "by_category": totals_by_category,
        "categories": EXPENSE_CATEGORIES
    }

@api_router.post("/expenses")
async def create_expense(expense: ExpenseCreate, username: str = Depends(verify_gestor)):
    """Create a new expense"""
    new_expense = {
        "id": str(uuid.uuid4()),
        "description": expense.description,
        "amount": expense.amount,
        "category": expense.category,
        "store": expense.store,
        "image_url": expense.image_url,
        "notes": expense.notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": username
    }
    await db.expenses.insert_one(new_expense)
    return {**new_expense, "_id": None}

@api_router.delete("/expenses/{expense_id}")
async def delete_expense(expense_id: str, username: str = Depends(verify_gestor)):
    """Delete an expense"""
    result = await db.expenses.delete_one({"id": expense_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Gasto não encontrado")
    return {"success": True, "message": "Gasto removido"}

# ==================== EXPORT TO ACCOUNTANT ====================
@api_router.get("/expenses/export-contador")
async def export_expenses_for_accountant(
    month: Optional[int] = None, 
    year: Optional[int] = None,
    store: Optional[str] = None,
    username: str = Depends(verify_gestor)
):
    """Export all financial data for accountant (IR - Imposto de Renda)"""
    brazil_tz = pytz.timezone('America/Sao_Paulo')
    now = datetime.now(brazil_tz)
    
    target_month = month or now.month
    target_year = year or now.year
    
    # Calculate date range
    month_start = brazil_tz.localize(datetime(target_year, target_month, 1))
    if target_month == 12:
        month_end = brazil_tz.localize(datetime(target_year + 1, 1, 1))
    else:
        month_end = brazil_tz.localize(datetime(target_year, target_month + 1, 1))
    
    month_start_utc = month_start.astimezone(pytz.UTC).isoformat()
    month_end_utc = month_end.astimezone(pytz.UTC).isoformat()
    
    # Build query for expenses
    expense_query = {"created_at": {"$gte": month_start_utc, "$lt": month_end_utc}}
    if store and store != "all":
        expense_query["$or"] = [{"store": store}, {"store": "all"}]
    
    # Get expenses
    expenses = await db.expenses.find(expense_query, {"_id": 0}).to_list(10000)
    
    # Get orders (sales)
    order_query = {
        "created_at": {"$gte": month_start_utc, "$lt": month_end_utc},
        "status": {"$in": ["ready", "delivered"]}
    }
    if store and store != "all":
        order_query["store"] = store
    
    orders = await db.orders.find(order_query, {"_id": 0}).to_list(10000)
    
    # Get menu items with fiscal info
    menu_items = await db.menu.find({}, {"_id": 0}).to_list(1000)
    
    # Calculate totals
    total_expenses = sum(e.get("amount", 0) for e in expenses)
    total_sales = sum(o.get("total", 0) for o in orders)
    profit = total_sales - total_expenses
    
    # Sales by store
    sales_runner = sum(o.get("total", 0) for o in orders if o.get("store") == "runner")
    sales_gym = sum(o.get("total", 0) for o in orders if o.get("store") == "gym-londres")
    orders_runner = len([o for o in orders if o.get("store") == "runner"])
    orders_gym = len([o for o in orders if o.get("store") == "gym-londres"])
    
    # Group expenses by category
    expenses_by_category = {}
    for exp in expenses:
        cat = exp.get("category", "outros")
        if cat not in expenses_by_category:
            expenses_by_category[cat] = {"total": 0, "count": 0, "items": []}
        expenses_by_category[cat]["total"] += exp.get("amount", 0)
        expenses_by_category[cat]["count"] += 1
        expenses_by_category[cat]["items"].append({
            "data": exp.get("created_at", "")[:10],
            "descricao": exp.get("description", ""),
            "valor": exp.get("amount", 0),
            "loja": "Runner" if exp.get("store") == "runner" else "GYM Londres" if exp.get("store") == "gym-londres" else "Todas",
            "observacoes": exp.get("notes", "")
        })
    
    # Group sales by payment method and store
    sales_by_payment = {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "prazo": 0, "voucher": 0}
    sales_by_payment_runner = {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "prazo": 0, "voucher": 0}
    sales_by_payment_gym = {"pix": 0, "debit": 0, "credit": 0, "cash": 0, "prazo": 0, "voucher": 0}
    
    for order in orders:
        pm = order.get("payment_method", "cash")
        total = order.get("total", 0)
        store_order = order.get("store", "")
        
        sales_by_payment[pm] = sales_by_payment.get(pm, 0) + total
        
        if store_order == "runner":
            sales_by_payment_runner[pm] = sales_by_payment_runner.get(pm, 0) + total
        elif store_order == "gym-londres":
            sales_by_payment_gym[pm] = sales_by_payment_gym.get(pm, 0) + total
    
    # Count items sold
    items_sold = {}
    for order in orders:
        for item in order.get("items", []):
            item_name = item.get("name", "Item")
            item_qty = item.get("quantity", 1)
            item_price = item.get("price", 0)
            
            if item_name not in items_sold:
                items_sold[item_name] = {"quantidade": 0, "valor_unitario": item_price, "total": 0}
            items_sold[item_name]["quantidade"] += item_qty
            items_sold[item_name]["total"] += item_price * item_qty
    
    # Products with fiscal info - ALL products
    products_fiscal = []
    for item in menu_items:
        products_fiscal.append({
            "id": item.get("id"),
            "codigo": item.get("codigo", ""),
            "codigo_externo": item.get("codigo_externo", ""),
            "nome": item.get("name"),
            "preco_venda": item.get("price", 0),
            "valor_custo": item.get("valor_custo", 0),
            "unidade": item.get("unidade", "UN"),
            "categoria": item.get("category", ""),
            "codigo_barras": item.get("codigo_barras", ""),
            "ncm": item.get("ncm", "21069090"),  # NCM padrão para alimentos
            "cst": item.get("cst", ""),
            "csosn": item.get("csosn", "0102"),  # CSOSN padrão Simples Nacional
            "cfop": item.get("cfop", "5102"),  # CFOP padrão venda mercadoria
            "cest": item.get("cest", ""),
            "icms_aliquota": item.get("icms_aliquota", 0),
            "icms_tipo": item.get("icms_tipo", "isento"),
            "pis_cst": item.get("pis_cst", "49"),
            "pis_aliquota": item.get("pis_aliquota", 0),
            "cofins_cst": item.get("cofins_cst", "49"),
            "cofins_aliquota": item.get("cofins_aliquota", 0)
        })
    
    month_names = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
                   "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    return {
        "titulo": "RELATÓRIO FINANCEIRO PARA CONTADOR",
        "empresa": {
            "nome": "GANOH Café Bistrô",
            "cnpj": "",  # User should fill
            "endereco": "Mogi das Cruzes, SP"
        },
        "periodo": {
            "mes": target_month,
            "ano": target_year,
            "mes_nome": month_names[target_month - 1],
            "data_inicio": month_start.strftime("%d/%m/%Y"),
            "data_fim": (month_end - timedelta(days=1)).strftime("%d/%m/%Y")
        },
        "resumo_geral": {
            "receita_total": round(total_sales, 2),
            "despesas_total": round(total_expenses, 2),
            "lucro_bruto": round(profit, 2),
            "total_pedidos": len(orders),
            "total_registros_despesas": len(expenses),
            "margem_lucro_percentual": round((profit / total_sales * 100) if total_sales > 0 else 0, 2)
        },
        "resumo_por_loja": {
            "runner": {
                "nome": "GANOH Café Bistrô - Runner",
                "receita": round(sales_runner, 2),
                "pedidos": orders_runner,
                "ticket_medio": round(sales_runner / orders_runner, 2) if orders_runner > 0 else 0,
                "receita_por_forma_pagamento": sales_by_payment_runner
            },
            "gym_londres": {
                "nome": "GANOH Café Bistrô - GYM Londres",
                "receita": round(sales_gym, 2),
                "pedidos": orders_gym,
                "ticket_medio": round(sales_gym / orders_gym, 2) if orders_gym > 0 else 0,
                "receita_por_forma_pagamento": sales_by_payment_gym
            }
        },
        "receita_por_forma_pagamento_consolidado": {
            "pix": round(sales_by_payment["pix"], 2),
            "debito": round(sales_by_payment["debit"], 2),
            "credito": round(sales_by_payment["credit"], 2),
            "dinheiro": round(sales_by_payment["cash"], 2),
            "prazo_fiado": round(sales_by_payment["prazo"], 2),
            "voucher": round(sales_by_payment["voucher"], 2)
        },
        "despesas_por_categoria": {
            cat: {
                "total": round(data["total"], 2),
                "quantidade": data["count"],
                "itens": data["items"]
            } for cat, data in expenses_by_category.items()
        },
        "produtos_vendidos": [
            {
                "produto": name,
                "quantidade_vendida": data["quantidade"],
                "valor_unitario": round(data["valor_unitario"], 2),
                "total_vendido": round(data["total"], 2)
            } for name, data in sorted(items_sold.items(), key=lambda x: x[1]["total"], reverse=True)
        ],
        "vendas_detalhadas": [
            {
                "id": o.get("id"),
                "data": o.get("created_at", "")[:10],
                "hora": o.get("created_at", "")[11:16] if len(o.get("created_at", "")) > 11 else "",
                "cliente": o.get("customer_name"),
                "valor": round(o.get("total", 0), 2),
                "forma_pagamento": o.get("payment_method"),
                "loja": "Runner" if o.get("store") == "runner" else "GYM Londres",
                "itens": [
                    {
                        "produto": item.get("name"),
                        "quantidade": item.get("quantity", 1),
                        "valor_unitario": round(item.get("price", 0), 2),
                        "subtotal": round(item.get("price", 0) * item.get("quantity", 1), 2)
                    } for item in o.get("items", [])
                ]
            } for o in sorted(orders, key=lambda x: x.get("created_at", ""))
        ],
        "cadastro_produtos_fiscal": products_fiscal,
        "observacoes_fiscais": {
            "regime_tributario": "Simples Nacional (presumido)",
            "ncm_padrao_alimentos": "21069090 - Preparações alimentícias diversas",
            "csosn_padrao": "0102 - Tributada pelo Simples Nacional sem permissão de crédito",
            "cfop_venda_interna": "5102 - Venda de mercadoria adquirida",
            "pis_cofins": "Não incidência (Simples Nacional)"
        },
        "gerado_em": now.strftime("%d/%m/%Y %H:%M:%S"),
        "gerado_por": username
    }

class ContadorEmailRequest(BaseModel):
    email: str
    month: Optional[int] = None
    year: Optional[int] = None
    store: Optional[str] = None

def generate_contador_html_report(data: dict) -> str:
    """Generate a beautiful HTML report for the accountant"""
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
            .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            h1 {{ color: #1a5f2a; border-bottom: 3px solid #1a5f2a; padding-bottom: 10px; }}
            h2 {{ color: #333; margin-top: 30px; border-bottom: 1px solid #ddd; padding-bottom: 5px; }}
            .header {{ text-align: center; margin-bottom: 30px; }}
            .summary-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }}
            .summary-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }}
            .summary-card.receita {{ background: #d4edda; border-left: 4px solid #28a745; }}
            .summary-card.despesa {{ background: #f8d7da; border-left: 4px solid #dc3545; }}
            .summary-card.lucro {{ background: #d1ecf1; border-left: 4px solid #17a2b8; }}
            .summary-label {{ font-size: 12px; color: #666; text-transform: uppercase; }}
            .summary-value {{ font-size: 24px; font-weight: bold; margin-top: 5px; }}
            table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
            th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
            th {{ background: #f8f9fa; font-weight: bold; }}
            .store-section {{ background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 10px 0; }}
            .store-name {{ font-weight: bold; color: #1a5f2a; }}
            .payment-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin: 15px 0; }}
            .payment-item {{ background: #f0f0f0; padding: 10px; border-radius: 5px; text-align: center; }}
            .fiscal-info {{ background: #fff3cd; padding: 15px; border-radius: 8px; margin-top: 20px; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; text-align: center; color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📊 {data['titulo']}</h1>
                <p><strong>{data['empresa']['nome']}</strong></p>
                <p>Período: {data['periodo']['mes_nome']} / {data['periodo']['ano']}</p>
                <p>({data['periodo']['data_inicio']} a {data['periodo']['data_fim']})</p>
            </div>
            
            <h2>📈 Resumo Geral</h2>
            <div class="summary-grid">
                <div class="summary-card receita">
                    <div class="summary-label">Receita Total</div>
                    <div class="summary-value">R$ {data['resumo_geral']['receita_total']:,.2f}</div>
                    <div class="summary-label">{data['resumo_geral']['total_pedidos']} pedidos</div>
                </div>
                <div class="summary-card despesa">
                    <div class="summary-label">Despesas Total</div>
                    <div class="summary-value">R$ {data['resumo_geral']['despesas_total']:,.2f}</div>
                    <div class="summary-label">{data['resumo_geral']['total_registros_despesas']} registros</div>
                </div>
                <div class="summary-card lucro">
                    <div class="summary-label">Lucro Bruto</div>
                    <div class="summary-value">R$ {data['resumo_geral']['lucro_bruto']:,.2f}</div>
                    <div class="summary-label">Margem: {data['resumo_geral']['margem_lucro_percentual']}%</div>
                </div>
            </div>
            
            <h2>🏪 Por Loja</h2>
            <div class="store-section">
                <p class="store-name">🏃 Runner</p>
                <p>Receita: R$ {data['resumo_por_loja']['runner']['receita']:,.2f} | Pedidos: {data['resumo_por_loja']['runner']['pedidos']} | Ticket Médio: R$ {data['resumo_por_loja']['runner']['ticket_medio']:,.2f}</p>
            </div>
            <div class="store-section">
                <p class="store-name">🏋️ GYM Londres</p>
                <p>Receita: R$ {data['resumo_por_loja']['gym_londres']['receita']:,.2f} | Pedidos: {data['resumo_por_loja']['gym_londres']['pedidos']} | Ticket Médio: R$ {data['resumo_por_loja']['gym_londres']['ticket_medio']:,.2f}</p>
            </div>
            
            <h2>💳 Receita por Forma de Pagamento</h2>
            <div class="payment-grid">
                <div class="payment-item"><strong>PIX</strong><br>R$ {data['receita_por_forma_pagamento_consolidado']['pix']:,.2f}</div>
                <div class="payment-item"><strong>Débito</strong><br>R$ {data['receita_por_forma_pagamento_consolidado']['debito']:,.2f}</div>
                <div class="payment-item"><strong>Crédito</strong><br>R$ {data['receita_por_forma_pagamento_consolidado']['credito']:,.2f}</div>
                <div class="payment-item"><strong>Dinheiro</strong><br>R$ {data['receita_por_forma_pagamento_consolidado']['dinheiro']:,.2f}</div>
                <div class="payment-item"><strong>Prazo/Fiado</strong><br>R$ {data['receita_por_forma_pagamento_consolidado']['prazo_fiado']:,.2f}</div>
                <div class="payment-item"><strong>Voucher</strong><br>R$ {data['receita_por_forma_pagamento_consolidado']['voucher']:,.2f}</div>
            </div>
            
            <h2>📦 Produtos Mais Vendidos</h2>
            <table>
                <tr><th>Produto</th><th>Qtd</th><th>Valor Unit.</th><th>Total</th></tr>
    """
    
    # Add top 15 products
    for prod in data.get('produtos_vendidos', [])[:15]:
        html += f"""
                <tr>
                    <td>{prod['produto']}</td>
                    <td>{prod['quantidade_vendida']}</td>
                    <td>R$ {prod['valor_unitario']:,.2f}</td>
                    <td>R$ {prod['total_vendido']:,.2f}</td>
                </tr>
        """
    
    html += """
            </table>
            
            <h2>💸 Despesas por Categoria</h2>
            <table>
                <tr><th>Categoria</th><th>Qtd</th><th>Total</th></tr>
    """
    
    # Add expenses by category
    for cat, cat_data in data.get('despesas_por_categoria', {}).items():
        html += f"""
                <tr>
                    <td>{cat.upper()}</td>
                    <td>{cat_data['quantidade']}</td>
                    <td>R$ {cat_data['total']:,.2f}</td>
                </tr>
        """
    
    html += f"""
            </table>
            
            <div class="fiscal-info">
                <h3>📋 Informações Fiscais</h3>
                <p><strong>Regime Tributário:</strong> {data['observacoes_fiscais']['regime_tributario']}</p>
                <p><strong>NCM Padrão:</strong> {data['observacoes_fiscais']['ncm_padrao_alimentos']}</p>
                <p><strong>CSOSN:</strong> {data['observacoes_fiscais']['csosn_padrao']}</p>
                <p><strong>CFOP:</strong> {data['observacoes_fiscais']['cfop_venda_interna']}</p>
                <p><strong>PIS/COFINS:</strong> {data['observacoes_fiscais']['pis_cofins']}</p>
            </div>
            
            <div class="footer">
                <p>Relatório gerado em {data['gerado_em']} por {data['gerado_por']}</p>
                <p>GANOH Café Bistrô - Sistema de Gestão</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html

@api_router.post("/expenses/send-contador-email")
async def send_contador_email(request: ContadorEmailRequest, username: str = Depends(verify_gestor)):
    """Send accountant report via email"""
    try:
        # Get the report data
        report_data = await export_expenses_for_accountant(
            month=request.month,
            year=request.year,
            store=request.store,
            username=username
        )
        
        # Generate HTML report
        html_content = generate_contador_html_report(report_data)
        
        # Configure Resend
        resend_key = os.environ.get("RESEND_API_KEY")
        if not resend_key:
            raise HTTPException(status_code=500, detail="RESEND_API_KEY não configurada. Configure a chave no ambiente.")
        
        resend.api_key = resend_key
        
        # Send email
        params = {
            "from": os.environ.get("SENDER_EMAIL", "onboarding@resend.dev"),
            "to": [request.email],
            "subject": f"📊 Relatório Financeiro GANOH - {report_data['periodo']['mes_nome']}/{report_data['periodo']['ano']}",
            "html": html_content
        }
        
        email = await asyncio.to_thread(resend.Emails.send, params)
        
        return {
            "success": True,
            "message": f"Relatório enviado para {request.email}",
            "email_id": email.get("id"),
            "periodo": f"{report_data['periodo']['mes_nome']}/{report_data['periodo']['ano']}"
        }
        
    except Exception as e:
        logger.error(f"Error sending contador email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao enviar email: {str(e)}")

@api_router.post("/expenses/analyze-image")
async def analyze_expense_image(analysis: ExpenseAnalysis, username: str = Depends(verify_gestor)):
    """Use AI to analyze expense receipt/invoice image"""
    try:
        llm_key = os.environ.get("EMERGENT_LLM_KEY")
        if not llm_key:
            raise HTTPException(status_code=500, detail="LLM key not configured")
        
        chat = LlmChat(
            api_key=llm_key,
            session_id=f"expense-analysis-{uuid.uuid4()}",
            system_message="""Você é um assistente especializado em analisar notas fiscais, recibos e comprovantes de gastos.
Analise a imagem e extraia as seguintes informações em formato JSON:
{
    "description": "descrição do gasto (o que foi comprado)",
    "amount": valor numérico em reais (apenas o número, sem R$),
    "notes": "nome do estabelecimento ou local onde foi gasto",
    "store": "runner" ou "gym-londres" ou "all" (tente identificar pela nota se é para Runner ou GYM Londres. Se não conseguir identificar, use "all")
}

IMPORTANTE: Tente identificar a loja pelo endereço, nome do estabelecimento ou contexto da nota fiscal.
- Se mencionar "Runner" ou estiver na região do Runner -> "runner"
- Se mencionar "GYM Londres", "Londres" ou estiver na região -> "gym-londres"
- Se for um gasto geral (contador, sistema, etc) ou não conseguir identificar -> "all"

Responda APENAS com o JSON, sem texto adicional."""
        ).with_model("openai", "gpt-4o")
        
        # Create ImageContent for the image (uses content_type="image" internally)
        image_content = ImageContent(image_base64=analysis.image_base64)
        
        # Create user message with image
        user_message = UserMessage(
            text="Analise este comprovante/nota fiscal e extraia: o valor total, o que foi comprado, onde foi comprado, e para qual loja (Runner, GYM Londres ou geral).",
            file_contents=[image_content]
        )
        
        response = await chat.send_message(user_message)
        
        # Parse JSON from response
        import json
        try:
            # Clean response - remove markdown code blocks if present
            clean_response = response.strip()
            if clean_response.startswith("```"):
                clean_response = clean_response.split("```")[1]
                if clean_response.startswith("json"):
                    clean_response = clean_response[4:]
            clean_response = clean_response.strip()
            
            result = json.loads(clean_response)
            return {
                "success": True,
                "analysis": result
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Não foi possível extrair informações da imagem",
                "raw_response": response
            }
            
    except Exception as e:
        logger.error(f"Error analyzing expense image: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao analisar imagem: {str(e)}")

# Multi-image analysis for expenses
class MultiImageAnalysis(BaseModel):
    images: list  # List of base64 images

@api_router.post("/expenses/analyze-multiple")
async def analyze_multiple_expense_images(data: MultiImageAnalysis, username: str = Depends(verify_gestor)):
    """Use AI to analyze multiple expense receipt/invoice images and return a list"""
    try:
        llm_key = os.environ.get("EMERGENT_LLM_KEY")
        if not llm_key:
            raise HTTPException(status_code=500, detail="LLM key not configured")
        
        if not data.images or len(data.images) == 0:
            raise HTTPException(status_code=400, detail="Nenhuma imagem enviada")
        
        chat = LlmChat(
            api_key=llm_key,
            session_id=f"expense-multi-{uuid.uuid4()}",
            system_message=f"""Você é um assistente especializado em analisar notas fiscais, recibos e comprovantes de gastos.
Você vai receber {len(data.images)} imagem(ns) de comprovantes.

Para CADA imagem, extraia as informações e retorne um JSON com uma lista:
{{
    "expenses": [
        {{
            "id": 1,
            "description": "o que foi comprado",
            "amount": valor numérico em reais (apenas o número),
            "notes": "nome do estabelecimento/local",
            "store": "runner" ou "gym-londres" ou "all"
        }}
    ]
}}

IMPORTANTE: Tente identificar a loja pelo endereço, nome do estabelecimento ou contexto da nota fiscal.
- Se mencionar "Runner" ou estiver na região do Runner -> "runner"
- Se mencionar "GYM Londres", "Londres" ou estiver na região -> "gym-londres"
- Se for um gasto geral (contador, sistema, etc) ou não conseguir identificar -> "all"

Responda APENAS com o JSON, sem texto adicional."""
        ).with_model("openai", "gpt-4o")
        
        # Create ImageContent for each image
        image_contents = [ImageContent(image_base64=img) for img in data.images]
        
        # Create user message with all images
        user_message = UserMessage(
            text=f"Analise estas {len(data.images)} nota(s) fiscal(is) e liste: valor, o que foi comprado, onde foi comprado, e para qual loja (Runner, GYM Londres ou geral).",
            file_contents=image_contents
        )
        
        response = await chat.send_message(user_message)
        
        # Parse JSON from response
        import json
        try:
            clean_response = response.strip()
            if clean_response.startswith("```"):
                clean_response = clean_response.split("```")[1]
                if clean_response.startswith("json"):
                    clean_response = clean_response[4:]
            clean_response = clean_response.strip()
            
            result = json.loads(clean_response)
            return {
                "success": True,
                "count": len(result.get("expenses", [])),
                "expenses": result.get("expenses", [])
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Não foi possível extrair informações das imagens",
                "raw_response": response
            }
            
    except Exception as e:
        logger.error(f"Error analyzing multiple expense images: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao analisar imagens: {str(e)}")

# ==================== PRAZO WHATSAPP LINK ====================
@api_router.get("/prazo/whatsapp-link/{customer_name}")
async def get_prazo_whatsapp_link(customer_name: str):
    """Generate WhatsApp link for prazo collection"""
    # Get customer info
    customer = await db.prazo_customers.find_one({"name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"}})
    
    if not customer:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    phone = customer.get("phone", "")
    if not phone:
        raise HTTPException(status_code=400, detail="Cliente não tem telefone cadastrado")
    
    # Get total debt
    prazo_orders = await db.orders.find({
        "customer_name": {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"},
        "payment_method": "prazo",
        "prazo_paid": {"$ne": True}
    }, {"_id": 0}).to_list(1000)
    
    total_debt = sum(o.get("total", 0) for o in prazo_orders)
    
    # Format phone (remove non-digits and add country code if needed)
    clean_phone = ''.join(filter(str.isdigit, phone))
    if not clean_phone.startswith('55'):
        clean_phone = '55' + clean_phone
    
    # Create message
    message = f"""Olá {customer_name}! 👋

Este é um lembrete de cobrança do GANOH Café Bistrô.

💰 *Valor pendente:* R$ {total_debt:.2f}
📅 *Pedidos:* {len(prazo_orders)} pedido(s)

Por favor, entre em contato para regularizar sua situação.

Obrigado! ☕"""
    
    # URL encode the message
    from urllib.parse import quote
    encoded_message = quote(message)
    
    whatsapp_url = f"https://wa.me/{clean_phone}?text={encoded_message}"
    
    return {
        "url": whatsapp_url,
        "phone": clean_phone,
        "total_debt": total_debt,
        "order_count": len(prazo_orders)
    }

# ==================== UPDATED CHART DATA WITH EXPENSES ====================
@api_router.get("/gestor/chart/monthly-with-expenses")
async def get_monthly_chart_with_expenses(month: int = None, year: int = None, store: str = None, username: str = Depends(verify_gestor)):
    """Get daily sales AND expenses data for a specific month, optionally filtered by store.
    Revenue = order totals (excl. prazo) + PIX manual adjustments + prazo payments received.
    """
    now = datetime.now(timezone.utc)
    
    target_month = month if month else now.month
    target_year = year if year else now.year
    
    month_start = datetime(target_year, target_month, 1, tzinfo=timezone.utc)
    
    if target_month == 12:
        month_end = datetime(target_year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(target_year, target_month + 1, 1, tzinfo=timezone.utc)
    
    import calendar
    days_in_month = calendar.monthrange(target_year, target_month)[1]
    
    # Get all completed orders this month (filter by store if provided)
    orders_query = {
        "status": {"$in": ["ready", "delivered", "received", "preparing"]},
        "created_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}
    }
    if store and store != "all":
        orders_query["store"] = store
    orders = await db.orders.find(orders_query, {"_id": 0, "created_at": 1, "total": 1, "store": 1, "payment_method": 1}).to_list(10000)
    
    # Get all expenses this month (filter by store if provided)
    expenses_query = {
        "created_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}
    }
    if store and store != "all":
        expenses_query["$or"] = [{"store": store}, {"store": "all"}, {"store": {"$exists": False}}]
    expenses = await db.expenses.find(expenses_query, {"_id": 0}).to_list(1000)

    # PIX manual adjustments (real revenue not represented as orders)
    pix_query = {
        "removed": {"$ne": True},
        "created_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}
    }
    if store and store != "all":
        pix_query["store"] = store
    pix_adjustments = await db.pix_adjustments.find(pix_query, {"_id": 0}).to_list(10000)

    # Prazo payments (cash actually received from customers paying their debt)
    prazo_query = {
        "created_at": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()}
    }
    if store and store != "all":
        prazo_query["store"] = store
    prazo_payments = await db.prazo_payments.find(prazo_query, {"_id": 0}).to_list(10000)
    prazo_partial_payments = await db.prazo_partial_payments.find(prazo_query, {"_id": 0}).to_list(10000)
    all_prazo_payments = prazo_payments + prazo_partial_payments
    
    # Group by day
    daily_data = {}
    for i in range(days_in_month):
        day_date = month_start + timedelta(days=i)
        day_str = day_date.strftime("%Y-%m-%d")
        daily_data[day_str] = {
            "date": day_str, 
            "day": i + 1, 
            "revenue": 0, 
            "expenses": 0,
            "profit": 0,
            "order_count": 0,
            "expenses_by_category": {}
        }
    
    for order in orders:
        # Skip prazo orders - they're not real revenue until paid
        if order.get("payment_method") == "prazo":
            continue
        date = order.get("created_at", "")[:10]
        if date in daily_data:
            daily_data[date]["revenue"] += order.get("total", 0)
            daily_data[date]["order_count"] += 1

    for adj in pix_adjustments:
        date = adj.get("created_at", "")[:10]
        if date in daily_data:
            daily_data[date]["revenue"] += adj.get("amount", 0)

    for payment in all_prazo_payments:
        date = payment.get("created_at", "")[:10]
        if date in daily_data:
            daily_data[date]["revenue"] += payment.get("amount", 0)
    
    for exp in expenses:
        date = exp.get("created_at", "")[:10]
        if date in daily_data:
            daily_data[date]["expenses"] += exp.get("amount", 0)
            cat = exp.get("category", "outros")
            daily_data[date]["expenses_by_category"][cat] = daily_data[date]["expenses_by_category"].get(cat, 0) + exp.get("amount", 0)
    
    # Calculate profit
    for day in daily_data.values():
        day["profit"] = day["revenue"] - day["expenses"]
    
    # Total expenses by category for the month
    expenses_by_category = {}
    for exp in expenses:
        cat = exp.get("category", "outros")
        expenses_by_category[cat] = expenses_by_category.get(cat, 0) + exp.get("amount", 0)
    
    # Convert to sorted list
    chart_data = sorted(daily_data.values(), key=lambda x: x["date"])
    
    total_revenue = sum(d["revenue"] for d in chart_data)
    total_expenses = sum(d["expenses"] for d in chart_data)
    
    month_names = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", 
                   "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    return {
        "month": f"{month_names[target_month]} {target_year}",
        "period": "month",
        "data": chart_data,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "total_profit": total_revenue - total_expenses,
        "total_orders": sum(d["order_count"] for d in chart_data),
        "expenses_by_category": expenses_by_category,
        "categories": EXPENSE_CATEGORIES
    }

@api_router.get("/gestor/chart/daily-with-expenses")
async def get_daily_chart_with_expenses(date: str = None, store: str = None, username: str = Depends(verify_gestor)):
    """Get hourly sales AND expenses data for a specific day, optionally filtered by store.
    Revenue = order totals (excl. prazo) + PIX manual adjustments + prazo payments received.
    """
    now = datetime.now(timezone.utc)
    
    if date:
        target_date = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        target_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    
    # Get orders and expenses for this day (filter by store if provided)
    orders_query = {
        "status": {"$in": ["ready", "delivered", "received", "preparing"]},
        "created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}
    }
    if store and store != "all":
        orders_query["store"] = store
    orders = await db.orders.find(orders_query, {"_id": 0, "created_at": 1, "total": 1, "payment_method": 1}).to_list(10000)
    
    expenses_query = {
        "created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}
    }
    if store and store != "all":
        expenses_query["$or"] = [{"store": store}, {"store": "all"}, {"store": {"$exists": False}}]
    expenses = await db.expenses.find(expenses_query, {"_id": 0}).to_list(1000)

    # PIX manual adjustments + Prazo payments
    pix_query = {
        "removed": {"$ne": True},
        "created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}
    }
    if store and store != "all":
        pix_query["store"] = store
    pix_adjustments = await db.pix_adjustments.find(pix_query, {"_id": 0}).to_list(10000)

    prazo_query = {
        "created_at": {"$gte": day_start.isoformat(), "$lt": day_end.isoformat()}
    }
    if store and store != "all":
        prazo_query["store"] = store
    prazo_payments = await db.prazo_payments.find(prazo_query, {"_id": 0}).to_list(10000)
    prazo_partial_payments = await db.prazo_partial_payments.find(prazo_query, {"_id": 0}).to_list(10000)
    all_prazo_payments = prazo_payments + prazo_partial_payments
    
    # Group by hour
    hourly_data = {}
    for hour in range(24):
        hourly_data[hour] = {
            "hour": f"{hour:02d}:00",
            "revenue": 0,
            "expenses": 0,
            "profit": 0,
            "order_count": 0
        }
    
    for order in orders:
        # Skip prazo orders - they're not real revenue until paid
        if order.get("payment_method") == "prazo":
            continue
        try:
            order_time = datetime.fromisoformat(order.get("created_at", "").replace("Z", "+00:00"))
            brazil_hour = (order_time.hour - 3) % 24
            hourly_data[brazil_hour]["revenue"] += order.get("total", 0)
            hourly_data[brazil_hour]["order_count"] += 1
        except:
            pass

    for adj in pix_adjustments:
        try:
            adj_time = datetime.fromisoformat(adj.get("created_at", "").replace("Z", "+00:00"))
            brazil_hour = (adj_time.hour - 3) % 24
            hourly_data[brazil_hour]["revenue"] += adj.get("amount", 0)
        except:
            pass

    for payment in all_prazo_payments:
        try:
            p_time = datetime.fromisoformat(payment.get("created_at", "").replace("Z", "+00:00"))
            brazil_hour = (p_time.hour - 3) % 24
            hourly_data[brazil_hour]["revenue"] += payment.get("amount", 0)
        except:
            pass
    
    for exp in expenses:
        try:
            exp_time = datetime.fromisoformat(exp.get("created_at", "").replace("Z", "+00:00"))
            brazil_hour = (exp_time.hour - 3) % 24
            hourly_data[brazil_hour]["expenses"] += exp.get("amount", 0)
        except:
            pass
    
    for h in hourly_data.values():
        h["profit"] = h["revenue"] - h["expenses"]
    
    chart_data = sorted(hourly_data.values(), key=lambda x: x["hour"])
    
    total_revenue = sum(d["revenue"] for d in chart_data)
    total_expenses = sum(d["expenses"] for d in chart_data)
    
    return {
        "date": target_date.strftime("%d/%m/%Y"),
        "period": "day",
        "data": chart_data,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "total_profit": total_revenue - total_expenses,
        "total_orders": sum(d["order_count"] for d in chart_data)
    }

@api_router.get("/gestor/chart/yearly-with-expenses")
async def get_yearly_chart_with_expenses(year: int = None, store: str = None, username: str = Depends(verify_gestor)):
    """Get monthly sales AND expenses data for a specific year, optionally filtered by store.
    Revenue = order totals (excl. prazo) + PIX manual adjustments + prazo payments received.
    """
    now = datetime.now(timezone.utc)
    target_year = year if year else now.year
    
    year_start = datetime(target_year, 1, 1, tzinfo=timezone.utc)
    year_end = datetime(target_year + 1, 1, 1, tzinfo=timezone.utc)
    
    orders_query = {
        "status": {"$in": ["ready", "delivered", "received", "preparing"]},
        "created_at": {"$gte": year_start.isoformat(), "$lt": year_end.isoformat()}
    }
    if store and store != "all":
        orders_query["store"] = store
    orders = await db.orders.find(orders_query, {"_id": 0, "created_at": 1, "total": 1, "payment_method": 1}).to_list(100000)
    
    expenses_query = {
        "created_at": {"$gte": year_start.isoformat(), "$lt": year_end.isoformat()}
    }
    if store and store != "all":
        expenses_query["$or"] = [{"store": store}, {"store": "all"}, {"store": {"$exists": False}}]
    expenses = await db.expenses.find(expenses_query, {"_id": 0}).to_list(10000)

    # PIX manual adjustments + Prazo payments
    pix_query = {
        "removed": {"$ne": True},
        "created_at": {"$gte": year_start.isoformat(), "$lt": year_end.isoformat()}
    }
    if store and store != "all":
        pix_query["store"] = store
    pix_adjustments = await db.pix_adjustments.find(pix_query, {"_id": 0}).to_list(100000)

    prazo_query = {
        "created_at": {"$gte": year_start.isoformat(), "$lt": year_end.isoformat()}
    }
    if store and store != "all":
        prazo_query["store"] = store
    prazo_payments = await db.prazo_payments.find(prazo_query, {"_id": 0}).to_list(100000)
    prazo_partial_payments = await db.prazo_partial_payments.find(prazo_query, {"_id": 0}).to_list(100000)
    all_prazo_payments = prazo_payments + prazo_partial_payments
    
    month_names = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
    monthly_data = {}
    for m in range(1, 13):
        monthly_data[m] = {
            "month": m,
            "month_name": month_names[m-1],
            "revenue": 0,
            "expenses": 0,
            "profit": 0,
            "order_count": 0
        }
    
    for order in orders:
        # Skip prazo orders - they're not real revenue until paid
        if order.get("payment_method") == "prazo":
            continue
        try:
            order_date = datetime.fromisoformat(order.get("created_at", "").replace("Z", "+00:00"))
            monthly_data[order_date.month]["revenue"] += order.get("total", 0)
            monthly_data[order_date.month]["order_count"] += 1
        except:
            pass

    for adj in pix_adjustments:
        try:
            adj_date = datetime.fromisoformat(adj.get("created_at", "").replace("Z", "+00:00"))
            monthly_data[adj_date.month]["revenue"] += adj.get("amount", 0)
        except:
            pass

    for payment in all_prazo_payments:
        try:
            p_date = datetime.fromisoformat(payment.get("created_at", "").replace("Z", "+00:00"))
            monthly_data[p_date.month]["revenue"] += payment.get("amount", 0)
        except:
            pass
    
    for exp in expenses:
        try:
            exp_date = datetime.fromisoformat(exp.get("created_at", "").replace("Z", "+00:00"))
            monthly_data[exp_date.month]["expenses"] += exp.get("amount", 0)
        except:
            pass
    
    for m in monthly_data.values():
        m["profit"] = m["revenue"] - m["expenses"]
    
    chart_data = sorted(monthly_data.values(), key=lambda x: x["month"])
    
    total_revenue = sum(d["revenue"] for d in chart_data)
    total_expenses = sum(d["expenses"] for d in chart_data)
    
    return {
        "year": target_year,
        "period": "year",
        "data": chart_data,
        "total_revenue": total_revenue,
        "total_expenses": total_expenses,
        "total_profit": total_revenue - total_expenses,
        "total_orders": sum(d["order_count"] for d in chart_data)
    }

# ==================== ADMIN CLEAR DATA ROUTE ====================
CLEAR_DATA_PASSWORD = "152637"

@api_router.post("/admin/clear-data")
async def clear_all_data(password: str):
    """Clear all orders, expenses, history, and related data. Protected with password."""
    if password != CLEAR_DATA_PASSWORD:
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    # Delete all orders
    await db.orders.delete_many({})
    # Delete all expenses
    await db.expenses.delete_many({})
    # Delete order history
    await db.order_history.delete_many({})
    # Delete daily sales data (for graphs)
    await db.daily_sales.delete_many({})
    # Delete monthly sales data
    await db.monthly_sales.delete_many({})
    # Delete any cached chart data
    await db.chart_cache.delete_many({})
    # Delete stock movements
    await db.stock_movements.delete_many({})
    
    return {"success": True, "message": "Todos os dados foram apagados: pedidos, gastos, histórico e gráficos"}

@api_router.post("/admin/clear-store/{store}")
async def clear_store_data(store: StoreLocation, password: str):
    """Clear all data for a specific store. Protected with password."""
    if password != CLEAR_DATA_PASSWORD:
        raise HTTPException(status_code=403, detail="Senha incorreta")
    
    # Delete orders for this store
    result = await db.orders.delete_many({"store": store.value})
    # Delete expenses for this store
    await db.expenses.delete_many({"$or": [{"store": store.value}, {"store": "all"}]})
    # Delete order history for this store
    await db.order_history.delete_many({"store": store.value})
    # Delete daily sales for this store
    await db.daily_sales.delete_many({"store": store.value})
    # Delete monthly sales for this store
    await db.monthly_sales.delete_many({"store": store.value})
    # Delete stock movements for this store
    await db.stock_movements.delete_many({"store": store.value})
    
    return {"success": True, "message": f"Todos os dados da loja {store.value} apagados: pedidos, gastos, histórico e gráficos", "deleted_count": result.deleted_count}

# ==================== WHATSAPP GREEN API PROXY ====================

@api_router.get("/whatsapp/status")
async def get_whatsapp_status():
    """Get WhatsApp status via Green API"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client_http:
            response = await client_http.get(get_green_api_url("getStateInstance"))
            data = response.json()
            state = data.get("stateInstance", "unknown")
            return {
                "status": "connected" if state == "authorized" else state,
                "connected": state == "authorized",
                "qrCode": None,
                "greenApi": True
            }
    except Exception as e:
        return {"status": "offline", "connected": False, "qrCode": None, "error": str(e)}

@api_router.get("/whatsapp/qr")
async def get_whatsapp_qr():
    """Get WhatsApp QR code via Green API (if needed for reconnection)"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client_http:
            response = await client_http.get(get_green_api_url("qr"))
            data = response.json()
            return {"qrCode": data.get("message"), "connected": False}
    except Exception as e:
        return {"qrCode": None, "connected": False, "error": str(e)}

@api_router.get("/whatsapp/groups")
async def get_whatsapp_groups():
    """Get WhatsApp groups via Green API"""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client_http:
            response = await client_http.get(get_green_api_url("getChats"))
            data = response.json()
            groups = [
                {"id": chat.get("id"), "name": chat.get("name", "Grupo")}
                for chat in data if "@g.us" in chat.get("id", "")
            ]
            return {"success": True, "groups": groups, "currentTarget": WHATSAPP_GROUP_ID}
    except Exception as e:
        return {"success": False, "groups": [], "error": str(e)}

class WhatsAppTargetUpdate(BaseModel):
    target: str

@api_router.post("/whatsapp/set-target")
async def set_whatsapp_target(data: WhatsAppTargetUpdate):
    """Set WhatsApp notification target group"""
    global WHATSAPP_GROUP_ID
    WHATSAPP_GROUP_ID = data.target
    # Save to database for persistence
    await db.settings.update_one(
        {"key": "whatsapp_group_id"},
        {"$set": {"value": data.target, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    return {"success": True, "target": WHATSAPP_GROUP_ID}

class WhatsAppJoinGroup(BaseModel):
    inviteLink: str

@api_router.post("/whatsapp/join-group")
async def join_whatsapp_group(data: WhatsAppJoinGroup):
    """Join a WhatsApp group via invite link using Green API"""
    try:
        # Extract invite code from link
        invite_link = data.inviteLink
        if "chat.whatsapp.com/" in invite_link:
            invite_code = invite_link.split("chat.whatsapp.com/")[1].split("?")[0]
        else:
            invite_code = invite_link
        
        async with httpx.AsyncClient(timeout=30.0) as client_http:
            # Get group info
            response = await client_http.post(
                get_green_api_url("getGroupDataByInviteLink"),
                json={"inviteLink": f"https://chat.whatsapp.com/{invite_code}"}
            )
            group_data = response.json()
            
            if group_data.get("groupJid"):
                group_id = group_data.get("groupJid")
                # Set as target
                global WHATSAPP_GROUP_ID
                WHATSAPP_GROUP_ID = group_id
                await db.settings.update_one(
                    {"key": "whatsapp_group_id"},
                    {"$set": {"value": group_id, "updated_at": datetime.now(timezone.utc).isoformat()}},
                    upsert=True
                )
                return {"success": True, "groupId": group_id, "groupName": group_data.get("groupName")}
            
            return {"success": False, "error": "Could not get group info", "data": group_data}
    except Exception as e:
        return {"success": False, "error": str(e)}

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ==================== LOW STOCK ALERT SYSTEM ====================
# Timezone for Brazil
BRAZIL_TZ = pytz.timezone('America/Sao_Paulo')
LOW_STOCK_THRESHOLD = 2
AUTO_READY_MINUTES = 4  # Minutes after which orders are automatically marked as ready

# Scheduler instance
scheduler = AsyncIOScheduler(timezone=BRAZIL_TZ)

async def auto_mark_orders_ready():
    """Automatically mark orders as 'ready' after AUTO_READY_MINUTES minutes"""
    try:
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(minutes=AUTO_READY_MINUTES)
        cutoff_iso = cutoff_time.isoformat()
        
        # Find orders that are "received" and older than 4 minutes
        result = await db.orders.update_many(
            {
                "status": "received",
                "created_at": {"$lte": cutoff_iso}
            },
            {
                "$set": {
                    "status": "ready",
                    "auto_ready": True,
                    "ready_at": now.isoformat(),
                    "updated_at": now.isoformat()
                }
            }
        )
        
        if result.modified_count > 0:
            logger.info(f"Auto-marked {result.modified_count} orders as ready (after {AUTO_READY_MINUTES} min)")
    except Exception as e:
        logger.error(f"Error in auto_mark_orders_ready: {e}")

async def check_and_save_low_stock_items():
    """Check stock and save items with quantity <= 2 to low_stock_list collection"""
    try:
        # Get all stock items with quantity <= LOW_STOCK_THRESHOLD
        low_stock_items = await db.stock.find({
            "quantity": {"$lte": LOW_STOCK_THRESHOLD, "$gt": 0}
        }).to_list(100)
        
        for item in low_stock_items:
            # Get item name from menu if not in stock record
            item_name = item.get("name")
            if not item_name:
                menu_item = await db.menu.find_one({"id": item.get("menu_item_id")})
                if menu_item:
                    item_name = menu_item.get("name")
                else:
                    # Try to get from default menu
                    item_name = f"Item {item.get('menu_item_id')}"
            
            # Check if already in the list
            existing = await db.low_stock_list.find_one({
                "menu_item_id": item.get("menu_item_id"),
                "store": item.get("store")
            })
            
            if not existing:
                await db.low_stock_list.insert_one({
                    "menu_item_id": item.get("menu_item_id"),
                    "name": item_name,
                    "store": item.get("store"),
                    "quantity": item.get("quantity"),
                    "added_at": datetime.now(timezone.utc).isoformat()
                })
                logger.info(f"Added to low stock list: {item_name} ({item.get('store')}) - {item.get('quantity')} unidades")
            else:
                # Update quantity if changed
                await db.low_stock_list.update_one(
                    {"menu_item_id": item.get("menu_item_id"), "store": item.get("store")},
                    {"$set": {"quantity": item.get("quantity"), "name": item_name}}
                )
        
        # Also check for items that are now out of stock (quantity = 0)
        out_of_stock = await db.stock.find({"quantity": 0}).to_list(100)
        for item in out_of_stock:
            item_name = item.get("name")
            if not item_name:
                menu_item = await db.menu.find_one({"id": item.get("menu_item_id")})
                if menu_item:
                    item_name = menu_item.get("name")
                else:
                    item_name = f"Item {item.get('menu_item_id')}"
            
            existing = await db.low_stock_list.find_one({
                "menu_item_id": item.get("menu_item_id"),
                "store": item.get("store")
            })
            if not existing:
                await db.low_stock_list.insert_one({
                    "menu_item_id": item.get("menu_item_id"),
                    "name": item_name,
                    "store": item.get("store"),
                    "quantity": 0,
                    "added_at": datetime.now(timezone.utc).isoformat()
                })
                logger.info(f"OUT OF STOCK: {item_name} ({item.get('store')})")
                
    except Exception as e:
        logger.error(f"Error checking low stock: {e}")

async def send_morning_shift_report():
    """Send morning shift sales report to WhatsApp groups at 14:00"""
    try:
        brazil_tz = pytz.timezone('America/Sao_Paulo')
        now = datetime.now(brazil_tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        morning_end = now.replace(hour=14, minute=0, second=0, microsecond=0)
        
        for store, group_id, store_name, emoji in [
            ("runner", WHATSAPP_GROUP_RUNNER, "RUNNER", "🏃"),
            ("gym-londres", WHATSAPP_GROUP_ID, "GYM LONDRES", "🏋️")
        ]:
            try:
                # Get morning orders for this store (excluding prazo from totals)
                orders = await db.orders.find({
                    "store": store,
                    "status": {"$in": ["ready", "delivered"]},
                    "created_at": {"$gte": today_start.isoformat()},
                    "payment_method": {"$ne": "prazo"}
                }, {"_id": 0}).to_list(1000)
                
                # Filter only morning orders (before 14:00)
                morning_orders = []
                for order in orders:
                    try:
                        order_time = datetime.fromisoformat(order.get("created_at", "").replace("Z", "+00:00"))
                        order_time_brazil = order_time.astimezone(brazil_tz)
                        # Include orders from 00:00 to 14:00
                        if order_time_brazil.hour < 14:
                            morning_orders.append(order)
                    except Exception:
                        pass
                
                if not morning_orders:
                    logger.info(f"No morning orders for {store_name}, skipping report")
                    continue
                
                # Calculate totals by payment method
                totals = {"pix": 0, "cash": 0, "debit": 0, "credit": 0, "voucher": 0}
                for o in morning_orders:
                    method = o.get("payment_method", "cash")
                    totals[method] = totals.get(method, 0) + o.get("total", 0)
                
                morning_total = sum(totals.values())
                
                # Get prazo payments made this morning
                prazo_payments = await db.prazo_payments.find({
                    "store": store,
                    "created_at": {"$gte": today_start.isoformat()}
                }, {"_id": 0}).to_list(1000)
                prazo_partial = await db.prazo_partial_payments.find({
                    "store": store,
                    "created_at": {"$gte": today_start.isoformat()}
                }, {"_id": 0}).to_list(1000)
                
                # Filter prazo payments for morning only
                prazo_morning = 0
                for p in prazo_payments + prazo_partial:
                    try:
                        p_time = datetime.fromisoformat(p.get("created_at", "").replace("Z", "+00:00"))
                        p_time_brazil = p_time.astimezone(brazil_tz)
                        if p_time_brazil.hour < 14:
                            prazo_morning += p.get("amount", 0)
                    except Exception:
                        pass
                
                # Build message
                message_lines = [
                    f"☀️ *FECHAMENTO TURNO MANHÃ*",
                    f"*{emoji} {store_name}* - {now.strftime('%d/%m/%Y')}",
                    "",
                    "━━━━━━━━━━━━━━━━━━━━━",
                    f"📦 Pedidos: {len(morning_orders)}",
                    "",
                    f"💵 Dinheiro: R$ {totals.get('cash', 0):.2f}",
                    f"📱 PIX: R$ {totals.get('pix', 0):.2f}",
                    f"💳 Débito: R$ {totals.get('debit', 0):.2f}",
                    f"💳 Crédito: R$ {totals.get('credit', 0):.2f}",
                    f"🎫 Voucher: R$ {totals.get('voucher', 0):.2f}",
                    "",
                    "━━━━━━━━━━━━━━━━━━━━━",
                ]
                
                if prazo_morning > 0:
                    message_lines.append(f"💰 Prazo Recebido: R$ {prazo_morning:.2f}")
                    message_lines.append("")
                
                message_lines.extend([
                    f"🎯 *TOTAL MANHÃ: R$ {morning_total + prazo_morning:.2f}*",
                    "",
                    f"_Relatório às {now.strftime('%H:%M')}_"
                ])
                
                message = "\n".join(message_lines)
                result = await send_whatsapp_message(message, group_id)
                
                if result.get("success"):
                    logger.info(f"Morning shift report sent to {store_name}! Total: R$ {morning_total:.2f}")
                else:
                    logger.error(f"Failed to send morning report to {store_name}: {result}")
                    
            except Exception as store_error:
                logger.error(f"Error sending morning report to {store_name}: {store_error}")
                continue  # Continue to next store even if one fails
        
    except Exception as e:
        logger.error(f"Error in send_morning_shift_report: {e}")

async def send_daily_sales_report():
    """Send daily sales report to WhatsApp groups at 22:00 (end of day summary)"""
    try:
        brazil_tz = pytz.timezone('America/Sao_Paulo')
        now = datetime.now(brazil_tz)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Define shifts
        morning_end = now.replace(hour=14, minute=0, second=0, microsecond=0)  # Morning: 00:00 - 14:00
        
        for store, group_id, store_name, emoji in [
            ("runner", WHATSAPP_GROUP_RUNNER, "RUNNER", "🏃"),
            ("gym-londres", WHATSAPP_GROUP_ID, "GYM LONDRES", "🏋️")
        ]:
            # Get today's orders for this store (excluding prazo from totals)
            orders = await db.orders.find({
                "store": store,
                "status": {"$in": ["ready", "delivered"]},
                "created_at": {"$gte": today_start.isoformat()},
                "payment_method": {"$ne": "prazo"}
            }, {"_id": 0}).to_list(1000)
            
            if not orders:
                continue
            
            # Separate by shift
            morning_orders = []
            afternoon_orders = []
            
            for order in orders:
                try:
                    order_time = datetime.fromisoformat(order.get("created_at", "").replace("Z", "+00:00"))
                    order_time_brazil = order_time.astimezone(brazil_tz)
                    if order_time_brazil < morning_end:
                        morning_orders.append(order)
                    else:
                        afternoon_orders.append(order)
                except:
                    afternoon_orders.append(order)
            
            # Calculate totals by payment method
            def calc_totals(order_list):
                totals = {"pix": 0, "cash": 0, "debit": 0, "credit": 0, "voucher": 0}
                for o in order_list:
                    method = o.get("payment_method", "cash")
                    totals[method] = totals.get(method, 0) + o.get("total", 0)
                return totals
            
            morning_totals = calc_totals(morning_orders)
            afternoon_totals = calc_totals(afternoon_orders)
            
            morning_total = sum(morning_totals.values())
            afternoon_total = sum(afternoon_totals.values())
            day_total = morning_total + afternoon_total
            
            # Get prazo payments made today (these count as revenue)
            prazo_payments = await db.prazo_payments.find({
                "store": store,
                "created_at": {"$gte": today_start.isoformat()}
            }, {"_id": 0}).to_list(1000)
            prazo_partial = await db.prazo_partial_payments.find({
                "store": store,
                "created_at": {"$gte": today_start.isoformat()}
            }, {"_id": 0}).to_list(1000)
            
            prazo_received = sum(p.get("amount", 0) for p in prazo_payments) + sum(p.get("amount", 0) for p in prazo_partial)
            
            # Build message
            message_lines = [
                f"📊 *VENDAS DO DIA - {now.strftime('%d/%m/%Y')}*",
                f"*{emoji} {store_name}*",
                "",
                "━━━━━━━━━━━━━━━━━━━━━",
                f"*☀️ TURNO MANHÃ* (até 14h)",
                f"   Pedidos: {len(morning_orders)}",
                f"   💵 Dinheiro: R$ {morning_totals.get('cash', 0):.2f}",
                f"   📱 PIX: R$ {morning_totals.get('pix', 0):.2f}",
                f"   💳 Débito: R$ {morning_totals.get('debit', 0):.2f}",
                f"   💳 Crédito: R$ {morning_totals.get('credit', 0):.2f}",
                f"   🎫 Voucher: R$ {morning_totals.get('voucher', 0):.2f}",
                f"   *Total Manhã: R$ {morning_total:.2f}*",
                "",
                "━━━━━━━━━━━━━━━━━━━━━",
                f"*🌙 TURNO TARDE* (após 14h)",
                f"   Pedidos: {len(afternoon_orders)}",
                f"   💵 Dinheiro: R$ {afternoon_totals.get('cash', 0):.2f}",
                f"   📱 PIX: R$ {afternoon_totals.get('pix', 0):.2f}",
                f"   💳 Débito: R$ {afternoon_totals.get('debit', 0):.2f}",
                f"   💳 Crédito: R$ {afternoon_totals.get('credit', 0):.2f}",
                f"   🎫 Voucher: R$ {afternoon_totals.get('voucher', 0):.2f}",
                f"   *Total Tarde: R$ {afternoon_total:.2f}*",
                "",
                "━━━━━━━━━━━━━━━━━━━━━",
            ]
            
            if prazo_received > 0:
                message_lines.append(f"💰 *Prazo Recebido Hoje: R$ {prazo_received:.2f}*")
                message_lines.append("")
            
            message_lines.extend([
                f"🎯 *TOTAL DO DIA: R$ {day_total + prazo_received:.2f}*",
                f"📦 Total de Pedidos: {len(orders)}",
                "",
                f"_Relatório gerado às {now.strftime('%H:%M')}_"
            ])
            
            message = "\n".join(message_lines)
            result = await send_whatsapp_message(message, group_id)
            
            if result.get("success"):
                logger.info(f"Daily sales report sent to {store_name}! Total: R$ {day_total:.2f}")
        
    except Exception as e:
        logger.error(f"Error sending daily sales report: {e}")

# Endpoint to manually check low stock (for testing)
@api_router.get("/admin/low-stock-list")
async def get_low_stock_list():
    """Get current low stock list"""
    items = await db.low_stock_list.find({}, {"_id": 0}).to_list(100)
    return {"items": items, "count": len(items)}

@api_router.post("/admin/check-low-stock")
async def trigger_low_stock_check():
    """Manually trigger low stock check"""
    await check_and_save_low_stock_items()
    items = await db.low_stock_list.find({}, {"_id": 0}).to_list(100)
    return {"success": True, "items": items, "message": f"Encontrados {len(items)} itens com estoque baixo"}

@api_router.post("/admin/send-low-stock-report")
async def trigger_send_report():
    """Manually trigger sending the low stock report (deprecated)"""
    return {"success": False, "message": "Relatório de estoque baixo desativado. Use /admin/send-sales-report"}

@api_router.post("/admin/send-sales-report")
async def trigger_send_sales_report():
    """Manually trigger sending the daily sales report"""
    await send_daily_sales_report()
    return {"success": True, "message": "Relatório de vendas enviado para os grupos!"}

@api_router.post("/admin/send-morning-report")
async def trigger_send_morning_report():
    """Manually trigger sending the morning shift report"""
    await send_morning_shift_report()
    return {"success": True, "message": "Relatório da manhã enviado para os grupos!"}

@api_router.post("/admin/fix-categories")
async def fix_duplicate_categories():
    """Fix duplicate categories (lowercase to proper case)"""
    category_mapping = {
        "bebidas": "Bebidas Geladas",
        "cafes": "Bebidas Quentes", 
        "outros": "Outros",
        "doces": "Doces"
    }
    
    fixed_count = 0
    for old_cat, new_cat in category_mapping.items():
        result = await db.menu.update_many(
            {"category": old_cat},
            {"$set": {"category": new_cat}}
        )
        fixed_count += result.modified_count
    
    return {"success": True, "fixed_count": fixed_count, "message": f"Corrigidas {fixed_count} categorias"}

@api_router.post("/admin/fix-product-names")
async def fix_product_names(username: str = Depends(verify_gestor)):
    """Normalize misspelled / inconsistent product names in db.menu.
    Returns a list of renames performed and merges of duplicates by normalized name.
    Protected by gestor auth."""
    import re

    # Known spelling fixes (case-insensitive match → canonical name)
    SPELLING_FIXES = {
        "yorgut": "Iogurte",
        "iogurt": "Iogurte",
        "jun gle": "Jungle",
        "agua com gas": "Água com Gás",
        "água com gas": "Água com Gás",
        "agua com gás": "Água com Gás",
        "coca lata normal": "Coca-Cola Lata",
        "coca lata zero": "Coca-Cola Lata Zero",
        "coca cola lata": "Coca-Cola Lata",
        "coca-cola lata normal": "Coca-Cola Lata",
        "cafe gelado": "Café Gelado",
        "cafe expresso": "Café Expresso",
        "cha gelado": "Chá Gelado",
        "chocolate quente": "Chocolate Quente",
    }

    def _title_pt(s: str) -> str:
        connectors = {"e", "de", "da", "do", "das", "dos", "a", "o", "com", "ou", "em"}
        words = s.split()
        out = []
        for i, w in enumerate(words):
            wl = w.lower()
            if i > 0 and wl in connectors:
                out.append(wl)
            elif w.isupper() and len(w) > 1:
                out.append(w)
            else:
                out.append(w[:1].upper() + w[1:].lower())
        return " ".join(out)

    def _canonical(name: str) -> str:
        if not name:
            return name
        cleaned = re.sub(r"\s+", " ", name).strip()
        key = cleaned.lower()
        if key in SPELLING_FIXES:
            return SPELLING_FIXES[key]
        return _title_pt(cleaned)

    items = await db.menu.find({}, {"_id": 0}).to_list(2000)
    renamed = []
    merged = []
    seen = {}

    for it in items:
        original = it.get("name", "")
        canonical = _canonical(original)
        norm_key = canonical.lower()
        item_id = it.get("id")
        if not item_id:
            continue

        if original != canonical:
            await db.menu.update_one({"id": item_id}, {"$set": {"name": canonical}})
            renamed.append({"id": item_id, "from": original, "to": canonical})

        if norm_key in seen:
            kept_id = seen[norm_key]
            await db.menu.delete_one({"id": item_id})
            merged.append({"removed_id": item_id, "kept_id": kept_id, "name": canonical})
        else:
            seen[norm_key] = item_id

    adicionais_docs = await db.adicionais.find({}, {"_id": 0}).to_list(500)
    renamed_adicionais = []
    merged_adicionais = []
    seen_ad = {}
    for a in adicionais_docs:
        original = a.get("name", "")
        canonical = _canonical(original)
        if canonical.lower() in ("2 fruta", "duas fruta"):
            canonical = "2 Frutas"
        norm_key = canonical.lower()
        ad_id = a.get("id")
        if not ad_id:
            continue
        if original != canonical:
            await db.adicionais.update_one({"id": ad_id}, {"$set": {"name": canonical}})
            renamed_adicionais.append({"id": ad_id, "from": original, "to": canonical})
        if norm_key in seen_ad:
            kept_id = seen_ad[norm_key]
            await db.adicionais.delete_one({"id": ad_id})
            merged_adicionais.append({"removed_id": ad_id, "kept_id": kept_id, "name": canonical})
        else:
            seen_ad[norm_key] = ad_id

    return {
        "success": True,
        "renamed": renamed,
        "merged": merged,
        "renamed_adicionais": renamed_adicionais,
        "merged_adicionais": merged_adicionais,
        "totals": {
            "products_renamed": len(renamed),
            "products_merged": len(merged),
            "adicionais_renamed": len(renamed_adicionais),
            "adicionais_merged": len(merged_adicionais),
        }
    }


@api_router.post("/admin/reset-stock-placeholders")
async def reset_stock_placeholders(username: str = Depends(verify_gestor)):
    """Reset stock rows that are still using the legacy '50' placeholder.
    Sets quantity=0 and `stock_unmanaged: true` only for rows never touched
    by the operator (created_at == updated_at OR no updated_at).
    Protected by gestor auth."""
    target = await db.stock.find({"quantity": 50}, {"_id": 0}).to_list(2000)
    reset_ids = []
    now_iso = datetime.now(timezone.utc).isoformat()
    for s in target:
        created = s.get("created_at")
        updated = s.get("updated_at")
        if updated and created and updated != created:
            continue
        await db.stock.update_one(
            {"menu_item_id": s.get("menu_item_id"), "store": s.get("store")},
            {"$set": {"quantity": 0, "stock_unmanaged": True, "updated_at": now_iso}}
        )
        reset_ids.append({"menu_item_id": s.get("menu_item_id"), "store": s.get("store")})
    return {"success": True, "reset_count": len(reset_ids), "reset_ids": reset_ids}


@api_router.get("/admin/prazo-audit-log")
async def get_prazo_audit_log(
    store: str = None,
    customer_id: str = None,
    customer_name: str = None,
    action: str = None,
    limit: int = 200,
    username: str = Depends(verify_gestor)
):
    """Return prazo audit entries from `prazo_history` (single source of truth
    populated by _log_prazo_event in routers/prazo.py).
    Filterable by store / customer / action."""
    q = {}
    if store and store != "all":
        q["store"] = store
    if customer_id:
        q["customer_id"] = customer_id
    if customer_name:
        q["customer_name"] = {"$regex": f"^{re.escape(customer_name)}$", "$options": "i"}
    if action:
        q["event_type"] = action
    rows = await db.prazo_history.find(q, {"_id": 0}).sort("created_at", -1).to_list(min(max(1, limit), 500))
    return {"entries": rows, "count": len(rows)}


@api_router.post("/admin/clear-low-stock-alerts")
async def clear_low_stock_alerts():
    """Clear the low stock alerts list"""
    result = await db.low_stock_list.delete_many({})
    return {"success": True, "deleted_count": result.deleted_count, "message": "Lista de estoque baixo limpa"}

@api_router.post("/admin/fix-payment-method/{payment_id}")
async def fix_payment_method(payment_id: str, new_method: str = "pix"):
    """Fix payment method for a prazo payment record"""
    # Try in prazo_payments
    result = await db.prazo_payments.update_one(
        {"id": payment_id},
        {"$set": {"payment_method": new_method}}
    )
    if result.modified_count > 0:
        return {"success": True, "message": f"Método alterado para {new_method} em prazo_payments"}
    
    # Try in prazo_partial_payments
    result = await db.prazo_partial_payments.update_one(
        {"id": payment_id},
        {"$set": {"payment_method": new_method}}
    )
    if result.modified_count > 0:
        return {"success": True, "message": f"Método alterado para {new_method} em prazo_partial_payments"}
    
    return {"success": False, "message": "Pagamento não encontrado"}

@api_router.get("/admin/stock-debug/{store}")
async def debug_stock(store: str):
    """Debug stock issues - find items with zero or negative stock"""
    # Get ALL stock records including zeros
    all_stock = await db.stock.find({"store": store}, {"_id": 0}).to_list(10000)
    
    zero_stock = [s for s in all_stock if s.get("quantity", 999) <= 0]
    low_stock = [s for s in all_stock if 0 < s.get("quantity", 999) <= 2]
    
    return {
        "store": store,
        "total_stock_records": len(all_stock),
        "zero_or_negative": zero_stock,
        "zero_count": len(zero_stock),
        "low_stock": low_stock,
        "low_count": len(low_stock)
    }

@api_router.post("/admin/fix-zero-stock/{store}")
async def fix_zero_stock(store: str):
    """Remove all stock records with zero or negative quantity (allows orders again)"""
    # Find items with zero stock first
    zero_items = await db.stock.find({
        "store": store,
        "quantity": {"$lte": 0}
    }, {"_id": 0, "name": 1, "menu_item_id": 1, "quantity": 1}).to_list(1000)
    
    # Delete all zero/negative stock records
    result = await db.stock.delete_many({
        "store": store,
        "quantity": {"$lte": 0}
    })
    
    return {
        "success": True,
        "deleted_count": result.deleted_count,
        "deleted_items": zero_items,
        "message": f"Removidos {result.deleted_count} registros de estoque zerado/negativo"
    }

@api_router.post("/admin/clear-withdrawals/{store}")
async def clear_withdrawals(store: str):
    """Clear all cash withdrawals for a store"""
    # Get withdrawals before deleting
    withdrawals = await db.cash_withdrawals.find({"store": store}, {"_id": 0}).to_list(1000)
    total_amount = sum(w.get("amount", 0) for w in withdrawals)
    
    # Delete all withdrawals
    result = await db.cash_withdrawals.delete_many({"store": store})
    
    return {
        "success": True,
        "deleted_count": result.deleted_count,
        "total_amount_cleared": total_amount,
        "message": f"Removidas {result.deleted_count} retiradas totalizando R$ {total_amount:.2f}"
    }

@api_router.get("/admin/check-stock-issues/{store}")
async def check_stock_issues(store: str):
    """Check for stock issues that could block orders"""
    # Get all stock records
    all_stock = await db.stock.find({"store": store}, {"_id": 0}).to_list(10000)
    
    # Get menu items
    menu_items = await db.menu.find({"store": store}, {"_id": 0, "id": 1, "name": 1}).to_list(1000)
    menu_dict = {str(m.get("id")): m.get("name") for m in menu_items}
    
    issues = []
    for s in all_stock:
        qty = s.get("quantity", 0)
        menu_id = s.get("menu_item_id")
        name = s.get("name") or menu_dict.get(menu_id, f"ID {menu_id}")
        
        if qty <= 0:
            issues.append({
                "menu_item_id": menu_id,
                "name": name,
                "quantity": qty,
                "issue": "ZERO_OR_NEGATIVE - Will block orders"
            })
        elif qty <= 2:
            issues.append({
                "menu_item_id": menu_id,
                "name": name,
                "quantity": qty,
                "issue": "LOW_STOCK - Warning only"
            })
    
    return {
        "store": store,
        "total_stock_records": len(all_stock),
        "issues_count": len(issues),
        "issues": issues
    }

async def _register_manual_morning_sales_runner_v1():
    """ONE-TIME idempotent insert: registers manual morning sales for Runner.
    R$ 600,55 no Crédito + R$ 416,00 no Débito — turno da manhã, status entregue.
    Roda no startup APENAS na primeira vez (marcador em db.deploy_markers).
    Em redeploys futuros, o marker já existe e nada acontece.
    """
    MARKER_ID = "manual_morning_sales_runner_v1"
    try:
        existing = await db.deploy_markers.find_one({"marker_id": MARKER_ID})
        if existing:
            logger.info(f"[STARTUP TASK] {MARKER_ID} já executado em {existing.get('executed_at')}; pulando.")
            return

        brazil_tz = pytz.timezone("America/Sao_Paulo")
        now_brz = datetime.now(brazil_tz)
        # Horário "da manhã" no fuso de Brasília → UTC
        morning_brz = now_brz.replace(hour=9, minute=0, second=0, microsecond=0)
        morning_utc = morning_brz.astimezone(timezone.utc)

        orders_to_insert = [
            {
                "id": str(uuid.uuid4()),
                "store": "runner",
                "customer_name": "Vendas Manhã (Crédito)",
                "items": [{
                    "menu_item_id": "manual-morning-credit",
                    "name": "Vendas manhã - Crédito",
                    "category": "Outros",
                    "price": 600.55,
                    "quantity": 1,
                }],
                "total": 600.55,
                "original_total": 600.55,
                "payment_method": "credit",
                "pickup_time": "manha",
                "status": "delivered",
                "created_at": morning_utc.isoformat(),
                "delivered_at": morning_utc.isoformat(),
                "manual_morning_sale": True,
            },
            {
                "id": str(uuid.uuid4()),
                "store": "runner",
                "customer_name": "Vendas Manhã (Débito)",
                "items": [{
                    "menu_item_id": "manual-morning-debit",
                    "name": "Vendas manhã - Débito",
                    "category": "Outros",
                    "price": 416.00,
                    "quantity": 1,
                }],
                "total": 416.00,
                "original_total": 416.00,
                "payment_method": "debit",
                "pickup_time": "manha",
                "status": "delivered",
                "created_at": (morning_utc + timedelta(minutes=1)).isoformat(),
                "delivered_at": (morning_utc + timedelta(minutes=1)).isoformat(),
                "manual_morning_sale": True,
            },
        ]
        await db.orders.insert_many(orders_to_insert)
        await db.deploy_markers.insert_one({
            "marker_id": MARKER_ID,
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "details": "Inseridos 2 pedidos manuais: Runner R$ 600,55 Crédito + R$ 416,00 Débito (manhã).",
        })
        logger.info(f"[STARTUP TASK] {MARKER_ID} executado: 2 pedidos manuais inseridos.")
    except Exception as e:
        logger.exception(f"[STARTUP TASK] Falha em {MARKER_ID}: {e}")


@app.on_event("startup")
async def startup_db_client():
    """Initialize database, scheduler and default tenant"""
    await ensure_default_tenant()
    await _register_manual_morning_sales_runner_v1()
    
    # Performance: create indexes on hot query paths
    try:
        await db.orders.create_index([("store", 1), ("status", 1)])
        await db.orders.create_index([("store", 1), ("created_at", -1)])
        await db.orders.create_index([("status", 1), ("created_at", -1)])
        await db.stock.create_index([("store", 1), ("menu_item_id", 1)])
        await db.pix_adjustments.create_index([("store", 1), ("created_at", -1)])
        await db.prazo_debts.create_index([("store", 1), ("status", 1)])
        await db.prazo_payments.create_index([("store", 1), ("created_at", -1)])
        await db.prazo_partial_payments.create_index([("store", 1), ("created_at", -1)])
        await db.cash_withdrawals.create_index([("store", 1), ("created_at", -1)])
        await db.tenants.create_index("username", unique=True)
        logger.info("MongoDB indexes ensured (performance optimization)")
    except Exception as e:
        logger.warning(f"Could not ensure all indexes (non-fatal): {e}")
    
    # Schedule auto-ready check every minute
    scheduler.add_job(auto_mark_orders_ready, 'interval', minutes=1, id='auto_ready_orders')
    
    # Schedule MORNING shift report at 14:00 Brazil time
    scheduler.add_job(
        send_morning_shift_report, 
        CronTrigger(hour=14, minute=0, timezone=BRAZIL_TZ),
        id='morning_shift_report'
    )
    
    # Schedule daily SALES report at 22:00 Brazil time (end of day summary)
    scheduler.add_job(
        send_daily_sales_report, 
        CronTrigger(hour=22, minute=0, timezone=BRAZIL_TZ),
        id='daily_sales_report'
    )
    
    scheduler.start()
    logger.info("Database initialized, default tenant ensured")
    logger.info("Scheduler started - Auto-ready every 1 min, Morning report at 14:00, Daily report at 22:00")

@app.on_event("shutdown")
async def shutdown_db_client():
    scheduler.shutdown()
    client.close()

# Import and configure new routers
from routers import prazo, menu, stock, cash, live

# Initialize dependencies for new routers
prazo.set_dependencies(db, PRAZO_PASSWORD, send_whatsapp_message)
menu.set_dependencies(db, verify_gestor)
stock.set_dependencies(db)
cash.set_dependencies(db, BRAZIL_TZ)
live.set_dependencies(db, BRAZIL_TZ)

# Include routers - api_router must be LAST to ensure new routers take priority
api_router.include_router(prazo.router)
api_router.include_router(menu.router)
api_router.include_router(stock.router)
api_router.include_router(cash.router)
api_router.include_router(live.router)

app.include_router(api_router)
