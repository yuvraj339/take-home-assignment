"""Tenant operations and state-machine guards."""

import json
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.outbox import OutboxEvent
from app.models.task import Task
from app.models.tenant import Tenant


class DomainError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _new_task(db: Session, tenant: Tenant, task_type: str) -> Task:
    task = Task(id=str(uuid4()), type=task_type, tenant_id=tenant.id, status="accepted")
    db.add(task)
    # Store exactly the task fields needed to reconstruct the event. The publisher
    # only sees committed outbox rows, so rollback can never leak a task event.
    payload = {
        "id": task.id,
        "type": task.type,
        "tenant_id": task.tenant_id,
        "status": task.status,
    }
    db.add(OutboxEvent(id=task.id, payload=json.dumps(payload)))
    return task


def create_tenant(db: Session, slug: str, name: str) -> tuple[Tenant, Task]:
    tenant = Tenant(slug=slug, name=name, status="provisioning", version=1)
    try:
        db.add(tenant)
        db.flush()
        task = _new_task(db, tenant, "deploy")
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        # The slug constraint is the authority even under simultaneous requests.
        raise DomainError(
            "tenant_already_exists", "A tenant with this slug already exists", 409
        ) from exc
    db.refresh(tenant)
    db.refresh(task)
    return tenant, task


def list_tenants(db: Session, limit: int, offset: int) -> list[Tenant]:
    return list(
        db.scalars(
            select(Tenant)
            .order_by(Tenant.created_at, Tenant.id)
            .limit(limit)
            .offset(offset)
        )
    )


def get_tenant(db: Session, tenant_id: str) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise DomainError("tenant_not_found", "Tenant does not exist", 404)
    return tenant


def update_tenant(
    db: Session, tenant_id: str, expected_version: int, name: str | None
) -> tuple[Tenant, Task]:
    tenant = get_tenant(db, tenant_id)
    if tenant.version != expected_version:
        raise DomainError(
            "tenant_version_conflict", "Tenant version does not match", 409
        )
    if tenant.status != "active":
        raise DomainError(
            "tenant_update_not_allowed", "Only active tenants can be updated", 409
        )
    changed = db.execute(
        update(Tenant)
        .where(
            Tenant.id == tenant_id,
            Tenant.version == expected_version,
            Tenant.status == "active",
        )
        .values(
            name=name if name is not None else tenant.name,
            status="updating",
            version=Tenant.version + 1,
        )
    )
    if changed.rowcount != 1:
        db.rollback()
        raise DomainError(
            "tenant_version_conflict", "Tenant changed during this request", 409
        )
    tenant = get_tenant(db, tenant_id)
    task = _new_task(db, tenant, "update")
    db.commit()
    db.refresh(tenant)
    db.refresh(task)
    return tenant, task


def delete_tenant(db: Session, tenant_id: str) -> tuple[Tenant, Task]:
    tenant = get_tenant(db, tenant_id)
    if tenant.status not in {"active", "failed"}:
        raise DomainError(
            "tenant_update_not_allowed",
            "Only active or failed tenants can be deleted",
            409,
        )
    changed = db.execute(
        update(Tenant)
        .where(
            Tenant.id == tenant_id,
            Tenant.status == tenant.status,
            Tenant.version == tenant.version,
        )
        .values(status="destroying", version=Tenant.version + 1)
    )
    if changed.rowcount != 1:
        db.rollback()
        raise DomainError(
            "tenant_version_conflict", "Tenant changed during this request", 409
        )
    tenant = get_tenant(db, tenant_id)
    task = _new_task(db, tenant, "destroy")
    db.commit()
    db.refresh(tenant)
    db.refresh(task)
    return tenant, task
