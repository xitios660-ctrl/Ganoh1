"""Authentication and Tenant Routes"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/auth", tags=["Authentication"])

# Will be set by main app
db = None
security = HTTPBasic()

def set_db(database):
    global db
    db = database

# ==================== MODELS ====================

class TenantCreate(BaseModel):
    username: str
    password: str
    business_name: str

class TenantLogin(BaseModel):
    username: str
    password: str

class TenantResponse(BaseModel):
    id: str
    username: str
    business_name: str
    created_at: str

# ==================== HELPER FUNCTIONS ====================

async def get_tenant_by_credentials(username: str, password: str):
    tenant = await db.tenants.find_one({
        "username": username,
        "password": password
    })
    return tenant

async def get_tenant_by_id(tenant_id: str):
    return await db.tenants.find_one({"id": tenant_id})

def verify_gestor(credentials: HTTPBasicCredentials = Depends(security)):
    import os
    GESTOR_USERNAME = os.environ.get("GESTOR_USERNAME", "gestor")
    GESTOR_PASSWORD = os.environ.get("GESTOR_PASSWORD", "admin123")
    
    if credentials.username != GESTOR_USERNAME or credentials.password != GESTOR_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# ==================== ROUTES ====================

@router.post("/register")
async def register_tenant(tenant: TenantCreate):
    # Check if max tenants reached (2)
    tenant_count = await db.tenants.count_documents({})
    if tenant_count >= 2:
        raise HTTPException(status_code=400, detail="Máximo de 2 contas atingido")
    
    # Check if username already exists
    existing = await db.tenants.find_one({"username": tenant.username})
    if existing:
        raise HTTPException(status_code=400, detail="Nome de usuário já existe")
    
    # Create tenant
    tenant_doc = {
        "id": str(uuid.uuid4()),
        "username": tenant.username,
        "password": tenant.password,
        "business_name": tenant.business_name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    
    await db.tenants.insert_one(tenant_doc)
    
    return TenantResponse(
        id=tenant_doc["id"],
        username=tenant_doc["username"],
        business_name=tenant_doc["business_name"],
        created_at=tenant_doc["created_at"]
    )

@router.post("/login")
async def login_tenant(credentials: TenantLogin):
    tenant = await get_tenant_by_credentials(credentials.username, credentials.password)
    if not tenant:
        raise HTTPException(status_code=401, detail="Credenciais inválidas")
    
    return {
        "id": tenant["id"],
        "username": tenant["username"],
        "business_name": tenant["business_name"]
    }

@router.get("/accounts")
async def list_accounts():
    """Return only counts to prevent user enumeration."""
    count = await db.tenants.count_documents({})
    return {
        "accounts": [],
        "count": count,
        "max_accounts": 2
    }

@router.get("/check/{tenant_id}")
async def check_tenant(tenant_id: str):
    tenant = await get_tenant_by_id(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Conta não encontrada")
    
    return {
        "id": tenant["id"],
        "username": tenant["username"],
        "business_name": tenant["business_name"]
    }
