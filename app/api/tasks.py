"""Read-only REST endpoints for provisioning tasks."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import TaskRead
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskRead])
def list_tasks(
    db: Annotated[Session, Depends(get_db)],
    tenant_id: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return task_service.list_tasks(db, limit, offset, tenant_id)


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: str, db: Annotated[Session, Depends(get_db)]):
    return task_service.get_task(db, task_id)
