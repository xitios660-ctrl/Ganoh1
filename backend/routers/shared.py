"""Shared configuration and utilities"""
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional, List
import pytz
import uuid

# Timezone
BRAZIL_TZ = pytz.timezone("America/Sao_Paulo")

# Store configuration
STORES = {
    "runner": {"name": "GANOH Café Bistrô - Runner", "address": "Runner"},
    "gym-londres": {"name": "GANOH Café Bistrô - GYM Londres", "address": "GYM Londres"}
}

# ==================== ENUMS ====================

class OrderStatus(str, Enum):
    PENDING_PAYMENT = "pending_payment"
    PAYMENT_REJECTED = "payment_rejected"
    RECEIVED = "received"
    PREPARING = "preparing"
    READY = "ready"
    DELIVERED = "delivered"

class PaymentMethod(str, Enum):
    PIX = "pix"
    DEBIT = "debit"
    CREDIT = "credit"
    CASH = "cash"
    PRAZO = "prazo"

class StoreLocation(str, Enum):
    RUNNER = "runner"
    GYM_LONDRES = "gym-londres"

# ==================== MODELS ====================

class MenuItem(BaseModel):
    id: str
    name: str
    description: str = ""
    price: float
    category: str
    image: str = ""
    available: bool = True
    prep_time: int = 15

class StockItem(BaseModel):
    menu_item_id: str
    store: str
    quantity: int
    min_quantity: int = 5
    item_name: Optional[str] = None

class StockUpdate(BaseModel):
    quantity: int

class OrderItem(BaseModel):
    menu_item_id: str
    name: str
    price: float
    quantity: int = 1

class Order(BaseModel):
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
    synced: bool = True

class OrderCreate(BaseModel):
    store: StoreLocation
    customer_name: str
    items: List[OrderItem]
    total: float
    payment_method: PaymentMethod
    pickup_time: Optional[str] = None
    offline_id: Optional[str] = None
    pix_proof: Optional[str] = None

class OrderStatusUpdate(BaseModel):
    status: OrderStatus

class PixProofUpload(BaseModel):
    proof_image: str

class PaymentApproval(BaseModel):
    approved: bool
    rejection_reason: Optional[str] = None

class SalesReport(BaseModel):
    total_sales: float
    order_count: int
    by_payment_method: dict
    date: str

# ==================== HELPER FUNCTIONS ====================

def get_brazil_now():
    """Get current time in Brazil timezone"""
    return datetime.now(BRAZIL_TZ)

def get_today_start_utc():
    """Get start of today in UTC (based on Brazil timezone)"""
    now_brazil = get_brazil_now()
    today_brazil = now_brazil.replace(hour=0, minute=0, second=0, microsecond=0)
    return today_brazil.astimezone(pytz.UTC)

def get_month_start_utc():
    """Get start of current month in UTC (based on Brazil timezone)"""
    now_brazil = get_brazil_now()
    month_start_brazil = now_brazil.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return month_start_brazil.astimezone(pytz.UTC)
