# Tenant Provisioning Control Plane

A small Python control plane for creating and changing tenant environments. FastAPI accepts tenant requests, PostgreSQL stores tenants/tasks, and RabbitMQ delivers work to a separate simulator process.

## Start locally

Requirements: Docker Desktop with Docker Compose.

```bash
git clone take-home-assignment
cd take-home-assignment
docker compose up --build
```

That single command starts PostgreSQL, RabbitMQ, the API, the task worker, and the worker-update consumer (the consumer runs with the API process). API docs are at <http://localhost:8000/docs>; health is at <http://localhost:8000/health>. PostgreSQL is mapped to host port `5435` to avoid colliding with the local databases already using 5433 and 5434; change the left side of the mapping in `compose.yaml` if 5435 is already occupied.

Run the full local quality gate with one command:

```bash
docker compose run --rm --no-deps api sh -c 'ruff check . && ruff format --check . && bandit -q -r app && pytest -q'
```

The tests use an isolated in-memory SQLite database for service-level state and idempotency checks. The running application uses PostgreSQL.

## Architecture

```text
HTTP client
    | REST
    v
FastAPI ---- PostgreSQL (tenants, tasks, outbox, processed-message inbox)
    |                         ^                         |
    | outbox publisher        | worker updates          | committed task event
    v                         |                         v
RabbitMQ: provisioning.tasks ---> worker simulator
RabbitMQ: provisioning.updates <--- worker simulator
```

Tenant and task rows plus an outbox event are committed in one database transaction. A background publisher only sees committed outbox rows, publishes a durable task message with a broker confirmation, then marks the row as published. A process crash after the broker confirms but before that mark commits can publish the same event again; this is at-least-once delivery, so the task ID is stable and worker update handling is idempotent.

Worker updates include a stable `message_id` and `task_id`. The consumer stores message IDs in the same transaction as task/tenant changes, locks the task while applying a result, ignores stale status transitions, retries transient failures, and dead-letters malformed messages. The worker's `message_id` is deterministic (`<task-id>:<status>`), so redelivered tasks do not create duplicate progress changes.

## API

Errors have the shape `{"error":{"code":"...","message":"..."}}`; request validation errors also include `details`.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/tenants` | Start tenant provisioning; returns `202`, tenant body, and `X-Task-ID` |
| `GET` | `/tenants?limit=50&offset=0` | List tenants |
| `GET` | `/tenants/{tenant_id}` | Read tenant state and version |
| `PATCH` | `/tenants/{tenant_id}` | Rename an active tenant and start an update task |
| `DELETE` | `/tenants/{tenant_id}` | Start destruction for an active or failed tenant |
| `GET` | `/tasks?tenant_id=...&limit=50&offset=0` | List tasks |
| `GET` | `/tasks/{task_id}` | Read a task |

Create a tenant and keep the returned task ID:

```bash
curl -i -X POST http://localhost:8000/tenants \
  -H 'Content-Type: application/json' \
  -d '{"slug":"acme-prod","name":"Acme Production"}'
```

The response starts in `provisioning`; the worker moves its deploy task from `accepted` through `in_progress` to `done`, and the consumer moves the tenant to `active`. Observe both resources:

```bash
curl 'http://localhost:8000/tenants?limit=20'
curl 'http://localhost:8000/tasks?tenant_id=<tenant-id>'
curl 'http://localhost:8000/tasks/<task-id>'
```

After the tenant is active, PATCH requires the latest version returned by the tenant endpoint:

```bash
curl -X PATCH http://localhost:8000/tenants/<tenant-id> \
  -H 'Content-Type: application/json' \
  -d '{"version":2,"name":"Acme Production EU"}'
```

Only one update using a given version can win. The database update includes both the expected version and `active` state in its `WHERE` clause; a competing request receives `tenant_version_conflict` or `tenant_update_not_allowed`.

## Status and error behavior

- Tenant create starts `provisioning` with an `accepted` `deploy` task.
- PATCH is allowed only for `active`; it moves to `updating` and creates an `update` task.
- DELETE is allowed for `active` or `failed`; it moves to `destroying` and creates a `destroy` task.
- Successful deploy/update/destroy results move tenants to `active`/`active`/`destroyed`; any failed task moves the tenant to `failed`.
- Slugs are unique in PostgreSQL for the full lifetime of a tenant, including after `destroyed`.
- Contract error codes: `tenant_not_found`, `tenant_already_exists`, `tenant_update_not_allowed`, `tenant_version_conflict`, and `task_not_found`.

## Reproduce failure and ordering cases

Run all worker commands in a second terminal from the project directory. To switch to a worker that always fails, stop the default worker and launch the configured simulator:

```bash
docker compose stop worker
docker compose run --rm --no-deps worker python -m app.workers.simulator --fail-rate=1 --min-delay-ms=100 --max-delay-ms=100
```

Create a tenant in another terminal; its deploy task will fail and the tenant will become `failed`. Stop the one-off worker with Ctrl-C, then restore the default worker:

```bash
docker compose up -d worker
```

To check stale ordering, create a tenant, wait until its deploy task is `done`, then send a late progress update with a different message ID. The task must remain `done` and tenant `active`:

```bash
docker compose exec rabbitmq rabbitmqadmin publish \
  exchange=amq.default routing_key=provisioning.updates \
  payload='{"message_id":"manual-late-progress-1","task_id":"<task-id>","status":"in_progress"}'
```

To see poison-message handling, publish an invalid status. It should be routed to the durable `provisioning.updates.dead` queue rather than stopping the consumer:

```bash
docker compose exec rabbitmq rabbitmqadmin publish \
  exchange=amq.default routing_key=provisioning.updates \
  payload='{"message_id":"bad-1","task_id":"not-a-task","status":"unknown"}'
docker compose exec rabbitmq rabbitmqctl list_queues name messages
```

The update queue and task queue each have a durable dead-letter queue. Duplicate updates can be reproduced by publishing the same `message_id` twice; only its first delivery can mutate state.

## Design choices and trade-offs

- PostgreSQL unique constraints and compare-and-swap updates enforce slug uniqueness and optimistic concurrency in the database, where concurrent API instances share the same authority.
- The outbox avoids publishing events for rolled-back API writes. It provides at-least-once delivery; the task ID and inbox table make retries safe.
- RabbitMQ uses durable queues, persistent messages, and publisher confirms. The local setup favors a clear single-node demonstration over broker clustering.
- `create_all` keeps this take-home easy to start. A production service should use reviewed Alembic migrations, authentication, stricter operational configuration, and metrics.
- The worker simulates provisioning only; real infrastructure calls belong behind its task handler.

## Project layout

```text
app/api/       HTTP routes
app/models/    SQLAlchemy tenant, task, outbox, and inbox tables
app/services/  State rules and transactional operations
app/workers/   Worker simulator, outbox publisher, update consumer
tests/         State-machine and message behavior tests
```
# take-home-assignment
