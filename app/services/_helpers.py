"""Shared service helpers: typed 404 lookup used by all services/routers."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session


def get_or_404(db: Session, model, obj_id: int, name: str = "Not found"):
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(404, name)
    return obj
