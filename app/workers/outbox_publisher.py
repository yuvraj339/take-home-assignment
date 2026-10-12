"""Publish committed outbox events to RabbitMQ with publisher confirms."""

import logging
import time
from datetime import UTC, datetime

import pika
from sqlalchemy import select

from app.config import TASK_QUEUE
from app.db import SessionLocal
from app.messaging import connect, declare_queues
from app.models.outbox import OutboxEvent

logger = logging.getLogger(__name__)


def run_publisher() -> None:
    """Continuously publish committed events; unmarked rows retry after failures."""
    delay = 1
    while True:
        connection = None
        try:
            connection = connect()
            channel = connection.channel()
            declare_queues(channel)
            channel.confirm_delivery()
            delay = 1
            while connection.is_open:
                with SessionLocal.begin() as db:
                    event = db.scalar(
                        select(OutboxEvent)
                        .where(OutboxEvent.published_at.is_(None))
                        .order_by(OutboxEvent.created_at)
                        .with_for_update(skip_locked=True)
                        .limit(1)
                    )
                    if event is None:
                        time.sleep(0.4)
                        continue
                    channel.basic_publish(
                        exchange="",
                        routing_key=TASK_QUEUE,
                        body=event.payload,
                        properties=pika.BasicProperties(
                            delivery_mode=2,
                            content_type="application/json",
                            message_id=event.id,
                        ),
                        mandatory=True,
                    )
                    # A crash after broker confirmation and before DB commit can cause
                    # redelivery; consumers deduplicate using the stable task ID.
                    event.published_at = datetime.now(UTC)
        except Exception:
            logger.exception("Outbox publisher connection failed; retrying")
            time.sleep(delay)
            delay = min(delay * 2, 30)
        finally:
            if connection is not None and connection.is_open:
                connection.close()
