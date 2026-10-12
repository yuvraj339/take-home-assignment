"""Task queries and transactional worker-update application."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.processed_message import ProcessedMessage
from app.models.task import Task
from app.models.tenant import Tenant
from app.services.tenant_service import DomainError


def list_tasks(
    db: Session, limit: int, offset: int, tenant_id: str | None = None
) -> list[Task]:
    query = select(Task).order_by(Task.created_at, Task.id).limit(limit).offset(offset)
    if tenant_id is not None:
        query = query.where(Task.tenant_id == tenant_id)
    return list(db.scalars(query))


def get_task(db: Session, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise DomainError("task_not_found", "Task does not exist", 404)
    return task


def apply_worker_update(db: Session, message: dict) -> bool:
    """Apply a worker message once; return False for duplicate or stale updates."""
    message_id = message["message_id"]
    task = db.scalar(
        select(Task).where(Task.id == message["task_id"]).with_for_update()
    )
    if task is None:
        raise ValueError("message references an unknown task")

    # Locking the task serializes distinct messages too; the inbox key handles redelivery.
    if db.get(ProcessedMessage, message_id) is not None:
        db.rollback()
        return False
    try:
        db.add(ProcessedMessage(message_id=message_id))
        requested = message["status"]
        if task.status not in {"done", "failed"}:
            if requested == "in_progress" and task.status == "accepted":
                task.status = "in_progress"
            elif requested in {"done", "failed"}:
                # Permit terminal result directly from accepted so delivery order does
                # not leave a completed task stuck when in_progress was delayed.
                task.status = requested
                tenant = db.scalar(
                    select(Tenant).where(Tenant.id == task.tenant_id).with_for_update()
                )
                if tenant is not None:
                    if requested == "failed":
                        tenant.status = "failed"
                    elif task.type in {"deploy", "update"}:
                        tenant.status = "active"
                    elif task.type == "destroy":
                        tenant.status = "destroyed"
                    tenant.version += 1
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False
