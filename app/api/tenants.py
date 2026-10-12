"""REST endpoints for tenant resources."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import TenantCreate, TenantPatch, TenantRead
from app.services import tenant_service

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantRead, status_code=status.HTTP_202_ACCEPTED)
def create_tenant(
    payload: TenantCreate, response: Response, db: Annotated[Session, Depends(get_db)]
):
    tenant, task = tenant_service.create_tenant(db, payload.slug, payload.name)
    response.headers["Location"] = f"/tenants/{tenant.id}"
    response.headers["X-Task-ID"] = task.id
    return tenant


@router.get("", response_model=list[TenantRead])
def list_tenants(
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    return tenant_service.list_tenants(db, limit, offset)


@router.get("/{tenant_id}", response_model=TenantRead)
def get_tenant(tenant_id: str, db: Annotated[Session, Depends(get_db)]):
    return tenant_service.get_tenant(db, tenant_id)


@router.patch("/{tenant_id}", response_model=TenantRead)
def update_tenant(
    tenant_id: str,
    payload: TenantPatch,
    response: Response,
    db: Annotated[Session, Depends(get_db)],
):
    tenant, task = tenant_service.update_tenant(
        db, tenant_id, payload.version, payload.name
    )
    response.headers["X-Task-ID"] = task.id
    return tenant


@router.delete("/{tenant_id}", status_code=status.HTTP_202_ACCEPTED)
def delete_tenant(
    tenant_id: str, response: Response, db: Annotated[Session, Depends(get_db)]
):
    tenant, task = tenant_service.delete_tenant(db, tenant_id)
    response.headers["X-Task-ID"] = task.id
    return {"tenant_id": tenant.id, "status": tenant.status, "task_id": task.id}
