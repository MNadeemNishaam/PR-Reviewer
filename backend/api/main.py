import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from backend.api.webhook import handle_webhook
from backend.config.settings import settings

# Configure structured logging
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer()
    ]
)

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="PR Reviewer API",
    description="GitHub webhook handler for PR reviews",
    version="1.0.0"
)


@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    logger.info("Starting PR Reviewer API", environment=settings.environment)


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    logger.info("Shutting down PR Reviewer API")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "PR Reviewer API",
        "status": "running",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/api/webhook")
async def webhook(request: Request):
    """GitHub webhook endpoint."""
    return await handle_webhook(request)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    logger.error("Unhandled exception", error=str(exc), path=request.url.path)
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "detail": str(exc)}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.is_development
    )

