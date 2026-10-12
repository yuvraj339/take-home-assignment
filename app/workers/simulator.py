"""Provisioning worker simulator, configurable for repeatable failure scenarios."""

import argparse
import json
import logging
import secrets
import time

import pika

from app.config import TASK_QUEUE, UPDATE_QUEUE
from app.messaging import connect, declare_queues

logger = logging.getLogger(__name__)
random_source = secrets.SystemRandom()


def run_worker(fail_rate: float, min_delay_ms: int, max_delay_ms: int) -> None:
    delay = 1
    while True:
        connection = None
        try:
            connection = connect()
            channel = connection.channel()
            declare_queues(channel)
            channel.confirm_delivery()
            channel.basic_qos(prefetch_count=1)
            delay = 1

            def publish_update(channel, task_id: str, state: str) -> None:
                body = json.dumps(
                    {
                        # Deterministic IDs make repeated processing of a task safe.
                        "message_id": f"{task_id}:{state}",
                        "task_id": task_id,
                        "status": state,
                    }
                )
                channel.basic_publish(
                    exchange="",
                    routing_key=UPDATE_QUEUE,
                    body=body,
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        content_type="application/json",
                        message_id=f"{task_id}:{state}",
                    ),
                    mandatory=True,
                )

            def handle(ch, method, properties, body, channel=channel):
                try:
                    task = json.loads(body)
                    task_id = task["id"]
                    if task.get("type") not in {"deploy", "update", "destroy"}:
                        raise ValueError("unknown task type")
                    publish_update(channel, task_id, "in_progress")
                    time.sleep(random_source.randint(min_delay_ms, max_delay_ms) / 1000)
                    result = "failed" if random_source.random() < fail_rate else "done"
                    publish_update(channel, task_id, result)
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                except (
                    json.JSONDecodeError,
                    UnicodeDecodeError,
                    KeyError,
                    TypeError,
                    ValueError,
                ):
                    logger.exception(
                        "Invalid task; rejecting to the task queue dead-letter policy"
                    )
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                except Exception:
                    logger.exception("Task processing failed; requeueing")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

            channel.basic_consume(queue=TASK_QUEUE, on_message_callback=handle)
            channel.start_consuming()
        except Exception:
            logger.exception("Worker broker connection failed; reconnecting")
            time.sleep(delay)
            delay = min(delay * 2, 30)
        finally:
            if connection is not None and connection.is_open:
                connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fail-rate",
        type=float,
        default=0.0,
        help="Probability from 0 to 1 that a task fails",
    )
    parser.add_argument(
        "--min-delay-ms", type=int, default=300, help="Shortest simulated task delay"
    )
    parser.add_argument(
        "--max-delay-ms", type=int, default=900, help="Longest simulated task delay"
    )
    args = parser.parse_args()
    if not 0 <= args.fail_rate <= 1:
        parser.error("--fail-rate must be between 0 and 1")
    if args.min_delay_ms < 0 or args.max_delay_ms < args.min_delay_ms:
        parser.error("delay values must be non-negative and max must be >= min")
    logging.basicConfig(level=logging.INFO)
    run_worker(args.fail_rate, args.min_delay_ms, args.max_delay_ms)


if __name__ == "__main__":
    main()
