"""Consume worker progress updates without losing committed state changes."""

import json
import logging
import time
from functools import partial

from app.config import UPDATE_QUEUE
from app.db import SessionLocal
from app.messaging import connect, declare_queues
from app.services.task_service import apply_worker_update

logger = logging.getLogger(__name__)


def _valid_message(message: dict) -> None:
    if not isinstance(message.get("message_id"), str) or not message["message_id"]:
        raise ValueError("message_id is required")
    if not isinstance(message.get("task_id"), str) or not message["task_id"]:
        raise ValueError("task_id is required")
    if message.get("status") not in {"in_progress", "done", "failed"}:
        raise ValueError("status is invalid")


def _handle_update(ch, method, properties, body, *, retry_attempts: dict[str, int]):
    message_key = properties.message_id or body.decode("utf-8", errors="replace")
    try:
        message = json.loads(body)
        _valid_message(message)
        with SessionLocal() as db:
            apply_worker_update(db, message)
        retry_attempts.pop(message_key, None)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError, TypeError, KeyError):
        logger.exception("Poison worker update; moving it to the dead-letter queue")
        retry_attempts.pop(message_key, None)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
    except Exception:
        # Retry the same message with bounded exponential backoff.
        attempt = retry_attempts.get(message_key, 0) + 1
        retry_attempts[message_key] = attempt
        logger.exception("Worker update failed transiently; retrying")
        time.sleep(min(2**attempt, 30))
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)


def consume_updates() -> None:
    """Reconnect on broker failures; route malformed messages to the dead-letter queue."""
    delay = 1
    while True:
        connection = None
        try:
            connection = connect()
            channel = connection.channel()
            declare_queues(channel)
            channel.basic_qos(prefetch_count=1)
            delay = 1
            retry_attempts: dict[str, int] = {}

            channel.basic_consume(
                queue=UPDATE_QUEUE,
                on_message_callback=partial(
                    _handle_update, retry_attempts=retry_attempts
                ),
            )
            channel.start_consuming()
        except Exception:
            logger.exception("Update consumer connection failed; reconnecting")
            time.sleep(delay)
            delay = min(delay * 2, 30)
        finally:
            if connection is not None and connection.is_open:
                connection.close()
