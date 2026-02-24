"""SmartSpend360 — FastAPI Application Entry Point"""

import time
from contextlib import asynccontextmanager

import boto3
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routes import alerts, anomalies, forecast, metrics, pipeline, transactions
from app.core.config import get_settings
from app.core.logging import RequestLoggingMiddleware, configure_logging, get_logger
from app.models.schemas import HealthResponse

_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    log = get_logger("startup")
    log.info(
        "SmartSpend360 starting",
        version=settings.app_version,
        env=settings.app_env,
    )
    yield
    log.info("SmartSpend360 shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="SmartSpend360 API",
        description="Production-grade financial analytics platform API",
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request logging
    app.add_middleware(RequestLoggingMiddleware)

    # Routers
    prefix = "/api/v1"
    app.include_router(transactions.router, prefix=prefix, tags=["Transactions"])
    app.include_router(anomalies.router, prefix=prefix, tags=["Anomalies"])
    app.include_router(forecast.router, prefix=prefix, tags=["Forecast"])
    app.include_router(metrics.router, prefix=prefix, tags=["Metrics"])
    app.include_router(pipeline.router, prefix=prefix, tags=["Pipeline"])
    app.include_router(alerts.router, prefix=prefix, tags=["Alerts"])

    # Health check (no auth)
    @app.get("/health", response_model=HealthResponse, tags=["Health"])
    async def health():
        settings = get_settings()
        aws_ok = _check_aws()
        return HealthResponse(
            status="ok",
            version=settings.app_version,
            uptime_seconds=round(time.time() - _start_time, 1),
            aws_connected=aws_ok,
            environment=settings.app_env,
        )

    # Global error handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        log = get_logger("error")
        log.error("Unhandled exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "path": str(request.url.path)},
        )

    return app


def _check_aws() -> bool:
    try:
        settings = get_settings()
        if not settings.aws_access_key_id:
            return False
        sts = boto3.client(
            "sts",
            region_name=settings.aws_region,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
        )
        sts.get_caller_identity()
        return True
    except Exception:
        return False


app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
