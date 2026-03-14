"""
Installation wizard endpoints.
Handles first-run setup: license key validation, org creation, LLM config, API keys, first admin user.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from app.db.session import get_db
from app.models.organization import Organization
from app.models.user import User, UserRole
from app.models.tenant_settings import TenantSettings
from app.core.security import hash_password, create_access_token
from app.core.license import validate_key, LicenseError
from app.schemas.auth import Token

from app.core.logging_config import get_logger
logger = get_logger(__name__)


router = APIRouter()


class SetupStep1(BaseModel):
    """Organization + branding"""
    license_key: str
    org_name: str
    org_slug: str
    spokesperson_name: str
    spokesperson_title: str
    spokesperson_credential: str | None = None
    primary_color: str = "#0F172A"


class SetupStep2(BaseModel):
    """LLM configuration"""
    llm_provider: str   # openai | anthropic | ollama
    llm_api_key: str | None = None
    llm_model: str


class SetupStep3(BaseModel):
    """Email configuration"""
    email_provider: str  # gmail | smtp
    email_address: str
    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None


class SetupStep4(BaseModel):
    """External integrations (all optional)"""
    # Lead sources
    apollo_api_key:       str | None = None
    hunter_api_key:       str | None = None
    snov_client_id:       str | None = None
    snov_client_secret:   str | None = None
    # Research + notifications
    brave_search_api_key: str | None = None
    telegram_bot_token:   str | None = None
    telegram_chat_id:     str | None = None


class SetupComplete(BaseModel):
    """First admin account"""
    username: str
    password: str


class ValidateKeyRequest(BaseModel):
    license_key: str


@router.post("/validate-key")
async def validate_license_key(data: ValidateKeyRequest):
    """Step 0 — validate license key before allowing setup to proceed."""
    try:
        info = validate_key(data.license_key)
        return {
            "valid":   True,
            "org":     info.org,
            "tier":    info.tier,
            "seats":   info.seats,
            "expires": info.expires.isoformat() if info.expires else None,
        }
    except LicenseError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status")
async def wizard_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Organization))
    org = result.scalar_one_or_none()
    return {"completed": org is not None}


@router.post("/step/1")
async def setup_step1(data: SetupStep1, db: AsyncSession = Depends(get_db)):
    # Re-validate license key server-side
    try:
        license_info = validate_key(data.license_key)
    except LicenseError as e:
        raise HTTPException(400, f"License key invalid: {e}")

    existing = await db.execute(select(Organization).where(Organization.slug == data.org_slug))
    if existing.scalar_one_or_none():
        raise HTTPException(400, "Slug already taken")

    org_data = data.model_dump()
    org_data.pop("license_key")
    org = Organization(**org_data)
    db.add(org)
    await db.flush()

    # Create TenantSettings and store license
    settings = TenantSettings(
        organization_id=org.id,
        license_key=data.license_key,
        license_tier=license_info.tier,
        license_seats=license_info.seats,
    )
    db.add(settings)
    await db.commit()
    await db.refresh(org)
    return {"org_id": org.id}


@router.post("/step/2")
async def setup_step2(org_id: str, data: SetupStep2, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TenantSettings).where(TenantSettings.organization_id == org_id))
    settings = result.scalar_one_or_none()
    if not settings:
        settings = TenantSettings(organization_id=org_id)
        db.add(settings)
    settings.llm_provider = data.llm_provider
    settings.llm_api_key_enc = data.llm_api_key  # TODO: encrypt
    settings.llm_model = data.llm_model
    settings.wizard_step = 2
    await db.commit()
    return {"ok": True}


@router.post("/step/3")
async def setup_step3(org_id: str, data: SetupStep3, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TenantSettings).where(TenantSettings.organization_id == org_id))
    settings = result.scalar_one_or_none()
    settings.email_provider = data.email_provider
    settings.email_address = data.email_address
    settings.smtp_host = data.smtp_host
    settings.smtp_port = data.smtp_port
    settings.smtp_user = data.smtp_user
    settings.smtp_password_enc = data.smtp_password  # TODO: encrypt
    settings.wizard_step = 3
    await db.commit()
    return {"ok": True}


@router.post("/step/4")
async def setup_step4(org_id: str, data: SetupStep4, db: AsyncSession = Depends(get_db)):
    import json as _json

    result = await db.execute(select(TenantSettings).where(TenantSettings.organization_id == org_id))
    settings = result.scalar_one_or_none()

    # Apollo — dedicated column (also mirrored into lead_sources_config for consistency)
    if data.apollo_api_key:
        settings.apollo_api_key_enc = data.apollo_api_key

    # Brave Search + Telegram — dedicated columns
    if data.brave_search_api_key:
        settings.brave_search_api_key_enc = data.brave_search_api_key
    if data.telegram_bot_token:
        settings.telegram_bot_token_enc   = data.telegram_bot_token
    if data.telegram_chat_id:
        settings.telegram_chat_id         = data.telegram_chat_id

    # Lead sources (Hunter, Snov + Apollo mirror) — stored in lead_sources_config JSON
    try:
        lsc: dict = _json.loads(settings.lead_sources_config or "{}")
    except Exception:
        lsc = {}

    if data.apollo_api_key:
        lsc.setdefault("apollo", {})["api_key"] = data.apollo_api_key
        lsc["apollo"]["status"] = "saved"
    if data.hunter_api_key:
        lsc.setdefault("hunter", {})["api_key"] = data.hunter_api_key
        lsc["hunter"]["status"] = "saved"
    if data.snov_client_id:
        lsc.setdefault("snov", {})["client_id"] = data.snov_client_id
        lsc["snov"]["status"] = "saved"
    if data.snov_client_secret:
        lsc.setdefault("snov", {})["client_secret"] = data.snov_client_secret
        lsc["snov"]["status"] = "saved"

    settings.lead_sources_config = _json.dumps(lsc)
    settings.wizard_step = 4
    await db.commit()
    return {"ok": True}


@router.post("/complete", response_model=Token)
async def setup_complete(org_id: str, data: SetupComplete, db: AsyncSession = Depends(get_db)):
    """Create first admin user and mark wizard complete."""
    user = User(
        organization_id=org_id,
        username=data.username,
        full_name=data.username,
        hashed_password=hash_password(data.password),
        role=UserRole.admin,
    )
    db.add(user)

    result = await db.execute(select(TenantSettings).where(TenantSettings.organization_id == org_id))
    settings = result.scalar_one_or_none()
    settings.wizard_completed = True
    settings.wizard_step = 5

    await db.commit()
    token = create_access_token({"sub": user.id, "org": org_id, "role": user.role})
    return {"access_token": token, "token_type": "bearer"}
