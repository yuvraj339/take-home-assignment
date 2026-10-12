"""Environment-backed settings shared by the API and worker processes."""

import os

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://control:control@localhost:5433/control_plane",
)
AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@localhost:5672/%2F")
TASK_QUEUE = "provisioning.tasks"
UPDATE_QUEUE = "provisioning.updates"
DEAD_LETTER_QUEUE = "provisioning.updates.dead"
TASK_DEAD_LETTER_QUEUE = "provisioning.tasks.dead"
