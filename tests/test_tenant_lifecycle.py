"""State, idempotency, and optimistic-version behavior."""

import pytest

from app.models.outbox import OutboxEvent
from app.models.processed_message import ProcessedMessage
from app.services.task_service import apply_worker_update
from app.services.tenant_service import (
    DomainError,
    create_tenant,
    delete_tenant,
    get_tenant,
    update_tenant,
)


def send(db, task_id: str, message_id: str, state: str) -> bool:
    return apply_worker_update(
        db, {"message_id": message_id, "task_id": task_id, "status": state}
    )


def test_create_persists_tenant_task_and_outbox_atomically(db_session):
    tenant, task = create_tenant(db_session, "acme-prod", "Acme Production")

    assert tenant.status == "provisioning"
    assert tenant.version == 1
    assert task.type == "deploy"
    assert task.status == "accepted"
    event = db_session.get(OutboxEvent, task.id)
    assert event is not None
    assert '"tenant_id"' in event.payload
    assert event.published_at is None


def test_duplicate_slug_is_rejected_and_destroyed_slug_stays_reserved(db_session):
    tenant, deploy = create_tenant(db_session, "acme-prod", "Acme")
    send(db_session, deploy.id, "deploy-progress", "in_progress")
    send(db_session, deploy.id, "deploy-done", "done")
    _, destroy = delete_tenant(db_session, tenant.id)
    send(db_session, destroy.id, "destroy-done", "done")

    assert get_tenant(db_session, tenant.id).status == "destroyed"
    with pytest.raises(DomainError) as error:
        create_tenant(db_session, "acme-prod", "Another Acme")
    assert error.value.code == "tenant_already_exists"


def test_worker_update_is_idempotent_and_stale_progress_does_not_regress(db_session):
    tenant, task = create_tenant(db_session, "acme-prod", "Acme")
    assert send(db_session, task.id, "progress-1", "in_progress") is True
    assert send(db_session, task.id, "done-1", "done") is True
    assert send(db_session, task.id, "done-1", "done") is False
    assert send(db_session, task.id, "late-progress", "in_progress") is True

    assert db_session.get(type(task), task.id).status == "done"
    assert get_tenant(db_session, tenant.id).status == "active"
    assert db_session.get(ProcessedMessage, "done-1") is not None


def test_terminal_result_can_arrive_before_progress(db_session):
    tenant, task = create_tenant(db_session, "acme-prod", "Acme")
    send(db_session, task.id, "fast-done", "done")
    send(db_session, task.id, "late-progress", "in_progress")

    assert db_session.get(type(task), task.id).status == "done"
    assert get_tenant(db_session, tenant.id).status == "active"


def test_update_requires_active_state_and_expected_version(db_session):
    tenant, deploy = create_tenant(db_session, "acme-prod", "Acme")
    with pytest.raises(DomainError) as error:
        update_tenant(db_session, tenant.id, 1, "New Name")
    assert error.value.code == "tenant_update_not_allowed"

    send(db_session, deploy.id, "deploy-done", "done")
    updated, update_task = update_tenant(db_session, tenant.id, 2, "Renamed Acme")
    assert updated.status == "updating"
    assert updated.name == "Renamed Acme"
    assert update_task.type == "update"
    assert updated.version == 3

    with pytest.raises(DomainError) as error:
        update_tenant(db_session, tenant.id, 2, "Stale Name")
    assert error.value.code == "tenant_version_conflict"


def test_failed_tenant_can_be_destroyed(db_session):
    tenant, task = create_tenant(db_session, "acme-prod", "Acme")
    send(db_session, task.id, "deploy-failed", "failed")
    assert get_tenant(db_session, tenant.id).status == "failed"
    _, destroy = delete_tenant(db_session, tenant.id)
    assert destroy.type == "destroy"
    assert get_tenant(db_session, tenant.id).status == "destroying"
