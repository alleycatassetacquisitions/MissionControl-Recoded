"""POST /config — MCS peer hub pushes MCS base/token (+ optional public_base)."""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.runtime_config import apply_config, auth_token_matches, mcs_token

_LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["ops"])
_bearer = HTTPBearer(auto_error=False)


class GbnConfigUpdate(BaseModel):
    mcs_base: str = ""
    mcs_token: str = ""
    public_base: str = Field(
        default="",
        description="Optional public base for poster links when no request Host",
    )


def _verify_venue_token(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Security(_bearer)
    ] = None,
) -> str:
    """Auth with current GBN_MCS_TOKEN (same Bearer MCS uses to fan-out)."""
    bearer = credentials.credentials if credentials else None
    expected = mcs_token()
    if expected:
        if not auth_token_matches(bearer):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing Bearer token.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return bearer or ""
    if not bearer:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GBN MCS token not configured.",
        )
    return bearer


@router.post("/config", status_code=status.HTTP_204_NO_CONTENT)
async def post_config(
    body: GbnConfigUpdate,
    token: Annotated[str, Depends(_verify_venue_token)],
) -> None:
    """Called by MCS peer fan-out (not by Home Assistant)."""
    new_token = (body.mcs_token or "").strip() or token
    applied = apply_config(
        mcs_base=body.mcs_base,
        mcs_token=new_token,
        public_base=body.public_base,
    )
    _LOGGER.info("GBN /config applied — %s", applied)
