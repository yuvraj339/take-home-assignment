"""RabbitMQ connection and durable queue declarations."""

import pika

from app.config import (
    AMQP_URL,
    DEAD_LETTER_QUEUE,
    TASK_DEAD_LETTER_QUEUE,
    TASK_QUEUE,
    UPDATE_QUEUE,
)


def connect() -> pika.BlockingConnection:
    return pika.BlockingConnection(pika.URLParameters(AMQP_URL))


def declare_queues(channel) -> None:
    channel.queue_declare(queue=TASK_DEAD_LETTER_QUEUE, durable=True)
    channel.queue_declare(
        queue=TASK_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": TASK_DEAD_LETTER_QUEUE,
        },
    )
    channel.queue_declare(queue=DEAD_LETTER_QUEUE, durable=True)
    channel.queue_declare(
        queue=UPDATE_QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": DEAD_LETTER_QUEUE,
        },
    )
