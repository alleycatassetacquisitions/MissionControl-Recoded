"""CRUD for poster chrome templates."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request

from app.models import PosterTemplate, PosterTemplateCreate, PosterTemplateUpdate
from app.template_store import TemplateStore

_LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["poster-templates"])


def _store(request: Request) -> TemplateStore:
    return request.app.state.template_store


@router.get("/api/poster-templates", response_model=list[PosterTemplate])
async def list_templates(request: Request) -> list[PosterTemplate]:
    return _store(request).list()


@router.get("/api/poster-templates/{template_id}", response_model=PosterTemplate)
async def get_template(template_id: str, request: Request) -> PosterTemplate:
    found = _store(request).get(template_id)
    if not found:
        raise HTTPException(status_code=404, detail="Template not found")
    return found


@router.post("/api/poster-templates", response_model=PosterTemplate)
async def create_template(
    body: PosterTemplateCreate, request: Request
) -> PosterTemplate:
    name = (body.name or "").strip()
    headline = (body.headline or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if not headline:
        raise HTTPException(status_code=400, detail="headline is required")
    try:
        created = _store(request).create(
            name=name,
            headline=headline,
            subtitle=body.subtitle,
            amount_label=body.amount_label,
            list_label=body.list_label,
            list_empty=body.list_empty,
            template_id=body.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _LOGGER.info("Created poster template %s (%s)", created.id, created.name)
    return created


@router.put("/api/poster-templates/{template_id}", response_model=PosterTemplate)
async def update_template(
    template_id: str, body: PosterTemplateUpdate, request: Request
) -> PosterTemplate:
    try:
        return _store(request).update(
            template_id,
            name=body.name,
            headline=body.headline,
            subtitle=body.subtitle,
            amount_label=body.amount_label,
            list_label=body.list_label,
            list_empty=body.list_empty,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Template not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/api/poster-templates/{template_id}")
async def delete_template(template_id: str, request: Request) -> dict:
    try:
        _store(request).delete(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Template not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _LOGGER.info("Deleted poster template %s", template_id)
    return {"ok": True, "id": template_id}
