"""FastAPI app: logging, CORS setup, a health check and the API routers (one per frontend feature, see app/routers/)."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import get4, images, kpi, segmentation, unknown, v3
from .settings import CORS_ALLOW_ORIGINS, DEV_HOST, DEV_PORT, configure_logging

configure_logging()

app = FastAPI(title="EM QC API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOW_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for module in (get4, kpi, unknown, segmentation, images, v3):
    app.include_router(module.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check used by the frontend's data-readiness line."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    # Running this module directly starts the local development API on DEV_PORT (8000).
    uvicorn.run(app, host=DEV_HOST, port=DEV_PORT)
