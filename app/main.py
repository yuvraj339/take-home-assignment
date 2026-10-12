"""FastAPI application entry point."""

import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.tasks import router as tasks_router
from app.api.tenants import router as tenants_router
from app.db import init_db
from app.services.tenant_service import DomainError
from app.workers.consumer import consume_updates
from app.workers.outbox_publisher import run_publisher

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    # Broker outages do not prevent HTTP startup; these loops reconnect with backoff.
    threading.Thread(target=run_publisher, name="outbox-publisher", daemon=True).start()
    threading.Thread(
        target=consume_updates, name="update-consumer", daemon=True
    ).start()
    yield


app = FastAPI(
    title="Tenant Provisioning Control Plane", version="1.0.0", lifespan=lifespan
)
app.include_router(tenants_router)
app.include_router(tasks_router)


@app.get("/health", tags=["system"])
def health_check():
    return {"status": "ok"}


@app.exception_handler(DomainError)
async def domain_error_handler(_: Request, exc: DomainError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
                "details": jsonable_encoder(exc.errors()),
            }
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(exc.detail)}},
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(_: Request, exc: Exception):
    logging.getLogger(__name__).exception("Unexpected API error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "internal_error",
                "message": "An unexpected error occurred",
            }
        },
    )
