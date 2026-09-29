"""Flavor generation endpoint (templates now, local LLM later)."""
from __future__ import annotations

from fastapi import APIRouter

from app.models import FlavorRequest, FlavorResponse
from app.services.flavor import generate_flavor

router = APIRouter(tags=["flavor"])


@router.post("/api/flavor/generate", response_model=FlavorResponse)
async def flavor_generate(body: FlavorRequest) -> FlavorResponse:
    """Generate poster flavor text / crimes / stats / mock bounty."""
    return generate_flavor(body.name, body.neocorp, body.role)
